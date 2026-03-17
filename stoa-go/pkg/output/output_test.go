// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package output

import (
	"testing"
)

// TestParseFormat tests the format parsing function
func TestParseFormat(t *testing.T) {
	tests := []struct {
		input    string
		expected Format
	}{
		{"table", FormatTable},
		{"yaml", FormatYAML},
		{"json", FormatJSON},
		{"wide", FormatWide},
		{"", FormatTable},        // default
		{"invalid", FormatTable}, // default for unknown
		{"TABLE", FormatTable},   // case sensitive - should default
		{"YAML", FormatTable},    // case sensitive - should default
		{"JSON", FormatTable},    // case sensitive - should default
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := ParseFormat(tt.input)
			if result != tt.expected {
				t.Errorf("ParseFormat(%q) = %v, want %v", tt.input, result, tt.expected)
			}
		})
	}
}

// TestNewPrinter tests printer creation
func TestNewPrinter(t *testing.T) {
	tests := []struct {
		format Format
	}{
		{FormatTable},
		{FormatYAML},
		{FormatJSON},
		{FormatWide},
	}

	for _, tt := range tests {
		t.Run(string(tt.format), func(t *testing.T) {
			printer := NewPrinter(tt.format)

			if printer == nil {
				t.Fatal("NewPrinter() returned nil")
			}

			if printer.Format != tt.format {
				t.Errorf("NewPrinter() Format = %v, want %v", printer.Format, tt.format)
			}
		})
	}
}

// TestFormatConstants tests that format constants are correct
func TestFormatConstants(t *testing.T) {
	if FormatTable != "table" {
		t.Errorf("FormatTable = %q, want %q", FormatTable, "table")
	}
	if FormatWide != "wide" {
		t.Errorf("FormatWide = %q, want %q", FormatWide, "wide")
	}
	if FormatYAML != "yaml" {
		t.Errorf("FormatYAML = %q, want %q", FormatYAML, "yaml")
	}
	if FormatJSON != "json" {
		t.Errorf("FormatJSON = %q, want %q", FormatJSON, "json")
	}
}

// TestPrinterPrintYAMLNoError tests YAML marshaling doesn't error for valid data
func TestPrinterPrintYAMLNoError(t *testing.T) {
	printer := NewPrinter(FormatYAML)

	testData := map[string]string{
		"name":    "test",
		"version": "v1",
	}

	// Note: This writes to stdout, but we verify no error
	err := printer.PrintYAML(testData)
	if err != nil {
		t.Errorf("PrintYAML() error = %v, want nil", err)
	}
}

// TestPrinterPrintJSONNoError tests JSON marshaling doesn't error for valid data
func TestPrinterPrintJSONNoError(t *testing.T) {
	printer := NewPrinter(FormatJSON)

	testData := map[string]interface{}{
		"name":    "test",
		"count":   42,
		"enabled": true,
	}

	err := printer.PrintJSON(testData)
	if err != nil {
		t.Errorf("PrintJSON() error = %v, want nil", err)
	}
}

// TestPrinterPrintYAMLError tests YAML marshal error for invalid data
// Note: yaml.v3 panics on unmarshalable types, so we test with recover
func TestPrinterPrintYAMLError(t *testing.T) {
	printer := NewPrinter(FormatYAML)

	defer func() {
		if r := recover(); r == nil {
			t.Error("PrintYAML() did not panic for unmarshalable data")
		}
	}()

	// Functions cannot be marshaled to YAML - this will panic
	invalidData := func() {}
	_ = printer.PrintYAML(invalidData)
}

// TestPrinterPrintJSONError tests JSON marshal error for invalid data
func TestPrinterPrintJSONError(t *testing.T) {
	printer := NewPrinter(FormatJSON)

	// Channels cannot be marshaled to JSON
	invalidData := make(chan int)

	err := printer.PrintJSON(invalidData)
	if err == nil {
		t.Error("PrintJSON() error = nil, want error for unmarshalable data")
	}
}

// TestFormatTypeConversion tests Format type string conversion
func TestFormatTypeConversion(t *testing.T) {
	var f Format = "custom"

	// Verify Format behaves as string
	if string(f) != "custom" {
		t.Errorf("Format string conversion = %q, want %q", string(f), "custom")
	}
}
