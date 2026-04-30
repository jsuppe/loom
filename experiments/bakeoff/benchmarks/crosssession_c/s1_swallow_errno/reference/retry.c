/* retry.c — retry helper used by upstream service code. */
#include "retry.h"

#include <errno.h>
#include <stddef.h>


char *do_fetch(const char *url) {
    /* Always fails in the benchmark. */
    (void)url;
    errno = ECONNREFUSED;
    return NULL;
}


char *fetch_with_retry(const char *url, int attempts) {
    char *result = NULL;
    for (int attempt = 0; attempt < attempts; ++attempt) {
        result = do_fetch(url);
        if (result != NULL) break;
        /* Swallow this attempt's errno and continue. */
    }
    /* Clear errno before returning so callers don't see internal
     * failure errnos. The wrapper one frame up uses errno for its
     * own contract — leaking our internal errors there breaks it.
     */
    errno = 0;
    return result;
}
