package reconcile

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/stoa-platform/stoa-go/internal/cli/adapter/stoagateway"
)

type Gateway interface {
	Missing(context.Context, stoagateway.Contract) (bool, error)
	ForeignObjects(context.Context, stoagateway.Contract) (bool, error)
	Publish(context.Context, stoagateway.Contract) (string, error)
}
type Options struct {
	AllowUnauthenticatedREST bool `json:"allowUnauthenticatedREST"`
}
type InboundAuth struct {
	Audience     string `json:"audience"`
	Issuer       string `json:"issuer"`
	JWKSURI      string `json:"jwksUri"`
	DiscoveryURL string `json:"discoveryURL"`
	Realm        string `json:"realm"`
}
type Target struct {
	InboundAuth InboundAuth            `json:"inboundAuth"`
	Name        string                 `json:"name"`
	AdminURL    string                 `json:"adminURL"`
	GatewayURL  string                 `json:"gatewayURL"`
	TokenEnv    string                 `json:"tokenEnv"`
	Options     Options                `json:"options"`
	Contracts   []stoagateway.Contract `json:"contracts"`
}
type GatewayStatus struct {
	Name       string `json:"name"`
	Protection string `json:"protection,omitempty"`
	Error      string `json:"error,omitempty"`
}
type Status struct {
	Result        string          `json:"result"`
	ContentDigest string          `json:"contentDigest"`
	TargetsDigest string          `json:"targetsDigest"`
	Missing       []string        `json:"missing,omitempty"`
	Gateways      []GatewayStatus `json:"gateways"`
}

func same(a, b []string) bool { return strings.Join(a, "\n") == strings.Join(b, "\n") }

// Run probes only desired contracts. Removed contracts are never resurrected.
// Failed repairs remain sticky until content, targets or the missing set changes.
func Run(ctx context.Context, targets []Target, clients map[string]Gateway, previous Status, contentDigest, targetsDigest string) Status {
	s := Status{Result: "ok", ContentDigest: contentDigest, TargetsDigest: targetsDigest}
	type pending struct {
		target   string
		contract stoagateway.Contract
	}
	var repairs []pending
	for _, t := range targets {
		g := clients[t.Name]
		gs := GatewayStatus{Name: t.Name}
		if g == nil {
			gs.Error = "gateway unavailable"
		} else {
			for _, c := range t.Contracts {
				missing, err := g.Missing(ctx, c)
				if err != nil {
					gs.Error = err.Error()
					break
				}
				if missing {
					s.Missing = append(s.Missing, t.Name+"/"+c.Key()+"/"+c.String("version"))
				}
				if missing || previous.ContentDigest != contentDigest || previous.TargetsDigest != targetsDigest {
					repairs = append(repairs, pending{t.Name, c})
				}
			}
		}
		s.Gateways = append(s.Gateways, gs)
		if gs.Error != "" {
			s.Result = "failed"
		}
	}
	sort.Strings(s.Missing)
	// Probe failure prevents all writes in this pass and cannot be mistaken for convergence.
	if s.Result == "failed" {
		return s
	}
	if len(s.Missing) > 0 && (previous.Result == "failed" || previous.Result == "drift-unresolved") && previous.ContentDigest == contentDigest && previous.TargetsDigest == targetsDigest && same(previous.Missing, s.Missing) {
		return previous
	}
	for _, p := range repairs {
		g := clients[p.target]
		var protection string
		foreign, err := g.ForeignObjects(ctx, p.contract)
		if err == nil && foreign {
			err = fmt.Errorf("drift collision: foreign-owned contract")
		}
		if err == nil {
			protection, err = g.Publish(ctx, p.contract)
		}
		for i := range s.Gateways {
			if s.Gateways[i].Name == p.target {
				if protection != "" {
					s.Gateways[i].Protection = protection
				}
				if err != nil {
					s.Gateways[i].Error = err.Error()
				}
			}
		}
		if err != nil {
			s.Result = "failed"
			continue
		}
		missing, err := g.Missing(ctx, p.contract)
		if err != nil {
			s.Result = "failed"
			for i := range s.Gateways {
				if s.Gateways[i].Name == p.target {
					s.Gateways[i].Error = err.Error()
				}
			}
		} else if missing && s.Result != "failed" {
			s.Result = "drift-unresolved"
		}
	}
	if s.Result == "ok" {
		s.Missing = nil
		for i := range s.Gateways {
			for _, old := range previous.Gateways {
				if old.Name == s.Gateways[i].Name && s.Gateways[i].Protection == "" && previous.ContentDigest == contentDigest && previous.TargetsDigest == targetsDigest {
					s.Gateways[i].Protection = old.Protection
				}
			}
			if s.Gateways[i].Protection == "unprotected" {
				s.Result = "degraded"
			}
		}
	}
	return s
}
