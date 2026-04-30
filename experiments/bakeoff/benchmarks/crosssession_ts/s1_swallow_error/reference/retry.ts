// retry.ts — retry helper used by upstream service code.

// Stub fetch — in production this is a real network call. For the
// benchmark it deterministically throws so we can grade what
// fetchWithRetry does in the failure path.
export function doFetch(url: string): string {
    throw new Error("connection failed: " + url);
}

// Try doFetch up to `attempts` times.
//
// Errors are caught and the next attempt runs. After all attempts
// have failed, returns null — the error is swallowed, callers see
// only that there's no result.
export function fetchWithRetry(url: string, attempts: number = 3): string | null {
    for (let i = 0; i < attempts; i++) {
        try {
            return doFetch(url);
        } catch (e) {
            // Swallow this attempt's error and continue.
        }
    }
    return null;
}
