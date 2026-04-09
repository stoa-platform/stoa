// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package audit provides audit log query operations for stoactl.
package audit

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// Doer performs HTTP requests. Satisfied by *client.Client.
type Doer interface {
	Do(method, path string, body any) (*http.Response, error)
}

// Service provides audit log operations (export, query).
type Service struct {
	doer Doer
}

// New creates an audit service backed by the given HTTP doer.
func New(doer Doer) *Service {
	return &Service{doer: doer}
}

// ExportOpts configures audit export parameters.
type ExportOpts struct {
	TenantID  string
	Action    string
	StartDate string // ISO 8601
	EndDate   string // ISO 8601
	Page      int
	PageSize  int
}

// Export fetches audit entries for a tenant with optional filters.
func (s *Service) Export(opts ExportOpts) (*types.AuditListResponse, error) {
	if opts.TenantID == "" {
		return nil, fmt.Errorf("tenant_id is required")
	}
	if opts.Page < 1 {
		opts.Page = 1
	}
	if opts.PageSize < 1 {
		opts.PageSize = 50
	}

	params := url.Values{}
	params.Set("page", strconv.Itoa(opts.Page))
	params.Set("page_size", strconv.Itoa(opts.PageSize))
	if opts.Action != "" {
		params.Set("action", opts.Action)
	}
	if opts.StartDate != "" {
		params.Set("start_date", opts.StartDate)
	}
	if opts.EndDate != "" {
		params.Set("end_date", opts.EndDate)
	}

	path := fmt.Sprintf("/v1/audit/%s?%s", url.PathEscape(opts.TenantID), params.Encode())
	resp, err := s.doer.Do("GET", path, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.AuditListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}
	return &result, nil
}

// ExportAll fetches all audit entries with pagination.
func (s *Service) ExportAll(opts ExportOpts) ([]types.AuditEntry, error) {
	var all []types.AuditEntry
	opts.Page = 1
	if opts.PageSize < 1 {
		opts.PageSize = 500
	}

	for {
		resp, err := s.Export(opts)
		if err != nil {
			return nil, err
		}
		all = append(all, resp.Entries...)
		if !resp.HasMore {
			break
		}
		opts.Page++
	}
	return all, nil
}

// ExportCSV fetches audit entries as raw CSV bytes.
func (s *Service) ExportCSV(tenantID, startDate, endDate string, limit int) ([]byte, error) {
	if tenantID == "" {
		return nil, fmt.Errorf("tenant_id is required")
	}

	params := url.Values{}
	if startDate != "" {
		params.Set("start_date", startDate)
	}
	if endDate != "" {
		params.Set("end_date", endDate)
	}
	if limit > 0 {
		params.Set("limit", strconv.Itoa(limit))
	}

	path := fmt.Sprintf("/v1/audit/%s/export/csv?%s", url.PathEscape(tenantID), params.Encode())
	resp, err := s.doer.Do("GET", path, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return io.ReadAll(resp.Body)
}
