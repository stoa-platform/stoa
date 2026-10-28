//go:build o1integration

package connect

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net/url"
	"os"
	"path/filepath"
	"testing"
	"time"

	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/peer"
)

// Ephemeral mTLS material; nothing is taken from a user's credentials.
func o1TLS(t *testing.T, dir string) (*tls.Config, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ca := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "O1 test CA"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign}
	der, err := x509.CreateCertificate(rand.Reader, ca, ca, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	pool := x509.NewCertPool()
	pool.AddCert(mustO1Certificate(t, der))
	write := func(name string, data []byte) {
		if err := os.WriteFile(filepath.Join(dir, name), data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	write("ca.crt", pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))
	node := "spiffe://stoa.test/envoy/o1"
	issue := func(serial int64, client bool) tls.Certificate {
		leafKey, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if e != nil {
			t.Fatal(e)
		}
		cert := &x509.Certificate{SerialNumber: big.NewInt(serial), NotBefore: ca.NotBefore, NotAfter: ca.NotAfter, KeyUsage: x509.KeyUsageDigitalSignature, DNSNames: []string{"localhost"}, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
		name := "server"
		if client {
			uri, _ := url.Parse(node)
			cert.URIs = []*url.URL{uri}
			cert.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
			name = "client"
		}
		encoded, e := x509.CreateCertificate(rand.Reader, cert, ca, &leafKey.PublicKey, key)
		if e != nil {
			t.Fatal(e)
		}
		private, e := x509.MarshalECPrivateKey(leafKey)
		if e != nil {
			t.Fatal(e)
		}
		publicPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: encoded})
		privatePEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: private})
		write(name+".crt", publicPEM)
		write(name+".key", privatePEM)
		pair, e := tls.X509KeyPair(publicPEM, privatePEM)
		if e != nil {
			t.Fatal(e)
		}
		return pair
	}
	server := issue(2, false)
	issue(3, true)
	return &tls.Config{MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{server}, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: pool}, node
}

func mustO1Certificate(t *testing.T, der []byte) *x509.Certificate {
	t.Helper()
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return cert
}

func o1VerifiedIdentity(ctx context.Context) (string, error) {
	p, ok := peer.FromContext(ctx)
	if !ok {
		return "", fmt.Errorf("verified peer missing")
	}
	info, ok := p.AuthInfo.(credentials.TLSInfo)
	if !ok || len(info.State.VerifiedChains) == 0 || len(info.State.VerifiedChains[0][0].URIs) != 1 {
		return "", fmt.Errorf("verified URI missing")
	}
	return info.State.VerifiedChains[0][0].URIs[0].String(), nil
}
