package xds

import (
	"context"
	"fmt"
	"sync"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	discovery "github.com/envoyproxy/go-control-plane/envoy/service/discovery/v3"
	cache "github.com/envoyproxy/go-control-plane/pkg/cache/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	server "github.com/envoyproxy/go-control-plane/pkg/server/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Identity resolves a verified principal from server-owned stream context.
// Implementations must never derive identity from client discovery messages.
type Identity func(context.Context) (string, error)

type receipt struct{ version, nonce string }
type acknowledgement struct {
	types map[string]bool
	err   error
}

// Server serves SotW ADS for one verified node. Delta ADS is unsupported.
// Close stops the supplied gRPC server as well as the snapshot server.
type Server struct {
	discovery.UnimplementedAggregatedDiscoveryServiceServer
	config   Config
	identity Identity
	grpc     *grpc.Server
	ads      server.Server
	cache    cache.SnapshotCache
	cancel   context.CancelFunc
	mu       sync.Mutex
	sent     map[int64]map[string]receipt
	results  map[string]*acknowledgement
	changed  chan struct{}
	closed   bool
}

// NewServer registers ADS on g, or creates a gRPC server if g is nil.
// A missing identity resolver fails closed for every stream.
func NewServer(config Config, g *grpc.Server, identity Identity) (*Server, error) {
	c, err := normalize(config)
	if err != nil {
		return nil, err
	}
	if _, err = BuildSnapshot(c, nil); err != nil {
		return nil, err
	}
	if g == nil {
		g = grpc.NewServer()
	}
	ctx, cancel := context.WithCancel(context.Background())
	s := &Server{config: c, identity: identity, grpc: g, cancel: cancel, cache: cache.NewSnapshotCache(true, cache.IDHash{}, nil), sent: map[int64]map[string]receipt{}, results: map[string]*acknowledgement{}, changed: make(chan struct{})}
	s.ads = server.NewServer(ctx, s.cache, server.CallbackFuncs{
		StreamClosedFunc: func(id int64, _ *core.Node) { s.mu.Lock(); delete(s.sent, id); s.mu.Unlock() },
		StreamResponseFunc: func(_ context.Context, id int64, _ *discovery.DiscoveryRequest, r *discovery.DiscoveryResponse) {
			s.mu.Lock()
			defer s.mu.Unlock()
			if s.sent[id] == nil {
				s.sent[id] = map[string]receipt{}
			}
			s.sent[id][r.TypeUrl] = receipt{r.VersionInfo, r.Nonce}
		},
		StreamRequestFunc: func(id int64, r *discovery.DiscoveryRequest) error {
			s.mu.Lock()
			defer s.mu.Unlock()
			sent, ok := s.sent[id][r.TypeUrl]
			if !ok || r.ResponseNonce == "" || sent.nonce != r.ResponseNonce {
				return nil
			}
			result := s.results[sent.version]
			if result == nil {
				return nil
			}
			if r.ErrorDetail != nil {
				result.err = fmt.Errorf("xDS NACK for %s: %s", r.TypeUrl, r.ErrorDetail.Message)
			} else if r.VersionInfo == sent.version {
				result.types[r.TypeUrl] = true
			}
			close(s.changed)
			s.changed = make(chan struct{})
			return nil
		},
	})
	discovery.RegisterAggregatedDiscoveryServiceServer(g, s)
	return s, nil
}

// GRPCServer returns the server to serve on a caller-owned listener.
func (s *Server) GRPCServer() *grpc.Server { return s.grpc }

func (s *Server) verifiedNode(ctx context.Context, claimed *core.Node) (string, error) {
	if s.identity == nil {
		return "", status.Error(codes.Unauthenticated, "verified identity required")
	}
	id, err := s.identity(ctx)
	if err != nil || id == "" {
		return "", status.Error(codes.Unauthenticated, "verified identity required")
	}
	return id, nil
}

type verifiedStream struct {
	discovery.AggregatedDiscoveryService_StreamAggregatedResourcesServer
	owner *Server
}

func (v *verifiedStream) Recv() (*discovery.DiscoveryRequest, error) {
	req, err := v.AggregatedDiscoveryService_StreamAggregatedResourcesServer.Recv()
	if err != nil {
		return nil, err
	}
	id, err := v.owner.verifiedNode(v.Context(), req.Node)
	if err != nil {
		return nil, err
	}
	if id != v.owner.config.NodeID {
		return nil, status.Error(codes.PermissionDenied, "identity is not configured")
	}
	// Replace every message's node before the cache hash sees it, including ACKs.
	req.Node = &core.Node{Id: id}
	return req, nil
}

// StreamAggregatedResources serves only requests associated with verified identity.
func (s *Server) StreamAggregatedResources(stream discovery.AggregatedDiscoveryService_StreamAggregatedResourcesServer) error {
	return s.ads.StreamAggregatedResources(&verifiedStream{stream, s})
}

// Update publishes a complete snapshot. Concurrent calls are serialized.
func (s *Server) Update(ctx context.Context, routes []Route) (string, error) {
	snapshot, err := BuildSnapshot(s.config, routes)
	if err != nil {
		return "", err
	}
	version := snapshot.GetVersion(resource.ClusterType)
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return "", fmt.Errorf("server closed")
	}
	if err = ctx.Err(); err != nil {
		return "", err
	}
	if s.results[version] == nil || s.results[version].err != nil {
		// A rejected version may be retried after a reconnect or recovery.
		// The next attempt must collect fresh receipts, not inherit its NACK.
		s.results[version] = &acknowledgement{types: map[string]bool{}}
	}
	if err = s.cache.SetSnapshot(ctx, s.config.NodeID, snapshot); err != nil {
		return "", err
	}
	return version, nil
}

// WaitAck waits for CDS, LDS and RDS acknowledgements, or the first NACK.
// Nonpositive timeout uses Config.AckTimeout. Unknown versions are rejected.
func (s *Server) WaitAck(ctx context.Context, version string, timeout time.Duration) error {
	if timeout <= 0 {
		timeout = s.config.AckTimeout
	}
	timer := time.NewTimer(timeout)
	defer timer.Stop()
	for {
		s.mu.Lock()
		result := s.results[version]
		if s.closed {
			s.mu.Unlock()
			return fmt.Errorf("server closed")
		}
		if result == nil {
			s.mu.Unlock()
			return fmt.Errorf("unknown version")
		}
		err := result.err
		done := result.types[resource.ClusterType] && result.types[resource.ListenerType] && result.types[resource.RouteType]
		changed := s.changed
		s.mu.Unlock()
		if err != nil {
			return err
		}
		if done {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-timer.C:
			return context.DeadlineExceeded
		case <-changed:
		}
	}
}

// Close terminates active streams and wakes acknowledgement waiters.
func (s *Server) Close() {
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.closed = true
	close(s.changed)
	s.mu.Unlock()
	s.cancel()
	s.grpc.Stop()
}
