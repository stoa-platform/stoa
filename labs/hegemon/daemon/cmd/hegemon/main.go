package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/config"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/linear"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/metrics"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/reporter"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/scheduler"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/state"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/worker"
)

func main() {
	cfgPath := flag.String("config", "config.yaml", "path to config file")
	flag.Parse()

	cfg, err := config.Load(*cfgPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	d, err := newDaemon(cfg)
	if err != nil {
		log.Fatalf("init daemon: %v", err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	if err := d.run(ctx); err != nil {
		log.Fatalf("daemon: %v", err)
	}
}

type daemon struct {
	cfg              *config.Config
	state            *state.Store
	linear           *linear.Client
	scheduler        *scheduler.Scheduler
	executor         *worker.Executor
	gatewayExecutor  *worker.GatewayExecutor
	gatewayClient    *worker.GatewayClient
	reporter         *reporter.Reporter
	traceReporter    *reporter.TraceReporter
	metrics          *metrics.Pusher
	wg               sync.WaitGroup
}

func newDaemon(cfg *config.Config) (*daemon, error) {
	store, err := state.New(cfg.State.DBPath)
	if err != nil {
		return nil, fmt.Errorf("init state: %w", err)
	}

	lc := linear.New(cfg.Linear.APIKey, cfg.Linear.TeamID)
	if err := lc.Init(); err != nil {
		store.Close()
		return nil, fmt.Errorf("init linear: %w", err)
	}

	hostname, _ := os.Hostname()
	rep := reporter.New(
		cfg.Slack.WebhookURL, lc, hostname,
		cfg.Notification.HealthCooldown.Duration,
		cfg.Notification.DigestInterval.Duration,
	)
	sched := scheduler.New(cfg.Workers, store)
	exec := worker.New(cfg.Repo.Path, cfg.Repo.Branch)
	metricsPusher := metrics.New(cfg.Metrics.PushgatewayURL, cfg.Metrics.BasicAuth)

	d := &daemon{
		cfg:       cfg,
		state:     store,
		linear:    lc,
		scheduler: sched,
		executor:  exec,
		reporter:  rep,
		metrics:   metricsPusher,
	}

	// Initialize gateway executor and client if gateway URL is configured.
	if cfg.Gateway.URL != "" {
		gwExec := worker.NewGatewayExecutor(cfg.Gateway)
		d.gatewayExecutor = gwExec
		d.gatewayClient = worker.NewGatewayClient(cfg.Gateway.URL, gwExec.TokenCache())
		log.Printf("Gateway integration enabled: %s (mode: %s)", cfg.Gateway.URL, cfg.Gateway.DispatchMode)
	}

	// Initialize trace reporter if configured (pushes session summaries to CP API).
	if tr := reporter.NewTraceReporter(cfg.Trace.APIURL, cfg.Trace.IngestKey); tr != nil {
		d.traceReporter = tr
		log.Printf("Trace reporting enabled: %s", cfg.Trace.APIURL)
	}

	return d, nil
}

func (d *daemon) run(ctx context.Context) error {
	defer d.state.Close()

	log.Printf("HEGEMON daemon starting (%d workers)", len(d.cfg.Workers))
	d.reporter.NotifyDaemonStarted(len(d.cfg.Workers))

	// Initialize worker status.
	for _, w := range d.cfg.Workers {
		d.state.SetWorkerIdle(w.Name)
	}

	// Start health checker goroutine.
	d.wg.Add(1)
	go d.runHealthChecker(ctx)

	// Start stale dispatch cleanup goroutine (every 30 min).
	d.wg.Add(1)
	go d.runStaleCleanup(ctx)

	// Start metrics push goroutine (if Pushgateway configured).
	if d.metrics.Enabled() {
		d.wg.Add(1)
		go d.runMetricsPusher(ctx)
		log.Printf("Metrics push enabled → %s (every %s)", d.cfg.Metrics.PushgatewayURL, d.cfg.Metrics.PushInterval.Duration)
	}

	// Main poll loop.
	ticker := time.NewTicker(d.cfg.Linear.PollInterval.Duration)
	defer ticker.Stop()

	// Initial poll immediately.
	d.pollAndDispatch(ctx)

	for {
		select {
		case <-ctx.Done():
			log.Println("Shutdown signal received, draining...")
			d.reporter.Stop() // Flush digest buffer before final notification.
			d.reporter.NotifyDaemonStopped()
			d.wg.Wait()
			log.Println("Shutdown complete")
			return nil
		case <-ticker.C:
			d.pollAndDispatch(ctx)
		}
	}
}

func (d *daemon) pollAndDispatch(ctx context.Context) {
	cycle, err := d.linear.GetActiveCycle()
	if err != nil {
		log.Printf("ERROR poll cycle: %v", err)
		return
	}
	if cycle == nil {
		log.Println("No active cycle")
		return
	}

	// Get Todo issues (state type "unstarted").
	issues, err := d.linear.GetCycleIssues(cycle.ID, "unstarted")
	if err != nil {
		log.Printf("ERROR poll issues: %v", err)
		return
	}

	// Budget check: prefer gateway, fallback to local SQLite.
	if d.cfg.Budget.DailyLimitUSD > 0 {
		budgetAllowed := true
		if d.gatewayClient != nil {
			budget, err := d.gatewayClient.CheckBudget(ctx, "fleet")
			if err != nil {
				log.Printf("WARN gateway budget check failed, falling back to local: %v", err)
				dailyCost, localErr := d.state.GetDailyCost()
				if localErr != nil {
					log.Printf("WARN local budget check: %v", localErr)
				} else if dailyCost >= d.cfg.Budget.DailyLimitUSD {
					budgetAllowed = false
					log.Printf("BUDGET EXCEEDED (local): $%.2f / $%.2f", dailyCost, d.cfg.Budget.DailyLimitUSD)
				}
			} else if !budget.Allowed {
				budgetAllowed = false
				log.Printf("BUDGET EXCEEDED (gateway): $%.2f / $%.2f", budget.DailySpentUSD, budget.DailyLimitUSD)
			}
		} else {
			dailyCost, err := d.state.GetDailyCost()
			if err != nil {
				log.Printf("WARN budget check: %v", err)
			} else if dailyCost >= d.cfg.Budget.DailyLimitUSD {
				budgetAllowed = false
				log.Printf("BUDGET EXCEEDED: $%.2f / $%.2f — skipping dispatches", dailyCost, d.cfg.Budget.DailyLimitUSD)
			}
		}
		if !budgetAllowed {
			return
		}
	}

	dispatched := 0
	for _, issue := range issues {
		if ctx.Err() != nil {
			return
		}

		instanceLabel := scheduler.ExtractInstanceLabel(issue.Labels)
		if instanceLabel == "" {
			continue
		}

		// Skip mega-tickets (they are containers, not implementable).
		if hasLabel(issue.Labels, "mega-ticket") {
			continue
		}

		active, _ := d.state.IsTicketActive(issue.Identifier)
		if active {
			continue
		}

		// Retry cap: skip tickets that have failed too many times.
		retries, _ := d.state.GetRetryCount(issue.Identifier)
		if retries >= d.cfg.Notification.MaxRetries {
			continue
		}

		role := scheduler.InstanceLabelToRole(instanceLabel)
		w := d.scheduler.FindAvailableWorker(role)
		if w == nil {
			continue
		}

		d.dispatch(ctx, issue, w)
		dispatched++
	}

	if dispatched > 0 {
		log.Printf("Poll: dispatched %d tickets from cycle %s", dispatched, cycle.Name)
	} else {
		log.Printf("Poll: no dispatchable tickets in cycle %s (%d issues scanned)", cycle.Name, len(issues))
	}
}

func (d *daemon) dispatch(ctx context.Context, issue linear.Issue, w *config.WorkerConfig) {
	estimate := issue.Estimate
	if estimate == 0 {
		estimate = 5 // default estimate
	}
	timeout := d.cfg.TimeoutForEstimate(estimate)

	dispatchID, err := d.state.CreateDispatch(
		issue.Identifier, issue.Title, estimate,
		scheduler.ExtractInstanceLabel(issue.Labels), w.Name,
	)
	if err != nil {
		log.Printf("ERROR create dispatch %s: %v", issue.Identifier, err)
		return
	}

	if err := d.state.SetWorkerBusy(w.Name, dispatchID); err != nil {
		log.Printf("ERROR set worker busy %s: %v", w.Name, err)
	}

	// Update Linear → In Progress.
	if err := d.reporter.LinearUpdateInProgress(issue.ID); err != nil {
		log.Printf("WARN linear update %s: %v", issue.Identifier, err)
	}

	d.reporter.NotifyDispatched(issue.Identifier, issue.Title, w.Name, estimate)
	log.Printf("DISPATCH %s → %s (est: %d, timeout: %s)", issue.Identifier, w.Name, estimate, timeout)

	// Reserve claim if issue has a parent (part of a MEGA).
	if issue.ParentID != "" && d.gatewayClient != nil {
		if err := d.gatewayClient.ReserveClaim(ctx, issue.ParentID, w.Name); err != nil {
			if err == worker.ErrClaimConflict {
				log.Printf("CLAIM CONFLICT %s (mega %s) — skipping, owned by another worker", issue.Identifier, issue.ParentID)
				d.state.SetWorkerIdle(w.Name)
				return
			}
			log.Printf("WARN claim reserve %s: %v (proceeding without claim)", issue.Identifier, err)
		}
	}

	// Execute async — don't block the poll loop.
	d.wg.Add(1)
	go func() {
		defer d.wg.Done()
		d.executeAndReport(ctx, issue, w, dispatchID, timeout)
	}()
}

func (d *daemon) executeAndReport(ctx context.Context, issue linear.Issue, w *config.WorkerConfig, dispatchID int64, timeout time.Duration) {
	execCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Start claim heartbeat if issue has a parent MEGA.
	if issue.ParentID != "" && d.gatewayClient != nil {
		heartbeatCtx, cancelHB := context.WithCancel(ctx)
		defer cancelHB()
		go d.runClaimHeartbeat(heartbeatCtx, issue.ParentID, w.Name)
	}

	startTime := time.Now()

	// Dispatch via configured mode: ssh (default), gateway, or hybrid.
	var result *worker.Result
	var raw string
	var err error

	switch d.cfg.Gateway.DispatchMode {
	case "gateway":
		if d.gatewayExecutor != nil {
			result, raw, err = d.gatewayExecutor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
		} else {
			result, raw, err = d.executor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
		}
	case "hybrid":
		if d.gatewayExecutor != nil {
			result, raw, err = d.gatewayExecutor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
			if err != nil {
				log.Printf("WARN gateway dispatch failed for %s, falling back to SSH: %v", issue.Identifier, err)
				result, raw, err = d.executor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
			}
		} else {
			result, raw, err = d.executor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
		}
	default: // "ssh"
		result, raw, err = d.executor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
	}

	duration := time.Since(startTime)

	// Release worker.
	d.state.SetWorkerIdle(w.Name)

	// Release claim on completion (best-effort).
	if issue.ParentID != "" && d.gatewayClient != nil {
		if releaseErr := d.gatewayClient.ReleaseClaim(ctx, issue.ParentID, w.Name); releaseErr != nil {
			log.Printf("WARN claim release %s: %v", issue.Identifier, releaseErr)
		}
	}

	// Record execution cost (best-effort, even on failure).
	if result != nil && result.CostUSD > 0 {
		d.state.RecordCost(dispatchID, result.CostUSD)
		// Record cost via gateway (fire-and-forget).
		if d.gatewayClient != nil {
			costDispatchID := fmt.Sprintf("%d", dispatchID)
			go func() {
				if gwErr := d.gatewayClient.RecordCost(context.Background(), w.Name, result.CostUSD, costDispatchID); gwErr != nil {
					log.Printf("WARN gateway cost record: %v", gwErr)
				}
			}()
		}
		// Check budget thresholds after recording cost.
		d.checkBudgetThresholds()
	}

	if err != nil {
		errMsg := err.Error()
		if strings.Contains(errMsg, "timeout") {
			d.state.CompleteDispatch(dispatchID, "timeout", raw, 0, errMsg)
			d.reporter.NotifyTimeout(issue.Identifier, issue.Title, w.Name, timeout)
			d.reporter.LinearUpdateBlocked(issue.ID, fmt.Sprintf("Timeout after %s", timeout))
		} else {
			d.state.CompleteDispatch(dispatchID, "failed", raw, 0, errMsg)
			// Increment retry count and check if exhausted.
			retryCount, _ := d.state.IncrRetryCount(issue.Identifier)
			if retryCount >= d.cfg.Notification.MaxRetries {
				d.reporter.NotifyRetriesExhausted(issue.Identifier, issue.Title, retryCount)
				d.reporter.LinearUpdateBlocked(issue.ID, fmt.Sprintf("Failed %d times, retries exhausted: %s", retryCount, errMsg))
			} else {
				d.reporter.NotifyError(issue.Identifier, issue.Title, errMsg, duration)
				// Reset ticket to Todo so it can be retried.
				if resetErr := d.linear.UpdateIssueState(issue.ID, "Todo"); resetErr != nil {
					log.Printf("WARN reset %s to Todo: %v", issue.Identifier, resetErr)
				}
			}
		}
		log.Printf("FAIL %s on %s after %s: %v", issue.Identifier, w.Name, duration.Round(time.Second), err)
		return
	}

	// Rate-limit detection: if the result indicates a 429/529, apply backoff + alert.
	if result.RateLimited {
		d.scheduler.RecordRateLimit(w.Name)
		qs := d.scheduler.GetQuotaState(w.Name)
		if qs != nil {
			d.reporter.NotifyRateLimit(w.Name, qs.HitCount, qs.BackoffAt)
			log.Printf("RATE-LIMIT %s on %s — backoff until %s (hit #%d)", issue.Identifier, w.Name, qs.BackoffAt.UTC().Format("15:04"), qs.HitCount)
		}
	} else {
		// Successful execution clears any backoff state.
		d.scheduler.ClearRateLimit(w.Name)
	}

	status := "completed"
	if result.Status == "blocked" {
		status = "blocked"
	} else if result.Status == "failed" {
		status = "failed"
	}

	d.state.CompleteDispatch(dispatchID, status, raw, result.PRNumber, "")

	// Push session trace to STOA Control Plane API (fire-and-forget).
	if d.traceReporter != nil {
		d.traceReporter.ReportTrace(w.Name, issue.Identifier, result, duration)
	}

	if status == "completed" {
		d.state.ResetRetryCount(issue.Identifier)
		d.reporter.NotifyCompleted(issue.Identifier, issue.Title, result, duration)
		d.reporter.LinearUpdateDone(issue.ID, result, duration)
		log.Printf("DONE %s on %s — PR #%d (%s)", issue.Identifier, w.Name, result.PRNumber, duration.Round(time.Second))
	} else if status == "blocked" {
		d.reporter.NotifyCompleted(issue.Identifier, issue.Title, result, duration)
		d.reporter.LinearUpdateBlocked(issue.ID, result.Summary)
		log.Printf("BLOCKED %s on %s: %s", issue.Identifier, w.Name, result.Summary)
	} else {
		// Result-based failure (Claude returned status=failed).
		retryCount, _ := d.state.IncrRetryCount(issue.Identifier)
		if retryCount >= d.cfg.Notification.MaxRetries {
			d.reporter.NotifyRetriesExhausted(issue.Identifier, issue.Title, retryCount)
			d.reporter.LinearUpdateBlocked(issue.ID, fmt.Sprintf("Failed %d times: %s", retryCount, result.Summary))
		} else {
			d.reporter.NotifyError(issue.Identifier, issue.Title, result.Summary, duration)
			d.reporter.LinearUpdateBlocked(issue.ID, result.Summary)
		}
		log.Printf("FAILED %s on %s: %s", issue.Identifier, w.Name, result.Summary)
	}
}

func (d *daemon) runHealthChecker(ctx context.Context) {
	defer d.wg.Done()
	ticker := time.NewTicker(d.cfg.HealthCheck.Interval.Duration)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			d.checkWorkerHealth()
		}
	}
}

func (d *daemon) checkWorkerHealth() {
	threshold := d.cfg.HealthCheck.CircuitThreshold
	pauseDur := time.Duration(d.cfg.HealthCheck.CircuitPauseSecs) * time.Second

	for _, w := range d.cfg.Workers {
		// Skip workers currently paused by circuit breaker.
		if paused, _ := d.state.IsWorkerPaused(w.Name); paused {
			continue
		}

		err := d.executor.Ping(&w, d.cfg.HealthCheck.SSHTimeout.Duration)
		if err != nil {
			d.state.SetWorkerHealth(w.Name, false, err.Error())

			failCount, _ := d.state.IncrHealthFail(w.Name)
			if failCount >= threshold {
				// Circuit breaker tripped: pause worker.
				until := time.Now().Add(pauseDur)
				d.state.SetWorkerPaused(w.Name, until)
				d.reporter.NotifyHealthFailure(w.Name,
					fmt.Sprintf("circuit breaker tripped (%d consecutive fails) — paused until %s",
						failCount, until.UTC().Format("15:04")))
				log.Printf("CIRCUIT-BREAK %s: %d fails → paused until %s", w.Name, failCount, until.UTC().Format("15:04:05"))
			} else {
				d.reporter.NotifyHealthFailure(w.Name, err.Error())
				log.Printf("HEALTH FAIL %s (%d/%d): %v", w.Name, failCount, threshold, err)
			}
		} else {
			d.state.SetWorkerHealth(w.Name, true, "")
			d.state.ResetHealthFails(w.Name)
		}
	}
}

func (d *daemon) runStaleCleanup(ctx context.Context) {
	defer d.wg.Done()
	ticker := time.NewTicker(30 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			cleaned, err := d.state.CleanStaleDispatches(2 * time.Hour)
			if err != nil {
				log.Printf("ERROR stale cleanup: %v", err)
			} else if cleaned > 0 {
				log.Printf("STALE-CLEANUP: released %d stale dispatches", cleaned)
			}
		}
	}
}

func (d *daemon) runMetricsPusher(ctx context.Context) {
	defer d.wg.Done()
	ticker := time.NewTicker(d.cfg.Metrics.PushInterval.Duration)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			d.pushMetrics()
		}
	}
}

func (d *daemon) pushMetrics() {
	stats, err := d.state.GetAllWorkerStats()
	if err != nil {
		log.Printf("WARN metrics: get worker stats: %v", err)
		return
	}
	queueDepth, err := d.state.GetQueueDepth()
	if err != nil {
		log.Printf("WARN metrics: get queue depth: %v", err)
		return
	}
	dailyCost, err := d.state.GetDailyCost()
	if err != nil {
		log.Printf("WARN metrics: get daily cost: %v", err)
	}
	costByWorker, err := d.state.GetDailyCostByWorker()
	if err != nil {
		log.Printf("WARN metrics: get cost by worker: %v", err)
	}
	if err := d.metrics.PushWorkerHealth(stats, queueDepth, dailyCost, d.cfg.Budget.DailyLimitUSD, costByWorker); err != nil {
		log.Printf("WARN metrics push: %v", err)
	}
}

// budgetWarnDate tracks the date (YYYY-MM-DD) when the warning was last sent,
// allowing it to reset at midnight UTC so warnings fire once per day.
var budgetWarnDate string

func (d *daemon) checkBudgetThresholds() {
	if d.cfg.Budget.DailyLimitUSD <= 0 {
		return
	}
	dailyCost, err := d.state.GetDailyCost()
	if err != nil {
		return
	}
	today := time.Now().UTC().Format("2006-01-02")
	pct := (dailyCost / d.cfg.Budget.DailyLimitUSD) * 100
	if dailyCost >= d.cfg.Budget.DailyLimitUSD {
		d.reporter.NotifyBudgetExceeded(dailyCost, d.cfg.Budget.DailyLimitUSD)
		log.Printf("BUDGET EXCEEDED: $%.2f / $%.2f", dailyCost, d.cfg.Budget.DailyLimitUSD)
	} else if pct >= d.cfg.Budget.WarnPercent && budgetWarnDate != today {
		d.reporter.NotifyBudgetWarning(dailyCost, d.cfg.Budget.DailyLimitUSD)
		budgetWarnDate = today
		log.Printf("BUDGET WARNING: $%.2f / $%.2f (%.0f%%)", dailyCost, d.cfg.Budget.DailyLimitUSD, pct)
	}
}

func (d *daemon) runClaimHeartbeat(ctx context.Context, megaID, owner string) {
	ticker := time.NewTicker(15 * time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := d.gatewayClient.Heartbeat(ctx, megaID, owner); err != nil {
				log.Printf("WARN claim heartbeat %s: %v", megaID, err)
			}
		}
	}
}

func hasLabel(labels []string, target string) bool {
	for _, l := range labels {
		if l == target {
			return true
		}
	}
	return false
}
