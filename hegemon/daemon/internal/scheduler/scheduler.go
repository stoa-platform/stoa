package scheduler

import (
	"strings"
	"sync"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/config"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/state"
)

// Scheduler assigns tickets to workers based on instance labels.
type Scheduler struct {
	workers []config.WorkerConfig
	state   *state.Store
	mu      sync.Mutex
}

// New creates a scheduler with the given worker pool.
func New(workers []config.WorkerConfig, store *state.Store) *Scheduler {
	return &Scheduler{workers: workers, state: store}
}

// FindAvailableWorker returns the first idle worker that handles the given role.
// Returns nil if no worker is available.
func (s *Scheduler) FindAvailableWorker(role string) *config.WorkerConfig {
	s.mu.Lock()
	defer s.mu.Unlock()

	for i := range s.workers {
		w := &s.workers[i]
		if !hasRole(w.Roles, role) {
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
