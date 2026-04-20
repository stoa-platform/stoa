// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package audit implements the stoactl audit command group.
package audit

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/cmdflags"
	auditpkg "github.com/stoa-platform/stoa-go/pkg/client/audit"
	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/redact"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

// NewAuditCmd creates the audit command group.
func NewAuditCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "audit",
		Short: "Query and export audit logs",
		Long: `Query and export audit trail entries for compliance and investigation.

Examples:
  # Export last 7 days for tenant (PII redacted by default)
  stoactl audit export --tenant acme --since 7d

  # Export last 30 days as CSV
  stoactl audit export --tenant acme --since 30d -o csv

  # Export with full PII (shows warning)
  stoactl audit export --tenant acme --since 7d --redact-pii=false

  # Filter by action
  stoactl audit export --tenant acme --since 7d --action api_call`,
	}

	cmd.AddCommand(newExportCmd())

	return cmd
}

var (
	exportTenantID  string
	exportSince     string
	exportAction    string
	exportRedactPII bool
	exportOutputFmt string
)

func newExportCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "export",
		Short: "Export audit log entries",
		Long: `Export audit log entries for a tenant. PII (emails, IPs) is redacted by default.

Time range can be relative (7d, 30d, 24h) or absolute (2026-01-01).`,
		RunE: runExport,
	}

	cmd.Flags().StringVar(&exportTenantID, "tenant", "", "Tenant ID (required)")
	cmd.Flags().StringVar(&exportSince, "since", "7d", "Time range: 7d, 30d, 24h, or ISO date")
	cmd.Flags().StringVar(&exportAction, "action", "", "Filter by action type")
	cmd.Flags().BoolVar(&exportRedactPII, "redact-pii", true, "Mask emails and IPs in output")
	cmd.Flags().StringVarP(&exportOutputFmt, "output", "o", "table", "Output format: table, json, yaml, csv")
	_ = cmd.MarkFlagRequired("tenant")

	return cmd
}

func runExport(_ *cobra.Command, _ []string) error {
	c, err := cmdflags.NewClientForMode()
	if err != nil {
		return err
	}

	if !exportRedactPII {
		fmt.Fprintln(os.Stderr, "Warning: PII redaction disabled — output may contain personal data")
	}

	startDate, err := parseSince(exportSince)
	if err != nil {
		return fmt.Errorf("invalid --since value %q: %w", exportSince, err)
	}

	svc := c.Audit()
	format := output.ParseFormat(exportOutputFmt)

	// CSV uses server-side export endpoint
	if exportOutputFmt == "csv" {
		return exportCSV(svc, startDate)
	}

	// Fetch all entries with pagination
	entries, err := svc.ExportAll(auditpkg.ExportOpts{
		TenantID:  exportTenantID,
		Action:    exportAction,
		StartDate: startDate,
		PageSize:  500,
	})
	if err != nil {
		return fmt.Errorf("failed to export audit entries: %w", err)
	}

	if len(entries) == 0 {
		output.Info("No audit entries found.")
		return nil
	}

	if exportRedactPII {
		redactEntries(entries)
	}

	printer := output.NewPrinter(format)

	switch format {
	case output.FormatJSON:
		return printer.PrintJSON(entries)
	case output.FormatYAML:
		return printer.PrintYAML(entries)
	default:
		return printTable(printer, entries)
	}
}

func exportCSV(svc *auditpkg.Service, startDate string) error {
	data, err := svc.ExportCSV(exportTenantID, startDate, "", 10000)
	if err != nil {
		return fmt.Errorf("failed to export CSV: %w", err)
	}

	csvStr := string(data)
	if exportRedactPII {
		csvStr = redact.All(csvStr)
	}

	fmt.Print(csvStr)
	return nil
}

func printTable(printer *output.Printer, entries []types.AuditEntry) error {
	headers := []string{"TIMESTAMP", "ACTION", "RESOURCE", "STATUS", "USER", "IP"}
	var rows [][]string
	for _, e := range entries {
		ts := e.Timestamp
		if len(ts) > 19 {
			ts = ts[:19]
		}
		resource := e.ResourceType
		if e.ResourceID != "" {
			resource += "/" + e.ResourceID
		}
		rows = append(rows, []string{
			ts, e.Action, resource, e.Status, e.UserEmail, e.ClientIP,
		})
	}
	printer.PrintTable(headers, rows)
	output.Info("\nTotal: %d entries", len(entries))
	return nil
}

func redactEntries(entries []types.AuditEntry) {
	for i := range entries {
		entries[i].UserEmail = redact.Email(entries[i].UserEmail)
		entries[i].ClientIP = redact.IP(entries[i].ClientIP)
		if entries[i].UserID != "" {
			entries[i].UserID = redact.Email(entries[i].UserID)
		}
	}
}

var relDurationRegex = regexp.MustCompile(`^(\d+)([dhm])$`)

// parseSince converts a relative or absolute time string to an ISO 8601 date.
func parseSince(s string) (string, error) {
	if s == "" {
		return "", nil
	}

	matches := relDurationRegex.FindStringSubmatch(s)
	if matches != nil {
		n, _ := strconv.Atoi(matches[1])
		var d time.Duration
		switch matches[2] {
		case "d":
			d = time.Duration(n) * 24 * time.Hour
		case "h":
			d = time.Duration(n) * time.Hour
		case "m":
			d = time.Duration(n) * time.Minute
		}
		return time.Now().UTC().Add(-d).Format(time.RFC3339), nil
	}

	// Try parsing as absolute date
	for _, layout := range []string{"2006-01-02", time.RFC3339, "2006-01-02T15:04:05"} {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UTC().Format(time.RFC3339), nil
		}
	}

	// Check if it looks like a relative duration but with invalid unit
	if strings.ContainsAny(s, "0123456789") {
		return "", fmt.Errorf("use format: 7d, 24h, 30m, or YYYY-MM-DD")
	}

	return "", fmt.Errorf("unrecognized date format")
}
