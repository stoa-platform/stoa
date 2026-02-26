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
	Status       string `json:"status"`        // done, blocked, failed
	PRNumber     int    `json:"pr_number"`
	Branch       string `json:"branch"`
	FilesChanged int    `json:"files_changed"`
	Summary      string `json:"summary"`
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
	prompt := buildPrompt(ticketID, title, description)

	// Write prompt to a temp file on the remote, then run claude with it.
	// This avoids shell quoting issues with multi-line prompts containing special characters.
	promptFile := fmt.Sprintf("/tmp/hegemon-prompt-%s.txt", ticketID)
	if err := e.writeRemoteFile(client, promptFile, prompt); err != nil {
		return nil, "", fmt.Errorf("write prompt file: %w", err)
	}

	// Build the remote command.
	// bash -l sources .profile which loads Infisical secrets.
	cmd := fmt.Sprintf(
		`bash -l -c 'cd %s && git checkout %s && git pull --ff-only && claude -p "$(cat %s)" --output-format json --max-turns %d --verbose 2>/dev/null; rm -f %s'`,
		e.repoPath, e.branch, promptFile, maxTurns, promptFile,
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

func turnsForEstimate(estimate int) int {
	switch {
	case estimate <= 3:
		return 20
	case estimate <= 5:
		return 30
	case estimate <= 8:
		return 40
	default:
		return 50
	}
}

func buildPrompt(ticketID, title, description string) string {
	return fmt.Sprintf(`You are HEGEMON worker executing ticket %s: %s

## Ticket Description
%s

## Instructions
1. Create a feature branch: feat/%s-<short-description>
2. Implement the changes following CLAUDE.md conventions
3. Run the relevant quality gate (lint, test, format)
4. Commit with conventional message including ticket ID
5. Push the branch and create a PR via gh pr create
6. Do NOT merge the PR — leave it for human review (Ask mode)

## Constraints
- Maximum 300 LOC changed
- All tests must pass
- No secrets in code
- Follow existing code patterns

## Output
End your response with a JSON block:
{"status": "done|blocked|failed", "pr_number": 0, "branch": "", "files_changed": 0, "summary": ""}`,
		ticketID, title, description, strings.ToLower(ticketID))
}

func shellQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "'\"'\"'") + "'"
}

func parseResult(raw string) (*Result, error) {
	// Claude --output-format json wraps output as {"type":"result","result":"..."}
	var claudeOut struct {
		Type   string `json:"type"`
		Result string `json:"result"`
	}
	if err := json.Unmarshal([]byte(raw), &claudeOut); err == nil && claudeOut.Type == "result" {
		// Try to extract JSON from the result text.
		return extractResultJSON(claudeOut.Result)
	}
	// Fallback: try direct parse (might be raw JSON).
	return extractResultJSON(raw)
}

func extractResultJSON(text string) (*Result, error) {
	// Find the last JSON object in the text.
	idx := strings.LastIndex(text, "{")
	if idx == -1 {
		return &Result{Status: "done", Summary: truncate(text, 200)}, nil
	}

	// Try to parse from each { found, going backwards.
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
				return &r, nil
			}
		}
	}

	return &Result{Status: "done", Summary: truncate(text, 200)}, nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
