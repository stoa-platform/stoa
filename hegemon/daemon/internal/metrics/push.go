package metrics

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/state"
)

// Pusher sends Prometheus metrics to a Pushgateway.
type Pusher struct {
	url       string // Pushgateway base URL
	basicAuth string // optional "user:pass"
	client    *http.Client
}

// New creates a Pusher. url may be empty (metrics disabled).
func New(url, basicAuth string) *Pusher {
	return &Pusher{
		url:       strings.TrimRight(url, "/"),
		basicAuth: basicAuth,
		client:    &http.Client{Timeout: 10 * time.Second},
	}
}

// Enabled returns true if a Pushgateway URL is configured.
func (p *Pusher) Enabled() bool {
	return p.url != ""
}

// PushWorkerHealth sends worker health gauges and cost metrics to the Pushgateway.
func (p *Pusher) PushWorkerHealth(stats []state.WorkerHealthStats, queueDepth int, dailyCost float64, budgetLimit float64, costByWorker []state.DailyCostByWorker) error {
	if !p.Enabled() {
		return nil
	}

	var b strings.Builder

	b.WriteString("# HELP hegemon_worker_health Worker health status (1=healthy, 0=unhealthy/paused)\n")
	b.WriteString("# TYPE hegemon_worker_health gauge\n")
	for _, ws := range stats {
		val := 0
		if ws.Status == "idle" || ws.Status == "busy" {
			val = 1
		}
		fmt.Fprintf(&b, "hegemon_worker_health{worker=%q} %d\n", ws.Name, val)
	}

	b.WriteString("# HELP hegemon_worker_status Worker status (idle=0, busy=1, unhealthy=2, paused=3)\n")
	b.WriteString("# TYPE hegemon_worker_status gauge\n")
	for _, ws := range stats {
		val := 0
		switch ws.Status {
		case "busy":
			val = 1
		case "unhealthy":
			val = 2
		case "paused":
			val = 3
		}
		fmt.Fprintf(&b, "hegemon_worker_status{worker=%q} %d\n", ws.Name, val)
	}

	b.WriteString("# HELP hegemon_worker_health_fail_count Consecutive health check failures\n")
	b.WriteString("# TYPE hegemon_worker_health_fail_count gauge\n")
	for _, ws := range stats {
		fmt.Fprintf(&b, "hegemon_worker_health_fail_count{worker=%q} %d\n", ws.Name, ws.HealthFailCount)
	}

	b.WriteString("# HELP hegemon_worker_paused Worker circuit breaker active (1=paused, 0=active)\n")
	b.WriteString("# TYPE hegemon_worker_paused gauge\n")
	for _, ws := range stats {
		val := 0
		if ws.PausedUntil != nil && time.Now().UTC().Before(*ws.PausedUntil) {
			val = 1
		}
		fmt.Fprintf(&b, "hegemon_worker_paused{worker=%q} %d\n", ws.Name, val)
	}

	b.WriteString("# HELP hegemon_queue_depth Number of active dispatches in queue\n")
	b.WriteString("# TYPE hegemon_queue_depth gauge\n")
	fmt.Fprintf(&b, "hegemon_queue_depth %d\n", queueDepth)

	b.WriteString("# HELP hegemon_daily_cost_usd Total cost in USD for today\n")
	b.WriteString("# TYPE hegemon_daily_cost_usd gauge\n")
	fmt.Fprintf(&b, "hegemon_daily_cost_usd %f\n", dailyCost)

	if budgetLimit > 0 {
		remaining := budgetLimit - dailyCost
		if remaining < 0 {
			remaining = 0
		}
		b.WriteString("# HELP hegemon_budget_remaining_usd Remaining daily budget in USD\n")
		b.WriteString("# TYPE hegemon_budget_remaining_usd gauge\n")
		fmt.Fprintf(&b, "hegemon_budget_remaining_usd %f\n", remaining)
	}

	if len(costByWorker) > 0 {
		b.WriteString("# HELP hegemon_worker_daily_cost_usd Daily cost per worker in USD\n")
		b.WriteString("# TYPE hegemon_worker_daily_cost_usd gauge\n")
		for _, c := range costByWorker {
			fmt.Fprintf(&b, "hegemon_worker_daily_cost_usd{worker=%q} %f\n", c.WorkerName, c.CostUSD)
		}
	}

	return p.push("hegemon_daemon", b.String())
}

func (p *Pusher) push(job, body string) error {
	url := fmt.Sprintf("%s/metrics/job/%s", p.url, job)
	req, err := http.NewRequest(http.MethodPut, url, strings.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "text/plain")

	if p.basicAuth != "" {
		parts := strings.SplitN(p.basicAuth, ":", 2)
		if len(parts) == 2 {
			req.SetBasicAuth(parts[0], parts[1])
		}
	}

	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("push metrics: %w", err)
	}
	resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("pushgateway returned %d", resp.StatusCode)
	}
	return nil
}
