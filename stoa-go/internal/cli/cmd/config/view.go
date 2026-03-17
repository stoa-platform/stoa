// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"fmt"

	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"

	cfg "github.com/stoa-platform/stoa-go/pkg/config"
)

func newViewCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "view",
		Short: "Display the current configuration",
		Long:  `Display the merged stoactl configuration from ~/.stoa/config`,
		Args:  cobra.NoArgs,
		RunE:  runView,
	}
}

func runView(cmd *cobra.Command, args []string) error {
	config, err := cfg.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	out, err := yaml.Marshal(config)
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	fmt.Print(string(out))
	return nil
}
