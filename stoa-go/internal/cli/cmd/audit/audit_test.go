// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package audit

import (
	"testing"
	"time"
)

func TestParseSince(t *testing.T) {
	tests := []struct {
		input   string
		wantErr bool
	}{
		{"7d", false},
		{"30d", false},
		{"24h", false},
		{"60m", false},
		{"2026-01-01", false},
		{"2026-01-01T10:00:00", false},
		{"", false},
		{"invalid", true},
		{"7x", true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := parseSince(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("parseSince(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
				return
			}
			if !tt.wantErr && tt.input != "" {
				// Verify the result is a valid RFC3339 timestamp
				if _, err := time.Parse(time.RFC3339, got); err != nil {
					t.Errorf("parseSince(%q) = %q, not valid RFC3339: %v", tt.input, got, err)
				}
			}
		})
	}
}

func TestParseSinceRelativeDuration(t *testing.T) {
	got, err := parseSince("7d")
	if err != nil {
		t.Fatalf("parseSince(7d) error: %v", err)
	}

	parsed, err := time.Parse(time.RFC3339, got)
	if err != nil {
		t.Fatalf("invalid RFC3339: %v", err)
	}

	diff := time.Since(parsed)
	// Should be approximately 7 days ago (with some tolerance)
	if diff < 6*24*time.Hour || diff > 8*24*time.Hour {
		t.Errorf("parseSince(7d) = %v, expected ~7 days ago", parsed)
	}
}
