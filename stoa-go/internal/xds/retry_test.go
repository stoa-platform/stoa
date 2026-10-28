package xds

import (
	"context"
	"testing"
	"time"

	discovery "github.com/envoyproxy/go-control-plane/envoy/service/discovery/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestRegressionCAB2280RetryAfterNACK(t *testing.T) {
	s, client := harness(t, own)
	ctx := context.Background()
	version, err := s.Update(ctx, routes())
	if err != nil {
		t.Fatal(err)
	}
	first := open(t, client)
	response := receive(t, first, resource.ClusterType, "own")
	if err = first.Send(&discovery.DiscoveryRequest{TypeUrl: response.TypeUrl, ResponseNonce: response.Nonce, ErrorDetail: status.New(codes.InvalidArgument, "temporary refusal").Proto()}); err != nil {
		t.Fatal(err)
	}
	if err = s.WaitAck(ctx, version, time.Second); err == nil {
		t.Fatal("NACK accepted")
	}
	if _, err = s.Update(ctx, routes()); err != nil {
		t.Fatal(err)
	}
	reconnect := open(t, client)
	for _, kind := range []string{resource.ClusterType, resource.ListenerType, resource.RouteType} {
		r := receive(t, reconnect, kind, "own")
		if err = reconnect.Send(&discovery.DiscoveryRequest{TypeUrl: kind, VersionInfo: r.VersionInfo, ResponseNonce: r.Nonce}); err != nil {
			t.Fatal(err)
		}
	}
	if err = s.WaitAck(ctx, version, time.Second); err != nil {
		t.Fatalf("successful retry retained obsolete NACK: %v", err)
	}
}
