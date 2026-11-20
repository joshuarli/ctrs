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
- **Loss.** FSEvents can coalesce or drop events. The host turns its
  `MustScanSubDirs`, `UserDropped`, `KernelDropped`, `RootChanged`, `Mount`
  and `Unmount` flags, and any batch that could not be sent whole, into a
  rescan (kind `s`, protocol 7) of the affected bind directories. A
  resumable DFS then re-reports entries whose ctime is at or after the last
  delivered batch minus 2 s. Each turn visits at most 128 entries or
  directory boundaries. The cursor retains one directory handle per depth,
  and the pending cutoff coalesces losses while a walk is active. A failed
  walk or delivery is logged and retried from the earliest pending cutoff.
  When bind roots change, the replacement stream replays from the last
  event id, so the gap between streams is covered.
- **Guest queue.** The agent queues lines the pipe to its writer refuses
  (1 MiB pipe, 8,192 queued lines) and retries every 20 ms. Beyond that,
  the queue collapses into one rescan of the share and the agent logs the
  count.
- **Rescan.** A rescan bumps the FUSE connection epoch and schedules a
  guest recovery walk. The worker retains its directory cursors and performs
  at most 128 cursor operations and one page of directory entries per turn.
  Each cursor operation skips at most 128 cached links. One restart flag
  coalesces additional rescans while it runs. It compares watched entries with host LOOKUP
  replies and reads watched directories to find names absent from the
  cache. The worker reports removed, replaced, modified and created names
  to inotify. It retries failed walks with a one-second delay. On virtiofs
  a stale-epoch dentry is revalidated with a LOOKUP rather than dropped, so
  a volume mounted inside an unchanged bind directory stays attached
  (`bind-rescan-keeps-mounts`).
- **Retained names.** A virtiofs inotify watch retains its directory's
  existing child dentries and metadata when the watch is installed. An
  internal fsnotify mark tracks subsequent creates, moves, changes and
  deletions, including events the user did not subscribe to. Watches on
  the same inode share the retained set. The last watch releases the set.
  This makes a missed deletion identifiable even after normal dcache
  reclaim or an unrelated lookup. Initial retention failure rejects watch
  installation. A later allocation failure is logged; recovery of a
  subsequently lost deletion for that name cannot be guaranteed.
- **Bounds and cost.** The host change channel holds at most 256 messages.
  The guest agent retains its 8,192-line queue. Recovery has one active
  work item, one restart flag, and a directory cursor per depth. Retained
  names occupy space proportional to the distinct entries of watched
  directories, rather than to the number of incoming events. In one scratch
  run of a prototype with the same retained-entry layout and 22,001 entries,
  the active FUSE inode, dentry and kmalloc-128
  slab counts after reclaim were 22,032, 22,680 and 23,679, versus 36,
  777 and 1,690 before the watch. At their reported object sizes this is
  about 25.5 MiB of additional active slab objects. The watcher process
  used four guest system CPU ticks during setup and one preflight event;
  this excludes host virtiofs work. This is one observation on a busy
  host, not a comparative timing result. Writeback caching remains off.

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
