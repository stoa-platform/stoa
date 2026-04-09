// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package redact

import "testing"

func TestEmail(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"user@example.com", "u***@e***.com"},
		{"alice.bob@company.org", "a***@c***.org"},
		{"x@y.io", "x***@y***.io"},
		{"no-email-here", "no-email-here"},
		{"", ""},
		{"text with user@domain.com inside", "text with u***@d***.com inside"},
		{"two@emails.com and three@test.org", "t***@e***.com and t***@t***.org"},
	}

	for _, tt := range tests {
		got := Email(tt.input)
		if got != tt.want {
			t.Errorf("Email(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestIP(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"192.168.1.100", "192.168.x.x"},
		{"10.0.0.1", "10.0.x.x"},
		{"255.255.255.255", "255.255.x.x"},
		{"not-an-ip", "not-an-ip"},
		{"", ""},
	}

	for _, tt := range tests {
		got := IP(tt.input)
		if got != tt.want {
			t.Errorf("IP(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestIPv6(t *testing.T) {
	got := IP("2001:db8::1")
	// Should mask — keep first two groups
	if got == "2001:db8::1" {
		t.Error("IPv6 address should be masked")
	}
}

func TestAllIPs(t *testing.T) {
	input := "from 192.168.1.1 to 10.0.0.5"
	got := AllIPs(input)
	want := "from 192.168.x.x to 10.0.x.x"
	if got != want {
		t.Errorf("AllIPs(%q) = %q, want %q", input, got, want)
	}
}

func TestAll(t *testing.T) {
	input := "user alice@corp.com from 192.168.1.50"
	got := All(input)
	want := "user a***@c***.com from 192.168.x.x"
	if got != want {
		t.Errorf("All(%q) = %q, want %q", input, got, want)
	}
}
