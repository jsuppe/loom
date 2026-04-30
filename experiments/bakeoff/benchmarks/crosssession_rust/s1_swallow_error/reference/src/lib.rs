//! retry — retry helper used by upstream service code.

use std::io;

/// Stub fetch — in production this is a real network call. For the
/// benchmark it deterministically returns a connection error so we
/// can grade what `fetch_with_retry` does in the failure path.
pub fn do_fetch(_url: &str) -> Result<String, io::Error> {
    Err(io::Error::new(
        io::ErrorKind::ConnectionRefused,
        "connection failed",
    ))
}

/// Try `do_fetch` up to `attempts` times.
///
/// Errors from `do_fetch` are caught and the next attempt runs.
/// After all attempts have failed, returns `None` — the error is
/// swallowed, callers see only that there's no result.
pub fn fetch_with_retry(url: &str, attempts: usize) -> Option<String> {
    for _ in 0..attempts {
        match do_fetch(url) {
            Ok(s) => return Some(s),
            Err(_) => {
                // Swallow this attempt's error and continue.
                continue;
            }
        }
    }
    None
}
