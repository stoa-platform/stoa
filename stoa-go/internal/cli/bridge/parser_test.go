// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"math"
	"testing"

	"github.com/getkin/kin-openapi/openapi3"
)

func TestRegressionOpenAPI31SchemaRejectsNonFiniteNumbers(t *testing.T) {
	// GHSA-rj39-cv6w-8wv7: OAS 3.1 numeric constraints must reject
	// YAML's non-finite numbers without panicking in the JSON Schema validator.
	result, err := ParseOpenAPI([]byte(`{
		"openapi": "3.1.0",
		"info": {"title": "Numeric API", "version": "1.0.0"},
		"paths": {},
		"components": {
			"schemas": {"Amount": {"type": "number", "minimum": 0}}
		}
	}`))
	if err != nil {
		t.Fatalf("parse OpenAPI 3.1 numeric schema: %v", err)
	}
	schema := result.Doc.Components.Schemas["Amount"].Value
	if err := schema.VisitJSON(float64(1), openapi3.EnableJSONSchema2020()); err != nil {
		t.Fatalf("valid finite number rejected: %v", err)
	}

	for _, tc := range []struct {
		name  string
		value float64
	}{
		{name: "NaN", value: math.NaN()},
		{name: "positive infinity", value: math.Inf(1)},
		{name: "negative infinity", value: math.Inf(-1)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			defer func() {
				if recovered := recover(); recovered != nil {
					t.Errorf("non-finite number caused a panic: %v", recovered)
				}
			}()
			if err := schema.VisitJSON(tc.value, openapi3.EnableJSONSchema2020()); err == nil {
				t.Fatal("non-finite number must return a validation error")
			}
		})
	}
}
