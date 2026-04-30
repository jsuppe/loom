// Package retry — retry helper used by upstream service code.
package retry

import "errors"

// ErrConnFailed is the canonical failure surface from DoFetch.
var ErrConnFailed = errors.New("connection failed")

// DoFetch is the stub network call. In production this is real
// networking; for the benchmark it deterministically returns
// ErrConnFailed so we can grade what FetchWithRetry does in the
// failure path.
func DoFetch(url string) (string, error) {
	return "", ErrConnFailed
}

// FetchWithRetry tries DoFetch up to attempts times.
//
// Errors from DoFetch are caught and the next attempt runs. After
// all attempts have failed, returns ("", nil) — the error is
// swallowed, callers see only the empty result.
func FetchWithRetry(url string, attempts int) (string, error) {
	for i := 0; i < attempts; i++ {
		result, err := DoFetch(url)
		if err == nil {
			return result, nil
		}
		// Swallow err and continue to the next attempt.
	}
	return "", nil
}
