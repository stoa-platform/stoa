// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package token_usage

import (
	"encoding/json"
	"fmt"
	"io"
	"sort"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/client"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

var (
	timeRange string
	compare   bool
)

// TokenUsageResponse mirrors the API response from /v1/usage/tokens
type TokenUsageResponse struct {
	TenantID    string           `json:"tenant_id"`
	TimeRange   string           `json:"time_range"`
	TotalTokens int64            `json:"total_tokens"`
	ByTool      map[string]int64 `json:"by_tool"`
}

// TokenCompareResponse mirrors /v1/usage/tokens/compare
type TokenCompareResponse struct {
	TenantID    string                    `json:"tenant_id"`
	TimeRange   string                    `json:"time_range"`
	TotalBefore int64                     `json:"total_before"`
	TotalAfter  int64                     `json:"total_after"`
	TotalSaved  int64                     `json:"total_saved"`
	ByTool      map[string]ToolComparison `json:"by_tool"`
}

// ToolComparison holds before/after for a single tool
type ToolComparison struct {
	Before       int64  `json:"before"`
	After        int64  `json:"after"`
	Saved        int64  `json:"saved"`
	ReductionPct string `json:"reduction_pct"`
}

// NewTokenUsageCmd creates the token-usage command
func NewTokenUsageCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "token-usage",
		Short: "Display token consumption for the current tenant",
		Long: `Display token consumption metrics for the tenant associated with the active context.

Requires authentication. The tenant is determined by the active stoactl context.

Examples:
  # Show last 24h token usage (default)
  stoactl token-usage

  # Show last 7 days
  stoactl token-usage --range 7d

  # Compare before/after optimization
  stoactl token-usage --compare`,
		RunE: runTokenUsage,
	}

	cmd.Flags().StringVar(&timeRange, "range", "24h", "Time range: 1h, 6h, 24h, 7d, 30d")
	cmd.Flags().BoolVar(&compare, "compare", false, "Show before/after optimization comparison")

	return cmd
}

func runTokenUsage(cmd *cobra.Command, args []string) error {
	c, err := client.New()
	if err != nil {
		return err
	}

	if !c.IsAuthenticated() {
		return fmt.Errorf("authentication required. Run 'stoactl auth login' first")
	}

	if compare {
		return runCompare(c)
	}

	usage, err := getTokenUsage(c, timeRange)
	if err != nil {
		return err
	}

	printTokenUsage(usage)
	return nil
}

func runCompare(c *client.Client) error {
	comp, err := getTokenCompare(c, timeRange)
	if err != nil {
		return err
	}

	printTokenCompare(comp)
	return nil
}

func getTokenUsage(c *client.Client, timeRange string) (*TokenUsageResponse, error) {
	path := fmt.Sprintf("/v1/usage/tokens?time_range=%s", timeRange)

	resp, err := c.DoRaw("GET", path, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch token usage: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == 401 || resp.StatusCode == 403 {
		return nil, fmt.Errorf("authentication failed. Run 'stoactl auth login' to refresh your token")
	}

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result TokenUsageResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

func getTokenCompare(c *client.Client, timeRange string) (*TokenCompareResponse, error) {
	path := fmt.Sprintf("/v1/usage/tokens/compare?time_range=%s", timeRange)

	resp, err := c.DoRaw("GET", path, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch comparison: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == 401 || resp.StatusCode == 403 {
		return nil, fmt.Errorf("authentication failed. Run 'stoactl auth login' to refresh your token")
	}

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result TokenCompareResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

func printTokenUsage(usage *TokenUsageResponse) {
	fmt.Printf("Token Usage — Tenant: %s — Range: %s\n", usage.TenantID, usage.TimeRange)
	fmt.Println("─────────────────────────────────────────────")

	if len(usage.ByTool) == 0 {
		output.Info("No token usage recorded for this period.")
		return
	}

	type toolEntry struct {
		name   string
		tokens int64
	}
	var entries []toolEntry
	for name, tokens := range usage.ByTool {
		entries = append(entries, toolEntry{name, tokens})
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].tokens > entries[j].tokens
	})

	headers := []string{"TOOL", "TOKENS", "% OF TOTAL"}
	var rows [][]string
	for _, e := range entries {
		pct := float64(0)
		if usage.TotalTokens > 0 {
			pct = float64(e.tokens) / float64(usage.TotalTokens) * 100
		}
		rows = append(rows, []string{
			e.name,
			formatTokens(e.tokens),
			fmt.Sprintf("%.1f%%", pct),
		})
	}

	printer := output.NewPrinter(output.FormatTable)
	printer.PrintTable(headers, rows)

	fmt.Printf("\nTotal: %s tokens\n", formatTokens(usage.TotalTokens))
}

func printTokenCompare(comp *TokenCompareResponse) {
	fmt.Printf("Token Optimization — Tenant: %s — Range: %s\n", comp.TenantID, comp.TimeRange)
	fmt.Println("═════════════════════════════════════════════════════════════")

	if len(comp.ByTool) == 0 {
		output.Info("No optimization data recorded for this period.")
		return
	}

	type toolEntry struct {
		name string
		comp ToolComparison
	}
	var entries []toolEntry
	for name, tc := range comp.ByTool {
		entries = append(entries, toolEntry{name, tc})
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].comp.Saved > entries[j].comp.Saved
	})

	headers := []string{"TOOL", "BEFORE", "AFTER", "SAVED", "REDUCTION"}
	var rows [][]string
	for _, e := range entries {
		rows = append(rows, []string{
			e.name,
			formatTokens(e.comp.Before),
			formatTokens(e.comp.After),
			formatTokens(e.comp.Saved),
			e.comp.ReductionPct,
		})
	}

	printer := output.NewPrinter(output.FormatTable)
	printer.PrintTable(headers, rows)

	totalPct := float64(0)
	if comp.TotalBefore > 0 {
		totalPct = float64(comp.TotalSaved) / float64(comp.TotalBefore) * 100
	}

	fmt.Println("─────────────────────────────────────────────────────────────")
	fmt.Printf("Before: %s tokens → After: %s tokens → Saved: %s tokens (%.1f%%)\n",
		formatTokens(comp.TotalBefore),
		formatTokens(comp.TotalAfter),
		formatTokens(comp.TotalSaved),
		totalPct,
	)
}

func formatTokens(n int64) string {
	if n >= 1_000_000 {
		return fmt.Sprintf("%.1fM", float64(n)/1_000_000)
	}
	if n >= 1_000 {
		return fmt.Sprintf("%.1fK", float64(n)/1_000)
	}
	return fmt.Sprintf("%d", n)
}
