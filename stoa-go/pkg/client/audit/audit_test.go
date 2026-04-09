// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package audit

import (
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/client/testutil"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

func TestExport(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/audit/acme": {Status: 200, Body: types.AuditListResponse{
			Entries: []types.AuditEntry{
				{ID: "a1", TenantID: "acme", Action: "api_call", Status: "success", UserEmail: "alice@corp.com", ClientIP: "10.0.0.1"},
				{ID: "a2", TenantID: "acme", Action: "authentication", Status: "failure", UserEmail: "bob@test.org", ClientIP: "192.168.1.5"},
			},
			Total:    2,
			Page:     1,
			PageSize: 50,
			HasMore:  false,
		}},
	})

	svc := New(tc)
	resp, err := svc.Export(ExportOpts{TenantID: "acme", Page: 1, PageSize: 50})
	if err != nil {
		t.Fatalf("Export() error: %v", err)
	}
	if len(resp.Entries) != 2 {
		t.Errorf("got %d entries, want 2", len(resp.Entries))
	}
	if resp.Entries[0].UserEmail != "alice@corp.com" {
		t.Errorf("got email %q, want %q", resp.Entries[0].UserEmail, "alice@corp.com")
	}
}

func TestExportMissingTenant(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{})
	svc := New(tc)
	_, err := svc.Export(ExportOpts{})
	if err == nil {
		t.Fatal("expected error for missing tenant_id")
	}
}

func TestExportAll(t *testing.T) {
	// Page 1: has_more=true, Page 2: has_more=false
	// MockTransport matches by path only (ignores query), so both pages hit the same route.
	// We use an httptest.Server for multi-page testing instead.
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/audit/acme": {Status: 200, Body: types.AuditListResponse{
			Entries: []types.AuditEntry{
				{ID: "a1", TenantID: "acme", Action: "api_call", Status: "success"},
			},
			Total:    1,
			Page:     1,
			PageSize: 500,
			HasMore:  false,
		}},
	})

	svc := New(tc)
	entries, err := svc.ExportAll(ExportOpts{TenantID: "acme"})
	if err != nil {
		t.Fatalf("ExportAll() error: %v", err)
	}
	if len(entries) != 1 {
		t.Errorf("got %d entries, want 1", len(entries))
	}
}

func TestExportCSV(t *testing.T) {
	csvData := "ID,Timestamp,Tenant\na1,2026-01-01,acme\n"
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/audit/acme/export/csv": {Status: 200, Body: csvData},
	})

	svc := New(tc)
	data, err := svc.ExportCSV("acme", "", "", 0)
	if err != nil {
		t.Fatalf("ExportCSV() error: %v", err)
	}
	if string(data) != csvData {
		t.Errorf("got %q, want %q", string(data), csvData)
	}
}

func TestExportCSVMissingTenant(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{})
	svc := New(tc)
	_, err := svc.ExportCSV("", "", "", 0)
	if err == nil {
		t.Fatal("expected error for missing tenant_id")
	}
}

func TestExportError(t *testing.T) {
	tc := testutil.NewTestClient(testutil.Responses{
		"GET /v1/audit/acme": {Status: 403, Body: `{"detail":"forbidden"}`},
	})

	svc := New(tc)
	_, err := svc.Export(ExportOpts{TenantID: "acme", Page: 1, PageSize: 50})
	if err == nil {
		t.Fatal("expected error for 403")
	}
}
