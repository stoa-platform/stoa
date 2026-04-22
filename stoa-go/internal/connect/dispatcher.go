package connect

import (
	"context"
	"log"
)

// eventHandler processes one rawEvent's payload. Handlers run inline on the
// SSE scanner goroutine — they MUST NOT block indefinitely. Long-running
// side effects (adapter syncs) are fine, but should respect ctx cancellation.
type eventHandler func(ctx context.Context, data []byte)

// eventDispatcher routes SSE rawEvents to registered handlers by event type.
//
// Each event is handled independently — the SSE protocol here has no
// ordering contract between event types (a "heartbeat" and a
// "sync-deployment" arriving back-to-back are logically concurrent; the
// scanner just delivers them in wire order). If we ever introduce a pair
// with an ordering dependency (e.g. "config-updated" gating "route-sync"),
// this is the place to make it explicit — either via a queue, a blocking
// ordering handler, or by moving one of the events out of the SSE channel.
//
// Unknown event types are logged and dropped (never fatal) so the CP can
// roll out new event types without breaking older agents.
//
// NOT safe for concurrent Register; intended to be populated once at
// goroutine spawn time. Dispatch is safe to call concurrently with reads
// once registration is complete (handlers map is read-only post-setup).
type eventDispatcher struct {
	handlers map[string]eventHandler
}

func newEventDispatcher() *eventDispatcher {
	return &eventDispatcher{handlers: make(map[string]eventHandler)}
}

// Register installs a handler for the given SSE event type. Silently
// overwrites any prior handler for the same type — callers are assumed to
// own their type exclusively.
func (d *eventDispatcher) Register(eventType string, h eventHandler) {
	d.handlers[eventType] = h
}

// Dispatch routes ev to the handler registered for ev.Type. Unknown types
// are logged at info level and dropped.
func (d *eventDispatcher) Dispatch(ctx context.Context, ev rawEvent) {
	if h, ok := d.handlers[ev.Type]; ok {
		h(ctx, ev.Data)
		return
	}
	log.Printf("sse-stream: unknown event type %q", ev.Type)
}
