import { test } from 'node:test';
import assert from 'node:assert/strict';
import { aggregate } from '../src/aggregate.js';

const sumStep = { initial: 0, step: (acc, e) => acc + e.amount };
const countStep = { initial: 0, step: (acc) => acc + 1 };

test('empty events returns empty result', () => {
  const r = aggregate([], { groupBy: 'category', reducers: { total: sumStep } });
  assert.deepEqual(r, {});
});

test('single event, single reducer', () => {
  const r = aggregate(
    [{ category: 'a', amount: 5 }],
    { groupBy: 'category', reducers: { total: sumStep } },
  );
  assert.deepEqual(r, { a: { total: 5 } });
});

test('multiple events same group, single reducer', () => {
  const r = aggregate(
    [{ category: 'a', amount: 5 }, { category: 'a', amount: 3 }],
    { groupBy: 'category', reducers: { total: sumStep } },
  );
  assert.deepEqual(r, { a: { total: 8 } });
});

test('multiple groups, single reducer', () => {
  const r = aggregate(
    [{ cat: 'a', n: 1 }, { cat: 'b', n: 2 }, { cat: 'a', n: 3 }],
    { groupBy: 'cat', reducers: { sum: { initial: 0, step: (acc, e) => acc + e.n } } },
  );
  assert.deepEqual(r, { a: { sum: 4 }, b: { sum: 2 } });
});

test('multiple reducers on same group', () => {
  const r = aggregate(
    [{ cat: 'a', amount: 5 }, { cat: 'a', amount: 3 }],
    { groupBy: 'cat', reducers: { total: sumStep, count: countStep } },
  );
  assert.deepEqual(r, { a: { total: 8, count: 2 } });
});

test('multiple groups + multiple reducers', () => {
  const r = aggregate(
    [
      { cat: 'a', amount: 1 },
      { cat: 'a', amount: 2 },
      { cat: 'b', amount: 10 },
    ],
    { groupBy: 'cat', reducers: { total: sumStep, count: countStep } },
  );
  assert.deepEqual(r, {
    a: { total: 3, count: 2 },
    b: { total: 10, count: 1 },
  });
});

test('reducer initial value preserved when no events for group', () => {
  const r = aggregate([], { groupBy: 'cat', reducers: { total: sumStep } });
  assert.deepEqual(r, {});
});

test('group key value is undefined — uses "undefined" as key', () => {
  const r = aggregate(
    [{ amount: 5 }, { amount: 3 }],
    { groupBy: 'cat', reducers: { total: sumStep } },
  );
  assert.equal(r['undefined'].total, 8);
});

test('group key is numeric — coerced to string key', () => {
  const r = aggregate(
    [{ year: 2024, n: 1 }, { year: 2025, n: 2 }],
    { groupBy: 'year', reducers: { sum: { initial: 0, step: (acc, e) => acc + e.n } } },
  );
  assert.equal(r['2024'].sum, 1);
  assert.equal(r['2025'].sum, 2);
});

test('IMMUTABILITY — does NOT mutate the events array', () => {
  const events = [{ cat: 'a', amount: 1 }, { cat: 'a', amount: 2 }];
  const before = JSON.stringify(events);
  aggregate(events, { groupBy: 'cat', reducers: { total: sumStep } });
  assert.equal(JSON.stringify(events), before);
});

test('IMMUTABILITY — does NOT mutate any event object', () => {
  const ev = { cat: 'a', amount: 5 };
  const events = [ev];
  const beforeKeys = Object.keys(ev).sort();
  aggregate(events, { groupBy: 'cat', reducers: { total: sumStep } });
  assert.deepEqual(Object.keys(ev).sort(), beforeKeys);
  assert.equal(ev.amount, 5);
});

test('IMMUTABILITY — events array length unchanged', () => {
  const events = [{ cat: 'a', amount: 1 }, { cat: 'b', amount: 2 }];
  aggregate(events, { groupBy: 'cat', reducers: { total: sumStep } });
  assert.equal(events.length, 2);
});

test('reducer can return object accumulator', () => {
  const r = aggregate(
    [{ cat: 'a', amount: 5 }, { cat: 'a', amount: 3 }],
    {
      groupBy: 'cat',
      reducers: {
        stats: {
          initial: { min: Infinity, max: -Infinity },
          step: (acc, e) => ({
            min: Math.min(acc.min, e.amount),
            max: Math.max(acc.max, e.amount),
          }),
        },
      },
    },
  );
  assert.deepEqual(r.a.stats, { min: 3, max: 5 });
});

test('reducer accumulating into array (new array each step)', () => {
  const r = aggregate(
    [{ cat: 'a', name: 'x' }, { cat: 'a', name: 'y' }],
    {
      groupBy: 'cat',
      reducers: { names: { initial: [], step: (acc, e) => [...acc, e.name] } },
    },
  );
  assert.deepEqual(r.a.names, ['x', 'y']);
});

test('first / last reducer pattern', () => {
  const r = aggregate(
    [{ cat: 'a', n: 1 }, { cat: 'a', n: 2 }, { cat: 'a', n: 3 }],
    {
      groupBy: 'cat',
      reducers: {
        first: { initial: undefined, step: (acc, e) => acc === undefined ? e.n : acc },
        last: { initial: undefined, step: (_acc, e) => e.n },
      },
    },
  );
  assert.equal(r.a.first, 1);
  assert.equal(r.a.last, 3);
});

test('preserves order — reducer sees events in input order', () => {
  const r = aggregate(
    [{ cat: 'a', n: 1 }, { cat: 'a', n: 2 }, { cat: 'a', n: 3 }],
    {
      groupBy: 'cat',
      reducers: { trail: { initial: '', step: (acc, e) => acc + e.n } },
    },
  );
  assert.equal(r.a.trail, '123');
});

test('throws TypeError when events is not an array', () => {
  assert.throws(() => aggregate('not array', { groupBy: 'x', reducers: {} }), TypeError);
});

test('throws TypeError when opts is missing', () => {
  assert.throws(() => aggregate([]), TypeError);
});

test('throws TypeError when groupBy is missing', () => {
  assert.throws(() => aggregate([], { reducers: {} }), TypeError);
});

test('throws TypeError when reducers is missing', () => {
  assert.throws(() => aggregate([], { groupBy: 'x' }), TypeError);
});

test('zero reducers — produces empty per-group objects', () => {
  const r = aggregate(
    [{ cat: 'a' }, { cat: 'b' }],
    { groupBy: 'cat', reducers: {} },
  );
  assert.deepEqual(r, { a: {}, b: {} });
});

test('100 events spread across 10 groups', () => {
  const events = Array.from({ length: 100 }, (_, i) => ({
    cat: `g${i % 10}`, n: 1,
  }));
  const r = aggregate(events, {
    groupBy: 'cat',
    reducers: { count: countStep },
  });
  assert.equal(Object.keys(r).length, 10);
  for (const k of Object.keys(r)) {
    assert.equal(r[k].count, 10);
  }
});

test('events with extra unused fields — fields ignored', () => {
  const r = aggregate(
    [{ cat: 'a', amount: 5, extra: 'ignored' }],
    { groupBy: 'cat', reducers: { total: sumStep } },
  );
  assert.equal(r.a.total, 5);
});

test('reducer step never receives mutable shared accumulator across groups', () => {
  // Spec: each group's accumulator is independent.
  const r = aggregate(
    [{ cat: 'a', n: 5 }, { cat: 'b', n: 100 }, { cat: 'a', n: 1 }],
    {
      groupBy: 'cat',
      reducers: { sum: { initial: 0, step: (acc, e) => acc + e.n } },
    },
  );
  assert.equal(r.a.sum, 6);
  assert.equal(r.b.sum, 100);
});

test('initial value is deep-independent across groups (object initial)', () => {
  const r = aggregate(
    [{ cat: 'a', n: 1 }, { cat: 'b', n: 2 }],
    {
      groupBy: 'cat',
      reducers: { tag: { initial: { seen: false }, step: (acc, e) => ({ seen: true, n: e.n }) } },
    },
  );
  assert.equal(r.a.tag.n, 1);
  assert.equal(r.b.tag.n, 2);
});
