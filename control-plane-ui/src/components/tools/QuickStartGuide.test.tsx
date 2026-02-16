import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuickStartGuide } from './QuickStartGuide';
import type { MCPTool } from '../../types';

// Mock config
vi.mock('../../config', () => ({
  config: {
    services: {
      mcpGateway: { url: 'https://mcp.test.dev' },
    },
  },
}));

const mockTool: MCPTool = {
  name: 'get_weather',
  description: 'Get weather for a location',
  inputSchema: {
    type: 'object',
    properties: {
      location: { type: 'string' },
      units: { type: 'string', enum: ['celsius', 'fahrenheit'], default: 'celsius' },
      count: { type: 'integer' },
      verbose: { type: 'boolean' },
    },
    required: ['location'],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('QuickStartGuide', () => {
  it('renders three tabs', () => {
    render(<QuickStartGuide tool={mockTool} />);
    expect(screen.getByText('Claude Desktop')).toBeInTheDocument();
    expect(screen.getByText('Python SDK')).toBeInTheDocument();
    expect(screen.getByText('cURL')).toBeInTheDocument();
  });

  it('defaults to Claude Desktop tab with config snippet', () => {
    render(<QuickStartGuide tool={mockTool} />);
    // The code block contains claude_desktop_config.json
    const codeBlocks = screen.getAllByRole('code');
    expect(codeBlocks.length).toBeGreaterThanOrEqual(1);
    const hasDesktopConfig = codeBlocks.some((el) =>
      el.textContent?.includes('claude_desktop_config.json')
    );
    expect(hasDesktopConfig).toBe(true);
  });

  it('switches to Python tab', async () => {
    const user = userEvent.setup();
    render(<QuickStartGuide tool={mockTool} />);

    await user.click(screen.getByText('Python SDK'));
    const codeBlocks = screen.getAllByRole('code');
    const hasPython = codeBlocks.some((el) => el.textContent?.includes('from anthropic'));
    expect(hasPython).toBe(true);
  });

  it('switches to cURL tab', async () => {
    const user = userEvent.setup();
    render(<QuickStartGuide tool={mockTool} />);

    await user.click(screen.getByText('cURL'));
    const codeBlocks = screen.getAllByRole('code');
    const hasCurl = codeBlocks.some((el) => el.textContent?.includes('curl -X'));
    expect(hasCurl).toBe(true);
  });

  it('includes tool name in code snippets', () => {
    render(<QuickStartGuide tool={mockTool} />);
    const codeBlocks = screen.getAllByRole('code');
    const hasToolName = codeBlocks.some((el) => el.textContent?.includes('get_weather'));
    expect(hasToolName).toBe(true);
  });

  it('includes MCP gateway URL in code snippets', () => {
    render(<QuickStartGuide tool={mockTool} />);
    const codeBlocks = screen.getAllByRole('code');
    const hasUrl = codeBlocks.some((el) => el.textContent?.includes('mcp.test.dev'));
    expect(hasUrl).toBe(true);
  });

  it('renders copy button', () => {
    render(<QuickStartGuide tool={mockTool} />);
    const copyButton = screen.getByTitle('Copy to clipboard');
    expect(copyButton).toBeInTheDocument();
  });

  it('generates example args from input schema', async () => {
    const user = userEvent.setup();
    render(<QuickStartGuide tool={mockTool} />);
    // Switch to Python tab which includes example args in the snippet
    await user.click(screen.getByText('Python SDK'));
    const codeBlocks = screen.getAllByRole('code');
    // Should contain example_location for the required string param
    const hasExampleArg = codeBlocks.some((el) => el.textContent?.includes('example_location'));
    expect(hasExampleArg).toBe(true);
  });

  it('shows help text per tab', async () => {
    const user = userEvent.setup();
    render(<QuickStartGuide tool={mockTool} />);

    // Claude Desktop tab help references config path
    expect(screen.getByText(/Application Support\/Claude/)).toBeInTheDocument();

    // Python tab help
    await user.click(screen.getByText('Python SDK'));
    expect(screen.getByText(/pip install anthropic/)).toBeInTheDocument();

    // cURL tab help references YOUR_TOKEN
    await user.click(screen.getByText('cURL'));
    const helpTexts = screen.getAllByText(/YOUR_TOKEN/);
    expect(helpTexts.length).toBeGreaterThanOrEqual(1);
  });

  it('handles tool with no input schema', () => {
    const simpleTool: MCPTool = {
      name: 'simple_tool',
      description: 'A simple tool',
    };
    render(<QuickStartGuide tool={simpleTool} />);
    expect(screen.getByText('Claude Desktop')).toBeInTheDocument();
  });
});
