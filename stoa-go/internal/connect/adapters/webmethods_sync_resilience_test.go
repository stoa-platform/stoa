// regression for CAB-1944 (GO-1 audit C.2 / C.4 / C.5): harden
// SyncRoutes against 409 conflicts (POST→re-list→PUT fallback, PUT 409
// tracked) and prevent single-route failures (deactivate / verifyActivate)
// from halting the batch. See BUG-REPORT-GO-1.md.
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
// C.2: 409 Conflict handling + POST→PUT fallback
// ---------------------------------------------------------------------------

// TestWebMethodsSyncRoutes_409OnPostFallbackToPut — C.2 happy path: initial
// POST returns 409 because the API exists out-of-band; adapter re-lists,
// finds the ID, issues PUT once, which succeeds. Route must be classified
// applied (no entry in FailedRoutes) and SpecHash recorded.
func TestWebMethodsSyncRoutes_409OnPostFallbackToPut(t *testing.T) {
	var postCount, putCount, listCount int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			n := atomic.AddInt64(&listCount, 1)
			if n == 1 {
				// First list: empty → adapter chooses POST
				_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
			} else {
				// Re-list after 409: API now visible
				_ = json.NewEncoder(w).Encode(map[string]interface{}{
					"apiResponse": []map[string]interface{}{
						{"id": "wm-found-1", "apiName": "stoa-pets", "isActive": true},
					},
				})
			}
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			atomic.AddInt64(&postCount, 1)
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(`{"error":"already exists"}`))
		case r.URL.Path == "/rest/apigateway/apis/wm-found-1" && r.Method == http.MethodPut:
			atomic.AddInt64(&putCount, 1)
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "wm-found-1"})
		case r.URL.Path == "/rest/apigateway/apis/wm-found-1" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "wm-found-1", "apiName": "stoa-pets", "isActive": true,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	result, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "pets", DeploymentID: "dep-1", Activated: true, SpecHash: "h-1"},
	})

	if err != nil {
		t.Fatalf("expected success after POST→PUT fallback, got err: %v", err)
	}
	if _, failed := result.FailedRoutes["dep-1"]; failed {
		t.Errorf("dep-1 should not be in FailedRoutes, got %v", result.FailedRoutes)
	}
	if got := atomic.LoadInt64(&postCount); got != 1 {
		t.Errorf("POST count: got %d, want 1", got)
	}
	if got := atomic.LoadInt64(&putCount); got != 1 {
		t.Errorf("PUT fallback count: got %d, want 1", got)
	}
	// Hash recorded after final success
	if h, ok := adapter.hashesGet("stoa-pets"); !ok || h != "h-1" {
		t.Errorf("expected hash h-1 to be recorded, got %q (ok=%v)", h, ok)
	}
}

// TestWebMethodsSyncRoutes_409OnPutTracked — C.2: a 409 returned by the
// initial PUT (existing API, version/content conflict) must be tracked in
// FailedRoutes, must NOT update the hash, and must not halt the batch.
func TestWebMethodsSyncRoutes_409OnPutTracked(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "wm-1", "apiName": "stoa-conflict", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/wm-1" && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(`{"error":"version mismatch"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	result, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "conflict", DeploymentID: "dep-conflict", Activated: true, SpecHash: "h-should-not-stick"},
	})

	if err == nil {
		t.Fatal("expected error for 409 on PUT")
	}
	msg, failed := result.FailedRoutes["dep-conflict"]
	if !failed {
		t.Fatalf("dep-conflict should be in FailedRoutes, got %v", result.FailedRoutes)
	}
	if !strings.Contains(msg, "409") {
		t.Errorf("FailedRoutes message should mention 409, got %q", msg)
	}
	// Hash must NOT be recorded
	if h, ok := adapter.hashesGet("stoa-conflict"); ok {
		t.Errorf("hash should not be recorded after 409 on PUT, got %q", h)
	}
}

// TestWebMethodsSyncRoutes_409PostAPINotInList — C.2 ghost conflict: POST
// returns 409 but the re-list does not contain the API. No retry happens;
// the route is marked failed.
func TestWebMethodsSyncRoutes_409PostAPINotInList(t *testing.T) {
	var postCount int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			// Always empty → re-list will also be empty (ghost).
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			atomic.AddInt64(&postCount, 1)
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(`{"error":"phantom"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	result, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "ghost", DeploymentID: "dep-ghost", Activated: true, SpecHash: "h-x"},
	})

	if err == nil {
		t.Fatal("expected error for ghost 409")
	}
	msg, failed := result.FailedRoutes["dep-ghost"]
	if !failed {
		t.Fatalf("dep-ghost should be in FailedRoutes, got %v", result.FailedRoutes)
	}
	if !strings.Contains(msg, "ghost") && !strings.Contains(msg, "not present") {
		t.Errorf("FailedRoutes message should describe the ghost case, got %q", msg)
	}
	if got := atomic.LoadInt64(&postCount); got != 1 {
		t.Errorf("expected exactly 1 POST (no retry loop), got %d", got)
	}
	if h, ok := adapter.hashesGet("stoa-ghost"); ok {
		t.Errorf("hash must not be set on ghost 409, got %q", h)
	}
}

// TestWebMethodsSyncRoutes_409DoesNotUpdateHash — C.2: after a 409 on PUT,
// the SpecHash must not be recorded, so the next sync cycle retries with
// the same hash (proving the hash gate was not poisoned on failure).
func TestWebMethodsSyncRoutes_409DoesNotUpdateHash(t *testing.T) {
	var putCount int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "wm-2", "apiName": "stoa-loop", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/wm-2" && r.Method == http.MethodPut:
			atomic.AddInt64(&putCount, 1)
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(`{"error":"conflict"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	routes := []Route{
		{Name: "loop", DeploymentID: "dep-loop", Activated: true, SpecHash: "same-hash"},
	}

	_, _ = adapter.SyncRoutes(context.Background(), server.URL, routes)
	_, _ = adapter.SyncRoutes(context.Background(), server.URL, routes)

	if got := atomic.LoadInt64(&putCount); got != 2 {
		t.Errorf("expected 2 PUTs (hash never poisoned → re-attempt), got %d", got)
	}
}

// ---------------------------------------------------------------------------
// C.4: verifyAndActivate failure must not halt the batch
// ---------------------------------------------------------------------------

// TestWebMethodsSyncRoutes_VerifyActivateFailureDoesNotHaltBatch — C.4:
// route 1's activation fails; route 2 must still be processed (POST +
// verify + activate happy path) instead of being silently skipped.
func TestWebMethodsSyncRoutes_VerifyActivateFailureDoesNotHaltBatch(t *testing.T) {
	var route2Created bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			// Only route 1 pre-exists, so route 1 = PUT, route 2 = POST.
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "wm-r1", "apiName": "stoa-r1", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/wm-r1" && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "wm-r1"})
		case r.URL.Path == "/rest/apigateway/apis/wm-r1" && r.Method == http.MethodGet:
			// Route 1 reported inactive → triggers activate path.
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "wm-r1", "apiName": "stoa-r1", "isActive": false,
			})
		case r.URL.Path == "/rest/apigateway/apis/wm-r1/activate" && r.Method == http.MethodPut:
			// Route 1's activation fails.
			w.WriteHeader(http.StatusInternalServerError)
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			// Route 2 created successfully.
			route2Created = true
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "wm-r2"})
		case r.URL.Path == "/rest/apigateway/apis/wm-r2" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "wm-r2", "apiName": "stoa-r2", "isActive": true,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	result, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "r1", DeploymentID: "dep-r1", Activated: true, SpecHash: "h1"},
		{Name: "r2", DeploymentID: "dep-r2", Activated: true, SpecHash: "h2"},
	})

	if err == nil {
		t.Fatal("expected aggregated error (route 1 activation failed)")
	}
	if !route2Created {
		t.Error("route 2 POST must still happen despite route 1 activation failure (C.4)")
	}
	if _, failed := result.FailedRoutes["dep-r1"]; !failed {
		t.Errorf("dep-r1 should be in FailedRoutes, got %v", result.FailedRoutes)
	}
	if _, leaked := result.FailedRoutes["dep-r2"]; leaked {
		t.Errorf("dep-r2 should NOT be in FailedRoutes (it succeeded), got %v", result.FailedRoutes)
	}
	// Route 1 hash must stay untouched (activation failed); route 2 recorded.
	if _, ok := adapter.hashesGet("stoa-r1"); ok {
		t.Error("stoa-r1 hash must not be recorded on activation failure")
	}
	if h, ok := adapter.hashesGet("stoa-r2"); !ok || h != "h2" {
		t.Errorf("stoa-r2 hash should be h2, got %q (ok=%v)", h, ok)
	}
}

// ---------------------------------------------------------------------------
// C.5: DeactivateAPI failure must not halt the batch
// ---------------------------------------------------------------------------

// TestWebMethodsSyncRoutes_DeactivateFailureDoesNotHaltBatch — C.5: the
// first route is a deactivation that fails; the second route must still be
// synced (POST + verify). Prior to the fix, a single deactivate error
// aborted the whole batch with an early return.
func TestWebMethodsSyncRoutes_DeactivateFailureDoesNotHaltBatch(t *testing.T) {
	var createCalled bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			// Route 1 ("stale") exists; route 2 ("new") does not.
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "wm-stale", "apiName": "stoa-stale", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/wm-stale/deactivate" && r.Method == http.MethodPut:
			// Deactivation fails.
			w.WriteHeader(http.StatusInternalServerError)
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			createCalled = true
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "wm-new"})
		case r.URL.Path == "/rest/apigateway/apis/wm-new" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "wm-new", "apiName": "stoa-new", "isActive": true,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	result, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "stale", DeploymentID: "dep-stale", Activated: false},
		{Name: "new", DeploymentID: "dep-new", Activated: true},
	})

	if err == nil {
		t.Fatal("expected aggregated error (deactivate failed)")
	}
	if !createCalled {
		t.Error("route 2 (new) POST must still happen despite route 1 deactivate failure (C.5)")
	}
	if _, failed := result.FailedRoutes["dep-stale"]; !failed {
		t.Errorf("dep-stale should be in FailedRoutes, got %v", result.FailedRoutes)
	}
	if _, leaked := result.FailedRoutes["dep-new"]; leaked {
		t.Errorf("dep-new should NOT be in FailedRoutes (it succeeded), got %v", result.FailedRoutes)
	}
}
