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

// mixedGateway models independently missing contracts and their publication protection.
type mixedGateway struct {
	missing    map[string]bool
	protection map[string]string
	posts      int
}

func (f *mixedGateway) Missing(_ context.Context, c stoagateway.Contract) (bool, error) {
	return f.missing[c.String("name")], nil
}
func (f *mixedGateway) ForeignObjects(context.Context, stoagateway.Contract) (bool, error) {
	return false, nil
}
func (f *mixedGateway) Publish(_ context.Context, c stoagateway.Contract) (string, error) {
	f.posts++
	f.missing[c.String("name")] = false
	return f.protection[c.String("name")], nil
}

func TestLeastProtectiveContractStatus(t *testing.T) {
	for _, names := range [][]string{{"open", "secured"}, {"secured", "open"}} {
		t.Run(names[0]+"-first", func(t *testing.T) {
			f := &mixedGateway{missing: map[string]bool{}, protection: map[string]string{"open": "unprotected", "secured": "enforced"}}
			target := Target{Name: "edge"}
			for _, name := range names {
				target.Contracts = append(target.Contracts, stoagateway.Contract{"name": name, "tenant_id": "sandbox", "version": "1"})
			}
			run := func(previous Status) Status {
				t.Helper()
				s := Run(context.Background(), []Target{target}, map[string]Gateway{"edge": f}, previous, "content", "targets")
				if s.Result != "degraded" || s.Gateways[0].Protection != "unprotected" {
					t.Fatalf("open contract hidden: %+v", s)
				}
				return s
			}
			s := run(Status{})
			if f.posts != 2 {
				t.Fatalf("initial publications: %d", f.posts)
			}
			s = run(s)
			if f.posts != 2 {
				t.Fatalf("converged pass republished: %d", f.posts)
			}
			for _, name := range []string{"secured", "open"} {
				f.missing[name] = true
				s = run(s)
				s = run(s)
			}
			if f.posts != 4 {
				t.Fatalf("partial repair publications: %d", f.posts)
			}
		})
	}
}
