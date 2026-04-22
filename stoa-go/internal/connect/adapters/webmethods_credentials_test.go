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

func TestWebMethodsInjectCredentialsWithAPIAssociation(t *testing.T) {
	var appCreated bool
	var associatedPath string
	var associatedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/applications" && r.Method == http.MethodPost:
			appCreated = true
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "app-42"})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-99", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/applications/") && strings.HasSuffix(r.URL.Path, "/apis") && r.Method == http.MethodPost:
			associatedPath = r.URL.Path
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &associatedPayload)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.InjectCredentials(context.Background(), server.URL, []Credential{
		{ConsumerID: "user-1", APIName: "Petstore", Key: "key-abc", AuthType: "key-auth"},
	})
	if err != nil {
		t.Fatalf("inject credentials error: %v", err)
	}
	if !appCreated {
		t.Error("expected application to be created")
	}
	if associatedPath != "/rest/apigateway/applications/app-42/apis" {
		t.Errorf("expected association to app-42, got path: %s", associatedPath)
	}
	apiIDs, ok := associatedPayload["apiIDs"].([]interface{})
	if !ok || len(apiIDs) != 1 || apiIDs[0] != "api-99" {
		t.Errorf("expected apiIDs=[api-99], got %v", associatedPayload["apiIDs"])
	}
}
