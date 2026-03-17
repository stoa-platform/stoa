// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"fmt"

	"github.com/spf13/cobra"

	cfg "github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

func newGetContextsCmd() *cobra.Command {
	return &cobra.Command{
		Use:     "get-contexts",
		Aliases: []string{"get-context"},
		Short:   "List all available contexts",
		Long: `Display all configured contexts.

The current context is marked with an asterisk (*).

Example:
  stoactl config get-contexts`,
		Args: cobra.NoArgs,
		RunE: runGetContexts,
	}
}

func runGetContexts(cmd *cobra.Command, args []string) error {
	config, err := cfg.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	if len(config.Contexts) == 0 {
		output.Info("No contexts configured. Use 'stoactl config set-context' to create one.")
		return nil
	}

	headers := []string{"CURRENT", "NAME", "SERVER", "TENANT"}
	var rows [][]string

	for _, ctx := range config.Contexts {
		current := ""
		if ctx.Name == config.CurrentContext {
			current = "*"
		}
		rows = append(rows, []string{current, ctx.Name, ctx.Context.Server, ctx.Context.Tenant})
	}

	printer := output.NewPrinter(output.FormatTable)
	printer.PrintTable(headers, rows)

	return nil
}

func newCurrentContextCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "current-context",
		Short: "Display the current context",
		Long: `Display the name of the current context.

Example:
  stoactl config current-context`,
		Args: cobra.NoArgs,
		RunE: runCurrentContext,
	}
}

func runCurrentContext(cmd *cobra.Command, args []string) error {
	config, err := cfg.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	if config.CurrentContext == "" {
		return fmt.Errorf("no current context set")
	}

	fmt.Println(config.CurrentContext)
	return nil
}
