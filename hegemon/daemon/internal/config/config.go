package config

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

// Config is the root configuration for the HEGEMON daemon.
type Config struct {
	Linear        LinearConfig            `yaml:"linear"`
	Workers       []WorkerConfig          `yaml:"workers"`
	Slack         SlackConfig             `yaml:"slack"`
	Notification  NotificationConfig      `yaml:"notification"`
	Timeouts      map[int]CustomDuration  `yaml:"timeouts"`
	HealthCheck   HealthCheckConfig       `yaml:"health_check"`
	State         StateConfig             `yaml:"state"`
	Log           LogConfig               `yaml:"log"`
	Repo          RepoConfig              `yaml:"repo"`
}

type LinearConfig struct {
	APIKey       string         `yaml:"api_key"`
	TeamID       string         `yaml:"team_id"`
	PollInterval CustomDuration `yaml:"poll_interval"`
}

type WorkerConfig struct {
	Name               string   `yaml:"name"`
	Host               string   `yaml:"host"`
	Port               int      `yaml:"port"`
	User               string   `yaml:"user"`
	SSHKey             string   `yaml:"ssh_key"`
	Roles              []string `yaml:"roles"`
	InfisicalSecretPath string  `yaml:"infisical_secret_path"` // Per-worker Infisical path (e.g. /hegemon/worker-1)
}

type SlackConfig struct {
	WebhookURL string `yaml:"webhook_url"`
}

type NotificationConfig struct {
	HealthCooldown CustomDuration `yaml:"health_cooldown"`
	DigestInterval CustomDuration `yaml:"digest_interval"`
	MaxRetries     int            `yaml:"max_retries"`
}

type HealthCheckConfig struct {
	Interval   CustomDuration `yaml:"interval"`
	SSHTimeout CustomDuration `yaml:"ssh_timeout"`
}

type StateConfig struct {
	DBPath string `yaml:"db_path"`
}

type LogConfig struct {
	Level      string `yaml:"level"`
	MaxAgeDays int    `yaml:"max_age_days"`
}

type RepoConfig struct {
	Path   string `yaml:"path"`
	Branch string `yaml:"branch"`
}

// CustomDuration wraps time.Duration for YAML unmarshaling.
type CustomDuration struct {
	time.Duration
}

func (d *CustomDuration) UnmarshalYAML(value *yaml.Node) error {
	var s string
	if err := value.Decode(&s); err != nil {
		return err
	}
	dur, err := time.ParseDuration(s)
	if err != nil {
		return fmt.Errorf("invalid duration %q: %w", s, err)
	}
	d.Duration = dur
	return nil
}

func (d CustomDuration) MarshalYAML() (interface{}, error) {
	return d.Duration.String(), nil
}

// Load reads and parses the YAML config, expanding env vars.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	expanded := os.ExpandEnv(string(data))

	cfg := &Config{}
	if err := yaml.Unmarshal([]byte(expanded), cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	setDefaults(cfg)
	expandTildes(cfg)
	return cfg, nil
}

func setDefaults(cfg *Config) {
	if cfg.Linear.PollInterval.Duration == 0 {
		cfg.Linear.PollInterval.Duration = 60 * time.Second
	}
	if cfg.HealthCheck.Interval.Duration == 0 {
		cfg.HealthCheck.Interval.Duration = 120 * time.Second
	}
	if cfg.HealthCheck.SSHTimeout.Duration == 0 {
		cfg.HealthCheck.SSHTimeout.Duration = 10 * time.Second
	}
	if cfg.State.DBPath == "" {
		cfg.State.DBPath = "./hegemon.db"
	}
	if cfg.Log.MaxAgeDays == 0 {
		cfg.Log.MaxAgeDays = 7
	}
	if cfg.Notification.HealthCooldown.Duration == 0 {
		cfg.Notification.HealthCooldown.Duration = time.Hour
	}
	if cfg.Notification.DigestInterval.Duration == 0 {
		cfg.Notification.DigestInterval.Duration = 30 * time.Minute
	}
	if cfg.Notification.MaxRetries == 0 {
		cfg.Notification.MaxRetries = 3
	}
	if cfg.Repo.Path == "" {
		cfg.Repo.Path = "~/stoa"
	}
	if cfg.Repo.Branch == "" {
		cfg.Repo.Branch = "main"
	}
	for i := range cfg.Workers {
		if cfg.Workers[i].Port == 0 {
			cfg.Workers[i].Port = 22
		}
		if cfg.Workers[i].User == "" {
			cfg.Workers[i].User = "hegemon"
		}
	}
}

func expandTildes(cfg *Config) {
	home, _ := os.UserHomeDir()
	if home == "" {
		return
	}
	expand := func(s string) string {
		if len(s) >= 2 && s[:2] == "~/" {
			return home + s[1:]
		}
		return s
	}
	for i := range cfg.Workers {
		cfg.Workers[i].SSHKey = expand(cfg.Workers[i].SSHKey)
	}
	cfg.Repo.Path = expand(cfg.Repo.Path)
	cfg.State.DBPath = expand(cfg.State.DBPath)
}

// TimeoutForEstimate returns the max execution time for a ticket based on its
// story point estimate. Council adjustment: progressive timeouts.
func (c *Config) TimeoutForEstimate(estimate int) time.Duration {
	if c.Timeouts != nil {
		if d, ok := c.Timeouts[estimate]; ok {
			return d.Duration
		}
	}
	switch {
	case estimate <= 3:
		return 15 * time.Minute
	case estimate <= 5:
		return 30 * time.Minute
	case estimate <= 8:
		return 45 * time.Minute
	case estimate <= 13:
		return 60 * time.Minute
	default:
		return 90 * time.Minute
	}
}
