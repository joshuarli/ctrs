#!/bin/sh
set -eu
export LC_ALL=C DEBIAN_FRONTEND=noninteractive

test "$(dpkg --print-architecture)" = arm64
libc_version=$(dpkg-query --showformat='${Version}' --show libc6)
sources=/tmp/w2-snapshot.list
cat > "$sources" <<'SOURCES'
deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://snapshot.debian.org/archive/debian/20261115T210008Z/ trixie main
deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://snapshot.debian.org/archive/debian-security/20261113T212035Z/ trixie-security main
SOURCES
set -- -o "Dir::Etc::sourcelist=$sources" -o Dir::Etc::sourceparts=-
apt-get "$@" update
apt-get "$@" install -y --no-install-recommends linux-perf=6.12.117-1 "libc6=$libc_version"
test "$(dpkg-query --showformat='${Version}' --show libc6)" = "$libc_version"
test "$(dpkg-query --showformat='${Version}' --show linux-perf)" = 6.12.117-1

mkdir -p /payload/lib/aarch64-linux-gnu /payload/usr/bin /out
install -m 755 /usr/bin/perf /payload/usr/bin/perf
ldd /usr/bin/perf > /tmp/w2-perf-ldd
if awk '/=> not found/ {missing = 1} END {exit !missing}' /tmp/w2-perf-ldd; then
    cat /tmp/w2-perf-ldd >&2
    exit 1
fi
awk '$2 == "=>" && $3 ~ /^\// { print $3 }' /tmp/w2-perf-ldd > /tmp/w2-perf-libs
test -s /tmp/w2-perf-libs
while IFS= read -r library; do
    install -m 644 "$library" "/payload/lib/aarch64-linux-gnu/${library##*/}"
done < /tmp/w2-perf-libs
LD_LIBRARY_PATH=/payload/lib/aarch64-linux-gnu /payload/usr/bin/perf version > /out/perf-version.txt
dpkg-query --showformat='${Package}	${Version}\n' --show > /out/packages.tsv
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    -C /payload -cf /tmp/native-tools.tar lib usr
gzip -n -c /tmp/native-tools.tar > /out/native-tools.tar.gz
