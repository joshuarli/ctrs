Prefix: DSLP
Next: 7

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier C). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1, base ddaf012): code lines Rust 34.6k (`ctrs` 24k, `ctrs-init` 12k, `ctrs-image` 3.5k, `ctrs-proto` 1.5k), Python 23.8k (`bench/native`); no vendored trees. `make test` (new Makefile target, run by CI `macos` on pull requests) exits 0: cold 4m41s, warm 50s-1m52s on a busy host (observations only; the global `kache` rustc wrapper makes cold partial). `make lint` is red in `crates/ctrs` (DSLP-6). Fixed with obvious causes: bench tests that assumed their working directory (`test_w12.py`) or a quiet disk (`test_resource_cells.py`), two clippy sites in `ctrs-image`. Linux-only and privileged checks are Needs environment; the unit-level ones run in CI `linux-musl`.

## Tickets

### DSLP-2 · P2 · Diagnose: ultrareview into this backlog

- **Area:** deslop · diagnose
- **Where:** whole repository
- **Problem:** No review has ranked this repository's risks for the deslop pass.
- **Recommendation:** Run the deslop Diagnose step. Accept: the diff touches only docs, comments, and this file, and every finding names its Fix with.
- **Fix with:** deslop
- **Effort:** M

### DSLP-3 · P2 · Types: strict profile and typing findings

- **Area:** deslop · types
- **Where:** type checker and lint configuration; Rust/Python sources
- **Problem:** The strict-profile candidates in the deslop skill's tools reference have not been measured here.
- **Recommendation:** Run the deslop Types step. Accept: clean at the adopted profile, escape hatches not increased, witnesses recorded.
- **Fix with:** deslop
- **Effort:** M

### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and mutation results are unmeasured; no deslop mutation lane exists.
- **Recommendation:** Run the deslop Tests step. Accept: no undispositioned survivor in critical code, the test cost budget holds, and the lane is green where the tools are mirrored.
- **Fix with:** deslop
- **Effort:** L

### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M

### DSLP-6 · P3 · make lint is red: 51 clippy errors in crates/ctrs

- **Area:** deslop · ground
- **Where:** crates/ctrs/src/daemon/{engine,api,ports,mirror,buildgrpc,proxy,builder}.rs, builds.rs, guest.rs, service.rs, diag/report.rs
- **Problem:** At base ddaf012 `make lint` (clippy --workspace --all-targets -D warnings, nightly-2026-11-09) fails in `ctrs` (bin) with 50 errors, 51 in its test build: 35 collapsible_if (edition 2024 let chains), 6 type_complexity, 2 too_many_arguments (8/7), and one each of single_match-class, useless_format, unnecessary_lazy_evaluations, needless_borrows_for_generic_args, redundant_closure, manual_range_contains, print_literal, unnecessary_cast, double_ended_iterator_last. Ground fixed the two sites in ctrs-image (a single_match in archive.rs and an unused test variable in registry.rs); ctrs-proto, ctrs-vmm, xtask and Linux ctrs-init (checked in a rust:1.100.0-bookworm container) are clean. CI does not run clippy, so nothing gates it.
- **Recommendation:** Apply the machine-fixable lints with `cargo clippy --fix` per file and review each diff (let-chain collapses must keep evaluation order); give the six complex types names and the two eight-argument functions a parameter struct or a reasoned allow. Accept: `make lint` exits 0, `make test` unchanged. Then decide whether CI should run `make lint`.
- **Fix with:** deslop
- **Effort:** M

