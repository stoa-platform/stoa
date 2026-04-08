// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package types

import "encoding/json"

// MCPServerSummary represents an MCP server in list responses
type MCPServerSummary struct {
	ID          string `json:"id" yaml:"id"`
	Name        string `json:"name" yaml:"name"`
	DisplayName string `json:"display_name" yaml:"displayName"`
	Category    string `json:"category" yaml:"category"`
	Status      string `json:"status" yaml:"status"`
	ToolCount   int    `json:"tool_count" yaml:"toolCount"`
}

// MCPServerListResponse is the response from listing MCP servers
type MCPServerListResponse struct {
	Servers    []MCPServerSummary `json:"servers" yaml:"servers"`
	TotalCount int               `json:"total_count" yaml:"totalCount"`
}

// MCPToolSummary represents a tool in list responses
type MCPToolSummary struct {
	Name        string `json:"name" yaml:"name"`
	DisplayName string `json:"display_name" yaml:"displayName"`
	Description string `json:"description" yaml:"description"`
	Enabled     bool   `json:"enabled" yaml:"enabled"`
	ServerName  string `json:"server_name" yaml:"serverName"`
}

// MCPToolListResponse is the response from listing tools
type MCPToolListResponse struct {
	Tools []MCPToolSummary `json:"tools" yaml:"tools"`
}

// MCPToolCallResponse is the response from invoking a tool
type MCPToolCallResponse struct {
	Result json.RawMessage `json:"result" yaml:"result"`
	Error  string          `json:"error,omitempty" yaml:"error,omitempty"`
}

// MCPHealthResponse is the response from the MCP health endpoint
type MCPHealthResponse struct {
	Status  string `json:"status" yaml:"status"`
	Version string `json:"version,omitempty" yaml:"version,omitempty"`
	Uptime  string `json:"uptime,omitempty" yaml:"uptime,omitempty"`
}
