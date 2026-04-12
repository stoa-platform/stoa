// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package delete

import (
	"fmt"
	"testing"
)

func TestNewDeleteCmd_HasAllSubcommands(t *testing.T) {
	cmd := NewDeleteCmd()

	expected := []string{
		"api",
		"tenant",
		"gateway",
		"subscription",
		"consumer",
		"contract",
		"service-account",
		"plan",
		"webhook",
	}

	commands := make(map[string]bool)
	for _, sub := range cmd.Commands() {
		// Use field may include args (e.g., "api <name> [name...]"), extract first word
		use := sub.Use
		for i, ch := range use {
			if ch == ' ' {
				use = use[:i]
				break
			}
		}
		commands[use] = true
	}

	for _, name := range expected {
		if !commands[name] {
			t.Errorf("delete command missing %q subcommand", name)
		}
	}
}

func TestDeleteResources_AllSucceed(t *testing.T) {
	deleted := []string{}
	deleteFn := func(id string) error {
		deleted = append(deleted, id)
		return nil
	}

	err := deleteResources([]string{"a", "b", "c"}, "test", deleteFn)
	if err != nil {
		t.Fatalf("deleteResources() error = %v, want nil", err)
	}
	if len(deleted) != 3 {
		t.Errorf("deleteResources() deleted %d items, want 3", len(deleted))
	}
}

func TestDeleteResources_SomeFail(t *testing.T) {
	deleteFn := func(id string) error {
		if id == "bad" {
			return fmt.Errorf("not found")
		}
		return nil
	}

	err := deleteResources([]string{"good", "bad", "also-good"}, "test", deleteFn)
	if err == nil {
		t.Error("deleteResources() error = nil, want error when some fail")
	}
}

func TestDeleteResources_AllFail(t *testing.T) {
	deleteFn := func(id string) error {
		return fmt.Errorf("fail")
	}

	err := deleteResources([]string{"a", "b"}, "test", deleteFn)
	if err == nil {
		t.Error("deleteResources() error = nil, want error when all fail")
	}
}

func TestDeleteTenantCmd_RequiresArgs(t *testing.T) {
	cmd := newDeleteTenantCmd()
	err := cmd.Args(cmd, []string{})
	if err == nil {
		t.Error("delete tenant should require at least 1 argument")
	}
}

func TestDeleteConsumerCmd_RequiresArgs(t *testing.T) {
	cmd := newDeleteConsumerCmd()
	err := cmd.Args(cmd, []string{})
	if err == nil {
		t.Error("delete consumer should require at least 1 argument")
	}
}

func TestDeleteContractCmd_Aliases(t *testing.T) {
	cmd := newDeleteContractCmd()
	aliases := make(map[string]bool)
	for _, a := range cmd.Aliases {
		aliases[a] = true
	}
	if !aliases["contracts"] {
		t.Error("delete contract missing 'contracts' alias")
	}
	if !aliases["uac"] {
		t.Error("delete contract missing 'uac' alias")
	}
}

func TestDeleteGatewayCmd_Aliases(t *testing.T) {
	cmd := newDeleteGatewayCmd()
	aliases := make(map[string]bool)
	for _, a := range cmd.Aliases {
		aliases[a] = true
	}
	if !aliases["gw"] {
		t.Error("delete gateway missing 'gw' alias")
	}
}
