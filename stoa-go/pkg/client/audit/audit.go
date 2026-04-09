// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package audit provides audit log query operations for stoactl.
// Implementation comes in Phase 1b (CAB-2022).
package audit

import "net/http"

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
