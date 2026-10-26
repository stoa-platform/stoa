package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"math/big"
	"net"
	"net/url"
	"testing"
	"time"

	core "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	discovery "github.com/envoyproxy/go-control-plane/envoy/service/discovery/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
	"github.com/stoa-platform/stoa-go/internal/xds"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/peer"
)

// Certificates exist only in memory and are generated anew for each test.
func envoyTLS(t *testing.T) (*tls.Config, *tls.Config) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ca := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test CA"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign}
	der, err := x509.CreateCertificate(rand.Reader, ca, ca, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	root, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	pool := x509.NewCertPool()
	pool.AddCert(root)
	issue := func(serial int64, client bool) tls.Certificate {
		k, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if e != nil {
			t.Fatal(e)
		}
		cert := &x509.Certificate{SerialNumber: big.NewInt(serial), NotBefore: ca.NotBefore, NotAfter: ca.NotAfter, KeyUsage: x509.KeyUsageDigitalSignature}
		if client {
			u, _ := url.Parse("spiffe://example.org/envoy")
			cert.URIs = []*url.URL{u}
			cert.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
		} else {
			cert.IPAddresses = []net.IP{net.ParseIP("127.0.0.1")}
			cert.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
		}
		b, e := x509.CreateCertificate(rand.Reader, cert, root, &k.PublicKey, key)
		if e != nil {
			t.Fatal(e)
		}
		return tls.Certificate{Certificate: [][]byte{b}, PrivateKey: k}
	}
	return &tls.Config{MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{issue(2, false)}, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: pool}, &tls.Config{MinVersion: tls.VersionTLS13, RootCAs: pool, Certificates: []tls.Certificate{issue(3, true)}, ServerName: "127.0.0.1"}
}

func TestEnvoyModeVerifiedIdentityAndShutdown(t *testing.T) {
	serverTLS, clientTLS := envoyTLS(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	cfg := xds.Config{NodeID: "spiffe://example.org/envoy", ListenerPort: 8080, AuthCluster: "auth", AuthAddress: "127.0.0.1:9000", AuthTimeout: time.Second, AckTimeout: time.Second}
	s, l, err := serveEnvoy(ctx, "127.0.0.1:0", cfg, serverTLS)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	version, err := s.Update(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	conn, err := grpc.NewClient(l.Addr().String(), grpc.WithTransportCredentials(credentials.NewTLS(clientTLS)))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	}()
	rpcCtx, rpcCancel := context.WithTimeout(ctx, 3*time.Second)
	defer rpcCancel()
	stream, err := discovery.NewAggregatedDiscoveryServiceClient(conn).StreamAggregatedResources(rpcCtx)
	if err != nil {
		t.Fatal(err)
	}
	if err = stream.Send(&discovery.DiscoveryRequest{Node: &core.Node{Id: "forged"}, TypeUrl: resource.ClusterType}); err != nil {
		t.Fatal(err)
	}
	response, err := stream.Recv()
	if err != nil || response.VersionInfo != version {
		t.Fatalf("verified certificate must override forged node: %v %v", response, err)
	}
	cancel()
	if _, err = stream.Recv(); err == nil {
		t.Fatal("stream survived cancellation")
	}
	deadline := time.Now().Add(time.Second)
	for {
		c, e := net.DialTimeout("tcp", l.Addr().String(), 10*time.Millisecond)
		if e != nil {
			break
		}
		_ = c.Close()
		if time.Now().After(deadline) {
			t.Fatal("listener survived cancellation")
		}
		time.Sleep(time.Millisecond)
	}
}

func TestEnvoyRefusesUnverifiedIdentity(t *testing.T) {
	for _, ctx := range []context.Context{context.Background(), peer.NewContext(context.Background(), &peer.Peer{AuthInfo: credentials.TLSInfo{State: tls.ConnectionState{PeerCertificates: []*x509.Certificate{{}}}}})} {
		if _, err := verifiedEnvoyIdentity(ctx); err == nil {
			t.Fatal("unverified identity accepted")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	tlsCfg, _ := envoyTLS(t)
	if _, _, err := serveEnvoy(ctx, "192.0.2.1:0", xds.Config{}, tlsCfg); err == nil {
		t.Fatal("non-loopback accepted")
	}
	if _, _, err := serveEnvoy(ctx, "127.0.0.1:0", xds.Config{}, nil); err == nil {
		t.Fatal("plaintext accepted")
	}
}
