use std::collections::{BTreeSet, HashMap, HashSet};
use std::ffi::{c_char, c_void, CStr, CString};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, Weak, mpsc};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use ctrs_proto::{FsEvent, FsEventKind};
use super::engine::Engine;

const MUST_SCAN_SUB_DIRS: u32 = 0x1;
const USER_DROPPED: u32 = 0x2;
const KERNEL_DROPPED: u32 = 0x4;
const HISTORY_DONE: u32 = 0x10;
const ROOT_CHANGED: u32 = 0x20;
const MOUNT: u32 = 0x40;
const UNMOUNT: u32 = 0x80;
const CREATED: u32 = 0x100;
const REMOVED: u32 = 0x200;
const INODE: u32 = 0x400;
const RENAMED: u32 = 0x800;
const MODIFIED: u32 = 0x1000;
const XATTR: u32 = 0x8000;

fn classify(flags: u32, exists: bool) -> Vec<FsEventKind> {
    if flags & (CREATED | REMOVED | INODE | RENAMED | MODIFIED | XATTR) == 0 { return Vec::new(); }
    if !exists { return vec![FsEventKind::Removed]; }
    let mut kinds = Vec::new();
    if flags & (CREATED | RENAMED) != 0 { kinds.push(FsEventKind::Created); }
    if flags & (MODIFIED | INODE | XATTR) != 0 { kinds.push(FsEventKind::Modified); }
    kinds
}

/// Entries a reconciliation walk visits before it stops.
const RECONCILE_LIMIT: usize = 20_000;
/// How far before the last delivered batch a reconciliation looks, for
/// timestamp granularity and the stream's own latency.
const RECONCILE_SLACK: Duration = Duration::from_secs(2);

/// The bind directories under which FSEvents says it may have missed
/// changes: all of them when it dropped events, else those at or under
/// (or containing) the flagged path.
fn lost_under(flags: u32, path: &Path, directories: &HashSet<PathBuf>) -> Vec<PathBuf> {
    if flags & (USER_DROPPED | KERNEL_DROPPED) != 0 {
        return directories.iter().cloned().collect();
    }
    if flags & (MUST_SCAN_SUB_DIRS | ROOT_CHANGED | MOUNT | UNMOUNT) == 0 {
        return Vec::new();
    }
    directories.iter().filter_map(|root| {
        if path.starts_with(root) { Some(path.to_path_buf()) } else if root.starts_with(path) { Some(root.clone()) } else { None }
    }).collect()
}

/// Changes under `dir` whose ctime is at or after `since`, for the guest
/// to recheck: directories as created, everything else as modified.
/// Returns whether the walk finished within `limit` entries.
fn reconcile(dir: &Path, since: SystemTime, limit: usize, out: &mut Vec<(FsEventKind, String)>) -> bool {
    let cutoff = since.duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs() as i64);
    let mut stack = vec![dir.to_path_buf()];
    let mut seen = 0;
    while let Some(next) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&next) else { continue };
        for entry in entries.flatten() {
            seen += 1;
            if seen > limit { return false; }
            let path = entry.path();
            let Ok(meta) = std::fs::symlink_metadata(&path) else { continue };
            let changed = meta.ctime() >= cutoff;
            if meta.is_dir() {
                if changed { if let Some(p) = path.to_str() { out.push((FsEventKind::Created, p.to_owned())); } }
                stack.push(path);
            } else if changed {
                if let Some(p) = path.to_str() { out.push((FsEventKind::Modified, p.to_owned())); }
            }
        }
    }
    true
}

#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub(super) struct Root { path: PathBuf, file: bool }

#[derive(Default)]
struct Roots { containers: HashMap<String, Vec<Root>>, counts: HashMap<Root, usize> }
impl Roots {
    fn remove(&mut self, id: &str) {
        if let Some(roots) = self.containers.remove(id) {
            for root in roots {
                let count = self.counts.get_mut(&root).unwrap();
                *count -= 1;
                if *count == 0 { self.counts.remove(&root); }
            }
        }
    }
    fn insert(&mut self, id: String, roots: Vec<Root>) {
        self.remove(&id);
        for root in &roots { *self.counts.entry(root.clone()).or_default() += 1; }
        self.containers.insert(id, roots);
    }
    fn accepts(&self, path: &Path) -> bool {
        self.counts.keys().any(|r| if r.file { path == r.path } else { path.starts_with(&r.path) })
    }
    fn directories(&self) -> HashSet<PathBuf> {
        self.counts.keys().filter_map(|r| if r.file { r.path.parent().map(Path::to_path_buf) } else { Some(r.path.clone()) }).filter(|p| p != Path::new("/")).collect()
    }
}

enum Change { Add(String, Vec<Root>), Remove(String), Clear }
pub struct Watcher(mpsc::Sender<Change>);
impl Watcher {
    pub fn start(engine: Weak<Engine>) -> Self {
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let roots = Arc::new(Mutex::new(Roots::default()));
            let state = Arc::new(Delivery::default());
            let mut stream = None;
            let mut watched = HashSet::new();
            while let Ok(change) = rx.recv() {
                let (next, directories) = {
                    let mut roots = roots.lock().unwrap();
                    match change { Change::Add(id, paths) => roots.insert(id, paths), Change::Remove(id) => roots.remove(&id), Change::Clear => *roots = Roots::default() }
                    (roots.counts.keys().cloned().collect::<HashSet<_>>(), roots.directories())
                };
                if next != watched {
                    if stream.take().is_none() { state.last_id.store(0, Ordering::Relaxed); }
                    if !directories.is_empty() {
                        // Replaying from the last event seen covers the
                        // gap between the old stream and this one.
                        stream = Stream::start(&directories, roots.clone(), engine.clone(), state.clone());
                        if stream.is_none() {
                            crate::diag::warn!("could not start bind mount FSEvents stream");
                            state.undelivered.store(true, Ordering::Relaxed);
                        }
                    }
                    watched = next;
                }
            }
        });
        Self(tx)
    }
    pub fn roots(mounts: &[String]) -> Vec<Root> {
        mounts.iter().filter_map(|m| {
            let source = m.split('\t').next()?.strip_prefix("/mnt/mac")?;
            if !source.starts_with('/') { return None; }
            let path = std::fs::canonicalize(source).ok()?;
            let file = !path.is_dir();
            if path == Path::new("/") || (file && path.parent() == Some(Path::new("/"))) { return None; }
            Some(Root { path, file })
        }).collect::<HashSet<_>>().into_iter().collect()
    }
    pub fn add(&self, id: &str, roots: Vec<Root>) {
        let _ = self.0.send(Change::Add(id.to_owned(), roots));
    }
    pub fn remove(&self, id: &str) { let _ = self.0.send(Change::Remove(id.to_owned())); }
    pub fn clear(&self) { let _ = self.0.send(Change::Clear); }
}

type Ref = *const c_void;
type StreamRef = *mut c_void;
#[repr(C)]
struct Context { version: isize, info: *mut c_void, retain: Option<unsafe extern "C" fn(*const c_void) -> *const c_void>, release: Option<unsafe extern "C" fn(*const c_void)>, description: Option<unsafe extern "C" fn(*const c_void) -> Ref> }
#[link(name = "CoreServices", kind = "framework")]
unsafe extern "C" {
    fn FSEventStreamCreate(allocator: Ref, callback: unsafe extern "C" fn(StreamRef, *mut c_void, usize, *mut c_void, *const u32, *const u64), context: *mut Context, paths: Ref, since: u64, latency: f64, flags: u32) -> StreamRef;
    fn FSEventStreamSetDispatchQueue(stream: StreamRef, queue: *mut c_void);
    fn FSEventStreamStart(stream: StreamRef) -> bool;
    fn FSEventStreamStop(stream: StreamRef);
    fn FSEventStreamInvalidate(stream: StreamRef);
    fn FSEventStreamRelease(stream: StreamRef);
}
#[link(name = "CoreFoundation", kind = "framework")]
unsafe extern "C" {
    fn CFStringCreateWithCString(allocator: Ref, string: *const c_char, encoding: u32) -> Ref;
    fn CFArrayCreate(allocator: Ref, values: *const Ref, count: isize, callbacks: Ref) -> Ref;
    fn CFRelease(value: Ref);
}
unsafe extern "C" {
    fn dispatch_queue_create(label: *const c_char, attr: Ref) -> *mut c_void;
    fn dispatch_sync_f(queue: *mut c_void, context: *mut c_void, work: unsafe extern "C" fn(*mut c_void));
    fn dispatch_release(object: *mut c_void);
}
/// What the guest has been sent, across stream restarts.
struct Delivery {
    /// The last FSEvents event id seen (0 before any).
    last_id: AtomicU64,
    /// When the guest last had every event.
    delivered_at: Mutex<SystemTime>,
    /// Events were lost since then: the next batch starts with rescans.
    undelivered: AtomicBool,
    test_drop_gate: Option<PathBuf>,
}
impl Default for Delivery {
    fn default() -> Self {
        Self { last_id: AtomicU64::new(0), delivered_at: Mutex::new(SystemTime::now()), undelivered: AtomicBool::new(false), test_drop_gate: std::env::var_os("CTRS_TEST_FSEVENTS_GATE").map(PathBuf::from) }
    }
}

struct Callback { roots: Arc<Mutex<Roots>>, engine: Weak<Engine>, state: Arc<Delivery> }
struct Stream { stream: StreamRef, queue: *mut c_void, callback: *mut Callback }
impl Stream {
    fn start(paths: &HashSet<PathBuf>, roots: Arc<Mutex<Roots>>, engine: Weak<Engine>, state: Arc<Delivery>) -> Option<Self> {
        let strings: Vec<_> = paths.iter().filter_map(|p| CString::new(p.to_str()?).ok()).collect();
        // SAFETY: CoreFoundation copies the strings and the stream copies the array.
        unsafe {
            let values: Vec<Ref> = strings.iter().map(|s| CFStringCreateWithCString(std::ptr::null(), s.as_ptr(), 0x08000100)).filter(|p| !p.is_null()).collect();
            let array = CFArrayCreate(std::ptr::null(), values.as_ptr(), values.len() as isize, std::ptr::null());
            let since = match state.last_id.load(Ordering::Relaxed) { 0 => u64::MAX, id => id };
            let callback = Box::into_raw(Box::new(Callback { roots, engine, state }));
            let mut context = Context { version: 0, info: callback.cast(), retain: None, release: None, description: None };
            let stream = FSEventStreamCreate(std::ptr::null(), events, &mut context, array, since, 0.01, 0x10 | 0x2 | 0x4);
            CFRelease(array);
            for value in values { CFRelease(value); }
            if stream.is_null() { drop(Box::from_raw(callback)); return None; }
            let queue = dispatch_queue_create(c"ctrs.fsevents".as_ptr(), std::ptr::null());
            FSEventStreamSetDispatchQueue(stream, queue);
            if !FSEventStreamStart(stream) { FSEventStreamInvalidate(stream); FSEventStreamRelease(stream); dispatch_release(queue); drop(Box::from_raw(callback)); return None; }
            Some(Self { stream, queue, callback })
        }
    }
}
unsafe extern "C" fn drained(_: *mut c_void) {}
impl Drop for Stream {
    fn drop(&mut self) {
        // SAFETY: draining the serial queue ensures no callback uses the context after it is freed.
        unsafe { FSEventStreamStop(self.stream); FSEventStreamInvalidate(self.stream); dispatch_sync_f(self.queue, std::ptr::null_mut(), drained); FSEventStreamRelease(self.stream); dispatch_release(self.queue); drop(Box::from_raw(self.callback)); }
    }
}
unsafe extern "C" fn events(_: StreamRef, info: *mut c_void, count: usize, paths: *mut c_void, flags: *const u32, ids: *const u64) {
    // SAFETY: FSEvents supplies arrays valid for this callback and the stream owns the context.
    let (callback, paths, flags, ids) = unsafe { (&*(info as *const Callback), std::slice::from_raw_parts(paths as *const *const c_char, count), std::slice::from_raw_parts(flags, count), std::slice::from_raw_parts(ids, count)) };
    let state = &callback.state;
    if state.test_drop_gate.as_ref().is_some_and(|path| path.exists()) {
        for id in ids { state.last_id.fetch_max(*id, Ordering::Relaxed); }
        if !state.undelivered.swap(true, Ordering::Relaxed) {
            crate::diag::warn!("test gate suppressed bind mount change notifications");
        }
        return;
    }
    let started = SystemTime::now();
    let since = *state.delivered_at.lock().unwrap_or_else(|e| e.into_inner());
    let mut seen = HashSet::new();
    let mut ordered = Vec::new();
    let mut lost = BTreeSet::new();
    {
        let roots = callback.roots.lock().unwrap();
        let directories = roots.directories();
        if state.undelivered.swap(false, Ordering::Relaxed) { lost.extend(directories.iter().cloned()); }
        for ((path, flags), id) in paths.iter().zip(flags).zip(ids) {
            state.last_id.fetch_max(*id, Ordering::Relaxed);
            if flags & HISTORY_DONE != 0 { continue; }
            // SAFETY: each path is a NUL-terminated FSEvents path.
            let Ok(path) = unsafe { CStr::from_ptr(*path) }.to_str() else { continue };
            lost.extend(lost_under(*flags, Path::new(path), &directories));
            if !roots.accepts(Path::new(path)) { continue; }
            for kind in classify(*flags, Path::new(path).exists()) {
                if seen.insert((kind, path.to_owned())) { ordered.push((kind, path.to_owned())); }
            }
        }
    }
    let mut rescans = Vec::new();
    for dir in &lost {
        let Some(p) = dir.to_str() else { continue };
        rescans.push((FsEventKind::Rescan, p.to_owned()));
        let from = since.checked_sub(RECONCILE_SLACK).unwrap_or(UNIX_EPOCH);
        if !reconcile(dir, from, RECONCILE_LIMIT, &mut rescans) {
            crate::diag::warn!("bind mount changes were lost; reconciliation stopped early", dir = p, limit = RECONCILE_LIMIT);
        }
    }
    if !lost.is_empty() { crate::diag::warn!("bind mount change notifications were lost; the guest revalidates", dirs = lost.len()); }
    rescans.extend(ordered);
    let Some(engine) = callback.engine.upgrade() else { return };
    let events: Vec<_> = rescans.iter().map(|(kind, path)| FsEvent { kind: *kind, path }).collect();
    if engine.send_fs_events(&events) {
        *state.delivered_at.lock().unwrap_or_else(|e| e.into_inner()) = started;
    } else {
        state.undelivered.store(true, Ordering::Relaxed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn classification() {
        assert_eq!(classify(CREATED | MODIFIED, true), vec![FsEventKind::Created, FsEventKind::Modified]);
        assert_eq!(classify(RENAMED, false), vec![FsEventKind::Removed]);
        assert_eq!(classify(INODE | XATTR, true), vec![FsEventKind::Modified]);
        assert!(classify(0x10, false).is_empty());
    }
    #[test]
    fn lost_events_name_the_bind_directories_to_rescan() {
        let dirs: HashSet<PathBuf> = ["/Users/a/proj".into(), "/Users/b".into()].into_iter().collect();
        let mut all = lost_under(KERNEL_DROPPED, Path::new("/"), &dirs);
        all.sort();
        assert_eq!(all, vec![PathBuf::from("/Users/a/proj"), PathBuf::from("/Users/b")]);
        assert_eq!(lost_under(MUST_SCAN_SUB_DIRS, Path::new("/Users/a/proj/src"), &dirs), vec![PathBuf::from("/Users/a/proj/src")]);
        assert_eq!(lost_under(ROOT_CHANGED, Path::new("/Users/a"), &dirs), vec![PathBuf::from("/Users/a/proj")]);
        assert!(lost_under(MUST_SCAN_SUB_DIRS, Path::new("/Users/c"), &dirs).is_empty());
        assert!(lost_under(MODIFIED, Path::new("/Users/b/x"), &dirs).is_empty());
    }
    #[test]
    fn reconciliation_reports_recent_changes_within_its_limit() {
        let base = std::env::temp_dir().join(format!("ctrs-reconcile-{}", std::process::id()));
        std::fs::create_dir_all(base.join("sub")).unwrap();
        std::fs::write(base.join("sub/new"), b"x").unwrap();
        let mut out = Vec::new();
        assert!(reconcile(&base, SystemTime::now() - Duration::from_secs(60), 100, &mut out));
        let sub = base.join("sub").to_str().unwrap().to_owned();
        let new = base.join("sub/new").to_str().unwrap().to_owned();
        assert!(out.contains(&(FsEventKind::Created, sub)));
        assert!(out.contains(&(FsEventKind::Modified, new)));
        out.clear();
        assert!(reconcile(&base, SystemTime::now() + Duration::from_secs(60), 100, &mut out));
        assert!(out.is_empty());
        assert!(!reconcile(&base, UNIX_EPOCH, 1, &mut out));
        std::fs::remove_dir_all(&base).unwrap();
    }
    #[test]
    fn root_refcounts_and_file_filter() {
        let root = Root { path: "/Users/a".into(), file: false };
        let file = Root { path: "/Users/b/file".into(), file: true };
        let mut roots = Roots::default();
        roots.insert("a".into(), vec![root.clone(), file]);
        roots.insert("b".into(), vec![root.clone()]);
        assert!(roots.accepts(Path::new("/Users/b/file")));
        assert!(!roots.accepts(Path::new("/Users/b/other")));
        roots.remove("a");
        assert_eq!(roots.counts.get(&root), Some(&1));
        assert!(roots.accepts(Path::new("/Users/a/x")));
        assert!(!roots.accepts(Path::new("/Users/b/file")));
        roots.remove("b");
        assert!(roots.directories().is_empty());
    }
}
