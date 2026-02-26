package reporter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/linear"
	"github.com/stoa-platform/stoa/hegemon/daemon/internal/worker"
)

// Reporter sends notifications to Slack and updates Linear.
type Reporter struct {
	slackURL string
	linear   *linear.Client
	http     *http.Client
	hostname string

	// Health check throttle: only notify once per cooldown per worker.
	healthCooldown  time.Duration
	mu              sync.Mutex
	lastHealthAlert map[string]time.Time

	// Digest buffer: accumulate non-critical messages, flush periodically.
	digestInterval time.Duration
	digestBuf      []string
	digestStop     chan struct{}
}

// New creates a reporter with throttle and digest support.
func New(slackURL string, linearClient *linear.Client, hostname string, healthCooldown, digestInterval time.Duration) *Reporter {
	r := &Reporter{
		slackURL:        slackURL,
		linear:          linearClient,
		http:            &http.Client{Timeout: 10 * time.Second},
		hostname:        hostname,
		healthCooldown:  healthCooldown,
		lastHealthAlert: make(map[string]time.Time),
		digestInterval:  digestInterval,
		digestStop:      make(chan struct{}),
	}
	if digestInterval > 0 {
		go r.runDigestFlusher()
	}
	return r
}

// Stop cleanly shuts down the digest flusher and flushes remaining messages.
func (r *Reporter) Stop() {
	close(r.digestStop)
	r.flushDigest()
}

// NotifyDaemonStarted sends a startup notification (immediate, P0).
func (r *Reporter) NotifyDaemonStarted(workerCount int) {
	r.slack(fmt.Sprintf(":robot_face: *HEGEMON daemon started* on `%s`\nWorkers: %d | Polling Linear...", r.hostname, workerCount))
}

// NotifyDaemonStopped sends a shutdown notification (immediate, P0).
func (r *Reporter) NotifyDaemonStopped() {
	r.slack(fmt.Sprintf(":stop_sign: *HEGEMON daemon stopped* on `%s`", r.hostname))
}

// NotifyDispatched buffers a ticket dispatch notification (digest, P2).
func (r *Reporter) NotifyDispatched(ticketID, title, workerName string, estimate int) {
	r.digest(fmt.Sprintf(
		":rocket: `%s` — %s → `%s` (%d pts)",
		ticketID, title, workerName, estimate,
	))
}

// NotifyCompleted sends a completion notification.
// Success/blocked go to digest (P2); failures go immediate (P0).
func (r *Reporter) NotifyCompleted(ticketID, title string, result *worker.Result, duration time.Duration) {
	emoji := ":white_check_mark:"
	status := "done"
	detail := result.Summary
	if result.PRNumber > 0 {
		detail = fmt.Sprintf("PR #%d — %s", result.PRNumber, result.Summary)
	}
	if result.Status == "blocked" {
		emoji = ":no_entry_sign:"
		status = "blocked"
	} else if result.Status == "failed" {
		emoji = ":x:"
		status = "failed"
	}

	msg := fmt.Sprintf(
		"%s *%s* `%s` — %s\n%s | %s | %d files",
		emoji, status, ticketID, title, detail,
		duration.Round(time.Second), result.FilesChanged,
	)

	if result.Status == "failed" {
		r.slack(msg) // P0: immediate
	} else {
		r.digest(msg) // P2: digest
	}
}

// NotifyError sends an error notification (immediate, P0).
func (r *Reporter) NotifyError(ticketID, title, errMsg string, duration time.Duration) {
	r.slack(fmt.Sprintf(
		":x: *HEGEMON error* `%s` — %s\n```%s```\nDuration: %s",
		ticketID, title, truncate(errMsg, 500), duration.Round(time.Second),
	))
}

// NotifyTimeout sends a timeout notification (immediate, P0).
func (r *Reporter) NotifyTimeout(ticketID, title, workerName string, timeout time.Duration) {
	r.slack(fmt.Sprintf(
		":hourglass: *HEGEMON timeout* `%s` — %s\nWorker: `%s` | Timeout: %s",
		ticketID, title, workerName, timeout,
	))
}

// NotifyRetriesExhausted sends a notification when a ticket exceeds max retries (immediate, P0).
func (r *Reporter) NotifyRetriesExhausted(ticketID, title string, retries int) {
	r.slack(fmt.Sprintf(
		":rotating_light: *HEGEMON retries exhausted* `%s` — %s\nFailed %d times — ticket will NOT be retried. Check Linear for details.",
		ticketID, title, retries,
	))
}

// NotifyHealthFailure sends a worker health failure notification with per-worker cooldown.
// Only fires once per healthCooldown per worker to prevent spam.
func (r *Reporter) NotifyHealthFailure(workerName, errMsg string) {
	r.mu.Lock()
	last, exists := r.lastHealthAlert[workerName]
	now := time.Now()
	if exists && now.Sub(last) < r.healthCooldown {
		r.mu.Unlock()
		return // suppressed
	}
	r.lastHealthAlert[workerName] = now
	r.mu.Unlock()

	r.slack(fmt.Sprintf(
		":warning: *HEGEMON worker unhealthy* `%s`\n%s\n_Next alert in %s_",
		workerName, errMsg, r.healthCooldown,
	))
}

// LinearUpdateInProgress moves a ticket to In Progress on Linear.
func (r *Reporter) LinearUpdateInProgress(issueID string) error {
	if r.linear == nil {
		return nil
	}
	return r.linear.UpdateIssueState(issueID, "In Progress")
}

// LinearUpdateDone moves a ticket to Done on Linear with a comment.
func (r *Reporter) LinearUpdateDone(issueID string, result *worker.Result, duration time.Duration) error {
	if r.linear == nil {
		return nil
	}
	comment := fmt.Sprintf(
		"Completed by HEGEMON worker\n\n**PR**: #%d\n**Branch**: %s\n**Files**: %d\n**Duration**: %s\n**Summary**: %s",
		result.PRNumber, result.Branch, result.FilesChanged,
		duration.Round(time.Second), result.Summary,
	)
	if err := r.linear.CreateComment(issueID, comment); err != nil {
		return fmt.Errorf("create comment: %w", err)
	}
	// Council adjustment: no auto-merge, leave ticket as "In Review" not "Done".
	// Human validates the PR then moves to Done.
	return r.linear.UpdateIssueState(issueID, "In Review")
}

// LinearUpdateBlocked moves a ticket to Blocked on Linear with a reason.
func (r *Reporter) LinearUpdateBlocked(issueID, reason string) error {
	if r.linear == nil {
		return nil
	}
	if err := r.linear.CreateComment(issueID, fmt.Sprintf("Blocked by HEGEMON: %s", reason)); err != nil {
		return fmt.Errorf("create comment: %w", err)
	}
	return r.linear.UpdateIssueState(issueID, "Blocked")
}

// digest adds a message to the digest buffer (flushed periodically).
func (r *Reporter) digest(text string) {
	r.mu.Lock()
	r.digestBuf = append(r.digestBuf, text)
	r.mu.Unlock()
}

// DigestLen returns the number of buffered digest messages (for testing).
func (r *Reporter) DigestLen() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.digestBuf)
}

// flushDigest posts all buffered messages as a single Slack message.
func (r *Reporter) flushDigest() {
	r.mu.Lock()
	if len(r.digestBuf) == 0 {
		r.mu.Unlock()
		return
	}
	msgs := make([]string, len(r.digestBuf))
	copy(msgs, r.digestBuf)
	r.digestBuf = r.digestBuf[:0]
	r.mu.Unlock()

	header := fmt.Sprintf(":memo: *HEGEMON digest* — %d events (%s)\n", len(msgs), time.Now().UTC().Format("15:04 UTC"))
	body := header
	for _, m := range msgs {
		body += "• " + m + "\n"
	}
	r.slack(body)
}

// runDigestFlusher periodically flushes the digest buffer.
func (r *Reporter) runDigestFlusher() {
	ticker := time.NewTicker(r.digestInterval)
	defer ticker.Stop()
	for {
		select {
		case <-r.digestStop:
			return
		case <-ticker.C:
			r.flushDigest()
		}
	}
}

func (r *Reporter) slack(text string) {
	if r.slackURL == "" {
		return
	}
	payload, _ := json.Marshal(map[string]interface{}{
		"blocks": []map[string]interface{}{
			{
				"type": "section",
				"text": map[string]string{
					"type": "mrkdwn",
					"text": text,
				},
			},
		},
	})
	//nolint:errcheck // best-effort notification
	r.http.Post(r.slackURL, "application/json", bytes.NewReader(payload))
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
