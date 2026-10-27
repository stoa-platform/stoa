//go:build o1integration

package connect

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typepb "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
	"github.com/stoa-platform/stoa-go/internal/xds"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/status"
)

type o1Auth struct {
	auth.UnimplementedAuthorizationServer
	mode  atomic.Int32
	calls atomic.Int64
}

func (s *o1Auth) Check(ctx context.Context, r *auth.CheckRequest) (*auth.CheckResponse, error) {
	s.calls.Add(1)
	if r.GetAttributes().GetRequest().GetHttp().GetPath() == "" {
		return nil, status.Error(codes.InvalidArgument, "missing HTTP request")
	}
	switch s.mode.Load() {
	case 1:
		return &auth.CheckResponse{Status: status.New(codes.PermissionDenied, "denied").Proto(), HttpResponse: &auth.CheckResponse_DeniedResponse{DeniedResponse: &auth.DeniedHttpResponse{Status: &typepb.HttpStatus{Code: typepb.StatusCode_Forbidden}}}}, nil
	case 2:
		return nil, status.Error(codes.Unavailable, "test outage")
	case 3:
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	return &auth.CheckResponse{Status: status.New(codes.OK, "").Proto()}, nil
}

type o1Route struct {
	Name  string                     `json:"name"`
	Typed map[string]json.RawMessage `json:"typed_per_filter_config"`
}
type o1State struct {
	version string
	routes  map[string]o1Route
}

// o1PolicyFixture exposes only the local witnesses needed by the optional policy phase.
type o1PolicyFixture struct {
	t                                               *testing.T
	gatewayID, targetCatalog, targetPath, otherPath string
	request                                         func(string, string, interface{}, interface{}) time.Time
	state                                           func() o1State
	eventually                                      func(time.Duration, string, func() bool)
	call                                            func(string, string, map[string]string) (int, http.Header)
	authorization                                   *o1Auth
	upstreamCalls                                   *atomic.Int64
}

// The route harness runs independently when the policy test file is absent.
var o1PoliciesPhase func(o1PolicyFixture) (map[string]interface{}, func())

func TestO1OfflineEnvoy(t *testing.T) {
	cp := os.Getenv("O1_CP_URL")
	if cp == "" {
		t.Skip("local CP fixture required")
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	dir := t.TempDir()
	listen := func() net.Listener {
		l, e := net.Listen("tcp", ":0")
		if e != nil {
			t.Fatal(e)
		}
		t.Cleanup(func() { _ = l.Close() })
		return l
	}
	port := func(l net.Listener) int {
		_, p, _ := net.SplitHostPort(l.Addr().String())
		n, _ := strconv.Atoi(p)
		return n
	}
	upstreamCalls := atomic.Int64{}
	upstream := listen()
	httpServer := &http.Server{ReadHeaderTimeout: time.Second, Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		upstreamCalls.Add(1)
		w.Header().Set("X-O1-Upstream", "true")
		w.WriteHeader(http.StatusOK)
	})}
	go func() { _ = httpServer.Serve(upstream) }()
	defer func() { _ = httpServer.Close() }()
	authorization := &o1Auth{}
	authListener := listen()
	authServer := grpc.NewServer()
	auth.RegisterAuthorizationServer(authServer, authorization)
	go func() { _ = authServer.Serve(authListener) }()
	defer authServer.Stop()
	tlsConfig, node := o1TLS(t, dir)
	adsListener := listen()
	grpcServer := grpc.NewServer(grpc.Creds(credentials.NewTLS(tlsConfig)))
	dataListener := listen()
	dataPort := port(dataListener)
	_ = dataListener.Close()
	ads, err := xds.NewServer(xds.Config{NodeID: node, ListenerPort: uint32(dataPort), AuthCluster: "authorization", AuthAddress: fmt.Sprintf("localhost:%d", port(authListener)), AuthTimeout: time.Second, AckTimeout: 5 * time.Second}, grpcServer, o1VerifiedIdentity)
	if err != nil {
		t.Fatal(err)
	}
	defer ads.Close()
	go func() { _ = grpcServer.Serve(adsListener) }()
	adminSocket := filepath.Join(dir, "admin.sock")
	bootstrap := fmt.Sprintf(`node: {id: deliberately-untrusted-node, cluster: o1}
admin: {address: {pipe: {path: %q}}}
dynamic_resources:
  ads_config: {api_type: GRPC, transport_api_version: V3, grpc_services: [{envoy_grpc: {cluster_name: xds}}]}
  cds_config: {ads: {}, resource_api_version: V3}
  lds_config: {ads: {}, resource_api_version: V3}
static_resources:
  clusters:
  - name: xds
    type: STRICT_DNS
    connect_timeout: 1s
    http2_protocol_options: {}
    load_assignment:
      cluster_name: xds
      endpoints: [{lb_endpoints: [{endpoint: {address: {socket_address: {address: localhost, port_value: %d}}}}]}]
    transport_socket:
      name: envoy.transport_sockets.tls
      typed_config:
        "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
        sni: localhost
        common_tls_context:
          tls_params: {tls_minimum_protocol_version: TLSv1_3, tls_maximum_protocol_version: TLSv1_3}
          tls_certificates: [{certificate_chain: {filename: %q}, private_key: {filename: %q}}]
          validation_context: {trusted_ca: {filename: %q}, match_typed_subject_alt_names: [{san_type: DNS, matcher: {exact: localhost}}]}
`, adminSocket, port(adsListener), filepath.Join(dir, "client.crt"), filepath.Join(dir, "client.key"), filepath.Join(dir, "ca.crt"))
	configFile := filepath.Join(dir, "bootstrap.yaml")
	if err = os.WriteFile(configFile, []byte(bootstrap), 0600); err != nil {
		t.Fatal(err)
	}
	envoy := exec.CommandContext(ctx, "/usr/local/bin/envoy", "-c", configFile, "--concurrency", "1", "--disable-hot-restart", "--log-level", "warning")
	var envoyLogs bytes.Buffer
	envoy.Stdout = &envoyLogs
	envoy.Stderr = &envoyLogs
	if err = envoy.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() {
		_ = envoy.Process.Kill()
		_ = envoy.Wait()
		if t.Failed() {
			for _, line := range strings.Split(envoyLogs.String(), "\n") {
				if strings.Contains(line, "[warning]") || strings.Contains(line, "[error]") {
					// Envoy diagnostics may contain resolved local addresses.
					line = regexp.MustCompile(`\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b`).ReplaceAllString(line, "[local address]")
					line = regexp.MustCompile(`\[[0-9a-fA-F:]+\]`).ReplaceAllString(line, "[local address]")
					t.Log(line)
				}
			}
		}
	}()
	client := &http.Client{Timeout: 2 * time.Second}
	admin := &http.Client{Timeout: time.Second, Transport: &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", adminSocket)
	}}}
	defer admin.CloseIdleConnections()
	defer client.CloseIdleConnections()
	request := func(method, path string, body interface{}, out interface{}) time.Time {
		t.Helper()
		var payload io.Reader
		if body != nil {
			data, e := json.Marshal(body)
			if e != nil {
				t.Fatal(e)
			}
			payload = bytes.NewReader(data)
		}
		req, e := http.NewRequest(method, cp+path, payload)
		if e != nil {
			t.Fatal(e)
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Gateway-Key", "o1-local-test-key")
		response, e := client.Do(req)
		if e != nil {
			t.Fatal(e)
		}
		defer func() { _ = response.Body.Close() }()
		data, e := io.ReadAll(response.Body)
		if e != nil {
			t.Fatal(e)
		}
		completed := time.Now()
		if response.StatusCode < 200 || response.StatusCode >= 300 {
			t.Fatalf("CP %s %s: %d %s", method, path, response.StatusCode, string(data))
		}
		if out != nil {
			if e = json.Unmarshal(data, out); e != nil {
				t.Fatal(e)
			}
		}
		return completed
	}
	var ids struct{ Own, Foreign string }
	request("GET", "/o1/identity", nil, &ids)
	state := func() o1State {
		t.Helper()
		result := o1State{routes: map[string]o1Route{}}
		response, e := admin.Get("http://admin/config_dump")
		if e != nil {
			return result
		}
		defer func() { _ = response.Body.Close() }()
		var dump struct {
			Configs []struct {
				Dynamic []struct {
					Version string `json:"version_info"`
					Config  struct {
						Hosts []struct {
							Routes []o1Route `json:"routes"`
						} `json:"virtual_hosts"`
					} `json:"route_config"`
				} `json:"dynamic_route_configs"`
			} `json:"configs"`
		}
		if json.NewDecoder(response.Body).Decode(&dump) != nil {
			return result
		}
		for _, config := range dump.Configs {
			for _, dynamic := range config.Dynamic {
				result.version = dynamic.Version
				for _, host := range dynamic.Config.Hosts {
					for _, r := range host.Routes {
						result.routes[r.Name] = r
					}
				}
			}
		}
		return result
	}
	eventually := func(timeout time.Duration, description string, check func() bool) {
		t.Helper()
		deadline := time.Now().Add(timeout)
		for {
			if check() {
				return
			}
			if time.Now().After(deadline) {
				t.Fatalf("timeout: %s", description)
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	dataURL := fmt.Sprintf("http://localhost:%d", dataPort)
	call := func(method, path string, headers map[string]string) (int, http.Header) {
		req, _ := http.NewRequest(method, dataURL+path, nil)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		response, e := client.Do(req)
		if e != nil {
			return 0, nil
		}
		_, _ = io.Copy(io.Discard, response.Body)
		_ = response.Body.Close()
		return response.StatusCode, response.Header
	}
	get := func(path string, headers map[string]string) (int, http.Header) {
		return call(http.MethodGet, path, headers)
	}
	startAgent := func() (*Agent, *adapters.EnvoyAdapter, func()) {
		agent := New(Config{ControlPlaneURL: cp, GatewayAPIKey: "o1-local-test-key", InstanceName: "own"})
		agent.state.SetGatewayID(ids.Own)
		adapter := adapters.NewEnvoyAdapter(ads)
		agentCtx, stop := context.WithCancel(ctx)
		done := make(chan struct{})
		go func() {
			defer close(done)
			runSSEStream(agentCtx, agent, adapter, "envoy", backoffPolicy{Initial: 10 * time.Millisecond, Max: 100 * time.Millisecond, Multiplier: 2})
		}()
		return agent, adapter, func() { stop(); <-done }
	}
	agent, adapter, stop := startAgent()
	defer func() { stop() }()
	eventually(15*time.Second, "initial Envoy ADS acknowledgement", func() bool { return state().version != "" })
	type publication struct {
		ID           string  `json:"deployment_id"`
		Catalog      string  `json:"catalog_id"`
		Path         string  `json:"path"`
		Milliseconds float64 `json:"latency_ms"`
	}
	publications := []publication{}
	publish := func(number int, foreign bool) publication {
		api := fmt.Sprintf("o1-%02d", number)
		var catalog struct{ ID string }
		request("POST", "/o1/catalog", map[string]interface{}{"api_id": api, "backend_url": fmt.Sprintf("http://localhost:%d", port(upstream))}, &catalog)
		gateway := ids.Own
		if foreign {
			gateway = ids.Foreign
		}
		var deployments []struct{ ID string }
		t0 := request("POST", "/v1/admin/deployments", map[string]interface{}{"api_catalog_id": catalog.ID, "gateway_instance_ids": []string{gateway}}, &deployments)
		p := publication{ID: deployments[0].ID, Catalog: catalog.ID, Path: "/apis/" + api + "/ping"}
		if !foreign {
			before := len(publications)
			eventually(5*time.Second, "published route visible and serving 200", func() bool {
				current := state()
				if len(current.routes) < before {
					t.Fatal("route count decreased without removal")
				}
				if len(current.routes) == 0 && before > 0 {
					t.Fatal("ZERO_ROUTE")
				}
				_, exists := current.routes[catalog.ID]
				code, h := get(p.Path, nil)
				return exists && len(current.routes) == before+1 && code == 200 && h.Get("X-O1-Upstream") == "true"
			})
			p.Milliseconds = float64(time.Since(t0).Microseconds()) / 1000
			if p.Milliseconds >= 5000 {
				t.Fatal("publication exceeded five seconds")
			}
			eventually(5*time.Second, "CP received applied acknowledgement", func() bool {
				var config GatewayConfigResponse
				request("GET", "/v1/internal/gateways/"+ids.Own+"/config", nil, &config)
				for _, dep := range config.PendingDeployments {
					if dep.ID == p.ID && dep.SyncStatus == "synced" {
						return true
					}
				}
				return false
			})
		}
		return p
	}
	for i := 1; i <= 10; i++ {
		publications = append(publications, publish(i, false))
	}
	initial := state()
	publish(12, true)
	endForeign := time.Now().Add(5 * time.Second)
	for time.Now().Before(endForeign) {
		current := state()
		if current.version != initial.version || len(current.routes) != 10 {
			t.Fatal("foreign publication altered own snapshot")
		}
		time.Sleep(100 * time.Millisecond)
	}
	remove := func(p publication, count int) float64 {
		t0 := request("DELETE", "/v1/admin/deployments/"+p.ID, nil, nil)
		eventually(5*time.Second, "explicit removal served as 404", func() bool {
			current := state()
			_, present := current.routes[p.Catalog]
			code, _ := get(p.Path, nil)
			return !present && len(current.routes) == count && code == 404
		})
		return float64(time.Since(t0).Microseconds()) / 1000
	}
	undeployMS := remove(publications[0], 9)
	stop()
	code, _ := get(publications[1].Path, nil)
	if code != 200 {
		t.Fatal("last snapshot not retained while disconnected")
	}
	// Publish during the outage, then reconstruct using a fresh agent/adapter.
	pending := publication{}
	api := "o1-11"
	var catalog struct{ ID string }
	request("POST", "/o1/catalog", map[string]interface{}{"api_id": api, "backend_url": fmt.Sprintf("http://localhost:%d", port(upstream))}, &catalog)
	var deployment []struct{ ID string }
	request("POST", "/v1/admin/deployments", map[string]interface{}{"api_catalog_id": catalog.ID, "gateway_instance_ids": []string{ids.Own}}, &deployment)
	pending = publication{ID: deployment[0].ID, Catalog: catalog.ID, Path: "/apis/" + api + "/ping"}
	reconnectAt := time.Now()
	agent, adapter, stop = startAgent()
	eventually(5*time.Second, "reconnect reconstructed complete route table", func() bool { code, _ := get(pending.Path, nil); return len(state().routes) == 10 && code == 200 })
	reconnectMS := float64(time.Since(reconnectAt).Microseconds()) / 1000
	stable := state()
	request("POST", "/o1/fault", map[string]bool{"empty": true}, nil)
	agent.RunRouteSync(ctx, adapter, "envoy")
	request("POST", "/o1/fault", map[string]bool{"empty": false}, nil)
	if after := state(); len(after.routes) != 10 || after.version != stable.version {
		t.Fatal("unexpected empty CP table erased Envoy")
	}

	policyResults := map[string]interface{}{}
	policyCleanup := func() {}
	if o1PoliciesPhase != nil {
		policyResults, policyCleanup = o1PoliciesPhase(o1PolicyFixture{
			t: t, gatewayID: ids.Own, targetCatalog: publications[1].Catalog,
			targetPath: publications[1].Path, otherPath: publications[2].Path,
			request: request, state: state, eventually: eventually, call: call,
			authorization: authorization, upstreamCalls: &upstreamCalls,
		})
	}
	for _, mode := range []int32{1, 2, 3} {
		authorization.mode.Store(mode)
		before := upstreamCalls.Load()
		code, _ = get(publications[2].Path, nil)
		if code != 403 || upstreamCalls.Load() != before {
			t.Fatalf("authorization mode %d did not fail closed: %d", mode, code)
		}
	}
	authorization.mode.Store(0)
	code, _ = get(publications[2].Path, nil)
	if code != 200 || authorization.calls.Load() == 0 {
		t.Fatal("gRPC authorization chain not exercised")
	}
	policyCleanup()
	remaining := append(append([]publication(nil), publications[1:]...), pending)
	for i, p := range remaining {
		remove(p, len(remaining)-i-1)
	}
	// Removal ACKs must also clear CP tombstones, including the final route.
	eventually(5*time.Second, "CP removal acknowledgements", func() bool {
		var cfg GatewayConfigResponse
		request("GET", "/v1/internal/gateways/"+ids.Own+"/config", nil, &cfg)
		return len(cfg.PendingDeployments) == 0
	})
	durations := make([]float64, 0, 10)
	for _, p := range publications {
		durations = append(durations, p.Milliseconds)
	}
	sort.Float64s(durations)
	result := map[string]interface{}{"verdict": "OK", "candidate_sha": os.Getenv("O1_CANDIDATE_SHA"), "envoy_image": os.Getenv("O1_ENVOY_IMAGE"), "publications": publications, "median_ms": (durations[4] + durations[5]) / 2, "max_ms": durations[9], "threshold_ms": 5000, "undeploy_ms": undeployMS, "reconnect_ms": reconnectMS, "foreign_gateway_unchanged": true, "unexpected_empty_preserved": true, "explicit_final_empty": true, "authz_denial_error_timeout_closed": true, "authz_calls": authorization.calls.Load(), "cp_database": "SQLite with real repositories", "operator_authentication": "fixture dependency", "authorization": "independent gRPC witness; not the Rust adapter"}
	for key, value := range policyResults {
		result[key] = value
	}
	data, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(os.Getenv("O1_RESULT"), append(data, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	t.Logf("10 publications: median %.2f ms, max %.2f ms; reconnect %.2f ms; authz checks %d", (durations[4]+durations[5])/2, durations[9], reconnectMS, authorization.calls.Load())
}
