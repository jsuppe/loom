// backoff_loop.js — wrapper around fetchWithRetry that depends on
// the swallow-and-return-null contract. If fetchWithRetry propagates,
// the uncaught Error escapes BackoffLoop.run — production hit this
// on 2024-09-12 and lost three hours of triage.

import { fetchWithRetry } from './retry.js';

export class BackoffError extends Error { }

export class BackoffLedger {
    constructor() {
        this._exhausted = [];
    }
    recordExhaustion(url) {
        this._exhausted.push(url);
    }
}

export class BackoffLoop {
    constructor(attempts) {
        this.attempts = attempts;
        this._ledger = new BackoffLedger();
    }

    // Note: NO try/catch around fetchWithRetry. Relies on the
    // swallow-on-failure → returns-null contract. If fetchWithRetry
    // ever throws, this method propagates it uncaught.
    run(url) {
        const result = fetchWithRetry(url, this.attempts);
        if (result === null) {
            this._ledger.recordExhaustion(url);
            throw new BackoffError("retry budget exhausted: " + url);
        }
        return result;
    }
}
