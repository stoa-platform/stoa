import { describe, it, expect } from 'vitest';
import { validateField } from '../TryItForm';
import type { MCPPropertySchema } from '../../../types';

describe('validateField', () => {
  describe('required fields', () => {
    it('returns error when required field is empty', () => {
      const prop: MCPPropertySchema = { type: 'string' };
      expect(validateField('', prop, true)).toBe('This field is required');
      expect(validateField(undefined, prop, true)).toBe('This field is required');
      expect(validateField(null, prop, true)).toBe('This field is required');
    });

    it('passes when required field has value', () => {
      const prop: MCPPropertySchema = { type: 'string' };
      expect(validateField('hello', prop, true)).toBeUndefined();
    });

    it('skips validation for optional empty fields', () => {
      const prop: MCPPropertySchema = { type: 'string', minLength: 5 };
      expect(validateField('', prop, false)).toBeUndefined();
    });
  });

  describe('string minLength / maxLength', () => {
    it('rejects string shorter than minLength', () => {
      const prop: MCPPropertySchema = { type: 'string', minLength: 3 };
      expect(validateField('ab', prop, false)).toBe('Minimum length is 3');
    });

    it('accepts string at minLength', () => {
      const prop: MCPPropertySchema = { type: 'string', minLength: 3 };
      expect(validateField('abc', prop, false)).toBeUndefined();
    });

    it('rejects string longer than maxLength', () => {
      const prop: MCPPropertySchema = { type: 'string', maxLength: 5 };
      expect(validateField('abcdef', prop, false)).toBe('Maximum length is 5');
    });

    it('accepts string at maxLength', () => {
      const prop: MCPPropertySchema = { type: 'string', maxLength: 5 };
      expect(validateField('abcde', prop, false)).toBeUndefined();
    });
  });

  describe('string pattern', () => {
    it('rejects string not matching pattern', () => {
      const prop: MCPPropertySchema = { type: 'string', pattern: '^[a-z]+$' };
      expect(validateField('ABC123', prop, false)).toBe('Must match pattern: ^[a-z]+$');
    });

    it('accepts string matching pattern', () => {
      const prop: MCPPropertySchema = { type: 'string', pattern: '^[a-z]+$' };
      expect(validateField('abc', prop, false)).toBeUndefined();
    });

    it('skips validation for invalid regex', () => {
      const prop: MCPPropertySchema = { type: 'string', pattern: '[invalid(' };
      expect(validateField('anything', prop, false)).toBeUndefined();
    });
  });

  describe('string enum', () => {
    it('rejects value not in enum', () => {
      const prop: MCPPropertySchema = { type: 'string', enum: ['a', 'b', 'c'] };
      expect(validateField('d', prop, false)).toBe('Must be one of: a, b, c');
    });

    it('accepts value in enum', () => {
      const prop: MCPPropertySchema = { type: 'string', enum: ['a', 'b', 'c'] };
      expect(validateField('b', prop, false)).toBeUndefined();
    });
  });

  describe('number minimum / maximum', () => {
    it('rejects number below minimum', () => {
      const prop: MCPPropertySchema = { type: 'number', minimum: 10 };
      expect(validateField(5, prop, false)).toBe('Minimum value is 10');
    });

    it('accepts number at minimum', () => {
      const prop: MCPPropertySchema = { type: 'number', minimum: 10 };
      expect(validateField(10, prop, false)).toBeUndefined();
    });

    it('rejects number above maximum', () => {
      const prop: MCPPropertySchema = { type: 'number', maximum: 100 };
      expect(validateField(101, prop, false)).toBe('Maximum value is 100');
    });

    it('accepts number at maximum', () => {
      const prop: MCPPropertySchema = { type: 'number', maximum: 100 };
      expect(validateField(100, prop, false)).toBeUndefined();
    });

    it('works for integer type', () => {
      const prop: MCPPropertySchema = { type: 'integer', minimum: 1, maximum: 10 };
      expect(validateField(0, prop, false)).toBe('Minimum value is 1');
      expect(validateField(11, prop, false)).toBe('Maximum value is 10');
      expect(validateField(5, prop, false)).toBeUndefined();
    });
  });
});
