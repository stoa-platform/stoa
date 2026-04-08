// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package completion

import (
	"fmt"

	"github.com/spf13/cobra"
)

// NewCompletionCmd creates the completion command
func NewCompletionCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "completion <bash|zsh|fish>",
		Short: "Generate shell completion scripts",
		Long: `Generate shell completion scripts for stoactl.

Bash:
  source <(stoactl completion bash)
  # Or persist:
  stoactl completion bash > /etc/bash_completion.d/stoactl

Zsh:
  source <(stoactl completion zsh)
  # Or persist:
  stoactl completion zsh > "${fpath[1]}/_stoactl"

Fish:
  stoactl completion fish | source
  # Or persist:
  stoactl completion fish > ~/.config/fish/completions/stoactl.fish`,
		Args:      cobra.ExactArgs(1),
		ValidArgs: []string{"bash", "zsh", "fish"},
		RunE: func(cmd *cobra.Command, args []string) error {
			root := cmd.Root()
			switch args[0] {
			case "bash":
				return root.GenBashCompletionV2(cmd.OutOrStdout(), true)
			case "zsh":
				return root.GenZshCompletion(cmd.OutOrStdout())
			case "fish":
				return root.GenFishCompletion(cmd.OutOrStdout(), true)
			default:
				return fmt.Errorf("unsupported shell: %s (supported: bash, zsh, fish)", args[0])
			}
		},
	}

	return cmd
}
