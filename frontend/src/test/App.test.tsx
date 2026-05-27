import { describe, it, expect } from 'vitest';

describe('App basic sanity', () => {
  it('should pass a trivial test', () => {
    expect(1 + 1).toBe(2);
  });

  it('should have the correct test environment', () => {
    // Verify jsdom is loaded
    expect(typeof document).toBe('object');
    expect(typeof window).toBe('object');
  });
});
