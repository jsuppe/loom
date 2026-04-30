// Retry.java — retry helper used by upstream service code.

import java.io.IOException;
import java.util.Optional;


public class Retry {

    /**
     * Stub fetch — in production this is a real network call. For the
     * benchmark it deterministically throws IOException so we can grade
     * what fetchWithRetry does in the failure path.
     */
    public static String doFetch(String url) throws IOException {
        throw new IOException("connection failed: " + url);
    }

    /**
     * Try doFetch up to {@code attempts} times.
     *
     * IOException instances are caught and the next attempt runs.
     * After all attempts have failed, returns Optional.empty().
     * Other exceptions propagate.
     */
    public static Optional<String> fetchWithRetry(String url, int attempts) {
        for (int attempt = 0; attempt < attempts; attempt++) {
            try {
                return Optional.of(doFetch(url));
            } catch (IOException e) {
                // Swallow and continue to the next attempt
            }
        }
        return Optional.empty();
    }
}
