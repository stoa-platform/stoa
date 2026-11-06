package xds

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	bootstrap "github.com/envoyproxy/go-control-plane/envoy/config/bootstrap/v3"
	cluster "github.com/envoyproxy/go-control-plane/envoy/config/cluster/v3"
	listener "github.com/envoyproxy/go-control-plane/envoy/config/listener/v3"
	route "github.com/envoyproxy/go-control-plane/envoy/config/route/v3"
	authconfig "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_authz/v3"
	hcm "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/network/http_connection_manager/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
)

// Exercise the production snapshot both with and without the supported policies.
func TestStreamingFilterContract(t *testing.T) {
	host, _, err := net.SplitHostPort(config().AuthAddress)
	if err != nil {
		t.Fatal(err)
	}
	for _, policies := range [][]Policy{nil, {
		{ID: "cors", Type: "cors", Config: map[string]interface{}{"allowedOrigins": []string{"*"}}},
		{ID: "limit", Type: "rate_limit", Config: map[string]interface{}{"maxRequests": 100, "intervalSeconds": 1}},
		{ID: "ip", Type: "ip_filter", Config: map[string]interface{}{"mode": "deny", "ip_list": []string{host}}},
	}} {
		rs := routes()
		rs[0].Policies = policies
		s, err := BuildSnapshot(config(), rs)
		if err != nil {
			t.Fatal(err)
		}
		l := s.GetResources(resource.ListenerType)["listener"].(*listener.Listener)
		m := &hcm.HttpConnectionManager{}
		if err := l.FilterChains[0].Filters[0].GetTypedConfig().UnmarshalTo(m); err != nil {
			t.Fatal(err)
		}
		for _, f := range m.HttpFilters {
			switch f.Name {
			case "envoy.filters.http.ext_authz":
				a := &authconfig.ExtAuthz{}
				if err := f.GetTypedConfig().UnmarshalTo(a); err != nil {
					t.Fatal(err)
				}
				if a.WithRequestBody != nil {
					t.Fatal("authorization must not buffer request bodies")
				}
			case "envoy.filters.http.router", corsFilter, limitFilter, rbacFilter:
			default:
				t.Fatalf("review body streaming before adding filter %s", f.Name)
			}
		}
		rc := s.GetResources(resource.RouteType)["routes"].(*route.RouteConfiguration)
		for _, vh := range rc.VirtualHosts {
			for _, r := range vh.Routes {
				a := &authconfig.ExtAuthzPerRoute{}
				if err := r.TypedPerFilterConfig["envoy.filters.http.ext_authz"].UnmarshalTo(a); err != nil {
					t.Fatal(err)
				}
				if a.GetCheckSettings().GetWithRequestBody() != nil {
					t.Fatal("route authorization buffers bodies")
				}
			}
		}
	}
}

type streamingAuthorization struct {
	auth.UnimplementedAuthorizationServer
}

func (streamingAuthorization) Check(context.Context, *auth.CheckRequest) (*auth.CheckResponse, error) {
	return &auth.CheckResponse{Status: status.New(codes.OK, "").Proto()}, nil
}

// Run with ENVOY_BINARY pointing to a local Envoy executable. A producer cannot
// send EOF until its first fragment reaches the consumer: full buffering deadlocks.
func TestEnvoyStreamingRelay(t *testing.T) {
	binary := os.Getenv("ENVOY_BINARY")
	if binary == "" {
		t.Skip("set ENVOY_BINARY to run the real Envoy streaming proof")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	received := make(chan struct{})
	release := make(chan struct{})
	defer close(release)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			first := make([]byte, 5)
			if _, err := io.ReadFull(r.Body, first); err != nil || string(first) != "first" {
				return
			}
			close(received)
			rest, err := io.ReadAll(r.Body)
			if err != nil || string(rest) != "last" {
				w.WriteHeader(400)
				return
			}
			_, _ = io.WriteString(w, "uploaded")
			return
		}
		_, _ = io.WriteString(w, "first")
		w.(http.Flusher).Flush()
		select {
		case <-release:
		case <-r.Context().Done():
			return
		}
		_, _ = io.WriteString(w, "last")
	}))
	defer upstream.Close()
	authListener, err := net.Listen("tcp4", "localhost:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	auth.RegisterAuthorizationServer(server, streamingAuthorization{})
	go func() { _ = server.Serve(authListener) }()
	defer server.Stop()
	reserved, err := net.Listen("tcp4", "localhost:0")
	if err != nil {
		t.Fatal(err)
	}
	port := uint32(reserved.Addr().(*net.TCPAddr).Port)
	_ = reserved.Close()
	c := config()
	c.ListenerPort, c.AuthAddress = port, authListener.Addr().String()
	s, err := BuildSnapshot(c, []Route{{TenantID: "test", APIID: "test", ID: "test", Path: "/", Backend: upstream.URL}})
	if err != nil {
		t.Fatal(err)
	}
	l := s.GetResources(resource.ListenerType)["listener"].(*listener.Listener)
	m := &hcm.HttpConnectionManager{}
	if err = l.FilterChains[0].Filters[0].GetTypedConfig().UnmarshalTo(m); err != nil {
		t.Fatal(err)
	}
	// Only replace ADS delivery with an inline route; preserve the generated filters.
	m.RouteSpecifier = &hcm.HttpConnectionManager_RouteConfig{RouteConfig: s.GetResources(resource.RouteType)["routes"].(*route.RouteConfiguration)}
	l.FilterChains[0].Filters[0].ConfigType = &listener.Filter_TypedConfig{TypedConfig: typed(m)}
	b := &bootstrap.Bootstrap{StaticResources: &bootstrap.Bootstrap_StaticResources{Listeners: []*listener.Listener{l}}}
	for _, v := range s.GetResources(resource.ClusterType) {
		b.StaticResources.Clusters = append(b.StaticResources.Clusters, v.(*cluster.Cluster))
	}
	data, err := protojson.Marshal(b)
	if err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(t.TempDir(), "envoy.json")
	if err = os.WriteFile(file, data, 0600); err != nil {
		t.Fatal(err)
	}
	cmd := exec.CommandContext(ctx, binary, "-c", file, "--concurrency", "1", "--disable-hot-restart", "--log-level", "error")
	cmd.Stderr = os.Stderr
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = cmd.Process.Kill(); _ = cmd.Wait() }()
	url := fmt.Sprintf("http://localhost:%d/", port)
	for {
		conn, err := net.DialTimeout("tcp4", fmt.Sprintf("localhost:%d", port), 50*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			break
		}
		select {
		case <-ctx.Done():
			t.Fatal("Envoy listener did not start")
		case <-time.After(20 * time.Millisecond):
		}
	}
	client := &http.Client{Timeout: 5 * time.Second}
	defer client.CloseIdleConnections()
	reader, writer := io.Pipe()
	defer func() { _ = reader.Close() }()
	defer func() { _ = writer.Close() }()
	upload := make(chan error, 1)
	go func() {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, reader)
		if err != nil {
			upload <- err
			return
		}
		res, err := client.Do(req)
		if err == nil {
			defer func() { _ = res.Body.Close() }()
			body, readErr := io.ReadAll(res.Body)
			err = readErr
			if string(body) != "uploaded" {
				err = fmt.Errorf("unexpected upload response: %s", body)
			}
		}
		upload <- err
	}()
	if _, err = io.WriteString(writer, "first"); err != nil {
		t.Fatal(err)
	}
	select {
	case <-received:
	case <-time.After(2 * time.Second):
		t.Fatal("request buffered before upstream received first fragment")
	}
	if _, err = io.WriteString(writer, "last"); err != nil {
		t.Fatal(err)
	}
	_ = writer.Close()
	if err = <-upload; err != nil {
		t.Fatal(err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		t.Fatal(err)
	}
	res, err := client.Do(req)
	if err != nil {
		t.Fatalf("response buffered before headers/first fragment: %v", err)
	}
	defer func() { _ = res.Body.Close() }()
	first := make([]byte, 5)
	if _, err = io.ReadFull(res.Body, first); err != nil || string(first) != "first" {
		t.Fatalf("first response fragment: %q, %v", first, err)
	}
	release <- struct{}{}
	rest, err := io.ReadAll(res.Body)
	if err != nil || string(rest) != "last" {
		t.Fatalf("response tail: %q, %v", rest, err)
	}
}
