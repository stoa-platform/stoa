package state

import (
	"path/filepath"
	"testing"
	"time"
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

func TestRetryCount(t *testing.T) {
	s := newTestStore(t)

	// Initial count is 0.
	count, err := s.GetRetryCount("CAB-100")
	if err != nil {
		t.Fatal(err)
	}
	if count != 0 {
		t.Errorf("initial count = %d, want 0", count)
	}

	// Increment.
	count, err = s.IncrRetryCount("CAB-100")
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Errorf("count after 1st incr = %d, want 1", count)
	}

	// Increment again.
	count, err = s.IncrRetryCount("CAB-100")
	if err != nil {
		t.Fatal(err)
	}
	if count != 2 {
		t.Errorf("count after 2nd incr = %d, want 2", count)
	}

	// Different ticket is independent.
	count, _ = s.GetRetryCount("CAB-200")
	if count != 0 {
		t.Errorf("CAB-200 count = %d, want 0", count)
	}

	// Reset.
	if err := s.ResetRetryCount("CAB-100"); err != nil {
		t.Fatal(err)
	}
	count, _ = s.GetRetryCount("CAB-100")
	if count != 0 {
		t.Errorf("count after reset = %d, want 0", count)
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

func TestCircuitBreaker(t *testing.T) {
	s := newTestStore(t)
	s.SetWorkerIdle("w1")

	// Initial: not paused, 0 fails.
	paused, err := s.IsWorkerPaused("w1")
	if err != nil {
		t.Fatal(err)
	}
	if paused {
		t.Error("new worker should not be paused")
	}

	// Increment health fails.
	count, err := s.IncrHealthFail("w1")
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Errorf("fail count = %d, want 1", count)
	}

	count, _ = s.IncrHealthFail("w1")
	if count != 2 {
		t.Errorf("fail count = %d, want 2", count)
	}

	count, _ = s.IncrHealthFail("w1")
	if count != 3 {
		t.Errorf("fail count = %d, want 3", count)
	}

	// Pause the worker.
	until := time.Now().Add(5 * time.Minute)
	if err := s.SetWorkerPaused("w1", until); err != nil {
		t.Fatal(err)
	}

	paused, _ = s.IsWorkerPaused("w1")
	if !paused {
		t.Error("worker should be paused after SetWorkerPaused")
	}

	status, _ := s.GetWorkerStatus("w1")
	if status != "paused" {
		t.Errorf("status = %q, want %q", status, "paused")
	}

	// Reset health fails also clears pause.
	if err := s.ResetHealthFails("w1"); err != nil {
		t.Fatal(err)
	}

	paused, _ = s.IsWorkerPaused("w1")
	if paused {
		t.Error("worker should not be paused after ResetHealthFails")
	}
}

func TestCircuitBreakerExpired(t *testing.T) {
	s := newTestStore(t)
	s.SetWorkerIdle("w1")

	// Set pause in the past → should be treated as not paused.
	past := time.Now().Add(-1 * time.Minute)
	if err := s.SetWorkerPaused("w1", past); err != nil {
		t.Fatal(err)
	}

	paused, _ := s.IsWorkerPaused("w1")
	if paused {
		t.Error("expired pause should not count as paused")
	}
}

func TestGetAllWorkerStats(t *testing.T) {
	s := newTestStore(t)
	s.SetWorkerIdle("w1")
	s.SetWorkerIdle("w2")
	s.SetWorkerBusy("w2", 1)
	s.IncrHealthFail("w1")

	stats, err := s.GetAllWorkerStats()
	if err != nil {
		t.Fatal(err)
	}
	if len(stats) != 2 {
		t.Fatalf("stats count = %d, want 2", len(stats))
	}

	// w1 should have 1 fail.
	for _, ws := range stats {
		if ws.Name == "w1" && ws.HealthFailCount != 1 {
			t.Errorf("w1 health_fail_count = %d, want 1", ws.HealthFailCount)
		}
		if ws.Name == "w2" && ws.Status != "busy" {
			t.Errorf("w2 status = %q, want busy", ws.Status)
		}
	}
}

func TestGetQueueDepth(t *testing.T) {
	s := newTestStore(t)

	depth, err := s.GetQueueDepth()
	if err != nil {
		t.Fatal(err)
	}
	if depth != 0 {
		t.Errorf("empty queue depth = %d, want 0", depth)
	}

	s.CreateDispatch("CAB-1", "T1", 3, "instance:backend", "w1")
	s.CreateDispatch("CAB-2", "T2", 5, "instance:mcp", "w2")

	depth, _ = s.GetQueueDepth()
	if depth != 2 {
		t.Errorf("queue depth = %d, want 2", depth)
	}
}

func TestCleanStaleDispatches(t *testing.T) {
	s := newTestStore(t)

	// Create a dispatch and manually backdate it.
	id, _ := s.CreateDispatch("CAB-99", "Stale ticket", 3, "instance:backend", "w1")
	s.db.Exec(`UPDATE dispatches SET started_at = datetime('now', '-3 hours') WHERE id = ?`, id)

	cleaned, err := s.CleanStaleDispatches(2 * time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if cleaned != 1 {
		t.Errorf("cleaned = %d, want 1", cleaned)
	}

	active, _ := s.IsTicketActive("CAB-99")
	if active {
		t.Error("stale dispatch should no longer be active")
	}
}
