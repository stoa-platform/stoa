package worker

import (
	"testing"
)

func TestParseResultJSONArray(t *testing.T) {
	raw := `[hegemon] Secrets loaded from Infisical (5 vars)
[{"type":"system","subtype":"init"},{"type":"assistant","message":"done"},{"type":"result","subtype":"success","is_error":false,"total_cost_usd":0.05,"num_turns":5,"result":"All done.\n{\"status\": \"done\", \"pr_number\": 42, \"branch\": \"feat/test\", \"files_changed\": 3, \"summary\": \"implemented feature\"}"}]`
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "done" {
		t.Errorf("status = %q, want done", r.Status)
	}
	if r.PRNumber != 42 {
		t.Errorf("pr_number = %d, want 42", r.PRNumber)
	}
	if r.CostUSD != 0.05 {
		t.Errorf("cost_usd = %f, want 0.05", r.CostUSD)
	}
}

func TestParseResultMaxTurns(t *testing.T) {
	raw := `[{"type":"result","subtype":"error_max_turns","is_error":true,"total_cost_usd":0.10,"num_turns":30,"result":"max turns reached"}]`
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	if r.Summary != "hit max turns (30)" {
		t.Errorf("summary = %q, want hit max turns (30)", r.Summary)
	}
}

func TestParseResultAuthFailure(t *testing.T) {
	raw := "Not logged in. Please run claude login."
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	if r.Summary != "Claude CLI not authenticated on worker" {
		t.Errorf("summary = %q", r.Summary)
	}
}

func TestParseResultEmptyResultText(t *testing.T) {
	raw := `[{"type":"result","subtype":"success","is_error":false,"total_cost_usd":0.01,"num_turns":1,"result":""}]`
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "done" {
		t.Errorf("status = %q, want done", r.Status)
	}
}

func TestParseResultIsError(t *testing.T) {
	raw := `[{"type":"result","subtype":"error","is_error":true,"total_cost_usd":0.02,"num_turns":3,"result":"something went wrong"}]`
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
}

func TestParseResultLegacySingleObject(t *testing.T) {
	raw := `{"type":"result","result":"All done.\n{\"status\": \"done\", \"pr_number\": 7, \"branch\": \"feat/x\", \"files_changed\": 1, \"summary\": \"fixed it\"}"}`
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "done" {
		t.Errorf("status = %q, want done", r.Status)
	}
	if r.PRNumber != 7 {
		t.Errorf("pr_number = %d, want 7", r.PRNumber)
	}
}

func TestTurnsForEstimate(t *testing.T) {
	tests := []struct {
		est  int
		want int
	}{
		{1, 20}, {3, 20}, {5, 30}, {8, 40}, {13, 50}, {21, 50},
	}
	for _, tt := range tests {
		got := turnsForEstimate(tt.est)
		if got != tt.want {
			t.Errorf("turnsForEstimate(%d) = %d, want %d", tt.est, got, tt.want)
		}
	}
}

func TestModelForEstimate(t *testing.T) {
	// v2 routing: Haiku for <=3pts, Opus for everything else.
	tests := []struct {
		est  int
		want string
	}{
		{1, "haiku"}, {3, "haiku"}, {4, "opus"}, {5, "opus"}, {8, "opus"}, {13, "opus"},
	}
	for _, tt := range tests {
		got := modelForEstimate(tt.est)
		if got != tt.want {
			t.Errorf("modelForEstimate(%d) = %q, want %q", tt.est, got, tt.want)
		}
	}
}

func TestIsRateLimited(t *testing.T) {
	tests := []struct {
		raw  string
		want bool
	}{
		{"error: 429 Too Many Requests", true},
		{"error: 529 Overloaded", true},
		{"RateLimitError: rate_limit_exceeded", true},
		{"API overloaded, please try again", true},
		{"quota exhausted for this billing period", true},
		{"insufficient credit balance", true},
		{"All done. PR #42 created.", false},
		{"Not logged in. Please run claude login.", false},
		{"", false},
	}
	for _, tt := range tests {
		got := isRateLimited(tt.raw)
		if got != tt.want {
			t.Errorf("isRateLimited(%q) = %v, want %v", tt.raw[:min(len(tt.raw), 40)], got, tt.want)
		}
	}
}

func TestParseResultRateLimited(t *testing.T) {
	raw := "error: 429 Too Many Requests - rate_limit_exceeded"
	r, err := parseResult(raw)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	if !r.RateLimited {
		t.Error("RateLimited should be true")
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func TestBuildPrompt(t *testing.T) {
	p := buildPrompt("CAB-1234", "Test Title", "Do the thing")
	if !contains(p, "CAB-1234") || !contains(p, "Test Title") || !contains(p, "Do the thing") {
		t.Errorf("prompt missing expected content")
	}
	if !contains(p, "feat/cab-1234") {
		t.Errorf("prompt missing lowercase branch prefix")
	}
	if !contains(p, "Environment Setup") {
		t.Errorf("prompt missing environment setup section")
	}
	if !contains(p, "Budget your turns") {
		t.Errorf("prompt missing turn budget hint")
	}
}

func TestShellQuote(t *testing.T) {
	tests := []struct {
		in, want string
	}{
		{"hello", "'hello'"},
		{"it's", "'it'\"'\"'s'"},
		{"", "''"},
	}
	for _, tt := range tests {
		got := shellQuote(tt.in)
		if got != tt.want {
			t.Errorf("shellQuote(%q) = %q, want %q", tt.in, got, tt.want)
		}
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(s) > 0 && containsHelper(s, sub))
}

func containsHelper(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
