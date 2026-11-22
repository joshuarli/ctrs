# Connection lifecycle fixture

The host runs concurrent clients against the pinned API image through a loopback published port. Newline-delimited JSON responses contain deterministic request and chunk identities and are checked exactly. Each mode and its parameters define a separate cohort. Streaming lateness is measured against the client send schedule, so includes transport and server scheduling. Cancellation closes after one chunk; cleanup latency runs from completion of all client workers until the server reports zero open sessions. Restart timing and retries both start immediately before the restart command. A reconnect counts only when a response comes from a new server instance (each server tags responses with its own instance id) within 60 seconds. Errors and old-instance answers inside that window are reported as `restart_window_errors` and do not fail correctness; a missed deadline or failed restart does. Idle durations above 300 seconds expose the host relay's socket timeout.

Fresh mode opens clients × operations loopback connections per trial, and each closed one holds a Mac ephemeral port in TIME_WAIT for 2 × MSL (30 s on macOS, 16,384 ports). Before a fresh trial the runner waits, up to 45 seconds, until twice that many ports are free (the range minus `net.inet.tcp.pcbcount`, which counts TIME_WAIT and both loopback ends, so it errs toward waiting), and records the wait as `client_port_wait_seconds`. An `EADDRNOTAVAIL` connect counts as `client_ports`, a client-side limit, and still fails correctness. `w14-v1` fresh cohorts ran into this limit on both engines; never pool them with `w14-v2`.

The `w14-v4-buffered-frames` fixture keeps one buffered reader per
connection and caps each frame at 64 KiB. Writes flush each frame to
preserve the application schedule. The paired receipt includes the
protocol source hash. Compare this revision in a fresh cohort.
