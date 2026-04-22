package adapters

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWebMethodsTelemetrySubscribe(t *testing.T) {
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/rest/apigateway/subscriptions" && r.Method == http.MethodPost {
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "sub-123"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	subID, err := adapter.SubscribeTelemetry(context.Background(), server.URL, "http://stoa-connect:8090/webhook/events")
	if err != nil {
		t.Fatalf("subscribe telemetry error: %v", err)
	}
	if subID != "sub-123" {
		t.Errorf("expected subscription ID sub-123, got %s", subID)
	}
	if receivedPayload["eventType"] != "transactionalEvents" {
		t.Errorf("expected eventType=transactionalEvents, got %v", receivedPayload["eventType"])
	}
	if receivedPayload["callbackURL"] != "http://stoa-connect:8090/webhook/events" {
		t.Errorf("unexpected callbackURL: %v", receivedPayload["callbackURL"])
	}
}

func TestWebMethodsTelemetryPoll(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasPrefix(r.URL.Path, "/rest/apigateway/transactionalEvents") {
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"transactionalEvents": []map[string]interface{}{
					{
						"eventTimestamp": "1711500000000",
						"apiId":          "api-1",
						"apiName":        "Petstore",
						"httpMethod":     "GET",
						"resourcePath":   "/pets",
						"status":         200,
						"totalTime":      42,
						"tenantId":       "tenant-acme",
					},
					{
						"eventTimestamp": "1711500001000",
						"apiId":          "api-2",
						"apiName":        "Orders",
						"httpMethod":     "POST",
						"resourcePath":   "/orders",
						"status":         201,
						"totalTime":      150,
					},
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	events, err := adapter.PollTelemetry(context.Background(), server.URL, 1711500000000, 1711500002000)
	if err != nil {
		t.Fatalf("poll telemetry error: %v", err)
	}
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}
	if events[0].Method != "GET" || events[0].Path != "/pets" || events[0].Status != 200 {
		t.Errorf("event 0 mismatch: %+v", events[0])
	}
	if events[0].TenantID != "tenant-acme" {
		t.Errorf("expected tenant-acme, got %s", events[0].TenantID)
	}
	if events[1].LatencyMs != 150 {
		t.Errorf("expected latency 150ms, got %d", events[1].LatencyMs)
	}
}

func TestWebMethodsEventNormalization(t *testing.T) {
	raw := wmTransactionalEvent{
		EventTimestamp: "1711500000000",
		APIID:          "api-42",
		APIName:        "Petstore",
		HTTPMethod:     "DELETE",
		ResourcePath:   "/pets/123",
		Status:         204,
		TotalTime:      7,
		TenantID:       "tenant-xyz",
	}

	event := NormalizeEvent(raw)
	if event.Method != "DELETE" {
		t.Errorf("expected DELETE, got %s", event.Method)
	}
	if event.Path != "/pets/123" {
		t.Errorf("expected /pets/123, got %s", event.Path)
	}
	if event.Status != 204 {
		t.Errorf("expected 204, got %d", event.Status)
	}
	if event.LatencyMs != 7 {
		t.Errorf("expected 7ms, got %d", event.LatencyMs)
	}
	if event.TenantID != "tenant-xyz" {
		t.Errorf("expected tenant-xyz, got %s", event.TenantID)
	}
	if event.APIID != "api-42" {
		t.Errorf("expected api-42, got %s", event.APIID)
	}
	if event.Timestamp.UnixMilli() != 1711500000000 {
		t.Errorf("unexpected timestamp: %v", event.Timestamp)
	}

	// Test fallback: operationName used when httpMethod is empty
	rawNoMethod := wmTransactionalEvent{
		OperationName: "getPets",
		ResourcePath:  "/pets",
		Status:        200,
	}
	event2 := NormalizeEvent(rawNoMethod)
	if event2.Method != "getPets" {
		t.Errorf("expected operationName fallback, got %s", event2.Method)
	}
}
