package connect

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// sseTestServer builds an httptest.Server that emits a single sync-deployment
// event with `data:` payload of the given size, then closes the stream.
func sseTestServer(t *testing.T, dataSize int) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		flusher, _ := w.(http.Flusher)
		// Build a large data line. desired_state carries an inline JSON object
		// approximated here by a string of `x` chars large enough to exceed
		// bufio default 64KB.
		payload := strings.Repeat("x", dataSize)
		_, _ = fmt.Fprintf(w, "event: sync-deployment\ndata: %s\n\n", payload)
		flusher.Flush()
	}))
}

// TestSSEStreamAcceptsLargeEvent is the regression guard for REWRITE-BUGS.md F.6.
// Default bufio.Scanner buffer (64 KB) would silently drop events whose `data:`
// line exceeds that size; the fix raises max to sseScannerMaxBuf (1 MB) and
// relies on scanner.Err() propagation to surface bufio.ErrTooLong if ever hit.
func TestSSEStreamAcceptsLargeEvent(t *testing.T) {
	// 500 KB — well past the old 64 KB limit, comfortably under the new 1 MB cap.
	const size = 500 << 10
	srv := sseTestServer(t, size)
	defer srv.Close()

	stream := newSSEStream(srv.URL, "test-key", http.DefaultTransport)
	var receivedSize atomic.Int64
	sink := func(ctx context.Context, ev rawEvent) error {
		if ev.Type == "sync-deployment" {
			receivedSize.Store(int64(len(ev.Data)))
		}
		return nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	err := stream.Run(ctx, "gw-big", sink)

	// Stream ends when server closes connection — expect io.EOF, NOT ErrTooLong.
	if !errors.Is(err, io.EOF) {
		t.Errorf("expected io.EOF, got %v", err)
	}
	if errors.Is(err, bufio.ErrTooLong) {
		t.Errorf("scanner should not trigger ErrTooLong for %d-byte event", size)
	}
	if got := receivedSize.Load(); got != int64(size) {
		t.Errorf("sink received %d bytes, expected %d (silent truncation? F.6 regression)", got, size)
	}
}

// TestSSEStreamReportsScannerErrorOnOversizedEvent asserts that an event
// payload exceeding sseScannerMaxBuf surfaces bufio.ErrTooLong visibly
// rather than ending the stream silently.
func TestSSEStreamReportsScannerErrorOnOversizedEvent(t *testing.T) {
	// 2 MB — past the 1 MB cap.
	const size = 2 << 20
	srv := sseTestServer(t, size)
	defer srv.Close()

	stream := newSSEStream(srv.URL, "test-key", http.DefaultTransport)
	sink := func(ctx context.Context, ev rawEvent) error {
		t.Errorf("sink should not receive an oversized event, got %d bytes", len(ev.Data))
		return nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	err := stream.Run(ctx, "gw-huge", sink)

	if err == nil {
		t.Fatal("expected non-nil error on oversized event")
	}
	if !errors.Is(err, bufio.ErrTooLong) {
		t.Errorf("expected bufio.ErrTooLong wrapped in err chain, got %v", err)
	}
}

// TestSSEStreamPropagatesHTTPStatus asserts a non-200 status from the SSE
// endpoint surfaces as a concrete error (caller decides whether to retry).
func TestSSEStreamPropagatesHTTPStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer srv.Close()

	stream := newSSEStream(srv.URL, "bad-key", http.DefaultTransport)
	err := stream.Run(context.Background(), "gw-401", func(ctx context.Context, ev rawEvent) error {
		return nil
	})
	if err == nil {
		t.Fatal("expected non-nil error on 401")
	}
	if !strings.Contains(err.Error(), "401") {
		t.Errorf("expected error to mention status 401, got %v", err)
	}
}

// TestSSEStreamSinkErrorAborts asserts a sink error stops the stream loop
// and is surfaced to the caller.
func TestSSEStreamSinkErrorAborts(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		flusher, _ := w.(http.Flusher)
		_, _ = fmt.Fprintf(w, "event: sync-deployment\ndata: {\"x\":1}\n\n")
		flusher.Flush()
		// Keep conn open so scanner waits — sink error should bail out.
		time.Sleep(2 * time.Second)
	}))
	defer srv.Close()

	sinkErr := errors.New("sink failure")
	stream := newSSEStream(srv.URL, "key", http.DefaultTransport)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	err := stream.Run(ctx, "gw-sink-err", func(ctx context.Context, ev rawEvent) error {
		return sinkErr
	})
	if !errors.Is(err, sinkErr) {
		t.Errorf("expected sink error surfaced, got %v", err)
	}
}
