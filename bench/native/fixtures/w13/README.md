# W13 verified artifact transfer

The sender creates deterministic bytes before timing. Each 1 MiB block is SHAKE-256 of UTF-8 `w13-v1-seed-2026:<block index>`, truncated for the last block. A transfer's total bytes are divided evenly among its streams; each stream uses the same generated file. The default is 1 GiB total. The sender reads a host local disk file or a container tmpfs file; every location prepares the same file and the driver checks that their SHA-256 digests agree. The receiver compares each received block byte for byte with its local copy and stores nothing. The host Python on this campaign host is an OpenSSL-free build whose software SHA-256 runs near 320 MiB/s, below the transfer rates being measured, so v1's receiver-side hashing limited host-side receivers. v2 (byte comparison) results never pool with v1.

Each TCP connection begins with a newline-terminated JSON request containing the stream id. The sender responds with a newline-terminated JSON header containing `id`, `bytes`, and `sha256`, followed by exactly that many raw bytes and EOF. The receiver verifies the header and compares every byte with its prepared reference. Upload receivers acknowledge their verification. Client completion includes that acknowledgement. Times use a monotonic clock. Stalls are receive-progress gaps of at least one second. Host and single-container loopback controls use the same program, size, direction and stream count. A result above half the slower control is marked tool-limited. Controlled egress is unsupported because there is no owned external endpoint.

The proof driver uses 256 MiB and one attempt per condition, for functional validation only. It loads an OrbStack-saved image into the isolated ctrs root; the loaded platform image ID is recorded separately from the OrbStack image index ID. It never changes a Docker context.

Measure native host loopback capacity before rerunning engine paths:

```sh
TMPDIR="$PWD/.work/tmp" python3 bench/native/diagnostics/w13_host_headroom.py > "$results_jsonl"
```

The default runs five byte-exact 1 GiB attempts in each upload and download
condition at one and four streams. It records the exact tool hash and every
receiver result. The host must reach twice the engine goodput for the same
direction and stream count before considering a host-spanning throughput
verdict. A separate container loopback control must establish guest-side
headroom, and each measured engine trial keeps the existing tool-limit check.
