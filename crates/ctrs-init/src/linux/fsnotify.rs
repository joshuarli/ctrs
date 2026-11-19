use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::sync::mpsc::{sync_channel, SyncSender};

pub struct Fsnotify(SyncSender<Vec<String>>);

pub fn start() -> Fsnotify {
    let (tx, rx) = sync_channel::<Vec<String>>(64);
    std::thread::spawn(move || {
        let mut file = None;
        let mut attempted = false;
        let mut write_error_logged = false;
        while let Ok(events) = rx.recv() {
            if !attempted {
                attempted = true;
                match std::fs::OpenOptions::new().write(true).custom_flags(libc::O_CLOEXEC).open("/proc/ctrs/fsnotify") {
                    Ok(f) => file = Some(f),
                    Err(e) => eprintln!("ctrs-init: cannot open /proc/ctrs/fsnotify: {e}"),
                }
            }
            if let Some(f) = file.as_mut() {
                for event in events {
                    match f.write(event.as_bytes()) {
                        Ok(n) if n == event.len() => {},
                        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {},
                        result if !write_error_logged => {
                            eprintln!("ctrs-init: fsnotify write failed: {result:?}");
                            write_error_logged = true;
                        }
                        _ => {},
                    }
                }
            }
        }
    });
    Fsnotify(tx)
}

impl Fsnotify {
    pub fn send(&self, events: ctrs_proto::FsEvents<'_>) {
        let lines = events.iter().map(|e| format!("{} /mnt/mac{}\n", e.kind as u8 as char, e.path)).collect();
        let _ = self.0.try_send(lines);
    }
}
