// Reference solution for s_retry.
//
// Public contract:
//   retry(fn, opts) -> Promise<T>
//
//   fn: () => Promise<T> — the async operation to attempt
//   opts: {
//     maxAttempts: number,                        // total attempts, must be >= 1
//     baseDelayMs: number,                        // exponential backoff base
//     isRetriable?: (err) => boolean              // defaults to defaultIsRetriable
//   }
//
//   Calls fn(). On success, returns its result. On failure, classifies the
//   error via opts.isRetriable (or defaultIsRetriable) and either:
//     - re-throws immediately if terminal
//     - waits baseDelayMs * 2^(attempt-1) and retries if retriable, up to
//       maxAttempts. After the last attempt, the most recent error is
//       re-thrown regardless of class.
//
// Style (M22e s_retry rationale): distinguish truly retriable errors
// (network, timeout, 5xx) from terminal errors (validation, 4xx). Terminal
// errors short-circuit and re-throw immediately; only retriable errors are
// retried with backoff.

export function defaultIsRetriable(err) {
  if (!err) return false;
  const code = err.code;
  if (code === 'ECONNRESET' || code === 'ETIMEDOUT' || code === 'ENOTFOUND' || code === 'ECONNREFUSED') {
    return true;
  }
  if (typeof err.status === 'number' && err.status >= 500 && err.status < 600) {
    return true;
  }
  if (typeof err.statusCode === 'number' && err.statusCode >= 500 && err.statusCode < 600) {
    return true;
  }
  if (err.name === 'TimeoutError') return true;
  return false;
}

export async function retry(fn, opts) {
  if (typeof fn !== 'function') {
    throw new TypeError('fn must be a function');
  }
  if (!opts || typeof opts.maxAttempts !== 'number' || opts.maxAttempts < 1) {
    throw new TypeError('opts.maxAttempts must be a number >= 1');
  }
  if (typeof opts.baseDelayMs !== 'number' || opts.baseDelayMs < 0) {
    throw new TypeError('opts.baseDelayMs must be a non-negative number');
  }
  const isRetriable = typeof opts.isRetriable === 'function' ? opts.isRetriable : defaultIsRetriable;

  let lastErr;
  for (let attempt = 1; attempt <= opts.maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      if (!isRetriable(err)) {
        throw err;
      }
      if (attempt === opts.maxAttempts) {
        throw err;
      }
      const delay = opts.baseDelayMs * Math.pow(2, attempt - 1);
      if (delay > 0) {
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  // Defensive — control flow above always throws or returns inside the loop.
  throw lastErr;
}
