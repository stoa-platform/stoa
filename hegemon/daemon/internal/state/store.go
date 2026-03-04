package state

import (
	"database/sql"
	"fmt"
	"time"

	_ "modernc.org/sqlite"
)

// Store manages local SQLite state for dispatches and worker status.
type Store struct {
	db *sql.DB
}

// Dispatch represents a ticket dispatched to a worker.
type Dispatch struct {
	ID            int64
	TicketID      string
	TicketTitle   string
	Estimate      int
	InstanceLabel string
	WorkerName    string
	Status        string
	StartedAt     *time.Time
	CompletedAt   *time.Time
	ResultJSON    string
	PRNumber      int
	ErrorMessage  string
	CostUSD       float64
	CreatedAt     time.Time
}

const schema = `
CREATE TABLE IF NOT EXISTS dispatches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    ticket_title TEXT,
    estimate INTEGER DEFAULT 0,
    instance_label TEXT,
    worker_name TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    started_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    pr_number INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS worker_status (
    name TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'idle',
    current_dispatch_id INTEGER,
    last_health_at TEXT,
    last_error TEXT,
    health_fail_count INTEGER NOT NULL DEFAULT 0,
    paused_until TEXT
);

CREATE TABLE IF NOT EXISTS retry_counts (
    ticket_id TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0,
    last_failed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dispatches_ticket ON dispatches(ticket_id);
CREATE INDEX IF NOT EXISTS idx_dispatches_status ON dispatches(status);
`

// migrations adds columns that may be missing from older databases.
const migrations = `
ALTER TABLE worker_status ADD COLUMN health_fail_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE worker_status ADD COLUMN paused_until TEXT;
ALTER TABLE dispatches ADD COLUMN cost_usd REAL DEFAULT 0;
`

// New opens (or creates) the SQLite database and runs migrations.
func New(dbPath string) (*Store, error) {
	db, err := sql.Open("sqlite", dbPath+"?_pragma=journal_mode(WAL)")
	if err != nil {
		return nil, fmt.Errorf("open db: %w", err)
	}
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("init schema: %w", err)
	}
	// Best-effort migration for existing databases (columns may already exist).
	for _, stmt := range []string{
		"ALTER TABLE worker_status ADD COLUMN health_fail_count INTEGER NOT NULL DEFAULT 0",
		"ALTER TABLE worker_status ADD COLUMN paused_until TEXT",
		"ALTER TABLE dispatches ADD COLUMN cost_usd REAL DEFAULT 0",
	} {
		db.Exec(stmt) // ignore "duplicate column" errors
	}
	return &Store{db: db}, nil
}

func (s *Store) Close() error {
	return s.db.Close()
}

// CreateDispatch records a new ticket dispatch.
func (s *Store) CreateDispatch(ticketID, title string, estimate int, instanceLabel, workerName string) (int64, error) {
	res, err := s.db.Exec(
		`INSERT INTO dispatches (ticket_id, ticket_title, estimate, instance_label, worker_name, status, started_at)
		 VALUES (?, ?, ?, ?, ?, 'dispatched', datetime('now'))`,
		ticketID, title, estimate, instanceLabel, workerName,
	)
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// CompleteDispatch marks a dispatch as completed with result data.
func (s *Store) CompleteDispatch(id int64, status, resultJSON string, prNumber int, errMsg string) error {
	_, err := s.db.Exec(
		`UPDATE dispatches SET status = ?, completed_at = datetime('now'),
		 result_json = ?, pr_number = ?, error_message = ? WHERE id = ?`,
		status, resultJSON, prNumber, errMsg, id,
	)
	return err
}

// IsTicketActive checks if a ticket already has an active dispatch.
func (s *Store) IsTicketActive(ticketID string) (bool, error) {
	var count int
	err := s.db.QueryRow(
		`SELECT COUNT(*) FROM dispatches WHERE ticket_id = ? AND status IN ('queued', 'dispatched', 'running')`,
		ticketID,
	).Scan(&count)
	return count > 0, err
}

// SetWorkerBusy marks a worker as busy with a dispatch.
func (s *Store) SetWorkerBusy(name string, dispatchID int64) error {
	_, err := s.db.Exec(
		`INSERT INTO worker_status (name, status, current_dispatch_id, last_health_at)
		 VALUES (?, 'busy', ?, datetime('now'))
		 ON CONFLICT(name) DO UPDATE SET status = 'busy', current_dispatch_id = ?, last_health_at = datetime('now')`,
		name, dispatchID, dispatchID,
	)
	return err
}

// SetWorkerIdle marks a worker as idle (available for new dispatches).
func (s *Store) SetWorkerIdle(name string) error {
	_, err := s.db.Exec(
		`INSERT INTO worker_status (name, status, current_dispatch_id, last_health_at)
		 VALUES (?, 'idle', NULL, datetime('now'))
		 ON CONFLICT(name) DO UPDATE SET status = 'idle', current_dispatch_id = NULL, last_health_at = datetime('now')`,
		name,
	)
	return err
}

// SetWorkerHealth updates a worker's health check timestamp.
func (s *Store) SetWorkerHealth(name string, healthy bool, errMsg string) error {
	status := "idle"
	if !healthy {
		status = "unhealthy"
	}
	_, err := s.db.Exec(
		`INSERT INTO worker_status (name, status, last_health_at, last_error)
		 VALUES (?, ?, datetime('now'), ?)
		 ON CONFLICT(name) DO UPDATE SET
		   status = CASE WHEN worker_status.status = 'busy' THEN worker_status.status ELSE ? END,
		   last_health_at = datetime('now'),
		   last_error = ?`,
		name, status, errMsg, status, errMsg,
	)
	return err
}

// GetWorkerStatus returns the current status of a worker.
func (s *Store) GetWorkerStatus(name string) (string, error) {
	var status string
	err := s.db.QueryRow(`SELECT COALESCE(status, 'unknown') FROM worker_status WHERE name = ?`, name).Scan(&status)
	if err == sql.ErrNoRows {
		return "unknown", nil
	}
	return status, err
}

// GetRetryCount returns the number of failed dispatch attempts for a ticket.
func (s *Store) GetRetryCount(ticketID string) (int, error) {
	var count int
	err := s.db.QueryRow(`SELECT COALESCE(count, 0) FROM retry_counts WHERE ticket_id = ?`, ticketID).Scan(&count)
	if err == sql.ErrNoRows {
		return 0, nil
	}
	return count, err
}

// IncrRetryCount increments the retry counter for a ticket.
func (s *Store) IncrRetryCount(ticketID string) (int, error) {
	_, err := s.db.Exec(
		`INSERT INTO retry_counts (ticket_id, count, last_failed_at)
		 VALUES (?, 1, datetime('now'))
		 ON CONFLICT(ticket_id) DO UPDATE SET count = count + 1, last_failed_at = datetime('now')`,
		ticketID,
	)
	if err != nil {
		return 0, err
	}
	return s.GetRetryCount(ticketID)
}

// ResetRetryCount clears the retry counter for a ticket (on success).
func (s *Store) ResetRetryCount(ticketID string) error {
	_, err := s.db.Exec(`DELETE FROM retry_counts WHERE ticket_id = ?`, ticketID)
	return err
}

// IncrHealthFail increments the consecutive health failure counter for a worker.
// Returns the new count.
func (s *Store) IncrHealthFail(name string) (int, error) {
	_, err := s.db.Exec(
		`UPDATE worker_status SET health_fail_count = health_fail_count + 1 WHERE name = ?`,
		name,
	)
	if err != nil {
		return 0, err
	}
	var count int
	err = s.db.QueryRow(`SELECT health_fail_count FROM worker_status WHERE name = ?`, name).Scan(&count)
	return count, err
}

// ResetHealthFails resets the consecutive health failure counter (on successful ping).
func (s *Store) ResetHealthFails(name string) error {
	_, err := s.db.Exec(
		`UPDATE worker_status SET health_fail_count = 0, paused_until = NULL WHERE name = ?`,
		name,
	)
	return err
}

// SetWorkerPaused marks a worker as paused until the given time.
func (s *Store) SetWorkerPaused(name string, until time.Time) error {
	_, err := s.db.Exec(
		`UPDATE worker_status SET status = 'paused', paused_until = ? WHERE name = ?`,
		until.UTC().Format("2006-01-02 15:04:05"), name,
	)
	return err
}

// IsWorkerPaused checks if a worker is currently paused. Returns false if not paused or pause expired.
func (s *Store) IsWorkerPaused(name string) (bool, error) {
	var pausedUntil sql.NullString
	err := s.db.QueryRow(`SELECT paused_until FROM worker_status WHERE name = ?`, name).Scan(&pausedUntil)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if !pausedUntil.Valid || pausedUntil.String == "" {
		return false, nil
	}
	t, err := time.Parse("2006-01-02 15:04:05", pausedUntil.String)
	if err != nil {
		return false, nil
	}
	return time.Now().UTC().Before(t), nil
}

// GetWorkerHealthStats returns per-worker health stats for metrics export.
type WorkerHealthStats struct {
	Name           string
	Status         string
	HealthFailCount int
	PausedUntil    *time.Time
	LastHealthAt   *time.Time
	LastError      string
}

func (s *Store) GetAllWorkerStats() ([]WorkerHealthStats, error) {
	rows, err := s.db.Query(
		`SELECT name, status, health_fail_count, paused_until, last_health_at, COALESCE(last_error, '')
		 FROM worker_status ORDER BY name`,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var stats []WorkerHealthStats
	for rows.Next() {
		var ws WorkerHealthStats
		var pausedUntil, lastHealthAt sql.NullString
		if err := rows.Scan(&ws.Name, &ws.Status, &ws.HealthFailCount, &pausedUntil, &lastHealthAt, &ws.LastError); err != nil {
			return nil, err
		}
		if pausedUntil.Valid {
			t, _ := time.Parse("2006-01-02 15:04:05", pausedUntil.String)
			ws.PausedUntil = &t
		}
		if lastHealthAt.Valid {
			t, _ := time.Parse("2006-01-02 15:04:05", lastHealthAt.String)
			ws.LastHealthAt = &t
		}
		stats = append(stats, ws)
	}
	return stats, rows.Err()
}

// GetQueueDepth returns the number of active (non-completed) dispatches.
func (s *Store) GetQueueDepth() (int, error) {
	var count int
	err := s.db.QueryRow(
		`SELECT COUNT(*) FROM dispatches WHERE status IN ('queued', 'dispatched', 'running')`,
	).Scan(&count)
	return count, err
}

// CleanStaleDispatches marks dispatches older than maxAge as 'stale' and releases workers.
func (s *Store) CleanStaleDispatches(maxAge time.Duration) (int64, error) {
	cutoff := time.Now().Add(-maxAge).UTC().Format("2006-01-02 15:04:05")
	res, err := s.db.Exec(
		`UPDATE dispatches SET status = 'stale', completed_at = datetime('now'), error_message = 'auto-cleaned: stale dispatch'
		 WHERE status IN ('dispatched', 'running') AND started_at < ?`,
		cutoff,
	)
	if err != nil {
		return 0, err
	}
	// Release workers that were busy on stale dispatches.
	s.db.Exec(`UPDATE worker_status SET status = 'idle', current_dispatch_id = NULL
		WHERE current_dispatch_id IN (SELECT id FROM dispatches WHERE status = 'stale')`)
	return res.RowsAffected()
}

// RecordCost updates the cost for a completed dispatch.
func (s *Store) RecordCost(dispatchID int64, costUSD float64) error {
	_, err := s.db.Exec(`UPDATE dispatches SET cost_usd = ? WHERE id = ?`, costUSD, dispatchID)
	return err
}

// GetDailyCost returns the total cost in USD for dispatches completed today (UTC).
func (s *Store) GetDailyCost() (float64, error) {
	var total sql.NullFloat64
	err := s.db.QueryRow(
		`SELECT SUM(cost_usd) FROM dispatches WHERE date(completed_at) = date('now')`,
	).Scan(&total)
	if !total.Valid {
		return 0, err
	}
	return total.Float64, err
}

// DailyCostByWorker holds per-worker cost data for metrics export.
type DailyCostByWorker struct {
	WorkerName string
	CostUSD    float64
}

// GetDailyCostByWorker returns cost breakdown per worker for today (UTC).
func (s *Store) GetDailyCostByWorker() ([]DailyCostByWorker, error) {
	rows, err := s.db.Query(
		`SELECT worker_name, COALESCE(SUM(cost_usd), 0) FROM dispatches
		 WHERE date(completed_at) = date('now') GROUP BY worker_name ORDER BY worker_name`,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var costs []DailyCostByWorker
	for rows.Next() {
		var c DailyCostByWorker
		if err := rows.Scan(&c.WorkerName, &c.CostUSD); err != nil {
			return nil, err
		}
		costs = append(costs, c)
	}
	return costs, rows.Err()
}

// GetActiveDispatches returns all dispatches currently in progress.
func (s *Store) GetActiveDispatches() ([]Dispatch, error) {
	rows, err := s.db.Query(
		`SELECT id, ticket_id, ticket_title, estimate, instance_label, worker_name, status, started_at, created_at
		 FROM dispatches WHERE status IN ('dispatched', 'running') ORDER BY created_at`,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var dispatches []Dispatch
	for rows.Next() {
		var d Dispatch
		var startedAt, createdAt sql.NullString
		if err := rows.Scan(&d.ID, &d.TicketID, &d.TicketTitle, &d.Estimate,
			&d.InstanceLabel, &d.WorkerName, &d.Status, &startedAt, &createdAt); err != nil {
			return nil, err
		}
		if startedAt.Valid {
			t, _ := time.Parse("2006-01-02 15:04:05", startedAt.String)
			d.StartedAt = &t
		}
		if createdAt.Valid {
			t, _ := time.Parse("2006-01-02 15:04:05", createdAt.String)
			d.CreatedAt = t
		}
		dispatches = append(dispatches, d)
	}
	return dispatches, rows.Err()
}
