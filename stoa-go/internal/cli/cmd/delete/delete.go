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
		Long: `Delete resources by name.

Examples:
  # Delete an API
  stoactl delete api billing-api

  # Delete multiple APIs
  stoactl delete api billing-api payments-api`,
	}

	cmd.AddCommand(newDeleteAPICmd())

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
