Prefix: CTRS
Next: 11
### CTRS-1 · P3 · Image-adjacent state files are written with the process umask, not 0600

- **Area:** daemon
- **Where:** crates/ctrs/src/daemon/engine.rs:1011, crates/ctrs/src/daemon/volumes.rs:56, crates/ctrs/src/daemon/network.rs:575, crates/ctrs/src/daemon/builder.rs:447, crates/ctrs/src/daemon/proxy.rs:42
- **Problem:** save() writes the tmp file with default permissions and renames it over containers.json/volumes.json/network.json/proxy.json; containers.json Spec.env routinely carries API tokens, so a 0644 file inside the 0700 root depends on the umask to stay private. Docker keeps these 0600.
- **Recommendation:** Create the tmp files with mode 0o600 before rename, as config.rs and the pidfile path already do.
- **Fix with:** OpenOptions::new().mode(0o600) in the five save paths
- **Effort:** S


### CTRS-2 · P3 · HTTP handler panic unwinds the connection thread without a 5xx

- **Area:** daemon
- **Where:** crates/ctrs/src/daemon/api.rs:25-60 (serve loop); no catch_unwind in src/
- **Problem:** A panic in any handler (e.g. an expect on attacker-influenced JSON) unwinds the connection thread; the docker client sees a dropped connection with no error body and the thread dies with no log line. Engine survives (thread-per-connection, locks poison-tolerant) but the request and its error are lost silently.
- **Recommendation:** Wrap the route dispatch in catch_unwind and answer 500 on panic, or document the unwind contract explicitly.
- **Fix with:** catch_unwind(AssertUnwindSafe(...)) around route in serve + a 500 reply mapping
- **Effort:** S


### CTRS-6 · P3 · Image index rename without fsync can lose or tear images.json

- **Area:** image
- **Where:** crates/ctrs-image/src/store.rs:261 (fs::write tmp + fs::rename, no sync_all or dir sync) vs layers.rs:82 (sync_fs)
- **Problem:** A crash between rename and flush can leave images.json zero-length; the whole index then fails with InvalidData and is unreadable until repaired, taking every image record down with it (blobs are safe).
- **Recommendation:** sync the temp file before rename and the directory after, mirroring the layers install path.
- **Fix with:** File::create + sync_all + rename + dir sync in write_index
- **Effort:** S


### CTRS-3 · P4 · Corrupt volumes.json is silently replaced with an empty list

- **Area:** daemon
- **Where:** crates/ctrs/src/daemon/volumes.rs:47 (serde_json::from_slice(&b).unwrap_or_default()) vs engine.rs:889-894 which logs
- **Problem:** A corrupt volumes.json is replaced with an empty list with no log line; anonymous volumes disappear from tracking while their data dirs remain, so --rm/rm -v never cleans them.
- **Recommendation:** Log the parse failure like the containers path before defaulting.
- **Fix with:** match on the parse result; diag::error! with the cause; then default
- **Effort:** S


### CTRS-4 · P4 · restart_count persists and is never reset, holding throttled containers at the cap

- **Area:** daemon
- **Where:** crates/ctrs/src/daemon/engine.rs (restart_count in Saved; cap 1 << min(restart_count,10))
- **Problem:** restart_count is persisted across daemon restarts and never resets after a successful run, so a container that flaky-failed 10 times is permanently at the 60s backoff cap; Docker resets the counter on start. Behavior is undocumented.
- **Recommendation:** Reset restart_count on the start_inner success path, or document the persistent-counter semantics.
- **Fix with:** reset in the success path; add the semantics to docs/architecture.md
- **Effort:** S


### CTRS-5 · P4 · Image ingest caps a blob at 64 GiB but has no total-archive budget

- **Area:** image
- **Where:** crates/ctrs-image/src/archive.rs (MAX_BLOB 64 GiB since S7; manifest.json still MAX_JSON 4 MiB)
- **Problem:** A crafted docker-load archive can still fill the disk with arbitrarily many sub-cap blobs; a per-blob cap bounds single-file damage only.
- **Recommendation:** Add a running total cap across one load() invocation (size TBD by the owner; 64-256 GiB) or refuse on the aggregate of manifest-declared layer sizes.
- **Fix with:** a total budget accumulator in load(), mirroring MAX_BLOB; fails closed on overflow
- **Effort:** S


### CTRS-7 · P4 · docker cp unpack has no expansion cap or whiteout translation

- **Area:** guest
- **Where:** crates/ctrs-init/src/linux/copy.rs:130-150 (copy_in unpacks straight with unpack_in; no limit) vs layers.rs Capped pattern
- **Problem:** An archive unpacked via docker cp into the container path is uncapped on expanded size; unlike the guest layer path, nothing bounds it. Host is the sender (trusted), so impact is a buggy or compromised host, not a hostile image.
- **Recommendation:** Reuse the layers.rs Capped pattern if the host threat model ever weakens; noted for parity.
- **Fix with:** Capped wrapper with an expansion cap in copy_in
- **Effort:** S


### CTRS-8 · P4 · copy_in pre-check is TOCTOU and path-unaware

- **Area:** guest
- **Where:** crates/ctrs-init/src/linux/copy.rs:138-149 (symlink_metadata(dest.join(entry.path()?)) before unpack_in)
- **Problem:** entry.path() may contain '..' or absolute components at check time (unpack_in rejects them later), so the metadata check can stat a path outside dest, and a swap between check and unpack is unguarded. Safety rests on unpack_in; this yields wrong errors/decisions, not escapes.
- **Recommendation:** Normalize/validate the entry path before the pre-check, or drop the pre-check and rely on unpack_in.
- **Fix with:** reuse unpack_in's path validation for the metadata check, or remove the check
- **Effort:** S


### CTRS-9 · P4 · conformance/failure.sh S9 publishes a fixed host port

- **Area:** conformance
- **Where:** conformance/failure.sh:262-264 (-p 127.0.0.1:18081:80)
- **Problem:** Two concurrent failure.sh runs collide on 18081, and a host process already bound to it makes the negative assertion pass for the wrong reason (false pass).
- **Recommendation:** Allocate an ephemeral port from a free-port probe like iso_alloc_ports before S9.
- **Fix with:** free-port bind test before S9; pass it into the publish flag
- **Effort:** S


### CTRS-10 · P4 · iso_alloc_ports has a check-then-use race

- **Area:** tests
- **Where:** tests/lib/isolated-env.sh:71-91
- **Problem:** A probed-free port is handed out with no reservation between probe and use; a concurrent process can grab it first. Acceptable for a serial harness but undocumented.
- **Recommendation:** Document the acceptance for serial runs or bind-and-hold a reservation socket.
- **Fix with:** document in the header, or hold the probe socket until handoff
- **Effort:** S

