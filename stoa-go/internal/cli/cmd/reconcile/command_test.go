package reconcile

import (
	"encoding/json"
	"errors"
	"github.com/spf13/cobra"
	"io"
	"os"
	"path/filepath"
	"testing"
)

func TestOnceExitResult(t *testing.T) {
	for _, result := range []string{"ok", "degraded", "failed", "drift-unresolved"} {
		err := onceError(Status{Result: result}, nil)
		if (err != nil) != (result == "failed" || result == "drift-unresolved") {
			t.Fatalf("incorrect exit: %s: %v", result, err)
		}
	}
	failure := errors.New("read failed")
	if !errors.Is(onceError(Status{}, failure), failure) {
		t.Fatal("lost original error")
	}
}

func TestOnceCommandExit(t *testing.T) {
	for _, result := range []string{"ok", "degraded", "failed", "drift-unresolved"} {
		t.Run(result, func(t *testing.T) {
			calls := 0
			cmd := newReconcileCmd(func(*cobra.Command, string, string) (Status, error) { calls++; return Status{Result: result}, nil })
			cmd.SetOut(io.Discard)
			cmd.SetErr(io.Discard)
			cmd.SetArgs([]string{"--file", "snapshot.yaml", "--once"})
			err := cmd.Execute()
			if calls != 1 || (err != nil) != (result == "failed" || result == "drift-unresolved") {
				t.Fatalf("calls=%d error=%v", calls, err)
			}
		})
	}
}
func TestStatePermissions(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	if err := saveStatus(path, Status{Result: "degraded"}); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0600 {
		t.Fatalf("unsafe permissions: %v", info.Mode())
	}
	var status Status
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(b, &status); err != nil || status.Result != "degraded" {
		t.Fatalf("invalid state: %v", err)
	}
}
