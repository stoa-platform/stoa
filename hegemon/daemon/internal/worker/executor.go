package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/config"
)

// Result is the structured output from a Claude execution.
type Result struct {
	Status       string  `json:"status"` // done, blocked, failed
	PRNumber     int     `json:"pr_number"`
	Branch       string  `json:"branch"`
	FilesChanged int     `json:"files_changed"`
	Summary      string  `json:"summary"`
	CostUSD      float64 `json:"cost_usd"`
}

// Executor runs Claude CLI on remote workers via SSH.
type Executor struct {
	repoPath string
	branch   string
}

// New creates a worker executor.
func New(repoPath, branch string) *Executor {
	return &Executor{repoPath: repoPath, branch: branch}
}

// Execute dispatches a ticket to a worker via SSH and waits for completion.
// Returns the parsed result and raw stdout.
func (e *Executor) Execute(ctx context.Context, w *config.WorkerConfig, ticketID, title, description string, estimate int, timeout time.Duration) (*Result, string, error) {
	client, err := e.dial(w)
	if err != nil {
		return nil, "", fmt.Errorf("ssh dial %s: %w", w.Host, err)
	}
	defer client.Close()

	maxTurns := turnsForEstimate(estimate)
	model := modelForEstimate(estimate)
	prompt := buildPrompt(ticketID, title, description)

	// Write prompt to a temp file on the remote, then run claude with it.
	// This avoids shell quoting issues with multi-line prompts containing special characters.
	promptFile := fmt.Sprintf("/tmp/hegemon-prompt-%s.txt", ticketID)
	if err := e.writeRemoteFile(client, promptFile, prompt); err != nil {
		return nil, "", fmt.Errorf("write prompt file: %w", err)
	}

	// Build the remote command.
	// bash -l sources .profile which loads Infisical secrets (ANTHROPIC_API_KEY, GH_TOKEN).
	// --dangerously-skip-permissions: workers are sandboxed fleet, bypasses all permission checks
	// including PreToolUse hooks (pre-instance-scope.sh blocks Bash otherwise).
	// --model: route to Opus for complex tickets (>5pts), Sonnet for small ones.
	cmd := fmt.Sprintf(
		`bash -l -c 'cd %s && git checkout %s && git pull --ff-only && claude -p "$(cat %s)" --output-format json --dangerously-skip-permissions --model %s --max-turns %d --verbose 2>/dev/null; rm -f %s'`,
		e.repoPath, e.branch, promptFile, model, maxTurns, promptFile,
	)

	session, err := client.NewSession()
	if err != nil {
		return nil, "", fmt.Errorf("ssh session: %w", err)
	}
	defer session.Close()

	var stdout, stderr bytes.Buffer
	session.Stdout = &stdout
	session.Stderr = &stderr

	// Run with timeout context.
	done := make(chan error, 1)
	go func() {
		done <- session.Run(cmd)
	}()

	select {
	case err := <-done:
		raw := stdout.String()
		if err != nil {
			return nil, raw, fmt.Errorf("claude execution: %w\nstderr: %s", err, stderr.String())
		}
		result, parseErr := parseResult(raw)
		return result, raw, parseErr
	case <-ctx.Done():
		// Timeout — signal the session to close (kills remote process).
		session.Signal(ssh.SIGTERM)
		return nil, "", fmt.Errorf("timeout after %s", timeout)
	}
}

// Ping checks if a worker is reachable via SSH and Claude CLI is available.
func (e *Executor) Ping(w *config.WorkerConfig, timeout time.Duration) error {
	client, err := e.dialWithTimeout(w, timeout)
	if err != nil {
		return fmt.Errorf("ssh: %w", err)
	}
	defer client.Close()

	session, err := client.NewSession()
	if err != nil {
		return fmt.Errorf("session: %w", err)
	}
	defer session.Close()

	out, err := session.CombinedOutput("bash -l -c 'claude --version 2>/dev/null || echo MISSING'")
	if err != nil {
		return fmt.Errorf("run: %w", err)
	}
	if strings.Contains(string(out), "MISSING") {
		return fmt.Errorf("claude CLI not found on %s", w.Host)
	}
	return nil
}

func (e *Executor) dial(w *config.WorkerConfig) (*ssh.Client, error) {
	return e.dialWithTimeout(w, 10*time.Second)
}

func (e *Executor) dialWithTimeout(w *config.WorkerConfig, timeout time.Duration) (*ssh.Client, error) {
	keyData, err := os.ReadFile(os.ExpandEnv(w.SSHKey))
	if err != nil {
		return nil, fmt.Errorf("read key %s: %w", w.SSHKey, err)
	}
	signer, err := ssh.ParsePrivateKey(keyData)
	if err != nil {
		return nil, fmt.Errorf("parse key: %w", err)
	}

	cfg := &ssh.ClientConfig{
		User:            w.User,
		Auth:            []ssh.AuthMethod{ssh.PublicKeys(signer)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), //nolint:gosec // internal fleet
		Timeout:         timeout,
	}

	addr := fmt.Sprintf("%s:%d", w.Host, w.Port)
	return ssh.Dial("tcp", addr, cfg)
}

// writeRemoteFile writes content to a file on the remote host via SSH.
func (e *Executor) writeRemoteFile(client *ssh.Client, path, content string) error {
	session, err := client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()
	session.Stdin = bytes.NewReader([]byte(content))
	return session.Run(fmt.Sprintf("cat > %s", path))
}

// modelForEstimate selects claude model based on ticket complexity.
// All STOA tickets use Opus: the codebase has 40K tokens of rules that saturate
// Sonnet's context, causing it to spend all turns reading without writing.
// Sonnet 3pt attempt: $2.91 wasted (31 turns, 0 output). Opus resolves in 5-15 turns.
func modelForEstimate(estimate int) string {
	// Always Opus for STOA — Sonnet can't handle the rule density.
	// Keep the estimate param for future per-repo routing.
	_ = estimate
	return "opus"
}

func turnsForEstimate(estimate int) int {
	switch {
	case estimate <= 3:
		return 40
	case estimate <= 5:
		return 50
	case estimate <= 8:
		return 60
	default:
		return 75
	}
}

func buildPrompt(ticketID, title, description string) string {
	return fmt.Sprintf(`You are HEGEMON worker executing ticket %s: %s

## Ticket Description
%s

## Instructions
1. Create a feature branch: feat/%s-<short-description>
2. Read ONLY the files you need to modify — do NOT explore the full codebase
3. Implement the changes following existing patterns in adjacent files
4. Run the relevant quality gate (lint, test, format)
5. Commit with conventional message including ticket ID
6. Push the branch and create a PR via gh pr create
7. Do NOT merge the PR — leave it for human review (Ask mode)

## Environment Setup (IMPORTANT — do this first if needed)
- Python (control-plane-api): cd control-plane-api && source .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]")
- Node (control-plane-ui, portal): cd <component> && npm ci
- Rust (stoa-gateway): cargo build (toolchain is pre-installed)
- Do NOT spend more than 3 tool calls on environment setup

## Constraints
- Maximum 300 LOC changed
- All tests must pass
- No secrets in code
- Follow existing code patterns
- Start coding within the first 5 tool calls — minimize exploration
- Budget your turns: save at least 5 turns for commit + push + PR creation

## Output
End your response with a JSON block:
{"status": "done|blocked|failed", "pr_number": 0, "branch": "", "files_changed": 0, "summary": ""}`,
		ticketID, title, description, strings.ToLower(ticketID))
}

func shellQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "'\"'\"'") + "'"
}

// claudeResultItem represents one item in Claude's --output-format json output array.
type claudeResultItem struct {
	Type     string  `json:"type"`
	Subtype  string  `json:"subtype"`
	Result   string  `json:"result"`
	IsError  bool    `json:"is_error"`
	CostUSD  float64 `json:"total_cost_usd"`
	NumTurns int     `json:"num_turns"`
}

func parseResult(raw string) (*Result, error) {
	// Claude --output-format json produces a JSON array prefixed by shell output.
	// Find the JSON array start: first '[{"type":' in the output.
	idx := strings.Index(raw, `[{"type":`)
	if idx == -1 {
		// Not a JSON array — check for auth failure in raw text.
		if strings.Contains(raw, "Not logged in") || strings.Contains(raw, "authentication_failed") {
			return &Result{Status: "failed", Summary: "Claude CLI not authenticated on worker"}, nil
		}
		// Try legacy single-object parse.
		return parseLegacyResult(raw)
	}

	// Parse the JSON array.
	var items []claudeResultItem
	if err := json.Unmarshal([]byte(raw[idx:]), &items); err != nil {
		return &Result{Status: "failed", Summary: fmt.Sprintf("parse claude output: %s", truncate(err.Error(), 100))}, nil
	}

	// Find the result item (always last).
	for i := len(items) - 1; i >= 0; i-- {
		if items[i].Type != "result" {
			continue
		}
		r := &Result{CostUSD: items[i].CostUSD}

		// Check for error subtypes.
		switch items[i].Subtype {
		case "error_max_turns":
			r.Status = "failed"
			r.Summary = fmt.Sprintf("hit max turns (%d)", items[i].NumTurns)
		case "error_tool_use":
			r.Status = "failed"
			r.Summary = "tool use error"
		default:
			if items[i].IsError {
				r.Status = "failed"
				r.Summary = truncate(items[i].Result, 200)
			} else {
				// Try to extract our structured JSON from the result text.
				if parsed := extractResultJSON(items[i].Result); parsed != nil {
					parsed.CostUSD = items[i].CostUSD
					return parsed, nil
				}
				r.Status = "done"
				r.Summary = truncate(items[i].Result, 200)
			}
		}
		return r, nil
	}

	return &Result{Status: "failed", Summary: "no result item in claude output"}, nil
}

func parseLegacyResult(raw string) (*Result, error) {
	// Legacy: single {"type":"result","result":"..."} object.
	var claudeOut struct {
		Type   string `json:"type"`
		Result string `json:"result"`
	}
	if err := json.Unmarshal([]byte(raw), &claudeOut); err == nil && claudeOut.Type == "result" {
		if parsed := extractResultJSON(claudeOut.Result); parsed != nil {
			return parsed, nil
		}
	}
	return &Result{Status: "done", Summary: truncate(raw, 200)}, nil
}

func extractResultJSON(text string) *Result {
	if text == "" {
		return nil
	}
	// Find the last JSON object with a "status" field in the text.
	for i := len(text) - 1; i >= 0; i-- {
		if text[i] != '}' {
			continue
		}
		for j := i; j >= 0; j-- {
			if text[j] != '{' {
				continue
			}
			var r Result
			if err := json.Unmarshal([]byte(text[j:i+1]), &r); err == nil && r.Status != "" {
				return &r
			}
		}
	}
	return nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
