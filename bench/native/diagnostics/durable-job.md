# Launch a finite local benchmark job

This native ARM64 macOS supervisor runs one local argv command after its launcher
exits. Complete the caller's frozen-candidate readiness checks before launching
qualification. This component does not validate those gates or launch engines.

From a repository worktree, create an input receipt outside the new job directory:

```sh
python3.14 bench/native/durable_job.py receipt /absolute/executable /absolute/input > /absolute/receipts.json
python3.14 bench/native/durable_job.py launch \
  --job /absolute/repo/.work/tmp/new-job \
  --deadline-epoch 2000000000 --inputs /absolute/receipts.json \
  -- /absolute/executable argument
```

Choose a finite future Unix deadline. Include the executable and every relevant
script, configuration and input in the receipt. The launcher and supervisor check
resolved file identities and SHA-256 before execution. Supervisor/interpreter
receipts are added automatically. Conflicting frozen receipts fail. The executable
path is canonicalized; other inputs must stay immutable. Checking does not lock
files or eliminate a check-to-exec race. The command inherits the launcher's
environment and saved working directory. No shell is invoked.

The job directory must be new, inside an existing directory under the shared
repository `.work`. It is created exclusively with mode 0700. `spec.json` records
job ID, argv, inputs, launch clocks and fixed wall/monotonic deadlines. An exclusive
fsynced claim prevents a second supervisor from executing or publishing status.
This is at-most-once execution; missing status is indeterminate and must not cause
an automatic retry. The claim is never removed for reuse.

`running.json` records historical native PID/start identities. It does not prove
those processes remain live. Nothing adopts or signals a PID from these files.
`stdout` and `stderr` retain child output. Atomic, fsynced `status.json` records
`exited`, `deadline`, `interrupted` or `error`, actual child exit code/signal,
cleanup result and finish time. Version 1 readers reject another version and
ignore additional fields. Null exit fields mean no child exit was observed;
a very short completed child can lack a live identity snapshot.

The first wall or monotonic deadline initiates cleanup. TERM, HUP, INT and QUIT
also initiate cleanup; after recording, the supervisor re-raises the original
signal. The child starts in its own process group. Deadline/interruption sends
TERM, grants up to 0.5 seconds, then sends KILL. Normal leader exit also removes
remaining group members. Group quiescence and child wait have a five-second
budget, with individual process-list calls bounded at two seconds. Incomplete
cleanup remains explicit and prevents acceptance. Descendants that leave the
owned group can escape this boundary; benchmark commands must not do that.

Forced supervisor death, host power loss, interpreter failure or filesystem errors
can prevent terminal recording. No launchd service, restart loop or recovery
adoption is installed. Signal the supervisor only after independently checking
its current kernel start identity. Full 12-hour W11 integration and qualification
remain separate work; short child tests do not close those gates.
