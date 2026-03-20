// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/keyring"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

const (
	authServerBase = "https://auth.gostoa.dev"
	realm          = "stoa"
	clientID       = "stoactl"
)

// DeviceAuthResponse represents the device authorization response
type DeviceAuthResponse struct {
	DeviceCode              string `json:"device_code"`
	UserCode                string `json:"user_code"`
	VerificationURI         string `json:"verification_uri"`
	VerificationURIComplete string `json:"verification_uri_complete"`
	ExpiresIn               int    `json:"expires_in"`
	Interval                int    `json:"interval"`
}

// TokenResponse represents the token response
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
	TokenType    string `json:"token_type"`
	Error        string `json:"error,omitempty"`
}

func newLoginCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "login",
		Short: "Authenticate with STOA Platform",
		Long: `Authenticate with STOA Platform using OAuth2 device flow.

This command initiates the device authorization flow:
1. You'll receive a code and URL
2. Open the URL in your browser
3. Enter the code to authorize
4. The CLI will automatically receive your credentials

Example:
  stoactl auth login`,
		Args: cobra.NoArgs,
		RunE: runLogin,
	}
}

func runLogin(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	ctx, err := cfg.GetCurrentContext()
	if err != nil {
		return err
	}

	output.Info("Authenticating to context %q...", ctx.Name)

	// Step 1: Request device authorization
	deviceAuth, err := requestDeviceAuthorization()
	if err != nil {
		return fmt.Errorf("failed to initiate device authorization: %w", err)
	}

	// Step 2: Display instructions to user
	fmt.Println()
	fmt.Println("To authenticate, visit:")
	fmt.Printf("  %s\n", deviceAuth.VerificationURIComplete)
	fmt.Println()
	fmt.Printf("Or open %s and enter code: %s\n", deviceAuth.VerificationURI, deviceAuth.UserCode)
	fmt.Println()
	fmt.Println("Waiting for authorization...")

	// Step 3: Poll for token
	pollInterval := time.Duration(deviceAuth.Interval) * time.Second
	if pollInterval < 5*time.Second {
		pollInterval = 5 * time.Second
	}

	deadline := time.Now().Add(time.Duration(deviceAuth.ExpiresIn) * time.Second)
	token, err := pollForToken(context.Background(), deviceAuth.DeviceCode, pollInterval, deadline)
	if err != nil {
		return fmt.Errorf("authentication failed: %w", err)
	}

	// Step 4: Save token to keychain (primary) + file (fallback)
	expiresAt := time.Now().Add(time.Duration(token.ExpiresIn) * time.Second).Unix()

	store := keyring.NewOSKeyring()
	tokenData := &keyring.TokenData{
		AccessToken:  token.AccessToken,
		RefreshToken: token.RefreshToken,
		ExpiresAt:    expiresAt,
		Context:      ctx.Name,
	}

	if err := store.Set(ctx.Name, tokenData); err != nil {
		output.Info("Warning: could not store in keychain: %v", err)
		output.Info("Falling back to file-based storage.")
	} else {
		_ = config.AppendAuditLog("keyring.Set", ctx.Name, "success")
	}

	// Also save to file for backward compatibility
	tokenCache := &config.TokenCache{
		AccessToken:  token.AccessToken,
		RefreshToken: token.RefreshToken,
		ExpiresAt:    expiresAt,
		Context:      ctx.Name,
	}
	if err := config.SaveTokenCache(tokenCache); err != nil {
		return fmt.Errorf("failed to save token: %w", err)
	}

	output.Success("Successfully authenticated to %s (stored in: %s)", ctx.Name, store.Name())
	return nil
}

func requestDeviceAuthorization() (*DeviceAuthResponse, error) {
	deviceAuthURL := fmt.Sprintf("%s/realms/%s/protocol/openid-connect/auth/device", authServerBase, realm)

	data := url.Values{}
	data.Set("client_id", clientID)
	data.Set("scope", "openid profile email")

	resp, err := http.Post(deviceAuthURL, "application/x-www-form-urlencoded", strings.NewReader(data.Encode()))
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("device authorization failed (%d): %s", resp.StatusCode, string(body))
	}

	var result DeviceAuthResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return &result, nil
}

func pollForToken(ctx context.Context, deviceCode string, interval time.Duration, deadline time.Time) (*TokenResponse, error) {
	tokenURL := fmt.Sprintf("%s/realms/%s/protocol/openid-connect/token", authServerBase, realm)

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-ticker.C:
			if time.Now().After(deadline) {
				return nil, fmt.Errorf("authorization timed out")
			}

			token, err := requestToken(tokenURL, deviceCode)
			if err != nil {
				// Continue polling on authorization_pending
				if strings.Contains(err.Error(), "authorization_pending") {
					continue
				}
				// Slow down if requested
				if strings.Contains(err.Error(), "slow_down") {
					ticker.Reset(interval + 5*time.Second)
					continue
				}
				return nil, err
			}

			return token, nil
		}
	}
}

func requestToken(tokenURL, deviceCode string) (*TokenResponse, error) {
	data := url.Values{}
	data.Set("grant_type", "urn:ietf:params:oauth:grant-type:device_code")
	data.Set("client_id", clientID)
	data.Set("device_code", deviceCode)

	resp, err := http.Post(tokenURL, "application/x-www-form-urlencoded", strings.NewReader(data.Encode()))
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	var result TokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	if result.Error != "" {
		return nil, fmt.Errorf("%s", result.Error)
	}

	return &result, nil
}
