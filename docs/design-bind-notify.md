# Design: Mac-side change notifications for bind mounts

Status: **implemented 2026-11-18; recovery contract revised 2026-11-20.**
It adds host→guest `Msg::HostFsEvents` (wire protocol 6, rescan kind in 7)
and guest kernel patches 0006 (`/proc/ctrs/fsnotify`) and 0012 (echo proof
and rescan). The
owner delegated the approval. The host watcher is
`crates/ctrs/src/daemon/fsevents.rs`. A forked writer in
`crates/ctrs-init/src/linux/fsnotify.rs` writes the events, so the agent
stays single-threaded. `tests/e2e.sh` `bind-inotify-*` covers save, atomic
replace, create, rename and delete.

## Problem

Containers on ctrs never see inotify events for edits made on the Mac under a
bind mount. On 2026-11-18 a raw inotify probe on `-v <mac dir>:/w` tried
save, atomic replace, create, rename and delete. OrbStack delivered events
for all five; ctrs delivered none. The W12-watch fixture (`tsc --watch`,
fs.watch backend, Kutt workspace) shows the user-visible effect: ctrs bind
**missed 140 of 140** edit results, while OrbStack bind missed none. Watchers
such as tsc, webpack, vite, nodemon and chokidar only work on ctrs if they
poll.

Cause: the guest mounts the Mac's `/` as virtiofs tag `ctrs-mac` at
`/mnt/mac` (`crates/ctrs-init/src/linux/mod.rs:349`), and bind mounts are
subtrees of it. Linux fsnotify only fires for operations made through the
guest's own VFS. Apple's virtiofs server sends no change notifications, and
ctrs has nothing that forwards them.

## Proposal

1. **Host watcher.** The daemon runs one FSEvents stream with
   `kFSEventStreamCreateFlagFileEvents | NoDefer` and low latency (about
   10 ms). It watches only the source directories of bind mounts in running
   containers, and reference-counts them as containers start and stop. It
   never watches all of `/`. Each event carries a Mac path and flags
   (created, removed, renamed, modified, attribute changed).
2. **Message.** A new `Msg::HostFsEvents { events }` on the existing control
   connection, host→guest, with no reply. Each event is a
   `kind: u8 | path: str`, and the path is guest-relative under `/mnt/mac`.
   Batches stay under `MAX_FRAME`. The protocol already says unknown kinds
   are ignored by an older agent, so the change is additive: an old guest
   keeps today's behavior.
3. **Guest injection.** ctrs-init writes each event to a small kernel
   interface added by patch 0005, for example a write-only
   `/proc/ctrs/fsnotify` that accepts `kind path`. The kernel resolves the
   path under `/mnt/mac` and does the following:
   - **modified or attribute changed:** invalidate the cached attributes, then
     call `fsnotify_modify` or `fsnotify_change` on the inode.
   - **created:** invalidate the parent's entry cache, look the name up, then
     call `fsnotify_create` (or `fsnotify_mkdir`) on the parent.
   - **removed:** call `fsnotify_delete` on the parent, then `d_invalidate` the
     dentry.
   - **renamed:** FSEvents reports renames as separate old/new path events.
     Each becomes removed plus created. Rename cookies (IN_MOVED_FROM/TO
     pairing) are not reproduced.

   inotify watches belong to inodes, so containers that watch the path
   through their bind mounts receive the events. Fanotify mount marks would
   not, which is acceptable.
4. **No user-file writes.** Injection must never touch the Mac file.
   Re-setting attributes or touching files from the guest would modify user
   data and would loop back through FSEvents.

## Coherence contract (2026-11-19)

Notifications are best effort on the Mac side, so the guest never treats
their absence as proof that nothing changed, and it never skips one it
cannot prove redundant.

- **Echoes.** The host reports the guest's own virtiofs writes too.
  Patch 0012 skips an event only when it provably reports the guest's own
  change: a removed name that is already negative in the guest, or a name
  whose inode the guest changed since a notification last named it and
  whose LOOKUP returns the same node with the cached size, mtime and
  ctime. Everything else is raised. A same-node change is raised in place
  (attributes refreshed from the LOOKUP reply, page cache dropped, dentry
  kept). The earlier rule (skip any name changed here within two seconds)
  hid a Mac edit that followed the guest's own; `bind-mixed-writer`
  reproduces that on the old kernel and passes on the new one.
- **Loss.** The host translates FSEvents loss flags and failed delivery
  into a rescan. A resumable walk revisits at most 20,000 entries per loss
  and 128 entries per turn. It stays on each bind root's device, skips
  unreadable entries, and keeps its cursor when bind roots change. Failed
  delivery retries only the undelivered batch.
- **Guest queue.** The agent queues lines the pipe to its writer refuses
  and retries every 20 ms. When its 8,192-line queue fills, it schedules a
  share rescan and logs the count.
- **Rescan.** A rescan bumps the FUSE connection epoch and schedules a
  recovery walk. The worker compares cached inode attributes and compares
  each watched directory's host listing with its retained name set. It
  reports missing, new and replaced names to inotify. For a retained name
  with no checked cached dentry, it performs a LOOKUP and reports a
  modification because the previous attributes are unavailable. It also
  uses watched inode marks to report overflow for per-file watches and for
  directories the walk could not reach. Directory failures receive up to
  three attempts with backoff, then queue overflow. Entry
  failures are retried and logged before they are skipped. The writer does
  not wait for FUSE operations held by the worker.
  Overflow and attribute events for unvisited watches are sent after the
  watch table lock is released, because an `IN_ONESHOT` watch tears its
  mark down inside the event and re-takes that lock (patch 0016); the
  `oneshot` case in `tests/watch-recovery.sh` hangs the guest on the
  0013–0015 kernel and passes with 0016.
- **Retained names.** Watches on the same virtiofs inode share a name set.
  The initial set costs one directory scan, without a LOOKUP per entry.
  An internal mark updates names on creates, deletes and moves. It does not
  subscribe to child writes. The set holds names and directory-entry inode
  numbers, but no dentry, mount or memcg references. Allocations are not
  charged to the watching container's memcg. On 64-bit guests each name has
  56 bytes of fields before its bytes and allocator rounding. A six-byte
  name occupies 64 bytes.
- **Bounds and degraded recovery.** Name allocations use at most the lesser
  of 64 MiB and one sixty-fourth of guest RAM. `/proc/ctrs/watch_bytes`
  reports allocated bytes and the limit. If a name set cannot be retained,
  the kernel releases it, logs once, and reports `IN_Q_OVERFLOW` and
  `IN_ATTRIB` for that directory on recovery. Applications must rebuild
  their view after overflow. The budget is global and first come: one
  container can exhaust it for others. Linux reports overflow with watch
  descriptor -1. libuv can ignore that event, so its users cannot rely on
  this degraded path to trigger a rebuild. The counter (mode `0444`)
  exposes aggregate watch activity to guest users. These limitations are
  accepted. The host's root updates share a single coalescing wakeup.
  Writeback caching remains off.

The opt-in `CTRS_TEST_FSEVENTS_GATE` is used only by
`tests/watch-recovery.sh`. Its loss gate suppresses host callbacks. Its
overflow gate buffers the real changes and sends them after a large test
batch, so the regression can assert guest queue loss without host loss.
Neither gate is active without that environment variable. The wire
protocol remains version 9; no new message or event kind is required.

Regressions in `tests/e2e.sh`: `bind-mixed-writer` (in-place overwrite and
atomic replace by the Mac 0.3 s after the container's own write; final
bytes and a re-reading builder), `bind-made-here-mac-create` (nested Mac
changes inside a container-made directory), `bind-burst` (20,000 Mac
creates past the guest queue), `bind-root-churn` (stream replacement while
the Mac edits), `bind-rescan-keeps-mounts` and `bind-root-renamed`.

## Host descriptor bound (2026-11-20)

Virtualization.framework's virtiofs server keeps one host file descriptor
open for each inode the guest has looked up. It closes the descriptor when
the guest sends `FUSE_FORGET`, which happens only when the guest evicts the
inode. The guest has enough memory that its dcache is rarely reclaimed.
Walking a bind-mounted tree therefore pins one Mac descriptor per file. On
one scratch engine, a 150,000-file walk raised the VM process from 38 to
150,192 descriptors. After `echo 2 > /proc/sys/vm/drop_caches` in the
guest, the process held 48. On this Mac `kern.maxfilesperproc` is 245,760
and `kern.maxvnodes` is 263,168, and the vnode table is shared by every
process. W12 full-bind cohorts reached ENFILE on the Mac and failed module
resolution in the guest.

Kernel patch 0017 bounds the live virtiofs inodes in each guest, across all
virtiofs mounts, because one VM process serves every share. The default
bound is 65,536, about a quarter of the per-process limit. With it, two
VMs together stay at about half of the vnode table. `/proc/ctrs/fuse_inodes`
reads `<live> <bound>`; a `CAP_SYS_ADMIN` write sets the bound, and 0
removes it. When a new inode takes the count past the bound, a work item
prunes unused virtiofs dentries in LRU order (referenced dentries get a
second pass) until the count is at most seven eighths of the bound. Each
pass walks every memory cgroup's dentry list with its own budget. A first
version walked the lists with one shared budget, root list first. After
`tests/watch-recovery.sh`, that budget never reached the walking
container's list: the next 150,000-file walk reached 196,963 descriptors.
The work visits only virtiofs superblocks, so it never waits on another
filesystem's mount or unmount. FUSE
evicts an inode on its last reference, so each pruned dentry sends
`FUSE_FORGET`. In-use dentries are skipped: open files, working
directories and mount points stay. Inodes with an inotify mark stay too,
because the mark holds an inode reference. Retained watch names (patch
0014) are not dentries and are not touched. Progress is counted in evicted
inodes, not isolated dentries. If two passes evict nothing because every
inode is in use, pruning pauses for one second.

The cost is a fresh LOOKUP for a pruned name, and the loss of that file's
guest page cache. Working sets under the bound are unaffected. A walk-and-
read of 150,000 files took 31.3 s without the bound and 32.8–34.9 s with it, on
a loaded host.

`tests/fuse-inode-bound.sh` walks a tree larger than the bound. It asserts
that the VM process stays under the bound plus a margin, that every file
and every file held open across the walk reads back its own path, and that
descriptors return after the guest drops its caches. The walk check fails
on the 0001–0016 kernel and passes with 0017, on a fresh boot and right
after `tests/watch-recovery.sh`.

## Remaining questions

- **Ordering and latency.** W12-watch's missed/stale counts and
  edit-to-result latency are the acceptance measures; a watch trial with
  any missed or stale result is now scored as failed. Its latency observer
  is exec-poll limited and should move into the container before it is
  used for tail claims.
- **Scale.** The watched-root set is bounded by running containers' bind
  sources, and streams stop when containers exit.

## Acceptance

- W12-watch bind on ctrs: no missed or stale results beyond OrbStack's count
  on the same fixture version, measured over a 10-pair paired cohort.
- No regression in W12 full-bind build phases.
- The e2e raw inotify probe covers save, atomic replace, create, rename and
  delete.
