# Verify PostgreSQL relation ENOSPC recovery

Use a new owned ctrs root for each disclosed binary variant. This diagnostic
fills guest space with unwritten extents. It does not fill the host filesystem.

Run the 64MiB preflight first:

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/storage_space_pilot.py \
  --stage allocation \
  --fsync-binary .work/tmp/disk-expand-target/release/ctrs \
  --full-binary .work/tmp/full-sync-target/release/ctrs \
  --portfolio-archive .work/native-perf/inputs/w8-portfolio-v6/portfolio.tar
```

Require FIEMAP unwritten extents, exact database contents and at most 8MiB of
active backing-file allocation growth. Run the relation test with the same
command and `--stage enospc`. Both stages require 2GiB host free space.

The helper reserves guest space until non-root available capacity reaches 8MiB.
It recomputes available capacity to account for extent metadata. After each
allocation attempt of at most 64MiB, the helper waits while the controller
checks host growth and requires at least 2GiB free. A failed check releases the
reservation before another attempt. ENOSPC during reservation reduces the
allocation step. Other allocation errors fail. FIEMAP must confirm unwritten
extents. Reservation growth on the host must stay within
512MiB. Both limits are diagnostic budgets, not final resource acceptance.

PostgreSQL keeps fsync, synchronous_commit and full_page_writes enabled. The
transaction generates 32MiB with LOCAL work_mem=128MB to avoid a temporary spill.
It must fail with ENOSPC on a relation or WAL file. A temporary-file failure does
not pass. Release the reservation, verify all 100 acknowledged records, then
commit and verify 10 more. Named-volume identity must remain unchanged.

The helper releases its file on command, stdin EOF or a 90-second alarm. The
controller closes stdin on failure, observes the helper and removes only its
labelled fixture. Commands are bounded. For unattended execution, launch the
controller through the finite supervisor described in [durable-job.md](durable-job.md)
with frozen source, image, binary and guest receipts. Inspect both the supervisor
status and workload cleanup errors.

The run saves source copies, hashes, FIEMAP and filesystem identity, exact data,
PostgreSQL errors and actual allocated bytes under `.work/tmp/space-*`. Host
allocation uses stat.st_blocks and can include shared clone extents. These
records do not prove exclusive APFS reclaim, root-reserved-block exhaustion,
host-full storage, power-loss durability, performance or 12-hour reliability.
Fsync and Full labels describe supplied binaries. Their recorded hashes identify
the actual variants. This diagnostic does not promote the Full candidate.
