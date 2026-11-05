package reconcile

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/spf13/cobra"
	"github.com/stoa-platform/stoa-go/internal/cli/adapter/stoagateway"
	"gopkg.in/yaml.v3"
)

// NewReconcileCmd reconciles a local governance snapshot. It never writes to Git.
func NewReconcileCmd() *cobra.Command {
	return newReconcileCmd(runFile)
}

func newReconcileCmd(run func(*cobra.Command, string, string) (Status, error)) *cobra.Command {
	var file, state string
	var once bool
	var interval time.Duration
	cmd := &cobra.Command{Use: "reconcile", Short: "Reconcile owned UAC contracts from a local governance snapshot", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if interval <= 0 {
				return errors.New("interval must be positive")
			}
			for {
				status, err := run(cmd, file, state)
				if err != nil {
					return err
				}
				if _, err = fmt.Fprintln(cmd.OutOrStdout(), status.Result); err != nil {
					return err
				}
				if once {
					return onceError(status, nil)
				}
				timer := time.NewTimer(interval)
				select {
				case <-cmd.Context().Done():
					timer.Stop()
					return cmd.Context().Err()
				case <-timer.C:
				}
			}
		}}
	cmd.Flags().StringVarP(&file, "file", "f", "", "local YAML or JSON snapshot containing targets and contracts")
	cmd.Flags().StringVar(&state, "state", ".stoactl-reconcile.json", "local status file")
	cmd.Flags().BoolVar(&once, "once", false, "run one reconciliation pass")
	cmd.Flags().DurationVar(&interval, "interval", 5*time.Second, "reconciliation interval")
	_ = cmd.MarkFlagRequired("file")
	return cmd
}
func digest(v any) string {
	b, _ := json.Marshal(v)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func runFile(cmd *cobra.Command, file, state string) (Status, error) {
	b, err := os.ReadFile(file)
	if err != nil {
		return Status{}, err
	}
	var raw any
	if err = yaml.Unmarshal(b, &raw); err != nil {
		return Status{}, errors.New("invalid governance snapshot")
	}
	b, err = json.Marshal(raw)
	if err != nil {
		return Status{}, errors.New("invalid governance snapshot keys")
	}
	var manifest struct {
		Targets []Target `json:"targets"`
	}
	if err = json.Unmarshal(b, &manifest); err != nil {
		return Status{}, errors.New("invalid governance snapshot structure")
	}
	if len(manifest.Targets) == 0 {
		return Status{}, errors.New("snapshot requires targets")
	}
	var previous Status
	b, err = os.ReadFile(state)
	if err == nil {
		if err = json.Unmarshal(b, &previous); err != nil {
			return Status{}, errors.New("invalid reconcile state")
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return Status{}, err
	}
	clients := map[string]Gateway{}
	content := map[string][]stoagateway.Contract{}
	configs := make([]Target, 0, len(manifest.Targets))
	for _, target := range manifest.Targets {
		if target.Name == "" || target.AdminURL == "" || target.GatewayURL == "" || target.TokenEnv == "" {
			return Status{}, errors.New("target requires name, adminURL, gatewayURL and tokenEnv")
		}
		if clients[target.Name] != nil {
			return Status{}, errors.New("duplicate target name")
		}
		token := os.Getenv(target.TokenEnv)
		if token == "" {
			return Status{}, errors.New("target admin token environment variable is empty")
		}
		a := stoagateway.New(target.AdminURL, target.GatewayURL, token, nil)
		a.AllowUnauthenticatedREST = target.Options.AllowUnauthenticatedREST
		a.Audience = target.InboundAuth.Audience
		a.Realms = stoagateway.RealmNames(target.InboundAuth.Realm, target.InboundAuth.Issuer, target.InboundAuth.JWKSURI, target.InboundAuth.DiscoveryURL)
		clients[target.Name] = a
		content[target.Name] = target.Contracts
		target.Contracts = nil
		configs = append(configs, target)
	}
	status := Run(cmd.Context(), manifest.Targets, clients, previous, digest(content), digest(configs))
	if digest(status) != digest(previous) {
		if err = saveStatus(state, status); err != nil {
			return status, err
		}
	}
	return status, nil
}
func saveStatus(path string, status Status) error {
	b, err := json.MarshalIndent(status, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".reconcile-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer func() { _ = os.Remove(tmp) }()
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(append(b, '\n'))
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(tmp, path)
}

// onceError exposes failed and unresolved passes to automation. Explicitly
// accepted degraded operation remains a successful invocation.
func onceError(status Status, err error) error {
	if err != nil {
		return err
	}
	if status.Result == "failed" || status.Result == "drift-unresolved" {
		return fmt.Errorf("reconcile: %s", status.Result)
	}
	return nil
}
