// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package get

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/clientx"
	"github.com/stoa-platform/stoa-go/pkg/client"
	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

var outputFormat string

// NewGetCmd creates the get command
func NewGetCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "get",
		Short: "Display one or many resources",
		Long: `Display one or many resources.

Prints a table of the most important information about the specified resources.
You can filter the list using a NAME or use -o for different output formats.

Examples:
  # List all APIs in table format
  stoactl get apis

  # Get a specific API
  stoactl get api billing-api

  # List APIs in wide format (more columns)
  stoactl get apis -o wide

  # Get API as YAML
  stoactl get api billing-api -o yaml

  # Get APIs as JSON
  stoactl get apis -o json`,
	}

	cmd.PersistentFlags().StringVarP(&outputFormat, "output", "o", "table", "Output format: table, wide, yaml, json")

	cmd.AddCommand(newGetAPIsCmd())
	cmd.AddCommand(newGetTenantsCmd())
	cmd.AddCommand(newGetSubscriptionsCmd())
	cmd.AddCommand(newGetGatewaysCmd())
	cmd.AddCommand(newGetConsumersCmd())
	cmd.AddCommand(newGetContractsCmd())
	cmd.AddCommand(newGetServiceAccountsCmd())
	cmd.AddCommand(newGetEnvironmentsCmd())
	cmd.AddCommand(newGetPlansCmd())
	cmd.AddCommand(newGetWebhooksCmd())

	return cmd
}

func newGetAPIsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "apis [name]",
		Aliases: []string{"api"},
		Short:   "Display APIs",
		Long: `Display one or many APIs.

Examples:
  stoactl get apis
  stoactl get api billing-api
  stoactl get apis -o yaml`,
		Args: cobra.MaximumNArgs(1),
		RunE: runGetAPIs,
	}
}

func runGetAPIs(cmd *cobra.Command, args []string) error {
	c, err := clientx.New(cmd)
	if err != nil {
		return err
	}

	format := output.ParseFormat(outputFormat)
	printer := output.NewPrinter(format)

	// Single API
	if len(args) == 1 {
		return getAPI(c, printer, args[0])
	}

	// List all APIs
	return listAPIs(c, printer)
}

func getAPI(c *client.Client, printer *output.Printer, name string) error {
	api, err := c.GetAPI(name)
	if err != nil {
		return err
	}

	switch printer.Format {
	case output.FormatYAML:
		resource := apiToResource(api)
		return printer.PrintYAML(resource)
	case output.FormatJSON:
		return printer.PrintJSON(api)
	default:
		headers := []string{"NAME", "VERSION", "STATUS", "BACKEND"}
		rows := [][]string{{api.Name, api.Version, api.Status, api.BackendURL}}
		printer.PrintTable(headers, rows)
	}

	return nil
}

func listAPIs(c *client.Client, printer *output.Printer) error {
	resp, err := c.ListAPIs()
	if err != nil {
		return err
	}

	if len(resp.Items) == 0 {
		output.Info("No APIs found.")
		return nil
	}

	switch printer.Format {
	case output.FormatYAML:
		var resources []types.Resource
		for _, api := range resp.Items {
			resources = append(resources, apiToResource(&api))
		}
		return printer.PrintYAML(resources)
	case output.FormatJSON:
		return printer.PrintJSON(resp.Items)
	case output.FormatWide:
		headers := []string{"NAME", "DISPLAY NAME", "VERSION", "STATUS", "BACKEND", "TENANT", "TAGS"}
		var rows [][]string
		for _, api := range resp.Items {
			rows = append(rows, []string{
				api.Name,
				api.DisplayName,
				api.Version,
				api.Status,
				api.BackendURL,
				api.TenantID,
				strings.Join(api.Tags, ","),
			})
		}
		printer.PrintTable(headers, rows)
	default:
		headers := []string{"NAME", "VERSION", "STATUS", "BACKEND"}
		var rows [][]string
		for _, api := range resp.Items {
			rows = append(rows, []string{api.Name, api.Version, api.Status, api.BackendURL})
		}
		printer.PrintTable(headers, rows)
	}

	return nil
}

func apiToResource(api *types.API) types.Resource {
	return types.Resource{
		APIVersion: types.CanonicalAPIVersion,
		Kind:       "API",
		Metadata: types.Metadata{
			Name:      api.Name,
			Namespace: api.TenantID,
		},
		Spec: types.APISpec{
			Version:     api.Version,
			Description: api.Description,
			Upstream: types.UpstreamSpec{
				URL: api.BackendURL,
			},
			Catalog: types.CatalogSpec{
				DisplayName: api.DisplayName,
				Tags:        api.Tags,
			},
		},
	}
}

// GetOutputFormat returns the current output format
func GetOutputFormat() string {
	return outputFormat
}

func newGetTenantsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "tenants [id]",
		Aliases: []string{"tenant"},
		Short:   "Display tenants",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
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
				headers := []string{"ID", "NAME", "DISPLAY NAME", "STATUS", "OWNER", "APIS", "CREATED"}
				var rows [][]string
				for _, t := range tenants {
					rows = append(rows, []string{
						t.ID, t.Name, t.DisplayName, t.Status,
						t.OwnerEmail, fmt.Sprintf("%d", t.APICount), t.CreatedAt,
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
		},
	}
}

func newGetSubscriptionsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "subscriptions [id]",
		Aliases: []string{"subscription", "sub", "subs"},
		Short:   "Display subscriptions",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
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
			}

			resp, err := c.ListSubscriptions("", 1, 50)
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
}

func newGetGatewaysCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "gateways [id]",
		Aliases: []string{"gateway", "gw"},
		Short:   "Display gateway instances",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
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
			}

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

func newGetConsumersCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "consumers [id]",
		Aliases: []string{"consumer"},
		Short:   "Display consumers",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
				consumer, err := c.GetConsumer(args[0])
				if err != nil {
					return err
				}
				switch printer.Format {
				case output.FormatJSON:
					return printer.PrintJSON(consumer)
				case output.FormatYAML:
					return printer.PrintYAML(consumer)
				default:
					headers := []string{"ID", "NAME", "EMAIL", "STATUS", "TENANT"}
					rows := [][]string{{consumer.ID, consumer.Name, consumer.Email, consumer.Status, consumer.TenantID}}
					printer.PrintTable(headers, rows)
				}
				return nil
			}

			resp, err := c.ListConsumers()
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No consumers found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			case output.FormatWide:
				headers := []string{"ID", "NAME", "DISPLAY NAME", "EMAIL", "STATUS", "TENANT", "CREATED"}
				var rows [][]string
				for _, cs := range resp.Items {
					rows = append(rows, []string{
						cs.ID, cs.Name, cs.DisplayName, cs.Email, cs.Status, cs.TenantID, cs.CreatedAt,
					})
				}
				printer.PrintTable(headers, rows)
			default:
				headers := []string{"ID", "NAME", "EMAIL", "STATUS"}
				var rows [][]string
				for _, cs := range resp.Items {
					rows = append(rows, []string{cs.ID, cs.Name, cs.Email, cs.Status})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGetContractsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "contracts [id]",
		Aliases: []string{"contract", "uac"},
		Short:   "Display Universal API Contracts",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
				contract, err := c.GetContract(args[0])
				if err != nil {
					return err
				}
				switch printer.Format {
				case output.FormatJSON:
					return printer.PrintJSON(contract)
				case output.FormatYAML:
					return printer.PrintYAML(contract)
				default:
					headers := []string{"ID", "NAME", "VERSION", "STATUS", "TENANT"}
					rows := [][]string{{contract.ID, contract.Name, contract.Version, contract.Status, contract.TenantID}}
					printer.PrintTable(headers, rows)
				}
				return nil
			}

			resp, err := c.ListContracts()
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No contracts found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			case output.FormatWide:
				headers := []string{"ID", "NAME", "DISPLAY NAME", "VERSION", "STATUS", "TENANT", "CREATED"}
				var rows [][]string
				for _, ct := range resp.Items {
					rows = append(rows, []string{
						ct.ID, ct.Name, ct.DisplayName, ct.Version, ct.Status, ct.TenantID, ct.CreatedAt,
					})
				}
				printer.PrintTable(headers, rows)
			default:
				headers := []string{"ID", "NAME", "VERSION", "STATUS"}
				var rows [][]string
				for _, ct := range resp.Items {
					rows = append(rows, []string{ct.ID, ct.Name, ct.Version, ct.Status})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGetServiceAccountsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "service-accounts",
		Aliases: []string{"service-account", "sa"},
		Short:   "Display service accounts",
		Args:    cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			accounts, err := c.ListServiceAccounts()
			if err != nil {
				return err
			}

			if len(accounts) == 0 {
				output.Info("No service accounts found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(accounts)
			case output.FormatYAML:
				return printer.PrintYAML(accounts)
			default:
				headers := []string{"ID", "NAME", "CLIENT ID", "STATUS", "CREATED"}
				var rows [][]string
				for _, sa := range accounts {
					rows = append(rows, []string{sa.ID, sa.Name, sa.ClientID, sa.Status, sa.CreatedAt})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGetEnvironmentsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "environments",
		Aliases: []string{"environment", "env", "envs"},
		Short:   "Display environments",
		Args:    cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			resp, err := c.ListEnvironments()
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No environments found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			default:
				headers := []string{"ID", "NAME", "TYPE", "URL", "STATUS"}
				var rows [][]string
				for _, e := range resp.Items {
					rows = append(rows, []string{e.ID, e.Name, e.Type, e.URL, e.Status})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGetPlansCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "plans [id]",
		Aliases: []string{"plan"},
		Short:   "Display subscription plans",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
				plan, err := c.GetPlan(args[0])
				if err != nil {
					return err
				}
				switch printer.Format {
				case output.FormatJSON:
					return printer.PrintJSON(plan)
				case output.FormatYAML:
					return printer.PrintYAML(plan)
				default:
					headers := []string{"ID", "NAME", "SLUG", "STATUS", "TENANT"}
					rows := [][]string{{plan.ID, plan.Name, plan.Slug, plan.Status, plan.TenantID}}
					printer.PrintTable(headers, rows)
				}
				return nil
			}

			resp, err := c.ListPlans()
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No plans found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			case output.FormatWide:
				headers := []string{"ID", "NAME", "SLUG", "DISPLAY NAME", "STATUS", "TENANT", "CREATED"}
				var rows [][]string
				for _, p := range resp.Items {
					rows = append(rows, []string{
						p.ID, p.Name, p.Slug, p.DisplayName, p.Status, p.TenantID, p.CreatedAt,
					})
				}
				printer.PrintTable(headers, rows)
			default:
				headers := []string{"ID", "NAME", "SLUG", "STATUS"}
				var rows [][]string
				for _, p := range resp.Items {
					rows = append(rows, []string{p.ID, p.Name, p.Slug, p.Status})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}

func newGetWebhooksCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "webhooks [id]",
		Aliases: []string{"webhook", "wh"},
		Short:   "Display webhook configurations",
		Args:    cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := clientx.New(cmd)
			if err != nil {
				return err
			}

			format := output.ParseFormat(outputFormat)
			printer := output.NewPrinter(format)

			if len(args) == 1 {
				wh, err := c.GetWebhook(args[0])
				if err != nil {
					return err
				}
				switch printer.Format {
				case output.FormatJSON:
					return printer.PrintJSON(wh)
				case output.FormatYAML:
					return printer.PrintYAML(wh)
				default:
					enabled := "false"
					if wh.Enabled {
						enabled = "true"
					}
					headers := []string{"ID", "NAME", "URL", "ENABLED", "TENANT"}
					rows := [][]string{{wh.ID, wh.Name, wh.URL, enabled, wh.TenantID}}
					printer.PrintTable(headers, rows)
				}
				return nil
			}

			resp, err := c.ListWebhooks()
			if err != nil {
				return err
			}

			if len(resp.Items) == 0 {
				output.Info("No webhooks found.")
				return nil
			}

			switch printer.Format {
			case output.FormatJSON:
				return printer.PrintJSON(resp.Items)
			case output.FormatYAML:
				return printer.PrintYAML(resp.Items)
			default:
				headers := []string{"ID", "NAME", "URL", "ENABLED"}
				var rows [][]string
				for _, wh := range resp.Items {
					enabled := "false"
					if wh.Enabled {
						enabled = "true"
					}
					rows = append(rows, []string{wh.ID, wh.Name, wh.URL, enabled})
				}
				printer.PrintTable(headers, rows)
			}

			return nil
		},
	}
}
