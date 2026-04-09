// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package catalog

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// Doer performs HTTP requests. Satisfied by *client.Client.
type Doer interface {
	Do(method, path string, body any) (*http.Response, error)
}

// Service provides catalog API operations (list, get, create, delete, validate).
type Service struct {
	doer Doer
}

// New creates a catalog service backed by the given HTTP doer.
func New(doer Doer) *Service {
	return &Service{doer: doer}
}

// List fetches all APIs.
func (s *Service) List() (*types.APIListResponse, error) {
	resp, err := s.doer.Do("GET", "/v1/portal/apis", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.APIListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// Get fetches a single API by name.
func (s *Service) Get(name string) (*types.API, error) {
	resp, err := s.doer.Do("GET", fmt.Sprintf("/v1/portal/apis/%s", name), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("api %q not found", name)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.API
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// CreateOrUpdate creates or updates an API from a resource definition.
func (s *Service) CreateOrUpdate(resource *types.Resource) error {
	resp, err := s.doer.Do("POST", "/v1/apis", resource)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// Delete deletes an API by name.
func (s *Service) Delete(name string) error {
	resp, err := s.doer.Do("DELETE", fmt.Sprintf("/v1/apis/%s", name), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("api %q not found", name)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// Validate performs a dry-run validation of an API resource.
func (s *Service) Validate(resource *types.Resource) error {
	resp, err := s.doer.Do("POST", "/v1/apis?dryRun=true", resource)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("validation error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}
