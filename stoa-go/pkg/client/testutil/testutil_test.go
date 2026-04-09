// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package testutil

import (
	"encoding/json"
	"io"
	"net/http"
	"testing"
)

func TestMockTransportMatchesRoute(t *testing.T) {
	mt := NewMockTransport(Responses{
		"GET /v1/health": {Status: http.StatusOK, Body: map[string]string{"status": "ok"}},
	})

	req, _ := http.NewRequest("GET", "http://mock/v1/health", nil)
	resp, err := mt.RoundTrip(req)
	if err != nil {
		t.Fatalf("RoundTrip error = %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want 200", resp.StatusCode)
	}

	var body map[string]string
	_ = json.NewDecoder(resp.Body).Decode(&body)
	if body["status"] != "ok" {
		t.Errorf("body status = %q, want %q", body["status"], "ok")
	}

	if len(mt.Calls) != 1 {
		t.Errorf("Calls = %d, want 1", len(mt.Calls))
	}
}

func TestMockTransportReturns404ForUnknownRoute(t *testing.T) {
	mt := NewMockTransport(Responses{})

	req, _ := http.NewRequest("GET", "http://mock/unknown", nil)
	resp, err := mt.RoundTrip(req)
	if err != nil {
		t.Fatalf("RoundTrip error = %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusNotFound {
		t.Errorf("status = %d, want 404", resp.StatusCode)
	}
}

func TestNewTestClientDo(t *testing.T) {
	tc := NewTestClient(Responses{
		"POST /v1/apis": {Status: http.StatusCreated, Body: `{"id":"abc"}`},
	})

	resp, err := tc.Do("POST", "/v1/apis", map[string]string{"name": "test"})
	if err != nil {
		t.Fatalf("Do() error = %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated {
		t.Errorf("status = %d, want 201", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if string(body) != `{"id":"abc"}` {
		t.Errorf("body = %q, want %q", string(body), `{"id":"abc"}`)
	}
}

func TestMockTransportStringBody(t *testing.T) {
	mt := NewMockTransport(Responses{
		"GET /text": {Status: http.StatusOK, Body: "plain text"},
	})

	req, _ := http.NewRequest("GET", "http://mock/text", nil)
	resp, err := mt.RoundTrip(req)
	if err != nil {
		t.Fatalf("RoundTrip error = %v", err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)
	if string(body) != "plain text" {
		t.Errorf("body = %q, want %q", string(body), "plain text")
	}
}
