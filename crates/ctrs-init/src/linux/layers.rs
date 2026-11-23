//! The guest's layer store: compressed layer blobs arrive from the host over
//! vsock and are unpacked once into `layers/<hex>/`, ready to be stacked by
//! overlayfs. A layer directory only appears, by rename, once it is complete,
//! and is only used once `<hex>.done` beside it says its files are on disk:
//! a VM that stops before the guest flushes can keep a layer's names but
//! lose its contents, leaving every file empty.

use std::fs;
use std::io::{self, BufReader, Read};
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::time::Instant;

use ctrs_proto::LayerBegin;
#[cfg(test)]
use ctrs_proto::LayerStored;

use super::sys;

pub fn hex(digest: &str) -> io::Result<&str> {
    let h = digest.strip_prefix("sha256:").unwrap_or(digest);
    if h.len() != 64 || !h.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, format!("bad layer digest {digest}")));
    }
    Ok(h)
}

pub fn dir(root: &Path, digest: &str) -> io::Result<PathBuf> {
    Ok(root.join(hex(digest)?))
}

fn marker(root: &Path, digest: &str) -> io::Result<PathBuf> {
    Ok(root.join(format!("{}.done", hex(digest)?)))
}

pub fn present(root: &Path, digest: &str) -> bool {
    dir(root, digest).is_ok_and(|d| d.is_dir()) && marker(root, digest).is_ok_and(|m| m.is_file())
}

/// Reads exactly `begin.size` bytes of blob from `stream` and unpacks them.
/// The stream stays in sync even if unpacking fails part-way. Synchronous
/// reference path kept for tests; the agent stages then installs in a
/// forked child instead.
#[cfg(test)]
pub fn receive(stream: &mut impl Read, begin: &LayerBegin<'_>, root: &Path) -> io::Result<LayerStored> {
    let started = Instant::now();
    let blob = stage_blob(stream, begin, root, 0)?;
    let result = install_blob(root, begin.digest, begin.media_type, begin.size, &blob);
    let _ = fs::remove_file(&blob);
    result.map(|unpacked_bytes| LayerStored { unpacked_bytes, elapsed_ns: started.elapsed().as_nanos() as u64 })
}

/// A layer install handed to a forked child: the compressed blob is already
/// staged beside the layer store; the child unpacks and installs it off the
/// event loop. `seq` makes the staging name unique so two queued jobs for
/// the same digest cannot overwrite each other's blob.
pub struct InstallJob {
    pub seq: u64,
    pub digest: String,
    pub media_type: String,
    pub size: u64,
    pub blob: PathBuf,
    pub started: Instant,
}

/// What the agent reports back for one finished [`InstallJob`]; the
/// agent keys it by the job's `seq`, so the record does not repeat it.
pub struct InstallDone {
    pub digest: String,
    pub started: Instant,
    pub result: io::Result<u64>,
}

fn blob_tmp(root: &Path, digest: &str, seq: u64) -> io::Result<PathBuf> {
    Ok(root.join(format!(".blob-{seq}-{}", hex(digest)?)))
}

/// Reads exactly `begin.size` blob bytes from `stream` into a staging file
/// in the layer store. The stream stays in sync even on error: whatever
/// was not written is drained, so the next frame still lines up.
pub fn stage_blob(stream: &mut impl Read, begin: &LayerBegin<'_>, root: &Path, seq: u64) -> io::Result<PathBuf> {
    let blob = blob_tmp(root, begin.digest, seq)?;
    let _ = fs::remove_file(&blob);
    let result = (|| -> io::Result<()> {
        let mut file = fs::File::create(&blob)?;
        let mut limited = stream.take(begin.size);
        io::copy(&mut limited, &mut file)?;
        io::copy(&mut limited, &mut io::sink())?;
        if file.metadata()?.len() != begin.size {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "layer blob shrank in transit"));
        }
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&blob);
    }
    result.map(|()| blob)
}

/// Unpacks a staged blob and installs it: the worker half of the receive
/// path. Returns the unpacked byte count.
pub fn install_blob(root: &Path, digest: &str, media_type: &str, size: u64, blob: &Path) -> io::Result<u64> {
    let tmp = root.join(format!(".tmp-{}", hex(digest)?));
    let _ = fs::remove_dir_all(&tmp);
    fs::create_dir_all(&tmp)?;
    let result = (|| -> io::Result<u64> {
        let file = fs::File::open(blob)?;
        unpack(&mut file.take(size), media_type, &tmp, size)
    })();
    match result.and_then(|unpacked| install(root, digest, &tmp, &dir(root, digest)?).map(|()| unpacked)) {
        Ok(unpacked) => Ok(unpacked),
        Err(e) => {
            let _ = fs::remove_dir_all(&tmp);
            Err(e)
        }
    }
}

/// The forked child's half of a staged install: unpack, install, drop the
/// staging file. Runs in a copy of the single-threaded agent, like the
/// `docker cp` children.
pub fn finish_job(root: &Path, job: &InstallJob) -> io::Result<u64> {
    let result = install_blob(root, &job.digest, &job.media_type, job.size, &job.blob);
    let _ = fs::remove_file(&job.blob);
    result
}

/// Puts an unpacked layer in place: its files reach the disk first, then
/// the directory is renamed in, then the marker says it is whole.
fn install(root: &Path, digest: &str, tmp: &Path, final_dir: &Path) -> io::Result<()> {
    if present(root, digest) {
        let _ = fs::remove_dir_all(tmp);
        return Ok(());
    }
    sync_fs(tmp)?;
    if final_dir.exists() {
        // A copy without a marker was cut short and may hold empty files.
        // Moved aside rather than deleted here, which can take a while;
        // the next RetainLayers clears it.
        let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_nanos());
        fs::rename(final_dir, root.join(format!(".stale-{}-{nanos}", hex(digest)?)))?;
    }
    fs::rename(tmp, final_dir)?;
    fs::File::create(marker(root, digest)?)?.sync_all()?;
    fs::File::open(root)?.sync_all()
}

/// Flushes the filesystem holding `path` to disk.
fn sync_fs(path: &Path) -> io::Result<()> {
    let f = fs::File::open(path)?;
    // SAFETY: a valid descriptor that outlives the call.
    sys::check(unsafe { libc::syncfs(std::os::fd::AsRawFd::as_raw_fd(&f)) } as _, "syncfs")?;
    Ok(())
}

/// Deletes every layer not in `keep` (blob digests), every layer without
/// its marker, and whatever an unpack left half-done. Anything that isn't
/// one of those names is left alone.
pub fn retain<'a>(root: &Path, keep: impl Iterator<Item = &'a str>) {
    let keep: std::collections::HashSet<&str> = keep.filter_map(|d| hex(d).ok()).collect();
    let Ok(entries) = fs::read_dir(root) else { return };
    for entry in entries.flatten() {
        let name = entry.file_name();
        let Some(name) = name.to_str() else { continue };
        let leftover = name.starts_with(".tmp-") || name.starts_with(".stale-") || name.starts_with(".blob-");
        let (h, is_marker) = match name.strip_suffix(".done") {
            Some(h) => (h, true),
            None => (name, false),
        };
        let layer = h.len() == 64 && h.bytes().all(|b| b.is_ascii_hexdigit());
        if !leftover && !layer {
            continue;
        }
        let whole = layer && root.join(h).is_dir() && root.join(format!("{h}.done")).is_file();
        if leftover || !keep.contains(h) || !whole {
            let path = entry.path();
            let _ = if is_marker || !path.is_dir() { fs::remove_file(&path) } else { fs::remove_dir_all(&path) };
        }
    }
}

/// The most a layer may expand to. The blob's digest covers only its
/// compressed bytes, so a tiny, digest-valid layer could otherwise expand
/// without limit onto the disk (on a Linux host or in WSL, the host's own).
/// 256x the compressed size, never below 1 GiB nor above 64 GiB.
fn expansion_cap(compressed: u64) -> u64 {
    compressed.saturating_mul(256).clamp(1 << 30, 64 << 30)
}

/// A reader that fails once more than `left` bytes have come through.
pub(super) struct Capped<R> {
    pub(super) inner: R,
    pub(super) left: u64,
}

impl<R: Read> Read for Capped<R> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let n = self.inner.read(buf)?;
        if n as u64 > self.left {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "stream exceeds the allowed size"));
        }
        self.left -= n as u64;
        Ok(n)
    }
}

fn unpack(blob: &mut impl Read, media_type: &str, dest: &Path, compressed: u64) -> io::Result<u64> {
    untar(decoded(blob, media_type, compressed)?, dest)
}

/// The layer's tar stream, failing once it passes [`expansion_cap`].
fn decoded<'a>(blob: &'a mut impl Read, media_type: &str, compressed: u64) -> io::Result<Capped<Box<dyn Read + 'a>>> {
    let buffered = BufReader::with_capacity(256 * 1024, blob);
    let inner: Box<dyn Read + 'a> = if media_type.ends_with("gzip") {
        Box::new(flate2::read::MultiGzDecoder::new(buffered))
    } else if media_type.ends_with("zstd") {
        Box::new(
            ruzstd::decoding::StreamingDecoder::new(buffered)
                .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("zstd: {e}")))?,
        )
    } else {
        Box::new(buffered)
    };
    Ok(Capped { inner, left: expansion_cap(compressed) })
}

/// Unpacks a layer tarball, translating OCI whiteouts into the form overlayfs
/// reads: `.wh.name` becomes a 0:0 character device `name`, and
/// `.wh..wh..opq` marks its directory opaque.
fn untar(reader: impl Read, dest: &Path) -> io::Result<u64> {
    let mut archive = tar::Archive::new(reader);
    archive.set_preserve_permissions(true);
    archive.set_preserve_ownerships(true);
    archive.set_preserve_mtime(true);
    archive.set_overwrite(true);
    let mut total = 0u64;
    for entry in archive.entries()? {
        let mut entry = entry?;
        let path = entry.path()?.into_owned();
        let name = path.file_name().map(|n| n.as_bytes()).unwrap_or_default();
        if let Some(hidden) = name.strip_prefix(b".wh.") {
            // `.wh.`, `.wh..` and `.wh...` would hide the directory itself or its parent.
            if matches!(hidden, b"" | b"." | b"..") {
                return Err(escapes());
            }
            let parent = whiteout_dir(dest, path.parent().unwrap_or(Path::new("")))?;
            if hidden == b".wh..opq" {
                let p = sys::cstr(&parent)?;
                // SAFETY: valid NUL-terminated path, name and a 1-byte value.
                let ret = unsafe {
                    libc::setxattr(p.as_ptr(), c"trusted.overlay.opaque".as_ptr(), b"y".as_ptr().cast(), 1, 0)
                };
                sys::check(ret as _, "mark opaque")?;
            } else {
                let target = parent.join(std::ffi::OsStr::from_bytes(hidden));
                let _ = fs::remove_file(&target);
                let _ = fs::remove_dir_all(&target);
                sys::mknod(&sys::cstr(&target)?, libc::S_IFCHR, 0, 0)?;
            }
            continue;
        }
        total += entry.size();
        let xattrs = pax_xattrs(&mut entry)?;
        // Entries whose paths escape the root (`..` components) come back
        // false and were skipped; a layer recorded as loaded with bytes
        // missing is a silent corruption, so refuse it.
        if !entry.unpack_in(dest)? {
            return Err(escapes());
        }
        for (key, value) in xattrs {
            set_pax_xattr(&dest.join(&path), &key, &value);
        }
    }
    Ok(total)
}

/// The `SCHILY.xattr.*` pax keywords an entry carries, filtered to Linux
/// xattr namespaces. tar-rs applies these verbatim and fails the whole
/// entry on the first setxattr error, which rejects archives made by
/// macOS tooling (`com.apple.provenance` et al. have no Linux
/// namespace); filtering here keeps real xattrs (`user.*`, `security.*`,
/// `trusted.*`, `system.*`) working while foreign ones are skipped.
pub(crate) fn pax_xattrs<R: Read>(entry: &mut tar::Entry<'_, R>) -> io::Result<Vec<(Vec<u8>, Vec<u8>)>> {
    let mut out = Vec::new();
    let Some(exts) = entry.pax_extensions()? else { return Ok(out) };
    for e in exts.flatten() {
        let Some(key) = e.key_bytes().strip_prefix(b"SCHILY.xattr.") else { continue };
        if key.starts_with(b"user.") || key.starts_with(b"trusted.") || key.starts_with(b"security.") || key.starts_with(b"system.") {
            out.push((key.to_vec(), e.value_bytes().to_vec()));
        }
    }
    Ok(out)
}

/// Best-effort `lsetxattr` for one pax keyword: a layer whose xattrs the
/// filesystem refuses still unpacks, matching how Docker treats xattr
/// application as non-fatal.
///
/// `lsetxattr` never follows a symlink at the last component, so a symlink
/// entry's xattrs can only label the link itself, never its target outside the
/// layer (DSLP-7). Linux refuses `user.*` on a symlink (EPERM); like Docker
/// (`pkg/archive`) and containerd, that error is ignored with the rest.
pub(crate) fn set_pax_xattr(path: &Path, key: &[u8], value: &[u8]) {
    let (Ok(p), Ok(k)) = (sys::cstr(path), std::ffi::CString::new(key)) else { return };
    // SAFETY: valid NUL-terminated path and name; value is an arbitrary
    // byte string with an explicit length.
    unsafe {
        libc::lsetxattr(p.as_ptr(), k.as_ptr(), value.as_ptr().cast(), value.len(), 0);
    }
}

fn escapes() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "whiteout escapes the layer")
}

/// The directory under `dest` a whiteout lives in, made if missing. Every
/// step must be a real directory of this layer: an earlier entry could have
/// made one a symlink, which a check of the path's text cannot see and which
/// would carry the whiteout outside the layer.
fn whiteout_dir(dest: &Path, parent: &Path) -> io::Result<PathBuf> {
    let mut dir = dest.to_path_buf();
    for part in parent.components() {
        match part {
            std::path::Component::Normal(name) => dir.push(name),
            std::path::Component::CurDir => continue,
            _ => return Err(escapes()),
        }
        match fs::symlink_metadata(&dir) {
            Ok(m) if m.is_dir() => {}
            Ok(_) => return Err(escapes()),
            Err(e) if e.kind() == io::ErrorKind::NotFound => fs::create_dir(&dir)?,
            Err(e) => return Err(e),
        }
    }
    Ok(dir)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A complete header: tar-rs refuses to unpack one with empty uid/gid.
    fn header(size: u64, mode: u32) -> tar::Header {
        let mut h = tar::Header::new_gnu();
        h.set_size(size);
        h.set_mode(mode);
        // SAFETY: these getters have no preconditions.
        let (uid, gid) = unsafe { (libc::geteuid(), libc::getegid()) };
        h.set_uid(u64::from(uid));
        h.set_gid(u64::from(gid));
        h.set_mtime(0);
        h.set_cksum();
        h
    }

    fn scratch(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("ctrs-layers-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    /// One pax extended-header record (`"%d %s=%s\n"`, length includes
    /// itself, the space and the newline).
    fn pax_record(key: &str, value: &[u8]) -> Vec<u8> {
        let body = format!("{key}=");
        let mut len = body.len() + value.len() + 8;
        loop {
            let total = len.to_string().len() + 1 + body.len() + value.len() + 1;
            if total == len {
                break;
            }
            len = total;
        }
        let mut rec = format!("{len} {body}").into_bytes();
        rec.extend_from_slice(value);
        rec.push(b'\n');
        rec
    }

    /// bsdtar-style pax xattrs: `com.apple.*` names have no Linux
    /// namespace and must be skipped, not fail the unpack; `user.*` must
    /// still be applied.
    #[test]
    fn pax_xattrs_filtered_to_linux_namespaces() {
        let mut pax = pax_record("SCHILY.xattr.user.note", b"hello");
        pax.extend(pax_record("SCHILY.xattr.com.apple.provenance", b"junk"));
        let mut b = tar::Builder::new(Vec::new());
        let mut h = header(pax.len() as u64, 0o644);
        h.set_entry_type(tar::EntryType::XHeader);
        b.append_data(&mut h, "PaxHeader.0/f.txt", &pax[..]).unwrap();
        let mut h = header(1, 0o644);
        b.append_data(&mut h, "f.txt", &b"x"[..]).unwrap();
        let bytes = b.into_inner().unwrap();
        let dest = scratch("pax");
        untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).unwrap();
        assert_eq!(fs::read(dest.join("f.txt")).unwrap(), b"x");
        let p = sys::cstr(dest.join("f.txt")).unwrap();
        let mut buf = [0u8; 16];
        // SAFETY: valid path, buffer and length.
        let n = unsafe { libc::lgetxattr(p.as_ptr(), c"user.note".as_ptr(), buf.as_mut_ptr().cast(), buf.len()) };
        assert_eq!(&buf[..n as usize], b"hello");
        let _ = fs::remove_dir_all(&dest);
    }

    fn xattr_of(path: &Path, name: &std::ffi::CStr) -> Option<Vec<u8>> {
        let p = sys::cstr(path).unwrap();
        let mut buf = [0u8; 64];
        // SAFETY: valid path, name, buffer and length.
        let n = unsafe { libc::lgetxattr(p.as_ptr(), name.as_ptr(), buf.as_mut_ptr().cast(), buf.len()) };
        (n >= 0).then(|| buf[..n as usize].to_vec())
    }

    /// A pax xattr header followed by a symlink entry aimed outside the layer
    /// must not label the link's target (DSLP-7); a regular file's xattrs are
    /// still applied. `security.capability` is root-only, as in CI.
    #[test]
    fn symlink_entry_xattrs_do_not_follow_the_link() {
        // VFS_CAP_REVISION_2 blob granting CAP_SETUID.
        let mut cap = vec![1, 0, 0, 2, 0x80, 0, 0, 0];
        cap.resize(20, 0);
        // SAFETY: geteuid has no preconditions.
        let root = unsafe { libc::geteuid() } == 0;
        let base = scratch("xattr-outside");
        let dest = base.join(".tmp-layer");
        fs::create_dir_all(&dest).unwrap();
        let victim = base.join("victim");
        fs::write(&victim, b"host").unwrap();

        let mut b = tar::Builder::new(Vec::new());
        let mut add = |name: &str, link: Option<&str>| {
            let mut pax = pax_record("SCHILY.xattr.user.deslop", b"pwned");
            if root {
                pax.extend(pax_record("SCHILY.xattr.security.capability", &cap));
            }
            let mut h = header(pax.len() as u64, 0o644);
            h.set_entry_type(tar::EntryType::XHeader);
            b.append_data(&mut h, format!("PaxHeader.0/{name}"), &pax[..]).unwrap();
            match link {
                Some(to) => {
                    let mut h = header(0, 0o777);
                    h.set_entry_type(tar::EntryType::Symlink);
                    b.append_link(&mut h, name, to).unwrap();
                }
                None => {
                    let mut h = header(1, 0o644);
                    b.append_data(&mut h, name, &b"x"[..]).unwrap();
                }
            }
        };
        add("abs", Some(victim.to_str().unwrap()));
        add("rel", Some("../victim"));
        add("plain", None);
        let bytes = b.into_inner().unwrap();
        untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).unwrap();

        assert_eq!(fs::read_link(dest.join("abs")).unwrap(), victim);
        assert_eq!(fs::read_link(dest.join("rel")).unwrap(), Path::new("../victim"));
        assert_eq!(xattr_of(&victim, c"user.deslop"), None, "user xattr followed the symlink");
        assert_eq!(xattr_of(&victim, c"security.capability"), None, "capability followed the symlink");
        // Behaviour kept: the regular file carries its records.
        assert_eq!(xattr_of(&dest.join("plain"), c"user.deslop").as_deref(), Some(&b"pwned"[..]));
        if root {
            assert_eq!(xattr_of(&dest.join("plain"), c"security.capability"), Some(cap));
        }
        let _ = fs::remove_dir_all(&base);
    }

    /// A layer whose first entry makes `foo` a symlink to `/` and whose
    /// second writes `foo/x` must not write outside the layer directory.
    #[test]
    fn symlink_parent_cannot_escape_layer() {
        let mut b = tar::Builder::new(Vec::new());
        let mut h = header(0, 0o777);
        h.set_entry_type(tar::EntryType::Symlink);
        b.append_link(&mut h, "foo", "/").unwrap();
        let mut h = header(1, 0o644);
        b.append_data(&mut h, "foo/x", &b"x"[..]).unwrap();
        let bytes = b.into_inner().unwrap();
        let dest = scratch("escape");
        let err = untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).expect_err("writing through a symlinked parent must fail");
        // The refusal must be the path check, not some other unpack error.
        assert!(err.to_string().contains("outside"), "unexpected error: {err}");
        assert!(!Path::new("/x").is_file() || fs::read_to_string("/x").map_or(true, |c| c != "x"), "escaped to /x");
        let _ = fs::remove_dir_all(&dest);
    }

    fn whiteout_layer(entries: &[(&str, Option<&str>)]) -> Vec<u8> {
        let mut b = tar::Builder::new(Vec::new());
        for (name, link) in entries {
            if let Some(to) = link {
                let mut h = header(0, 0o777);
                h.set_entry_type(tar::EntryType::Symlink);
                b.append_link(&mut h, name, to).unwrap();
            } else {
                let mut h = header(0, 0o644);
                b.append_data(&mut h, name, &[][..]).unwrap();
            }
        }
        b.into_inner().unwrap()
    }

    /// A whiteout under a symlink to a directory outside the layer must not
    /// delete, replace or mark anything there.
    #[test]
    fn whiteout_through_symlink_stays_in_layer() {
        let outside = scratch("wh-outside");
        fs::write(outside.join("victim"), "keep").unwrap();
        let to = outside.to_str().unwrap();
        for hidden in ["foo/.wh.victim", "foo/.wh..wh..opq"] {
            let dest = scratch("wh-escape");
            let bytes = whiteout_layer(&[("foo", Some(to)), (hidden, None)]);
            let err = untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).expect_err(hidden);
            assert!(err.to_string().contains("escapes"), "{hidden}: unexpected error: {err}");
            assert_eq!(fs::read_to_string(outside.join("victim")).unwrap(), "keep", "{hidden}");
            assert!(!outside.join(&hidden[4..]).exists(), "{hidden}: placeholder written outside");
            let _ = fs::remove_dir_all(&dest);
        }
        let _ = fs::remove_dir_all(&outside);
    }

    /// Whiteouts naming the directory itself or its parent are refused
    /// before anything is removed.
    #[test]
    fn whiteout_of_dot_or_dotdot_is_refused() {
        for hidden in ["d/.wh.", "d/.wh..", "d/.wh..."] {
            let dest = scratch("wh-dots");
            fs::create_dir_all(dest.join("d")).unwrap();
            fs::write(dest.join("d/keep"), "x").unwrap();
            let bytes = whiteout_layer(&[(hidden, None)]);
            let err = untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).expect_err(hidden);
            assert!(err.to_string().contains("escapes"), "{hidden}: unexpected error: {err}");
            assert!(dest.join("d/keep").is_file(), "{hidden}");
            let _ = fs::remove_dir_all(&dest);
        }
    }

    /// A whiteout whose own path is absolute (the tar builder won't write
    /// one, so the header is patched by hand) must not reach outside.
    #[test]
    fn whiteout_path_cannot_escape_layer() {
        let base = scratch("wh-abs");
        let dest = base.join("layer");
        fs::create_dir(&dest).unwrap();
        fs::write(base.join("keep"), "x").unwrap();
        let path = format!("{}/.wh.keep", base.display());
        let mut b = tar::Builder::new(Vec::new());
        b.append_data(&mut header(0, 0o644), "a".repeat(path.len()), &[][..]).unwrap();
        let mut bytes = b.into_inner().unwrap();
        bytes[..100].fill(0);
        bytes[..path.len()].copy_from_slice(path.as_bytes());
        bytes[148..156].fill(b' ');
        let checksum: u32 = bytes[..512].iter().map(|b| u32::from(*b)).sum();
        bytes[148..156].copy_from_slice(format!("{checksum:06o}\0 ").as_bytes());
        assert!(untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).is_err());
        assert!(base.join("keep").is_file());
        let _ = fs::remove_dir_all(&base);
    }

    /// An ordinary whiteout becomes overlayfs's 0:0 character device and
    /// leaves no `.wh.` file behind. mknod needs root, as in the guest.
    #[test]
    fn whiteout_becomes_char_device() {
        // SAFETY: a plain getter.
        if unsafe { libc::geteuid() } != 0 {
            eprintln!("skipped: needs root for mknod");
            return;
        }
        let probe = scratch("wh-probe");
        fs::create_dir_all(&probe).unwrap();
        let probe_path = probe.join("dev");
        // SAFETY: plain C library call.
        match sys::cstr(&probe_path).and_then(|p| sys::mknod(&p, libc::S_IFCHR, 0, 0)) {
            Ok(()) => {
                let _ = fs::remove_file(&probe_path);
            }
            Err(_) => {
                eprintln!("skipped: this environment forbids mknod of device 0:0");
                let _ = fs::remove_dir_all(&probe);
                return;
            }
        }
        let _ = fs::remove_dir_all(&probe);
        use std::os::unix::fs::{FileTypeExt, MetadataExt};
        let dest = scratch("wh-ok");
        fs::create_dir_all(dest.join("etc")).unwrap();
        fs::write(dest.join("etc/gone"), "x").unwrap();
        let bytes = whiteout_layer(&[("etc/.wh.gone", None)]);
        untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).unwrap();
        let m = fs::symlink_metadata(dest.join("etc/gone")).unwrap();
        assert!(m.file_type().is_char_device() && m.rdev() == 0, "not a 0:0 char device");
        assert!(!dest.join("etc/.wh.gone").exists(), "placeholder left behind");
        let _ = fs::remove_dir_all(&dest);
        // As `docker commit` writes them: no owner or time, which tar-rs
        // would refuse to unpack. A whiteout is never unpacked, so it works,
        // and missing parents are made.
        let mut b = tar::Builder::new(Vec::new());
        let mut h = tar::Header::new_gnu();
        h.set_entry_type(tar::EntryType::Regular);
        h.set_size(0);
        h.set_mode(0o644);
        b.append_data(&mut h, "usr/share/.wh.doc", std::io::empty()).unwrap();
        let bytes = b.into_inner().unwrap();
        let dest = scratch("wh-bare");
        untar(Capped { inner: &bytes[..], left: u64::MAX }, &dest).unwrap();
        assert!(fs::symlink_metadata(dest.join("usr/share/doc")).unwrap().file_type().is_char_device());
        let _ = fs::remove_dir_all(&dest);
    }

    fn layer_blob(files: &[(&str, &[u8])]) -> Vec<u8> {
        let mut b = tar::Builder::new(Vec::new());
        for (name, data) in files {
            b.append_data(&mut header(data.len() as u64, 0o644), name, *data).unwrap();
        }
        b.into_inner().unwrap()
    }

    const D1: &str = "sha256:1111111111111111111111111111111111111111111111111111111111111111";
    const D2: &str = "sha256:2222222222222222222222222222222222222222222222222222222222222222";

    fn gzip(bytes: &[u8]) -> Vec<u8> {
        use std::io::Write;
        let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::fast());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    #[test]
    fn gzip_layers_restore_contents_and_empty_archives() {
        let root = scratch("gzip");
        for (digest, files) in [(D1, vec![("file", &b"contents"[..])]), (D2, vec![])] {
            let blob = gzip(&layer_blob(&files));
            let begin = LayerBegin { digest, media_type: "application/vnd.oci.image.layer.v1.tar+gzip", size: blob.len() as u64 };
            receive(&mut &blob[..], &begin, &root).unwrap();
            assert!(present(&root, digest));
        }
        assert_eq!(fs::read(dir(&root, D1).unwrap().join("file")).unwrap(), b"contents");
        assert_eq!(fs::read_dir(dir(&root, D2).unwrap()).unwrap().count(), 0);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn concatenated_gzip_members_form_one_layer() {
        let root = scratch("gzip-members");
        let tar = layer_blob(&[("file", b"contents")]);
        let split = tar.len() / 2;
        let mut blob = gzip(&tar[..split]);
        blob.extend(gzip(&tar[split..]));
        let begin = LayerBegin { digest: D1, media_type: "application/vnd.oci.image.layer.v1.tar+gzip", size: blob.len() as u64 };
        receive(&mut &blob[..], &begin, &root).unwrap();
        assert_eq!(fs::read(dir(&root, D1).unwrap().join("file")).unwrap(), b"contents");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn truncated_gzip_never_commits_a_layer() {
        let root = scratch("gzip-truncated");
        let mut blob = gzip(&layer_blob(&[("file", &vec![b'x'; 512 * 1024])]));
        blob.truncate(blob.len() / 2);
        let begin = LayerBegin { digest: D1, media_type: "application/vnd.oci.image.layer.v1.tar+gzip", size: blob.len() as u64 };
        assert!(receive(&mut &blob[..], &begin, &root).is_err());
        assert!(!present(&root, D1));
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
        fs::remove_dir_all(root).unwrap();
    }

    fn send(root: &Path, digest: &str, blob: &[u8]) -> LayerStored {
        let begin = LayerBegin { digest, media_type: "application/vnd.oci.image.layer.v1.tar", size: blob.len() as u64 };
        receive(&mut &blob[..], &begin, root).unwrap()
    }

    /// A stored layer is present only with its marker; one cut short
    /// (directory, no marker) is not, and is replaced when sent again.
    #[test]
    fn layer_without_marker_is_replaced() {
        let root = scratch("marker");
        let blob = layer_blob(&[("bin/sh", b"real")]);
        send(&root, D1, &blob);
        assert!(present(&root, D1));
        assert_eq!(fs::read(dir(&root, D1).unwrap().join("bin/sh")).unwrap(), b"real");

        // What a VM stopped before the flush leaves: names, empty contents.
        fs::remove_file(marker(&root, D1).unwrap()).unwrap();
        fs::write(dir(&root, D1).unwrap().join("bin/sh"), b"").unwrap();
        assert!(!present(&root, D1));
        send(&root, D1, &blob);
        assert!(present(&root, D1));
        assert_eq!(fs::read(dir(&root, D1).unwrap().join("bin/sh")).unwrap(), b"real");
        let _ = fs::remove_dir_all(&root);
    }

    /// Retain keeps whole layers it is told to and deletes the rest:
    /// unlisted layers, unmarked ones, leftovers. Other names stay.
    #[test]
    fn retain_deletes_unused_and_broken_layers() {
        let root = scratch("retain");
        let blob = layer_blob(&[("f", b"x")]);
        send(&root, D1, &blob);
        send(&root, D2, &blob);
        let broken = "3".repeat(64);
        fs::create_dir(root.join(&broken)).unwrap();
        fs::create_dir(root.join(format!(".stale-{broken}-1"))).unwrap();
        fs::create_dir(root.join(format!(".tmp-{broken}"))).unwrap();
        fs::write(root.join("other"), "keep").unwrap();

        retain(&root, [D1, &format!("sha256:{broken}")].into_iter());
        assert!(present(&root, D1));
        assert!(!dir(&root, D2).unwrap().exists() && !marker(&root, D2).unwrap().exists());
        assert!(!root.join(&broken).exists(), "unmarked layer kept");
        assert!(!root.join(format!(".stale-{broken}-1")).exists() && !root.join(format!(".tmp-{broken}")).exists());
        assert!(root.join("other").is_file());
        let _ = fs::remove_dir_all(&root);
    }

    /// A layer that expands past its cap is refused.
    #[test]
    fn expansion_is_capped() {
        let mut b = tar::Builder::new(Vec::new());
        let data = vec![0u8; 4096];
        let mut h = header(data.len() as u64, 0o644);
        b.append_data(&mut h, "big", &data[..]).unwrap();
        let bytes = b.into_inner().unwrap();
        // As in receive(): a layer that fails is discarded, never reused.
        let capped = scratch("cap");
        assert!(untar(Capped { inner: &bytes[..], left: 1024 }, &capped).is_err());
        let _ = fs::remove_dir_all(&capped);
        let fresh = scratch("cap-ok");
        assert_eq!(untar(Capped { inner: &bytes[..], left: u64::MAX }, &fresh).unwrap(), 4096);
        let _ = fs::remove_dir_all(&fresh);
        assert_eq!(expansion_cap(1), 1 << 30);
        assert_eq!(expansion_cap(1 << 40), 64 << 30);
    }

    const GZIP: &str = "application/vnd.oci.image.layer.v1.tar+gzip";
    const ZSTD: &str = "application/vnd.oci.image.layer.v1.tar+zstd";
    const BLOCK: usize = 64 << 10;
    const BLOCKS: u64 = 32768;

    /// A deterministic equivalent of the W6 compatibility fixture, rebuilt
    /// from its documented construction because the original artifacts were
    /// deleted: one 64 KiB high-entropy block repeated 32,768 times (2 GiB)
    /// as the single file of a layer tarball.
    fn repeated_block() -> Vec<u8> {
        let mut x = 0x9E37_79B9_7F4A_7C15_u64;
        (0..BLOCK)
            .map(|_| {
                x ^= x << 13;
                x ^= x >> 7;
                x ^= x << 17;
                x as u8
            })
            .collect()
    }

    fn payload_header() -> tar::Header {
        let mut h = header(BLOCKS * BLOCK as u64, 0o644);
        h.set_path("payload").unwrap();
        h.set_cksum();
        h
    }

    /// The layer tarball, streamed: header, payload, end-of-archive blocks.
    struct RepeatedLayer {
        head: Vec<u8>,
        block: Vec<u8>,
        offset: u64,
    }

    impl RepeatedLayer {
        fn new() -> Self {
            Self { head: payload_header().as_bytes().to_vec(), block: repeated_block(), offset: 0 }
        }
        fn len() -> u64 {
            512 + BLOCKS * BLOCK as u64 + 1024
        }
    }

    impl Read for RepeatedLayer {
        fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
            let payload_end = 512 + BLOCKS * BLOCK as u64;
            let n = if self.offset < 512 {
                let at = self.offset as usize;
                let n = buf.len().min(512 - at);
                buf[..n].copy_from_slice(&self.head[at..at + n]);
                n
            } else if self.offset < payload_end {
                let at = ((self.offset - 512) % BLOCK as u64) as usize;
                let n = buf.len().min(BLOCK - at).min((payload_end - self.offset) as usize);
                buf[..n].copy_from_slice(&self.block[at..at + n]);
                n
            } else {
                let n = buf.len().min((Self::len() - self.offset) as usize);
                buf[..n].fill(0);
                n
            };
            self.offset += n as u64;
            Ok(n)
        }
    }

    /// The same layer as one zstd frame: a raw block holding the tar header
    /// and the first payload block, then blocks that each copy the previous
    /// 64 KiB, as a long-window zstd encoder (BuildKit's level 3) emits.
    fn repeated_layer_zstd() -> Vec<u8> {
        fn block_header(out: &mut Vec<u8>, kind: u32, size: u32, last: bool) {
            out.extend_from_slice(&((size << 3) | (kind << 1) | u32::from(last)).to_le_bytes()[..3]);
        }
        fn copy_previous_block(out: &mut Vec<u8>, length: u32) {
            let (ml_code, ml_bits, ml_base) = if length > 65538 { (52u8, 16, 65539) } else { (51u8, 15, 32771) };
            let of_extra = 3u64;
            let bits = (u64::from(length - ml_base)) | (of_extra << ml_bits) | (1 << (ml_bits + 16));
            let stream = &bits.to_le_bytes()[..(ml_bits as usize + 16) / 8 + 1];
            let body = [&[0x00, 0x01, 0x54, 0x00, 16, ml_code][..], stream].concat();
            block_header(out, 2, body.len() as u32, false);
            out.extend_from_slice(&body);
        }
        let mut out = vec![0x28, 0xb5, 0x2f, 0xfd, 0x00, 0x38];
        let first = [payload_header().as_bytes(), &repeated_block()[..]].concat();
        block_header(&mut out, 0, first.len() as u32, false);
        out.extend_from_slice(&first);
        for _ in 0..(BLOCKS - 1) / 2 {
            copy_previous_block(&mut out, 2 * BLOCK as u32);
        }
        copy_previous_block(&mut out, BLOCK as u32);
        block_header(&mut out, 1, 1024, true);
        out.push(0);
        out
    }

    fn same_bytes(mut got: impl Read, mut want: impl Read) -> io::Result<u64> {
        let (mut a, mut b) = (vec![0; 1 << 20], vec![0; 1 << 20]);
        let mut total = 0;
        loop {
            let n = got.read(&mut a)?;
            want.read_exact(&mut b[..n])?;
            assert!(a[..n] == b[..n], "decoded layer differs at byte {total}");
            if n == 0 {
                assert_eq!(want.read(&mut b)?, 0, "decoded layer ends early at byte {total}");
                return Ok(total);
            }
            total += n as u64;
        }
    }

    /// The compressed size that made a zstd default reject a valid layer:
    /// the frame decodes to the exact tarball, but its 256x expansion
    /// allowance is the 1 GiB floor, below the 2 GiB payload.
    #[test]
    fn highly_compressible_zstd_layer_exceeds_the_expansion_cap() {
        let blob = repeated_layer_zstd();
        assert!(expansion_cap(blob.len() as u64) < RepeatedLayer::len());
        let decoder = ruzstd::decoding::StreamingDecoder::new(&blob[..]).unwrap();
        assert_eq!(same_bytes(decoder, RepeatedLayer::new()).unwrap(), RepeatedLayer::len());

        let err = same_bytes(decoded(&mut &blob[..], ZSTD, blob.len() as u64).unwrap(), RepeatedLayer::new()).unwrap_err();
        assert_eq!(err.to_string(), "stream exceeds the allowed size");
    }

    #[test]
    fn rejected_zstd_layer_leaves_no_partial_layer() {
        let root = scratch("zstd-cap");
        let blob = repeated_layer_zstd();
        let begin = LayerBegin { digest: D1, media_type: ZSTD, size: blob.len() as u64 };
        let err = receive(&mut &blob[..], &begin, &root).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::InvalidData);
        assert!(format!("{err:?}").contains("stream exceeds the allowed size"), "{err:?}");
        assert!(!present(&root, D1));
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
        fs::remove_dir_all(root).unwrap();
    }

    /// Deflate's 32 KiB window cannot reach a 64 KiB repeat, so a gzip layer
    /// of this payload stays about its own size (BuildKit's default gzip
    /// layer was 2,148,142,839 bytes) and keeps the 64 GiB allowance. Stored
    /// deflate blocks stand in for that encoder here.
    #[test]
    fn same_layer_as_gzip_decodes_exactly_within_the_cap() {
        let mut encoder = flate2::read::GzEncoder::new(RepeatedLayer::new(), flate2::Compression::none());
        let gzip_len = io::copy(&mut encoder, &mut io::sink()).unwrap();
        assert!(expansion_cap(gzip_len) > RepeatedLayer::len());
        let mut blob = flate2::read::GzEncoder::new(RepeatedLayer::new(), flate2::Compression::none());
        assert_eq!(same_bytes(decoded(&mut blob, GZIP, gzip_len).unwrap(), RepeatedLayer::new()).unwrap(), RepeatedLayer::len());
    }
}
