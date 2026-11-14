//! Typed nf_tables configuration for Kiri's networking.
//!
//! CTRS-11 defines the vocabulary only: `netlink.rs` remains the
//! implementation until CTRS-12 wires an adapter behind the `crabtables`
//! feature (same semantics, different encoder). The types here exist so the
//! configuration is *checkable* — ownership by construction (only the `kiri`
//! table can be named), canonical chain priorities, one policy per family —
//! and so a backend can report what the kernel accepted.
//!
//! Unused until CTRS-12; the allow rides on the module, not the items, so a
//! dangling reference is still an error.
//!
//! Semantics match `docs/firewall.md`: a policy is the *whole table*, applied
//! as one batch (`DESTROYTABLE` + `NEWTABLE` + chains + rules). A refused
//! batch leaves the previous table in place (that is [`ApplyOutcome::RolledBack`]);
//! an ambiguous reply is [`ApplyOutcome::OutcomeUnknown`], and the caller must
//! re-read the table before building another transaction.

#![allow(dead_code)]

use std::io;
use std::os::fd::RawFd;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NftFamily {
    Ipv4,
    Ipv6,
}

/// Version of the reference configuration; a transaction carries it so a
/// backend can refuse one built by a newer agent.
pub const FIREWALL_CONFIG_VERSION: u64 = 1;

/// The only table this crate manages. Owned by construction: there is no way
/// to name another.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TableName(());

impl TableName {
    pub const KIRI: TableName = TableName(());
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Hook {
    Prerouting,
    Input,
    Forward,
    Postrouting,
    LocalOut,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChainKind {
    Nat,
    Filter,
}

/// The closed set of chains the reference configuration uses.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChainName {
    Prerouting,
    Output,
    Forward,
    Input,
    Postrouting,
}

impl ChainName {
    pub fn hook(self) -> Hook {
        match self {
            ChainName::Prerouting => Hook::Prerouting,
            ChainName::Output => Hook::LocalOut,
            ChainName::Forward => Hook::Forward,
            ChainName::Input => Hook::Input,
            ChainName::Postrouting => Hook::Postrouting,
        }
    }

    pub fn kind(self) -> ChainKind {
        match self {
            ChainName::Prerouting | ChainName::Output | ChainName::Postrouting => ChainKind::Nat,
            ChainName::Forward | ChainName::Input => ChainKind::Filter,
        }
    }

    /// The canonical priority for the reference configuration: NAT
    /// prerouting/output -100, filter chains 0, NAT postrouting 100.
    pub fn priority(self) -> i32 {
        match (self.kind(), self.hook()) {
            (ChainKind::Nat, Hook::Postrouting) => 100,
            (ChainKind::Nat, _) => -100,
            (ChainKind::Filter, _) => 0,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            ChainName::Prerouting => "prerouting",
            ChainName::Output => "output",
            ChainName::Forward => "forward",
            ChainName::Input => "input",
            ChainName::Postrouting => "postrouting",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Accept,
    Drop,
}

/// One typed atom of a rule. Deliberately small: it covers exactly the
/// expressions the reference configuration uses today, not a general nft AST.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Match {
    /// `iifname|oifname <op> "kiri*"`: a 4-byte prefix match.
    IifnamePrefix,
    OifnamePrefix,
    /// Whole IFNAMSIZ comparison (NUL-padded), used per bridge.
    IifnameIs(String),
    OifnameIs(String),
    /// `meta iif|oif <index>` equality.
    Iif(u32),
    Oif(u32),
    /// `meta l4proto` equality.
    L4Proto(u8),
    /// `ct state & mask != 0` (NF_CT_STATE_BIT bits, e.g. ESTABLISHED|RELATED).
    CtStateMasked(u32),
    /// `ct status & mask != 0` (IPS_DST_NAT = 1 << 5).
    CtStatusMasked(u32),
    /// Destination address payload match (network header +16, 4 bytes for
    /// IPv4, +8/16 for IPv6), with an optional 4-bit mask over the first byte
    /// (`!= 127.0.0.0/8` in the reference).
    PayloadDaddrV4 { masked_neq: bool },
    /// Source address prefix match (IPv6 NAT66).
    PayloadSaddrV6 { prefix: u8 },
    /// `fib daddr type local` (NFTA_FIB_DREG, ADDRTYPE, DADDR): v4 only.
    FibDaddrTypeLocal,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Target {
    /// `masquerade` (IPv4) or NAT66 via `saddr` prefix.
    Masquerade { random_fully: bool },
    Dnat { to_ip: [u8; 4], to_port: u16 },
    /// `redirect` to `port`.
    Redirect { to: u16 },
    Verdict(Verdict),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Rule {
    pub chain: ChainName,
    pub matches: Vec<Match>,
    pub target: Target,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChainSpec {
    pub name: ChainName,
    pub policy: Verdict,
}

impl ChainSpec {
    pub fn of(name: ChainName, policy: Verdict) -> Self {
        ChainSpec { name, policy }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TableSpec {
    pub family: NftFamily,
    pub table: TableName,
    pub chains: Vec<ChainSpec>,
    /// In order: `forward` and `input` are order-sensitive.
    pub rules: Vec<Rule>,
}

/// The whole desired state, one table per family (at most one each).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FirewallPolicy {
    pub version: u64,
    pub tables: Vec<TableSpec>,
}

impl FirewallPolicy {
    /// The state of an engine with no managed networks: no tables at all.
    pub fn empty() -> Self {
        FirewallPolicy { version: FIREWALL_CONFIG_VERSION, tables: Vec::new() }
    }

    pub fn validate(&self) -> Result<(), PolicyError> {
        let mut families = Vec::new();
        for table in &self.tables {
            if families.contains(&table.family) {
                return Err(PolicyError::DuplicateTable(table.family));
            }
            families.push(table.family);
            for rule in &table.rules {
                if !table.chains.iter().any(|c| c.name == rule.chain) {
                    return Err(PolicyError::UnknownChain { family: table.family, chain: rule.chain });
                }
            }
        }
        Ok(())
    }

    /// The batch that installs this policy atomically into `netns`.
    pub fn transaction(&self, netns: Netns) -> Result<FirewallTransaction, PolicyError> {
        self.validate()?;
        let mut steps = Vec::new();
        for table in &self.tables {
            steps.push(Step::BeginBatch);
            steps.push(Step::DestroyTable { family: table.family });
            steps.push(Step::CreateTable { family: table.family });
            for chain in &table.chains {
                steps.push(Step::CreateChain { family: table.family, chain: *chain });
            }
            for rule in &table.rules {
                steps.push(Step::CreateRule { family: table.family, rule: rule.clone() });
            }
            steps.push(Step::EndBatch);
        }
        Ok(FirewallTransaction { version: self.version, netns, steps })
    }
}

/// Which network namespace a transaction applies to. Explicit: the caller
/// chooses the VM's or the calling thread's namespace.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Netns {
    /// The socket is opened in the calling thread's namespace.
    Current,
    /// A `NETLINK_ROUTE` socket opened inside another namespace, kept bound to it.
    File(RawFd),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Step {
    BeginBatch,
    DestroyTable { family: NftFamily },
    CreateTable { family: NftFamily },
    CreateChain { family: NftFamily, chain: ChainSpec },
    CreateRule { family: NftFamily, rule: Rule },
    EndBatch,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FirewallTransaction {
    pub version: u64,
    pub netns: Netns,
    pub steps: Vec<Step>,
}

/// What the kernel answered. An atomic batch either commits or does not.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApplyOutcome {
    /// The batch committed; the table now matches the policy.
    Applied,
    /// Refused somewhere; the kernel keeps the previous table.
    RolledBack { cause: String },
    /// The reply path failed or was ambiguous; whether the batch committed
    /// is unknowable. Re-read the table before building another transaction
    /// (do not retry blindly).
    OutcomeUnknown { cause: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyError {
    DuplicateTable(NftFamily),
    UnknownChain { family: NftFamily, chain: ChainName },
}

/// The hole CTRS-12 plugs into: build the wire bytes from a transaction.
pub trait FirewallBackend {
    fn apply(&self, transaction: &FirewallTransaction) -> ApplyOutcome;
}

pub fn describe_apply(outcome: &ApplyOutcome) -> &'static str {
    match outcome {
        ApplyOutcome::Applied => "applied",
        ApplyOutcome::RolledBack { .. } => "rolled-back",
        ApplyOutcome::OutcomeUnknown { .. } => "outcome-unknown",
    }
}

pub fn io_outcome(result: Result<(), io::Error>) -> ApplyOutcome {
    match result {
        Ok(()) => ApplyOutcome::Applied,
        // Any refusal mid-batch is atomic: the kernel keeps the old table.
        Err(e) => ApplyOutcome::RolledBack { cause: e.to_string() },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy() -> FirewallPolicy {
        FirewallPolicy {
            version: FIREWALL_CONFIG_VERSION,
            tables: vec![TableSpec {
                family: NftFamily::Ipv4,
                table: TableName::KIRI,
                chains: vec![ChainSpec::of(ChainName::Postrouting, Verdict::Accept), ChainSpec::of(ChainName::Forward, Verdict::Accept)],
                rules: vec![Rule {
                    chain: ChainName::Postrouting,
                    matches: vec![Match::Oif(3)],
                    target: Target::Masquerade { random_fully: false },
                }],
            }],
        }
    }

    #[test]
    fn ownership_is_a_single_name() {
        // Only TableName::KIRI exists; there is no constructor for another.
        assert_eq!(TableName::KIRI, TableName(()));
    }

    #[test]
    fn canonical_chain_priorities() {
        assert_eq!(ChainName::Prerouting.priority(), -100);
        assert_eq!(ChainName::Output.priority(), -100);
        assert_eq!(ChainName::Postrouting.priority(), 100);
        assert_eq!(ChainName::Forward.priority(), 0);
        assert_eq!(ChainName::Input.priority(), 0);
        assert_eq!(ChainName::Prerouting.hook(), Hook::Prerouting);
        assert_eq!(ChainName::Output.hook(), Hook::LocalOut);
    }

    #[test]
    fn validate_rejects_duplicate_table_family() {
        let mut p = policy();
        p.tables.push(p.tables[0].clone());
        assert_eq!(p.validate(), Err(PolicyError::DuplicateTable(NftFamily::Ipv4)));
    }

    #[test]
    fn validate_rejects_a_rule_for_a_chain_that_is_not_there() {
        let mut p = policy();
        p.tables[0].rules.push(Rule { chain: ChainName::Input, matches: Vec::new(), target: Target::Verdict(Verdict::Drop) });
        assert_eq!(p.validate(), Err(PolicyError::UnknownChain { family: NftFamily::Ipv4, chain: ChainName::Input }));
    }

    #[test]
    fn transaction_is_one_atomic_batch_per_table() {
        let p = policy();
        let tx = p.transaction(Netns::Current).unwrap();
        assert_eq!(tx.version, FIREWALL_CONFIG_VERSION);
        assert_eq!(tx.netns, Netns::Current);
        let batch: Vec<&Step> = tx.steps.iter().collect();
        assert!(matches!(batch[0], Step::BeginBatch));
        assert!(batch.iter().any(|s| matches!(s, Step::DestroyTable { family: NftFamily::Ipv4 })));
        assert!(batch.iter().any(|s| matches!(s, Step::CreateTable { .. })));
        assert!(matches!(batch.last(), Some(Step::EndBatch)));
        // Destroy before create; End after everything.
        let i_destroy = batch.iter().position(|s| matches!(s, Step::DestroyTable { .. })).unwrap();
        let i_table = batch.iter().position(|s| matches!(s, Step::CreateTable { .. })).unwrap();
        let i_chain = batch.iter().position(|s| matches!(s, Step::CreateChain { .. })).unwrap();
        let i_rule = batch.iter().position(|s| matches!(s, Step::CreateRule { .. })).unwrap();
        assert!(i_destroy < i_table && i_table < i_chain && i_chain < i_rule);
    }

    #[test]
    fn a_stub_backend_applies_in_order() {
        struct Stub {
            seen: std::sync::Mutex<Vec<Step>>,
        }
        impl FirewallBackend for Stub {
            fn apply(&self, transaction: &FirewallTransaction) -> ApplyOutcome {
                self.seen.lock().unwrap().extend(transaction.steps.iter().cloned());
                ApplyOutcome::Applied
            }
        }
        let stub = Stub { seen: std::sync::Mutex::new(Vec::new()) };
        let tx = policy().transaction(Netns::File(42)).unwrap();
        assert_eq!(stub.apply(&tx), ApplyOutcome::Applied);
        assert_eq!(stub.seen.lock().unwrap().len(), tx.steps.len());
        assert_eq!(describe_apply(&ApplyOutcome::Applied), "applied");
    }

    #[test]
    fn empty_policy_has_no_tables_but_validates() {
        assert_eq!(FirewallPolicy::empty().validate(), Ok(()));
        assert_eq!(FirewallPolicy::empty().transaction(Netns::Current).unwrap().steps, Vec::new());
    }
}
