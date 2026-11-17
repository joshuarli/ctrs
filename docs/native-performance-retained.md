# Retained native performance work

This inventory records the owner-requested winddown on 2026-11-16.
The campaign resumed later the same day. Original winddown lanes are terminal;
the storage repair lane is also terminal and integrated. Checkouts preserve source or
qualification evidence. The current campaign status and next action live in
[native-performance-progress.md](native-performance-progress.md).

## Parked work

| Branch | Revision | Cause and retry condition |
| --- | --- | --- |
| `campaign/np-storage-space` | `538e2c3` | Restored on resumed main as 3a87d61 with repair 97a6a69. Revised native allocation and relation-ENOSPC proofs pass; retain original failed/narrower evidence separately. |
| `campaign/np-space-fix` | `34a0c39` | Integrated as 97a6a69 after parent review, six focused tests, full harness suite and both native storage stages. Retained checkout `np-space-fix` preserves repair provenance. |
| `campaign/np-w8-content` | `bc6625f` | Reviewed and integrated as 00ac842. Real four-image generation reproduces 37 layer identities. Native full-transfer/marker proofs pass; sub-API guest cache absence and scored qualification remain open. |
| `campaign/np-full-sync` | `f536b6e` | Full synchronization candidate remains unpromoted. Complete resource and performance confirmations in an exclusive window. |
| `campaign/np-refusal-ttl` | `54c6a00` | Recovery candidate remains parked. Re-establish the v2 exclusive baseline and preserve the failed prior confirmation. |
| `campaign/np-sched-mc` | `1bea138` | Rejected scheduler configuration snapshot. Do not deploy it. Reconsider only with a new causal profile. |

Storage proof `space-32241aef` lives under `.work/tmp/`. Its finite supervisor
receipt is `.work/tmp/space-source-20261116T0935/`, job
`570bdc7ba990456e94b3c7b25b652099`, exited 0. Both variants preserve the exact
100-record prefix and accept 10 more records after relation SQLSTATE 53100.
The reported zero host allocation growth compares endpoints. It is not a peak
bound. Root-reserved blocks, host-full storage, power loss and exclusive reclaim
remain untested. Failed `space-0691f55a` and temporary-spill-only `space-e9a6bb14`
are retained separately. The review is terminal session
`usrw_34112a16-8e65-4b9d-953d-8b88183d95eb`.

## Retained checkouts

Paths below are relative to `.work/wt/`. Their current consumers are the named
qualification or source-review tasks. Native artifacts retain their original
paths. No ignored fixture or build data was discarded during winddown.

| Checkout | Branch | Current consumer |
| --- | --- | --- |
| `np-disk-expand` | `campaign/np-disk-expand` | Expansion source and guest assets for later qualification provenance. |
| `np-disk-review` | `review/np-disk-expand` | Original expansion review receipts and patch comparison. |
| `np-durable-job` | `campaign/np-durable-job` | Original supervisor source and lifecycle proof provenance. |
| `np-durable-review` | `review/np-durable-job` | Retirement refused because the head is not integrated. Preserve for patch review. |
| `np-flush-audit` | `review/np-flush-path` | Flush-path audit inputs for remaining storage guarantees. |
| `np-full-sync` | `campaign/np-full-sync` | Parked Full synchronization source for candidate confirmation. |
| `np-image-diffids` | `fix/image-inspect-diffids` | Native image deployment proof and release provenance. |
| `np-resource-cells` | `campaign/np-resource-cells` | Original resource prototype snapshot `b486f06`; compare before retirement. |
| `np-sched-mc` | `campaign/np-sched-mc` | Rejected kernel configuration and retained guest assets. |
| `np-w10-cache-trace` | `campaign/np-w10-cache-trace` | Recovery trace prototype snapshot `942bba3` and binary provenance. |
| `np-w11-deadline` | `campaign/np-w11-deadline` | Raw final W11 normal and cancellation proofs referenced by progress. |
| `np-w11-v2` | `campaign/np-w11-v2` | Original mixed fixture snapshot `9052439` and native evidence. |
| `np-w4` | `campaign/np-w4` | Original queue fixture snapshot `45dca6d`; compare with accepted source. |
| `np-w5` | `campaign/np-w5` | Original watch fixture snapshot `14d3427` and source provenance. |
| `np-w8-content` | `campaign/np-w8-content` | Parent review and real artifact proof for the parked W8 slice. |
| `np-w8-v2` | `campaign/np-w8-v2` | Common portfolio native evidence and reproduction artifacts. |
| `np-w9-v2` | `campaign/np-w9-v2` | Fixed build-job fixture evidence and source provenance. |

Completed checkouts `np-cpu-review`, `np-space-review`, `np-w11-fix-review` and
`np-w11-review` were retired after integration or preservation of their source.
Branches `campaign/np-w11-fix-review` and `campaign/np-w11-review` remain as
patch-equivalent provenance. Their checkouts contained no ignored evidence.

Pre-existing branches `chore/ctrs-proto-target-gate`, `cleanup/mount-guard` and
`repomod/fix/f844dfc9dd284537af0a958ad9dfadf1` remain unchanged outside this winddown.
