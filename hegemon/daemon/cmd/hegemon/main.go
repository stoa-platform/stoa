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
	cfg       *config.Config
	state     *state.Store
	linear    *linear.Client
	scheduler *scheduler.Scheduler
	executor  *worker.Executor
	reporter  *reporter.Reporter
	wg        sync.WaitGroup
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

	return &daemon{
		cfg:       cfg,
		state:     store,
		linear:    lc,
		scheduler: sched,
		executor:  exec,
		reporter:  rep,
	}, nil
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

	startTime := time.Now()
	result, raw, err := d.executor.Execute(execCtx, w, issue.Identifier, issue.Title, issue.Description, issue.Estimate, timeout)
	duration := time.Since(startTime)

	// Release worker.
	d.state.SetWorkerIdle(w.Name)

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
	for _, w := range d.cfg.Workers {
		err := d.executor.Ping(&w, d.cfg.HealthCheck.SSHTimeout.Duration)
		if err != nil {
			d.state.SetWorkerHealth(w.Name, false, err.Error())
			d.reporter.NotifyHealthFailure(w.Name, err.Error())
			log.Printf("HEALTH FAIL %s: %v", w.Name, err)
		} else {
			d.state.SetWorkerHealth(w.Name, true, "")
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
