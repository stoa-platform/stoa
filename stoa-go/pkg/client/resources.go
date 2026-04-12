// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package client

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// ---- Consumer Methods (CAB-2053) ----

// ListConsumers fetches all consumers for the current tenant
func (c *Client) ListConsumers() (*types.ConsumerListResponse, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/consumers/%s", c.tenant), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.ConsumerListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetConsumer fetches a single consumer by ID
func (c *Client) GetConsumer(id string) (*types.Consumer, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/consumers/%s/%s", c.tenant, id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("consumer %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Consumer
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// DeleteConsumer deletes a consumer by ID
func (c *Client) DeleteConsumer(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/consumers/%s/%s", c.tenant, id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("consumer %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ---- Contract Methods (CAB-2053) ----

// ListContracts fetches all contracts for the current tenant
func (c *Client) ListContracts() (*types.ContractListResponse, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s/contracts", c.tenant), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.ContractListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetContract fetches a single contract by ID
func (c *Client) GetContract(id string) (*types.Contract, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s/contracts/%s", c.tenant, id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("contract %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Contract
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// DeleteContract deletes a contract by ID
func (c *Client) DeleteContract(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/tenants/%s/contracts/%s", c.tenant, id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("contract %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ---- Service Account Methods (CAB-2053) ----

// ListServiceAccounts fetches all service accounts for the current user
func (c *Client) ListServiceAccounts() ([]types.ServiceAccount, error) {
	resp, err := c.do("GET", "/v1/service-accounts", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result []types.ServiceAccount
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return result, nil
}

// DeleteServiceAccount deletes a service account by ID
func (c *Client) DeleteServiceAccount(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/service-accounts/%s", id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("service account %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ---- Environment Methods (CAB-2053) ----

// ListEnvironments fetches all environments
func (c *Client) ListEnvironments() (*types.EnvironmentListResponse, error) {
	resp, err := c.do("GET", "/v1/environments", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.EnvironmentListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// ---- Plan Methods (CAB-2053) ----

// ListPlans fetches all plans for the current tenant
func (c *Client) ListPlans() (*types.PlanListResponse, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/plans/%s", c.tenant), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.PlanListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetPlan fetches a single plan by ID
func (c *Client) GetPlan(id string) (*types.Plan, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/plans/%s/%s", c.tenant, id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("plan %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Plan
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// DeletePlan deletes a plan by ID
func (c *Client) DeletePlan(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/plans/%s/%s", c.tenant, id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("plan %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ---- Webhook Methods (CAB-2053) ----

// ListWebhooks fetches all webhooks for the current tenant
func (c *Client) ListWebhooks() (*types.WebhookListResponse, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s/webhooks", c.tenant), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.WebhookListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetWebhook fetches a single webhook by ID
func (c *Client) GetWebhook(id string) (*types.Webhook, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s/webhooks/%s", c.tenant, id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("webhook %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Webhook
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// DeleteWebhook deletes a webhook by ID
func (c *Client) DeleteWebhook(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/tenants/%s/webhooks/%s", c.tenant, id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("webhook %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ---- Gateway Delete (CAB-2053) ----

// DeleteGateway deletes a gateway instance by ID
func (c *Client) DeleteGateway(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/admin/gateways/%s", id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("gateway %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// DeleteSubscription deletes a subscription by ID
func (c *Client) DeleteSubscription(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/subscriptions/%s", id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("subscription %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}
