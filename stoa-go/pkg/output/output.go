// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package output

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/olekukonko/tablewriter"
	"gopkg.in/yaml.v3"
)

// Format represents an output format
type Format string

const (
	FormatTable Format = "table"
	FormatWide  Format = "wide"
	FormatYAML  Format = "yaml"
	FormatJSON  Format = "json"
)

// ParseFormat parses a format string
func ParseFormat(s string) Format {
	switch s {
	case "yaml":
		return FormatYAML
	case "json":
		return FormatJSON
	case "wide":
		return FormatWide
	default:
		return FormatTable
	}
}

// Printer handles output formatting
type Printer struct {
	Format Format
}

// NewPrinter creates a new printer
func NewPrinter(format Format) *Printer {
	return &Printer{Format: format}
}

// PrintTable prints data as a table
func (p *Printer) PrintTable(headers []string, rows [][]string) {
	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader(headers)
	table.SetBorder(false)
	table.SetHeaderLine(false)
	table.SetColumnSeparator("   ")
	table.SetNoWhiteSpace(true)
	table.SetTablePadding("   ")
	table.AppendBulk(rows)
	table.Render()
}

// PrintYAML prints data as YAML
func (p *Printer) PrintYAML(data any) error {
	out, err := yaml.Marshal(data)
	if err != nil {
		return err
	}
	fmt.Print(string(out))
	return nil
}

// PrintJSON prints data as JSON
func (p *Printer) PrintJSON(data any) error {
	out, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(out))
	return nil
}

// Print prints data in the configured format
func (p *Printer) Print(data any, tableHeaders []string, toRow func(any) []string, toWideRow func(any) []string) error {
	switch p.Format {
	case FormatYAML:
		return p.PrintYAML(data)
	case FormatJSON:
		return p.PrintJSON(data)
	case FormatWide:
		if items, ok := data.([]any); ok {
			var rows [][]string
			for _, item := range items {
				rows = append(rows, toWideRow(item))
			}
			p.PrintTable(tableHeaders, rows)
		}
		return nil
	default: // table
		if items, ok := data.([]any); ok {
			var rows [][]string
			for _, item := range items {
				rows = append(rows, toRow(item))
			}
			p.PrintTable(tableHeaders, rows)
		}
		return nil
	}
}

// Success prints a success message
func Success(format string, args ...any) {
	fmt.Printf(format+"\n", args...)
}

// Error prints an error message
func Error(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "Error: "+format+"\n", args...)
}

// Info prints an info message
func Info(format string, args ...any) {
	fmt.Printf(format+"\n", args...)
}

// Warn prints a warning message to stderr
func Warn(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "Warning: "+format+"\n", args...)
}
