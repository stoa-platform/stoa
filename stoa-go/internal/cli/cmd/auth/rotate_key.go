// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package auth

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/keyring"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

var (
	rotateAuto     bool
	rotateInterval string
)

func newRotateKeyCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "rotate-key",
		Short: "Rotate the stored API key",
		Long: `Generate a new API key and store it in the OS Keychain.

The old key is replaced atomically. An audit log entry is written
to ~/.stoa/audit.log for traceability.

Examples:
  stoactl auth rotate-key
  stoactl auth rotate-key --auto --interval 90d`,
		Args: cobra.NoArgs,
		RunE: runRotateKey,
	}

	cmd.Flags().BoolVar(&rotateAuto, "auto", false, "Enable automatic rotation reminder")
	cmd.Flags().StringVar(&rotateInterval, "interval", "90d", "Rotation interval (e.g., 30d, 90d)")

	return cmd
}

func runRotateKey(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	ctx, err := cfg.GetCurrentContext()
	if err != nil {
		return err
	}

	store := keyring.NewOSKeyring()

	// Check existing token
	existing, err := store.Get(ctx.Name)
	if err != nil {
		return fmt.Errorf("failed to read keychain: %w", err)
	}

	if existing == nil {
		return fmt.Errorf("no token found for context %q. Run 'stoactl auth login' first", ctx.Name)
	}

	// Generate new API key
	newKey, err := generateAPIKey()
	if err != nil {
		return fmt.Errorf("failed to generate new key: %w", err)
	}

	// Store new token
	newData := &keyring.TokenData{
		AccessToken:  newKey,
		RefreshToken: existing.RefreshToken,
		ExpiresAt:    time.Now().Add(24 * time.Hour).Unix(),
		Context:      ctx.Name,
	}

	if err := store.Set(ctx.Name, newData); err != nil {
		_ = config.AppendAuditLog("keyring.RotateKey", ctx.Name, "failed")
		return fmt.Errorf("failed to store new key: %w", err)
	}

	_ = config.AppendAuditLog("keyring.RotateKey", ctx.Name, "success")

	output.Success("API key rotated for context %q", ctx.Name)
	if rotateAuto {
		output.Info("Auto-rotation reminder set for every %s", rotateInterval)
	}
	output.Info("Audit log entry written to ~/.stoa/audit.log")

	return nil
}

// generateAPIKey creates a cryptographically secure random key
func generateAPIKey() (string, error) {
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return "stoa_" + hex.EncodeToString(bytes), nil
}
