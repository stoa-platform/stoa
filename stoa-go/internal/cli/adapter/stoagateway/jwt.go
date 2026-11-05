package stoagateway

import (
	"errors"
	"maps"
	"net/url"
	"strings"
)

// RealmNames extracts realm names from configured identity-provider URLs.
func RealmNames(explicit string, rawURLs ...string) []string {
	var realms []string
	add := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		for _, r := range realms {
			if strings.EqualFold(r, value) {
				return
			}
		}
		realms = append(realms, value)
	}
	add("stoa")
	add(explicit)
	for _, raw := range rawURLs {
		u, err := url.Parse(raw)
		if err != nil {
			continue
		}
		segments := strings.Split(u.Path, "/")
		for i := 0; i+1 < len(segments); i++ {
			if segments[i] == "realms" {
				add(segments[i+1])
			}
		}
	}
	return realms
}
func genericAudience(audience string, realms []string) bool {
	audience = strings.TrimSpace(audience)
	if audience == "" || strings.ContainsAny(audience, "*?") || strings.EqualFold(audience, "account") {
		return true
	}
	for _, realm := range realms {
		if strings.EqualFold(strings.TrimSpace(realm), audience) {
			return true
		}
	}
	return false
}
func (a *Adapter) authenticatedContract(c Contract) (Contract, error) {
	class := strings.ToUpper(strings.TrimSpace(c.String("classification")))
	if class != "H" && class != "VH" && class != "VVH" {
		return nil, errors.New("classification must be H, VH or VVH")
	}
	if a.AllowUnauthenticatedREST && class != "H" {
		return nil, errors.New("allowUnauthenticatedREST is restricted to classification H")
	}
	audience := strings.TrimSpace(a.Audience)
	if audience == "" {
		audience = strings.TrimSpace(authField(c, "inboundAuthAudience", "inbound_auth_audience"))
	}
	if audience == "" {
		if !a.AllowUnauthenticatedREST {
			return nil, errors.New("specific inboundAuth audience required before publish")
		}
	} else if genericAudience(audience, a.Realms) {
		return nil, errors.New("generic inboundAuth audience refused before publish")
	}
	// Copy the map so callers retain their original desired document.
	out := maps.Clone(c)
	delete(out, "inbound_auth")
	delete(out, "inbound_auth_audience")
	delete(out, "inboundAuth")
	delete(out, "inboundAuthAudience")
	out["classification"] = class
	if audience != "" {
		out["inboundAuth"] = "jwt"
		out["inboundAuthAudience"] = audience
	}
	return out, nil
}
func authField(c Contract, camel, snake string) string {
	if s := c.String(camel); s != "" {
		return s
	}
	return c.String(snake)
}
func (a *Adapter) mayRestore(c Contract) bool {
	auth := strings.TrimSpace(authField(c, "inboundAuth", "inbound_auth"))
	audience := authField(c, "inboundAuthAudience", "inbound_auth_audience")
	if strings.EqualFold(auth, "jwt") && !genericAudience(audience, a.Realms) {
		return true
	}
	return a.AllowUnauthenticatedREST && strings.EqualFold(strings.TrimSpace(c.String("classification")), "H")
}
func verifiedAuth(live, want Contract) bool {
	return authField(live, "inboundAuth", "inbound_auth") == want.String("inboundAuth") && authField(live, "inboundAuthAudience", "inbound_auth_audience") == want.String("inboundAuthAudience")
}
