.PHONY: test test-rust test-bench lint

# CI and local verification share this entry point; the Linux-only unit tests
# of ctrs-init run in the linux-musl CI job (the same cargo command in a builder image).
test: test-rust test-bench

test-rust:
	cargo test --workspace --lib --tests --no-fail-fast

# Offline benchmark harness: manifest contract and Python unit tests.
# Durable-job tests require their scratch directories under the repository's .work.
test-bench: export TMPDIR := $(CURDIR)/.work/tmp
test-bench:
	mkdir -p $(TMPDIR)
	python3 bench/native/runner.py validate-manifest
	python3 -m unittest discover -s bench/native -p 'test_*.py' -v

lint:
	cargo clippy --workspace --all-targets -- -D warnings

.PHONY: clean
clean:
	@if test -L ./target || { test -e ./target && ! test -d ./target; }; then \
	  printf '%s\n' 'make clean: ./target must be a local build directory' >&2; exit 1; \
	fi
	rm -rf -- ./target
