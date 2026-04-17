// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingenierie / Christophe ABOULICAM
package tenant

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/clientx"
	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

var outputFormat string

// NewTenantCmd creates the tenant command group
func NewTenantCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "tenant",
		Short: "Manage tenants",
		Long: `Manage STOA Platform tenants.

Examples:
  stoactl tenant list
  stoactl tenant get acme-corp
  stoactl tenant create --name acme-corp --display-name "Acme Corp"
  stoactl tenant delete acme-corp`,
	}

	cmd.PersistentFlags().StringVarP(&outputFormat, "output", "o", "table", "Output format: table, wide, yaml, json")

	cmd.AddCommand(newTenantListCmd())
	cmd.AddCommand(newTenantGetCmd())
	cmd.AddCommand(newTenantCreateCmd())
	cmd.AddCommand(newTenantDeleteCmd())
	cmd.AddCommand(newTenantStatusCmd())

	return cmd
}

func newTenantStatusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status <id>",
		Short: "Show provisioning status for a tenant",
		Long: `Poll the async provisioning saga for a tenant.

After 'tenant create' the backend fires an async saga (Keycloak group + admin
user + policy seed + Kafka events). Use this command to check progress.

Example:
  stoactl tenant status acme-corp`,
		Args: cobra.ExactArgs(1),
		RunE: runTenantStatus,
	}
}

func runTenantStatus(cmd *cobra.Command, args []string) error {
	c, err := clientx.New(cmd)
	if err != nil {
		return err
	}

	format := output.ParseFormat(outputFormat)
	printer := output.NewPrinter(format)

	st, err := c.GetTenantProvisioningStatus(args[0])
	if err != nil {
		return err
	}

	switch printer.Format {
	case output.FormatJSON:
		return printer.PrintJSON(st)
	case output.FormatYAML:
		return printer.PrintYAML(st)
	default:
		headers := []string{"TENANT", "STATUS", "ATTEMPTS", "KC GROUP", "ERROR"}
		rows := [][]string{{
			st.TenantID, st.ProvisioningStatus,
			fmt.Sprintf("%d", st.ProvisioningAttempts),
			st.KCGroupID, st.ProvisioningError,
		}}
		printer.PrintTable(headers, rows)
	}

	return nil
}

func newTenantListCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List all tenants",
		RunE:  runTenantList,
	}
}

func newTenantGetCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "get <id>",
		Short: "Get a tenant by ID",
		Args:  cobra.ExactArgs(1),
		RunE:  runTenantGet,
	}
}

func newTenantCreateCmd() *cobra.Command {
	var name, displayName, description, ownerEmail string

	cmd := &cobra.Command{
		Use:   "create",
		Short: "Create a new tenant",
		RunE: func(cmd *cobra.Command, args []string) error {
			if name == "" {
				return fmt.Errorf("--name is required")
			}
			if ownerEmail == "" {
				return fmt.Errorf("--owner-email is required")
			}
			if displayName == "" {
				displayName = name
			}

			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			create := &types.TenantCreate{
				Name:        name,
				DisplayName: displayName,
				Description: description,
				OwnerEmail:  ownerEmail,
			}

			tenant, err := c.CreateTenant(create)
			if err != nil {
				return err
			}

			output.Success("Tenant %q created (ID: %s)", tenant.Name, tenant.ID)
			return nil
		},
	}

	cmd.Flags().StringVar(&name, "name", "", "Tenant name (required)")
	cmd.Flags().StringVar(&displayName, "display-name", "", "Display name")
	cmd.Flags().StringVar(&description, "description", "", "Description")
	cmd.Flags().StringVar(&ownerEmail, "owner-email", "", "Owner email address")

	return cmd
}

func newTenantDeleteCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "delete <id>",
		Short: "Delete a tenant",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			if err := c.DeleteTenant(args[0]); err != nil {
				return err
			}

			output.Success("Tenant %q deleted.", args[0])
			return nil
		},
	}
}

func runTenantList(cmd *cobra.Command, args []string) error {
	c, err := clientx.New(cmd)
	if err != nil {
		return err
	}

	format := output.ParseFormat(outputFormat)
	printer := output.NewPrinter(format)

	tenants, err := c.ListTenants()
	if err != nil {
		return err
	}

	if len(tenants) == 0 {
		output.Info("No tenants found.")
		return nil
	}

	switch printer.Format {
	case output.FormatJSON:
		return printer.PrintJSON(tenants)
	case output.FormatYAML:
		return printer.PrintYAML(tenants)
	case output.FormatWide:
		headers := []string{"ID", "NAME", "DISPLAY NAME", "STATUS", "OWNER", "APIS", "APPS", "CREATED"}
		var rows [][]string
		for _, t := range tenants {
			rows = append(rows, []string{
				t.ID, t.Name, t.DisplayName, t.Status,
				t.OwnerEmail, fmt.Sprintf("%d", t.APICount),
				fmt.Sprintf("%d", t.ApplicationCount), t.CreatedAt,
			})
		}
		printer.PrintTable(headers, rows)
	default:
		headers := []string{"ID", "NAME", "STATUS", "APIS"}
		var rows [][]string
		for _, t := range tenants {
			rows = append(rows, []string{t.ID, t.Name, t.Status, fmt.Sprintf("%d", t.APICount)})
		}
		printer.PrintTable(headers, rows)
	}

	return nil
}

func runTenantGet(cmd *cobra.Command, args []string) error {
	c, err := clientx.New(cmd)
	if err != nil {
		return err
	}

	format := output.ParseFormat(outputFormat)
	printer := output.NewPrinter(format)

	tenant, err := c.GetTenant(args[0])
	if err != nil {
		return err
	}

	switch printer.Format {
	case output.FormatJSON:
		return printer.PrintJSON(tenant)
	case output.FormatYAML:
		return printer.PrintYAML(tenant)
	default:
		headers := []string{"ID", "NAME", "DISPLAY NAME", "STATUS", "OWNER"}
		rows := [][]string{{tenant.ID, tenant.Name, tenant.DisplayName, tenant.Status, tenant.OwnerEmail}}
		printer.PrintTable(headers, rows)
	}

	return nil
}
