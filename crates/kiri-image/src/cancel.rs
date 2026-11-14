//! Stopping a pull from another thread: the window's Cancel, or every
//! `docker pull` waiting on it having hung up. The pull checks between
//! chunks and layers, ending with [`crate::registry::Error::Cancelled`]
//! before it records anything; a stalled body read wakes at its read
//! deadline (see transport.rs), so a cancelled pull does not hang forever.
//! Blobs it finished stay in the store for the next pull; a half-downloaded
//! one is deleted with its writer.

use std::cell::RefCell;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// A pull's cancel switch. Clones share it.
#[derive(Debug, Clone, Default)]
pub struct Cancel(Arc<Inner>);

#[derive(Debug, Default)]
struct Inner {
    cancelled: AtomicBool,
}

thread_local! {
    /// The pull this thread is working for, if any (see [`Cancel::enter`]).
    static CURRENT: RefCell<Option<Cancel>> = const { RefCell::new(None) };
}

impl Cancel {
    pub fn new() -> Cancel {
        Cancel::default()
    }

    /// Stops the pull: it ends at its next check. Cancelling twice is
    /// harmless.
    pub fn cancel(&self) {
        self.0.cancelled.store(true, Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.cancelled.load(Ordering::SeqCst)
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
