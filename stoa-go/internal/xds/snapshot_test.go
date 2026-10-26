package xds

import (
	"reflect"
	"strings"
	"testing"
	"time"

	cluster "github.com/envoyproxy/go-control-plane/envoy/config/cluster/v3"
	listener "github.com/envoyproxy/go-control-plane/envoy/config/listener/v3"
	route "github.com/envoyproxy/go-control-plane/envoy/config/route/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_authz/v3"
	hcm "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/network/http_connection_manager/v3"
	upstreamhttp "github.com/envoyproxy/go-control-plane/envoy/extensions/upstreams/http/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
)

func config() Config {
	return Config{NodeID: "own", ListenerPort: 10000, AuthCluster: "authorization", AuthAddress: "127.0.0.1:9000", AuthTimeout: time.Second, AckTimeout: time.Second}
}
func routes() []Route {
	return []Route{{ID: "a", Path: "/a", Methods: []string{"POST", "GET"}, Backend: "https://example.com"}, {ID: "b", Path: "/b", Backend: "http://127.0.0.1:8080"}}
}
func TestSnapshot(t *testing.T) {
	input := routes()
	original := routes()
	s, err := BuildSnapshot(config(), input)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.Consistent(); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(input, original) {
		t.Fatal("mutated input")
	}
	reversed := []Route{input[1], input[0]}
	reversed[1].Methods = []string{"GET", "POST", "GET"}
	other, err := BuildSnapshot(config(), reversed)
	if err != nil {
		t.Fatal(err)
	}
	if s.GetVersion(resource.ClusterType) != other.GetVersion(resource.ClusterType) {
		t.Fatal("order changed version")
	}
	changed := routes()
	changed[0].Path = "/new"
	next, _ := BuildSnapshot(config(), changed)
	if s.GetVersion(resource.ClusterType) == next.GetVersion(resource.ClusterType) {
		t.Fatal("change did not change version")
	}
	l := s.GetResources(resource.ListenerType)["listener"].(*listener.Listener)
	if l.Address.GetSocketAddress().Address != "127.0.0.1" {
		t.Fatal("unsafe default")
	}
	manager := &hcm.HttpConnectionManager{}
	if err = l.FilterChains[0].Filters[0].GetTypedConfig().UnmarshalTo(manager); err != nil {
		t.Fatal(err)
	}
	if len(manager.HttpFilters) != 2 || manager.HttpFilters[0].Name != "envoy.filters.http.ext_authz" || manager.HttpFilters[1].Name != "envoy.filters.http.router" {
		t.Fatal("filter order")
	}
	authorization := &auth.ExtAuthz{}
	if err = manager.HttpFilters[0].GetTypedConfig().UnmarshalTo(authorization); err != nil {
		t.Fatal(err)
	}
	if authorization.FailureModeAllow || authorization.GetGrpcService().GetEnvoyGrpc().ClusterName != "authorization" || authorization.GetGrpcService().Timeout.AsDuration() != time.Second {
		t.Fatal("authorization configuration")
	}
	rc := s.GetResources(resource.RouteType)["routes"].(*route.RouteConfiguration)
	rr := rc.VirtualHosts[0].Routes
	if len(rr) != 3 || rr[0].Match.GetPrefix() != "/a" || rr[0].Match.Headers[0].GetStringMatch().GetExact() != "GET" || rr[1].Match.Headers[0].GetStringMatch().GetExact() != "POST" || len(rr[2].Match.Headers) != 0 {
		t.Fatal("routes or methods")
	}
	cc := s.GetResources(resource.ClusterType)
	if len(cc) != 3 {
		t.Fatal("clusters")
	}
	https := cc["backend/a"].(*cluster.Cluster)
	static := cc["backend/b"].(*cluster.Cluster)
	ac := cc["authorization"].(*cluster.Cluster)
	if https.GetType() != cluster.Cluster_STRICT_DNS || https.TransportSocket == nil || https.LoadAssignment.Endpoints[0].LbEndpoints[0].GetEndpoint().Address.GetSocketAddress().GetPortValue() != 443 || static.GetType() != cluster.Cluster_STATIC {
		t.Fatal("upstream configuration")
	}
	protocolOptions := &upstreamhttp.HttpProtocolOptions{}
	httpOptions := ac.TypedExtensionProtocolOptions["envoy.extensions.upstreams.http.v3.HttpProtocolOptions"]
	if httpOptions == nil {
		t.Fatal("missing authorization HTTP protocol options")
	}
	if err := httpOptions.UnmarshalTo(protocolOptions); err != nil {
		t.Fatal(err)
	}
	if protocolOptions.GetExplicitHttpConfig().GetHttp2ProtocolOptions() == nil {
		t.Fatal("authorization upstream must use HTTP/2")
	}
	empty, err := BuildSnapshot(config(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if err = empty.Consistent(); err != nil {
		t.Fatal(err)
	}
}
func TestInvalidSnapshot(t *testing.T) {
	tests := []struct {
		name string
		c    Config
		r    []Route
	}{
		{"empty path", config(), []Route{{ID: "a", Backend: "http://example.com"}}},
		{"relative path", config(), []Route{{ID: "a", Path: "a", Backend: "http://example.com"}}},
		{"duplicate", config(), []Route{routes()[0], routes()[0]}},
		{"empty ID", config(), []Route{{Path: "/a", Backend: "http://example.com"}}},
	}
	for _, backend := range []string{"", "://", "ftp://example.com", "http://", "http://example.com:0", "http://example.com:99999", "http://user@example.com", "https://example.com/path", "https://example.com?q=1"} {
		r := routes()
		r[0].Backend = backend
		tests = append(tests, struct {
			name string
			c    Config
			r    []Route
		}{"backend " + backend, config(), r})
	}
	for _, addr := range []string{"bad", "localhost:no", "localhost:0", ":9000"} {
		c := config()
		c.AuthAddress = addr
		tests = append(tests, struct {
			name string
			c    Config
			r    []Route
		}{"auth " + addr, c, nil})
	}
	for _, field := range []string{"node", "port", "cluster", "timeout", "ack", "listener"} {
		c := config()
		switch field {
		case "node":
			c.NodeID = ""
		case "port":
			c.ListenerPort = 65536
		case "cluster":
			c.AuthCluster = ""
		case "timeout":
			c.AuthTimeout = 0
		case "ack":
			c.AckTimeout = 0
		case "listener":
			c.ListenerAddress = "localhost"
		}
		tests = append(tests, struct {
			name string
			c    Config
			r    []Route
		}{field, c, nil})
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := BuildSnapshot(tt.c, tt.r); err == nil {
				t.Fatal("expected error")
			}
		})
	}
	c := config()
	c.AuthAddress = "example.com:9000"
	r := routes()
	r[0].Backend = "http://example.com:8081"
	if _, err := BuildSnapshot(c, r); err != nil {
		t.Fatal(err)
	}
	if _, err := NewServer(Config{}, nil, nil); err == nil {
		t.Fatal("invalid server config")
	}
	c = config()
	c.AuthAddress = "bad"
	if _, err := NewServer(c, nil, nil); err == nil || !strings.Contains(err.Error(), "authorization") {
		t.Fatal("invalid authorization config")
	}
}
