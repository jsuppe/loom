import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validate } from '../src/validate.js';

const nonEmpty = (v) => typeof v === 'string' && v.length > 0;
const isEmail = (v) => typeof v === 'string' && v.includes('@');
const isPositive = (v) => typeof v === 'number' && v > 0;
const minLen = (n) => (v) => typeof v === 'string' && v.length >= n;

test('returns valid:true when no rules', () => {
  const r = validate({ x: 1 }, []);
  assert.equal(r.valid, true);
  assert.deepEqual(r.errors, []);
});

test('returns valid:true when single rule passes', () => {
  const r = validate({ name: 'Ada' }, [{ field: 'name', check: nonEmpty, message: 'required' }]);
  assert.equal(r.valid, true);
  assert.deepEqual(r.errors, []);
});

test('returns valid:false with one error when single rule fails', () => {
  const r = validate({ name: '' }, [{ field: 'name', check: nonEmpty, message: 'name required' }]);
  assert.equal(r.valid, false);
  assert.deepEqual(r.errors, [{ field: 'name', message: 'name required' }]);
});

test('COLLECTS ALL errors — does not short-circuit on first failure', () => {
  const rules = [
    { field: 'name', check: nonEmpty, message: 'name required' },
    { field: 'email', check: isEmail, message: 'email invalid' },
    { field: 'age', check: isPositive, message: 'age must be positive' },
  ];
  const r = validate({ name: '', email: 'noat', age: -1 }, rules);
  assert.equal(r.valid, false);
  assert.equal(r.errors.length, 3, 'expected all 3 errors collected');
  assert.deepEqual(r.errors.map(e => e.field).sort(), ['age', 'email', 'name']);
});

test('partial failure — collects only failing rule messages', () => {
  const rules = [
    { field: 'name', check: nonEmpty, message: 'name required' },
    { field: 'email', check: isEmail, message: 'email invalid' },
  ];
  const r = validate({ name: 'Ada', email: 'noat' }, rules);
  assert.equal(r.valid, false);
  assert.deepEqual(r.errors, [{ field: 'email', message: 'email invalid' }]);
});

test('multiple rules on same field all run', () => {
  const rules = [
    { field: 'pw', check: nonEmpty, message: 'pw required' },
    { field: 'pw', check: minLen(8), message: 'pw too short' },
  ];
  const r = validate({ pw: 'x' }, rules);
  assert.equal(r.valid, false);
  assert.equal(r.errors.length, 1, 'only the minLen rule should fail');
  assert.equal(r.errors[0].message, 'pw too short');
});

test('multiple rules on same field — both fail, both reported', () => {
  const rules = [
    { field: 'pw', check: nonEmpty, message: 'pw required' },
    { field: 'pw', check: minLen(8), message: 'pw too short' },
  ];
  const r = validate({ pw: '' }, rules);
  assert.equal(r.valid, false);
  assert.equal(r.errors.length, 2, 'both rules should fail');
});

test('missing field — check sees undefined', () => {
  const r = validate({}, [{ field: 'name', check: nonEmpty, message: 'name required' }]);
  assert.equal(r.valid, false);
  assert.equal(r.errors[0].message, 'name required');
});

test('rule check that throws — treated as failure, not propagated', () => {
  const r = validate({ x: 1 }, [{ field: 'x', check: () => { throw new Error('boom'); }, message: 'check errored' }]);
  assert.equal(r.valid, false);
  assert.equal(r.errors[0].message, 'check errored');
});

test('input null — returns valid:false with single * error', () => {
  const r = validate(null, [{ field: 'x', check: nonEmpty, message: 'x required' }]);
  assert.equal(r.valid, false);
  assert.equal(r.errors.length, 1);
  assert.equal(r.errors[0].field, '*');
});

test('input undefined — returns valid:false with single * error', () => {
  const r = validate(undefined, []);
  assert.equal(r.valid, false);
  assert.equal(r.errors[0].field, '*');
});

test('input not an object (string) — returns valid:false with * error', () => {
  const r = validate('hello', []);
  assert.equal(r.valid, false);
  assert.equal(r.errors[0].field, '*');
});

test('rules not an array — returns valid:false with * error', () => {
  const r = validate({}, 'not an array');
  assert.equal(r.valid, false);
  assert.equal(r.errors[0].field, '*');
});

test('errors preserves rule order', () => {
  const rules = [
    { field: 'a', check: nonEmpty, message: 'a' },
    { field: 'b', check: nonEmpty, message: 'b' },
    { field: 'c', check: nonEmpty, message: 'c' },
  ];
  const r = validate({ a: '', b: '', c: '' }, rules);
  assert.deepEqual(r.errors.map(e => e.message), ['a', 'b', 'c']);
});

test('zero-valued numeric field passes isPositive only if > 0', () => {
  const r = validate({ n: 0 }, [{ field: 'n', check: isPositive, message: 'n>0' }]);
  assert.equal(r.valid, false);
});

test('truthy non-boolean returns from check counts as pass', () => {
  const r = validate({ x: 'hi' }, [{ field: 'x', check: (v) => v && v.length, message: 'x' }]);
  assert.equal(r.valid, true);
});

test('falsy non-boolean returns count as fail (0)', () => {
  const r = validate({ x: '' }, [{ field: 'x', check: (v) => v.length, message: 'x empty' }]);
  assert.equal(r.valid, false);
});

test('errors entries have ONLY field and message keys', () => {
  const r = validate({ x: '' }, [{ field: 'x', check: nonEmpty, message: 'm' }]);
  const keys = Object.keys(r.errors[0]).sort();
  assert.deepEqual(keys, ['field', 'message']);
});

test('result has ONLY valid and errors keys', () => {
  const r = validate({}, []);
  const keys = Object.keys(r).sort();
  assert.deepEqual(keys, ['errors', 'valid']);
});

test('valid is strictly boolean, not truthy', () => {
  const r = validate({ x: 1 }, []);
  assert.strictEqual(typeof r.valid, 'boolean');
});

test('errors is always an array even on success', () => {
  const r = validate({}, []);
  assert.ok(Array.isArray(r.errors));
});

test('does NOT mutate input', () => {
  const input = { name: 'Ada' };
  const before = JSON.stringify(input);
  validate(input, [{ field: 'name', check: nonEmpty, message: 'm' }]);
  assert.equal(JSON.stringify(input), before);
});

test('does NOT mutate rules array', () => {
  const rules = [{ field: 'x', check: nonEmpty, message: 'm' }];
  const before = JSON.stringify(rules.map(r => ({ field: r.field, message: r.message })));
  validate({ x: '' }, rules);
  const after = JSON.stringify(rules.map(r => ({ field: r.field, message: r.message })));
  assert.equal(after, before);
});

test('large rule set (50 rules) runs all', () => {
  const rules = Array.from({ length: 50 }, (_, i) => ({
    field: `f${i}`, check: nonEmpty, message: `m${i}`,
  }));
  const r = validate({}, rules);
  assert.equal(r.errors.length, 50);
});

test('all rules pass on a fully-valid object', () => {
  const rules = [
    { field: 'name', check: nonEmpty, message: 'n' },
    { field: 'email', check: isEmail, message: 'e' },
    { field: 'age', check: isPositive, message: 'a' },
  ];
  const r = validate({ name: 'Ada', email: 'a@b.c', age: 30 }, rules);
  assert.equal(r.valid, true);
  assert.deepEqual(r.errors, []);
});
