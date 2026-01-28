// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { useState } from 'react';
import { Copy, Check, Terminal, Code, Cpu } from 'lucide-react';
import type { MCPTool } from '../../types';
import { config } from '../../config';

interface QuickStartGuideProps {
  tool: MCPTool;
}

type TabType = 'claude-desktop' | 'python' | 'curl';

export function QuickStartGuide({ tool }: QuickStartGuideProps) {
  const [activeTab, setActiveTab] = useState<TabType>('claude-desktop');
  const [copied, setCopied] = useState(false);

  const mcpGatewayUrl = config.services.mcpGateway.url;

  const tabs: { id: TabType; label: string; icon: React.ReactNode }[] = [
    { id: 'claude-desktop', label: 'Claude Desktop', icon: <Cpu className="h-4 w-4" /> },
    { id: 'python', label: 'Python SDK', icon: <Code className="h-4 w-4" /> },
    { id: 'curl', label: 'cURL', icon: <Terminal className="h-4 w-4" /> },
  ];

  const generateExampleArgs = (): Record<string, unknown> => {
    const args: Record<string, unknown> = {};
    const properties = tool.inputSchema?.properties || {};
    const required = tool.inputSchema?.required || [];

    for (const [name, prop] of Object.entries(properties)) {
      if (required.includes(name) || Object.keys(args).length < 2) {
        if (prop.enum && prop.enum.length > 0) {
          args[name] = prop.enum[0];
        } else if (prop.default !== undefined) {
          args[name] = prop.default;
        } else {
          switch (prop.type) {
            case 'string':
              args[name] = `example_${name}`;
              break;
            case 'number':
            case 'integer':
              args[name] = 42;
              break;
            case 'boolean':
              args[name] = true;
              break;
            case 'array':
              args[name] = [];
              break;
            case 'object':
              args[name] = {};
              break;
            default:
              args[name] = null;
          }
        }
      }
    }
    return args;
  };

  const exampleArgs = generateExampleArgs();

  const codeSnippets: Record<TabType, string> = {
    'claude-desktop': `// claude_desktop_config.json
{
  "mcpServers": {
    "stoa": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic-ai/mcp-remote",
        "${mcpGatewayUrl}",
        "--header",
        "Authorization: Bearer YOUR_TOKEN"
      ]
    }
  }
}

// After configuring, use the tool in Claude Desktop:
// "Use the ${tool.name} tool to..."`,

    python: `from anthropic import Anthropic
import httpx

# Initialize client with MCP support
client = Anthropic()

# Configure MCP server connection
mcp_config = {
    "servers": {
        "stoa": {
            "url": "${mcpGatewayUrl}",
            "headers": {
                "Authorization": "Bearer YOUR_TOKEN"
            }
        }
    }
}

# Invoke tool via Claude
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=[{
        "type": "mcp",
        "server": "stoa",
        "tool": "${tool.name}"
    }],
    messages=[{
        "role": "user",
        "content": "Use the ${tool.name} tool with: ${JSON.stringify(exampleArgs)}"
    }]
)

print(response.content)`,

    curl: `# List available tools
curl -X GET "${mcpGatewayUrl}/mcp/tools" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json"

# Invoke the ${tool.name} tool
curl -X POST "${mcpGatewayUrl}/mcp/tools/invoke" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "${tool.name}",
    "arguments": ${JSON.stringify(exampleArgs, null, 4).split('\n').join('\n    ')}
  }'`,
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(codeSnippets[activeTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-blue-600 border-b-2 border-blue-600 -mb-px bg-blue-50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Code Block */}
      <div className="relative">
        <button
          onClick={handleCopy}
          className="absolute top-3 right-3 p-2 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 transition-colors z-10"
          title="Copy to clipboard"
        >
          {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
        </button>
        <pre className="bg-gray-900 text-gray-100 p-4 overflow-x-auto text-xs leading-relaxed rounded-b-lg">
          <code>{codeSnippets[activeTab]}</code>
        </pre>
      </div>

      {/* Help Text */}
      <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 rounded-b-lg">
        <p className="text-xs text-gray-500">
          {activeTab === 'claude-desktop' && (
            <>
              Add this configuration to your Claude Desktop config file at{' '}
              <code className="bg-gray-200 px-1 rounded">~/Library/Application Support/Claude/claude_desktop_config.json</code>
            </>
          )}
          {activeTab === 'python' && (
            <>
              Install the Anthropic SDK: <code className="bg-gray-200 px-1 rounded">pip install anthropic</code>
            </>
          )}
          {activeTab === 'curl' && (
            <>Replace <code className="bg-gray-200 px-1 rounded">YOUR_TOKEN</code> with your Keycloak access token.</>
          )}
        </p>
      </div>
    </div>
  );
}
