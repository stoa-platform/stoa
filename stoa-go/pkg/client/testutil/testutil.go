// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package testutil provides reusable HTTP mocking for stoactl client tests.
// Use MockTransport for route-based responses or NewTestClientWithURL for
// httptest.Server-backed tests.
package testutil

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// Response defines a canned HTTP response for a given route.
type Response struct {
	Status int
	Body   any // JSON-marshalled automatically; string and []byte sent as-is
}

// Responses maps "METHOD /path" keys to canned responses.
type Responses map[string]Response

// MockTransport implements http.RoundTripper with canned responses.
// Routes are matched by "METHOD /path" (query string ignored).
type MockTransport struct {
	routes Responses
	// Calls records every request for assertion.
	Calls []*http.Request
}

// NewMockTransport creates a transport that returns canned responses.
func NewMockTransport(routes Responses) *MockTransport {
	return &MockTransport{routes: routes}
}

// RoundTrip implements http.RoundTripper.
func (m *MockTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	m.Calls = append(m.Calls, req)

	key := fmt.Sprintf("%s %s", req.Method, req.URL.Path)
	r, ok := m.routes[key]
	if !ok {
		return &http.Response{
			StatusCode: http.StatusNotFound,
			Body:       io.NopCloser(bytes.NewBufferString(fmt.Sprintf("no mock for %s", key))),
			Header:     make(http.Header),
		}, nil
	}

	var bodyReader io.ReadCloser
	switch v := r.Body.(type) {
	case nil:
		bodyReader = io.NopCloser(bytes.NewReader(nil))
	case string:
		bodyReader = io.NopCloser(bytes.NewBufferString(v))
	case []byte:
		bodyReader = io.NopCloser(bytes.NewReader(v))
	default:
		data, err := json.Marshal(v)
		if err != nil {
			return nil, fmt.Errorf("testutil: failed to marshal response body: %w", err)
		}
		bodyReader = io.NopCloser(bytes.NewReader(data))
	}

	return &http.Response{
		StatusCode: r.Status,
		Body:       bodyReader,
		Header:     http.Header{"Content-Type": {"application/json"}},
	}, nil
}

// TestClient wraps an http.Client with MockTransport and satisfies the Doer
// interface used by sub-packages (catalog, audit, trace, quota).
type TestClient struct {
	baseURL   string
	tenant    string
	Transport *MockTransport
	http      *http.Client
}

// NewTestClient creates a TestClient backed by canned responses.
// The baseURL is set to "" so paths are used as-is in the mock.
func NewTestClient(routes Responses) *TestClient {
	mt := NewMockTransport(routes)
	return &TestClient{
		baseURL:   "http://mock",
		tenant:    "test-tenant",
		Transport: mt,
		http:      &http.Client{Transport: mt},
	}
}

// NewTestClientWithURL creates a TestClient pointing at a real httptest.Server URL.
// Use this when you need httptest.Server for more complex response logic.
func NewTestClientWithURL(baseURL string) *TestClient {
	return &TestClient{
		baseURL: baseURL,
		tenant:  "test-tenant",
		http:    &http.Client{},
	}
}

// WithTenant overrides the default test tenant ID.
func (tc *TestClient) WithTenant(tenant string) *TestClient {
	tc.tenant = tenant
	return tc
}

// TenantID satisfies catalog.Doer.
func (tc *TestClient) TenantID() string {
	return tc.tenant
}

// Do performs an HTTP request, satisfying the catalog.Doer interface.
func (tc *TestClient) Do(method, path string, body any) (*http.Response, error) {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	url := fmt.Sprintf("%s%s", tc.baseURL, path)
	req, err := http.NewRequest(method, url, bodyReader)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	return tc.http.Do(req)
}
