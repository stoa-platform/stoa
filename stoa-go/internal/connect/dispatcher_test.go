package connect

import (
	"context"
	"sync/atomic"
	"testing"
)

func TestDispatcherCallsRegisteredHandler(t *testing.T) {
	d := newEventDispatcher()
	var called atomic.Int32
	var receivedData atomic.Pointer[[]byte]

	d.Register("sync-deployment", func(ctx context.Context, data []byte) {
		called.Add(1)
		cp := make([]byte, len(data))
		copy(cp, data)
		receivedData.Store(&cp)
	})

	d.Dispatch(context.Background(), rawEvent{Type: "sync-deployment", Data: []byte("hello")})

	if got := called.Load(); got != 1 {
		t.Errorf("expected handler called once, got %d", got)
	}
	if got := receivedData.Load(); got == nil || string(*got) != "hello" {
		t.Errorf("expected data 'hello', got %v", got)
	}
}

func TestDispatcherUnknownEventTypeDropped(t *testing.T) {
	d := newEventDispatcher()
	var called atomic.Int32
	d.Register("sync-deployment", func(ctx context.Context, data []byte) {
		called.Add(1)
	})

	// "heartbeat" is NOT registered — should be logged + dropped, no panic.
	d.Dispatch(context.Background(), rawEvent{Type: "heartbeat", Data: []byte("{}")})

	if got := called.Load(); got != 0 {
		t.Errorf("expected registered handler not called, got %d calls", got)
	}
}

func TestDispatcherNoOpHandler(t *testing.T) {
	// A registered no-op handler must silence the "unknown event" log by
	// matching the type — this is how we handle SSE heartbeats without
	// the log line polluting output on every keepalive.
	d := newEventDispatcher()
	d.Register("heartbeat", func(ctx context.Context, data []byte) {})
	// Should not panic, should not log "unknown event type".
	d.Dispatch(context.Background(), rawEvent{Type: "heartbeat", Data: nil})
}

func TestDispatcherLastRegisterWins(t *testing.T) {
	d := newEventDispatcher()
	var first, second atomic.Int32
	d.Register("x", func(ctx context.Context, data []byte) { first.Add(1) })
	d.Register("x", func(ctx context.Context, data []byte) { second.Add(1) })

	d.Dispatch(context.Background(), rawEvent{Type: "x", Data: nil})

	if first.Load() != 0 {
		t.Errorf("first handler called %d times, expected 0 (overwritten)", first.Load())
	}
	if second.Load() != 1 {
		t.Errorf("second handler called %d times, expected 1", second.Load())
	}
}
