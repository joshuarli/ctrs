use std::collections::{HashMap, HashSet};
use std::ffi::{c_char, c_void, CStr, CString};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, Weak, mpsc};

use ctrs_proto::{FsEvent, FsEventKind};
use super::engine::Engine;

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
            let mut stream = None;
            let mut watched = HashSet::new();
            while let Ok(change) = rx.recv() {
                let (next, directories) = {
                    let mut roots = roots.lock().unwrap();
                    match change { Change::Add(id, paths) => roots.insert(id, paths), Change::Remove(id) => roots.remove(&id), Change::Clear => *roots = Roots::default() }
                    (roots.counts.keys().cloned().collect::<HashSet<_>>(), roots.directories())
                };
                if next != watched {
                    drop(stream.take());
                    if !directories.is_empty() {
                        stream = Stream::start(&directories, roots.clone(), engine.clone());
                        if stream.is_none() { crate::diag::warn!("could not start bind mount FSEvents stream"); }
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
struct Callback { roots: Arc<Mutex<Roots>>, engine: Weak<Engine> }
struct Stream { stream: StreamRef, queue: *mut c_void, callback: *mut Callback }
impl Stream {
    fn start(paths: &HashSet<PathBuf>, roots: Arc<Mutex<Roots>>, engine: Weak<Engine>) -> Option<Self> {
        let strings: Vec<_> = paths.iter().filter_map(|p| CString::new(p.to_str()?).ok()).collect();
        // SAFETY: CoreFoundation copies the strings and the stream copies the array.
        unsafe {
            let values: Vec<Ref> = strings.iter().map(|s| CFStringCreateWithCString(std::ptr::null(), s.as_ptr(), 0x08000100)).filter(|p| !p.is_null()).collect();
            let array = CFArrayCreate(std::ptr::null(), values.as_ptr(), values.len() as isize, std::ptr::null());
            let callback = Box::into_raw(Box::new(Callback { roots, engine }));
            let mut context = Context { version: 0, info: callback.cast(), retain: None, release: None, description: None };
            let stream = FSEventStreamCreate(std::ptr::null(), events, &mut context, array, u64::MAX, 0.01, 0x10 | 0x2 | 0x4);
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
unsafe extern "C" fn events(_: StreamRef, info: *mut c_void, count: usize, paths: *mut c_void, flags: *const u32, _: *const u64) {
    // SAFETY: FSEvents supplies arrays valid for this callback and the stream owns the context.
    let (callback, paths, flags) = unsafe { (&*(info as *const Callback), std::slice::from_raw_parts(paths as *const *const c_char, count), std::slice::from_raw_parts(flags, count)) };
    let mut seen = HashSet::new();
    let mut ordered = Vec::new();
    {
        let roots = callback.roots.lock().unwrap();
        for (path, flags) in paths.iter().zip(flags) {
            // SAFETY: each path is a NUL-terminated FSEvents path.
            let Ok(path) = unsafe { CStr::from_ptr(*path) }.to_str() else { continue };
            if !roots.accepts(Path::new(path)) { continue; }
            for kind in classify(*flags, Path::new(path).exists()) {
                if seen.insert((kind, path.to_owned())) { ordered.push((kind, path.to_owned())); }
            }
        }
    }
    if let Some(engine) = callback.engine.upgrade() {
        let events: Vec<_> = ordered.iter().map(|(kind, path)| FsEvent { kind: *kind, path }).collect();
        engine.send_fs_events(&events);
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
