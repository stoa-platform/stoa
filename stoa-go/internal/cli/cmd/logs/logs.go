// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package logs implements the top-level `stoactl logs` command (CAB-1412).
package logs

import (
	"fmt"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/cmdflags"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

var (
	logEnv   string
	logLimit int
)

// NewLogsCmd creates the top-level logs command.
func NewLogsCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "logs <api-name>",
		Short: "Show deployment history for an API",
		Long: `Show recent deployments for an API, including status and error details.

Examples:
  stoactl logs customer-api
  stoactl logs customer-api --env production
  stoactl logs customer-api --limit 5`,
		Args: cobra.ExactArgs(1),
		RunE: runLogs,
	}

	cmd.Flags().StringVar(&logEnv, "env", "", "Filter by environment (dev, staging, production)")
	cmd.Flags().IntVar(&logLimit, "limit", 10, "Number of recent deployments to show")

	return cmd
}

func runLogs(_ *cobra.Command, args []string) error {
	apiName := args[0]

	c, err := cmdflags.NewClientForMode()
	if err != nil {
		return err
	}

	// Resolve API name → UUID if registered in the catalog; fall back to using
	// name as api_id directly (the convention for stoa.yaml-based deploys).
	apiID := apiName
	if api, err := c.GetAPI(apiName); err == nil {
		apiID = api.ID
	}

	resp, err := c.ListDeployments(apiID, logEnv, "", 1, logLimit)
	if err != nil {
		return err
	}

	if len(resp.Items) == 0 {
		output.Info("No deployments found for %q.", apiName)
		return nil
	}

	headers := []string{"ID", "ENV", "VERSION", "STATUS", "BY", "STARTED", "MESSAGE"}
	var rows [][]string
	for _, d := range resp.Items {
		msg := d.ErrorMessage
		if msg == "" && d.Status == "success" {
			msg = "deployed successfully"
		}
		rows = append(rows, []string{
			shortID(d.ID),
			strings.ToUpper(d.Environment),
			d.Version,
			statusLabel(d.Status),
			d.DeployedBy,
			formatTime(d.CreatedAt),
			msg,
		})
	}

	printer := output.NewPrinter(output.FormatTable)
	printer.PrintTable(headers, rows)

	if resp.Total > logLimit {
		fmt.Printf("  (showing %d of %d — use --limit to show more)\n", logLimit, resp.Total)
	}

	return nil
}

func shortID(id string) string {
	if len(id) >= 8 {
		return id[:8]
	}
	return id
}

func statusLabel(status string) string {
	switch status {
	case "success":
		return "OK"
	case "failed":
		return "FAIL"
	case "in_progress":
		return "..."
	case "pending":
		return "WAIT"
	case "rolled_back":
		return "<<<"
	default:
		return status
	}
}

func formatTime(t string) string {
	parsed, err := time.Parse(time.RFC3339, t)
	if err != nil {
		return t
	}
	return parsed.Format("2006-01-02 15:04")
}
