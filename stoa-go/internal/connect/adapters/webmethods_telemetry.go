package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// NormalizeEvent converts a raw webMethods transactional event to the common schema.
func NormalizeEvent(raw wmTransactionalEvent) TelemetryEvent {
	var ts time.Time
	if raw.EventTimestamp != "" {
		if ms, err := parseEpochMillis(raw.EventTimestamp); err == nil {
			ts = time.UnixMilli(ms)
		}
	}
	if ts.IsZero() {
		ts = time.Now().UTC()
	}

	method := raw.HTTPMethod
	if method == "" {
		method = raw.OperationName
	}

	return TelemetryEvent{
		Timestamp: ts,
		Method:    method,
		Path:      raw.ResourcePath,
		Status:    raw.Status,
		LatencyMs: raw.TotalTime,
		TenantID:  raw.TenantID,
		APIName:   raw.APIName,
		APIID:     raw.APIID,
	}
}

// parseEpochMillis parses a string epoch timestamp in milliseconds.
func parseEpochMillis(s string) (int64, error) {
	var ms int64
	_, err := fmt.Sscanf(s, "%d", &ms)
	return ms, err
}

// SubscribeTelemetry creates a push subscription on webMethods to receive transactional events.
// callbackURL is the URL where webMethods will POST events (e.g., http://stoa-connect:8090/webhook/events).
// Returns the subscription ID. Trial license resets lose subscriptions — recreate on agent restart.
func (w *WebMethodsAdapter) SubscribeTelemetry(ctx context.Context, adminURL string, callbackURL string) (string, error) {
	payload := map[string]interface{}{
		"eventType":   "transactionalEvents",
		"callbackURL": callbackURL,
		"active":      true,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("marshal subscription: %w", err)
	}

	subURL := adminURL + "/rest/apigateway/subscriptions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, subURL, bytes.NewReader(data))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("create telemetry subscription: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("subscription create failed (%d): %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return "", fmt.Errorf("decode subscription response: %w", err)
	}

	return result.ID, nil
}

// PollTelemetry fetches transactional events from webMethods for the given time range.
// fromDate and toDate are epoch milliseconds. Used as fallback when push subscription fails.
func (w *WebMethodsAdapter) PollTelemetry(ctx context.Context, adminURL string, fromDate, toDate int64) ([]TelemetryEvent, error) {
	pollURL := fmt.Sprintf("%s/rest/apigateway/transactionalEvents?fromDate=%d&toDate=%d&size=100",
		adminURL, fromDate, toDate)

	body, err := w.doGet(ctx, pollURL)
	if err != nil {
		return nil, fmt.Errorf("poll telemetry events: %w", err)
	}

	var resp struct {
		TransactionalEvents []wmTransactionalEvent `json:"transactionalEvents"`
	}
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode telemetry events: %w", err)
	}

	events := make([]TelemetryEvent, 0, len(resp.TransactionalEvents))
	for _, raw := range resp.TransactionalEvents {
		events = append(events, NormalizeEvent(raw))
	}

	return events, nil
}

// HandleWebhookEvents parses a batch of webMethods push events from a webhook POST body.
func HandleWebhookEvents(body []byte) ([]TelemetryEvent, error) {
	var payload struct {
		Events []wmTransactionalEvent `json:"events"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("decode webhook events: %w", err)
	}

	events := make([]TelemetryEvent, 0, len(payload.Events))
	for _, raw := range payload.Events {
		events = append(events, NormalizeEvent(raw))
	}

	return events, nil
}
