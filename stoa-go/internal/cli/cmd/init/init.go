// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package initcmd

import (
	"fmt"
	"os"
	"path/filepath"
	"text/template"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/output"
)

var (
	initDir       string
	initPort      int
	initNoContext bool
)

// NewInitCmd creates the init command
func NewInitCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "init [name]",
		Short: "Initialize a new STOA project",
		Long: `Create a new STOA project directory with docker-compose.yml and stoa.yaml.

This sets up everything needed to run a local MCP gateway:
  stoactl init my-api
  cd my-api && docker compose up -d
  stoactl doctor

Examples:
  stoactl init my-api
  stoactl init my-api --port 9090
  stoactl init my-api --dir /tmp/projects
  stoactl init my-api --no-context`,
		Args: cobra.ExactArgs(1),
		RunE: runInit,
	}

	cmd.Flags().StringVar(&initDir, "dir", ".", "Parent directory for the project")
	cmd.Flags().IntVar(&initPort, "port", 8080, "Gateway port")
	cmd.Flags().BoolVar(&initNoContext, "no-context", false, "Skip creating a local context")

	return cmd
}

// templateData holds values for template rendering
type templateData struct {
	ProjectName string
	Port        int
}

func runInit(cmd *cobra.Command, args []string) error {
	name := args[0]
	projectDir := filepath.Join(initDir, name)

	// Check if directory already exists
	if _, err := os.Stat(projectDir); err == nil {
		return fmt.Errorf("directory %q already exists", projectDir)
	}

	// Create project directory
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	data := templateData{
		ProjectName: name,
		Port:        initPort,
	}

	// Write all project files
	files := []struct {
		name     string
		template string
	}{
		{"docker-compose.yml", dockerComposeTemplate},
		{"stoa.yaml", stoaConfigTemplate},
		{"echo-nginx.conf", echoNginxTemplate},
		{"example-api.yaml", exampleAPITemplate},
		{"README.md", readmeTemplate},
	}

	for _, f := range files {
		if err := writeTemplate(filepath.Join(projectDir, f.name), f.template, data); err != nil {
			return fmt.Errorf("failed to write %s: %w", f.name, err)
		}
	}

	// Create tools/ directory for bridge output
	if err := os.MkdirAll(filepath.Join(projectDir, "tools"), 0755); err != nil {
		return fmt.Errorf("failed to create tools directory: %w", err)
	}

	// Set local context unless --no-context
	if !initNoContext {
		cfg, err := config.Load()
		if err != nil {
			output.Info("Warning: could not load config: %v", err)
		} else {
			server := fmt.Sprintf("http://localhost:%d", initPort)
			cfg.SetContext("local", server, "default")
			if cfg.CurrentContext == "" {
				cfg.CurrentContext = "local"
			}
			if err := cfg.Save(); err != nil {
				output.Info("Warning: could not save config: %v", err)
			}
		}
	}

	output.Success("Project %q created in %s", name, projectDir)
	fmt.Println()
	fmt.Println("Next steps:")
	fmt.Printf("  cd %s\n", name)
	fmt.Println("  docker compose up -d")
	fmt.Println("  stoactl doctor")
	fmt.Println()
	fmt.Println("Then bridge your API to MCP:")
	fmt.Println("  stoactl bridge example-api.yaml --namespace default --output ./tools/")

	return nil
}

func writeTemplate(path, tmplContent string, data templateData) error {
	tmpl, err := template.New(filepath.Base(path)).Parse(tmplContent)
	if err != nil {
		return fmt.Errorf("failed to parse template: %w", err)
	}

	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer func() { _ = f.Close() }()

	return tmpl.Execute(f, data)
}
