//! Typed nf_tables configuration for ctrs's networking.
//!
//! CTRS-11 defines the vocabulary only: `netlink.rs` remains the
//! implementation until CTRS-12 wires an adapter behind the `crabtables`
//! feature (same semantics, different encoder). The types here exist so the
//! configuration is *checkable* — ownership by construction (only the `ctrs`
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
    pub const CTRS: TableName = TableName(());
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
    /// `iifname|oifname <op> "ctrs*"`: a 4-byte prefix match.
    IifnamePrefix,
    OifnamePrefix,
    /// `oifname != "ctrs*"`: the forward filter's not-into-ctrs-bridges rule.
    OifnamePrefixNeq,
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
    /// `ct state & mask == 0` (the localnet guard's fresh-connection test).
    CtStateMaskedEqZero(u32),
    /// `ct status & mask == 0` (the relay and localnet guards' DNAT test).
    CtStatusMaskedEqZero(u32),
    /// `ip daddr == addr` (payload network header +16).
    DaddrV4([u8; 4]),
    /// `ip daddr <subnet>/<prefix>` (a masked payload match, not a set).
    DaddrV4Prefix { subnet: [u8; 4], prefix: u8 },
    /// `ip saddr == addr` (payload network header +12).
    SaddrV4([u8; 4]),
    /// `ip daddr & 255.0.0.0 != 127.0.0.0`.
    DaddrV4NotLoopback,
    /// `tcp dport == port`.
    TcpDport(u16),
    /// `udp dport == port`.
    UdpDport(u16),
    /// `ip6 saddr <subnet>/<prefix>` (NAT66 source match).
    PayloadSaddrV6 { subnet: [u8; 16], prefix: u8 },
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
                table: TableName::CTRS,
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
        // Only TableName::CTRS exists; there is no constructor for another.
        assert_eq!(TableName::CTRS, TableName(()));
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

/// The crabtables-backed implementation of [`FirewallBackend`] (CTRS-12),
/// selected by the `crabtables` cargo feature. Same semantics as `netlink.rs`:
/// one atomic batch per table, destroy-and-recreate, `NLM_F_APPEND` rules.
#[cfg(feature = "crabtables")]
pub mod crabtables_backend {
    use std::net::IpAddr;
    use std::os::fd::AsRawFd;

    use crabtables::expr::{Bitwise, Cmp, Expr, Fib};
    use crabtables::sys::NFTA_FIB_F_DADDR;
    use crabtables::{Batch, BitwiseOp, Chain, ChainType, CmpOp, CtKey, Family, FibResult, Policy, Reg, Table};

    use super::*;

    const TABLE: &str = "ctrs";
    /// RTN_LOCAL: a local address type from fib daddr.
    const RTN_LOCAL: u32 = 2;
    /// NF_NAT_RANGE_PROTO_RANDOM_FULLY.
    const MASQ_RANDOM_FULLY: u32 = 16;

    pub struct CrabtablesBackend;

    fn fam(f: NftFamily) -> Family {
        match f {
            NftFamily::Ipv4 => Family::Ipv4,
            NftFamily::Ipv6 => Family::Ipv6,
        }
    }

    fn nft_hook(h: Hook) -> crabtables::Hook {
        match h {
            Hook::Prerouting => crabtables::Hook::PREROUTING,
            Hook::Input => crabtables::Hook::INPUT,
            Hook::Forward => crabtables::Hook::FORWARD,
            Hook::LocalOut => crabtables::Hook::OUTPUT,
            Hook::Postrouting => crabtables::Hook::POSTROUTING,
        }
    }

    fn chain_type(t: ChainKind) -> ChainType {
        match t {
            ChainKind::Nat => ChainType::Nat,
            ChainKind::Filter => ChainType::Filter,
        }
    }

    fn apply_match(b: crabtables::RuleBuilder, m: &Match) -> crabtables::RuleBuilder {
        use crabtables::Field;
        match m {
            Match::IifnamePrefix => b.match_prefix(Field::IifName, "ctrs", 32),
            Match::OifnamePrefix => b.match_prefix(Field::OifName, "ctrs", 32),
            Match::OifnamePrefixNeq => {
                // `oifname != "ctrs*"`: the byte-aligned prefix match
                // truncated to 4 bytes, then compare not-equal.
                let load = Field::OifName.load(Reg::R1);
                let load = match load {
                    Expr::Payload(mut p) => {
                        p.len = 4;
                        Expr::Payload(p)
                    }
                    other => other,
                };
                b.expr(load).expr(Expr::Cmp(Cmp { sreg: Reg::R1, op: CmpOp::Neq, data: b"ctrs".to_vec() }))
            }
            Match::IifnameIs(n) => b.match_eq(Field::IifName, n.as_str()),
            Match::OifnameIs(n) => b.match_eq(Field::OifName, n.as_str()),
            Match::Iif(i) => b.match_eq(Field::Iif, *i),
            Match::Oif(i) => b.match_eq(Field::Oif, *i),
            Match::L4Proto(n) => b.match_eq(Field::L4Proto, *n),
            Match::CtStateMasked(mask) => b.ct_state(*mask),
            Match::CtStatusMasked(mask) => b.ct_status(*mask),
            Match::CtStateMaskedEqZero(mask) => b.match_masked(Field::CtState, *mask, 0u32),
            Match::CtStatusMaskedEqZero(mask) => b.match_masked(Field::Ct(CtKey::Status, None), *mask, 0u32),
            Match::DaddrV4(a) => b.match_eq(Field::IpDaddr, *a),
            Match::DaddrV4Prefix { subnet, prefix } => b.match_prefix(Field::IpDaddr, *subnet, *prefix as u32),
            Match::SaddrV4(a) => b.match_eq(Field::IpSaddr, *a),
            Match::DaddrV4NotLoopback => b
                .expr(Field::IpDaddr.load(Reg::R1))
                .expr(Expr::Bitwise(Bitwise {
                    sreg: Reg::R1,
                    dreg: Reg::R1,
                    len: 4,
                    op: Some(BitwiseOp::MaskXor),
                    mask: Some(vec![255, 0, 0, 0]),
                    xor: Some(vec![0; 4]),
                    data: None,
                }))
                .expr(Expr::Cmp(Cmp {
                    sreg: Reg::R1,
                    op: CmpOp::Neq,
                    data: vec![127, 0, 0, 0],
                })),
            Match::TcpDport(p) => b.match_eq(Field::TcpDport, *p),
            Match::UdpDport(p) => b.match_eq(Field::UdpDport, *p),
            Match::PayloadSaddrV6 { subnet, prefix } => b.match_prefix(Field::Ip6Saddr, *subnet, *prefix as u32),
            Match::FibDaddrTypeLocal => b
                .expr(Expr::Fib(Fib {
                    dreg: Reg::R1,
                    result: FibResult::AddrType,
                    flags: NFTA_FIB_F_DADDR,
                }))
                .expr(Expr::Cmp(Cmp {
                    sreg: Reg::R1,
                    op: CmpOp::Eq,
                    data: RTN_LOCAL.to_ne_bytes().to_vec(),
                })),
        }
    }

    fn apply_target(b: crabtables::RuleBuilder, target: &Target) -> crabtables::RuleBuilder {
        match target {
            Target::Masquerade { random_fully } => b.masquerade(if *random_fully { MASQ_RANDOM_FULLY } else { 0 }),
            Target::Dnat { to_ip, to_port } => b.dnat(IpAddr::V4((*to_ip).into()), Some(*to_port)),
            Target::Redirect { to } => b.redirect(Some(*to)),
            Target::Verdict(Verdict::Accept) => b.accept(),
            Target::Verdict(Verdict::Drop) => b.drop(),
        }
    }

    fn build(transaction: &FirewallTransaction) -> Batch {
        let mut batch = Batch::new();
        for step in &transaction.steps {
            match step {
                Step::BeginBatch | Step::EndBatch => {}
                Step::DestroyTable { family } => {
                    batch.destroy_table(fam(*family), TABLE);
                }
                Step::CreateTable { family } => {
                    batch.create_table(&Table::new(fam(*family), TABLE));
                }
                Step::CreateChain { family, chain } => {
                    let f = fam(*family);
                    let c = Chain::new(f, TABLE, chain.name.name())
                        .with_hook(chain_type(chain.name.kind()), nft_hook(chain.name.hook()), chain.name.priority())
                        .with_policy(match chain.policy {
                            Verdict::Accept => Policy::Accept,
                            Verdict::Drop => Policy::Drop,
                        });
                    batch.create_chain(&c);
                }
                Step::CreateRule { family, rule } => {
                    let f = fam(*family);
                    let mut b = crabtables::RuleBuilder::new(f, TABLE, rule.chain.name());
                    for m in &rule.matches {
                        b = apply_match(b, m);
                    }
                    b = apply_target(b, &rule.target);
                    batch.add_rule(&b.build());
                }
            }
        }
        batch
    }

    fn open_socket(netns: Netns) -> crabtables::Result<crabtables::Socket> {
        match netns {
            Netns::Current => crabtables::Socket::new(),
            Netns::File(fd) => {
                // Enter the namespace just long enough to create the socket,
                // which stays bound to it (as in Netlink::open_in).
                let own = std::fs::File::open("/proc/self/ns/net").map_err(crabtables::Error::from)?;
                // SAFETY: the caller hands us a valid netns fd; nothing about
                // thread state is disturbed and we restore it at once.
                if unsafe { libc::setns(fd, libc::CLONE_NEWNET) } != 0 {
                    return Err(crabtables::Error::from(std::io::Error::last_os_error()));
                }
                let r = crabtables::Socket::new();
                // SAFETY: as above; a failure here is not reported (the
                // socket already carries the namespace) but the error is
                // surfaced through the io path otherwise.
                let _ = unsafe { libc::setns(own.as_raw_fd(), libc::CLONE_NEWNET) };
                r
            }
        }
    }

    impl super::FirewallBackend for CrabtablesBackend {
        fn apply(&self, transaction: &FirewallTransaction) -> ApplyOutcome {
            let batch = build(transaction);
            match open_socket(transaction.netns).and_then(|mut s| s.commit(&batch)) {
                Ok(_) => ApplyOutcome::Applied,
                Err(crabtables::Error::OutcomeUnknown(u)) => ApplyOutcome::OutcomeUnknown { cause: u.cause().to_string() },
                Err(crabtables::Error::Batch(b)) => {
                    // Debug carries the full per-op error list; Display truncates.
                    let details = format!("{b:?}");
                    ApplyOutcome::RolledBack { cause: details }
                }
                // A send that never reached the kernel: the table is the previous one.
                Err(e) => ApplyOutcome::RolledBack { cause: e.to_string() },
            }
        }
    }
}

/// CTRS-13: apply the reference policy to the calling network namespace
/// through the crabtables adapter. Run only inside a scratch netns as root,
/// with nft(8) available to dump the result:
///
/// ```text
/// apk add --no-cache nftables iproute2 util-linux
/// unshare -n sh -c 'env CARGO_TEST_NOCAPTURE=1 /path/ctrs_init_test --ignored --nocapture crabtables_matches_reference'
/// nft -j list table ip ctrs > /w/cmp/adapter-v4.json   # same netns
/// ```
///
/// Never run this in the engine's VM root netns: it destroys and recreates
/// the `ctrs` table. The scratch netns dies with the unshare, taking the
/// tables with it.
#[cfg(all(test, feature = "crabtables"))]
mod compare {
    use super::*;

    /// The reference configuration as a policy, VM mode: a published TCP
    /// port (61000), host.docker.internal redirect, DNS redirect, per-bridge
    /// forward filter, both input guards; the IPv6 table holds NAT66 and a
    /// v6 forward filter.
    pub fn reference_policy() -> FirewallPolicy {
        let v4 = TableSpec {
            family: NftFamily::Ipv4,
            table: TableName::CTRS,
            chains: vec![
                ChainSpec::of(ChainName::Postrouting, Verdict::Accept),
                ChainSpec::of(ChainName::Prerouting, Verdict::Accept),
                ChainSpec::of(ChainName::Output, Verdict::Accept),
                ChainSpec::of(ChainName::Forward, Verdict::Accept),
                ChainSpec::of(ChainName::Input, Verdict::Accept),
            ],
            rules: vec![
                Rule { chain: ChainName::Postrouting, matches: vec![Match::Oif(2)], target: Target::Masquerade { random_fully: false } },
                Rule { chain: ChainName::Postrouting, matches: vec![Match::Iif(2), Match::SaddrV4([192, 168, 64, 1]), Match::OifnamePrefix], target: Target::Masquerade { random_fully: true } },
                Rule {
                    chain: ChainName::Prerouting,
                    matches: vec![Match::IifnamePrefix, Match::DaddrV4([198, 19, 248, 254]), Match::L4Proto(libc::IPPROTO_TCP as u8)],
                    target: Target::Redirect { to: 1026 },
                },
                Rule {
                    chain: ChainName::Prerouting,
                    matches: vec![Match::IifnamePrefix, Match::UdpDport(53), Match::DaddrV4([198, 19, 248, 254])],
                    target: Target::Redirect { to: 53 },
                },
                Rule {
                    chain: ChainName::Prerouting,
                    matches: vec![Match::Iif(2), Match::SaddrV4([192, 168, 64, 1]), Match::FibDaddrTypeLocal, Match::DaddrV4NotLoopback, Match::TcpDport(61000)],
                    target: Target::Dnat { to_ip: [172, 17, 0, 2], to_port: 80 },
                },
                Rule {
                    chain: ChainName::Output,
                    matches: vec![Match::DaddrV4([198, 19, 248, 254]), Match::L4Proto(libc::IPPROTO_TCP as u8)],
                    target: Target::Redirect { to: 1026 },
                },
                Rule { chain: ChainName::Forward, matches: vec![Match::OifnamePrefixNeq], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![Match::CtStateMasked(1 << 1 | 1 << 2)], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![Match::CtStatusMasked(1 << 5)], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![Match::IifnameIs("ctrs0".into()), Match::OifnameIs("ctrs0".into())], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![], target: Target::Verdict(Verdict::Drop) },
                Rule {
                    chain: ChainName::Input,
                    matches: vec![Match::IifnamePrefix, Match::DaddrV4Prefix { subnet: [127, 0, 0, 0], prefix: 8 }, Match::CtStateMaskedEqZero(1 << 1 | 1 << 2), Match::CtStatusMaskedEqZero(1 << 5)],
                    target: Target::Verdict(Verdict::Drop),
                },
                Rule { chain: ChainName::Input, matches: vec![Match::TcpDport(1026), Match::CtStatusMaskedEqZero(1 << 5)], target: Target::Verdict(Verdict::Drop) },
            ],
        };
        let mut fd00 = [0u8; 16];
        fd00[0] = 0xfd;
        fd00[1] = 0xde;
        fd00[2] = 0xed;
        let v6 = TableSpec {
            family: NftFamily::Ipv6,
            table: TableName::CTRS,
            chains: vec![ChainSpec::of(ChainName::Postrouting, Verdict::Accept), ChainSpec::of(ChainName::Forward, Verdict::Accept)],
            rules: vec![
                Rule { chain: ChainName::Postrouting, matches: vec![Match::PayloadSaddrV6 { subnet: fd00, prefix: 64 }, Match::OifnamePrefixNeq], target: Target::Masquerade { random_fully: false } },
                Rule { chain: ChainName::Forward, matches: vec![Match::OifnamePrefixNeq], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![Match::CtStateMasked(1 << 1 | 1 << 2)], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![Match::CtStatusMasked(1 << 5)], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![Match::IifnameIs("ctrs1".into()), Match::OifnameIs("ctrs1".into())], target: Target::Verdict(Verdict::Accept) },
                Rule { chain: ChainName::Forward, matches: vec![], target: Target::Verdict(Verdict::Drop) },
            ],
        };
        FirewallPolicy { version: FIREWALL_CONFIG_VERSION, tables: vec![v4, v6] }
    }

    #[test]
    #[ignore = "needs Linux root inside a scratch netns (see module docs); never the engine's netns"]
    fn crabtables_matches_reference() {
        // SAFETY: no preconditions; geteuid is always safe.
        if unsafe { libc::geteuid() } != 0 {
            panic!("needs root");
        }
        let policy = reference_policy();
        let tx = policy.transaction(Netns::Current).expect("reference policy validates");
        use super::FirewallBackend;
        let backend = crate::linux::firewall::crabtables_backend::CrabtablesBackend;
        let first = backend.apply(&tx);
        eprintln!("first apply: {first:?}");
        assert_eq!(first, ApplyOutcome::Applied);
        let second = backend.apply(&tx);
        eprintln!("second apply: {second:?}");
        assert_eq!(second, ApplyOutcome::Applied, "re-apply must destroy-and-recreate cleanly");
        eprintln!("crabtables applied the reference policy twice; tables left for nft dump");
    }
}
