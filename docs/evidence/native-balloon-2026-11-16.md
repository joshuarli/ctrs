# Native balloon reclamation diagnostic, 2026-11-16

The three-pair calibration found no native physical-footprint reduction during
requested inflation, followed by higher read CPU in each pair. This is a
mechanism lead, not evidence that ballooning is useless under host pressure or
that disabling it is safe. Product defaults remain unchanged.

## Design and integrity

Raw source, plan, counters, snapshots, results and analysis are under
`.work/tmp/vz-balloon-reclaim-20261116/`. Durable job
`e07ad19c53fd462d9db66d7b80d36074` exits 0, all six payload/hash checks pass,
zero guest OOM kills are observed, and owned containers/volumes/daemons clean up.
Every scenario writes/fsyncs a 2GiB zero file in a uniquely owned named volume,
idles for 60 seconds, then reads and hashes every byte.

Three pairs alternate inflate/hold, hold/inflate, inflate/hold. Host executable
58f64738…, stock pinned guest, 2 vCPUs/8192MiB and pinned native Python image are
common. Each scenario has a new owned VM lifetime. Existing quiet thresholds
20 seconds versus 86,400 seconds exercise shrinking versus holding the ceiling;
both retain guest-stat collection. `CTRS_NO_BALLOON` would also disable that
collection and was deliberately avoided. VM sleep is disabled in this resident
control. The normal 120-second shrink delay and 60-second sleep policy remain
unchanged. No controlled host-memory pressure was applied; all timing is ineligible.

## Observations and limits

Requested target starts at 8GiB. Inflation reaches a requested target near
274MB, while held controls retain 8GiB. The native `ri_phys_footprint` counter
does not fall in the inflation windows; native RSS does not fall either.
For example, the first inflation window changes VM physical footprint from
3,175,797,656 to 3,176,863,072 bytes. These are same-process before/after
observations, not memory comparisons between differently aged VMs.

After the idle window, the reread's paired inflate/hold engine-CPU ratios are
1.788, 1.754 and 1.843. Idle CPU is also higher in the inflation conditions.
Raw whole-operation boundaries include container setup/read/hash/removal;
CPU includes the identified daemon and VM. These diagnostic observations do
not qualify application latency, idle observer overhead or resource budgets.
The native sampler measures physical footprint separately from RSS, and neither
counter supplies a per-process compression breakdown.

The original guest cache snapshot is after the reread, so it cannot independently
prove cache contents immediately before reading. Requested target also does not
prove achieved inflation. Guest deflate-on-OOM and pressure-driven growth can
intervene without an OOM kill. The calibration does not establish behavior under
host pressure or near the VM's usable-memory limit. The source's contradictory
comments about returning Mac memory are hypotheses, not platform evidence.

## Independent review and next proof

Worker `usrw_26b74548-8aad-4d46-997c-efd34333556a` is terminal succeeded, no
changed files or commits, retained tree `.work/wt/np-balloon-review`, base
1074737. Parent independently confirms clean diff and untracked status. Its
report is retained in `independent-review.json` beside the calibration.

The review supports a bounded experiment, not disabling shrinking. It identifies
actual inflation, compression/host-pressure response, application next-use costs
and limits/growth behavior as unresolved. API quiet is not application idle;
holding the target preserves a finite VM ceiling and container limits, but it
does not prove equivalent host-pressure behavior.

The immediate follow-up uses one inflate/hold mechanism pair with Linux
`balloon_inflate`/`balloon_deflate` events, page size and cache snapshots before
and after idle and after reread. Host `vm_stat`, observed pressure level and
owned-VM `vmmap -summary` are recorded outside work boundaries. It applies no
host-pressure stressor. The stock kernel enables memory ballooning and balloon
compaction; the [Linux event implementation](https://github.com/torvalds/linux/blob/v6.12/mm/balloon_compaction.c)
counts enqueue/dequeue events. Actual captured counters and page size, rather
than the requested VZ target, must support the inflation inference. Missing
events or failed native summaries remain unknown; no replacement runs to green.
Controlled-pressure and real W2/W6 proofs remain necessary before a default
policy change.

| Artifact under the calibration root | SHA-256 |
| --- | --- |
| `plan.json` | 4cdf12d28185905b6e6807ad484bf69ffe1d14eb9ebb6a21fa5841ee20de7310 |
| `job/status.json` | a877bb7dac30b63d16dc410689bd77247d18969336c8966d415c8a97409d2aa6 |
| `analysis.json` | 09be6c7342d4e8297042826d60947ffde6a77ec32da28e6c5d09e152ac6d2d20 |

## Actual inflation follow-up

Job `.work/tmp/vz-balloon-actual-20261116/job`, ID
`78dffe92188a4b3685de5803f403e5e0`, exits 0 with both payload/hash checks and
owned cleanup complete; all 83 frozen receipts remain unchanged. Both guests
report Linux 6.18.58 and 4KiB pages. This is one mechanism pair, not speed or
default-policy qualification.

Before idle, inflation/deflation counters are zero. After idle the inflation
case records 2,036,482 enqueued and 19,456 returned pages: net 8,261,738,496
balloon bytes. Guest cache falls from 2,161,479,680 to 12,664,832 bytes;
available memory becomes zero. Native VM physical footprint changes from
2,515,357,656 to 2,609,500,744 bytes rather than falling. After reread, net
balloon bytes fall to 6,168,772,608 and cache returns to 2,014,470,144 bytes.
The hold control has no balloon events and retains about 2.23GB of cache.
All observed OOM-kill counts are zero.

All native summaries succeed. `vmmap` reports about 2.4GiB physical footprint
after inflation, agreeing with the native counter, and zero swapped bytes in
its region summary. Observed kernel pressure level remains 1 in all snapshots;
no pressure stressor was applied. These observations close the actual-inflation
and before-read-cache gaps, while leaving pressure-dependent reclaim and real
application performance unproved. They do not justify disabling ballooning.

| Artifact under the actual-inflation root | SHA-256 |
| --- | --- |
| `plan.json` | b895f504b845c437bcc1449a1dde3ef809eb3aa884b336f8737cd04bc1165250 |
| `job/status.json` | ce1fafeb15aa5e9cd337f8dbe0f6544859a4fadb82c86a63b6671444551098f3 |
| `analysis.json` | 848a08f44efdc4c808a415700881f9df1d9d3dfb917b95cf85c26bf5dc460118 |

## Reserve arithmetic candidate remains unpromoted

The SDK targets total physical VM memory in whole MiB; Linux `MemTotal`
excludes memory reserved at boot. Private commit 4ecd599 in
`.work/wt/np-balloon-reserve`, branch `fix/np-balloon-reserve`, adds that reserve
to held-use plus headroom, rounds up for the SDK, and holds the ceiling for
unknown/invalid totals. It preserves the existing timer, growth, sleep and
64MiB update hysteresis. One new regression fails the old arithmetic; all three
selected Rust tests pass after correction. The signed candidate is
fda6246703f48c42a126fb0b63ecc246619e03760598cd569e6d0760207681f6,
6,613,968 bytes versus 6,613,856 baseline. No guest/wire/disk format change.

Independent scout usrw_9a3a8456-e686-4fbe-90f0-3da3c97abbb9 is terminal
succeeded with no demonstrated source defects and no changed files. Parent
reviews the exact diff and verifies clean review-tree status. Source review and
unit success do not override the native failure below.

The native comparison `.work/tmp/balloon-reserve-paired-20261116/job`, ID
`34664b99200b4d0b8a2148df74391ba5`, exits 1 with clean owned teardown. It stops
at the first candidate invariant failure; no replacement or extra pairs.
The candidate's target preserves about 270.5MB of calculated usable headroom,
but guest `MemAvailable` is only 44,544,000 bytes, below the declared 128MiB
practical floor. Its following read was not admitted. The baseline had about
88.9MB calculated headroom; actual balloon deflation can make its instantaneous
available value exceed the requested budget. Both use the same stock guest,
2 vCPUs/8192MiB, accelerated quiet=0, resident idle=0 and a 45-second interval;
this distinct comparison is not pooled with the preceding 60-second calibration.

The root-cgroup held-use reading is about 5MB in the failed candidate, whereas
the captured total, available and actual-balloon values imply 226,048KiB of
nonavailable memory after excluding balloon pages. That quantity includes
watermark protection and is not identical to cgroup-held physical memory.
The next source slice audits the guest memory model instead of weakening the
128MiB check. The host-only candidate remains private/unmerged pending that
accounting repair and fresh native proof. No performance or memory-policy
promotion follows from the passing unit tests.
