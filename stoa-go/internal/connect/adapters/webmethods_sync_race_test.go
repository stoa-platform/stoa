// regression for CAB-1944 (GO-1 audit C.3 / C.6): per-call SyncResult
// replaces the mutable FailedRoutes field on WebMethodsAdapter; syncedHashes
// is mutex-guarded. Without these tests, the concurrent polling + SSE paths
// race on the shared adapter and produce `concurrent map read/write` panics
// and mis-acked routes (see BUG-REPORT-GO-1.md).
package adapters

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
)

// Regression for C.3 (BUG-REPORT-GO-1.md): syncedHashes must be safe for
// concurrent reads and writes. Prior to the fix the map was written without
// a mutex and tripped Go's -race detector (and occasionally triggered
// `fatal error: concurrent map read and map write`).
//
// Exercised with `go test ./... -race`.
func TestWebMethodsSyncedHashes_ConcurrentReadWrite(t *testing.T) {
	t.Parallel()

	adapter := NewWebMethodsAdapter(AdapterConfig{})

	const workers = 50
	const iterations = 200

	var wg sync.WaitGroup
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(id int) {
			defer wg.Done()
			name := fmt.Sprintf("route-%d", id%7) // intentional overlap
			for j := 0; j < iterations; j++ {
				_, _ = adapter.hashesGet(name)
				adapter.hashesSet(name, fmt.Sprintf("hash-%d-%d", id, j))
			}
		}(i)
	}
	wg.Wait()
}

// Regression for C.3: SyncRoutes itself must not race on per-call state. Two
// concurrent batches hit a shared httptest server; each call must return an
// independent SyncResult and the adapter must not panic or produce a
// `concurrent map write` runtime error under -race.
func TestWebMethodsSyncRoutes_ConcurrentCalls(t *testing.T) {
	t.Parallel()

	var postCount int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			id := atomic.AddInt64(&postCount, 1)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": fmt.Sprintf("new-%d", id)})
		case r.Method == http.MethodGet:
			// verify path: respond active
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "ok", "apiName": "stoa", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})

	const concurrent = 10
	const routesPerCall = 10

	errs := make(chan error, concurrent)
	var wg sync.WaitGroup
	wg.Add(concurrent)
	for i := 0; i < concurrent; i++ {
		go func(caller int) {
			defer wg.Done()
			routes := make([]Route, routesPerCall)
			for j := range routes {
				routes[j] = Route{
					Name:       fmt.Sprintf("c%d-r%d", caller, j),
					BackendURL: "http://example.com",
					PathPrefix: "/p",
					Methods:    []string{"GET"},
					Activated:  true,
				}
			}
			_, err := adapter.SyncRoutes(context.Background(), server.URL, routes)
			errs <- err
		}(i)
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Errorf("concurrent SyncRoutes returned error: %v", err)
		}
	}
}

// Regression for C.6: before the fix, the polling goroutine and the SSE
// goroutine shared a mutable FailedRoutes map on the adapter. When SSE fired
// mid-batch, it would `w.FailedRoutes = make(map[string]string)` and wipe
// the polling batch's in-flight error tracking, causing failed routes to be
// classified `applied` in the CP ack.
//
// Post-fix, each SyncRoutes call owns its own SyncResult.FailedRoutes. We
// prove the isolation by running concurrent calls where one batch has a
// failing route (dep-FAIL) while another batch is all-success, and verify
// the failing call's FailedRoutes is neither empty nor leaked to the other
// call's result.
func TestWebMethodsSyncRoutes_PollingSSEIsolation(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			body, _ := readBody(r)
			var payload map[string]interface{}
			_ = json.Unmarshal(body, &payload)
			name, _ := payload["apiName"].(string)
			if name == "stoa-FAIL" {
				w.WriteHeader(http.StatusInternalServerError)
				_, _ = w.Write([]byte(`{"error":"forced"}`))
				return
			}
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "ok-" + name})
		case r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "x", "apiName": "stoa", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})

	// Polling-like batch: includes a failing route (dep-FAIL).
	batchPolling := []Route{
		{Name: "good-a", DeploymentID: "dep-ok-a", Activated: true},
		{Name: "FAIL", DeploymentID: "dep-FAIL", Activated: true},
	}
	// SSE-like batch: single route, all-success.
	batchSSE := []Route{
		{Name: "sse-only", DeploymentID: "dep-sse", Activated: true},
	}

	var resPolling, resSSE SyncResult
	var errPolling error
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		resPolling, errPolling = adapter.SyncRoutes(context.Background(), server.URL, batchPolling)
	}()
	go func() {
		defer wg.Done()
		resSSE, _ = adapter.SyncRoutes(context.Background(), server.URL, batchSSE)
	}()
	wg.Wait()

	if errPolling == nil {
		t.Fatal("polling batch should have returned an error (dep-FAIL)")
	}
	if _, failed := resPolling.FailedRoutes["dep-FAIL"]; !failed {
		t.Errorf("polling.FailedRoutes must contain dep-FAIL, got %v", resPolling.FailedRoutes)
	}
	// Isolation: SSE call's FailedRoutes must not contain dep-FAIL.
	if _, leaked := resSSE.FailedRoutes["dep-FAIL"]; leaked {
		t.Errorf("SSE.FailedRoutes leaked polling failure: %v", resSSE.FailedRoutes)
	}
	// Isolation: polling.FailedRoutes must not contain SSE's dep.
	if _, leaked := resPolling.FailedRoutes["dep-sse"]; leaked {
		t.Errorf("polling.FailedRoutes leaked SSE entry: %v", resPolling.FailedRoutes)
	}
}

// readBody is a tiny helper because tests run on a stdlib-only path.
func readBody(r *http.Request) ([]byte, error) {
	const max = 1 << 20 // 1 MiB safety cap
	buf := make([]byte, 0, 256)
	tmp := make([]byte, 256)
	for len(buf) < max {
		n, err := r.Body.Read(tmp)
		if n > 0 {
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			break
		}
	}
	return buf, nil
}
