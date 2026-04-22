package connect

import "time"

// backoffPolicy describes an exponential backoff schedule used by the SSE
// reconnect loop. Currently the single user, but kept as a named type so the
// policy (initial, cap, multiplier) can be surfaced in logs and tuned via
// configuration rather than buried as magic constants.
//
// Scope is deliberately SSE-only. The heartbeat 404 re-register threshold is
// a different concept (a stateful counter) and lives as its own const in
// connect.go — do not fold it in here without considering the protocol
// semantics described in ADR-057.
type backoffPolicy struct {
	Initial    time.Duration // delay before the 1st retry
	Max        time.Duration // cap on any single delay
	Multiplier float64       // growth factor per attempt (typically 2.0)
}

// backoff returns the delay to wait before the `attempt`-th retry (1-indexed).
// attempt=1 returns Initial. Each subsequent attempt multiplies by Multiplier,
// capped at Max. attempt<=0 returns 0.
func (p backoffPolicy) backoff(attempt int) time.Duration {
	if attempt <= 0 {
		return 0
	}
	if p.Multiplier <= 0 {
		// Guard against misconfiguration; treat as flat Initial.
		return clampDuration(p.Initial, p.Max)
	}
	d := float64(p.Initial)
	for i := 1; i < attempt; i++ {
		d *= p.Multiplier
		if p.Max > 0 && d >= float64(p.Max) {
			return p.Max
		}
	}
	return clampDuration(time.Duration(d), p.Max)
}

func clampDuration(d, max time.Duration) time.Duration {
	if max > 0 && d > max {
		return max
	}
	return d
}
