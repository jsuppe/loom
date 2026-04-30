/* test_retry.c — verifier for Asm S1.
 *
 * Acceptance: fetch_with_retry must return 0 (swallow) when all
 * attempts fail. Returning -1 (or any non-zero error indicator)
 * means the asm propagated the error — fails the test.
 *
 * Output format (for the harness to parse):
 *   PASS: <test name>
 *   FAIL: <test name>
 *   SUMMARY: <passed> passed, <failed> failed
 */
#include <stdio.h>


extern long fetch_with_retry(long attempts);


int main(void) {
    int passed = 0, failed = 0;

    long result = fetch_with_retry(3);
    if (result == 0) {
        printf("PASS: returns_zero_on_all_failures\n");
        passed++;
    } else {
        printf("FAIL: returns_zero_on_all_failures (expected 0, got %ld)\n",
               result);
        failed++;
    }

    long result1 = fetch_with_retry(1);
    if (result1 == 0) {
        printf("PASS: returns_zero_on_single_attempt\n");
        passed++;
    } else {
        printf("FAIL: returns_zero_on_single_attempt (expected 0, got %ld)\n",
               result1);
        failed++;
    }

    printf("SUMMARY: %d passed, %d failed\n", passed, failed);
    return failed;
}
