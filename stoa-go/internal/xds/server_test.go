package xds

import (
	"context"
	"errors"
	"io"
	"net"
	"strings"
	"testing"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	discovery "github.com/envoyproxy/go-control-plane/envoy/service/discovery/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

func harness(t *testing.T, identity Identity) (*Server, discovery.AggregatedDiscoveryServiceClient) {
	t.Helper()
	s, err := NewServer(config(), grpc.NewServer(), identity)
	if err != nil {
		t.Fatal(err)
	}
	l := bufconn.Listen(1024 * 1024)
	t.Cleanup(func() {
		s.Close()
		if err := l.Close(); err != nil {
			t.Errorf("close listener: %v", err)
		}
	})
	go func() { _ = s.GRPCServer().Serve(l) }()
	conn, err := grpc.NewClient("passthrough:///memory", grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return l.DialContext(ctx) }))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := conn.Close(); err != nil {
			t.Errorf("close connection: %v", err)
		}
	})
	return s, discovery.NewAggregatedDiscoveryServiceClient(conn)
}
func own(context.Context) (string, error) { return "own", nil }
func open(t *testing.T, c discovery.AggregatedDiscoveryServiceClient) discovery.AggregatedDiscoveryService_StreamAggregatedResourcesClient {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	t.Cleanup(cancel)
	stream, err := c.StreamAggregatedResources(ctx)
	if err != nil {
		t.Fatal(err)
	}
	return stream
}
func receive(t *testing.T, stream discovery.AggregatedDiscoveryService_StreamAggregatedResourcesClient, kind, node string) *discovery.DiscoveryResponse {
	t.Helper()
	if err := stream.Send(&discovery.DiscoveryRequest{Node: &core.Node{Id: node}, TypeUrl: kind}); err != nil {
		t.Fatal(err)
	}
	r, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	return r
}
func TestVerifiedIdentityOverridesClaim(t *testing.T) {
	s, c := harness(t, own)
	version, err := s.Update(context.Background(), routes())
	if err != nil {
		t.Fatal(err)
	}
	// A different claimed node must still receive the verified node's snapshot.
	r := receive(t, open(t, c), resource.ClusterType, "other")
	if r.VersionInfo != version || len(r.Resources) != 3 {
		t.Fatal("wrong identity snapshot")
	}
}
func TestMissingVerifiedIdentity(t *testing.T) {
	for _, identity := range []Identity{nil, func(context.Context) (string, error) { return "", nil }, func(context.Context) (string, error) { return "", errors.New("unverified") }} {
		s, c := harness(t, identity)
		if _, err := s.Update(context.Background(), routes()); err != nil {
			t.Fatal(err)
		}
		stream := open(t, c)
		if err := stream.Send(&discovery.DiscoveryRequest{Node: &core.Node{Id: "own"}, TypeUrl: resource.ClusterType}); err != nil {
			t.Fatal(err)
		}
		if _, err := stream.Recv(); status.Code(err) != codes.Unauthenticated && !errors.Is(err, io.EOF) {
			t.Fatalf("expected unauthenticated refusal, got %v", err)
		}
	}
}
func TestUnconfiguredIdentity(t *testing.T) {
	s, c := harness(t, func(context.Context) (string, error) { return "other", nil })
	_, _ = s.Update(context.Background(), routes())
	stream := open(t, c)
	_ = stream.Send(&discovery.DiscoveryRequest{Node: &core.Node{Id: "own"}, TypeUrl: resource.ClusterType})
	if _, err := stream.Recv(); status.Code(err) != codes.PermissionDenied && !errors.Is(err, io.EOF) {
		t.Fatalf("expected refusal: %v", err)
	}
}
func TestADS(t *testing.T) {
	s, c := harness(t, own)
	ctx := context.Background()
	version, err := s.Update(ctx, routes())
	if err != nil {
		t.Fatal(err)
	}
	stream := open(t, c)
	for _, kind := range []string{resource.ClusterType, resource.ListenerType, resource.RouteType} {
		r := receive(t, stream, kind, "own")
		if r.VersionInfo != version || len(r.Resources) == 0 {
			t.Fatal("snapshot")
		}
		// A nonce that was not sent must not acknowledge anything.
		if err = stream.Send(&discovery.DiscoveryRequest{TypeUrl: kind, VersionInfo: version, ResponseNonce: "unknown"}); err != nil {
			t.Fatal(err)
		}
		if err = s.WaitAck(ctx, version, time.Millisecond); !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("premature ACK: %v", err)
		}
		if err = stream.Send(&discovery.DiscoveryRequest{TypeUrl: kind, VersionInfo: version, ResponseNonce: r.Nonce}); err != nil {
			t.Fatal(err)
		}
	}
	if err = s.WaitAck(ctx, version, 0); err != nil {
		t.Fatal(err)
	}
	// Reconnecting clients receive the current snapshot without republishing.
	reconnect := open(t, c)
	if r := receive(t, reconnect, resource.ClusterType, "own"); r.VersionInfo != version {
		t.Fatal("reconnect version")
	}
	next := routes()
	next[0].Path = "/changed"
	v2, err := s.Update(ctx, next)
	if err != nil {
		t.Fatal(err)
	}
	response, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if err = stream.Send(&discovery.DiscoveryRequest{TypeUrl: response.TypeUrl, VersionInfo: version, ResponseNonce: response.Nonce, ErrorDetail: status.New(codes.InvalidArgument, "rejected configuration").Proto()}); err != nil {
		t.Fatal(err)
	}
	if err = s.WaitAck(ctx, v2, time.Second); err == nil || !strings.Contains(err.Error(), "rejected configuration") {
		t.Fatalf("NACK detail: %v", err)
	}
}
func TestWaitAndClose(t *testing.T) {
	s, _ := harness(t, own)
	ctx := context.Background()
	v, err := s.Update(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.WaitAck(ctx, "unknown", time.Millisecond); err == nil {
		t.Fatal("unknown version")
	}
	if err = s.WaitAck(ctx, v, time.Millisecond); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatal(err)
	}
	canceled, cancel := context.WithCancel(ctx)
	cancel()
	if err = s.WaitAck(canceled, v, time.Second); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	if _, err = s.Update(canceled, nil); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	invalid := routes()
	invalid[0].Path = ""
	if _, err = s.Update(ctx, invalid); err == nil {
		t.Fatal("invalid update")
	}
	done := make(chan error, 1)
	go func() { done <- s.WaitAck(ctx, v, time.Second) }()
	s.Close()
	s.Close()
	if err = <-done; err == nil {
		t.Fatal("close did not wake waiter")
	}
	if _, err = s.Update(ctx, nil); err == nil {
		t.Fatal("update after close")
	}
}
func TestDeltaUnsupported(t *testing.T) {
	_, c := harness(t, own)
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	stream, err := c.DeltaAggregatedResources(ctx)
	if err != nil {
		t.Fatal(err)
	}
	_, err = stream.Recv()
	if status.Code(err) != codes.Unimplemented {
		t.Fatal(err)
	}
}
