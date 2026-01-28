// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ToolSchemaViewer, SchemaJsonViewer } from './ToolSchemaViewer';
import { mockTool } from '../../test/mocks';

describe('ToolSchemaViewer', () => {
  it('renders title', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    expect(screen.getByText('Input Schema')).toBeInTheDocument();
  });

  it('renders custom title', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} title="Parameters" />);

    expect(screen.getByText('Parameters')).toBeInTheDocument();
  });

  it('renders property names', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    Object.keys(mockTool.inputSchema.properties).forEach((propName) => {
      expect(screen.getByText(propName)).toBeInTheDocument();
    });
  });

  it('renders property types', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    // Should show 'string' type
    expect(screen.getAllByText('string').length).toBeGreaterThan(0);
  });

  it('marks required properties', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    // Required props should have the required badge
    const requiredBadges = screen.getAllByText('required');
    expect(requiredBadges.length).toBe(mockTool.inputSchema.required?.length || 0);
  });

  it('renders property descriptions', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    // Check for one of the descriptions
    expect(screen.getByText('Filter by tenant ID')).toBeInTheDocument();
  });

  it('shows enum values for enum properties', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    // Status has an enum
    expect(screen.getByText(/enum: \[draft, published, deprecated\]/)).toBeInTheDocument();
  });

  it('shows default values', () => {
    render(<ToolSchemaViewer schema={mockTool.inputSchema} />);

    // limit has a default of 20
    expect(screen.getByText(/default: 20/)).toBeInTheDocument();
  });

  it('shows message for empty schema', () => {
    const emptySchema = { type: 'object' as const, properties: {} };
    render(<ToolSchemaViewer schema={emptySchema} />);

    expect(screen.getByText('This tool has no input parameters.')).toBeInTheDocument();
  });
});

describe('SchemaJsonViewer', () => {
  it('renders JSON schema as formatted code', () => {
    render(<SchemaJsonViewer schema={mockTool.inputSchema} />);

    // Should contain the type
    expect(screen.getByText(/"type": "object"/)).toBeInTheDocument();
  });

  it('renders in a preformatted block', () => {
    const { container } = render(<SchemaJsonViewer schema={mockTool.inputSchema} />);

    expect(container.querySelector('pre')).toBeInTheDocument();
    expect(container.querySelector('code')).toBeInTheDocument();
  });
});
