// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingenierie / Christophe ABOULICAM
package gateway

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/clientx"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

var outputFormat string

// NewGatewayCmd creates the gateway command group
func NewGatewayCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:     "gateway",
		Aliases: []string{"gw", "gateways"},
		Short:   "Manage gateway instances",
		Long: `Manage STOA Platform gateway instances.

Examples:
  stoactl gateway list
  stoactl gateway get <id>
  stoactl gateway health <id>`,
	}

	cmd.PersistentFlags().StringVarP(&outputFormat, "output", "o", "table", "Output format: table, wide, yaml, json")

	cmd.AddCommand(newGatewayListCmd())
	cmd.AddCommand(newGatewayGetCmd())
	cmd.AddCommand(newGatewayHealthCmd())

	return cmd
}

func newGatewayListCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List all gateway instances",
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			resp, err := c.ListGateways()
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No gateway instances found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			case output.FormatWide:
				headers := []string{"ID", "NAME", "TYPE", "STATUS", "URL", "ENV", "TENANT", "CREATED"}
				var rows [][]string
				for _, g := range resp.Items {
					rows = append(rows, []string{
						g.ID, g.Name, g.GatewayType, g.Status,
						g.BaseURL, g.Environment, g.TenantID, g.CreatedAt,
					})
				}
				printer.PrintTable(headers, rows)
			default:
				headers := []string{"ID", "NAME", "TYPE", "STATUS", "URL"}
				var rows [][]string
				for _, g := range resp.Items {
					rows = append(rows, []string{g.ID, g.Name, g.GatewayType, g.Status, g.BaseURL})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGatewayGetCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "get <id>",
		Short: "Get a gateway instance by ID",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			gw, err := c.GetGateway(args[0])
			if err != nil {
				return err
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(gw)
			case output.FormatYAML:
				return printer.PrintYAML(gw)
			default:
				headers := []string{"ID", "NAME", "TYPE", "STATUS", "URL", "ENV"}
				rows := [][]string{{gw.ID, gw.Name, gw.GatewayType, gw.Status, gw.BaseURL, gw.Environment}}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGatewayHealthCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "health <id>",
		Short: "Check gateway health",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			health, err := c.GatewayHealth(args[0])
			if err != nil {
				return err
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(health)
			case output.FormatYAML:
				return printer.PrintYAML(health)
			default:
				status := health.Status
				if status == "healthy" || status == "ok" {
					fmt.Printf("Gateway %s: HEALTHY", args[0])
				} else {
					fmt.Printf("Gateway %s: %s", args[0], status)
				}
				if health.Version != "" {
					fmt.Printf(" (version: %s)", health.Version)
				}
				if health.Uptime != "" {
					fmt.Printf(" (uptime: %s)", health.Uptime)
				}
				fmt.Println()
			}

			return nil
		},
	}
}
