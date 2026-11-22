# W2 resource-cycle pilot

This functional diagnostic consumes the existing fixed-work W2 fixture. It does
not qualify performance. Service images and workload inputs use the frozen
portfolio pins. Runs use engine blocks rather than interleaved pairs, and host
exclusivity must be reviewed separately. Historical proxy scores remain unchanged.

Before collection, `resource_cycles.BUDGETS` version w2-resource-v1 declares:

| Higher-is-worse metric | Allowed increase over comparable reference |
| --- | --- |
| Idle CPU | larger of 0.01 core or 3% |
| Package-idle and interrupt wakes | larger of 5/s or 3%, separately |
| Steady and sampled peak physical footprint | larger of 16 MiB or 3% |
| Next use, including stack setup and fixed work | larger of 10 ms or 3% |
| Explicit active-disk allocated bytes | larger of 16 MiB or 3% |
| Post-warmup footprint/allocation growth | 16 MiB, each; every cycle checked |

Return-to-initial tolerances are 16 MiB for footprint and disk allocation.
Five cycles after a separate warmup, 30 seconds initial idle and 30 seconds
post-cleanup reclamation per cycle are the minimum diagnostic design. Shorter
functional pilots retain unknown growth verdicts. A budget pass alone is never
a qualification pass. Observer CPU should stay below 0.01 core during idle;
record raw collection durations so scheduling interruptions remain visible.
The prior v3 sampler on/off controls still require final frozen confirmation.

Each main fixed-work trial records setup, workload and owned cleanup CPU/wakes/
physical footprint separately. Fast native boundaries bracket even very short
phases with no interior sample. The 200 ms trace supplies sampled peaks; it cannot
establish continuous high-water marks. Counter collection duration and operation
wall time are separate. Any missing daemon/VM or native counter invalidates totals.

Allocation snapshots run outside workload/cleanup CPU boundaries: before setup,
before work, after work/verification and immediately after cleanup, then after
the reclamation window. `st_blocks * 512` includes shared clone extents. The W8
allocation diagnostic also samples macOS per-file private bytes with
`getattrlist` and `ATTR_CMNEXT_PRIVATESIZE`. The same metadata call verifies
device, inode, node type and link count without opening the file for reading.
Private bytes are the bytes an individual file would release
on deletion, excluding bytes held by a clone or snapshot. Missing private
attributes leave that observation unknown. Isolated build-cache size remains
unknown. The scope is the explicit active backing files. Do not compare
an aged shared OrbStack disk with a fresh ctrs disk as a storage win. Repeated-cycle
deltas are descriptive until background allocation and workload histories are controlled.
W8 records separate ten-second idle windows before the pull and after
application cleanup. Each idle boundary verifies an empty running-container
inventory and the same backing-file identities.
[Apple `getattrlist` manual](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/man/man2/getattrlist.2)

Next use is a fresh stack setup/readiness plus a declared smaller fixed workload,
including command cost. It excludes cleanup. Exact seed and acknowledged-write
payloads are checked in every main/next-use trial; next-use cleanup precedes the
next cycle. This is a post-reclamation application journey, not a warm HTTP ping.

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/resource_pilot.py \
  --image-refs /Users/josh/repos/ctrs/.work/native-perf/results/w11-mixed-20261116T063716-8565/ctrs-host/refs.json \
  --ctrs-binary /path/to/signed/ctrs \
  --orbstack-storage-file '/actual/open/data.img.raw' \
  --orbstack-storage-file '/actual/open/swap.img'
```

Both options are required. The refs file must contain the five mixed-portfolio
references; the three W2 images must already be installed with matching ARM64
digests and DiffIDs before warmup. The pinned, network-isolated warmup boots the
guest and checks API source; its uniquely named container is cleaned up only
after ownership verification. The live ctrs daemon binary is then checked before
resource trials. Compose cannot build or pull images, and warmup cannot pull.
The plan records the pins and source hashes. These checks have not yet been proved by a native
resource run and do not establish qualification.

The supplied storage files must be nonsymlink regular files open by an identified engine
process. Duplicate inodes are rejected. ctrs uses its owned active data disk. The
command refuses active containers without stopping them, saves pre/post host gate,
process, power and thermal diagnostics, verifies unchanged running identity and
requires owned cleanup. A successful gate exit alone does not certify exclusivity.
All output under the printed run directory is marked unqualified. Use
`--cycles 2 --operations 1000 --next-use-operations 200 --idle-seconds 3
--reclaim-seconds 3` for a short functional coverage check; those settings cannot
meet the declared duration/cycle minima.
