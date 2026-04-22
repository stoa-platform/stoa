package connect

import "sync"

// agentState holds the agent's mutable runtime state, guarded by a single RWMutex.
//
// Only fields that are concurrently mutated from multiple goroutines live here.
// Immutable-after-New fields (Agent.cfg, Agent.client, Agent.startTime, Agent.healthPort
// — set once in the first Register before any loop goroutine starts) stay on Agent
// without locking.
type agentState struct {
	mu             sync.RWMutex
	gatewayID      string
	discoveredAPIs []DiscoveredAPIPayload // owned copy; SetDiscoveredAPIs and DiscoveredAPIs
	// clone the outer slice. Inner slices (Paths, Methods, Policies) are treated
	// as read-only by all consumers — freshly built in runDiscovery, never mutated
	// afterwards — so shallow clone is sufficient.
}

func newAgentState() *agentState {
	return &agentState{}
}

// GatewayID returns the current assigned gateway ID, or empty string if unregistered.
func (s *agentState) GatewayID() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.gatewayID
}

// SetGatewayID stores the given gateway ID.
func (s *agentState) SetGatewayID(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.gatewayID = id
}

// ClearGatewayID resets the gateway ID to empty (used before re-registration).
func (s *agentState) ClearGatewayID() {
	s.SetGatewayID("")
}

// SetDiscoveredAPIs stores a defensive copy of in. Mutating in after this call
// does not affect internal state.
func (s *agentState) SetDiscoveredAPIs(in []DiscoveredAPIPayload) {
	var copied []DiscoveredAPIPayload
	if in != nil {
		copied = make([]DiscoveredAPIPayload, len(in))
		copy(copied, in)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.discoveredAPIs = copied
}

// DiscoveredAPIs returns a defensive copy of the currently cached discovered APIs.
// The returned slice is safe for the caller to mutate.
func (s *agentState) DiscoveredAPIs() []DiscoveredAPIPayload {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.discoveredAPIs == nil {
		return nil
	}
	out := make([]DiscoveredAPIPayload, len(s.discoveredAPIs))
	copy(out, s.discoveredAPIs)
	return out
}

// DiscoveredAPIsCount returns the number of cached discovered APIs.
func (s *agentState) DiscoveredAPIsCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.discoveredAPIs)
}

// ComputeRoutesCount returns the total number of routes across active discovered APIs.
// Each path on an active API counts as one route (CAB-1916); an active API with no
// declared paths counts as 1.
func (s *agentState) ComputeRoutesCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	count := 0
	for _, api := range s.discoveredAPIs {
		if !api.IsActive {
			continue
		}
		paths := len(api.Paths)
		if paths == 0 {
			paths = 1
		}
		count += paths
	}
	return count
}
