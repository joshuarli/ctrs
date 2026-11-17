use std::fs;

#[derive(Debug)]
pub(crate) struct Snapshot {
    total: Result<u64, String>,
    available: Result<u64, String>,
    balloon: Result<u64, String>,
}

impl Snapshot {
    pub(crate) fn read() -> Self {
        match fs::read_to_string("/proc/meminfo") {
            Ok(text) => Self::parse(&text),
            Err(error) => {
                let error = format!("read /proc/meminfo: {error}");
                Self { total: Err(error.clone()), available: Err(error.clone()), balloon: Err(error) }
            }
        }
    }

    fn parse(text: &str) -> Self {
        Self {
            total: field(text, "MemTotal"),
            available: field(text, "MemAvailable"),
            balloon: field(text, "Balloon"),
        }
    }

    pub(crate) fn total_kib(&self) -> u64 {
        value_or_zero(&self.total)
    }

    pub(crate) fn available_kib(&self) -> u64 {
        value_or_zero(&self.available)
    }

    pub(crate) fn target_used_kib(&self) -> Result<u64, String> {
        let total = *self.total.as_ref().map_err(Clone::clone)?;
        let available = *self.available.as_ref().map_err(Clone::clone)?;
        let balloon = *self.balloon.as_ref().map_err(Clone::clone)?;
        total.checked_sub(available).and_then(|used| used.checked_sub(balloon))
            .ok_or_else(|| "meminfo available and balloon exceed total".to_string())
    }
}

fn value_or_zero(value: &Result<u64, String>) -> u64 {
    match value {
        Ok(value) => *value,
        Err(error) => {
            eprintln!("ctrs-init: {error}; reporting 0 KiB");
            0
        }
    }
}

fn field(text: &str, name: &str) -> Result<u64, String> {
    let mut matches = text.lines().filter_map(|line| {
        let (key, value) = line.split_once(':')?;
        (key == name).then_some(value)
    });
    let value = matches.next().ok_or_else(|| format!("meminfo missing {name}"))?;
    if matches.next().is_some() {
        return Err(format!("meminfo duplicate {name}"));
    }
    let mut parts = value.split_whitespace();
    let number = parts.next().and_then(|value| value.parse::<u64>().ok());
    match (number, parts.next(), parts.next()) {
        (Some(number), Some("kB"), None) => Ok(number),
        _ => Err(format!("meminfo invalid {name}: {value}")),
    }
}

#[cfg(test)]
mod tests {
    use super::Snapshot;

    #[test]
    fn captured_actual_balloon() {
        let snapshot = Snapshot::parse("MemTotal: 8211692 kB\nMemAvailable: 43500 kB\nBalloon: 7942144 kB\n");
        assert_eq!(snapshot.total_kib(), 8211692);
        assert_eq!(snapshot.available_kib(), 43500);
        assert_eq!(snapshot.target_used_kib().unwrap(), 226048);
    }

    #[test]
    fn zero_balloon() {
        let snapshot = Snapshot::parse("MemTotal: 1000 kB\nMemAvailable: 300 kB\nBalloon: 0 kB\n");
        assert_eq!(snapshot.target_used_kib().unwrap(), 700);
    }

    #[test]
    fn missing_and_invalid_counters_are_errors() {
        for text in [
            "MemTotal: 1000 kB\nMemAvailable: 300 kB\n",
            "MemTotal: nope kB\nMemAvailable: 300 kB\nBalloon: 0 kB\n",
            "MemTotal: 18446744073709551616 kB\nMemAvailable: 300 kB\nBalloon: 0 kB\n",
            "MemTotal: 1000 MB\nMemAvailable: 300 kB\nBalloon: 0 kB\n",
            "MemTotal: 1000 kB extra\nMemAvailable: 300 kB\nBalloon: 0 kB\n",
            "MemTotal: 1000 kB\nMemTotal: 1000 kB\nMemAvailable: 300 kB\nBalloon: 0 kB\n",
            "MemTotal: 1000 kB\nMemAvailable: 1001 kB\nBalloon: 0 kB\n",
            "MemTotal: 1000 kB\nMemAvailable: 300 kB\nBalloon: 701 kB\n",
        ] {
            assert!(Snapshot::parse(text).target_used_kib().is_err(), "{text}");
        }
    }
}
