// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingenierie / Christophe ABOULICAM
package subscription

import (
	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/clientx"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

var outputFormat string

// NewSubscriptionCmd creates the subscription command group
func NewSubscriptionCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:     "subscription",
		Aliases: []string{"sub", "subscriptions"},
		Short:   "Manage subscriptions",
		Long: `Manage API subscriptions.

Examples:
  stoactl subscription list
  stoactl subscription get <id>
  stoactl subscription approve <id>
  stoactl subscription revoke <id>`,
	}

	cmd.PersistentFlags().StringVarP(&outputFormat, "output", "o", "table", "Output format: table, wide, yaml, json")

	cmd.AddCommand(newSubListCmd())
	cmd.AddCommand(newSubGetCmd())
	cmd.AddCommand(newSubApproveCmd())
	cmd.AddCommand(newSubRevokeCmd())

	return cmd
}

func newSubListCmd() *cobra.Command {
	var status string

	cmd := &cobra.Command{
		Use:   "list",
		Short: "List subscriptions",
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			resp, err := c.ListSubscriptions(status, 1, 50)
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No subscriptions found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			case output.FormatWide:
				headers := []string{"ID", "API", "PLAN", "STATUS", "SUBSCRIBER", "TENANT", "CREATED"}
				var rows [][]string
				for _, s := range resp.Items {
					rows = append(rows, []string{
						s.ID, s.APIName, s.PlanName, s.Status,
						s.SubscriberID, s.TenantID, s.CreatedAt,
					})
				}
				printer.PrintTable(headers, rows)
			default:
				headers := []string{"ID", "API", "PLAN", "STATUS"}
				var rows [][]string
				for _, s := range resp.Items {
					rows = append(rows, []string{s.ID, s.APIName, s.PlanName, s.Status})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&status, "status", "", "Filter by status (pending, approved, revoked)")

	return cmd
}

func newSubGetCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "get <id>",
		Short: "Get a subscription by ID",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			sub, err := c.GetSubscription(args[0])
			if err != nil {
				return err
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(sub)
			case output.FormatYAML:
				return printer.PrintYAML(sub)
			default:
				headers := []string{"ID", "API", "PLAN", "STATUS", "SUBSCRIBER"}
				rows := [][]string{{sub.ID, sub.APIName, sub.PlanName, sub.Status, sub.SubscriberID}}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newSubApproveCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "approve <id>",
		Short: "Approve a pending subscription",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			if err := c.ApproveSubscription(args[0]); err != nil {
				return err
			}

			output.Success("Subscription %q approved.", args[0])
			return nil
		},
	}
}

func newSubRevokeCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "revoke <id>",
		Short: "Revoke an active subscription",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			if err := c.RevokeSubscription(args[0]); err != nil {
				return err
			}

			output.Success("Subscription %q revoked.", args[0])
			return nil
		},
	}
}
