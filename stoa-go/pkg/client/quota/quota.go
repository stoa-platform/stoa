// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package quota provides quota management operations for stoactl.
// Implementation comes in Phase 2 (CAB-2023).
package quota

import "net/http"

// Doer performs HTTP requests. Satisfied by *client.Client.
type Doer interface {
	Do(method, path string, body any) (*http.Response, error)
}

// Service provides quota management operations.
type Service struct {
	doer Doer
}

// New creates a quota service backed by the given HTTP doer.
func New(doer Doer) *Service {
	return &Service{doer: doer}
}
