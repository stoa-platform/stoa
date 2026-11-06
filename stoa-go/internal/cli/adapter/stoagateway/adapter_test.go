package stoagateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func contract(version, owner string) Contract {
	return Contract{"name": "sample", "tenant_id": "sandbox", "version": version, "status": "published", "classification": "H", "description": owner, "inboundAuth": "jwt", "inboundAuthAudience": "items-read", "endpoints": []any{map[string]any{"path": "/items/", "methods": []string{"GET"}, "backend_url": "/upstream/"}}}
}

func TestPublishRollbackAndOwnership(t *testing.T) {
	for _, mode := range []string{"probe", "verify", "foreign", "new"} {
		t.Run(mode, func(t *testing.T) {
			previous := contract("1", "owner-a")
			var live Contract
			if mode != "new" {
				live = previous
			}
			posts, deletes := 0, 0
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch {
				case r.Method == http.MethodPost:
					posts++
					_ = json.NewDecoder(r.Body).Decode(&live)
					if mode == "foreign" {
						live["description"] = "owner-b"
					}
				case r.Method == http.MethodDelete:
					deletes++
					live = nil
				case r.URL.Path == "/apis/sandbox/sample/items/":
					w.WriteHeader(http.StatusOK)
				default:
					if live == nil {
						w.WriteHeader(404)
						return
					}
					if mode == "verify" && posts == 1 {
						w.WriteHeader(500)
						return
					}
					_ = json.NewEncoder(w).Encode(live)
				}
			}))
			defer srv.Close()
			a := New(srv.URL, srv.URL, "test-token", srv.Client())
			_, err := a.Publish(context.Background(), contract("2", "owner-a"))
			if err == nil {
				t.Fatal("expected failure")
			}
			switch mode {
			case "foreign":
				if deletes != 0 || posts != 1 {
					t.Fatal("foreign contract changed")
				}
			case "new":
				if deletes != 1 || live != nil {
					t.Fatal("new contract not removed")
				}
			case "probe":
				if live.String("version") != "1" || posts != 2 {
					t.Fatal("previous version not restored")
				}
			case "verify":
				if posts != 1 {
					t.Fatal("rollback must fail closed when ownership cannot be read")
				}
			}
		})
	}
}

func TestDeleteRefusesForeign(t *testing.T) {
	deletes := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodDelete {
			deletes++
		}
		_ = json.NewEncoder(w).Encode(contract("1", "other"))
	}))
	defer srv.Close()
	a := New(srv.URL, srv.URL, "test-token", srv.Client())
	if a.Delete(context.Background(), contract("1", "owner")) == nil || deletes != 0 {
		t.Fatal("foreign deletion allowed")
	}
}
