package connect

import (
	"testing"
	"time"
)

func TestBackoffPolicy(t *testing.T) {
	p := backoffPolicy{
		Initial:    2 * time.Second,
		Max:        60 * time.Second,
		Multiplier: 2.0,
	}

	tests := []struct {
		attempt int
		want    time.Duration
	}{
		{0, 0},
		{-1, 0},
		{1, 2 * time.Second},
		{2, 4 * time.Second},
		{3, 8 * time.Second},
		{4, 16 * time.Second},
		{5, 32 * time.Second},
		{6, 60 * time.Second},   // capped
		{100, 60 * time.Second}, // still capped
	}
	for _, tc := range tests {
		got := p.backoff(tc.attempt)
		if got != tc.want {
			t.Errorf("backoff(%d) = %s, want %s", tc.attempt, got, tc.want)
		}
	}
}

func TestBackoffPolicyNoMultiplierTreatedAsFlat(t *testing.T) {
	p := backoffPolicy{
		Initial:    2 * time.Second,
		Max:        60 * time.Second,
		Multiplier: 0, // misconfigured
	}
	if got := p.backoff(1); got != 2*time.Second {
		t.Errorf("attempt=1 with zero Multiplier: got %s, want %s", got, 2*time.Second)
	}
	if got := p.backoff(5); got != 2*time.Second {
		t.Errorf("attempt=5 with zero Multiplier: got %s, want %s (should stay flat)", got, 2*time.Second)
	}
}

func TestBackoffPolicyNoMaxUnbounded(t *testing.T) {
	p := backoffPolicy{
		Initial:    1 * time.Second,
		Max:        0, // unbounded
		Multiplier: 2.0,
	}
	// attempt=4 → 1 * 2 * 2 * 2 = 8s, no cap
	if got := p.backoff(4); got != 8*time.Second {
		t.Errorf("attempt=4 unbounded: got %s, want 8s", got)
	}
}
