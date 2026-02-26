package state

import (
	"path/filepath"
	"testing"
)

func newTestStore(t *testing.T) *Store {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	s, err := New(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestCreateAndCompleteDispatch(t *testing.T) {
	s := newTestStore(t)

	id, err := s.CreateDispatch("CAB-100", "Test ticket", 5, "instance:backend", "worker-1")
	if err != nil {
		t.Fatal(err)
	}
	if id == 0 {
		t.Error("expected non-zero dispatch ID")
	}

	active, err := s.IsTicketActive("CAB-100")
	if err != nil {
		t.Fatal(err)
	}
	if !active {
		t.Error("expected ticket to be active")
	}

	if err := s.CompleteDispatch(id, "completed", `{"status":"done"}`, 42, ""); err != nil {
		t.Fatal(err)
	}

	active, err = s.IsTicketActive("CAB-100")
	if err != nil {
		t.Fatal(err)
	}
	if active {
		t.Error("expected ticket to not be active after completion")
	}
}

func TestWorkerStatus(t *testing.T) {
	s := newTestStore(t)

	// Unknown worker.
	status, err := s.GetWorkerStatus("w1")
	if err != nil {
		t.Fatal(err)
	}
	if status != "unknown" {
		t.Errorf("status = %q, want %q", status, "unknown")
	}

	// Set idle.
	if err := s.SetWorkerIdle("w1"); err != nil {
		t.Fatal(err)
	}
	status, _ = s.GetWorkerStatus("w1")
	if status != "idle" {
		t.Errorf("status = %q, want %q", status, "idle")
	}

	// Set busy.
	if err := s.SetWorkerBusy("w1", 1); err != nil {
		t.Fatal(err)
	}
	status, _ = s.GetWorkerStatus("w1")
	if status != "busy" {
		t.Errorf("status = %q, want %q", status, "busy")
	}

	// Health check does NOT override busy.
	if err := s.SetWorkerHealth("w1", true, ""); err != nil {
		t.Fatal(err)
	}
	status, _ = s.GetWorkerStatus("w1")
	if status != "busy" {
		t.Errorf("status = %q after health check, want %q (should stay busy)", status, "busy")
	}

	// Set idle again.
	if err := s.SetWorkerIdle("w1"); err != nil {
		t.Fatal(err)
	}
	status, _ = s.GetWorkerStatus("w1")
	if status != "idle" {
		t.Errorf("status = %q, want %q", status, "idle")
	}
}

func TestGetActiveDispatches(t *testing.T) {
	s := newTestStore(t)

	s.CreateDispatch("CAB-1", "Ticket 1", 3, "instance:backend", "w1")
	s.CreateDispatch("CAB-2", "Ticket 2", 5, "instance:mcp", "w2")
	id3, _ := s.CreateDispatch("CAB-3", "Ticket 3", 8, "instance:qa", "w3")

	// Complete one.
	s.CompleteDispatch(id3, "completed", "", 0, "")

	active, err := s.GetActiveDispatches()
	if err != nil {
		t.Fatal(err)
	}
	if len(active) != 2 {
		t.Errorf("active dispatches = %d, want 2", len(active))
	}
}

func TestIsTicketActiveOnlyActiveStatuses(t *testing.T) {
	s := newTestStore(t)

	id, _ := s.CreateDispatch("CAB-50", "Test", 3, "instance:backend", "w1")
	s.CompleteDispatch(id, "failed", "", 0, "error")

	active, _ := s.IsTicketActive("CAB-50")
	if active {
		t.Error("failed dispatch should not count as active")
	}
}
