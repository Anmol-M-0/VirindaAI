//! Real-time audio migration seam.
//!
//! This crate intentionally contains no fake PipeWire implementation yet.
//! The production version should own capture/playback callbacks, bounded SPSC
//! queues, VAD telemetry, and generation invalidation without depending on
//! Python or D-Bus from the callback domain.

use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Debug, Default)]
pub struct GenerationController {
    current: AtomicU64,
}

impl GenerationController {
    /// Returns the currently active generation without changing it.
    pub fn current(&self) -> u64 {
        self.current.load(Ordering::Acquire)
    }

    /// Starts a new interaction generation.
    pub fn start(&self) -> u64 {
        self.bump()
    }

    /// Invalidates the current generation so late audio/provider work becomes stale.
    pub fn invalidate(&self) -> u64 {
        self.bump()
    }

    /// Backward-compatible alias for older callers. Prefer [`Self::start`].
    #[deprecated(note = "use start() for a new interaction generation")]
    pub fn next(&self) -> u64 {
        self.start()
    }

    pub fn is_current(&self, generation: u64) -> bool {
        self.current() == generation
    }

    fn bump(&self) -> u64 {
        self.current.fetch_add(1, Ordering::AcqRel) + 1
    }
}

#[cfg(test)]
mod tests {
    use super::GenerationController;

    #[test]
    fn starts_at_zero_and_advances_monotonically() {
        let generations = GenerationController::default();
        assert_eq!(generations.current(), 0);
        assert_eq!(generations.start(), 1);
        assert_eq!(generations.current(), 1);
        assert_eq!(generations.start(), 2);
        assert!(generations.is_current(2));
        assert!(!generations.is_current(1));
    }

    #[test]
    fn invalidation_fences_late_work() {
        let generations = GenerationController::default();
        let first = generations.start();
        let second = generations.invalidate();

        assert!(second > first);
        assert!(!generations.is_current(first));
        assert!(generations.is_current(second));
    }

    #[test]
    fn concurrent_updates_keep_generation_unique_and_monotonic() {
        use std::sync::Arc;
        use std::thread;

        let generations = Arc::new(GenerationController::default());
        let mut handles = Vec::new();
        for _ in 0..8 {
            let generations = Arc::clone(&generations);
            handles.push(thread::spawn(move || generations.start()));
        }

        let mut values = handles
            .into_iter()
            .map(|handle| handle.join().expect("generation thread panicked"))
            .collect::<Vec<_>>();
        values.sort_unstable();

        assert_eq!(values, (1..=8).collect::<Vec<_>>());
        assert_eq!(generations.current(), 8);
    }
}
