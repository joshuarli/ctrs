# Optional service setup for ctrs

ctrs is a foreground process. The engine does not need launchd, systemd, or
any system-wide installation: you run `ctrs daemon`, it serves the Docker
Engine API on a Unix socket, and you stop it with SIGTERM (it exits in
well under 10 seconds and stops the VM and guest agent cleanly).

The daemon never creates a docker context and never edits
`/var/run/docker.sock` or any global docker configuration. To point the
docker CLI at it, set `DOCKER_HOST`:

```sh
export DOCKER_HOST=unix://$HOME/.ctrs/run/docker.sock
docker run --rm alpine echo hello
```

## The lifecycle commands

```sh
ctrs engine start     # spawn the daemon detached; returns once the API answers (idempotent)
ctrs engine status    # pid, rss, uptime, socket (--json for scripts); exit 1 when not running
ctrs engine stop      # the engine itself exits (same teardown as SIGTERM); falls back to a verified pidfile signal
ctrs engine restart   # stop then start
ctrs status           # shorthand for ctrs engine status
```

`ctrs engine start` is what `ctrs daemon` plus a supervisor is, without
one: the child runs in its own process group with stdio detached and logs
to `~/.local/share/ctrs/logs/daemon.log`. Stop it with `ctrs engine stop`. The
containers keep `ctrs start|stop|restart CONTAINER` (as docker has them);
the bare forms name a container to act on, or print an error pointing here.

## Foreground (the default)

```sh
ctrs daemon
```

Data goes to `~/.local/share/ctrs/data` (override with `CTRS_DATA_DIR`), the socket to
`~/.local/share/ctrs/run/docker.sock` (override with `CTRS_SOCKET`). Both follow `HOME`.
Logs go to `~/.local/share/ctrs/logs/`. Stop it with Ctrl-C or `kill <pid>` (SIGTERM).

## macOS: a launchd user agent (optional)

This makes the engine start at login and restart if it dies. It is a user
agent (`~/Library/LaunchAgents`), not a system daemon: no root, no
`/Library/LaunchDaemons`, nothing installed system-wide. It is entirely
optional; delete the plist to undo.

`~/Library/LaunchAgents/dev.ctrs.engine.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.ctrs.engine</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.local/bin/ctrs</string>
    <string>daemon</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>/Users/YOU/.ctrs/daemon.launchd.log</string>
  <key>StandardErrorPath</key><string>/Users/YOU/.ctrs/daemon.launchd.log</string>
</dict>
</plist>
```

```sh
cp dev.ctrs.engine.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.ctrs.engine.plist
launchctl bootout gui/$(id -u)/dev.ctrs.engine   # to undo
```

Replace `/Users/YOU/.local/bin/ctrs` with the actual path of the ad-hoc
signed binary (e.g. `target/release/ctrs` or a copied location). The binary
needs the virtualization entitlement: use `cargo xtask host` to build one.

## Linux: foreground, or your init system (optional)

The engine needs root on Linux (namespaces, cgroups v2):

```sh
sudo ctrs daemon
```

If you want it supervised, write your own unit — for example a systemd
service — but ctrs does not require systemd and ships no unit file. A
minimal example is at the bottom of this file; it is an example, not an
installation. Hand the `ExecStart` your binary path:

```ini
[Unit]
Description=ctrs container engine
After=network.target

[Service]
ExecStart=/usr/local/bin/ctrs daemon
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Installing it (`systemctl enable --now ctrs`) is your choice; ctrs never
installs it. On hosts without systemd, run the daemon from any process
supervisor, or from a terminal/tmux.

The socket is `0600`, root-only, unless `CTRS_SOCKET_GROUP=<group>` is set
(for example `CTRS_SOCKET_GROUP=docker`, which behaves like the docker
group does for dockerd). The data root is `0700`. Nothing in `/var/lib` is
created.
