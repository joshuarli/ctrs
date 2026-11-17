# Native resource-cycle diagnostics, 2026-11-17

The pinned W2 resource fixture is integrated in 44901ff. It verifies the three
installed ARM64 image digests and DiffIDs, checks the API files in an owned
network-isolated warmup, then verifies the live daemon against the requested
binary. Compose cannot pull or build. Warmup boots the lazy VM before ownership
discovery; cleanup verifies its campaign label even on source-check failure.
Shared Compose fallback cleanup now verifies exact project labels and full
container IDs instead of deleting name-prefix matches (22ef421).
The bounded `runner.py check resources` selector includes the new contract:
63 tests pass in 1.670s with zero skips. No full suite was run.

`PYTHONDONTWRITEBYTECODE=1 python3.14 bench/native/runner.py check resources`
passes 63 selected tests, zero skips, in 1.670s. The selector includes the new
pin/source/cleanup contract. Full suites remain manual-only.

## Native functional proof

Job `0431cc8761244eb6950637c7736a01fb` under
`.work/tmp/resource-pinned-proof-20261117/job` exits 0, cleanup complete. Results:
`.work/native-perf/results/w2-resources-20261117T004927/`. All 81 frozen input
receipts are rechecked after completion (the receipt count below is authoritative
if the input set changes). No workload error or missing phase counter occurs.

The run uses the complete balloon accounting repair: signed host SHA-256
`fda6246703f48c42a126fb0b63ecc246619e03760598cd569e6d0760207681f6`,
6,613,968 bytes; initrd `6ae4d3abfb3be1f4dcc1edf200261a29e22ad96c922c2d677d5874df21abc8b2`;
stock kernel `35087713fd7b1b152b1ac0333e42edbcee482c82c6e695f27a8f126c271eee43`.
Explicit 2 vCPUs/8192MiB match product defaults. Sleep=60s and balloon quiet=120s
remain defaults. The dedicated existing root retains its prior image/build cache;
its active-disk allocation is not a fresh installation or exclusive APFS size.

To reproduce with those signed artifacts and guest directory, set
`CTRS_GUEST_DIR` to the directory containing that kernel/initrd/template and
`CTRS_CPUS=2 CTRS_MEMORY_MIB=8192`; leave sleep/balloon overrides unset. Run:

```sh
TMPDIR=$PWD/.work/tmp PYTHONDONTWRITEBYTECODE=1 python3.14 \
  bench/native/diagnostics/resource_pilot.py --engines ctrs \
  --image-refs /absolute/path/to/frozen-portfolio-refs.json \
  --ctrs-binary /absolute/path/to/signed/ctrs \
  --cycles 2 --operations 1000 --next-use-operations 200 \
  --idle-seconds 3 --reclaim-seconds 3
```

The refs must identify the exact five images in the checked portfolio/worker
pins, already installed in the dedicated engine. Historical refs are saved at
`.work/native-perf/results/w11-mixed-20261116T063716-8565/ctrs-host/refs.json`.
The local registry address is provenance, not a registry dependency during this
run. Refuse adoption of an already active warm-root daemon before reproduction.

Functional counter coverage is complete. Two cycles/3s deliberately fail the
five-cycle/30s minimum, so footprint/allocation growth stays **unknown**. Initial
idle physical footprint is 665,487,352 bytes; post-cycle values are 717,670,536
and 720,193,672. This motivates the declared longer diagnostic; it establishes
neither a leak nor acceptable return-to-initial memory. Active-disk allocation
rises from 56,983,355,392 to 56,986,320,896 bytes. Shared extents/build-cache size
remain unknown. No timing or OrbStack parity claim follows.

All 87 frozen input receipts were rechecked unchanged after completion.
Receipts: summary SHA-256
`ad1ca2b6881539eaefbb1f2b3e326b6469cebd2a79aecbc2c43503ab3b50428a`;
plan `dcb8ebe3fb9536b28bc66b668f072aca92a2cc721873920e66be71f2c93d7045`.

## Five-cycle growth failure

Job bc957b41bea04c02b46620b63b3f54f8 under
`.work/tmp/resource-five-cycles-20261117/job` exits 0, local cleanup complete.
Run `w2-resources-20261117T005046` uses the same pins/candidate/settings and
operation counts above, with five cycles and 30-second initial/reclaim intervals.
Application assertions, complete counters, unchanged running identity, empty
final container inventory and all 87 frozen input receipts pass. Both host
timing pre/post tools exit 0; independent machine exclusivity is not established,
so this engine-block diagnostic still establishes no performance qualification.

The physical-footprint budget **fails**; a successful diagnostic exit does not
override that result. Initial steady physical footprint is 696,059,896 bytes.
Every steady reclaim observation is retained:

| Cycle | Physical footprint, bytes | Active disk allocated, bytes |
| --- | ---: | ---: |
| 0 | 720,504,872 | 56,986,320,896 |
| 1 | 736,036,904 | 56,986,320,896 |
| 2 | 735,725,632 | 56,986,419,200 |
| 3 | 742,246,464 | 56,986,419,200 |
| 4 | 740,345,920 | 56,986,419,200 |

Maximum minus first post-warmup cycle is 21,741,592 bytes; maximum minus initial
is 46,186,568 bytes. Both exceed their unchanged 16MiB budgets. Active-disk
growth/return is only 98,304 bytes and passes. Exclusive allocation and isolated
build-cache size remain unknown. Final native samples attribute roughly 730MB
to the VM helper and 10MB to the daemon, so guest/VM attribution comes next;
these observations alone do not establish a leak or a cache-reclamation remedy.

Summary SHA-256:
`da2d0b301b894f160162a4b1a33b2146a0caecb45fe89f4ad3c1031259706e53`.
Do not repeat this run to erase the failed cell. The next bounded diagnostic
adds guest meminfo/vmstat/slab snapshots through one owned resident probe, keeps
the same five cycles, then tests explicit cache release and normal default
sleep/wake. That probe/cache action makes it a separate attribution fixture;
neither forced cache dropping nor the probe is a product policy change.

## Attribution and default sleep

Attribution job 1b5e52c1b6e24b16b24d22cfafc831d2 under
`.work/tmp/resource-growth-attribution-20261117/job` exits0 with clean teardown,
all87 frozen receipts unchanged. All12 fixed-work application trials pass
(8,000 operations total), with zero recorded guest `oom_kill` counters and no
accounting fallback. One constant owned Python probe keeps the guest resident
during the five attribution cycles; this is a separate fixture from the failed
default-policy run above. It does not replace that result.

The VM helper grows from729,908,736B to758,646,272B at the cycle snapshots,
while the daemon falls from15,516,272B to9,241,224B. Guest page cache stays
201,464KiB across the initial and cycle snapshots; slab rises by only1,836KiB.
The current evidence therefore points to guest/VM physical residency rather
than increasing daemon storage or comparably growing guest live allocations.
It does not prove the underlying VZ mechanism or an unbounded leak.

After an explicit guest sync/cache-drop, Cached falls201,464→12,700KiB
(184.34MiB), but immediate native footprint falls only49,152B (48KiB).
The subsequent30-second median is768,051,336B. This misses the predeclared
32MiB useful-reclaim screen: no product cache-dropping policy is selected.

After removing the owned probe, normal default sleep is observed, the old VM
helper no longer exists and its dedicated disk is closed. The daemon remains
alive at8,995,464B native footprint. That is a daemon observation, not a
complete engine CPU interval or a zero substituted for a missing VM counter.
The same daemon then boots a new VM identity with the exact pinned assets,
checks API source and completes a fresh exact1,000-operation W2 stack. This
proves functional next use, not persisted DB recovery across sleep, qualified
wake latency or full transition CPU accounting.

Result SHA-256:
`af2aa08315b03e83353c367dc04826e119ad83d75954b69e53a33b8c86a1c6a4`;
predeclared plan `04aee9a66ab878fb7c917b4c9eb4b08763f5dc04f6b614e5ce6eba14fae8f40f`.

Native feature-admission job c8d90a4955e14f3eb42ad127d8c1e9c2 also exits0,
owned cleanup complete, all87 inputs unchanged. The live balloon device5
negotiates bits0/2 but neither free-page hint bit3 nor reporting bit5. The
[Linux feature definitions](https://github.com/torvalds/linux/blob/v6.18/include/uapi/linux/virtio_balloon.h),
[sysfs bit order](https://github.com/torvalds/linux/blob/v6.18/drivers/virtio/virtio.c),
and [driver feature checks](https://github.com/torvalds/linux/blob/v6.18/drivers/virtio/virtio_balloon.c)
support that interpretation. Stock guest config already enables page reporting.
A guest-only reporting-parameter experiment is not admitted on this negotiated
device. This does not establish what a different host device offers.
Raw result is `.work/tmp/virtio-feature-admission-20261117/result.json`.
SHA-256: `55266dd1fb69dc314f70c81e2ef61b2b49d7903b20f1df0154a956dd4dd29ca7`.
After compaction, cache release and feature admission selected no resident
reclaim remedy, move to the real W9 parallel-build boundary. Keep the failed
resident growth and installed-default lifecycle accounting cells open.
