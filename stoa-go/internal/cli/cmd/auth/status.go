// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package auth

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/keyring"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

// JWTClaims represents JWT token claims
type JWTClaims struct {
	Subject   string `json:"sub"`
	Email     string `json:"email"`
	Name      string `json:"name"`
	ExpiresAt int64  `json:"exp"`
	IssuedAt  int64  `json:"iat"`
}

func newStatusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Display authentication status",
		Long: `Display the current authentication status.

Shows whether you are authenticated, token expiration,
and basic user information.

Example:
  stoactl auth status`,
		Args: cobra.NoArgs,
		RunE: runStatus,
	}
}

func runStatus(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	ctx, err := cfg.GetCurrentContext()
	if err != nil {
		return err
	}

	// Try keychain first, then file
	var accessToken string
	var expiresAt int64
	var tokenContext string
	storedIn := "unknown"

	store := keyring.NewOSKeyring()
	tokenData, err := store.Get(ctx.Name)
	if err == nil && tokenData != nil && tokenData.AccessToken != "" {
		accessToken = tokenData.AccessToken
		expiresAt = tokenData.ExpiresAt
		tokenContext = tokenData.Context
		storedIn = store.Name()
	} else {
		// Fallback to file
		tokenCache, err := config.LoadTokenCache()
		if err != nil {
			return fmt.Errorf("failed to load token cache: %w", err)
		}
		if tokenCache != nil && tokenCache.AccessToken != "" {
			accessToken = tokenCache.AccessToken
			expiresAt = tokenCache.ExpiresAt
			tokenContext = tokenCache.Context
			storedIn = "~/.stoa/tokens (deprecated)"
		}
	}

	if accessToken == "" {
		// Env-var auth paths bypass keychain entirely — check them before
		// telling the user to log in. Matches the resolution order in
		// pkg/client/client.go: STOA_ADMIN_KEY > STOA_API_KEY > keychain > file.
		if envToken := os.Getenv("STOA_ADMIN_KEY"); envToken != "" {
			accessToken = envToken
			storedIn = "STOA_ADMIN_KEY env (service account)"
			tokenContext = ctx.Name // env tokens implicitly match current context
		} else if envToken := os.Getenv("STOA_API_KEY"); envToken != "" {
			accessToken = envToken
			storedIn = "STOA_API_KEY env"
			tokenContext = ctx.Name
		} else {
			output.Info("Not authenticated.")
			output.Info("Run 'stoactl auth login' to authenticate.")
			return nil
		}
	}

	// Check if token is for current context
	if tokenContext != ctx.Name {
		output.Info("Token is for a different context (%s).", tokenContext)
		output.Info("Run 'stoactl auth login' to authenticate to %s.", ctx.Name)
		return nil
	}

	// Check if token is expired. Env tokens have expiresAt=0 — treat as
	// "unknown expiry" (user is responsible for rotation).
	if expiresAt > 0 && time.Now().Unix() > expiresAt {
		output.Info("Token expired.")
		output.Info("Run 'stoactl auth login' to re-authenticate.")
		return nil
	}

	// Parse token claims
	claims, err := parseJWTClaims(accessToken)
	if err != nil {
		output.Info("Authenticated (unable to parse token details)")
		return nil
	}

	fmt.Println("Authentication Status:")
	fmt.Printf("  Context:    %s\n", ctx.Name)
	fmt.Printf("  Server:     %s\n", ctx.Context.Server)
	fmt.Printf("  Tenant:     %s\n", ctx.Context.Tenant)
	fmt.Printf("  Stored in:  %s\n", storedIn)
	fmt.Println()
	fmt.Println("User:")
	if claims.Email != "" {
		fmt.Printf("  Email:      %s\n", claims.Email)
	}
	if claims.Name != "" {
		fmt.Printf("  Name:       %s\n", claims.Name)
	}
	fmt.Printf("  Subject:    %s\n", claims.Subject)
	fmt.Println()
	fmt.Println("Token:")
	if expiresAt > 0 {
		fmt.Printf("  Expires:    %s\n", time.Unix(expiresAt, 0).Format(time.RFC3339))
		fmt.Printf("  Valid for:  %s\n", time.Until(time.Unix(expiresAt, 0)).Round(time.Minute))
	} else {
		fmt.Println("  Expires:    unknown (env-provided token)")
	}

	return nil
}

func parseJWTClaims(token string) (*JWTClaims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, fmt.Errorf("invalid token format")
	}

	payload := parts[1]
	// Add padding if needed
	switch len(payload) % 4 {
	case 2:
		payload += "=="
	case 3:
		payload += "="
	}

	decoded, err := base64.URLEncoding.DecodeString(payload)
	if err != nil {
		return nil, err
	}

	var claims JWTClaims
	if err := json.Unmarshal(decoded, &claims); err != nil {
		return nil, err
	}

	return &claims, nil
}

func newLogoutCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "logout",
		Short: "Log out from STOA Platform",
		Long: `Remove stored authentication credentials.

Example:
  stoactl auth logout`,
		Args: cobra.NoArgs,
		RunE: runLogout,
	}
}

func runLogout(cmd *cobra.Command, args []string) error {
	if err := config.SaveTokenCache(&config.TokenCache{}); err != nil {
		return fmt.Errorf("failed to clear token cache: %w", err)
	}

	output.Success("Logged out successfully.")
	return nil
}
