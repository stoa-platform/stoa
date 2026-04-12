// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package get

import (
	"testing"
)

func TestNewGetCmd_HasAllSubcommands(t *testing.T) {
	cmd := NewGetCmd()

	expected := []string{
		"apis",
		"tenants",
		"subscriptions",
		"gateways",
		"consumers",
		"contracts",
		"service-accounts",
		"environments",
		"plans",
		"webhooks",
	}

	commands := make(map[string]bool)
	for _, sub := range cmd.Commands() {
		commands[sub.Use] = true
	}

	for _, name := range expected {
		// Commands may have args in Use (e.g., "apis [name]"), check prefix
		found := false
		for use := range commands {
			if len(use) >= len(name) && use[:len(name)] == name {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("get command missing %q subcommand", name)
		}
	}
}

func TestNewGetCmd_HasOutputFlag(t *testing.T) {
	cmd := NewGetCmd()
	flag := cmd.PersistentFlags().Lookup("output")
	if flag == nil {
		t.Fatal("get command missing --output persistent flag")
	}
	if flag.DefValue != "table" {
		t.Errorf("--output default = %q, want %q", flag.DefValue, "table")
	}
}

func TestGetConsumersCmd_Aliases(t *testing.T) {
	cmd := newGetConsumersCmd()
	if len(cmd.Aliases) == 0 {
		t.Error("consumers command has no aliases, want 'consumer'")
	}
	found := false
	for _, a := range cmd.Aliases {
		if a == "consumer" {
			found = true
		}
	}
	if !found {
		t.Error("consumers command missing 'consumer' alias")
	}
}

func TestGetContractsCmd_Aliases(t *testing.T) {
	cmd := newGetContractsCmd()
	aliases := make(map[string]bool)
	for _, a := range cmd.Aliases {
		aliases[a] = true
	}
	if !aliases["contract"] {
		t.Error("contracts command missing 'contract' alias")
	}
	if !aliases["uac"] {
		t.Error("contracts command missing 'uac' alias")
	}
}

func TestGetServiceAccountsCmd_Aliases(t *testing.T) {
	cmd := newGetServiceAccountsCmd()
	aliases := make(map[string]bool)
	for _, a := range cmd.Aliases {
		aliases[a] = true
	}
	if !aliases["sa"] {
		t.Error("service-accounts command missing 'sa' alias")
	}
}

func TestGetEnvironmentsCmd_Aliases(t *testing.T) {
	cmd := newGetEnvironmentsCmd()
	aliases := make(map[string]bool)
	for _, a := range cmd.Aliases {
		aliases[a] = true
	}
	if !aliases["env"] {
		t.Error("environments command missing 'env' alias")
	}
	if !aliases["envs"] {
		t.Error("environments command missing 'envs' alias")
	}
}

func TestGetPlansCmd_Aliases(t *testing.T) {
	cmd := newGetPlansCmd()
	found := false
	for _, a := range cmd.Aliases {
		if a == "plan" {
			found = true
		}
	}
	if !found {
		t.Error("plans command missing 'plan' alias")
	}
}

func TestGetWebhooksCmd_Aliases(t *testing.T) {
	cmd := newGetWebhooksCmd()
	aliases := make(map[string]bool)
	for _, a := range cmd.Aliases {
		aliases[a] = true
	}
	if !aliases["webhook"] {
		t.Error("webhooks command missing 'webhook' alias")
	}
	if !aliases["wh"] {
		t.Error("webhooks command missing 'wh' alias")
	}
}
