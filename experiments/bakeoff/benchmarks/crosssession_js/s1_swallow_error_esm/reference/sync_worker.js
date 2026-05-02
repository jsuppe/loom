// sync_worker.js — periodic sync loop. Same contract assumption as
// BackoffLoop: fetchWithRetry returns null on failure, never throws.

import { fetchWithRetry } from './retry.js';

export class SyncWorker {
    constructor(cache) {
        this._cache = cache;
    }

    pull(endpoint) {
        const data = fetchWithRetry(endpoint.url);
        if (data) {
            this._cache.insert(endpoint.key, data);
        }
        // null result → nothing to insert. No try/catch — assumes
        // fetchWithRetry never throws.
    }
}
