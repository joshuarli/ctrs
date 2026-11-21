use std::collections::{BTreeSet, HashMap, HashSet};
use std::ffi::{c_char, c_void, CStr, CString};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, Weak, mpsc};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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

struct Reconcile {
    roots: std::vec::IntoIter<Root>,
    stack: Vec<std::fs::ReadDir>,
    cutoff: i64,
    device: Option<u64>,
    visited: usize,
    warned: bool,
}
impl Reconcile {
    fn new(roots: Vec<Root>, since: SystemTime) -> Self {
        let roots = roots.iter().filter(|root| !roots.iter().any(|other| !other.file && other.path != root.path && root.path.starts_with(&other.path))).cloned().collect::<Vec<_>>();
        Self { roots: roots.into_iter(), stack: Vec::new(), cutoff: since.duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs() as i64), device: None, visited: 0, warned: false }
    }
    fn warn(&mut self, error: &std::io::Error) {
        if !self.warned && error.kind() != std::io::ErrorKind::NotFound {
            crate::diag::warn!("bind mount reconciliation skipped an unreadable entry", error = error);
            self.warned = true;
        }
    }
    fn turn(&mut self, limit: usize, out: &mut Vec<(FsEventKind, String)>) -> bool {
        let mut visited = 0;
        while visited < limit {
            if self.visited >= RECONCILE_LIMIT {
                crate::diag::warn!("bind mount reconciliation reached its entry limit", limit = RECONCILE_LIMIT);
                return true;
            }
            if self.stack.is_empty() {
                let Some(root) = self.roots.next() else { return true };
                visited += 1;
                self.visited += 1;
                if root.file {
                    match std::fs::symlink_metadata(&root.path) {
                        Ok(meta) if meta.ctime() >= self.cutoff => {
                            if let Some(path) = root.path.to_str() { out.push((FsEventKind::Modified, path.to_owned())); }
                        }
                        Ok(_) => {},
                        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {},
                        Err(e) => self.warn(&e),
                    }
                    continue;
                }
                self.device = match std::fs::symlink_metadata(&root.path) {
                    Ok(meta) => Some(meta.dev()),
                    Err(e) => { self.warn(&e); continue; }
                };
                match std::fs::read_dir(root.path) {
                    Ok(dir) => self.stack.push(dir),
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {},
                    Err(e) => self.warn(&e),
                }
                continue;
            }
            visited += 1;
            self.visited += 1;
            let Some(entry) = self.stack.last_mut().unwrap().next() else { self.stack.pop(); continue };
            let entry = match entry { Ok(entry) => entry, Err(e) => { self.warn(&e); continue; } };
            let path = entry.path();
            let meta = match std::fs::symlink_metadata(&path) {
                Ok(meta) => meta,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
                Err(e) => { self.warn(&e); continue; },
            };
            if Some(meta.dev()) != self.device { continue; }
            if meta.ctime() >= self.cutoff
                && let Some(p) = path.to_str() { out.push((if meta.is_dir() { FsEventKind::Created } else { FsEventKind::Modified }, p.to_owned())); }
            if meta.is_dir() {
                match std::fs::read_dir(path) {
                    Ok(dir) => self.stack.push(dir),
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {},
                    Err(e) => self.warn(&e),
                }
            }
        }
        false
    }
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

enum Change { Wake }
pub struct Watcher { changes: mpsc::SyncSender<Change>, roots: Arc<Mutex<Roots>>, stopping: Arc<AtomicBool> }
impl Watcher {
    pub fn start(engine: Weak<Engine>) -> Self {
        let (tx, rx) = mpsc::sync_channel(1);
        let roots = Arc::new(Mutex::new(Roots::default()));
        let worker_roots = roots.clone();
        let wake = tx.clone();
        let stopping = Arc::new(AtomicBool::new(false));
        let stopped = stopping.clone();
        std::thread::spawn(move || {
            let roots = worker_roots;
            let state = Arc::new(Delivery::default());
            let mut stream = None;
            let mut watched = HashSet::new();
            let mut recovery: Option<Reconcile> = None;
            let mut retry_at = Instant::now();
            let mut pending_entries: Option<(Vec<(FsEventKind, String)>, bool)> = None;
            loop {
                if stopped.load(Ordering::Acquire) { break; }
                let waiting = recovery.is_some() || state.reconcile_from.lock().unwrap().is_some();
                let change = if waiting { rx.recv_timeout(Duration::from_millis(20)) } else { rx.recv().map_err(|_| mpsc::RecvTimeoutError::Disconnected) };
                match change {
                    Ok(Change::Wake) => {
                        let (next, directories) = {
                            let roots = roots.lock().unwrap();
                            (roots.counts.keys().cloned().collect::<HashSet<_>>(), roots.directories())
                        };
                        if next != watched {
                            if stream.take().is_none() { state.last_id.store(0, Ordering::Relaxed); }
                            if !directories.is_empty() {
                                // Replaying from the last event seen covers the
                                // gap between the old stream and this one.
                                stream = Stream::start(&directories, roots.clone(), engine.clone(), state.clone(), wake.clone());
                                if stream.is_none() {
                                    crate::diag::warn!("could not start bind mount FSEvents stream");
                                    state.undelivered.store(true, Ordering::Relaxed);
                                }
                            }
                            watched = next;
                        }
                    }
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                    Err(mpsc::RecvTimeoutError::Disconnected) => break,
                }
                if recovery.is_none() && Instant::now() >= retry_at {
                    let pending = state.reconcile_from.lock().unwrap().take();
                    if let Some(since) = pending {
                        let (dirs, targets) = {
                            let roots = roots.lock().unwrap();
                            (roots.directories().into_iter().collect::<Vec<_>>(), roots.counts.keys().cloned().collect::<Vec<_>>())
                        };
                        let rescans: Vec<_> = dirs.iter().filter_map(|dir| dir.to_str().map(|path| FsEvent { kind: FsEventKind::Rescan, path })).collect();
                        let needs_rescan = state.undelivered.swap(false, Ordering::Relaxed);
                        if !needs_rescan || engine.upgrade().is_some_and(|engine| engine.send_fs_events(&rescans)) {
                            recovery = Some(Reconcile::new(targets, since));
                        } else {
                            crate::diag::warn!("bind mount rescan delivery failed; retrying");
                            state.undelivered.store(true, Ordering::Relaxed);
                            state.schedule_reconcile(since);
                            retry_at = Instant::now() + Duration::from_secs(1);
                        }
                    }
                }
                if let Some(walk) = &mut recovery {
                    if Instant::now() < retry_at { continue; }
                    if pending_entries.is_none() {
                        let mut entries = Vec::new();
                        let done = walk.turn(128, &mut entries);
                        pending_entries = Some((entries, done));
                    }
                    let (entries, done) = pending_entries.as_ref().unwrap();
                    let events: Vec<_> = entries.iter().map(|(kind, path)| FsEvent { kind: *kind, path }).collect();
                    if engine.upgrade().is_some_and(|engine| engine.send_fs_events(&events)) {
                        let done = *done;
                        pending_entries = None;
                        if done { recovery = None; }
                    } else {
                        crate::diag::warn!("bind mount reconciliation delivery failed; retrying");
                        retry_at = Instant::now() + Duration::from_secs(1);
                    }
                }
            }
        });
        Self { changes: tx, roots, stopping }
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
        self.roots.lock().unwrap().insert(id.to_owned(), roots);
        let _ = self.changes.try_send(Change::Wake);
    }
    pub fn remove(&self, id: &str) { self.roots.lock().unwrap().remove(id); let _ = self.changes.try_send(Change::Wake); }
    pub fn clear(&self) { *self.roots.lock().unwrap() = Roots::default(); let _ = self.changes.try_send(Change::Wake); }
}
impl Drop for Watcher {
    fn drop(&mut self) {
        self.stopping.store(true, Ordering::Release);
        let _ = self.changes.try_send(Change::Wake);
    }
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
    reconcile_from: Mutex<Option<SystemTime>>,
    test_drop_gate: Option<PathBuf>,
    test_overflow_events: Mutex<Option<Vec<(FsEventKind, String)>>>,
}
impl Default for Delivery {
    fn default() -> Self {
        Self { last_id: AtomicU64::new(0), delivered_at: Mutex::new(SystemTime::now()), undelivered: AtomicBool::new(false), reconcile_from: Mutex::new(None), test_drop_gate: std::env::var_os("CTRS_TEST_FSEVENTS_GATE").map(PathBuf::from), test_overflow_events: Mutex::new(None) }
    }
}
impl Delivery {
    fn schedule_reconcile(&self, since: SystemTime) {
        let mut pending = self.reconcile_from.lock().unwrap();
        *pending = Some(pending.map_or(since, |old| old.min(since)));
    }
}

struct Callback { roots: Arc<Mutex<Roots>>, engine: Weak<Engine>, state: Arc<Delivery>, wake: mpsc::SyncSender<Change> }
struct Stream { stream: StreamRef, queue: *mut c_void, callback: *mut Callback }
impl Stream {
    fn start(paths: &HashSet<PathBuf>, roots: Arc<Mutex<Roots>>, engine: Weak<Engine>, state: Arc<Delivery>, wake: mpsc::SyncSender<Change>) -> Option<Self> {
        let strings: Vec<_> = paths.iter().filter_map(|p| CString::new(p.to_str()?).ok()).collect();
        // SAFETY: CoreFoundation copies the strings and the stream copies the array.
        unsafe {
            let values: Vec<Ref> = strings.iter().map(|s| CFStringCreateWithCString(std::ptr::null(), s.as_ptr(), 0x08000100)).filter(|p| !p.is_null()).collect();
            let array = CFArrayCreate(std::ptr::null(), values.as_ptr(), values.len() as isize, std::ptr::null());
            let since = match state.last_id.load(Ordering::Relaxed) { 0 => u64::MAX, id => id };
            let callback = Box::into_raw(Box::new(Callback { roots, engine, state, wake }));
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
    if let Some(gate) = &state.test_drop_gate {
        let mut pending = state.test_overflow_events.lock().unwrap();
        if gate.with_extension("overflow").exists() {
            let events = pending.get_or_insert_with(|| {
                crate::diag::warn!("test gate collecting bind mount changes for guest overflow");
                Vec::new()
            });
            let roots = callback.roots.lock().unwrap();
            for ((path, flags), id) in paths.iter().zip(flags).zip(ids) {
                state.last_id.fetch_max(*id, Ordering::Relaxed);
                let Ok(path) = unsafe { CStr::from_ptr(*path) }.to_str() else { continue };
                if roots.accepts(Path::new(path)) {
                    for kind in classify(*flags, Path::new(path).exists()) {
                        if events.len() < 4096 { events.push((kind, path.to_owned())); }
                        else { crate::diag::warn!("test overflow gate capacity exceeded"); }
                    }
                }
            }
            return;
        }
        let captured = pending.take();
        drop(pending);
        if let Some(events) = captured {
            for (kind, path) in &events {
                crate::diag::warn!("test gate captured bind mount event", kind = *kind as u8, path = path);
            }
            let mut batch = vec![FsEvent { kind: FsEventKind::Modified, path: "/" }; 10_000];
            batch.extend(events.iter().map(|(kind, path)| FsEvent { kind: *kind, path }));
            if let Some(engine) = callback.engine.upgrade()
                && !engine.send_fs_events(&batch) { state.undelivered.store(true, Ordering::Relaxed); }
            crate::diag::warn!("test gate delivered guest overflow batch", events = events.len());
        }
    }
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
    }
    if !lost.is_empty() {
        crate::diag::warn!("bind mount change notifications were lost; the guest revalidates", dirs = lost.len());
    }
    rescans.extend(ordered);
    let Some(engine) = callback.engine.upgrade() else { return };
    let events: Vec<_> = rescans.iter().map(|(kind, path)| FsEvent { kind: *kind, path }).collect();
    if engine.send_fs_events(&events) {
        if !lost.is_empty() {
            let from = since.checked_sub(RECONCILE_SLACK).unwrap_or(UNIX_EPOCH);
            state.schedule_reconcile(from);
            let _ = callback.wake.try_send(Change::Wake);
        }
        *state.delivered_at.lock().unwrap_or_else(|e| e.into_inner()) = started;
    } else {
        state.undelivered.store(true, Ordering::Relaxed);
        state.schedule_reconcile(since.checked_sub(RECONCILE_SLACK).unwrap_or(UNIX_EPOCH));
        let _ = callback.wake.try_send(Change::Wake);
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
        let root = Root { path: base.clone(), file: false };
        assert!(Reconcile::new(vec![root.clone()], SystemTime::now() - Duration::from_secs(60)).turn(100, &mut out));
        let sub = base.join("sub").to_str().unwrap().to_owned();
        let new = base.join("sub/new").to_str().unwrap().to_owned();
        assert!(out.contains(&(FsEventKind::Created, sub)));
        assert!(out.contains(&(FsEventKind::Modified, new.clone())));
        out.clear();
        assert!(Reconcile::new(vec![root.clone()], SystemTime::now() + Duration::from_secs(60)).turn(100, &mut out));
        assert!(out.is_empty());
        let mut walk = Reconcile::new(vec![root], UNIX_EPOCH);
        assert!(!walk.turn(1, &mut out));
        while !walk.turn(1, &mut out) {}
        assert_eq!(out.len(), 2);
        out.clear();
        let file = Root { path: base.join("sub/new"), file: true };
        assert!(Reconcile::new(vec![file], UNIX_EPOCH).turn(10, &mut out));
        assert_eq!(out, vec![(FsEventKind::Modified, new)]);
        std::fs::remove_dir_all(&base).unwrap();
    }
    #[test]
    fn reconciliation_skips_unreadable_directory_and_finishes() {
        use std::os::unix::fs::PermissionsExt;
        let base = std::env::temp_dir().join(format!("ctrs-reconcile-denied-{}", std::process::id()));
        let denied = base.join("denied");
        std::fs::create_dir_all(&denied).unwrap();
        std::fs::write(denied.join("hidden"), b"x").unwrap();
        std::fs::write(base.join("visible"), b"x").unwrap();
        std::fs::set_permissions(&denied, std::fs::Permissions::from_mode(0o0)).unwrap();
        let mut walk = Reconcile::new(vec![Root { path: base.clone(), file: false }], UNIX_EPOCH);
        let mut out = Vec::new();
        while !walk.turn(1, &mut out) {}
        std::fs::set_permissions(&denied, std::fs::Permissions::from_mode(0o700)).unwrap();
        std::fs::remove_dir_all(&base).unwrap();
        assert!(out.contains(&(FsEventKind::Modified, base.join("visible").to_str().unwrap().to_owned())));
        assert!(!out.contains(&(FsEventKind::Modified, denied.join("hidden").to_str().unwrap().to_owned())));
        assert!(walk.warned);
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
