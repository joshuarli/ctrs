# CTRS-15 — h12tiny pilot: HTTP/1.1 on `laputa-hyper-futures-lite` vs the handwritten parser

Date: 2026-11-14. Verdict: **no win — the handwritten `http.rs` stays production;
the h12tiny path remains behind the `h12tiny` cargo feature, off by default.**

## Design

Behind `--features h12tiny` (off by default; nothing compiled into the
default build), the accept loop routes each accepted connection through a
per-connection h12tiny/hyper HTTP/1.1 driver (`h12tiny-server` 0.9.0, MIT,
on `laputa-hyper-futures-lite =1.12.0-beta.1`; no Tokio, no rustls/OpenSSL;
the `http1` feature only). **Streaming routes are not piloted**: a
`recv(MSG_PEEK)` sniff of the first line keeps `/build`, `/images/load`,
`/images/create`, `/images/get`, `/push`/`/get`, `/events`, `/archive`,
`/logs`, `/stats`, `/export`, `/wait`, `/attach`, `/exec/<id>/start` on the
incumbent parser (they upgrade or stream the socket after `route()` hands
over). Everything else is parsed by hyper, collected into the crate-internal
request (8 MiB cap, as the incumbent), routed by the *same* `route()`, and
the raw bytes it writes are captured on a `UnixStream::pair` and re-wrapped
as one h12tiny response (never `Transfer-Encoding: chunked` — a leak
aborts the request loudly instead of corrupting framing).

## Correctness

`conformance/http.sh` is green under **both** builds (10/10 fixtures; shared
fixtures relaxed only where hyper's semantics differ from the incumbent's:
hyper answers contradictory framing itself with an empty 400, and its
header cap (~400 KB) is larger than the incumbent's 64 KiB — the fixtures
now accept either refusal). Attach/exec-style upgrades were verified by
being left on the incumbent (not piloted); they were **not** re-qualified
against h12tiny, which is one reason the pilot is not for production.

## Benchmark (interleaved A/B/A/B/A, 5 trials each, scratch engines, keep-alive single connection; `garbage-create` = POST with invalid JSON → 400)

| metric | handwritten (`def`) | h12tiny (`h12`) | delta |
| --- | --- | --- | --- |
| ping p50 (µs) | 181 / 206 / 189 / 190 / 196 | 237 / 244 / 244 / 238 / 236 | **+22…+33 %** |
| ping p99 (µs) | 242 / 228 / 201 / 203 / 285 | 253 / 270 / 293 / 253 / 253 | ≈ +5–22 % |
| version p50 (µs) | 158 / 178 / 166 / 169 / 172 | 215 / 222 / 223 / 214 / 212 | **+29…+33 %** |
| version p99 (µs) | 183 / 215 / 179 / 180 / 215 | 231 / 3924 / 384 / 226 / 229 | ≈ within noise (rare tail events, both sides) |
| garbage-create p50 (µs) | 256 / 259 / 249 / 249 / 240 | 289 / 300 / 284 / 296 / 299 | **+14…+20 %** |
| concurrent-16 wall (s, 2000 req) | 5.57 / 4.95 / 5.08 / 5.47 / 5.63 | 6.28 / 6.43 / 6.36 / 6.15 / 6.37 | **+13…+30 %** |
| concurrent-16 p50 (µs) | 30.3 / 23.4 / 28.6 / 31.8 / 30.4 | 35.0 / 37.2 / 35.4 / 35.0 / 36.2 | **+13…+52 %** |
| concurrent-16 p99 (µs) | 46.5 / 63.6 / 35.3 / 41.8 / 41.8 | 51.3 / 47.9 / 41.0 / 42.6 / 47.5 | overlapping |

Absolute latencies carry client-side (Python) overhead; the comparison is
A/B on the identical client, and the ordering — default faster in every
trial, every workload — is systematic, not noise.

## Size and supply chain

- default `target/release/kiri`: 4,073,824 B before the slice (4,076,560 B after; +2.7 KB from the #134 fixes).
- h12tiny `target/release/kiri`: 4,321,424 B (**+247,864 B, +6.1 %**), and `cargo check -p kiri --features h12tiny` adds ~minutes to a cold build (kache-warm checks are fast).
- New lock entries (feature-only, never fetched by the default build): `h12tiny-server`/`h12tiny-core` 0.9.0 (MIT), `laputa-hyper-futures-lite` 1.12.0-beta.1 (MIT, pins `=1.12.0-beta.1`), `async-net` 2.0.0 + `async-io` stack, `futures-lite` 2.6.1, `http` 1.5.0, `bytes`. **No vanilla `hyper` in the graph anymore; no Tokio, no rustls, no OpenSSL.** `cargo audit` clean (129 deps). Default build pulls none of these.
- Compile-time impact on `cargo check --workspace`: unmeasurable with warm cache (0.25–1.3 s both); cold impact unmeasured (recorded honestly as unknown).

## Decision

Keep the handwritten parser as production. The pilot remains in tree behind
`--features h12tiny` as a **negative result**: it is correct (oracle green)
but uniformly slower on the unix-socket API workload, costs +6 % binary and
a beta-locked dependency, and its upgrade/hijack semantics were never
qualified (streaming routes were not piloted). No cutover. Revisiting it
needs a measurable win on this workload, not parity.
