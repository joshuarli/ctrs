.PHONY: test test-rust test-bench lint

# CI and local verification share this entry point; the Linux-only unit tests
# of ctrs-init run in the linux-musl CI job (the same cargo command in a builder image).
test: test-rust test-bench

test-rust:
	cargo test --workspace --lib --tests --no-fail-fast

# Offline benchmark harness: manifest contract and Python unit tests.
test-bench:
	python3 bench/native/runner.py validate-manifest
	python3 -m unittest discover -s bench/native -p 'test_*.py' -v

lint:
	cargo clippy --workspace --all-targets -- -D warnings
