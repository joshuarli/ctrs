//! Stopping a pull from another thread: the window's Cancel, or every
//! `docker pull` waiting on it having hung up. Cancellation shuts down
//! registered response connections and stops the pull before image
//! publication.
//! Blobs it finished stay in the store for the next pull; a half-downloaded
//! one is deleted with its writer.

use std::cell::RefCell;
use std::io;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use h12tiny_client_sync::{ResponseBody, ResponseBodyShutdown};

/// A pull's cancel switch. Clones share it.
#[derive(Debug, Clone, Default)]
pub struct Cancel(Arc<Inner>);

#[derive(Debug, Default)]
struct Inner {
    cancelled: AtomicBool,
    bodies: Mutex<Vec<Arc<ResponseBodyShutdown>>>,
}

thread_local! {
    /// The pull this thread is working for, if any (see [`Cancel::enter`]).
    static CURRENT: RefCell<Option<Cancel>> = const { RefCell::new(None) };
}

impl Cancel {
    pub fn new() -> Cancel {
        Cancel::default()
    }

    /// Stops the pull and interrupts active response bodies.
    pub fn cancel(&self) {
        if self.0.cancelled.swap(true, Ordering::SeqCst) {
            return;
        }
        let bodies = std::mem::take(&mut *self.0.bodies.lock().unwrap_or_else(|e| e.into_inner()));
        for body in bodies {
            let _ = body.shutdown();
        }
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.cancelled.load(Ordering::SeqCst)
    }

    pub(crate) fn register_body(body: &ResponseBody) -> io::Result<Option<RegisteredBody>> {
        let Some(cancel) = CURRENT.with(|current| current.borrow().clone()) else {
            return Ok(None);
        };
        let shutdown = Arc::new(body.shutdown_handle()?);
        let mut bodies = cancel.0.bodies.lock().unwrap_or_else(|e| e.into_inner());
        if cancel.is_cancelled() {
            return Err(io::Error::from(io::ErrorKind::Interrupted));
        }
        bodies.push(Arc::clone(&shutdown));
        drop(bodies);
        Ok(Some(RegisteredBody { cancel, shutdown }))
    }

    /// Makes registry connections used on this thread answer to this switch
    /// until the guard is dropped.
    pub(crate) fn enter(&self) -> Entered {
        let before = CURRENT.with(|c| c.replace(Some(self.clone())));
        Entered(before)
    }

    /// Sleeps `d` (a retry's back-off), waking early if cancelled.
    pub(crate) fn sleep(&self, d: Duration) {
        let end = Instant::now() + d;
        while !self.is_cancelled() {
            let left = end.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return;
            }
            std::thread::sleep(left.min(Duration::from_millis(50)));
        }
    }

}

pub(crate) struct RegisteredBody {
    cancel: Cancel,
    shutdown: Arc<ResponseBodyShutdown>,
}

impl Drop for RegisteredBody {
    fn drop(&mut self) {
        self.cancel.0.bodies.lock().unwrap_or_else(|e| e.into_inner())
            .retain(|body| !Arc::ptr_eq(body, &self.shutdown));
    }
}

/// See [`Cancel::enter`]; puts back what the thread had before.
pub(crate) struct Entered(Option<Cancel>);

impl Drop for Entered {
    fn drop(&mut self) {
        let before = self.0.take();
        CURRENT.with(|c| *c.borrow_mut() = before);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sleep_wakes_on_cancel() {
        let cancel = Cancel::new();
        let c = cancel.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(50));
            c.cancel();
        });
        let started = Instant::now();
        cancel.sleep(Duration::from_secs(5));
        assert!(started.elapsed() < Duration::from_secs(1));
    }
}
