import { describe, test, expect } from 'vitest';
import { version, greeting } from '../src/index.js';

describe('Smoke', () => {
  test('package exposes version', () => {
    expect(version).toBe('0.0.1');
  });

  test('greeting interpolates name', () => {
    expect(greeting('world')).toBe('Hello, world!');
  });
});
