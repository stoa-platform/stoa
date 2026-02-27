package scheduler

import (
	"testing"
	"time"
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

func TestRecordRateLimitExponentialBackoff(t *testing.T) {
	s := &Scheduler{
		quotaState: make(map[string]*QuotaState),
	}

	// First hit: 1 minute backoff.
	s.RecordRateLimit("worker-1")
	qs := s.GetQuotaState("worker-1")
	if qs == nil {
		t.Fatal("QuotaState should exist after RecordRateLimit")
	}
	if qs.HitCount != 1 {
		t.Errorf("HitCount = %d, want 1", qs.HitCount)
	}
	backoff1 := qs.BackoffAt.Sub(qs.HitAt)
	if backoff1 < 59*time.Second || backoff1 > 61*time.Second {
		t.Errorf("first backoff = %s, want ~1m", backoff1)
	}

	// Second hit: 2 minute backoff.
	s.RecordRateLimit("worker-1")
	qs = s.GetQuotaState("worker-1")
	if qs.HitCount != 2 {
		t.Errorf("HitCount = %d, want 2", qs.HitCount)
	}
	backoff2 := qs.BackoffAt.Sub(qs.HitAt)
	if backoff2 < 119*time.Second || backoff2 > 121*time.Second {
		t.Errorf("second backoff = %s, want ~2m", backoff2)
	}

	// Third hit: 4 minute backoff.
	s.RecordRateLimit("worker-1")
	qs = s.GetQuotaState("worker-1")
	if qs.HitCount != 3 {
		t.Errorf("HitCount = %d, want 3", qs.HitCount)
	}
	backoff3 := qs.BackoffAt.Sub(qs.HitAt)
	if backoff3 < 239*time.Second || backoff3 > 241*time.Second {
		t.Errorf("third backoff = %s, want ~4m", backoff3)
	}
}

func TestRecordRateLimitCap(t *testing.T) {
	s := &Scheduler{
		quotaState: make(map[string]*QuotaState),
	}

	// Hit 5 times — backoff should cap at 15 minutes.
	for i := 0; i < 5; i++ {
		s.RecordRateLimit("worker-1")
	}
	qs := s.GetQuotaState("worker-1")
	backoff := qs.BackoffAt.Sub(qs.HitAt)
	if backoff > 15*time.Minute+time.Second {
		t.Errorf("backoff = %s, should be capped at 15m", backoff)
	}
}

func TestClearRateLimit(t *testing.T) {
	s := &Scheduler{
		quotaState: make(map[string]*QuotaState),
	}

	s.RecordRateLimit("worker-1")
	if s.GetQuotaState("worker-1") == nil {
		t.Fatal("QuotaState should exist")
	}

	s.ClearRateLimit("worker-1")
	if s.GetQuotaState("worker-1") != nil {
		t.Error("QuotaState should be nil after ClearRateLimit")
	}
}
