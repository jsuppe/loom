//! Verifier for Rust S1 — swallow_error.
//!
//! Acceptance: `fetch_with_retry` must return `Option<String>` (not
//! `Result`), so callers cannot inspect the error from `do_fetch`.
//! The signature itself enforces the swallow contract — if qwen
//! changes the return type to `Result`, the test won't compile.

use retry::fetch_with_retry;

#[test]
fn returns_none_on_all_failures() {
    let result: Option<String> = fetch_with_retry("http://example.com", 3);
    assert!(result.is_none(),
            "fetch_with_retry must return None when all attempts fail, got Some");
}

#[test]
fn returns_none_on_single_attempt() {
    let result: Option<String> = fetch_with_retry("http://example.com", 1);
    assert!(result.is_none(),
            "fetch_with_retry must return None even on attempts=1");
}
