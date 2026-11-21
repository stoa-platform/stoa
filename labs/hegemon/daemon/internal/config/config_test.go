package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoad(t *testing.T) {
	yaml := `
linear:
  api_key: "test-key"
  team_id: "team-123"
  poll_interval: "30s"

workers:
  - name: w1
    host: "1.2.3.4"
    roles: [backend, mcp]
  - name: w2
    host: "5.6.7.8"
    port: 2222
    user: admin
    ssh_key: /tmp/key
    roles: [frontend]

slack:
  webhook_url: "https://hooks.slack.com/test"

health_check:
  interval: "60s"
  ssh_timeout: "5s"

state:
  db_path: "/tmp/test.db"
`
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte(yaml), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}

	if cfg.Linear.APIKey != "test-key" {
		t.Errorf("api_key = %q, want %q", cfg.Linear.APIKey, "test-key")
	}
	if cfg.Linear.PollInterval.Duration != 30*time.Second {
		t.Errorf("poll_interval = %v, want 30s", cfg.Linear.PollInterval.Duration)
	}
	if len(cfg.Workers) != 2 {
		t.Fatalf("workers = %d, want 2", len(cfg.Workers))
	}

	// Check defaults applied.
	w1 := cfg.Workers[0]
	if w1.Port != 22 {
		t.Errorf("w1.Port = %d, want 22", w1.Port)
	}
	if w1.User != "hegemon" {
		t.Errorf("w1.User = %q, want %q", w1.User, "hegemon")
	}

	// Check explicit values.
	w2 := cfg.Workers[1]
	if w2.Port != 2222 {
		t.Errorf("w2.Port = %d, want 2222", w2.Port)
	}
	if w2.User != "admin" {
		t.Errorf("w2.User = %q, want %q", w2.User, "admin")
	}

	if cfg.HealthCheck.Interval.Duration != 60*time.Second {
		t.Errorf("health_check.interval = %v, want 60s", cfg.HealthCheck.Interval.Duration)
	}
}

func TestLoadEnvExpansion(t *testing.T) {
	t.Setenv("TEST_API_KEY", "secret-from-env")

	yaml := `
linear:
  api_key: "${TEST_API_KEY}"
  team_id: "t"
`
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte(yaml), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Linear.APIKey != "secret-from-env" {
		t.Errorf("api_key = %q, want %q", cfg.Linear.APIKey, "secret-from-env")
	}
}

func TestTimeoutForEstimate(t *testing.T) {
	cfg := &Config{}
	tests := []struct {
		estimate int
		want     time.Duration
	}{
		{1, 15 * time.Minute},
		{3, 15 * time.Minute},
		{5, 30 * time.Minute},
		{8, 45 * time.Minute},
		{13, 60 * time.Minute},
		{21, 90 * time.Minute},
	}
	for _, tt := range tests {
		got := cfg.TimeoutForEstimate(tt.estimate)
		if got != tt.want {
			t.Errorf("TimeoutForEstimate(%d) = %v, want %v", tt.estimate, got, tt.want)
		}
	}
}

func TestTimeoutForEstimateWithOverrides(t *testing.T) {
	cfg := &Config{
		Timeouts: map[int]CustomDuration{
			5: {Duration: 20 * time.Minute},
		},
	}
	if got := cfg.TimeoutForEstimate(5); got != 20*time.Minute {
		t.Errorf("TimeoutForEstimate(5) = %v, want 20m", got)
	}
	// Non-overridden falls back to default.
	if got := cfg.TimeoutForEstimate(3); got != 15*time.Minute {
		t.Errorf("TimeoutForEstimate(3) = %v, want 15m", got)
	}
}

func TestDefaults(t *testing.T) {
	yaml := `
linear:
  api_key: "k"
  team_id: "t"
workers: []
`
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte(yaml), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Linear.PollInterval.Duration != 60*time.Second {
		t.Errorf("default poll_interval = %v, want 60s", cfg.Linear.PollInterval.Duration)
	}
	if cfg.State.DBPath != "./hegemon.db" {
		t.Errorf("default db_path = %q, want %q", cfg.State.DBPath, "./hegemon.db")
	}
	home, _ := os.UserHomeDir()
	wantRepoPath := home + "/stoa"
	if cfg.Repo.Path != wantRepoPath {
		t.Errorf("default repo.path = %q, want %q", cfg.Repo.Path, wantRepoPath)
	}
	if cfg.Log.MaxAgeDays != 7 {
		t.Errorf("default max_age_days = %d, want 7", cfg.Log.MaxAgeDays)
	}
	if cfg.Notification.HealthCooldown.Duration != time.Hour {
		t.Errorf("default health_cooldown = %v, want 1h", cfg.Notification.HealthCooldown.Duration)
	}
	if cfg.Notification.DigestInterval.Duration != 30*time.Minute {
		t.Errorf("default digest_interval = %v, want 30m", cfg.Notification.DigestInterval.Duration)
	}
	if cfg.Notification.MaxRetries != 3 {
		t.Errorf("default max_retries = %d, want 3", cfg.Notification.MaxRetries)
	}
}

func TestNotificationConfigOverrides(t *testing.T) {
	yaml := `
linear:
  api_key: "k"
  team_id: "t"
workers: []
notification:
  health_cooldown: "2h"
  digest_interval: "15m"
  max_retries: 5
`
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte(yaml), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Notification.HealthCooldown.Duration != 2*time.Hour {
		t.Errorf("health_cooldown = %v, want 2h", cfg.Notification.HealthCooldown.Duration)
	}
	if cfg.Notification.DigestInterval.Duration != 15*time.Minute {
		t.Errorf("digest_interval = %v, want 15m", cfg.Notification.DigestInterval.Duration)
	}
	if cfg.Notification.MaxRetries != 5 {
		t.Errorf("max_retries = %d, want 5", cfg.Notification.MaxRetries)
	}
}
