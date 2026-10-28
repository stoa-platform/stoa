package xds

import (
	"encoding/json"
	"fmt"
	"math"
	"net/netip"
	"strconv"
	"strings"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	rbacconfig "github.com/envoyproxy/go-control-plane/envoy/config/rbac/v3"
	cors "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/cors/v3"
	limit "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/local_ratelimit/v3"
	rbac "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/rbac/v3"
	hcm "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/network/http_connection_manager/v3"
	matcher "github.com/envoyproxy/go-control-plane/envoy/type/matcher/v3"
	typepb "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"google.golang.org/protobuf/types/known/anypb"
	"google.golang.org/protobuf/types/known/durationpb"
	"google.golang.org/protobuf/types/known/wrapperspb"
)

// Policy carries a normalized v1 policy. The adapter owns contract validation;
// this translator additionally rejects values Envoy cannot represent.
type Policy struct {
	ID, Type string
	Config   map[string]interface{}
}

const corsFilter = "envoy.filters.http.cors"
const limitFilter = "envoy.filters.http.local_ratelimit"
const rbacFilter = "envoy.filters.http.rbac"

func policyHTTPFilters() []*hcm.HttpFilter {
	return []*hcm.HttpFilter{
		{Name: corsFilter, ConfigType: &hcm.HttpFilter_TypedConfig{TypedConfig: typed(&cors.Cors{})}},
		{Name: limitFilter, ConfigType: &hcm.HttpFilter_TypedConfig{TypedConfig: typed(&limit.LocalRateLimit{StatPrefix: "stoa_local"})}},
		{Name: rbacFilter, ConfigType: &hcm.HttpFilter_TypedConfig{TypedConfig: typed(&rbac.RBAC{})}},
	}
}

func hundred() *core.RuntimeFractionalPercent {
	return &core.RuntimeFractionalPercent{DefaultValue: &typepb.FractionalPercent{Numerator: 100, Denominator: typepb.FractionalPercent_HUNDRED}}
}

// PolicyConfigs emits one configuration per filter, never an implicit merge.
func PolicyConfigs(policies []Policy) (map[string]*anypb.Any, error) {
	result := map[string]*anypb.Any{}
	for _, p := range policies {
		name, config, err := translatePolicy(p)
		if err != nil {
			return nil, err
		}
		if _, duplicate := result[name]; duplicate {
			return nil, fmt.Errorf("conflicting policies for one route")
		}
		result[name] = config
	}
	return result, nil
}

func translatePolicy(p Policy) (string, *anypb.Any, error) {
	// Decode normalized JSON into projection fields, without another schema table.
	var c struct {
		Origins     []string `json:"allowedOrigins"`
		Methods     []string `json:"allowedMethods"`
		Headers     []string `json:"allowedHeaders"`
		Expose      []string `json:"exposeHeaders"`
		Age         uint64   `json:"maxAge"`
		Credentials bool     `json:"allowCredentials"`
		Requests    uint64   `json:"maxRequests"`
		Interval    uint64   `json:"intervalSeconds"`
		Mode        string   `json:"mode"`
		Addresses   []string `json:"ip_list"`
	}
	data, err := json.Marshal(p.Config)
	if err == nil {
		err = json.Unmarshal(data, &c)
	}
	if err != nil {
		return "", nil, fmt.Errorf("invalid policy projection")
	}
	switch p.Type {
	case "cors":
		cfg := &cors.CorsPolicy{AllowMethods: strings.Join(c.Methods, ","), AllowHeaders: strings.Join(c.Headers, ","), ExposeHeaders: strings.Join(c.Expose, ","), MaxAge: strconv.FormatUint(c.Age, 10), AllowCredentials: wrapperspb.Bool(c.Credentials)}
		for _, origin := range c.Origins {
			m := &matcher.StringMatcher{MatchPattern: &matcher.StringMatcher_Exact{Exact: origin}}
			if origin == "*" {
				m.MatchPattern = &matcher.StringMatcher_SafeRegex{SafeRegex: &matcher.RegexMatcher{Regex: ".*"}}
			}
			cfg.AllowOriginStringMatch = append(cfg.AllowOriginStringMatch, m)
		}
		if err = cfg.ValidateAll(); err != nil {
			return "", nil, fmt.Errorf("invalid CORS projection")
		}
		return corsFilter, typed(cfg), nil
	case "rate_limit":
		if c.Requests == 0 || c.Requests > math.MaxUint32 || c.Interval == 0 || c.Interval > uint64(math.MaxInt64/int64(time.Second)) {
			return "", nil, fmt.Errorf("rate limit exceeds Envoy bounds")
		}
		cfg := &limit.LocalRateLimit{StatPrefix: "stoa_local", TokenBucket: &typepb.TokenBucket{MaxTokens: uint32(c.Requests), TokensPerFill: wrapperspb.UInt32(uint32(c.Requests)), FillInterval: durationpb.New(time.Duration(c.Interval) * time.Second)}, FilterEnabled: hundred(), FilterEnforced: hundred()}
		if err = cfg.ValidateAll(); err != nil {
			return "", nil, fmt.Errorf("invalid rate limit projection")
		}
		return limitFilter, typed(cfg), nil
	case "ip_filter":
		action := rbacconfig.RBAC_ALLOW
		if strings.EqualFold(c.Mode, "deny") {
			action = rbacconfig.RBAC_DENY
		} else if !strings.EqualFold(c.Mode, "allow") {
			return "", nil, fmt.Errorf("invalid address filter mode")
		}
		principals := []*rbacconfig.Principal{}
		for _, value := range c.Addresses {
			prefix, e := netip.ParsePrefix(value)
			if e != nil {
				ip, addrErr := netip.ParseAddr(value)
				if addrErr != nil {
					return "", nil, fmt.Errorf("invalid address filter entry")
				}
				prefix = netip.PrefixFrom(ip, ip.BitLen())
			}
			if prefix.Addr().Zone() != "" {
				return "", nil, fmt.Errorf("invalid address filter entry")
			}
			prefix = prefix.Masked()
			principals = append(principals, &rbacconfig.Principal{Identifier: &rbacconfig.Principal_DirectRemoteIp{DirectRemoteIp: &core.CidrRange{AddressPrefix: prefix.Addr().String(), PrefixLen: wrapperspb.UInt32(uint32(prefix.Bits()))}}})
		}
		rules := map[string]*rbacconfig.Policy{}
		if len(principals) > 0 {
			rules["stoa"] = &rbacconfig.Policy{Permissions: []*rbacconfig.Permission{{Rule: &rbacconfig.Permission_Any{Any: true}}}, Principals: principals}
		}
		cfg := &rbac.RBACPerRoute{Rbac: &rbac.RBAC{Rules: &rbacconfig.RBAC{Action: action, Policies: rules}}}
		if err = cfg.ValidateAll(); err != nil {
			return "", nil, fmt.Errorf("invalid address filter projection")
		}
		return rbacFilter, typed(cfg), nil
	}
	return "", nil, fmt.Errorf("unsupported Envoy policy")
}
