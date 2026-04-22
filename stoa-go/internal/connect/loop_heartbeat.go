package connect

import (
	"context"
	"errors"
	"log"
	"time"
)

// runHeartbeat is the heartbeat ticker loop. Sends a.Heartbeat on each tick
// and auto-re-registers after reRegisterThreshold consecutive 404 responses
// from the CP (see ADR-057). Exits cleanly on ctx cancellation.
//
// Threshold value preserved verbatim from pre-GO-2 behavior — changing it
// would alter the CP↔agent re-registration sliding window.
func runHeartbeat(ctx context.Context, a *Agent) {
	ticker := time.NewTicker(a.cfg.HeartbeatInterval)
	defer ticker.Stop()
	consecutiveNotFound := 0
	for {
		select {
		case <-ctx.Done():
			log.Println("heartbeat stopped")
			return
		case <-ticker.C:
			err := a.Heartbeat(ctx)
			if err == nil {
				consecutiveNotFound = 0
				continue
			}
			if !errors.Is(err, ErrGatewayNotFound) {
				log.Printf("heartbeat error: %v", err)
				continue
			}
			consecutiveNotFound++
			log.Printf("heartbeat 404 (%d/%d) — gateway not found on CP",
				consecutiveNotFound, reRegisterThreshold)
			if consecutiveNotFound < reRegisterThreshold {
				continue
			}
			log.Println("gateway purged from CP, re-registering...")
			a.state.ClearGatewayID()
			if regErr := a.Register(ctx, a.healthPort); regErr != nil {
				log.Printf("re-registration failed: %v", regErr)
			} else {
				log.Printf("re-registered with CP: id=%s", a.state.GatewayID())
				consecutiveNotFound = 0
			}
		}
	}
}
