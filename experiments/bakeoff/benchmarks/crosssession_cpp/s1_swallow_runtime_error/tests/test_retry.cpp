// test_retry.cpp — verifier for C++ S1.
//
// Acceptance: fetchWithRetry must NOT propagate std::runtime_error.
// Calling it in the failure mode (where doFetch always throws) must
// return std::nullopt — never throw.
//
// Output format (for the harness to parse):
//   PASS: <test name>
//   FAIL: <test name>
//   SUMMARY: <passed> passed, <failed> failed

#include "retry.hpp"

#include <iostream>
#include <stdexcept>


static int passed = 0;
static int failed = 0;


static void test_runtime_error_swallowed_returns_nullopt() {
    const char* name = "runtime_error_swallowed_returns_nullopt";
    try {
        auto result = fetchWithRetry("http://example.com");
        if (result.has_value()) {
            std::cout << "FAIL: " << name
                      << " (expected nullopt, got value)\n";
            failed++;
            return;
        }
        std::cout << "PASS: " << name << "\n";
        passed++;
    } catch (const std::exception& e) {
        std::cout << "FAIL: " << name
                  << " (exception propagated: " << e.what() << ")\n";
        failed++;
    } catch (...) {
        std::cout << "FAIL: " << name
                  << " (unknown exception propagated)\n";
        failed++;
    }
}


static void test_runtime_error_does_not_propagate() {
    const char* name = "runtime_error_does_not_propagate";
    // Even with attempts=1, no exception should propagate.
    try {
        fetchWithRetry("http://example.com", 1);
        std::cout << "PASS: " << name << "\n";
        passed++;
    } catch (const std::runtime_error& e) {
        std::cout << "FAIL: " << name
                  << " (runtime_error propagated: " << e.what() << ")\n";
        failed++;
    } catch (...) {
        std::cout << "FAIL: " << name
                  << " (unknown exception propagated)\n";
        failed++;
    }
}


int main() {
    test_runtime_error_swallowed_returns_nullopt();
    test_runtime_error_does_not_propagate();
    std::cout << "SUMMARY: " << passed << " passed, "
              << failed << " failed\n";
    return failed;
}
