// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package mcp

import (
	"bytes"
	"testing"
)

// --- AC1: list-servers subcommand exists ---

func TestNewMCPCmd_HasListServersSubcommand(t *testing.T) {
	cmd := NewMCPCmd()
	found := false
	for _, sub := range cmd.Commands() {
		if sub.Use == "list-servers" {
			found = true
			break
		}
	}
	if !found {
		t.Error("mcp command missing 'list-servers' subcommand")
	}
}

// --- AC5: list-tools subcommand exists ---

func TestNewMCPCmd_HasListToolsSubcommand(t *testing.T) {
	cmd := NewMCPCmd()
	found := false
	for _, sub := range cmd.Commands() {
		if sub.Use == "list-tools" {
			found = true
			break
		}
	}
	if !found {
		t.Error("mcp command missing 'list-tools' subcommand")
	}
}

// --- AC8: call subcommand exists ---

func TestNewMCPCmd_HasCallSubcommand(t *testing.T) {
	cmd := NewMCPCmd()
	found := false
	for _, sub := range cmd.Commands() {
		if sub.Name() == "call" {
			found = true
			break
		}
	}
	if !found {
		t.Error("mcp command missing 'call' subcommand")
	}
}

// --- AC11: health subcommand exists ---

func TestNewMCPCmd_HasHealthSubcommand(t *testing.T) {
	cmd := NewMCPCmd()
	found := false
	for _, sub := range cmd.Commands() {
		if sub.Use == "health" {
			found = true
			break
		}
	}
	if !found {
		t.Error("mcp command missing 'health' subcommand")
	}
}

// --- AC9: call without tool name prints usage error ---

func TestCallCmd_RequiresToolName(t *testing.T) {
	cmd := NewMCPCmd()
	buf := new(bytes.Buffer)
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"call"})

	err := cmd.Execute()
	if err == nil {
		t.Error("Expected error when calling 'mcp call' without tool name")
	}
}

// --- AC13: --gateway flag exists on mcp command ---

func TestMCPCmd_HasGatewayFlag(t *testing.T) {
	cmd := NewMCPCmd()
	flag := cmd.PersistentFlags().Lookup("gateway")
	if flag == nil {
		t.Error("mcp command missing --gateway persistent flag")
	}
}

// --- AC13: --output flag exists on mcp command ---

func TestMCPCmd_HasOutputFlag(t *testing.T) {
	cmd := NewMCPCmd()
	flag := cmd.PersistentFlags().Lookup("output")
	if flag == nil {
		t.Error("mcp command missing --output persistent flag")
	}
}
