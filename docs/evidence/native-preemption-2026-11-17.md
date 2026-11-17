# Full-preemption W2 experiment

Full preemption is rejected. Job6420555463de43168c2f8f733b5540cb under
`.work/tmp/w2-preempt-cpu-20261117/` exits0 with clean teardown. All100 frozen
receipts pass before later edits. Six alternating voluntary/full pairs each
complete5000 exact C4 API operations after200 read-only priming operations.
All60,000 measured operations, application counters and owned cleanup pass.
The host is fda62467, initrd6ae4d3ab, resident17CPU/45091MiB. Only the kernel
preemption policy changes. No active uprobes run during these comparisons.

Private source631d704 changes PREEMPT_VOLUNTARY to PREEMPT. Parent reviewed the
forced Kconfig changes, exact compiler and generated config. The6CPU/6GiB build
exits0 in149s without OOM. Its Image is18,870,280B, only2048B above the diagnostic
voluntary kernel, within the3% size budget. Image SHA-256:
`651873d07a8e6d9542f5b92852c60aef7d9e68b64f4faa9b34575977b4fe86f4`.
Config SHA-256:
`02914e7e62009fe759369c98df314a180c870403274904ec989f01faebc12dae`.
Artifacts remain in `.work/wt/np-preempt-full/.work/kernel-preempt-full/`.
Main kernel assets are unchanged.

| Pair | Full/voluntary API CPU | Engine CPU | Work duration | p99 |
| --- | ---: | ---: | ---: | ---: |
|1|1.0675|1.0710|1.0580|1.0095|
|2|0.9687|0.9444|0.9614|0.8697|
|3|0.9695|0.9775|0.9674|0.9718|
|4|1.1122|1.1407|1.0901|1.1601|
|5|1.0547|1.0415|1.0354|1.0098|
|6|0.9201|0.9000|0.9059|0.7849|

No pair meets the required10% API CPU reduction. The declared screen requires
all six, plus5% engine reduction and at most3% wall, tail and footprint growth.
`analysis.json` records `advance=false`. Sampled native peaks span1.545–1.606GB;
some pairwise memory guards also fail. Host activity prevents qualified timing
or regression claims. Do not expand this rejected candidate to more workloads.
The branch and assets remain private for provenance.
