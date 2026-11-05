package reconcile

import (
	"context"
	"errors"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/cli/adapter/stoagateway"
)

type fakeGateway struct {
	missing    bool
	collision  bool
	fail       bool
	posts      int
	protection string
}

func (f *fakeGateway) Missing(context.Context, stoagateway.Contract) (bool, error) {
	return f.missing, nil
}
func (f *fakeGateway) ForeignObjects(context.Context, stoagateway.Contract) (bool, error) {
	return f.collision, nil
}
func (f *fakeGateway) Publish(context.Context, stoagateway.Contract) (string, error) {
	f.posts++
	if f.fail {
		return "", errors.New("publish failed")
	}
	return f.protection, nil
}

func TestStickyRepair(t *testing.T) {
	for _, fail := range []bool{false, true} {
		f := &fakeGateway{missing: true, fail: fail}
		targets := []Target{{Name: "edge", Contracts: []stoagateway.Contract{{"tenant_id": "sandbox", "name": "sample", "version": "1", "description": "owner"}}}}
		clients := map[string]Gateway{"edge": f}
		first := Run(context.Background(), targets, clients, Status{}, "content", "targets")
		second := Run(context.Background(), targets, clients, first, "content", "targets")
		if f.posts != 1 || (second.Result != "failed" && second.Result != "drift-unresolved") {
			t.Fatalf("repair repeated: %+v posts=%d", second, f.posts)
		}
		Run(context.Background(), targets, clients, second, "content", "changed")
		if f.posts != 2 {
			t.Fatal("target change did not retry")
		}
		Run(context.Background(), targets, clients, second, "changed", "targets")
		if f.posts != 3 {
			t.Fatal("content change did not retry")
		}
	}
}
func TestCollisionAndDegraded(t *testing.T) {
	f := &fakeGateway{missing: true, collision: true}
	targets := []Target{{Name: "edge", Contracts: []stoagateway.Contract{{"name": "sample", "tenant_id": "sandbox", "version": "1", "description": "owner"}}}}
	s := Run(context.Background(), targets, map[string]Gateway{"edge": f}, Status{}, "a", "b")
	if f.posts != 0 || s.Result != "failed" {
		t.Fatal("collision overwritten")
	}
	f.collision = false
	f.missing = false
	f.protection = "unprotected"
	s = Run(context.Background(), targets, map[string]Gateway{"edge": f}, Status{}, "a", "b")
	if s.Result != "degraded" {
		t.Fatalf("expected degraded: %+v", s)
	}
}
