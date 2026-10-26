package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"os"
	"strconv"
	"time"

	"github.com/stoa-platform/stoa-go/internal/xds"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/peer"
)

// verifiedEnvoyIdentity accepts only a URI SAN from a verified client chain.
// The discovery request's node.id is never an authentication input.
func verifiedEnvoyIdentity(ctx context.Context) (string, error) {
	p, ok := peer.FromContext(ctx)
	if !ok {
		return "", fmt.Errorf("verified client certificate required")
	}
	info, ok := p.AuthInfo.(credentials.TLSInfo)
	if !ok || len(info.State.VerifiedChains) == 0 || len(info.State.VerifiedChains[0]) == 0 {
		return "", fmt.Errorf("verified client certificate required")
	}
	uris := info.State.VerifiedChains[0][0].URIs
	if len(uris) != 1 {
		return "", fmt.Errorf("exactly one client URI SAN required")
	}
	return uris[0].String(), nil
}

func serveEnvoy(ctx context.Context, addr string, cfg xds.Config, tlsConfig *tls.Config) (*xds.Server, net.Listener, error) {
	host, _, err := net.SplitHostPort(addr)
	if err != nil || net.ParseIP(host) == nil || !net.ParseIP(host).IsLoopback() {
		return nil, nil, fmt.Errorf("ADS address must use a loopback IP")
	}
	if tlsConfig == nil || tlsConfig.ClientAuth != tls.RequireAndVerifyClientCert || tlsConfig.ClientCAs == nil {
		return nil, nil, fmt.Errorf("ADS requires mutual TLS")
	}
	g := grpc.NewServer(grpc.Creds(credentials.NewTLS(tlsConfig)))
	s, err := xds.NewServer(cfg, g, verifiedEnvoyIdentity)
	if err != nil {
		g.Stop()
		return nil, nil, err
	}
	l, err := net.Listen("tcp", addr)
	if err != nil {
		s.Close()
		return nil, nil, err
	}
	go func() { _ = g.Serve(l); s.Close() }()
	go func() { <-ctx.Done(); s.Close(); _ = l.Close() }()
	return s, l, nil
}

func startEnvoy(ctx context.Context) (*xds.Server, error) {
	addr := os.Getenv("STOA_ENVOY_ADS_ADDR")
	if addr == "" {
		addr = "127.0.0.1:18000"
	}
	port, err := strconv.ParseUint(os.Getenv("STOA_ENVOY_LISTENER_PORT"), 10, 16)
	if err != nil {
		return nil, fmt.Errorf("STOA_ENVOY_LISTENER_PORT is required")
	}
	cfg := xds.Config{NodeID: os.Getenv("STOA_ENVOY_NODE_URI"), ListenerPort: uint32(port), AuthCluster: "authorization", AuthAddress: os.Getenv("STOA_ENVOY_AUTH_ADDR"), AuthTimeout: time.Second, AckTimeout: 5 * time.Second}
	cert, err := tls.LoadX509KeyPair(os.Getenv("STOA_ENVOY_TLS_CERT"), os.Getenv("STOA_ENVOY_TLS_KEY"))
	if err != nil {
		return nil, fmt.Errorf("load ADS server TLS certificate: %w", err)
	}
	ca, err := os.ReadFile(os.Getenv("STOA_ENVOY_CLIENT_CA"))
	if err != nil {
		return nil, fmt.Errorf("load ADS client CA: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(ca) {
		return nil, fmt.Errorf("invalid ADS client CA")
	}
	s, _, err := serveEnvoy(ctx, addr, cfg, &tls.Config{MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{cert}, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: pool})
	return s, err
}
