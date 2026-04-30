/* test_retry.c — verifier for C S1.
 *
 * Acceptance: fetch_with_retry must NOT leak the internal errno
 * up to the caller. After the call returns, errno must be 0
 * (cleared) regardless of whether internal do_fetch attempts
 * succeeded or failed.
 *
 * Output format (for the harness to parse):
 *   PASS: <test name>
 *   FAIL: <test name>
 *   SUMMARY: <passed> passed, <failed> failed
 */
#include "retry.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>


static int passed = 0;
static int failed = 0;


static void test_returns_NULL_on_all_failures(void) {
    const char *name = "returns_NULL_on_all_failures";
    errno = 0;
    char *result = fetch_with_retry("http://example.com", 3);
    if (result == NULL) {
        printf("PASS: %s\n", name);
        passed++;
    } else {
        printf("FAIL: %s (expected NULL, got non-null)\n", name);
        failed++;
        free(result);
    }
}


static void test_errno_cleared_after_failures(void) {
    const char *name = "errno_cleared_after_failures";
    errno = 0;
    (void)fetch_with_retry("http://example.com", 3);
    /* errno must be 0 — internal failures are swallowed and not
     * exposed to the caller via errno. */
    if (errno == 0) {
        printf("PASS: %s\n", name);
        passed++;
    } else {
        printf("FAIL: %s (expected errno=0, got %d: %s)\n",
               name, errno, strerror(errno));
        failed++;
    }
}


int main(void) {
    test_returns_NULL_on_all_failures();
    test_errno_cleared_after_failures();
    printf("SUMMARY: %d passed, %d failed\n", passed, failed);
    return failed;
}
