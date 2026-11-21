use std::io;

use super::{CT_ESTABLISHED, CT_RELATED, Msg, NFNL_MSG_BATCH_BEGIN, NFNL_MSG_BATCH_END, NFNL_SUBSYS_NFTABLES, NFT_MSG_NEWCHAIN, NFT_MSG_NEWRULE, NLM_F_ACK, NLM_F_CREATE, Netlink, nfgen, nft_in, nl_raw};

const NFT_MSG_GETCHAIN: u16 = 4;
const NFT_MSG_GETRULE: u16 = 7;
const NFT_MSG_DELRULE: u16 = 8;
const XT_CONNTRACK_V3_SIZE: usize = 168;
const XT_CONNTRACK_MATCH_FLAGS: usize = 146;
const XT_CONNTRACK_STATE_MASK: usize = 150;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Direction {
    Outbound,
    Return,
}

impl Direction {
    fn comment(self) -> &'static str {
        match self {
            Self::Outbound => "ctrs-linux-forward-outbound",
            Self::Return => "ctrs-linux-forward-return",
        }
    }

    fn userdata(self) -> Vec<u8> {
        let mut data = vec![0, (self.comment().len() + 1) as u8];
        data.extend_from_slice(self.comment().as_bytes());
        data.push(0);
        data
    }
}

#[derive(Debug)]
struct Chain {
    family: u8,
    name: String,
    forward_hook: bool,
    drop_policy: bool,
}

#[derive(Debug)]
struct Rule {
    family: u8,
    chain: String,
    handle: u64,
    owner: Option<Direction>,
}

#[derive(Debug, PartialEq, Eq)]
enum Action {
    Delete { family: u8, chain: String, handle: u64 },
    Insert { family: u8, chain: String, direction: Direction },
}

fn plan(chains: &[Chain], rules: &[Rule], enable: bool) -> Vec<Action> {
    let mut actions = Vec::new();
    for family in [libc::NFPROTO_IPV4 as u8, libc::NFPROTO_IPV6 as u8, libc::NFPROTO_INET as u8] {
        let forward = chains.iter().find(|c| c.family == family && c.name == "FORWARD" && c.forward_hook);
        let target = if enable {
            forward.and_then(|c| {
                chains.iter().find(|c| c.family == family && c.name == "DOCKER-USER").map(|c| c.name.as_str()).or_else(|| c.drop_policy.then_some("FORWARD"))
            })
        } else {
            None
        };
        let owned: Vec<_> = rules.iter().filter(|r| r.family == family && r.owner.is_some()).collect();
        if let Some(target) = target {
            let head: Vec<_> = rules.iter().filter(|r| r.family == family && r.chain == target).take(2).collect();
            if owned.len() == 2 && head.len() == 2 && head[0].owner == Some(Direction::Outbound) && head[1].owner == Some(Direction::Return) {
                continue;
            }
        }
        actions.extend(owned.iter().map(|r| Action::Delete { family, chain: r.chain.clone(), handle: r.handle }));
        if let Some(chain) = target {
            for direction in [Direction::Return, Direction::Outbound] {
                actions.push(Action::Insert { family, chain: chain.to_owned(), direction });
            }
        }
    }
    actions
}

fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "invalid host firewall dump")
}

fn attributes(mut bytes: &[u8]) -> io::Result<Vec<(u16, &[u8])>> {
    let mut out = Vec::new();
    while !bytes.is_empty() {
        if bytes.len() < 4 {
            return Err(invalid());
        }
        let len = u16::from_ne_bytes(bytes[..2].try_into().expect("2")) as usize;
        let ty = u16::from_ne_bytes(bytes[2..4].try_into().expect("2")) & 0x3fff;
        let next = (len + 3) & !3;
        if len < 4 || next > bytes.len() {
            return Err(invalid());
        }
        out.push((ty, &bytes[4..len]));
        bytes = &bytes[next..];
    }
    Ok(out)
}

fn get<'a>(attrs: &[(u16, &'a [u8])], ty: u16) -> Option<&'a [u8]> {
    attrs.iter().find(|(t, _)| *t == ty).map(|(_, data)| *data)
}

fn string(bytes: &[u8]) -> io::Result<&str> {
    std::str::from_utf8(bytes.strip_suffix(&[0]).ok_or_else(invalid)?).map_err(|_| invalid())
}

fn parse_dump(bytes: &[u8], kind: u16, chains: &mut Vec<Chain>, rules: &mut Vec<Rule>) -> io::Result<()> {
    let mut offset = 0;
    while offset < bytes.len() {
        let message = bytes.get(offset..offset + 16).ok_or_else(invalid)?;
        let len = u32::from_ne_bytes(message[..4].try_into().expect("4")) as usize;
        let ty = u16::from_ne_bytes(message[4..6].try_into().expect("2"));
        if len < 16 {
            return Err(invalid());
        }
        let payload = bytes.get(offset + 16..offset + len).ok_or_else(invalid)?;
        offset += (len + 3) & !3;
        if ty != ((NFNL_SUBSYS_NFTABLES << 8) | kind) {
            continue;
        }
        let family = *payload.first().ok_or_else(invalid)?;
        let attrs = attributes(payload.get(4..).ok_or_else(invalid)?)?;
        if get(&attrs, 1).map(string).transpose()? != Some("filter") {
            continue;
        }
        if kind == NFT_MSG_NEWCHAIN {
            let name = string(get(&attrs, 3).ok_or_else(invalid)?)?;
            if !matches!(name, "FORWARD" | "DOCKER-USER") {
                continue;
            }
            let hook = get(&attrs, 4).map(attributes).transpose()?.unwrap_or_default();
            chains.push(Chain {
                family,
                name: name.to_owned(),
                forward_hook: get(&hook, 1) == Some(2u32.to_be_bytes().as_slice()),
                drop_policy: get(&attrs, 5) == Some(0u32.to_be_bytes().as_slice()),
            });
        } else {
            let chain = string(get(&attrs, 2).ok_or_else(invalid)?)?;
            if !matches!(chain, "FORWARD" | "DOCKER-USER") {
                continue;
            }
            let handle = u64::from_be_bytes(get(&attrs, 3).ok_or_else(invalid)?.try_into().map_err(|_| invalid())?);
            let owner = [Direction::Outbound, Direction::Return].into_iter().find(|d| get(&attrs, 7) == Some(d.userdata().as_slice()));
            rules.push(Rule { family, chain: chain.to_owned(), handle, owner });
        }
    }
    Ok(())
}

fn insert(family: u8, chain: &str, direction: Direction) -> Msg {
    let mut rule = nft_in(family, NFT_MSG_NEWRULE, NLM_F_ACK | NLM_F_CREATE);
    rule.attr_str(1, "filter").attr_str(2, chain).attr(7, &direction.userdata());
    rule.nest(4);
    let key = if direction == Direction::Outbound { 6 } else { 7 };
    rule.nest(1).attr_str(1, "meta").nest(2).attr_be32(1, 1).attr_be32(2, key).end().end();
    rule.nest(1).attr_str(1, "cmp").nest(2).attr_be32(1, 1).attr_be32(2, 0).nest(3).attr(1, b"ctrs").end().end().end();
    if direction == Direction::Return {
        if family == libc::NFPROTO_INET as u8 {
            rule.nest(1).attr_str(1, "ct").nest(2).attr_be32(1, 1).attr_be32(2, 0).end().end();
            rule.nest(1).attr_str(1, "bitwise").nest(2).attr_be32(1, 1).attr_be32(2, 1).attr_be32(3, 4);
            rule.nest(4).attr(1, &(CT_ESTABLISHED | CT_RELATED).to_ne_bytes()).end().nest(5).attr(1, &0u32.to_ne_bytes()).end().end().end();
            rule.nest(1).attr_str(1, "cmp").nest(2).attr_be32(1, 1).attr_be32(2, 1).nest(3).attr(1, &0u32.to_ne_bytes()).end().end().end();
        } else {
            let mut info = [0u8; XT_CONNTRACK_V3_SIZE];
            info[XT_CONNTRACK_MATCH_FLAGS..XT_CONNTRACK_MATCH_FLAGS + 2].copy_from_slice(&1u16.to_ne_bytes());
            info[XT_CONNTRACK_STATE_MASK..XT_CONNTRACK_STATE_MASK + 2].copy_from_slice(&((CT_ESTABLISHED | CT_RELATED) as u16).to_ne_bytes());
            rule.nest(1).attr_str(1, "match").nest(2).attr_str(1, "conntrack").attr_be32(2, 3).attr(3, &info).end().end();
        }
    }
    rule.nest(1).attr_str(1, "counter").nest(2).end().end();
    rule.nest(1).attr_str(1, "immediate").nest(2).attr_be32(1, 0).nest(2).nest(2).attr_be32(1, libc::NF_ACCEPT as u32).end().end().end().end();
    rule.end();
    rule
}

pub fn reconcile(enable: bool) -> io::Result<()> {
    let mut chains = Vec::new();
    let mut rules = Vec::new();
    for (request, response) in [(NFT_MSG_GETCHAIN, NFT_MSG_NEWCHAIN), (NFT_MSG_GETRULE, NFT_MSG_NEWRULE)] {
        let bytes = nl_raw(libc::NETLINK_NETFILTER, (NFNL_SUBSYS_NFTABLES << 8) | request, &nfgen(libc::NFPROTO_UNSPEC as u8, 0))?;
        parse_dump(&bytes, response, &mut chains, &mut rules)?;
    }
    let actions = plan(&chains, &rules, enable);
    if actions.is_empty() {
        return Ok(());
    }
    let mut begin = Msg::new(NFNL_MSG_BATCH_BEGIN, 0);
    begin.raw(&nfgen(libc::NFPROTO_UNSPEC as u8, NFNL_SUBSYS_NFTABLES));
    let mut messages = vec![begin];
    for action in actions {
        messages.push(match action {
            Action::Delete { family, chain, handle } => {
                let mut rule = nft_in(family, NFT_MSG_DELRULE, NLM_F_ACK);
                rule.attr_str(1, "filter").attr_str(2, &chain).attr(3, &handle.to_be_bytes());
                rule
            }
            Action::Insert { family, chain, direction } => insert(family, &chain, direction),
        });
    }
    let mut end = Msg::new(NFNL_MSG_BATCH_END, 0);
    end.raw(&nfgen(libc::NFPROTO_UNSPEC as u8, NFNL_SUBSYS_NFTABLES));
    messages.push(end);
    Netlink::open(libc::NETLINK_NETFILTER)?.request(&mut messages)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chain(name: &str, drop_policy: bool) -> Chain {
        Chain { family: libc::NFPROTO_IPV4 as u8, name: name.to_owned(), forward_hook: name == "FORWARD", drop_policy }
    }

    fn rule(chain: &str, handle: u64, owner: Option<Direction>) -> Rule {
        Rule { family: libc::NFPROTO_IPV4 as u8, chain: chain.to_owned(), handle, owner }
    }

    fn insertions(chain: &str) -> Vec<Action> {
        [Direction::Return, Direction::Outbound].into_iter().map(|direction| Action::Insert { family: libc::NFPROTO_IPV4 as u8, chain: chain.to_owned(), direction }).collect()
    }

    #[test]
    fn docker_hook_is_preferred_even_with_accept_policy() {
        for drop_policy in [false, true] {
            assert_eq!(plan(&[chain("FORWARD", drop_policy), chain("DOCKER-USER", false)], &[], true), insertions("DOCKER-USER"));
        }
    }

    #[test]
    fn fallback_requires_drop_policy_and_forward_hook() {
        assert_eq!(plan(&[chain("FORWARD", true)], &[], true), insertions("FORWARD"));
        assert!(plan(&[chain("FORWARD", false)], &[], true).is_empty());
        let mut c = chain("FORWARD", true);
        c.forward_hook = false;
        assert!(plan(&[c], &[], true).is_empty());
    }

    #[test]
    fn absent_chains_are_untouched() {
        assert!(plan(&[], &[], true).is_empty());
        assert!(plan(&[], &[], false).is_empty());
        assert!(plan(&[chain("DOCKER-USER", false)], &[], true).is_empty());
    }

    #[test]
    fn restart_is_idempotent_and_shutdown_deletes_only_owned_handles() {
        let chains = [chain("FORWARD", true), chain("DOCKER-USER", false)];
        let rules = [rule("DOCKER-USER", 4, Some(Direction::Outbound)), rule("DOCKER-USER", 8, Some(Direction::Return)), rule("DOCKER-USER", 10, None), rule("FORWARD", 20, None)];
        assert!(plan(&chains, &rules, true).is_empty());
        assert_eq!(plan(&chains, &rules, false), vec![Action::Delete { family: 2, chain: "DOCKER-USER".into(), handle: 4 }, Action::Delete { family: 2, chain: "DOCKER-USER".into(), handle: 8 }]);
        assert!(plan(&chains, &rules[2..], false).is_empty());
    }

    #[test]
    fn partial_duplicate_or_displaced_rules_are_reconciled_at_the_top() {
        let chains = [chain("FORWARD", true), chain("DOCKER-USER", false)];
        for rules in [vec![rule("DOCKER-USER", 8, Some(Direction::Return))], vec![rule("DOCKER-USER", 2, None), rule("DOCKER-USER", 4, Some(Direction::Outbound)), rule("DOCKER-USER", 8, Some(Direction::Return))], vec![rule("DOCKER-USER", 4, Some(Direction::Outbound)), rule("DOCKER-USER", 8, Some(Direction::Return)), rule("FORWARD", 16, Some(Direction::Outbound))]] {
            let actions = plan(&chains, &rules, true);
            assert_eq!(&actions[actions.len() - 2..], insertions("DOCKER-USER"));
            assert_eq!(actions.len() - 2, rules.iter().filter(|r| r.owner.is_some()).count());
        }
    }

    #[test]
    fn stale_fallback_moves_to_docker_hook_and_is_removed_when_no_longer_needed() {
        let rules = [rule("FORWARD", 1, Some(Direction::Outbound)), rule("FORWARD", 2, Some(Direction::Return))];
        let actions = plan(&[chain("FORWARD", true), chain("DOCKER-USER", false)], &rules, true);
        assert_eq!(&actions[2..], insertions("DOCKER-USER"));
        let actions = plan(&[chain("FORWARD", false)], &rules, true);
        assert_eq!(actions.len(), 2);
        assert!(actions.iter().all(|a| matches!(a, Action::Delete { .. })));
    }

    #[test]
    fn ipv4_ipv6_and_inet_are_planned_independently() {
        let chains: Vec<_> = [2, 10, 1].into_iter().map(|family| Chain { family, ..chain("FORWARD", true) }).collect();
        let actions = plan(&chains, &[], true);
        assert_eq!(actions.len(), 6);
        for (pair, family) in actions.chunks(2).zip([2, 10, 1]) {
            assert!(pair.iter().all(|a| matches!(a, Action::Insert { family: f, .. } if *f == family)));
        }
    }

    #[test]
    fn dump_parser_recognizes_only_exact_owner_comments() {
        let mut messages = Vec::new();
        let mut c = nft_in(2, NFT_MSG_NEWCHAIN, 0);
        c.attr_str(1, "filter").attr_str(3, "FORWARD").attr_be32(5, 0).nest(4).attr_be32(1, 2).end();
        messages.extend_from_slice(c.finish(1));
        let mut r = insert(2, "FORWARD", Direction::Outbound);
        r.attr(3, &42u64.to_be_bytes());
        let mut chains = Vec::new();
        let mut rules = Vec::new();
        parse_dump(&messages, NFT_MSG_NEWCHAIN, &mut chains, &mut rules).unwrap();
        parse_dump(r.finish(2), NFT_MSG_NEWRULE, &mut chains, &mut rules).unwrap();
        assert!(chains[0].forward_hook && chains[0].drop_policy);
        assert_eq!(rules[0].owner, Some(Direction::Outbound));
        assert_eq!(rules[0].handle, 42);
        let mut other = nft_in(2, NFT_MSG_NEWRULE, 0);
        other.attr_str(1, "filter").attr_str(2, "FORWARD").attr(3, &43u64.to_be_bytes()).attr(7, b"ctrs-linux-forward-outbound");
        parse_dump(other.finish(3), NFT_MSG_NEWRULE, &mut chains, &mut rules).unwrap();
        assert_eq!(rules[1].owner, None);
    }

    #[test]
    fn malformed_dumps_are_errors_not_empty_plans() {
        for bytes in [&[0u8][..], &[0u8; 16][..], &[255u8; 20][..]] {
            assert!(parse_dump(bytes, NFT_MSG_NEWCHAIN, &mut Vec::new(), &mut Vec::new()).is_err());
        }
        assert!(attributes(&[3, 0, 1, 0]).is_err());
        assert!(attributes(&[8, 0, 1, 0]).is_err());
        assert!(string(b"not-terminated").is_err());
    }

    #[test]
    fn accepts_only_ctrs_prefix_and_requires_conntrack_for_return() {
        for (family, direction) in [2, 10, 1].into_iter().flat_map(|family| [Direction::Outbound, Direction::Return].map(|d| (family, d))) {
            let r = insert(family, "DOCKER-USER", direction);
            let top = attributes(&r.buf[20..]).unwrap();
            let expressions = attributes(get(&top, 4).unwrap()).unwrap();
            let decoded: Vec<_> = expressions.iter().map(|(_, e)| attributes(e).unwrap()).collect();
            let names: Vec<_> = decoded.iter().map(|a| string(get(a, 1).unwrap()).unwrap()).collect();
            let expected = if direction == Direction::Outbound {
                vec!["meta", "cmp", "counter", "immediate"]
            } else if family == libc::NFPROTO_INET as u8 {
                vec!["meta", "cmp", "ct", "bitwise", "cmp", "counter", "immediate"]
            } else {
                vec!["meta", "cmp", "match", "counter", "immediate"]
            };
            assert_eq!(names, expected);
            let meta = attributes(get(&decoded[0], 2).unwrap()).unwrap();
            let key: u32 = if direction == Direction::Outbound { 6 } else { 7 };
            assert_eq!(get(&meta, 2).unwrap(), key.to_be_bytes());
            let cmp = attributes(get(&decoded[1], 2).unwrap()).unwrap();
            let data = attributes(get(&cmp, 3).unwrap()).unwrap();
            assert_eq!(get(&data, 1).unwrap(), b"ctrs");
            if direction == Direction::Return && family == libc::NFPROTO_INET as u8 {
                let bitwise = attributes(get(&decoded[3], 2).unwrap()).unwrap();
                let mask = attributes(get(&bitwise, 4).unwrap()).unwrap();
                assert_eq!(get(&mask, 1).unwrap(), (CT_ESTABLISHED | CT_RELATED).to_ne_bytes());
                let cmp = attributes(get(&decoded[4], 2).unwrap()).unwrap();
                assert_eq!(get(&cmp, 2).unwrap(), 1u32.to_be_bytes());
            } else if direction == Direction::Return {
                let conntrack = attributes(get(&decoded[2], 2).unwrap()).unwrap();
                assert_eq!(string(get(&conntrack, 1).unwrap()).unwrap(), "conntrack");
                assert_eq!(get(&conntrack, 2).unwrap(), 3u32.to_be_bytes());
                let info = get(&conntrack, 3).unwrap();
                assert_eq!(info.len(), 168);
                assert_eq!(&info[146..148], &1u16.to_ne_bytes());
                assert_eq!(&info[148..150], &[0, 0]);
                assert_eq!(&info[150..152], &((CT_ESTABLISHED | CT_RELATED) as u16).to_ne_bytes());
            }
            let verdict = attributes(get(decoded.last().unwrap(), 2).unwrap()).unwrap();
            let data = attributes(get(&verdict, 2).unwrap()).unwrap();
            let verdict = attributes(get(&data, 2).unwrap()).unwrap();
            assert_eq!(get(&verdict, 1).unwrap(), (libc::NF_ACCEPT as u32).to_be_bytes());
            let flags = u16::from_ne_bytes(r.buf[6..8].try_into().unwrap());
            assert_eq!(flags & 0x800, 0);
        }
    }
}
