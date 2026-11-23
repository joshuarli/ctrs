# Handoff: continue from a Linux host (2026-11-23)

Read this first when resuming on the native `linux-amd64` host. The Mac work
named in the 2026-11-23 steering is finished. The
[reconciliation record](evidence/main-reconciliation-2026-11-23.md) has the
detail behind everything below.

## Where things stand

- `main` follows the recorded experiment decisions again (`657a0f2`):
  - gzip default loads;
  - Cached+Fsync data disk;
  - 250 ms refusal TTL;
  - no SCHED_MC, LSE or uprobes in the guest kernel;
  - no registry vsock, relay-batch, extra virtiofs devices or readiness
    logging.

  H3 and the cache-usage fix are kept. Tests in `b5ec34b` pin the kernel
  options, the disk contract, the TTL and the load compression.
- The Mac runtime is verified at `b5ec34b`. Signed host `7c5fc5be…`,
  initramfs `4c8bec12…`, kernel `19657ca4…`.
  - smoke 21/21;
  - e2e 509/0/0;
  - watch-recovery pass;
  - fuse-inode-bound pass;
  - `tests/layer-expansion.sh` pass.
- Mac decisions:
  - **Registry vsock is not promoted.** Ten-pair candidate/baseline W7 and W6
    cohorts were non-inferior in every cell with no strict win.
  - **W12 full-bind needs an owner decision.** See below.
- The H3-affected Mac cells were remeasured against OrbStack at `b5ec34b`.
  The [record](evidence/main-reconciliation-2026-11-23.md#mac-remeasurement-at-b5ec34b)
  has W1 warm, W6, W7 and W8 installed-default. Every other matrix cell still
  belongs to its older recorded binary.

## Linux tasks, in order

The host is the existing native x86_64 lane machine: Ubuntu 22.04.5, kernel
`6.8.0-1060-aws`, Docker 29.9.2 (frozen). Its evidence roots live under
`/home/ubuntu/ctrs-evidence/`.

1. **Copy the retained evidence off the VM before retiring it.** Copy every
   directory under `/home/ubuntu/ctrs-evidence/` to durable off-host storage,
   for example `rsync -a ubuntu@HOST:/home/ubuntu/ctrs-evidence/ <dest>/`.
   Then, at the destination, run `sha256sum -c` against each committed
   manifest in `docs/evidence/linux-*.sha256`, using the relative paths the
   manifests expect. Each evidence doc gives its own manifest's root. Record
   the destination, the file count and the verification output in a short
   addendum to this file. Do not build another preservation framework.
2. **Build the integrated runtime at current `main`.**
   `./scripts/setup-dev`, then `CARGO_ENCODED_RUSTFLAGS="" cargo xtask linux
   --arch amd64`. Record the SHA-256 of `target/linux-x86_64/release/ctrs` and
   `ctrs-init`. Run `make test` and `make lint`. As root, run
   `cargo test -p ctrs-init --target x86_64-unknown-linux-musl`; it must
   include the three new `layers::tests` compressible-layer regressions.
3. **Run the integrated Linux runtime suite in owned, disposable state.**
   Repeat the procedure in
   [linux-integrated-runtime-2026-11-22.md](evidence/linux-integrated-runtime-2026-11-22.md),
   using `~/ctrs-evidence/linux-integrated-20261122/restore-owned.sh`:
   - start ctrs through `bench/native/linux/ctrs-engine.sh start`;
   - run the isolated Docker daemon in a private netns, with its own
     containerd, roots and socket, and no default bridge;
   - run `tests/linux-host.sh` and `tests/kernel-features.sh` in a privileged
     container;
   - run `tests/e2e.sh` against each engine.

   Do not start, stop or reconfigure the host's `docker.service`. Compare with
   the `65b7bbd` result (ctrs 482/1/26, Docker 471/2/30). Classify each
   failure with evidence, as before (host VRF module, Docker's AppArmor mount
   denial). Report nonzero exits as nonzero.
4. **Run the compression regression on a Linux host.** With ctrs running:
   `CTRS_SOCKET=<sock> CTRS_LAYER_ROOT=/var/lib/ctrs/layers
   tests/layer-expansion.sh`. That is the host lane's layer store; read it as
   root. The `zstd-refusal-cleanup` check that the Mac had to skip must pass
   here.
5. **Linux lane performance: nothing more is queued.** H3 stays at C/B 0.773
   [0.707, 0.786] and is still C/D 1.164 [1.036, 1.180] against Docker.
   - Do not restart these finished investigations:
     - the W2 candidate loop;
     - the three rejected HTTPie residual attempts;
     - W5's observer/cadence investigation;
     - exhausted W13 headroom configurations.
   - The W3, W12, resource-accounting and networking limitations stay open
     and stated.
   - Registry vsock, relay-batch and the readiness logging landed after the
     2026-11-22 Linux cohorts and are reverted again, so the Linux runtime
     matches what H3 measured. The one exception is the boxed `decoded()`
     reader in the layer install path. A one-cohort HTTPie first-use check at
     the new SHA is optional, not required.
6. Record the results as one addendum here plus a SHA-256 manifest beside it,
   and update the current-status sections.

## Decisions waiting for the owner (not Linux work)

- **W12 full-bind transport: parked by the owner (2026-11-23).** VZ virtiofs
  adds about 125 µs to every bind request. The only lever left is a ctrs-owned
  FUSE-over-vsock bind transport, and the owner parked it because FUSE is
  tricky. W12 full-bind stays a recorded VZ-bound loss (workflow 1.30×,
  install 2.11×, verification 4.16×). Mixed and all-volume layouts stay near
  parity. Reopen only with a new design that addresses the FUSE protocol,
  security and semantics risk, or with new evidence of a cheaper lever. The
  probe and estimate are in the
  [record](evidence/main-reconciliation-2026-11-23.md#w12-full-bind-the-next-intervention-boundary).
- **W11 12-hour legs.** These are not admitted. Both engines exceeded the
  short-run growth budgets, and the frozen cell contract and durability
  admission are still incomplete. Launching them now would be a known-failing
  qualification, not progress.
- **W1/W10 engine-cold.** These need a disposable OrbStack endpoint. The shared
  one stays with its users.
- **Disk durability.** Fsync stays the contract. Promoting Full needs an
  explicit decision and fresh storage cohorts.
