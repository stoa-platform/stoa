package scheduler

import (
	"testing"
)

func TestExtractInstanceLabel(t *testing.T) {
	tests := []struct {
		labels []string
		want   string
	}{
		{[]string{"instance:backend", "flow-ready"}, "instance:backend"},
		{[]string{"mega-ticket", "instance:mcp"}, "instance:mcp"},
		{[]string{"flow-ready", "hlfh:validated"}, ""},
		{nil, ""},
		{[]string{}, ""},
	}
	for _, tt := range tests {
		got := ExtractInstanceLabel(tt.labels)
		if got != tt.want {
			t.Errorf("ExtractInstanceLabel(%v) = %q, want %q", tt.labels, got, tt.want)
		}
	}
}

func TestInstanceLabelToRole(t *testing.T) {
	tests := []struct {
		label string
		want  string
	}{
		{"instance:backend", "backend"},
		{"instance:frontend", "frontend"},
		{"instance:mcp", "mcp"},
		{"instance:auth", "auth"},
		{"instance:qa", "qa"},
	}
	for _, tt := range tests {
		got := InstanceLabelToRole(tt.label)
		if got != tt.want {
			t.Errorf("InstanceLabelToRole(%q) = %q, want %q", tt.label, got, tt.want)
		}
	}
}
