# W4 v2 fixture

Build this directory as one image; all roles use the same image and code. Run a
fresh Redis 7 instance (persistence disabled) on a private trial network, then
run `serve --redis-host <redis-name>` on that network. Wait for HTTP GET
`/health`, then run `submit --url http://<app-name>:8080` to POST all 200
pinned job IDs. Submission must finish successfully before starting 1, 4, or
16 separate `worker --redis-host <redis-name>` containers concurrently. Wait
for all worker exits and require each exit status to be zero. Finally run
`verify --redis-host <redis-name>` and require exit status zero and
`verified 200`. Start each worker-count trial with an empty Redis database;
never submit and drain concurrently, since workers exit when the queue is empty.
The runner owns timeouts, network/container cleanup and measurement boundaries.

Each job derives its input from its ID and performs 256 chained SHA-256 rounds.
The result list contains full canonical content artifacts. Verification compares
the complete multiset of artifact bytes and checks the queue is empty, detecting
missing, duplicate, extra and corrupted results. It must run after all workers
have exited; a worker crash after dequeue leaves a missing artifact. HTTP 202
means Redis accepted the enqueue, not that work has completed. Retries after an
ambiguous HTTP failure can duplicate work and consequently fail verification.
