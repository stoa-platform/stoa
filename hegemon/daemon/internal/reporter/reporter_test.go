package reporter

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/worker"
)

func TestHealthThrottle(t *testing.T) {
	var mu sync.Mutex
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		calls++
		mu.Unlock()
		w.WriteHeader(200)
	}))
	defer srv.Close()

	r := New(srv.URL, nil, "test-host", time.Hour, 0)

	// First call should go through.
	r.NotifyHealthFailure("worker-1", "ssh timeout")
	mu.Lock()
	if calls != 1 {
		t.Errorf("calls = %d, want 1", calls)
	}
	mu.Unlock()

	// Second call within cooldown should be suppressed.
	r.NotifyHealthFailure("worker-1", "ssh timeout")
	mu.Lock()
	if calls != 1 {
		t.Errorf("calls = %d after suppressed, want 1", calls)
	}
	mu.Unlock()

	// Different worker should go through.
	r.NotifyHealthFailure("worker-2", "connection refused")
	mu.Lock()
	if calls != 2 {
		t.Errorf("calls = %d, want 2 (different worker)", calls)
	}
	mu.Unlock()
}

func TestHealthThrottleExpiry(t *testing.T) {
	var mu sync.Mutex
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		calls++
		mu.Unlock()
		w.WriteHeader(200)
	}))
	defer srv.Close()

	// Use very short cooldown for testing.
	r := New(srv.URL, nil, "test-host", 10*time.Millisecond, 0)

	r.NotifyHealthFailure("worker-1", "err")
	mu.Lock()
	c1 := calls
	mu.Unlock()

	time.Sleep(20 * time.Millisecond) // Wait for cooldown to expire.

	r.NotifyHealthFailure("worker-1", "err")
	mu.Lock()
	if calls != c1+1 {
		t.Errorf("calls = %d, want %d (after cooldown expired)", calls, c1+1)
	}
	mu.Unlock()
}

func TestDigestBuffer(t *testing.T) {
	var mu sync.Mutex
	var messages []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var payload struct {
			Blocks []struct {
				Text struct {
					Text string `json:"text"`
				} `json:"text"`
			} `json:"blocks"`
		}
		json.Unmarshal(body, &payload)
		if len(payload.Blocks) > 0 {
			mu.Lock()
			messages = append(messages, payload.Blocks[0].Text.Text)
			mu.Unlock()
		}
		w.WriteHeader(200)
	}))
	defer srv.Close()

	// Digest interval = 0 means no auto-flusher; we flush manually.
	r := New(srv.URL, nil, "test-host", time.Hour, 0)

	// Buffer some digest messages.
	r.digest("event 1")
	r.digest("event 2")
	r.digest("event 3")

	if r.DigestLen() != 3 {
		t.Errorf("digest buffer = %d, want 3", r.DigestLen())
	}

	// No Slack calls yet (buffered).
	mu.Lock()
	if len(messages) != 0 {
		t.Errorf("messages = %d, want 0 (not flushed yet)", len(messages))
	}
	mu.Unlock()

	// Flush.
	r.flushDigest()

	mu.Lock()
	if len(messages) != 1 {
		t.Fatalf("messages = %d, want 1 (single digest)", len(messages))
	}
	msg := messages[0]
	mu.Unlock()

	// Should contain all 3 events in one message.
	if !strings.Contains(msg, "3 events") {
		t.Errorf("digest should say '3 events', got: %s", msg)
	}
	if !strings.Contains(msg, "event 1") || !strings.Contains(msg, "event 3") {
		t.Errorf("digest should contain all events, got: %s", msg)
	}

	// Buffer should be empty after flush.
	if r.DigestLen() != 0 {
		t.Errorf("digest buffer = %d after flush, want 0", r.DigestLen())
	}
}

func TestDigestEmptyFlush(t *testing.T) {
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.WriteHeader(200)
	}))
	defer srv.Close()

	r := New(srv.URL, nil, "test-host", time.Hour, 0)

	// Flushing an empty buffer should not send anything.
	r.flushDigest()
	if calls != 0 {
		t.Errorf("calls = %d, want 0 (empty flush)", calls)
	}
}

func TestImmediateNotificationsSkipDigest(t *testing.T) {
	var mu sync.Mutex
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		calls++
		mu.Unlock()
		w.WriteHeader(200)
	}))
	defer srv.Close()

	r := New(srv.URL, nil, "test-host", time.Hour, 0)

	// P0 notifications go immediately.
	r.NotifyError("CAB-100", "Test", "ssh error", time.Minute)
	mu.Lock()
	if calls != 1 {
		t.Errorf("calls = %d, want 1 (P0 immediate)", calls)
	}
	mu.Unlock()

	r.NotifyRetriesExhausted("CAB-100", "Test", 3)
	mu.Lock()
	if calls != 2 {
		t.Errorf("calls = %d, want 2 (P0 immediate)", calls)
	}
	mu.Unlock()

	// Digest should be empty (P0 doesn't buffer).
	if r.DigestLen() != 0 {
		t.Errorf("digest = %d, want 0 (P0 skips digest)", r.DigestLen())
	}
}

func TestCompletedFailedGoesImmediate(t *testing.T) {
	var mu sync.Mutex
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		calls++
		mu.Unlock()
		w.WriteHeader(200)
	}))
	defer srv.Close()

	r := New(srv.URL, nil, "test-host", time.Hour, 0)

	// Completed with status=failed goes immediate (P0).
	r.NotifyCompleted("CAB-200", "Fail ticket", &worker.Result{
		Status:  "failed",
		Summary: "test failure",
	}, time.Minute)
	mu.Lock()
	if calls != 1 {
		t.Errorf("calls = %d, want 1 (failed = immediate)", calls)
	}
	mu.Unlock()

	// Completed with status=done goes to digest (P2).
	r.NotifyCompleted("CAB-201", "Good ticket", &worker.Result{
		Status:   "done",
		PRNumber: 42,
		Summary:  "all good",
	}, time.Minute)
	mu.Lock()
	if calls != 1 {
		t.Errorf("calls = %d, want 1 (done = digest, not immediate)", calls)
	}
	mu.Unlock()
	if r.DigestLen() != 1 {
		t.Errorf("digest = %d, want 1", r.DigestLen())
	}
}

func TestNotifyRateLimit(t *testing.T) {
	var mu sync.Mutex
	var message string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var payload struct {
			Blocks []struct {
				Text struct {
					Text string `json:"text"`
				} `json:"text"`
			} `json:"blocks"`
		}
		json.Unmarshal(body, &payload)
		if len(payload.Blocks) > 0 {
			mu.Lock()
			message = payload.Blocks[0].Text.Text
			mu.Unlock()
		}
		w.WriteHeader(200)
	}))
	defer srv.Close()

	r := New(srv.URL, nil, "test-host", time.Hour, 0)

	backoffUntil := time.Now().Add(2 * time.Minute)
	r.NotifyRateLimit("worker-1", 3, backoffUntil)

	mu.Lock()
	defer mu.Unlock()
	if !strings.Contains(message, "rate limit") {
		t.Errorf("message should contain 'rate limit', got: %s", message)
	}
	if !strings.Contains(message, "worker-1") {
		t.Errorf("message should contain worker name, got: %s", message)
	}
	if !strings.Contains(message, "consecutive: 3") {
		t.Errorf("message should contain hit count, got: %s", message)
	}
}

func TestNoSlackURLNoops(t *testing.T) {
	r := New("", nil, "test-host", time.Hour, 0)

	// These should not panic or error.
	r.NotifyDaemonStarted(3)
	r.NotifyHealthFailure("w1", "err")
	r.NotifyError("CAB-1", "t", "e", time.Second)
	r.digest("test")
	r.flushDigest()
}
