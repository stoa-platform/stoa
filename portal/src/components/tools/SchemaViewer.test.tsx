import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SchemaViewer } from './SchemaViewer';
import type { MCPInputSchema } from '../../types';

const sampleSchema: MCPInputSchema = {
  type: 'object',
  properties: {
    name: {
      type: 'string',
      description: 'The user name',
      minLength: 1,
      maxLength: 100,
    },
    age: {
      type: 'integer',
      description: 'User age',
      minimum: 0,
      maximum: 150,
    },
    role: {
      type: 'string',
      enum: ['admin', 'user', 'viewer'],
    },
    tags: {
      type: 'array',
      items: { type: 'string' },
    },
    address: {
      type: 'object',
      properties: {
        city: { type: 'string' },
      },
    },
  },
  required: ['name'],
};

describe('SchemaViewer', () => {
  it('should show "No schema defined" when schema is null', () => {
    render(<SchemaViewer schema={null} />);
    expect(screen.getByText('No schema defined')).toBeInTheDocument();
  });

  it('should show "No schema defined" when schema is undefined', () => {
    render(<SchemaViewer schema={undefined} />);
    expect(screen.getByText('No schema defined')).toBeInTheDocument();
  });

  it('should render title with property count', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    expect(screen.getByText('Input Schema')).toBeInTheDocument();
    expect(screen.getByText(/5 properties/)).toBeInTheDocument();
    expect(screen.getByText(/1 required/)).toBeInTheDocument();
  });

  it('should accept custom title', () => {
    render(<SchemaViewer schema={sampleSchema} title="Custom Title" />);
    expect(screen.getByText('Custom Title')).toBeInTheDocument();
  });

  it('should show property names', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    expect(screen.getByText('name')).toBeInTheDocument();
    expect(screen.getByText('age')).toBeInTheDocument();
    expect(screen.getByText('role')).toBeInTheDocument();
  });

  it('should mark required fields', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    const requiredBadges = screen.getAllByText('required');
    expect(requiredBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('should show type badges', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    expect(screen.getAllByText('string').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('integer')).toBeInTheDocument();
    expect(screen.getByText('array')).toBeInTheDocument();
  });

  it('should show property descriptions', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    expect(screen.getByText('The user name')).toBeInTheDocument();
    expect(screen.getByText('User age')).toBeInTheDocument();
  });

  it('should show constraints', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    expect(screen.getByText('minLen: 1')).toBeInTheDocument();
    expect(screen.getByText('maxLen: 100')).toBeInTheDocument();
    expect(screen.getByText('min: 0')).toBeInTheDocument();
    expect(screen.getByText('max: 150')).toBeInTheDocument();
  });

  it('should show enum values', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    expect(screen.getByText('"admin"')).toBeInTheDocument();
    expect(screen.getByText('"user"')).toBeInTheDocument();
    expect(screen.getByText('"viewer"')).toBeInTheDocument();
  });

  it('should toggle to raw JSON view', () => {
    render(<SchemaViewer schema={sampleSchema} />);
    fireEvent.click(screen.getByText('Raw JSON'));
    expect(screen.getByText(/"name"/)).toBeInTheDocument();
  });

  it('should copy schema to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<SchemaViewer schema={sampleSchema} />);
    fireEvent.click(screen.getByText('Copy'));
    expect(writeText).toHaveBeenCalled();
  });

  it('should show "No properties" for empty schema', () => {
    const emptySchema: MCPInputSchema = { type: 'object', properties: {} };
    render(<SchemaViewer schema={emptySchema} />);
    expect(screen.getByText('No properties defined in schema')).toBeInTheDocument();
  });

  it('should show additionalProperties warning', () => {
    const strictSchema: MCPInputSchema = {
      type: 'object',
      properties: { x: { type: 'string' } },
      additionalProperties: false,
    };
    render(<SchemaViewer schema={strictSchema} />);
    expect(screen.getByText('Additional properties not allowed')).toBeInTheDocument();
  });
});
