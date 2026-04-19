// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package cmdflags

import (
	"bytes"
	"os"
	"strings"
	"testing"
)

func reset() {
	TenantOverride = ""
	NamespaceOverride = ""
	WarnStderr = os.Stderr
}

// regression for CAB-2117
// WarnDeprecatedNamespace must format the exact contract string.
func TestWarnDeprecatedNamespace_Format(t *testing.T) {
	defer reset()
	var buf bytes.Buffer
	WarnStderr = &buf

	WarnDeprecatedNamespace("get")
	want := "--namespace is deprecated for tenant scope on 'stoactl get', use --tenant\n"
	if buf.String() != want {
		t.Errorf("got %q, want %q", buf.String(), want)
	}
}

// regression for CAB-2117
// Empty cmdName falls back to a generic placeholder rather than leaving an
// awkward double-space in the message.
func TestWarnDeprecatedNamespace_EmptyCmd(t *testing.T) {
	defer reset()
	var buf bytes.Buffer
	WarnStderr = &buf

	WarnDeprecatedNamespace("")
	if !strings.Contains(buf.String(), "stoactl <cmd>") {
		t.Errorf("empty cmd should render <cmd>; got %q", buf.String())
	}
}

// regression for CAB-2117
// ResolveTenant must never emit a warning when TenantOverride is set, even
// if NamespaceOverride is also set (the two are compatible: --tenant wins).
func TestResolveTenant_TenantSilentWhenBothSet(t *testing.T) {
	defer reset()
	var buf bytes.Buffer
	WarnStderr = &buf

	TenantOverride = "tenant-A"
	NamespaceOverride = "ns-B"

	if got := ResolveTenant("apply", true); got != "tenant-A" {
		t.Errorf("ResolveTenant = %q, want %q", got, "tenant-A")
	}
	if buf.Len() != 0 {
		t.Errorf("no warning expected; got %q", buf.String())
	}
}

// regression for CAB-2117
// When namespaceIsDeprecated is false (bridge context), NamespaceOverride is
// never consumed as a tenant alias and no warning fires.
func TestResolveTenant_NamespaceNotDeprecatedIsSilent(t *testing.T) {
	defer reset()
	var buf bytes.Buffer
	WarnStderr = &buf

	NamespaceOverride = "stoa-demo"
	if got := ResolveTenant("bridge", false); got != "" {
		t.Errorf("bridge context must not coerce --namespace to tenant; got %q", got)
	}
	if buf.Len() != 0 {
		t.Errorf("no warning in bridge context; got %q", buf.String())
	}
}
