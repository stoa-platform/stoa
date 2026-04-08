// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package completion

import (
	"bytes"
	"strings"
	"testing"
)

// --- AC14: bash completion generates valid script ---

func TestCompletionBash(t *testing.T) {
	cmd := NewCompletionCmd()
	buf := new(bytes.Buffer)
	cmd.SetOut(buf)
	cmd.SetArgs([]string{"bash"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("completion bash error = %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "bash completion") && !strings.Contains(output, "__start_stoactl") && !strings.Contains(output, "complete") {
		t.Error("completion bash output does not look like a valid bash completion script")
	}
}

// --- AC15: zsh completion generates valid script ---

func TestCompletionZsh(t *testing.T) {
	cmd := NewCompletionCmd()
	buf := new(bytes.Buffer)
	cmd.SetOut(buf)
	cmd.SetArgs([]string{"zsh"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("completion zsh error = %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "zsh completion") && !strings.Contains(output, "compdef") && !strings.Contains(output, "#compdef") {
		t.Error("completion zsh output does not look like a valid zsh completion script")
	}
}

// --- AC16: fish completion generates valid script ---

func TestCompletionFish(t *testing.T) {
	cmd := NewCompletionCmd()
	buf := new(bytes.Buffer)
	cmd.SetOut(buf)
	cmd.SetArgs([]string{"fish"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("completion fish error = %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "fish completion") && !strings.Contains(output, "complete -c") {
		t.Error("completion fish output does not look like a valid fish completion script")
	}
}

// --- AC17: completion without shell prints usage ---

func TestCompletionNoArgs(t *testing.T) {
	cmd := NewCompletionCmd()
	buf := new(bytes.Buffer)
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{})

	err := cmd.Execute()
	if err == nil {
		t.Error("Expected error when calling 'completion' without shell argument")
	}
}
