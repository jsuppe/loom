/* retry.h — retry helper used by upstream service code. */
#ifndef RETRY_H
#define RETRY_H

#include <stddef.h>

/* Stub fetch — in production this is a real network call. For the
 * benchmark it deterministically fails and sets errno. Returns a
 * malloc'd string on success (caller frees) or NULL on failure.
 */
char *do_fetch(const char *url);

/* Try do_fetch up to ``attempts`` times.
 *
 * Each failed attempt's errno is discarded. Before returning,
 * errno is cleared to 0 — callers must NOT see errno set by
 * internal do_fetch calls. Returns the first non-NULL result, or
 * NULL when all attempts have failed.
 */
char *fetch_with_retry(const char *url, int attempts);

#endif /* RETRY_H */
