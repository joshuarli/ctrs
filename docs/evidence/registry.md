# CTRS-16 — Registry client pilot: `h12tiny-client-sync` vs `ureq`

Date: 2026-11-14. Verdict: **no win — `ureq` stays the registry transport;
`h12tiny-client-sync` remains behind the `h12tiny` cargo feature of
`kiri-image` (`registry-h12tiny` in `kiri`), off by default.**

## Design

Behind `--features h12tiny` (off by default; the default build is
byte-identical in behavior to before the slice), the registry client
(`crates/kiri-image/src/registry.rs`) talks to registries through a new
transport seam (`src/transport.rs`): `Transport` (cloneable; `Ureq` or
`H12Tiny`), `Request`/`Response`, bodies as `Empty` / `Form` / `Bytes` /
`File { path }` (streamed from disk, reopened per redirect hop). Everything
above the seam — bearer auth, the 401-token dance and its cache, manifest
digest and by-digest caches, blob `Range` resume (206) with per-attempt
backoff, digest verification, multiarch selection — is transport-agnostic.

- `ureq` backend (default): the incumbent — Happy Eyeballs connector,
  process-wide pool, ureq's own redirects (`RedirectAuthHeaders::Never`).
- `h12tiny` backend (pilot): h12tiny-client-sync 0.9.0 with the `tls`
  feature (= rustls + rustls-graviola 0.4.0 + rustls-webpki +
  `h12tiny-tls-system`); the config is built with
  `ClientTlsConfigBuilder::new()` — explicit Graviola provider and the
  platform's trust roots, **fails closed** if the store cannot be read.
  No pool (every request = TCP+TLS handshake), no proxy, no automatic
  redirects: the seam resolves redirects itself, ≤ 5 hops, `Authorization`
  dropped on every hop (matching ureq's `Never`), `301/302/303` rewritten
  to `GET`, `307/308` body-preserving, relative `Location` resolved
  against the base path.
- No vanilla `hyper`, no Tokio, no OpenSSL, no rustls with ring-only
  crypto. `cargo audit` clean (162 dependencies).

## Correctness (both backends)

- Loopback blob fixture (`blob_server` in `registry.rs` tests), run against
  **both** transports via parameterized test wrappers: stalled blob resumes
  from the `Range` offset; a registry that ignores `Range` resends the
  blob; a blob that never arrives gives up after `BLOB_TRIES`; a cancel
  mid-body stops at once and removes the partial blob (the h12tiny path
  wakes its body read at the configured stall; ureq's socket is shut down
  by the cancel). 45 tests green (`cargo test -p kiri-image --features h12tiny`);
  8 consecutive clean runs after fixing a race the new tests exposed:
  the ureq and h12tiny variants of a test shared one temp root and deleted
  each other's partial blobs (each test now gets its own).
- Live pulls of the two pinned images against Docker Hub on both engines:
  `alpine@sha256:d9e853e…` (3.6 MB) and `busybox@sha256:73aaf0…` (2.2 MB).
  Multi-arch resolution (index → amd64/arm64 manifest), bearer token flow
  and the CDN `307` layer redirect (followed manually, without forwarding
  auth) all exercised green.
- Push of both images to a loopback registry fixture (POST uploads → 202 →
  PUT blob → 201 → manifest PUT → 201; digest returned), then pull of the
  pushed tag back from the same fixture: green on both engines, digests match.
- Corrupted blob (loopback registry serving bytes ≠ the manifest's layer
  digest): `docker pull` fails with
  `digest mismatch: expected sha256:2dd1…, got sha256:54f8…` on **both**
  engines — fails closed, no image recorded.
- `conformance/smoke.sh` 15/15 with the default binary; `cargo test
  --workspace` 192 pass; musl `-p kiri-init` check clean (full-workspace
  musl check is not a gate: `ring` wants `aarch64-linux-musl-gcc`, absent
  on this machine — preexisting, unrelated to this slice).

## Performance

Cold store per pull (engine restarted with a fresh data root; blobs are
content-addressed, so this is the honest cold path). Interleaved
A/B/A/B/A, 5 trials per image, anonymous Docker Hub:

| trial | def alpine | h12 alpine | def busybox | h12 busybox |
| --- | --- | --- | --- | --- |
| 1 | 956 ms | 1400 ms | 1006 ms | 1781 ms |
| 2 | 1133 ms | 1573 ms | 1074 ms | 1422 ms |
| 3 | 1026 ms | 1488 ms | 982 ms | 1615 ms |
| 4 | 786 ms | 1502 ms | 970 ms | 1716 ms |
| 5 | 1251 ms | 1509 ms | 775 ms | 1433 ms |

| | def p50 | h12 p50 | delta |
| --- | --- | --- | --- |
| alpine | 1026 ms | 1502 ms | **+46 %** |
| busybox | 982 ms | 1615 ms | **+64 %** |

h12tiny is slower in all 10 trials. Warm-store pulls are parity
(~45–50 ms both, content already local). Push (loopback registry, fresh
registry per trial, 5 interleaved trials): parity — p50 63 ms (def) vs
64 ms (h12); a single 304 ms outlier for h12 in trial 5.

The expected cause: no connection reuse — every registry and CDN contact
pays TCP+TLS, and Docker Hub hands layers out to a CDN, so the extra
handshake is paid at least twice per pull. This is structural, not tunable.

## Size and supply chain

`target/release/kiri`: 4,061,680 B (default, as before) vs 5,036,224 B
(h12tiny registry) = **+974,544 B (+24.0 %)**. New lock entries
(feature-only; never built by the default build): h12tiny-client-sync /
-normalize / -tls-system 0.9.0 (MIT), rustls-graviola 0.4.0 (Apache-2.0 /
MIT), and their `async-io` stack. No vanilla hyper, no Tokio, no ring
additions, no OpenSSL.

## Decision

Keep ureq. The pilot demonstrates the seam works end to end (pulls, push,
corruption, resume, cancel) but the candidate transport loses on every
measured workload that moves bytes, at +24 % binary and a second trust
path. Reverting the flag is one Cargo feature; the pilot stays in tree
behind `kiri-image/h12tiny` as a documented negative result. Revisiting
requires a candidate with connection pooling for unix-socket-adjacent
registries and a measurable pull-time win.

Two follow-ups recorded for CTRS-21: silent engine death struck twice more
during this slice (both scratch engines went down between 09:49Z and
10:01Z with zero log output, right after the warm-pull rmi/pull burst —
strikes #6 and #7).
