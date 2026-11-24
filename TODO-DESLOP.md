Prefix: DSLP
Next: 8

Deslop backlog. Campaign sequence and state are in [the roadmap](docs/roadmap.md).

## Tickets

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

