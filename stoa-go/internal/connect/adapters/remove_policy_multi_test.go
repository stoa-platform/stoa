package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

// ---------------------------------------------------------------------------
// C.1: RemovePolicy must delete ALL matching policy actions / plugins,
// not just the first one.
// Pre-GO-1 the loop returned after the first delete, leaving duplicates
// silently active on the gateway (security-functional bug).
// ---------------------------------------------------------------------------

// TestWebMethodsRemovePolicy_MultipleMatches — 3 policy actions share the
// same templateKey. All 3 must be deleted; RemovePolicy must succeed.
func TestWebMethodsRemovePolicy_MultipleMatches(t *testing.T) {
	var deleted []string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-1", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-1/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{"id": "pa-cors-a", "templateKey": "corsPolicy", "policyActionName": "cors-a"},
					{"id": "pa-cors-b", "templateKey": "corsPolicy", "policyActionName": "cors-b"},
					{"id": "pa-cors-c", "templateKey": "corsPolicy", "policyActionName": "cors-c"},
					{"id": "pa-keep", "templateKey": "throttlingPolicy", "policyActionName": "keep"},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/policyActions/") && r.Method == http.MethodDelete:
			deleted = append(deleted, strings.TrimPrefix(r.URL.Path, "/rest/apigateway/policyActions/"))
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	if err := adapter.RemovePolicy(context.Background(), server.URL, "Petstore", "cors"); err != nil {
		t.Fatalf("remove policy error: %v", err)
	}

	expectedDeleted := map[string]bool{"pa-cors-a": true, "pa-cors-b": true, "pa-cors-c": true}
	if len(deleted) != len(expectedDeleted) {
		t.Fatalf("expected %d deletions, got %d (%v)", len(expectedDeleted), len(deleted), deleted)
	}
	for _, d := range deleted {
		if !expectedDeleted[d] {
			t.Errorf("unexpected delete: %s", d)
		}
	}
	// pa-keep (throttlingPolicy) must NOT be deleted
	for _, d := range deleted {
		if d == "pa-keep" {
			t.Error("pa-keep must not be deleted (different templateKey)")
		}
	}
}

// TestWebMethodsRemovePolicy_PartialFailure — 3 matches, the second DELETE
// returns 500. Adapter must attempt all 3, then return an error wrapping
// the last failure with a "removed X/N" prefix.
func TestWebMethodsRemovePolicy_PartialFailure(t *testing.T) {
	var deleteAttempts int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-1", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-1/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{"id": "pa-1", "templateKey": "corsPolicy"},
					{"id": "pa-2", "templateKey": "corsPolicy"},
					{"id": "pa-3", "templateKey": "corsPolicy"},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/policyActions/") && r.Method == http.MethodDelete:
			n := atomic.AddInt64(&deleteAttempts, 1)
			if n == 2 {
				// Second delete fails
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.RemovePolicy(context.Background(), server.URL, "Petstore", "cors")

	if err == nil {
		t.Fatal("expected error on partial delete failure")
	}
	// All 3 deletions must have been attempted
	if got := atomic.LoadInt64(&deleteAttempts); got != 3 {
		t.Errorf("expected 3 delete attempts, got %d", got)
	}
	// Error message must include the "2/3" progress (2 succeeded out of 3)
	if !strings.Contains(err.Error(), "2/3") {
		t.Errorf("error should contain '2/3' count, got: %v", err)
	}
}

// TestWebMethodsRemovePolicy_NoMatchesStillIdempotent — sanity check: zero
// matching templates means RemovePolicy returns nil and performs 0 DELETEs.
func TestWebMethodsRemovePolicy_NoMatchesStillIdempotent(t *testing.T) {
	var deleteCount int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-1", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-1/policyActions" && r.Method == http.MethodGet:
			// No corsPolicy present
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{"id": "pa-other", "templateKey": "throttlingPolicy"},
				},
			})
		case r.Method == http.MethodDelete:
			atomic.AddInt64(&deleteCount, 1)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	if err := adapter.RemovePolicy(context.Background(), server.URL, "Petstore", "cors"); err != nil {
		t.Fatalf("expected nil on no match, got: %v", err)
	}
	if got := atomic.LoadInt64(&deleteCount); got != 0 {
		t.Errorf("expected 0 DELETEs, got %d", got)
	}
}

// TestKongRemovePolicy_MultipleMatches — 2 Kong plugins with the same name
// (e.g. two rate-limiting plugins racing on the same service). RemovePolicy
// must delete both.
func TestKongRemovePolicy_MultipleMatches(t *testing.T) {
	var deleted []string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/services/petstore/plugins" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{"id": "plug-1", "name": "rate-limiting"},
					{"id": "plug-2", "name": "rate-limiting"},
					{"id": "plug-3", "name": "cors"}, // must be preserved
				},
			})
		case strings.HasPrefix(r.URL.Path, "/plugins/") && r.Method == http.MethodDelete:
			deleted = append(deleted, strings.TrimPrefix(r.URL.Path, "/plugins/"))
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{})
	if err := adapter.RemovePolicy(context.Background(), server.URL, "petstore", "rate-limiting"); err != nil {
		t.Fatalf("remove policy error: %v", err)
	}

	if len(deleted) != 2 {
		t.Fatalf("expected 2 deletions, got %d (%v)", len(deleted), deleted)
	}
	expected := map[string]bool{"plug-1": true, "plug-2": true}
	for _, d := range deleted {
		if !expected[d] {
			t.Errorf("unexpected or duplicate delete: %s", d)
		}
		if d == "plug-3" {
			t.Error("plug-3 (cors) must not be deleted")
		}
	}
}

// TestKongRemovePolicy_PartialFailure — 2 matches, second DELETE returns
// 500. RemovePolicy must attempt both and return a wrapping error.
func TestKongRemovePolicy_PartialFailure(t *testing.T) {
	var deleteAttempts int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/services/petstore/plugins" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{"id": "plug-1", "name": "rate-limiting"},
					{"id": "plug-2", "name": "rate-limiting"},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/plugins/") && r.Method == http.MethodDelete:
			n := atomic.AddInt64(&deleteAttempts, 1)
			if n == 2 {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{})
	err := adapter.RemovePolicy(context.Background(), server.URL, "petstore", "rate-limiting")

	if err == nil {
		t.Fatal("expected error on partial failure")
	}
	if got := atomic.LoadInt64(&deleteAttempts); got != 2 {
		t.Errorf("expected 2 delete attempts, got %d", got)
	}
	if !strings.Contains(err.Error(), "1/2") {
		t.Errorf("error should contain '1/2' count, got: %v", err)
	}
}
