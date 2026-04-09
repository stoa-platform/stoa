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
