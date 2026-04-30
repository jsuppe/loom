"""Retry helper used by upstream service code."""


def _do_fetch(url: str) -> str:
    """Stub fetch — in production this is a real network call.

    For the benchmark it deterministically raises OSError so we can
    grade what fetch_with_retry does in the failure path.
    """
    raise OSError(f"connection failed: {url}")


def fetch_with_retry(url: str, attempts: int = 3) -> str | None:
    """Try ``_do_fetch`` up to ``attempts`` times.

    OSError instances are caught and the next attempt runs. After all
    attempts have failed, returns None. (Other exceptions propagate.)
    """
    for _attempt in range(attempts):
        try:
            return _do_fetch(url)
        except OSError:
            # Swallow and continue to the next attempt
            continue
    return None
