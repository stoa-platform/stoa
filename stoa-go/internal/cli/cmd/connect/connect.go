// Package connect provides the `stoactl connect` command group for managing
// stoa-connect agents and gateway interactions.
package connect

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/connect"
	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// NewConnectCmd creates the `stoactl connect` command group.
func NewConnectCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "connect",
		Short: "Manage stoa-connect gateway agents",
		Long: `Interact with stoa-connect agents running alongside third-party gateways.

Commands allow you to check agent status, trigger API discovery,
and initiate policy sync.`,
	}

	cmd.AddCommand(newStatusCmd())
	cmd.AddCommand(newDiscoverCmd())
	cmd.AddCommand(newSyncCmd())

	return cmd
}

// --- stoactl connect status ---

func newStatusCmd() *cobra.Command {
	var url string
	cmd := &cobra.Command{
		Use:   "status",
		Short: "Show stoa-connect agent status",
		Long:  "Query the /health endpoint of a stoa-connect agent to check its status.",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runStatus(url)
		},
	}
	cmd.Flags().StringVar(&url, "url", "", "stoa-connect agent URL (e.g., http://kong-vps:8090)")
	_ = cmd.MarkFlagRequired("url")
	return cmd
}

func runStatus(agentURL string) error {
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(agentURL + "/health")
	if err != nil {
		return fmt.Errorf("cannot reach agent at %s: %w", agentURL, err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)

	var health map[string]interface{}
	if err := json.Unmarshal(body, &health); err != nil {
		return fmt.Errorf("invalid response: %s", string(body))
	}

	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader([]string{"Field", "Value"})
	table.SetBorder(false)
	table.SetColumnSeparator("")

	for _, key := range []string{"status", "version", "commit", "gateway_id", "discovered_apis"} {
		if v, ok := health[key]; ok {
			table.Append([]string{key, fmt.Sprintf("%v", v)})
		}
	}

	table.Render()
	return nil
}

// --- stoactl connect discover ---

func newDiscoverCmd() *cobra.Command {
	var (
		adminURL    string
		gatewayType string
		token       string
		username    string
		password    string
	)

	cmd := &cobra.Command{
		Use:   "discover",
		Short: "Discover APIs on a gateway",
		Long:  "Connect to a gateway's admin API and list all discovered APIs/services.",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runDiscover(adminURL, gatewayType, token, username, password)
		},
	}
	cmd.Flags().StringVar(&adminURL, "admin-url", "", "Gateway admin API URL (e.g., http://localhost:8001)")
	cmd.Flags().StringVar(&gatewayType, "type", "auto", "Gateway type: kong, gravitee, webmethods, auto")
	cmd.Flags().StringVar(&token, "token", "", "Admin API token (Kong)")
	cmd.Flags().StringVar(&username, "username", "", "Admin API username (Gravitee, webMethods)")
	cmd.Flags().StringVar(&password, "password", "", "Admin API password")
	_ = cmd.MarkFlagRequired("admin-url")
	return cmd
}

func runDiscover(adminURL, gatewayType, token, username, password string) error {
	cfg := connect.DiscoveryConfig{
		GatewayAdminURL: adminURL,
		GatewayType:     gatewayType,
		AdapterConfig: adapters.AdapterConfig{
			Token:    token,
			Username: username,
			Password: password,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	adapter, gwType, err := connect.ResolveAdapter(ctx, cfg)
	if err != nil {
		return fmt.Errorf("resolve adapter: %w", err)
	}

	fmt.Printf("Gateway type: %s\n", gwType)
	fmt.Printf("Admin URL: %s\n\n", adminURL)

	apis, err := adapter.Discover(ctx, adminURL)
	if err != nil {
		return fmt.Errorf("discovery failed: %w", err)
	}

	if len(apis) == 0 {
		fmt.Println("No APIs discovered.")
		return nil
	}

	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader([]string{"Name", "Version", "Backend", "Paths", "Active", "Policies"})
	table.SetBorder(false)

	for _, api := range apis {
		paths := "-"
		if len(api.Paths) > 0 {
			paths = fmt.Sprintf("%v", api.Paths)
		}
		policies := "-"
		if len(api.Policies) > 0 {
			policies = fmt.Sprintf("%v", api.Policies)
		}
		active := "✗"
		if api.IsActive {
			active = "✓"
		}
		table.Append([]string{
			api.Name,
			api.Version,
			api.BackendURL,
			paths,
			active,
			policies,
		})
	}

	table.Render()
	fmt.Printf("\nTotal: %d APIs discovered\n", len(apis))
	return nil
}

// --- stoactl connect sync ---

func newSyncCmd() *cobra.Command {
	var url string
	cmd := &cobra.Command{
		Use:   "sync",
		Short: "Trigger policy sync on a stoa-connect agent",
		Long:  "Query the /sync endpoint of a stoa-connect agent to trigger a policy sync cycle.",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runSync(url)
		},
	}
	cmd.Flags().StringVar(&url, "url", "", "stoa-connect agent URL (e.g., http://kong-vps:8090)")
	_ = cmd.MarkFlagRequired("url")
	return cmd
}

func runSync(agentURL string) error {
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Post(agentURL+"/sync", "application/json", nil)
	if err != nil {
		return fmt.Errorf("cannot reach agent at %s: %w", agentURL, err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("sync failed (%d): %s", resp.StatusCode, string(body))
	}

	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		fmt.Printf("Sync triggered: %s\n", string(body))
		return nil
	}

	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader([]string{"Field", "Value"})
	table.SetBorder(false)
	table.SetColumnSeparator("")

	for _, key := range []string{"status", "policies_applied", "policies_removed", "policies_failed"} {
		if v, ok := result[key]; ok {
			table.Append([]string{key, fmt.Sprintf("%v", v)})
		}
	}

	table.Render()
	return nil
}
