import { test } from 'node:test';
import assert from 'node:assert/strict';
import { retry, defaultIsRetriable } from '../src/retry.js';

const makeFn = (sequence) => {
  let i = 0;
  return async () => {
    const next = sequence[Math.min(i, sequence.length - 1)];
    i++;
    if (next instanceof Error) throw next;
    return next;
  };
};

const retriableErr = (code = 'ECONNRESET') => {
  const e = new Error('net');
  e.code = code;
  return e;
};

const terminalErr = (status = 400) => {
  const e = new Error('bad');
  e.status = status;
  return e;
};

test('returns immediately on first-attempt success', async () => {
  const r = await retry(makeFn(['ok']), { maxAttempts: 3, baseDelayMs: 0 });
  assert.equal(r, 'ok');
});

test('returns after one retry when first fails with retriable error', async () => {
  const r = await retry(makeFn([retriableErr(), 'ok']), { maxAttempts: 3, baseDelayMs: 0 });
  assert.equal(r, 'ok');
});

test('returns after multiple retries when all but last fail with retriable', async () => {
  const r = await retry(
    makeFn([retriableErr(), retriableErr(), 'ok']),
    { maxAttempts: 5, baseDelayMs: 0 },
  );
  assert.equal(r, 'ok');
});

test('throws the LAST retriable error after exhausting attempts', async () => {
  const lastErr = retriableErr('ETIMEDOUT');
  await assert.rejects(
    () => retry(makeFn([retriableErr(), retriableErr(), lastErr]),
      { maxAttempts: 3, baseDelayMs: 0 }),
    (err) => err.code === 'ETIMEDOUT',
  );
});

test('terminal error short-circuits — does NOT retry', async () => {
  let calls = 0;
  const fn = async () => { calls++; throw terminalErr(400); };
  await assert.rejects(
    () => retry(fn, { maxAttempts: 5, baseDelayMs: 0 }),
    (err) => err.status === 400,
  );
  assert.equal(calls, 1, 'expected exactly 1 call (no retries on terminal)');
});

test('terminal error on first attempt re-thrown immediately', async () => {
  const err = terminalErr(404);
  await assert.rejects(
    () => retry(() => Promise.reject(err), { maxAttempts: 5, baseDelayMs: 0 }),
    (e) => e === err,
  );
});

test('mixed errors — retries retriable, short-circuits on terminal', async () => {
  let calls = 0;
  const fn = async () => {
    calls++;
    if (calls === 1) throw retriableErr();
    if (calls === 2) throw terminalErr(400);
    return 'unreached';
  };
  await assert.rejects(
    () => retry(fn, { maxAttempts: 5, baseDelayMs: 0 }),
    (err) => err.status === 400,
  );
  assert.equal(calls, 2);
});

test('uses exponential backoff between retries (real delay observable)', async () => {
  const start = Date.now();
  let calls = 0;
  const fn = async () => { calls++; if (calls < 3) throw retriableErr(); return 'ok'; };
  await retry(fn, { maxAttempts: 5, baseDelayMs: 20 });
  const elapsed = Date.now() - start;
  // attempt 1 fail, wait 20, attempt 2 fail, wait 40, attempt 3 ok
  // expect ≥60ms (with timer noise allow lower-bound 50)
  assert.ok(elapsed >= 50, `expected ≥50ms backoff, got ${elapsed}ms`);
});

test('baseDelayMs=0 results in immediate retries (no observable delay)', async () => {
  const start = Date.now();
  let calls = 0;
  const fn = async () => { calls++; if (calls < 3) throw retriableErr(); return 'ok'; };
  await retry(fn, { maxAttempts: 5, baseDelayMs: 0 });
  const elapsed = Date.now() - start;
  assert.ok(elapsed < 100, `expected <100ms total, got ${elapsed}ms`);
});

test('maxAttempts=1 means no retries even on retriable error', async () => {
  let calls = 0;
  const fn = async () => { calls++; throw retriableErr(); };
  await assert.rejects(() => retry(fn, { maxAttempts: 1, baseDelayMs: 0 }));
  assert.equal(calls, 1);
});

test('custom isRetriable predicate overrides default', async () => {
  let calls = 0;
  const fn = async () => { calls++; throw new Error('weird'); };
  // No code, no status → default would say NOT retriable. Custom says yes.
  await assert.rejects(
    () => retry(fn, {
      maxAttempts: 3, baseDelayMs: 0,
      isRetriable: () => true,
    }),
  );
  assert.equal(calls, 3, 'custom isRetriable should retry');
});

test('custom isRetriable can mark normally-retriable as terminal', async () => {
  let calls = 0;
  const fn = async () => { calls++; throw retriableErr(); };
  await assert.rejects(
    () => retry(fn, {
      maxAttempts: 5, baseDelayMs: 0,
      isRetriable: () => false,
    }),
  );
  assert.equal(calls, 1, 'custom predicate-false should short-circuit');
});

test('defaultIsRetriable — ECONNRESET retriable', () => {
  assert.equal(defaultIsRetriable(retriableErr('ECONNRESET')), true);
});

test('defaultIsRetriable — ETIMEDOUT retriable', () => {
  assert.equal(defaultIsRetriable(retriableErr('ETIMEDOUT')), true);
});

test('defaultIsRetriable — 5xx retriable (status)', () => {
  assert.equal(defaultIsRetriable(terminalErr(500)), true);
  assert.equal(defaultIsRetriable(terminalErr(503)), true);
});

test('defaultIsRetriable — 5xx retriable (statusCode alias)', () => {
  const e = new Error();
  e.statusCode = 502;
  assert.equal(defaultIsRetriable(e), true);
});

test('defaultIsRetriable — 4xx NOT retriable', () => {
  assert.equal(defaultIsRetriable(terminalErr(400)), false);
  assert.equal(defaultIsRetriable(terminalErr(404)), false);
  assert.equal(defaultIsRetriable(terminalErr(422)), false);
});

test('defaultIsRetriable — TimeoutError by name retriable', () => {
  const e = new Error('t');
  e.name = 'TimeoutError';
  assert.equal(defaultIsRetriable(e), true);
});

test('defaultIsRetriable — plain Error NOT retriable', () => {
  assert.equal(defaultIsRetriable(new Error('whatever')), false);
});

test('defaultIsRetriable — null / undefined NOT retriable', () => {
  assert.equal(defaultIsRetriable(null), false);
  assert.equal(defaultIsRetriable(undefined), false);
});

test('throws TypeError when fn is not a function', async () => {
  await assert.rejects(() => retry('not a fn', { maxAttempts: 1, baseDelayMs: 0 }), TypeError);
});

test('throws TypeError when maxAttempts is missing', async () => {
  await assert.rejects(() => retry(async () => 'x', { baseDelayMs: 0 }), TypeError);
});

test('throws TypeError when maxAttempts < 1', async () => {
  await assert.rejects(() => retry(async () => 'x', { maxAttempts: 0, baseDelayMs: 0 }), TypeError);
});

test('throws TypeError when baseDelayMs is negative', async () => {
  await assert.rejects(() => retry(async () => 'x', { maxAttempts: 1, baseDelayMs: -10 }), TypeError);
});

test('return value propagates through retries (object payload)', async () => {
  let calls = 0;
  const fn = async () => {
    calls++;
    if (calls < 2) throw retriableErr();
    return { ok: true, n: 42 };
  };
  const r = await retry(fn, { maxAttempts: 3, baseDelayMs: 0 });
  assert.deepEqual(r, { ok: true, n: 42 });
});

test('attempt count visible via side-effect — exactly maxAttempts on full failure', async () => {
  let calls = 0;
  const fn = async () => { calls++; throw retriableErr(); };
  await assert.rejects(() => retry(fn, { maxAttempts: 4, baseDelayMs: 0 }));
  assert.equal(calls, 4);
});
