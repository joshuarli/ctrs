# W4 event-batch fixture

Build this directory as one image; all roles use the same image and code. Start a
fresh Redis 7 instance with persistence disabled on a private trial network, and
create an empty named output volume for each trial. Run `serve --redis-host
<redis-name>` on the network and wait for HTTP GET `/health` to return 200;
readiness includes a Redis PING. Run `submit --url http://<app-name>:8080` to
POST 200 deterministic batches of 64 service events. Each event contains a UTC
timestamp, HTTP status, route, latency in milliseconds, and tenant. Submission
must finish successfully before starting 1, 4, or 16 concurrent worker
containers. Mount the same output volume in every worker and pass `worker
--redis-host <redis-name> --output-dir /output`. Wait for all workers and
require every exit status to be zero.

Run `verify --redis-host <redis-name> --output-dir /output` with the same volume
mounted and require exit status zero and `verified 200`. Each job creates
`job-NNNN.ndjson.gz` containing its complete event batch and
`job-NNNN.summary.json` containing event, status, route and tenant counts and
latency totals and maximum. Gzip headers use mtime zero. Verification checks the
empty queue and exact file names and bytes for all 200 jobs, including summaries;
missing, corrupted, or extra files fail verification. Workers create files
exclusively, so a duplicate delivery fails visibly without overwriting output;
the runner must check worker exit statuses. A crash after dequeue also leaves
missing or incomplete output. HTTP 202 means Redis accepted the enqueue, not
that processing completed. Do not retry ambiguous submissions without treating
duplicate delivery as a failed trial.

Use a fresh Redis database and empty output volume for every worker-count trial.
Do not submit and drain concurrently: workers exit when the queue is empty. The
runner owns timeouts, container and volume cleanup, and measurement boundaries.
