// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package catalog implements the stoactl catalog command group.
package catalog

import (
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/cmdflags"
	catalogpkg "github.com/stoa-platform/stoa-go/pkg/client/catalog"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

// NewCatalogCmd creates the catalog command group.
func NewCatalogCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "catalog",
		Short: "Manage API catalog synchronization",
		Long: `Manage the API catalog — trigger syncs, view stats, and inspect APIs.

Examples:
  # Show catalog stats and drift (dry-run, default)
  stoactl catalog sync

  # Trigger an actual sync
  stoactl catalog sync --apply

  # Sync a specific tenant
  stoactl catalog sync --apply --tenant acme

  # View stats as JSON
  stoactl catalog sync -o json`,
	}

	cmd.AddCommand(newSyncCmd())

	return cmd
}

var (
	syncApply     bool
	syncTenantID  string
	syncOutputFmt string
)

func newSyncCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "sync",
		Short: "Show catalog drift or trigger synchronization",
		Long: `Without --apply: shows current catalog stats and last sync status (dry-run).
With --apply: triggers a server-side catalog sync from Git and polls until complete.`,
		RunE: runSync,
	}

	cmd.Flags().BoolVar(&syncApply, "apply", false, "Trigger an actual sync (default is dry-run)")
	cmd.Flags().StringVar(&syncTenantID, "tenant", "", "Scope to a specific tenant")
	cmd.Flags().StringVarP(&syncOutputFmt, "output", "o", "table", "Output format: table, json, yaml")

	return cmd
}

func runSync(_ *cobra.Command, _ []string) error {
	c, err := cmdflags.NewAdminClient()
	if err != nil {
		return err
	}

	svc := c.Catalog()
	format := output.ParseFormat(syncOutputFmt)
	printer := output.NewPrinter(format)

	if !syncApply {
		return showDryRun(svc, printer)
	}

	return applySync(svc, printer)
}

func showDryRun(svc *catalogpkg.Service, printer *output.Printer) error {
	stats, err := svc.Stats()
	if err != nil {
		return fmt.Errorf("failed to fetch catalog stats: %w", err)
	}

	switch printer.Format {
	case output.FormatJSON:
		return printer.PrintJSON(stats)
	case output.FormatYAML:
		return printer.PrintYAML(stats)
	default:
		output.Info("Catalog Status (dry-run)")
		output.Info("========================")

		headers := []string{"METRIC", "VALUE"}
		rows := [][]string{
			{"Total APIs", fmt.Sprintf("%d", stats.TotalAPIs)},
			{"Published", fmt.Sprintf("%d", stats.PublishedAPIs)},
			{"Unpublished", fmt.Sprintf("%d", stats.UnpublishedAPIs)},
		}

		for tenant, count := range stats.ByTenant {
			rows = append(rows, []string{fmt.Sprintf("  Tenant: %s", tenant), fmt.Sprintf("%d", count)})
		}
		for category, count := range stats.ByCategory {
			rows = append(rows, []string{fmt.Sprintf("  Category: %s", category), fmt.Sprintf("%d", count)})
		}

		printer.PrintTable(headers, rows)

		if stats.LastSync != nil {
			fmt.Println()
			output.Info("Last Sync: %s (%s) — %d synced, %d failed",
				stats.LastSync.Status, stats.LastSync.CompletedAt,
				stats.LastSync.ItemsSynced, stats.LastSync.ItemsFailed)
		} else {
			fmt.Println()
			output.Info("Last Sync: never")
		}
	}

	return nil
}

func applySync(svc *catalogpkg.Service, printer *output.Printer) error {
	output.Info("Triggering catalog sync...")

	trigger, err := svc.TriggerSync(syncTenantID)
	if err != nil {
		return fmt.Errorf("failed to trigger sync: %w", err)
	}

	output.Info("Status: %s — %s", trigger.Status, trigger.Message)

	if trigger.Status == "sync_already_running" {
		return nil
	}

	// Poll for completion
	output.Info("Waiting for sync to complete...")
	for i := 0; i < 60; i++ {
		time.Sleep(2 * time.Second)

		status, err := svc.SyncStatus()
		if err != nil {
			return fmt.Errorf("failed to check sync status: %w", err)
		}
		if status == nil {
			continue
		}

		switch status.Status {
		case "success":
			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(status)
			case output.FormatYAML:
				return printer.PrintYAML(status)
			default:
				output.Success("Sync completed: %d synced, %d failed (%s)",
					status.ItemsSynced, status.ItemsFailed, status.Duration)
			}
			return nil
		case "failed":
			output.Error("Sync failed: %s", status.ErrorMessage)
			return fmt.Errorf("sync failed")
		}
	}

	return fmt.Errorf("sync timed out after 2 minutes")
}
