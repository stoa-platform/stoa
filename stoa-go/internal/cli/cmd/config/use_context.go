// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"fmt"

	"github.com/spf13/cobra"

	cfg "github.com/stoa-platform/stoa-go/pkg/config"
)

func newUseContextCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "use-context <name>",
		Short: "Set the current context",
		Long: `Switch to the specified context.

The current context determines which STOA server and tenant
stoactl commands will operate against.

Example:
  stoactl config use-context prod`,
		Args: cobra.ExactArgs(1),
		RunE: runUseContext,
	}
}

func runUseContext(cmd *cobra.Command, args []string) error {
	name := args[0]

	config, err := cfg.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	if err := config.UseContext(name); err != nil {
		return err
	}

	if err := config.Save(); err != nil {
		return fmt.Errorf("failed to save config: %w", err)
	}

	fmt.Printf("Switched to context %q.\n", name)
	return nil
}
