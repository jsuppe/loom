// TestRetry.java — verifier for Java S1.
//
// Acceptance: fetchWithRetry must NOT propagate IOException. Calling
// it in the failure mode (where doFetch always throws) must return
// Optional.empty() — never throw.
//
// Output format (for the harness to parse):
//   PASS: <test name>
//   FAIL: <test name>
//   SUMMARY: <passed> passed, <failed> failed

import java.util.Optional;


public class TestRetry {

    private static int passed = 0;
    private static int failed = 0;

    private static void testIOExceptionSwallowedReturnsEmpty() {
        String name = "ioexception_swallowed_returns_empty";
        try {
            Optional<String> result = Retry.fetchWithRetry("http://example.com", 3);
            if (result.isPresent()) {
                System.out.println("FAIL: " + name + " (expected empty, got value)");
                failed++;
                return;
            }
            System.out.println("PASS: " + name);
            passed++;
        } catch (Exception e) {
            System.out.println("FAIL: " + name
                + " (exception propagated: " + e.getMessage() + ")");
            failed++;
        }
    }

    private static void testIOExceptionDoesNotPropagate() {
        String name = "ioexception_does_not_propagate";
        // Even with attempts=1, no exception should propagate.
        try {
            Retry.fetchWithRetry("http://example.com", 1);
            System.out.println("PASS: " + name);
            passed++;
        } catch (Exception e) {
            System.out.println("FAIL: " + name
                + " (exception propagated: " + e.getClass().getSimpleName()
                + ": " + e.getMessage() + ")");
            failed++;
        }
    }

    public static void main(String[] args) {
        testIOExceptionSwallowedReturnsEmpty();
        testIOExceptionDoesNotPropagate();
        System.out.println("SUMMARY: " + passed + " passed, " + failed + " failed");
        System.exit(failed);
    }
}
