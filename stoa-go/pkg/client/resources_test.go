// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package client

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// ---- Consumer Tests ----

func TestListConsumers(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET, got %s", r.Method)
		}
		if r.URL.Path != "/v1/consumers/test-tenant" {
			t.Errorf("Expected path /v1/consumers/test-tenant, got %s", r.URL.Path)
		}

		resp := types.ConsumerListResponse{
			Items: []types.Consumer{
				{ID: "c1", Name: "consumer-1", Email: "c1@test.com", Status: "active"},
				{ID: "c2", Name: "consumer-2", Email: "c2@test.com", Status: "suspended"},
			},
			Total: 2,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.ListConsumers()
	if err != nil {
		t.Fatalf("ListConsumers() error = %v", err)
	}
	if len(result.Items) != 2 {
		t.Errorf("ListConsumers() got %d items, want 2", len(result.Items))
	}
	if result.Items[0].Name != "consumer-1" {
		t.Errorf("ListConsumers()[0].Name = %q, want %q", result.Items[0].Name, "consumer-1")
	}
}

func TestGetConsumer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET, got %s", r.Method)
		}
		if r.URL.Path != "/v1/consumers/test-tenant/c1" {
			t.Errorf("Expected path /v1/consumers/test-tenant/c1, got %s", r.URL.Path)
		}

		resp := types.Consumer{ID: "c1", Name: "consumer-1", Email: "c1@test.com", Status: "active"}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.GetConsumer("c1")
	if err != nil {
		t.Fatalf("GetConsumer() error = %v", err)
	}
	if result.Name != "consumer-1" {
		t.Errorf("GetConsumer().Name = %q, want %q", result.Name, "consumer-1")
	}
}

func TestGetConsumer_NotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	_, err := c.GetConsumer("missing")
	if err == nil {
		t.Error("GetConsumer() error = nil, want error for 404")
	}
}

func TestDeleteConsumer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		if r.URL.Path != "/v1/consumers/test-tenant/c1" {
			t.Errorf("Expected path /v1/consumers/test-tenant/c1, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteConsumer("c1")
	if err != nil {
		t.Fatalf("DeleteConsumer() error = %v", err)
	}
}

// ---- Contract Tests ----

func TestListContracts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET, got %s", r.Method)
		}
		if r.URL.Path != "/v1/tenants/test-tenant/contracts" {
			t.Errorf("Expected path /v1/tenants/test-tenant/contracts, got %s", r.URL.Path)
		}

		resp := types.ContractListResponse{
			Items: []types.Contract{
				{ID: "ct1", Name: "billing-contract", Version: "1.0", Status: "published"},
			},
			Total: 1,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.ListContracts()
	if err != nil {
		t.Fatalf("ListContracts() error = %v", err)
	}
	if len(result.Items) != 1 {
		t.Errorf("ListContracts() got %d items, want 1", len(result.Items))
	}
	if result.Items[0].Name != "billing-contract" {
		t.Errorf("ListContracts()[0].Name = %q, want %q", result.Items[0].Name, "billing-contract")
	}
}

func TestGetContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/tenants/test-tenant/contracts/ct1" {
			t.Errorf("Expected path /v1/tenants/test-tenant/contracts/ct1, got %s", r.URL.Path)
		}

		resp := types.Contract{ID: "ct1", Name: "billing-contract", Version: "1.0", Status: "published"}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.GetContract("ct1")
	if err != nil {
		t.Fatalf("GetContract() error = %v", err)
	}
	if result.Name != "billing-contract" {
		t.Errorf("GetContract().Name = %q, want %q", result.Name, "billing-contract")
	}
}

func TestDeleteContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteContract("ct1")
	if err != nil {
		t.Fatalf("DeleteContract() error = %v", err)
	}
}

// ---- Service Account Tests ----

func TestListServiceAccounts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/service-accounts" {
			t.Errorf("Expected path /v1/service-accounts, got %s", r.URL.Path)
		}

		resp := []types.ServiceAccount{
			{ID: "sa1", Name: "ci-bot", ClientID: "client-123", Status: "active"},
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.ListServiceAccounts()
	if err != nil {
		t.Fatalf("ListServiceAccounts() error = %v", err)
	}
	if len(result) != 1 {
		t.Errorf("ListServiceAccounts() got %d items, want 1", len(result))
	}
	if result[0].Name != "ci-bot" {
		t.Errorf("ListServiceAccounts()[0].Name = %q, want %q", result[0].Name, "ci-bot")
	}
}

func TestDeleteServiceAccount(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		if r.URL.Path != "/v1/service-accounts/sa1" {
			t.Errorf("Expected path /v1/service-accounts/sa1, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteServiceAccount("sa1")
	if err != nil {
		t.Fatalf("DeleteServiceAccount() error = %v", err)
	}
}

// ---- Environment Tests ----

func TestListEnvironments(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/environments" {
			t.Errorf("Expected path /v1/environments, got %s", r.URL.Path)
		}

		resp := types.EnvironmentListResponse{
			Items: []types.Environment{
				{ID: "e1", Name: "production", Type: "prod", URL: "https://api.example.com", Status: "active"},
				{ID: "e2", Name: "staging", Type: "staging", URL: "https://staging.example.com", Status: "active"},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.ListEnvironments()
	if err != nil {
		t.Fatalf("ListEnvironments() error = %v", err)
	}
	if len(result.Items) != 2 {
		t.Errorf("ListEnvironments() got %d items, want 2", len(result.Items))
	}
}

// ---- Plan Tests ----

func TestListPlans(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/plans/test-tenant" {
			t.Errorf("Expected path /v1/plans/test-tenant, got %s", r.URL.Path)
		}

		resp := types.PlanListResponse{
			Items: []types.Plan{
				{ID: "p1", Name: "free", Slug: "free", Status: "active"},
				{ID: "p2", Name: "pro", Slug: "pro", Status: "active"},
			},
			Total: 2,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.ListPlans()
	if err != nil {
		t.Fatalf("ListPlans() error = %v", err)
	}
	if len(result.Items) != 2 {
		t.Errorf("ListPlans() got %d items, want 2", len(result.Items))
	}
}

func TestGetPlan(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/plans/test-tenant/p1" {
			t.Errorf("Expected path /v1/plans/test-tenant/p1, got %s", r.URL.Path)
		}

		resp := types.Plan{ID: "p1", Name: "free", Slug: "free", Status: "active"}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.GetPlan("p1")
	if err != nil {
		t.Fatalf("GetPlan() error = %v", err)
	}
	if result.Name != "free" {
		t.Errorf("GetPlan().Name = %q, want %q", result.Name, "free")
	}
}

func TestDeletePlan(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		if r.URL.Path != "/v1/plans/test-tenant/p1" {
			t.Errorf("Expected path /v1/plans/test-tenant/p1, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeletePlan("p1")
	if err != nil {
		t.Fatalf("DeletePlan() error = %v", err)
	}
}

// ---- Webhook Tests ----

func TestListWebhooks(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/tenants/test-tenant/webhooks" {
			t.Errorf("Expected path /v1/tenants/test-tenant/webhooks, got %s", r.URL.Path)
		}

		resp := types.WebhookListResponse{
			Items: []types.Webhook{
				{ID: "wh1", Name: "deploy-hook", URL: "https://hooks.example.com/deploy", Enabled: true},
			},
			Total: 1,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.ListWebhooks()
	if err != nil {
		t.Fatalf("ListWebhooks() error = %v", err)
	}
	if len(result.Items) != 1 {
		t.Errorf("ListWebhooks() got %d items, want 1", len(result.Items))
	}
	if !result.Items[0].Enabled {
		t.Error("ListWebhooks()[0].Enabled = false, want true")
	}
}

func TestGetWebhook(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/tenants/test-tenant/webhooks/wh1" {
			t.Errorf("Expected path /v1/tenants/test-tenant/webhooks/wh1, got %s", r.URL.Path)
		}

		resp := types.Webhook{ID: "wh1", Name: "deploy-hook", URL: "https://hooks.example.com/deploy", Enabled: true}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	result, err := c.GetWebhook("wh1")
	if err != nil {
		t.Fatalf("GetWebhook() error = %v", err)
	}
	if result.Name != "deploy-hook" {
		t.Errorf("GetWebhook().Name = %q, want %q", result.Name, "deploy-hook")
	}
}

func TestDeleteWebhook(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteWebhook("wh1")
	if err != nil {
		t.Fatalf("DeleteWebhook() error = %v", err)
	}
}

// ---- Gateway/Subscription Delete Tests ----

func TestDeleteGateway(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/gateways/gw1" {
			t.Errorf("Expected path /v1/admin/gateways/gw1, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteGateway("gw1")
	if err != nil {
		t.Fatalf("DeleteGateway() error = %v", err)
	}
}

func TestDeleteGateway_NotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteGateway("missing")
	if err == nil {
		t.Error("DeleteGateway() error = nil, want error for 404")
	}
}

func TestDeleteSubscription(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE, got %s", r.Method)
		}
		if r.URL.Path != "/v1/subscriptions/sub1" {
			t.Errorf("Expected path /v1/subscriptions/sub1, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteSubscription("sub1")
	if err != nil {
		t.Fatalf("DeleteSubscription() error = %v", err)
	}
}

// ---- Error Handling Tests ----

func TestListConsumers_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal error"))
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	_, err := c.ListConsumers()
	if err == nil {
		t.Error("ListConsumers() error = nil, want error for 500")
	}
}

func TestListContracts_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal error"))
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	_, err := c.ListContracts()
	if err == nil {
		t.Error("ListContracts() error = nil, want error for 500")
	}
}

func TestDeleteConsumer_NotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")
	err := c.DeleteConsumer("missing")
	if err == nil {
		t.Error("DeleteConsumer() error = nil, want error for 404")
	}
}
