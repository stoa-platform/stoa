// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package mcp

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/clientx"
	"github.com/stoa-platform/stoa-go/pkg/client"
	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

var (
	outputFormat string
	gatewayURL   string
)

// NewMCPCmd creates the mcp command group
func NewMCPCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "mcp",
		Short: "Interact with MCP servers and tools",
		Long: `Manage MCP (Model Context Protocol) servers and tools on the STOA Platform.

By default, commands talk to the Control Plane API (source of truth).
Use --gateway to bypass the CP API and hit a gateway directly (for debugging).

Examples:
  stoactl mcp list-servers
  stoactl mcp list-tools --server petstore
  stoactl mcp call list-pets --server petstore --input '{"limit": 5}'
  stoactl mcp health
  stoactl mcp health --gateway http://localhost:30080`,
	}

	cmd.PersistentFlags().StringVarP(&outputFormat, "output", "o", "table", "Output format: table, json, yaml")
	cmd.PersistentFlags().StringVar(&gatewayURL, "gateway", "", "Gateway URL for direct access (bypasses CP API RBAC)")

	cmd.AddCommand(newListServersCmd())
	cmd.AddCommand(newListToolsCmd())
	cmd.AddCommand(newCallCmd())
	cmd.AddCommand(newHealthCmd())

	return cmd
}

func newListServersCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "list-servers",
		Short: "List registered MCP servers",
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			resp, err := c.ListMCPServers()
			if err != nil {
				return err
			}

			if len(resp.Servers) == 0 {
				output.Info("No MCP servers found.")
				return nil
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Servers)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Servers)
			default:
				headers := []string{"NAME", "DISPLAY NAME", "CATEGORY", "STATUS", "TOOLS"}
				var rows [][]string
				for _, s := range resp.Servers {
					rows = append(rows, []string{
						s.Name, s.DisplayName, s.Category, s.Status,
						strconv.Itoa(s.ToolCount),
					})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newListToolsCmd() *cobra.Command {
	var serverName string

	cmd := &cobra.Command{
		Use:   "list-tools",
		Short: "List MCP tools",
		Long: `List all MCP tools, optionally filtered by server name.

Examples:
  stoactl mcp list-tools
  stoactl mcp list-tools --server petstore
  stoactl mcp list-tools --gateway http://localhost:30080`,
		RunE: func(cmd *cobra.Command, args []string) error {
			// --gateway mode: hit gateway directly
			if gatewayURL != "" {
				return listToolsFromGateway(gatewayURL)
			}

			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			var allTools []types.MCPToolSummary

			if serverName != "" {
				// Resolve server name to ID
				serverID, srvName, err := resolveServerByName(c, serverName)
				if err != nil {
					return err
				}

				resp, err := c.ListTools(serverID)
				if err != nil {
					return err
				}

				for i := range resp.Tools {
					resp.Tools[i].ServerName = srvName
				}
				allTools = resp.Tools
			} else {
				// List all servers, gather tools from each
				servers, err := c.ListMCPServers()
				if err != nil {
					return err
				}

				for _, s := range servers.Servers {
					resp, err := c.ListTools(s.ID)
					if err != nil {
						continue
					}
					for i := range resp.Tools {
						resp.Tools[i].ServerName = s.Name
					}
					allTools = append(allTools, resp.Tools...)
				}
			}

			if len(allTools) == 0 {
				output.Info("No tools found.")
				return nil
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(allTools)
			case output.FormatYAML:
				return printer.PrintYAML(allTools)
			default:
				headers := []string{"NAME", "DISPLAY NAME", "SERVER", "ENABLED"}
				var rows [][]string
				for _, t := range allTools {
					enabled := "yes"
					if !t.Enabled {
						enabled = "no"
					}
					rows = append(rows, []string{t.Name, t.DisplayName, t.ServerName, enabled})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&serverName, "server", "", "Filter tools by server name")
	return cmd
}

func newCallCmd() *cobra.Command {
	var (
		serverName string
		inputStr   string
	)

	cmd := &cobra.Command{
		Use:   "call <tool-name>",
		Short: "Invoke an MCP tool",
		Long: `Call an MCP tool by name and display the result.

Examples:
  stoactl mcp call list-pets --server petstore --input '{"limit": 5}'
  stoactl mcp call echo --server debug
  stoactl mcp call get-weather --server weather --input '{"city": "Paris"}' -o json`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			toolName := args[0]

			// Validate --input is valid JSON if provided
			var input json.RawMessage
			if inputStr != "" {
				if !json.Valid([]byte(inputStr)) {
					return fmt.Errorf("invalid JSON in --input: %s", inputStr)
				}
				input = json.RawMessage(inputStr)
			}

			// --gateway mode: hit gateway directly
			if gatewayURL != "" {
				return callToolOnGateway(gatewayURL, toolName, input)
			}

			if serverName == "" {
				return fmt.Errorf("--server is required (specify MCP server name)")
			}

			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			serverID, _, err := resolveServerByName(c, serverName)
			if err != nil {
				return err
			}

			resp, err := c.CallTool(serverID, toolName, input)
			if err != nil {
				return err
			}

			if resp.Error != "" {
				return fmt.Errorf("tool error: %s", resp.Error)
			}

			// Pretty-print the result
			var pretty json.RawMessage
			if err := json.Unmarshal(resp.Result, &pretty); err == nil {
				out, _ := json.MarshalIndent(pretty, "", "  ")
				fmt.Println(string(out))
			} else {
				fmt.Println(string(resp.Result))
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&serverName, "server", "", "MCP server name (required)")
	cmd.Flags().StringVar(&inputStr, "input", "", "Tool input as JSON string")
	return cmd
}

func newHealthCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "health",
		Short: "Check MCP health status",
		Long: `Check the health of the MCP subsystem.

Examples:
  stoactl mcp health
  stoactl mcp health --gateway http://localhost:30080
  stoactl mcp health -o json`,
		RunE: func(cmd *cobra.Command, args []string) error {
			// --gateway mode: hit gateway directly
			if gatewayURL != "" {
				return healthFromGateway(gatewayURL)
			}

			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			resp, err := c.MCPHealth()
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp)
			case output.FormatYAML:
				return printer.PrintYAML(resp)
			default:
				headers := []string{"STATUS", "VERSION", "UPTIME"}
				rows := [][]string{{resp.Status, resp.Version, resp.Uptime}}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

// resolveServerByName looks up a server by name and returns its ID
func resolveServerByName(c *client.Client, name string) (string, string, error) {
	servers, err := c.ListMCPServers()
	if err != nil {
		return "", "", fmt.Errorf("failed to list servers: %w", err)
	}

	for _, s := range servers.Servers {
		if s.Name == name {
			return s.ID, s.Name, nil
		}
	}

	return "", "", fmt.Errorf("server '%s' not found", name)
}

// --- Gateway direct access helpers ---

func gatewayClient() *http.Client {
	return &http.Client{Timeout: 10 * time.Second}
}

func listToolsFromGateway(gwURL string) error {
	resp, err := gatewayClient().Get(gwURL + "/mcp/v1/tools")
	if err != nil {
		return fmt.Errorf("gateway unreachable: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	// Gateway returns a bare JSON array (not wrapped in {"tools": [...]})
	var tools []types.MCPToolSummary
	if err := json.NewDecoder(resp.Body).Decode(&tools); err != nil {
		return fmt.Errorf("failed to decode gateway response: %w", err)
	}

	if len(tools) == 0 {
		output.Info("No tools found.")
		return nil
	}

	format := output.ParseFormat(outputFormat)
	printer := output.NewPrinter(format)

	switch printer.Format {
	case output.FormatJSON:
		return printer.PrintJSON(tools)
	case output.FormatYAML:
		return printer.PrintYAML(tools)
	default:
		headers := []string{"NAME", "DISPLAY NAME", "SERVER", "ENABLED"}
		var rows [][]string
		for _, t := range tools {
			enabled := "yes"
			if !t.Enabled {
				enabled = "no"
			}
			rows = append(rows, []string{t.Name, t.DisplayName, t.ServerName, enabled})
		}
		printer.PrintTable(headers, rows)
	}

	return nil
}

func callToolOnGateway(gwURL, toolName string, input json.RawMessage) error {
	if input == nil {
		input = json.RawMessage(`{}`)
	}

	body := map[string]any{
		"tool_name": toolName,
		"input":     json.RawMessage(input),
	}
	bodyBytes, _ := json.Marshal(body)

	resp, err := gatewayClient().Post(gwURL+"/mcp/v1/tools/invoke", "application/json", bytes.NewReader(bodyBytes))
	if err != nil {
		return fmt.Errorf("gateway unreachable: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	var result types.MCPToolCallResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to decode gateway response: %w", err)
	}

	if result.Error != "" {
		return fmt.Errorf("tool error: %s", result.Error)
	}

	out, _ := json.MarshalIndent(result.Result, "", "  ")
	fmt.Println(string(out))
	return nil
}

func healthFromGateway(gwURL string) error {
	// Use /mcp/health for rich JSON (status, protocolVersion, tools, activeSessions).
	// /health is a plain text K8s liveness probe ("OK").
	resp, err := gatewayClient().Get(gwURL + "/mcp/health")
	if err != nil {
		return fmt.Errorf("gateway unreachable: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("health check failed: HTTP %d — %s", resp.StatusCode, strings.TrimSpace(string(bodyBytes)))
	}

	var result types.MCPHealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to decode health response: %w", err)
	}

	format := output.ParseFormat(outputFormat)
	printer := output.NewPrinter(format)

	switch printer.Format {
	case output.FormatJSON:
		return printer.PrintJSON(result)
	case output.FormatYAML:
		return printer.PrintYAML(result)
	default:
		// Gateway returns protocolVersion/tools/activeSessions,
		// CP API returns version/uptime — adapt columns
		if result.ProtocolVersion != "" {
			headers := []string{"STATUS", "PROTOCOL", "TOOLS", "SESSIONS"}
			rows := [][]string{{
				result.Status,
				result.ProtocolVersion,
				strconv.Itoa(result.Tools),
				strconv.Itoa(result.ActiveSessions),
			}}
			printer.PrintTable(headers, rows)
		} else {
			headers := []string{"STATUS", "VERSION", "UPTIME"}
			rows := [][]string{{result.Status, result.Version, result.Uptime}}
			printer.PrintTable(headers, rows)
		}
	}

	return nil
}
