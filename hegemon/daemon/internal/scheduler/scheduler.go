package scheduler

import (
	"strings"
	"sync"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/config"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/state"
)

// QuotaState tracks per-worker API rate-limit state for backoff decisions.
type QuotaState struct {
	HitAt     time.Time     // When the rate limit was last hit
	BackoffAt time.Time     // When the worker can be dispatched again
	HitCount  int           // Consecutive rate-limit hits
}

// Scheduler assigns tickets to workers based on instance labels.
type Scheduler struct {
	workers    []config.WorkerConfig
	state      *state.Store
	mu         sync.Mutex
	quotaState map[string]*QuotaState // keyed by worker name
}

// New creates a scheduler with the given worker pool.
func New(workers []config.WorkerConfig, store *state.Store) *Scheduler {
	return &Scheduler{
		workers:    workers,
		state:      store,
		quotaState: make(map[string]*QuotaState),
	}
}

// FindAvailableWorker returns the first idle worker that handles the given role.
// Skips workers in rate-limit backoff. Returns nil if no worker is available.
func (s *Scheduler) FindAvailableWorker(role string) *config.WorkerConfig {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	for i := range s.workers {
		w := &s.workers[i]
		if !hasRole(w.Roles, role) {
			continue
		}
		// Skip workers in rate-limit backoff.
		if qs, ok := s.quotaState[w.Name]; ok && now.Before(qs.BackoffAt) {
			continue
		}
		status, err := s.state.GetWorkerStatus(w.Name)
		if err != nil {
			continue
		}
		if status == "idle" || status == "unknown" {
			return w
		}
	}
	return nil
}

// RecordRateLimit marks a worker as rate-limited with exponential backoff.
// Backoff: 1min, 2min, 4min, 8min, 15min (capped).
func (s *Scheduler) RecordRateLimit(workerName string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	qs, ok := s.quotaState[workerName]
	if !ok {
		qs = &QuotaState{}
		s.quotaState[workerName] = qs
	}

	qs.HitAt = time.Now()
	qs.HitCount++

	// Exponential backoff: 1min * 2^(hits-1), capped at 15min.
	backoff := time.Minute * time.Duration(1<<uint(qs.HitCount-1))
	const maxBackoff = 15 * time.Minute
	if backoff > maxBackoff {
		backoff = maxBackoff
	}
	qs.BackoffAt = qs.HitAt.Add(backoff)
}

// ClearRateLimit resets the quota state for a worker after a successful execution.
func (s *Scheduler) ClearRateLimit(workerName string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.quotaState, workerName)
}

// GetQuotaState returns the current quota state for a worker (for alerting).
func (s *Scheduler) GetQuotaState(workerName string) *QuotaState {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.quotaState[workerName]
}

// ExtractInstanceLabel finds the instance:* label from a list of labels.
func ExtractInstanceLabel(labels []string) string {
	for _, l := range labels {
		if strings.HasPrefix(l, "instance:") {
			return l
		}
	}
	return ""
}

// InstanceLabelToRole converts "instance:backend" → "backend".
func InstanceLabelToRole(label string) string {
	return strings.TrimPrefix(label, "instance:")
}

func hasRole(roles []string, target string) bool {
	for _, r := range roles {
		if r == target {
			return true
		}
	}
	return false
}
