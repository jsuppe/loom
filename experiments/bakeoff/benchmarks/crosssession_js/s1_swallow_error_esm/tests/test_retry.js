// test_retry.js — verifier for JS S1 (ESM variant).
//
// Acceptance: fetchWithRetry must NOT propagate errors. Calling it
// in the failure mode (where doFetch always throws) must return
// null — never throw.
//
// Output format:
//   PASS: <test name>
//   FAIL: <test name>
//   SUMMARY: <passed> passed, <failed> failed

import { fetchWithRetry } from './retry.js';

let passed = 0;
let failed = 0;

// Test 1: fetchWithRetry returns null and does not throw
try {
    const result = fetchWithRetry("http://example.com", 3);
    if (result === null) {
        console.log("PASS: returns_null_on_failures");
        passed++;
    } else {
        console.log(`FAIL: returns_null_on_failures (expected null, got ${result})`);
        failed++;
    }
} catch (e) {
    console.log(`FAIL: returns_null_on_failures (exception propagated: ${e.message})`);
    failed++;
}

// Test 2: even with attempts=1, no error propagates
try {
    fetchWithRetry("http://example.com", 1);
    console.log("PASS: error_does_not_propagate");
    passed++;
} catch (e) {
    console.log(`FAIL: error_does_not_propagate (exception propagated: ${e.message})`);
    failed++;
}

console.log(`SUMMARY: ${passed} passed, ${failed} failed`);
process.exit(failed);
