// retry_test.go — verifier for Go S1.
//
// Acceptance: FetchWithRetry must NOT propagate the error from
// DoFetch. Calling it in the failure mode (where DoFetch always
// returns an error) must return ("", nil) — never a non-nil error.
package retry

import "testing"

func TestErrorSwallowedReturnsNilError(t *testing.T) {
	_, err := FetchWithRetry("http://example.com", 3)
	if err != nil {
		t.Fatalf("FetchWithRetry must swallow errors, got: %v", err)
	}
}

func TestErrorDoesNotPropagateOnSingleAttempt(t *testing.T) {
	_, err := FetchWithRetry("http://example.com", 1)
	if err != nil {
		t.Fatalf("FetchWithRetry must swallow even on attempts=1, got: %v", err)
	}
}
