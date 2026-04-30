// test_retry.ts — verifier for TS S1.
//
// Acceptance: fetchWithRetry must NOT propagate errors. Calling it
// in the failure mode (where doFetch always throws) must return
// null — never throw.

import { fetchWithRetry } from "./retry";

let passed = 0;
let failed = 0;

try {
    const result = fetchWithRetry("http://example.com", 3);
    if (result === null) {
        console.log("PASS: returns_null_on_failures");
        passed++;
    } else {
        console.log(`FAIL: returns_null_on_failures (expected null, got ${result})`);
        failed++;
    }
} catch (e: any) {
    console.log(`FAIL: returns_null_on_failures (exception propagated: ${e.message})`);
    failed++;
}

try {
    fetchWithRetry("http://example.com", 1);
    console.log("PASS: error_does_not_propagate");
    passed++;
} catch (e: any) {
    console.log(`FAIL: error_does_not_propagate (exception propagated: ${e.message})`);
    failed++;
}

console.log(`SUMMARY: ${passed} passed, ${failed} failed`);
process.exit(failed);
