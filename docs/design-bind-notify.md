# Design: Mac-side change notifications for bind mounts

Status: **implemented 2026-11-18.** It adds host→guest `Msg::HostFsEvents`
(wire protocol 6) and guest kernel patch 0006 (`/proc/ctrs/fsnotify`). The
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

## Open questions

- **Echoes.** A guest-side write also produces a host FSEvent, so the guest
  gets a second IN_MODIFY for its own write. Watchers debounce duplicates.
  Suppressing them would need write attribution that FSEvents does not
  provide. The first version measures the duplicate rate instead.
- **Staleness.** Is the guest's virtiofs attribute and entry cache also stale
  after Mac edits, or only un-notified? Step 3's invalidation covers both. A
  polling-watcher W12-watch condition would measure staleness independently.
- **Ordering and latency.** FSEvents coalesces events. W12-watch's
  missed/stale counts and edit-to-result latency are the acceptance
  measures. Its latency observer is currently exec-poll limited and should
  move into the container before it is used for tail claims.
- **Scale.** FSEvents handles large trees. The watched-root set must be
  bounded, and the daemon must stop streams when containers exit.

## Acceptance

- W12-watch bind on ctrs: no missed or stale results beyond OrbStack's count
  on the same fixture version, measured over a 10-pair paired cohort.
- No regression in W12 full-bind build phases.
- The e2e raw inotify probe covers save, atomic replace, create, rename and
  delete.
