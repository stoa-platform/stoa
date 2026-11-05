package xds

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"

	bootstrap "github.com/envoyproxy/go-control-plane/envoy/config/bootstrap/v3"
	cluster "github.com/envoyproxy/go-control-plane/envoy/config/cluster/v3"
	listener "github.com/envoyproxy/go-control-plane/envoy/config/listener/v3"
	route "github.com/envoyproxy/go-control-plane/envoy/config/route/v3"
	hcm "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/network/http_connection_manager/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/anypb"
	"google.golang.org/protobuf/types/known/durationpb"
)

type memoryAuth struct {
	auth.UnimplementedAuthorizationServer
}

func (memoryAuth) Check(context.Context, *auth.CheckRequest) (*auth.CheckResponse, error) {
	return &auth.CheckResponse{}, nil
}

func memoryCheck(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

type memoryResult struct {
	Bytes       int64  `json:"bytes"`
	Direction   string `json:"direction"`
	BaselineKiB int64  `json:"baseline_rss_kib"`
	PeakKiB     int64  `json:"peak_rss_kib"`
}

func memoryRSS(t *testing.T, pid int, field string) int64 {
	t.Helper()
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/status", pid))
	memoryCheck(t, err)
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, field+":") {
			value, err := strconv.ParseInt(strings.Fields(line)[1], 10, 64)
			if err != nil {
				t.Fatal(err)
			}
			return value
		}
	}
	t.Fatalf("missing %s", field)
	return 0
}

// Opt-in: the wrapper runs this binary inside the unmodified POC Envoy image.
func TestImageMemory(t *testing.T) {
	if os.Getenv("IMAGE_MEMORY") != "1" {
		t.Skip("use scripts/bench/gateway_image_memory.py")
	}
	var results []memoryResult
	for _, size := range []int64{50_000_000, 1_000_000_000, 5_000_000_000} {
		for _, direction := range []string{"upload", "download"} {
			t.Run(fmt.Sprintf("%d/%s", size, direction), func(t *testing.T) {
				results = append(results, measureImage(t, size, direction))
			})
		}
	}
	if t.Failed() {
		return
	}
	data, err := json.MarshalIndent(results, "", "  ")
	memoryCheck(t, err)
	if err = os.WriteFile("/evidence/results.json", data, 0600); err != nil {
		t.Fatal(err)
	}
}

func measureImage(t *testing.T, size int64, direction string) memoryResult {
	t.Helper()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			n, err := io.Copy(io.Discard, r.Body)
			if err != nil || n != size {
				w.WriteHeader(400)
				return
			}
			fmt.Fprint(w, n)
			return
		}
		w.Header().Set("Content-Length", strconv.FormatInt(size, 10))
		_, _ = io.CopyN(w, memoryZeros{}, size)
	}))
	defer upstream.Close()
	authListener, err := net.Listen("tcp", "127.0.0.1:0")
	memoryCheck(t, err)
	server := grpc.NewServer()
	auth.RegisterAuthorizationServer(server, memoryAuth{})
	go func() { _ = server.Serve(authListener) }()
	defer server.Stop()
	reserved, err := net.Listen("tcp", "127.0.0.1:0")
	memoryCheck(t, err)
	port := uint32(reserved.Addr().(*net.TCPAddr).Port)
	_ = reserved.Close()
	c := Config{NodeID: "memory", ListenerPort: port, AuthCluster: "auth", AuthAddress: authListener.Addr().String(), AuthTimeout: time.Second, AckTimeout: time.Second}
	snapshot, err := BuildSnapshot(c, []Route{{ID: "memory", TenantID: "test", APIID: "test", Path: "/", Backend: upstream.URL}})
	memoryCheck(t, err)
	l := snapshot.GetResources(resource.ListenerType)["listener"].(*listener.Listener)
	manager := &hcm.HttpConnectionManager{}
	if err = l.FilterChains[0].Filters[0].GetTypedConfig().UnmarshalTo(manager); err != nil {
		t.Fatal(err)
	}
	rc := snapshot.GetResources(resource.RouteType)["routes"].(*route.RouteConfiguration)
	// Retain generated filters; inline ADS and extend the default 15s route timeout.
	rc.VirtualHosts[0].Routes[0].GetRoute().Timeout = durationpb.New(120 * time.Second)
	manager.RouteSpecifier = &hcm.HttpConnectionManager_RouteConfig{RouteConfig: rc}
	packed, err := anypb.New(manager)
	memoryCheck(t, err)
	l.FilterChains[0].Filters[0].ConfigType = &listener.Filter_TypedConfig{TypedConfig: packed}
	b := &bootstrap.Bootstrap{StaticResources: &bootstrap.Bootstrap_StaticResources{Listeners: []*listener.Listener{l}}}
	for _, v := range snapshot.GetResources(resource.ClusterType) {
		b.StaticResources.Clusters = append(b.StaticResources.Clusters, v.(*cluster.Cluster))
	}
	data, err := protojson.Marshal(b)
	memoryCheck(t, err)
	file := fmt.Sprintf("/evidence/envoy-%d-%s.json", size, direction)
	if err = os.WriteFile(file, data, 0600); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command("/usr/local/bin/envoy", "-c", file, "--concurrency", "1", "--disable-hot-restart", "--log-level", "error")
	cmd.Stderr = os.Stderr
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = cmd.Process.Kill(); _ = cmd.Wait() }()
	address := fmt.Sprintf("127.0.0.1:%d", port)
	deadline := time.Now().Add(10 * time.Second)
	for {
		conn, err := net.DialTimeout("tcp", address, 50*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("Envoy listener timeout")
		}
		time.Sleep(20 * time.Millisecond)
	}
	baseline := memoryRSS(t, cmd.Process.Pid, "VmRSS")
	client := &http.Client{Timeout: 120 * time.Second}
	defer client.CloseIdleConnections()
	method := "GET"
	var body io.Reader
	if direction == "upload" {
		method = "POST"
		body = io.LimitReader(memoryZeros{}, size)
	}
	req, err := http.NewRequest(method, "http://"+address+"/", body)
	memoryCheck(t, err)
	if body != nil {
		req.ContentLength = size
	}
	res, err := client.Do(req)
	memoryCheck(t, err)
	defer res.Body.Close()
	if res.StatusCode != 200 {
		t.Fatalf("HTTP %d", res.StatusCode)
	}
	if direction == "upload" {
		answer, err := io.ReadAll(res.Body)
		if err != nil || string(answer) != strconv.FormatInt(size, 10) {
			t.Fatal("upload byte count mismatch")
		}
	} else {
		n, err := io.Copy(io.Discard, res.Body)
		if err != nil || n != size {
			t.Fatalf("download: %d bytes, %v", n, err)
		}
	}
	return memoryResult{size, direction, baseline, memoryRSS(t, cmd.Process.Pid, "VmHWM")}
}

type memoryZeros struct{}

func (memoryZeros) Read(p []byte) (int, error) {
	clear(p)
	return len(p), nil
}
