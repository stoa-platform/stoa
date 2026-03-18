// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"fmt"

	"github.com/spf13/cobra"

	cfg "github.com/stoa-platform/stoa-go/pkg/config"
)

var (
	setContextServer string
	setContextTenant string
)

func newSetContextCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "set-context <name>",
		Short: "Set a context entry in stoactl config",
		Long: `Create or update a context entry in the stoactl configuration.

A context specifies a STOA server and tenant to connect to.

Example:
  stoactl config set-context prod --server=https://api.gostoa.dev --tenant=acme
  stoactl config set-context staging --server=https://api.staging.gostoa.dev --tenant=acme-staging`,
		Args: cobra.ExactArgs(1),
		RunE: runSetContext,
	}

	cmd.Flags().StringVar(&setContextServer, "server", "", "STOA API server URL (required)")
	cmd.Flags().StringVar(&setContextTenant, "tenant", "", "Tenant identifier (required)")

	_ = cmd.MarkFlagRequired("server")
	_ = cmd.MarkFlagRequired("tenant")

	return cmd
}

func runSetContext(cmd *cobra.Command, args []string) error {
	name := args[0]

	config, err := cfg.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	config.SetContext(name, setContextServer, setContextTenant)

	if err := config.Save(); err != nil {
		return fmt.Errorf("failed to save config: %w", err)
	}

	fmt.Printf("Context %q set.\n", name)
	return nil
}
