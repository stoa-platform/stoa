package connect

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
	"github.com/stoa-platform/stoa-go/internal/xds"
)

type envoyTestServer struct{}

func (envoyTestServer) Update(context.Context, []xds.Route) (string, error)  { return "v", nil }
func (envoyTestServer) WaitAck(context.Context, string, time.Duration) error { return nil }
func TestExplicitEnvoyOnly(t *testing.T) {
	ctx := context.Background()
	a, kind, err := ResolveAdapter(ctx, DiscoveryConfig{GatewayType: "envoy", EnvoyServer: envoyTestServer{}})
	if err != nil || kind != "envoy" {
		t.Fatalf("selection: %s %v", kind, err)
	}
	if _, ok := a.(*adapters.EnvoyAdapter); !ok {
		t.Fatalf("adapter: %T", a)
	}
	if _, _, err = ResolveAdapter(ctx, DiscoveryConfig{GatewayType: "envoy"}); err == nil {
		t.Fatal("unwired envoy accepted")
	}
	server := httptest.NewServer(http.NotFoundHandler())
	defer server.Close()
	for _, mode := range []string{"auto", ""} {
		a, kind, _ = ResolveAdapter(ctx, DiscoveryConfig{GatewayType: mode, GatewayAdminURL: server.URL, EnvoyServer: envoyTestServer{}})
		if _, ok := a.(*adapters.EnvoyAdapter); ok || kind == "envoy" {
			t.Fatal("auto selected envoy")
		}
	}
}
