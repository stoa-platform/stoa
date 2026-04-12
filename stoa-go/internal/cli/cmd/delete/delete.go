// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package delete

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/client"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

// NewDeleteCmd creates the delete command
func NewDeleteCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "delete",
		Short: "Delete resources",
		Long: `Delete resources by name or ID.

Examples:
  # Delete an API
  stoactl delete api billing-api

  # Delete multiple APIs
  stoactl delete api billing-api payments-api

  # Delete a consumer
  stoactl delete consumer abc-123

  # Delete a contract
  stoactl delete contract my-contract-id`,
	}

	cmd.AddCommand(newDeleteAPICmd())
	cmd.AddCommand(newDeleteTenantCmd())
	cmd.AddCommand(newDeleteGatewayCmd())
	cmd.AddCommand(newDeleteSubscriptionCmd())
	cmd.AddCommand(newDeleteConsumerCmd())
	cmd.AddCommand(newDeleteContractCmd())
	cmd.AddCommand(newDeleteServiceAccountCmd())
	cmd.AddCommand(newDeletePlanCmd())
	cmd.AddCommand(newDeleteWebhookCmd())

	return cmd
}

func newDeleteAPICmd() *cobra.Command {
	return &cobra.Command{
		Use:     "api <name> [name...]",
		Aliases: []string{"apis"},
		Short:   "Delete one or more APIs",
		Long: `Delete one or more APIs by name.

Examples:
  stoactl delete api billing-api
  stoactl delete api billing-api payments-api`,
		Args: cobra.MinimumNArgs(1),
		RunE: runDeleteAPI,
	}
}

func runDeleteAPI(cmd *cobra.Command, args []string) error {
	c, err := client.New()
	if err != nil {
		return err
	}

	var errors []error
	for _, name := range args {
		if err := c.DeleteAPI(name); err != nil {
			output.Error("Failed to delete api %q: %v", name, err)
			errors = append(errors, err)
			continue
		}
		output.Success("api %q deleted", name)
	}

	if len(errors) > 0 {
		return fmt.Errorf("%d resource(s) failed to delete", len(errors))
	}

	return nil
}

func newDeleteTenantCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "tenant <id> [id...]",
		Aliases: []string{"tenants"},
		Short:   "Delete one or more tenants",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "tenant", c.DeleteTenant)
		},
	}
}

func newDeleteGatewayCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "gateway <id> [id...]",
		Aliases: []string{"gateways", "gw"},
		Short:   "Delete one or more gateway instances",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "gateway", c.DeleteGateway)
		},
	}
}

func newDeleteSubscriptionCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "subscription <id> [id...]",
		Aliases: []string{"subscriptions", "sub", "subs"},
		Short:   "Delete one or more subscriptions",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "subscription", c.DeleteSubscription)
		},
	}
}

func newDeleteConsumerCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "consumer <id> [id...]",
		Aliases: []string{"consumers"},
		Short:   "Delete one or more consumers",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "consumer", c.DeleteConsumer)
		},
	}
}

func newDeleteContractCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "contract <id> [id...]",
		Aliases: []string{"contracts", "uac"},
		Short:   "Delete one or more contracts",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "contract", c.DeleteContract)
		},
	}
}

func newDeleteServiceAccountCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "service-account <id> [id...]",
		Aliases: []string{"service-accounts", "sa"},
		Short:   "Delete one or more service accounts",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "service-account", c.DeleteServiceAccount)
		},
	}
}

func newDeletePlanCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "plan <id> [id...]",
		Aliases: []string{"plans"},
		Short:   "Delete one or more subscription plans",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "plan", c.DeletePlan)
		},
	}
}

func newDeleteWebhookCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "webhook <id> [id...]",
		Aliases: []string{"webhooks", "wh"},
		Short:   "Delete one or more webhooks",
		Args:    cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := client.New()
			if err != nil {
				return err
			}
			return deleteResources(args, "webhook", c.DeleteWebhook)
		},
	}
}

// deleteResources is a generic batch-delete helper. It iterates over IDs,
// calls the deleteFn for each, accumulates errors, and returns a summary error.
func deleteResources(ids []string, kind string, deleteFn func(string) error) error {
	var errors []error
	for _, id := range ids {
		if err := deleteFn(id); err != nil {
			output.Error("Failed to delete %s %q: %v", kind, id, err)
			errors = append(errors, err)
			continue
		}
		output.Success("%s %q deleted", kind, id)
	}

	if len(errors) > 0 {
		return fmt.Errorf("%d resource(s) failed to delete", len(errors))
	}

	return nil
}
