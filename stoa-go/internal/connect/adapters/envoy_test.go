package adapters

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"strings"
	"testing"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	routepb "github.com/envoyproxy/go-control-plane/envoy/config/route/v3"
	auth "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/ext_authz/v3"
	discovery "github.com/envoyproxy/go-control-plane/envoy/service/discovery/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"github.com/stoa-platform/stoa-go/internal/xds"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

func TestEnvoySync(t *testing.T) {
	for _, outcome := range []string{"ACK", "NACK", "timeout"} {
		t.Run(outcome, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			s, err := xds.NewServer(xds.Config{NodeID: "verified", ListenerPort: 8080, AuthCluster: "auth", AuthAddress: "127.0.0.1:9000", AuthTimeout: time.Second, AckTimeout: 100 * time.Millisecond}, nil, func(context.Context) (string, error) { return "verified", nil })
			if err != nil {
				t.Fatal(err)
			}
			defer s.Close()
			l := bufconn.Listen(1024 * 1024)
			defer func() {
				if err := l.Close(); err != nil {
					t.Errorf("close l: %v", err)
				}
			}()
			go func() { _ = s.GRPCServer().Serve(l) }()
			conn, err := grpc.NewClient("passthrough:///memory", grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return l.DialContext(ctx) }))
			if err != nil {
				t.Fatal(err)
			}
			defer func() {
				if err := conn.Close(); err != nil {
					t.Errorf("close conn: %v", err)
				}
			}()
			stream, err := discovery.NewAggregatedDiscoveryServiceClient(conn).StreamAggregatedResources(ctx)
			if err != nil {
				t.Fatal(err)
			}
			// This is the desired_state shape emitted by the deployment SSE service.
			var event struct {
				DeploymentID string `json:"deployment_id"`
				DesiredState Route  `json:"desired_state"`
			}
			err = json.Unmarshal([]byte(`{"deployment_id":"deploy","desired_state":{"api_id":"orders","api_catalog_id":"catalog","api_name":"Orders","tenant_id":"tenant","backend_url":"http://127.0.0.1:8000","methods":["GET"],"activated":true}}`), &event)
			if err != nil {
				t.Fatal(err)
			}
			event.DesiredState.DeploymentID = event.DeploymentID
			routes := []Route{event.DesiredState, {TenantID: "tenant", APICatalogID: "catalog-explicit", ID: "explicit", APIID: "ignored", PathPrefix: "/custom", BackendURL: "http://127.0.0.1:8001", Activated: true, DeploymentID: "second"}, {ID: "inactive", PathPrefix: "invalid", Activated: false, DeploymentID: "inactive"}}
			done := make(chan struct {
				result SyncResult
				err    error
			}, 1)
			go func() {
				r, e := NewEnvoyAdapter(s).SyncRoutes(ctx, "", routes)
				done <- struct {
					result SyncResult
					err    error
				}{r, e}
			}()
			if outcome != "timeout" {
				for _, kind := range []string{resource.ClusterType, resource.ListenerType, resource.RouteType} {
					if err = stream.Send(&discovery.DiscoveryRequest{Node: &core.Node{Id: "forged"}, TypeUrl: kind}); err != nil {
						t.Fatal(err)
					}
					response, e := stream.Recv()
					if e != nil {
						t.Fatal(e)
					}
					if kind == resource.RouteType {
						var config routepb.RouteConfiguration
						if e = response.Resources[0].UnmarshalTo(&config); e != nil {
							t.Fatal(e)
						}
						paths := map[string]string{}
						for _, r := range config.VirtualHosts[0].Routes {
							paths[r.Name] = r.Match.GetPrefix()
							settings := &auth.ExtAuthzPerRoute{}
							if err := r.TypedPerFilterConfig["envoy.filters.http.ext_authz"].UnmarshalTo(settings); err != nil {
								t.Fatal(err)
							}
							expectedAPI := "catalog"
							if r.Name == "explicit" {
								expectedAPI = "catalog-explicit"
							}
							extensions := settings.GetCheckSettings().ContextExtensions
							if extensions["tenant_id"] != "tenant" || extensions["api_id"] != expectedAPI {
								t.Fatalf("identity lost: %v", extensions)
							}
						}
						if len(paths) != 2 || paths["catalog"] != "/apis/orders" || paths["explicit"] != "/custom" {
							t.Fatalf("routes: %v", paths)
						}
					}
					ack := &discovery.DiscoveryRequest{TypeUrl: kind, VersionInfo: response.VersionInfo, ResponseNonce: response.Nonce}
					if outcome == "NACK" {
						ack.ErrorDetail = status.New(codes.InvalidArgument, "configuration rejected").Proto()
					}
					if err = stream.Send(ack); err != nil {
						t.Fatal(err)
					}
					if outcome == "NACK" {
						break
					}
				}
			}
			result := <-done
			if outcome == "ACK" {
				if result.err != nil || len(result.result.FailedRoutes) != 0 {
					t.Fatalf("SYNCED: %+v", result)
				}
			} else {
				message := "configuration rejected"
				if outcome == "timeout" {
					message = "deadline exceeded"
				}
				if result.err == nil || !strings.Contains(result.result.FailedRoutes["deploy"], message) || !strings.Contains(result.result.FailedRoutes["second"], message) {
					t.Fatalf("FAILED: %+v", result)
				}
				if _, ok := result.result.FailedRoutes["inactive"]; ok {
					t.Fatal("inactive route failed")
				}
			}
		})
	}
}

func TestEnvoyUnsupported(t *testing.T) {
	a := NewEnvoyAdapter(nil)
	ctx := context.Background()
	_, detect := a.Detect(ctx, "")
	_, discover := a.Discover(ctx, "")
	for _, err := range []error{detect, discover, a.ApplyPolicy(ctx, "", "api", PolicyAction{Type: "unknown"}), a.RemovePolicy(ctx, "", "api", "unknown"), a.InjectCredentials(ctx, "", nil)} {
		var unsupported *UnsupportedError
		if !errors.As(err, &unsupported) || !strings.Contains(err.Error(), "unsupported") {
			t.Fatalf("expected typed unsupported: %v", err)
		}
	}
	r, e := a.SyncRoutes(ctx, "", []Route{{Activated: true, DeploymentID: "d"}})
	if e == nil || r.FailedRoutes["d"] == "" {
		t.Fatal("missing api_id accepted")
	}
}
