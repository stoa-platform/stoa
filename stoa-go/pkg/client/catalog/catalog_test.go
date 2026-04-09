// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package catalog

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/client/testutil"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

// ---- Sync/Stats tests (CAB-2021) ----

func TestTriggerSync(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"POST /v1/admin/catalog/sync": {Status: 200, Body: types.SyncTriggerResponse{
			Status:  "sync_started",
			Message: "Catalog sync triggered successfully",
		}},
	})

	svc := New(tc)
	resp, err := svc.TriggerSync("")
	if err != nil {
		t.Fatalf("TriggerSync() error: %v", err)
	}
	if resp.Status != "sync_started" {
		t.Errorf("got status %q, want %q", resp.Status, "sync_started")
	}
}

func TestTriggerSyncTenant(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"POST /v1/admin/catalog/sync/tenant/acme": {Status: 200, Body: types.SyncTriggerResponse{
			Status:  "sync_started",
			Message: "Catalog sync triggered for tenant acme",
		}},
	})

	svc := New(tc)
	resp, err := svc.TriggerSync("acme")
	if err != nil {
		t.Fatalf("TriggerSync(acme) error: %v", err)
	}
	if resp.Status != "sync_started" {
		t.Errorf("got status %q, want %q", resp.Status, "sync_started")
	}
}

func TestSyncStatus(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/admin/catalog/sync/status": {Status: 200, Body: types.SyncStatusResponse{
			ID:          "sync-001",
			SyncType:    "full",
			Status:      "success",
			ItemsSynced: 15,
			ItemsFailed: 0,
			Duration:    "2.5s",
		}},
	})

	svc := New(tc)
	resp, err := svc.SyncStatus()
	if err != nil {
		t.Fatalf("SyncStatus() error: %v", err)
	}
	if resp.ItemsSynced != 15 {
		t.Errorf("got ItemsSynced %d, want 15", resp.ItemsSynced)
	}
}

func TestSyncStatusNotFound(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/admin/catalog/sync/status": {Status: 404, Body: `{"detail":"No sync operations found"}`},
	})

	svc := New(tc)
	resp, err := svc.SyncStatus()
	if err != nil {
		t.Fatalf("SyncStatus() error: %v", err)
	}
	if resp != nil {
		t.Error("expected nil response for 404")
	}
}

func TestStats(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/admin/catalog/stats": {Status: 200, Body: types.CatalogStatsResponse{
			TotalAPIs:       20,
			PublishedAPIs:   15,
			UnpublishedAPIs: 5,
			ByTenant:        map[string]int{"acme": 12, "test": 8},
			ByCategory:      map[string]int{"payments": 5},
		}},
	})

	svc := New(tc)
	resp, err := svc.Stats()
	if err != nil {
		t.Fatalf("Stats() error: %v", err)
	}
	if resp.TotalAPIs != 20 {
		t.Errorf("got TotalAPIs %d, want 20", resp.TotalAPIs)
	}
	if resp.ByTenant["acme"] != 12 {
		t.Errorf("got ByTenant[acme] %d, want 12", resp.ByTenant["acme"])
	}
}

func TestListAllAPIs(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/admin/catalog/apis": {Status: 200, Body: types.AdminAPIPaginatedResponse{
			Items: []types.AdminAPI{
				{ID: "billing", TenantID: "acme", Name: "billing", DisplayName: "Billing API", Version: "1.0.0", Status: "active"},
				{ID: "users", TenantID: "acme", Name: "users", DisplayName: "Users API", Version: "2.0.0", Status: "active"},
			},
			Total:    2,
			Page:     1,
			PageSize: 100,
		}},
	})

	svc := New(tc)
	resp, err := svc.ListAllAPIs("", 1, 100)
	if err != nil {
		t.Fatalf("ListAllAPIs() error: %v", err)
	}
	if len(resp.Items) != 2 {
		t.Errorf("got %d items, want 2", len(resp.Items))
	}
}

func TestTriggerSyncError(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"POST /v1/admin/catalog/sync": {Status: 403, Body: `{"detail":"Admin access required"}`},
	})

	svc := New(tc)
	_, err := svc.TriggerSync("")
	if err == nil {
		t.Fatal("expected error for 403")
	}
}

func TestList(t *testing.T) {
	want := types.APIListResponse{
		Items:      []types.API{{ID: "1", Name: "api-1", Version: "v1", Status: "active"}},
		TotalCount: 1,
	}
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/portal/apis": {Status: http.StatusOK, Body: want},
	})

	svc := New(tc)
	got, err := svc.List()
	if err != nil {
		t.Fatalf("List() error = %v", err)
	}
	if got.TotalCount != 1 {
		t.Errorf("List() TotalCount = %d, want 1", got.TotalCount)
	}
	if got.Items[0].Name != "api-1" {
		t.Errorf("List() Items[0].Name = %q, want %q", got.Items[0].Name, "api-1")
	}
}

func TestListError(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/portal/apis": {Status: http.StatusInternalServerError, Body: "internal error"},
	})

	svc := New(tc)
	_, err := svc.List()
	if err == nil {
		t.Error("List() error = nil, want error for 500")
	}
}

func TestGet(t *testing.T) {
	want := types.API{ID: "123", Name: "my-api", Version: "v1", Status: "active"}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/portal/apis/my-api" {
			t.Errorf("path = %q, want /v1/portal/apis/my-api", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(want)
	}))
	defer server.Close()

	tc := testutil.NewTestClientWithURL(server.URL)
	svc := New(tc)

	got, err := svc.Get("my-api")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if got.Name != "my-api" {
		t.Errorf("Get() Name = %q, want %q", got.Name, "my-api")
	}
}

func TestGetNotFound(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/portal/apis/gone": {Status: http.StatusNotFound},
	})
	svc := New(tc)

	_, err := svc.Get("gone")
	if err == nil {
		t.Error("Get() error = nil, want not-found error")
	}
}

func TestDelete(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("method = %s, want DELETE", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	tc := testutil.NewTestClientWithURL(server.URL)
	svc := New(tc)

	if err := svc.Delete("my-api"); err != nil {
		t.Errorf("Delete() error = %v", err)
	}
}

func TestValidate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("dryRun") != "true" {
			t.Error("expected dryRun=true query parameter")
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	tc := testutil.NewTestClientWithURL(server.URL)
	svc := New(tc)

	resource := &types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "API",
		Metadata:   types.Metadata{Name: "test"},
	}
	if err := svc.Validate(resource); err != nil {
		t.Errorf("Validate() error = %v", err)
	}
}
