package connect

import (
	"context"
	"fmt"
	"runtime"
	"sync"
	"testing"
	"time"
)

func TestAgentStateSetAndGetGatewayID(t *testing.T) {
	s := newAgentState()
	if got := s.GatewayID(); got != "" {
		t.Fatalf("expected empty initial gatewayID, got %q", got)
	}
	s.SetGatewayID("gw-1")
	if got := s.GatewayID(); got != "gw-1" {
		t.Fatalf("expected gw-1, got %q", got)
	}
	s.ClearGatewayID()
	if got := s.GatewayID(); got != "" {
		t.Fatalf("expected empty after Clear, got %q", got)
	}
}

func TestAgentStateDiscoveredAPIsCopyIn(t *testing.T) {
	s := newAgentState()
	in := []DiscoveredAPIPayload{
		{Name: "a", IsActive: true, Paths: []string{"/a"}},
		{Name: "b", IsActive: false},
	}
	s.SetDiscoveredAPIs(in)

	// Mutating in after Set must NOT affect internal state.
	in[0].Name = "mutated"
	in[0].IsActive = false

	got := s.DiscoveredAPIs()
	if len(got) != 2 {
		t.Fatalf("expected 2, got %d", len(got))
	}
	if got[0].Name != "a" {
		t.Fatalf("copy-in broken: expected name=a, got %q", got[0].Name)
	}
	if !got[0].IsActive {
		t.Fatalf("copy-in broken: expected IsActive=true, got false")
	}
}

func TestAgentStateDiscoveredAPIsCopyOut(t *testing.T) {
	s := newAgentState()
	s.SetDiscoveredAPIs([]DiscoveredAPIPayload{
		{Name: "a", IsActive: true},
	})

	// Mutating the returned slice must NOT affect internal state.
	got := s.DiscoveredAPIs()
	got[0].Name = "hacked"
	got[0].IsActive = false

	second := s.DiscoveredAPIs()
	if second[0].Name != "a" {
		t.Fatalf("copy-out broken: expected name=a, got %q", second[0].Name)
	}
	if !second[0].IsActive {
		t.Fatalf("copy-out broken: expected IsActive=true, got false")
	}
}

func TestAgentStateDiscoveredAPIsNil(t *testing.T) {
	s := newAgentState()
	s.SetDiscoveredAPIs(nil)
	if got := s.DiscoveredAPIs(); got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
	if got := s.DiscoveredAPIsCount(); got != 0 {
		t.Fatalf("expected 0, got %d", got)
	}
}

func TestAgentStateComputeRoutesCount(t *testing.T) {
	tests := []struct {
		name string
		in   []DiscoveredAPIPayload
		want int
	}{
		{"empty", nil, 0},
		{"single active with paths", []DiscoveredAPIPayload{
			{IsActive: true, Paths: []string{"/a", "/b"}},
		}, 2},
		{"active without paths counts as 1", []DiscoveredAPIPayload{
			{IsActive: true},
		}, 1},
		{"inactive skipped", []DiscoveredAPIPayload{
			{IsActive: false, Paths: []string{"/skipped"}},
			{IsActive: true, Paths: []string{"/kept"}},
		}, 1},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			s := newAgentState()
			s.SetDiscoveredAPIs(tc.in)
			if got := s.ComputeRoutesCount(); got != tc.want {
				t.Errorf("expected %d, got %d", tc.want, got)
			}
		})
	}
}

// TestAgentStateRace fires concurrent writers and readers against agentState
// with -race on to detect any unprotected field access. The test itself
// cannot fail under a correct implementation; the race detector is the judge.
func TestAgentStateRace(t *testing.T) {
	s := newAgentState()
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()

	var wg sync.WaitGroup

	// Writer: flips gatewayID and discoveredAPIs continuously.
	wg.Add(1)
	go func() {
		defer wg.Done()
		var i int
		for ctx.Err() == nil {
			i++
			s.SetGatewayID(fmt.Sprintf("gw-%d", i))
			s.SetDiscoveredAPIs([]DiscoveredAPIPayload{
				{Name: fmt.Sprintf("api-%d", i), IsActive: i%2 == 0, Paths: []string{"/p1", "/p2"}},
			})
			if i%5 == 0 {
				s.ClearGatewayID()
			}
			runtime.Gosched()
		}
	}()

	// Readers: mimic the goroutines that concurrently read in production
	// (heartbeat, /health handler, sync loops, SSE URL building).
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for ctx.Err() == nil {
				_ = s.GatewayID()
				_ = s.DiscoveredAPIsCount()
				_ = s.ComputeRoutesCount()
				_ = s.DiscoveredAPIs()
				runtime.Gosched()
			}
		}()
	}

	wg.Wait()
}
