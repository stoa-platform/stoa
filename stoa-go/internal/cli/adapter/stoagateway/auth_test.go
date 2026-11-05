package stoagateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAudienceValidationBeforePost(t *testing.T) {
	for _, aud := range []string{"", "*", "sample*", "?", "account", "AcCoUnT", "sandbox", "SANDBOX"} {
		t.Run(aud, func(t *testing.T) {
			calls := 0
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(500) }))
			defer srv.Close()
			a := New(srv.URL, srv.URL, "test-token", srv.Client())
			a.Audience = aud
			a.Realms = []string{"sandbox"}
			desired := contract("2", "owner")
			delete(desired, "inboundAuth")
			delete(desired, "inboundAuthAudience")
			if _, err := a.Publish(context.Background(), desired); err == nil || calls != 0 {
				t.Fatalf("invalid audience reached gateway: %d", calls)
			}
		})
	}
}
func TestAtomicAuthAndReadback(t *testing.T) {
	for _, echo := range []bool{false, true} {
		t.Run(map[bool]string{false: "unsupported", true: "supported"}[echo], func(t *testing.T) {
			var live Contract
			posts, policies := 0, 0
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.Contains(r.URL.Path, "policies") {
					policies++
					w.WriteHeader(500)
					return
				}
				if strings.HasPrefix(r.URL.Path, "/apis/") {
					w.WriteHeader(401)
					return
				}
				switch r.Method {
				case http.MethodPost:
					posts++
					_ = json.NewDecoder(r.Body).Decode(&live)
					if live.String("inboundAuth") != "jwt" || live.String("inboundAuthAudience") != "items-read" {
						t.Error("missing atomic auth fields")
					}
					if !echo {
						delete(live, "inboundAuthAudience")
					}
				case http.MethodDelete:
					live = nil
				default:
					if live == nil {
						w.WriteHeader(404)
					} else {
						_ = json.NewEncoder(w).Encode(live)
					}
				}
			}))
			defer srv.Close()
			a := New(srv.URL, srv.URL, "test-token", srv.Client())
			a.Audience = "items-read"
			_, err := a.Publish(context.Background(), contract("1", "owner"))
			if (err == nil) != echo || policies != 0 || posts != 1 {
				t.Fatalf("unexpected publish: %v posts=%d policies=%d", err, posts, policies)
			}
			if !echo && live != nil {
				t.Fatal("unsupported audience left published")
			}
		})
	}
}
func TestRollbackRejectsOpenContract(t *testing.T) {
	for _, aud := range []string{"", "account", "sandbox", "items-read"} {
		for _, opt := range []bool{false, true} {
			a := New("", "", "", nil)
			a.AllowUnauthenticatedREST = opt
			a.Realms = []string{"sandbox"}
			prev := contract("1", "owner")
			prev["inboundAuth"] = "jwt"
			prev["inboundAuthAudience"] = aud
			if a.mayRestore(prev) != (opt || aud == "items-read") {
				t.Fatalf("incorrect restore decision: audience=%q opt=%v", aud, opt)
			}
			prev["classification"] = "VH"
			if opt && aud == "" && a.mayRestore(prev) {
				t.Fatal("opt-in opened a high classification")
			}
		}
	}
}
func TestRealmNames(t *testing.T) {
	realms := RealmNames("primary", "/realms/secondary/protocol", "/realms/primary?test", "/realms/third#value")
	if strings.Join(realms, ",") != "stoa,primary,secondary,third" {
		t.Fatalf("realms: %v", realms)
	}
}

func TestFailedPublishDoesNotRestoreUnsafePredecessor(t *testing.T) {
	for _, opt := range []bool{false, true} {
		t.Run(map[bool]string{false: "closed", true: "opt-in"}[opt], func(t *testing.T) {
			live := contract("1", "owner")
			delete(live, "inboundAuth")
			delete(live, "inboundAuthAudience")
			posts, deletes := 0, 0
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasPrefix(r.URL.Path, "/apis/") {
					w.WriteHeader(500)
					return
				}
				switch r.Method {
				case http.MethodPost:
					posts++
					_ = json.NewDecoder(r.Body).Decode(&live)
					// Force post-publish verification failure even with the open-route opt-in.
					if posts == 1 {
						live["version"] = "unexpected"
					}
				case http.MethodDelete:
					deletes++
					live = nil
				default:
					if live == nil {
						w.WriteHeader(404)
					} else {
						_ = json.NewEncoder(w).Encode(live)
					}
				}
			}))
			defer srv.Close()
			a := New(srv.URL, srv.URL, "test-token", srv.Client())
			a.AllowUnauthenticatedREST = opt
			_, err := a.Publish(context.Background(), contract("2", "owner"))
			if err == nil {
				t.Fatal("verification failure lost")
			}
			if opt {
				if live.String("version") != "1" || posts != 2 || deletes != 0 {
					t.Fatal("explicit opt-in did not restore predecessor")
				}
			} else if live != nil || posts != 1 || deletes != 1 {
				t.Fatal("unsafe predecessor restored")
			}
		})
	}
}
func TestSnakeCaseReadbackPreservesAuth(t *testing.T) {
	c := contract("1", "owner")
	delete(c, "inboundAuth")
	delete(c, "inboundAuthAudience")
	c["inbound_auth"] = "jwt"
	c["inbound_auth_audience"] = "items-read"
	a := New("", "", "", nil)
	if !a.mayRestore(c) || !verifiedAuth(c, contract("1", "owner")) {
		t.Fatal("snake case authentication lost")
	}
}
func TestConsumerAndOptIn(t *testing.T) {
	for _, class := range []string{"H", "VH", "VVH"} {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("Authorization") != "" && strings.HasPrefix(r.URL.Path, "/apis/") {
				t.Error("admin token sent to data plane")
			}
			if strings.HasPrefix(r.URL.Path, "/apis/") {
				w.WriteHeader(200)
				return
			}
			c := contract("1", "owner")
			c["classification"] = class
			_ = json.NewEncoder(w).Encode(c)
		}))
		a := New(srv.URL, srv.URL, "test-token", srv.Client())
		a.AllowUnauthenticatedREST = true
		c := contract("1", "owner")
		c["classification"] = class
		result, err := a.VerifyConsumer(context.Background(), c)
		if (err == nil) != (class == "H") {
			t.Fatalf("consumer opt-in class %s: %v", class, err)
		}
		if class == "H" && result != "unprotected" {
			t.Fatal("missing degraded protection")
		}
		if class != "H" {
			if _, err = a.authenticatedContract(c); err == nil {
				t.Fatal("high-class publish opt-in accepted")
			}
		}
		srv.Close()
	}
}

func TestTransientVerificationFailureRestoresPrevious(t *testing.T) {
	live := contract("1", "owner")
	posts, reads := 0, 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			posts++
			_ = json.NewDecoder(r.Body).Decode(&live)
			return
		}
		reads++
		if reads == 2 {
			w.WriteHeader(500)
			return
		}
		_ = json.NewEncoder(w).Encode(live)
	}))
	defer srv.Close()
	a := New(srv.URL, srv.URL, "test-token", srv.Client())
	if _, err := a.Publish(context.Background(), contract("2", "owner")); err == nil {
		t.Fatal("expected verification failure")
	}
	if posts != 2 || live.String("version") != "1" {
		t.Fatal("previous contract was not restored")
	}
}
