# W10 persistent probe protocol

`w10-client-v2-persistent` gives each health/read worker one HTTPConnection with
a 200ms timeout. A call makes exactly one HTTP attempt, consumes and validates the
whole response, and closes the connection on failure. The next scheduled call
may reconnect; there is no hidden retry. Normal responses reuse the connection.
Every attempt includes native errno, timing, connect attempts, connections opened
and whether a socket was reused. HTTP 200 with wrong payload is a failed request.

The diagnostic retains the 2ms health schedule, configured read schedule and 100Hz
TCP reachability probe. TCP acceptance alone does not establish guest readiness.
A fresh TCP probe is intentionally separate from persistent HTTP application work.
At most 32 readers plus one health worker and one TCP worker run. Pairs are finite
(1..10), socket waits bounded, and recovery polling has a 30s deadline. Driver
commands have individual 120s timeouts; this is not a 120s total execution deadline.
Shared termination handling performs owned cleanup before original signal death.

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/recovery_pilot.py \
  --ctrs-binary .work/tmp/w10-target/release/ctrs
```

Before a scored comparison, save gate/process/power/thermal conditions and certify
exclusivity. Successful gate exit alone is insufficient. This diagnostic still
marks performance unqualified and checks the actual loaded daemon hash against
the requested binary. Keep command cost in restart-to-correct-response intervals,
expected outage errors separate, and exact precommitted records intact.

Old fresh-connection traces remain v1 diagnostics, including the failed 149-error
stress run. Do not pool versions or reinterpret it as a product failure or a
passed comparison. v2 baseline functional proof must precede any resumed TTL
candidate comparison; the 250ms product default is unchanged.
