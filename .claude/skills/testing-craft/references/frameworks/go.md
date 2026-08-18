# go test

The features that change how tests read in go test, and the specific traps in
it.

**Table-driven with subtests** is the idiomatic default: each case is named,
runnable in isolation (`go test -run 'TestParse/rejects_empty'`), and failures
say which row broke.

```go
func TestParseDuration(t *testing.T) {
	tests := []struct {
		name    string
		in      string
		want    time.Duration
		wantErr bool
	}{
		{name: "seconds", in: "30s", want: 30 * time.Second},
		{name: "rejects empty", in: "", wantErr: true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseDuration(tt.in)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ParseDuration(%q) error = %v, wantErr %v", tt.in, err, tt.wantErr)
			}
			if got != tt.want {
				t.Errorf("ParseDuration(%q) = %v, want %v", tt.in, got, tt.want)
			}
		})
	}
}
```

- `t.Fatalf` stops this test (use when continuing would panic); `t.Errorf`
  records and continues (use for independent assertions).
- Failure messages state *what was called, what came back, what was expected* —
  `got = X, want Y`. That convention makes any Go failure readable.
- `t.Cleanup(fn)` over `defer` for teardown: it runs after subtests too.
- `t.Parallel()` inside subtests to speed the suite — only if the cases share no
  state.
- `t.TempDir()` for filesystem work. `httptest.NewServer` for HTTP boundaries.
- **Always run `go test -race` in CI.** It finds data races that are otherwise
  invisible until production load.
- Golden files (`-update` flag convention) for large expected outputs.
