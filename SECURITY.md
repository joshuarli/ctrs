# Security

ctrs runs a virtual machine, containers that can be privileged, and a Linux
guest agent (`kiri-init`) that runs as root, so security reports matter a lot.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability
reporting on this repository (Security → Report a vulnerability).

Include what you found, how to reproduce it, and the ctrs version. You should
get a reply within a few days, and a fix or a plan once the issue is confirmed.
Reporters are credited in the release notes unless they prefer not to be.

## Supported versions

ctrs is pre-release software. Security fixes land on `main`.

## In scope

- Escaping a container or the VM to the host (the Mac, or the Linux machine).
- The daemon socket (`KIRI_SOCKET`), the Docker Engine API it serves, and the
  guest→Mac DNS relay.
- The Linux guest agent (`kiri-init`): namespaces, cgroups, seccomp, mounts,
  and every frame it accepts from the host.
- BuildKit builder provisioning (`docker buildx` integration).

## Out of scope

- Findings that require a deliberately modified or unsigned build.
- `--privileged` containers acting within the documented host boundary, which
  excludes the host socket and io_uring by design (see `docs/features.md`).
