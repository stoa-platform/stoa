// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package initcmd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRunInit_CreatesFiles(t *testing.T) {
	dir := t.TempDir()
	initDir = dir
	initPort = 9090
	initNoContext = true

	err := runInit(nil, []string{"test-project"})
	if err != nil {
		t.Fatalf("runInit failed: %v", err)
	}

	projectDir := filepath.Join(dir, "test-project")

	// Check docker-compose.yml exists
	compose, err := os.ReadFile(filepath.Join(projectDir, "docker-compose.yml"))
	if err != nil {
		t.Fatalf("docker-compose.yml not found: %v", err)
	}
	if !strings.Contains(string(compose), "9090:8080") {
		t.Error("docker-compose.yml missing port mapping")
	}
	if !strings.Contains(string(compose), "ghcr.io/stoa-platform/gateway:latest") {
		t.Error("docker-compose.yml missing gateway image")
	}

	// Check stoa.yaml exists
	stoaYaml, err := os.ReadFile(filepath.Join(projectDir, "stoa.yaml"))
	if err != nil {
		t.Fatalf("stoa.yaml not found: %v", err)
	}
	if !strings.Contains(string(stoaYaml), "test-project") {
		t.Error("stoa.yaml missing project name")
	}
	if !strings.Contains(string(stoaYaml), "edge-mcp") {
		t.Error("stoa.yaml missing mode")
	}

	// Check echo-nginx.conf exists
	echoConf, err := os.ReadFile(filepath.Join(projectDir, "echo-nginx.conf"))
	if err != nil {
		t.Fatalf("echo-nginx.conf not found: %v", err)
	}
	if !strings.Contains(string(echoConf), "listen 8888") {
		t.Error("echo-nginx.conf missing port")
	}
	if !strings.Contains(string(echoConf), "test-project") {
		t.Error("echo-nginx.conf missing project name")
	}

	// Check example-api.yaml exists
	exampleAPI, err := os.ReadFile(filepath.Join(projectDir, "example-api.yaml"))
	if err != nil {
		t.Fatalf("example-api.yaml not found: %v", err)
	}
	if !strings.Contains(string(exampleAPI), "test-project") {
		t.Error("example-api.yaml missing project name")
	}
	if !strings.Contains(string(exampleAPI), "listItems") {
		t.Error("example-api.yaml missing operationId")
	}

	// Check README.md exists
	readme, err := os.ReadFile(filepath.Join(projectDir, "README.md"))
	if err != nil {
		t.Fatalf("README.md not found: %v", err)
	}
	if !strings.Contains(string(readme), "test-project") {
		t.Error("README.md missing project name")
	}
	if !strings.Contains(string(readme), "stoactl bridge") {
		t.Error("README.md missing bridge instructions")
	}

	// Check tools/ directory exists
	info, err := os.Stat(filepath.Join(projectDir, "tools"))
	if err != nil {
		t.Fatalf("tools/ directory not found: %v", err)
	}
	if !info.IsDir() {
		t.Error("tools/ is not a directory")
	}
}

func TestRunInit_DirectoryAlreadyExists(t *testing.T) {
	dir := t.TempDir()
	initDir = dir
	initNoContext = true

	// Create the directory first
	_ = os.MkdirAll(filepath.Join(dir, "existing"), 0755)

	err := runInit(nil, []string{"existing"})
	if err == nil {
		t.Fatal("expected error for existing directory")
	}
	if !strings.Contains(err.Error(), "already exists") {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestRunInit_DefaultPort(t *testing.T) {
	dir := t.TempDir()
	initDir = dir
	initPort = 8080
	initNoContext = true

	err := runInit(nil, []string{"default-port"})
	if err != nil {
		t.Fatalf("runInit failed: %v", err)
	}

	compose, err := os.ReadFile(filepath.Join(dir, "default-port", "docker-compose.yml"))
	if err != nil {
		t.Fatalf("docker-compose.yml not found: %v", err)
	}
	if !strings.Contains(string(compose), "8080:8080") {
		t.Error("docker-compose.yml missing default port mapping")
	}
}

func TestWriteTemplate(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.yml")

	data := templateData{ProjectName: "my-api", Port: 3000}
	err := writeTemplate(path, "name: {{.ProjectName}}\nport: {{.Port}}", data)
	if err != nil {
		t.Fatalf("writeTemplate failed: %v", err)
	}

	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}
	if !strings.Contains(string(content), "my-api") {
		t.Error("template missing project name")
	}
	if !strings.Contains(string(content), "3000") {
		t.Error("template missing port")
	}
}
