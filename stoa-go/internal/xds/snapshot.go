// Package xds builds and serves single-node state-of-the-world snapshots.
package xds

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"

	cluster "github.com/envoyproxy/go-control-plane/envoy/config/cluster/v3"
	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	endpoint "github.com/envoyproxy/go-control-plane/envoy/config/endpoint/v3"
	listener "github.com/envoyproxy/go-control-plane/envoy/config/listener/v3"
	route "github.com/envoyproxy/go-control-plane/envoy/config/route/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_authz/v3"
	router "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/router/v3"
	hcm "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/network/http_connection_manager/v3"
	tls "github.com/envoyproxy/go-control-plane/envoy/extensions/transport_sockets/tls/v3"
	cachetypes "github.com/envoyproxy/go-control-plane/pkg/cache/types"
	cache "github.com/envoyproxy/go-control-plane/pkg/cache/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/anypb"
	"google.golang.org/protobuf/types/known/durationpb"
)

// Route describes a prefix route and its upstream URL.
type Route struct {
	ID      string
	Path    string
	Methods []string
	Backend string
}

// Config contains the single-node listener and authorization configuration.
// ListenerAddress defaults to loopback; all other fields must be explicit.
type Config struct {
	NodeID          string
	ListenerAddress string
	ListenerPort    uint32
	AuthCluster     string
	AuthAddress     string // host:port
	AuthTimeout     time.Duration
	AckTimeout      time.Duration
}

func typed(m proto.Message) *anypb.Any { a, _ := anypb.New(m); return a }
func address(host string, port uint32) *core.Address {
	return &core.Address{Address: &core.Address_SocketAddress{SocketAddress: &core.SocketAddress{Address: host, PortSpecifier: &core.SocketAddress_PortValue{PortValue: port}}}}
}
func upstream(name, host string, port uint32) *cluster.Cluster {
	kind := cluster.Cluster_STRICT_DNS
	if net.ParseIP(host) != nil {
		kind = cluster.Cluster_STATIC
	}
	return &cluster.Cluster{Name: name, ConnectTimeout: durationpb.New(5 * time.Second), ClusterDiscoveryType: &cluster.Cluster_Type{Type: kind}, LoadAssignment: &endpoint.ClusterLoadAssignment{ClusterName: name, Endpoints: []*endpoint.LocalityLbEndpoints{{LbEndpoints: []*endpoint.LbEndpoint{{HostIdentifier: &endpoint.LbEndpoint_Endpoint{Endpoint: &endpoint.Endpoint{Address: address(host, port)}}}}}}}}
}
func normalize(c Config) (Config, error) {
	if c.ListenerAddress == "" {
		c.ListenerAddress = "127.0.0.1"
	}
	if c.NodeID == "" || c.ListenerPort == 0 || c.ListenerPort > 65535 || c.AuthCluster == "" || c.AuthTimeout <= 0 || c.AckTimeout <= 0 {
		return c, fmt.Errorf("node, ports, cluster and positive timeouts are required")
	}
	if net.ParseIP(c.ListenerAddress) == nil {
		return c, fmt.Errorf("listener address must be an IP literal")
	}
	return c, nil
}

// BuildSnapshot returns a deterministic, internally consistent snapshot.
func BuildSnapshot(config Config, routes []Route) (*cache.Snapshot, error) {
	c, err := normalize(config)
	if err != nil {
		return nil, err
	}
	host, p, err := net.SplitHostPort(c.AuthAddress)
	if err != nil || host == "" {
		return nil, fmt.Errorf("invalid authorization address")
	}
	port, err := strconv.ParseUint(p, 10, 16)
	if err != nil || port == 0 {
		return nil, fmt.Errorf("invalid authorization port")
	}
	ac := upstream(c.AuthCluster, host, uint32(port))
	ac.Http2ProtocolOptions = &core.Http2ProtocolOptions{}
	clusters := []cachetypes.Resource{ac}
	canonical := make([]Route, len(routes))
	for i, r := range routes {
		canonical[i] = r
		canonical[i].Methods = append([]string{}, r.Methods...)
		sort.Strings(canonical[i].Methods)
		canonical[i].Methods = unique(canonical[i].Methods)
	}
	sort.Slice(canonical, func(i, j int) bool { return canonical[i].ID < canonical[j].ID })
	seen := map[string]bool{}
	rc := &route.RouteConfiguration{Name: "routes", VirtualHosts: []*route.VirtualHost{{Name: "default", Domains: []string{"*"}}}}
	for _, r := range canonical {
		if r.ID == "" || seen[r.ID] {
			return nil, fmt.Errorf("empty or duplicate route ID: %q", r.ID)
		}
		seen[r.ID] = true
		if r.Path == "" || !strings.HasPrefix(r.Path, "/") {
			return nil, fmt.Errorf("invalid route path: %q", r.Path)
		}
		u, e := url.Parse(r.Backend)
		if e != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.User != nil || (u.Path != "" && u.Path != "/") || u.RawQuery != "" || u.Fragment != "" {
			return nil, fmt.Errorf("invalid backend URL for %q", r.ID)
		}
		bp := uint64(80)
		if u.Scheme == "https" {
			bp = 443
		}
		if u.Port() != "" {
			bp, e = strconv.ParseUint(u.Port(), 10, 16)
			if e != nil || bp == 0 {
				return nil, fmt.Errorf("invalid backend port")
			}
		}
		name := "backend/" + r.ID
		cl := upstream(name, u.Hostname(), uint32(bp))
		if u.Scheme == "https" {
			cl.TransportSocket = &core.TransportSocket{Name: "envoy.transport_sockets.tls", ConfigType: &core.TransportSocket_TypedConfig{TypedConfig: typed(&tls.UpstreamTlsContext{Sni: u.Hostname(), CommonTlsContext: &tls.CommonTlsContext{ValidationContextType: &tls.CommonTlsContext_ValidationContext{ValidationContext: &tls.CertificateValidationContext{TrustedCa: &core.DataSource{Specifier: &core.DataSource_Filename{Filename: "/etc/ssl/certs/ca-certificates.crt"}}}}}})}}
		}
		clusters = append(clusters, cl)
		methods := r.Methods
		if len(methods) == 0 {
			methods = []string{""}
		}
		for _, m := range methods {
			match := &route.RouteMatch{PathSpecifier: &route.RouteMatch_Prefix{Prefix: r.Path}}
			if m != "" {
				match.Headers = []*route.HeaderMatcher{{Name: ":method", HeaderMatchSpecifier: &route.HeaderMatcher_ExactMatch{ExactMatch: m}}}
			}
			rc.VirtualHosts[0].Routes = append(rc.VirtualHosts[0].Routes, &route.Route{Name: r.ID, Match: match, Action: &route.Route_Route{Route: &route.RouteAction{ClusterSpecifier: &route.RouteAction_Cluster{Cluster: name}}}})
		}
	}
	source := &core.ConfigSource{ResourceApiVersion: core.ApiVersion_V3, ConfigSourceSpecifier: &core.ConfigSource_Ads{Ads: &core.AggregatedConfigSource{}}}
	manager := &hcm.HttpConnectionManager{StatPrefix: "xds", RouteSpecifier: &hcm.HttpConnectionManager_Rds{Rds: &hcm.Rds{RouteConfigName: "routes", ConfigSource: source}}, HttpFilters: []*hcm.HttpFilter{
		{Name: "envoy.filters.http.ext_authz", ConfigType: &hcm.HttpFilter_TypedConfig{TypedConfig: typed(&auth.ExtAuthz{TransportApiVersion: core.ApiVersion_V3, FailureModeAllow: false, Services: &auth.ExtAuthz_GrpcService{GrpcService: &core.GrpcService{TargetSpecifier: &core.GrpcService_EnvoyGrpc_{EnvoyGrpc: &core.GrpcService_EnvoyGrpc{ClusterName: c.AuthCluster}}, Timeout: durationpb.New(c.AuthTimeout)}}})}},
		{Name: "envoy.filters.http.router", ConfigType: &hcm.HttpFilter_TypedConfig{TypedConfig: typed(&router.Router{})}},
	}}
	l := &listener.Listener{Name: "listener", Address: address(c.ListenerAddress, c.ListenerPort), FilterChains: []*listener.FilterChain{{Filters: []*listener.Filter{{Name: "envoy.filters.network.http_connection_manager", ConfigType: &listener.Filter_TypedConfig{TypedConfig: typed(manager)}}}}}}
	data, _ := json.Marshal(struct {
		Config Config
		Routes []Route
	}{c, canonical})
	hash := sha256.Sum256(data)
	s, err := cache.NewSnapshot(hex.EncodeToString(hash[:16]), map[resource.Type][]cachetypes.Resource{resource.ClusterType: clusters, resource.RouteType: {rc}, resource.ListenerType: {l}})
	if err != nil {
		return nil, err
	}
	if err = s.Consistent(); err != nil {
		return nil, err
	}
	return s, nil
}
func unique(values []string) []string {
	out := values[:0]
	for _, v := range values {
		if len(out) == 0 || out[len(out)-1] != v {
			out = append(out, v)
		}
	}
	return out
}
