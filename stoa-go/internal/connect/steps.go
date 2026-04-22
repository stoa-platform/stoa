package connect

import "time"

// SyncStep records a single step in a sync pipeline for observability.
// Steps are attached to a SyncedRouteResult and surfaced by the CP UI to
// trace the deployment lifecycle (agent_received → adapter_connected →
// api_synced → ...).
type SyncStep struct {
	Name        string `json:"name"`
	Status      string `json:"status"` // "success", "failed", "skipped"
	StartedAt   string `json:"started_at"`
	CompletedAt string `json:"completed_at,omitempty"`
	Detail      string `json:"detail,omitempty"`
}

// newSyncStep creates a completed SyncStep with StartedAt == CompletedAt set
// to the current UTC time. Steps synthesized inline by the sync path are
// considered atomic — instrumenting real start/end timestamps would require
// restructuring the sync pipeline (follow-up).
func newSyncStep(name, status, detail string) SyncStep {
	now := time.Now().UTC().Format(time.RFC3339)
	return SyncStep{
		Name:        name,
		Status:      status,
		StartedAt:   now,
		CompletedAt: now,
		Detail:      detail,
	}
}
