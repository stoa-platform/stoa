package reporter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
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
}

// New creates a reporter.
func New(slackURL string, linearClient *linear.Client, hostname string) *Reporter {
	return &Reporter{
		slackURL: slackURL,
		linear:   linearClient,
		http:     &http.Client{Timeout: 10 * time.Second},
		hostname: hostname,
	}
}

// NotifyDaemonStarted sends a startup notification.
func (r *Reporter) NotifyDaemonStarted(workerCount int) {
	r.slack(fmt.Sprintf(":robot_face: *HEGEMON daemon started* on `%s`\nWorkers: %d | Polling Linear...", r.hostname, workerCount))
}

// NotifyDaemonStopped sends a shutdown notification.
func (r *Reporter) NotifyDaemonStopped() {
	r.slack(fmt.Sprintf(":stop_sign: *HEGEMON daemon stopped* on `%s`", r.hostname))
}

// NotifyDispatched sends a ticket dispatch notification.
func (r *Reporter) NotifyDispatched(ticketID, title, workerName string, estimate int) {
	r.slack(fmt.Sprintf(
		":rocket: *HEGEMON dispatch* `%s` — %s\nWorker: `%s` | Est: %d pts",
		ticketID, title, workerName, estimate,
	))
}

// NotifyCompleted sends a completion notification with result details.
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

	r.slack(fmt.Sprintf(
		"%s *HEGEMON %s* `%s` — %s\n%s\nDuration: %s | Files: %d",
		emoji, status, ticketID, title, detail,
		duration.Round(time.Second), result.FilesChanged,
	))
}

// NotifyError sends an error notification.
func (r *Reporter) NotifyError(ticketID, title, errMsg string, duration time.Duration) {
	r.slack(fmt.Sprintf(
		":x: *HEGEMON error* `%s` — %s\n```%s```\nDuration: %s",
		ticketID, title, truncate(errMsg, 500), duration.Round(time.Second),
	))
}

// NotifyTimeout sends a timeout notification.
func (r *Reporter) NotifyTimeout(ticketID, title, workerName string, timeout time.Duration) {
	r.slack(fmt.Sprintf(
		":hourglass: *HEGEMON timeout* `%s` — %s\nWorker: `%s` | Timeout: %s",
		ticketID, title, workerName, timeout,
	))
}

// NotifyHealthFailure sends a worker health check failure notification.
func (r *Reporter) NotifyHealthFailure(workerName, errMsg string) {
	r.slack(fmt.Sprintf(
		":warning: *HEGEMON worker unhealthy* `%s`\n%s",
		workerName, errMsg,
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
