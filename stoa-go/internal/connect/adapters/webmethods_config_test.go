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

func TestWebMethodsApplyConfigTelemetry(t *testing.T) {
	var receivedPath string
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasPrefix(r.URL.Path, "/rest/apigateway/configurations/") && r.Method == http.MethodPut {
			receivedPath = r.URL.Path
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.ApplyConfig(context.Background(), server.URL, "errorProcessing", map[string]interface{}{
		"errorDestination": "designTimeErrorDestination",
		"logLevel":         "ERROR",
	})
	if err != nil {
		t.Fatalf("apply config error: %v", err)
	}
	if receivedPath != "/rest/apigateway/configurations/errorProcessing" {
		t.Errorf("unexpected path: %s", receivedPath)
	}
	if receivedPayload["logLevel"] != "ERROR" {
		t.Errorf("expected logLevel=ERROR, got %v", receivedPayload["logLevel"])
	}
}
