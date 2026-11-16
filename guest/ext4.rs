use std::io::{self, Read, Seek, SeekFrom};

#[derive(Debug, PartialEq)]
pub struct Geometry {
    pub block_bytes: u64,
    pub filesystem_bytes: u64,
}

/// Read fixed ext4 geometry fields; mounting remains the filesystem validator.
/// Field offsets and little-endian encoding follow the Linux ext4 superblock ABI.
pub fn geometry(reader: &mut (impl Read + Seek)) -> io::Result<Geometry> {
    let mut bytes = [0u8; 1024];
    reader.seek(SeekFrom::Start(1024))?;
    reader.read_exact(&mut bytes)?;
    if u16::from_le_bytes(bytes[0x38..0x3a].try_into().unwrap()) != 0xef53 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "data disk is not ext4"));
    }
    let word = |at: usize| u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap());
    let log = word(0x18);
    if log > 6 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "unsupported ext4 block size"));
    }
    let block_bytes = 1024u64 << log;
    let blocks = u64::from(word(4)) | if word(0x60) & 0x80 != 0 { u64::from(word(0x150)) << 32 } else { 0 };
    let filesystem_bytes = blocks.checked_mul(block_bytes).filter(|n| *n >= 2048)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid ext4 block count"))?;
    Ok(Geometry { block_bytes, filesystem_bytes })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn image(blocks: u64, log: u32, wide: bool) -> Cursor<Vec<u8>> {
        let mut bytes = vec![0; 2048];
        let sb = &mut bytes[1024..];
        sb[0x38..0x3a].copy_from_slice(&0xef53u16.to_le_bytes());
        sb[4..8].copy_from_slice(&(blocks as u32).to_le_bytes());
        sb[0x150..0x154].copy_from_slice(&((blocks >> 32) as u32).to_le_bytes());
        sb[0x18..0x1c].copy_from_slice(&log.to_le_bytes());
        sb[0x60..0x64].copy_from_slice(&(if wide { 0x80u32 } else { 0 }).to_le_bytes());
        Cursor::new(bytes)
    }

    #[test]
    fn ext4_geometry_uses_feature_gated_high_count_and_block_units() {
        assert_eq!(geometry(&mut image(1 << 18, 2, true)).unwrap(), Geometry { block_bytes: 4096, filesystem_bytes: 1 << 30 });
        assert_eq!(geometry(&mut image((1 << 32) + 2, 0, true)).unwrap().filesystem_bytes, ((1 << 32) + 2) * 1024);
        assert_eq!(geometry(&mut image((1 << 32) + 2, 0, false)).unwrap().filesystem_bytes, 2048);
    }

    #[test]
    fn ext4_geometry_rejects_missing_magic_short_reads_and_overflow() {
        assert!(geometry(&mut Cursor::new(vec![0; 2048])).is_err());
        assert!(geometry(&mut Cursor::new(vec![0; 1800])).is_err());
        assert!(geometry(&mut image(0, 2, true)).is_err());
        assert!(geometry(&mut image(1, 7, true)).is_err());
        assert!(geometry(&mut image(u64::MAX, 6, true)).is_err());
    }
}
