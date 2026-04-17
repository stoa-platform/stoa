// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package cmd

import (
	"os"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/cmd/apply"
	auditcmd "github.com/stoa-platform/stoa-go/internal/cli/cmd/audit"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/auth"
	catalogcmd "github.com/stoa-platform/stoa-go/internal/cli/cmd/catalog"
	bridgecmd "github.com/stoa-platform/stoa-go/internal/cli/cmd/bridge"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/completion"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/config"
	connectcmd "github.com/stoa-platform/stoa-go/internal/cli/cmd/connect"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/delete"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/deploy"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/doctor"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/gateway"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/get"
	initcmd "github.com/stoa-platform/stoa-go/internal/cli/cmd/init"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/logs"
	mcpcmd "github.com/stoa-platform/stoa-go/internal/cli/cmd/mcp"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/subscription"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/tenant"
	"github.com/stoa-platform/stoa-go/internal/cli/cmd/token_usage"
)

var (
	// Version is set at build time
	Version = "dev"
	// Commit is set at build time
	Commit = "none"
)

// AdminMode indicates whether --admin was passed (service account context).
var AdminMode bool

// NamespaceOverride holds the value of the persistent --namespace flag.
// When non-empty, commands should prefer this over metadata.namespace / the
// configured tenant.
var NamespaceOverride string

// Namespace returns the namespace override set via the --namespace flag,
// or an empty string when the flag was not provided.
func Namespace() string { return NamespaceOverride }

var rootCmd = &cobra.Command{
	Use:   "stoactl",
	Short: "STOA Platform CLI",
	Long: `stoactl is a GitOps-native CLI for managing STOA Platform resources.

It provides a declarative, kubectl-like experience for managing APIs,
subscriptions, and other STOA resources through infrastructure-as-code patterns.

Example usage:
  stoactl config set-context prod --server=https://api.gostoa.dev --tenant=acme
  stoactl config use-context prod
  stoactl auth login
  stoactl get apis
  stoactl apply -f api.yaml

Admin mode:
  stoactl --admin get apis         # Uses service account token instead of user OIDC`,
	SilenceUsage:  true,
	SilenceErrors: true,
}

// Execute runs the root command
func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.PersistentFlags().BoolVar(&AdminMode, "admin", false, "Use service account token instead of user OIDC token")
	// `-n` intentionally omitted: the `bridge` command already defines a
	// local `-n` shortcut, and shadowing it globally would break existing
	// scripts. Long form only; users still get kubectl-like UX.
	rootCmd.PersistentFlags().StringVar(&NamespaceOverride, "namespace", "", "Target namespace (overrides metadata.namespace in manifests)")

	apply.SetNamespaceOverrideFn(Namespace)

	rootCmd.AddCommand(catalogcmd.NewCatalogCmd())
	rootCmd.AddCommand(auditcmd.NewAuditCmd())
	rootCmd.AddCommand(config.NewConfigCmd())
	rootCmd.AddCommand(auth.NewAuthCmd())
	rootCmd.AddCommand(get.NewGetCmd())
	rootCmd.AddCommand(apply.NewApplyCmd())
	rootCmd.AddCommand(delete.NewDeleteCmd())
	rootCmd.AddCommand(deploy.NewDeployCmd())
	rootCmd.AddCommand(logs.NewLogsCmd())
	rootCmd.AddCommand(token_usage.NewTokenUsageCmd())
	rootCmd.AddCommand(bridgecmd.NewBridgeCmd())
	rootCmd.AddCommand(initcmd.NewInitCmd())
	rootCmd.AddCommand(doctor.NewDoctorCmd())
	rootCmd.AddCommand(tenant.NewTenantCmd())
	rootCmd.AddCommand(subscription.NewSubscriptionCmd())
	rootCmd.AddCommand(gateway.NewGatewayCmd())
	rootCmd.AddCommand(connectcmd.NewConnectCmd())
	rootCmd.AddCommand(mcpcmd.NewMCPCmd())
	rootCmd.AddCommand(completion.NewCompletionCmd())
	rootCmd.AddCommand(versionCmd)
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print the version information",
	Run: func(cmd *cobra.Command, args []string) {
		cmd.Printf("stoactl version %s (%s)\n", Version, Commit)
	},
}

// ExitCode constants following ADR-001
const (
	ExitSuccess           = 0
	ExitGeneralError      = 1
	ExitMisuse            = 2
	ExitAuthFailed        = 3
	ExitResourceNotFound  = 4
	ExitConflict          = 5
	ExitValidationError   = 6
)

// Exit exits with the specified code
func Exit(code int) {
	os.Exit(code)
}
