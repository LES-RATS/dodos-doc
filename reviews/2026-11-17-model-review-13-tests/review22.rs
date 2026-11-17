//! The attacks of the twelfth model review (the final review of pass 22).
//! Each test reaches a state a user's calls, the values of the machine or a
//! faulty kernel's own rings can reach. Nothing here is part of the pull
//! request; the file lives in the reviewer's copy alone.

use super::*;
use crate::rings::Body;
use crate::{Message, Range, Transfer};
use dodos_abi::{Header, NodeMessage, RingHeader, START_SLOT_MAILBOX};

const REPLY: u32 = 100;
const OBJ: u32 = 101;
const GOT: u32 = 110;

fn recv(first: u32) -> Syscall {
    Syscall::Recv {
        endpoint: s(START_SLOT_MAILBOX),
        reply: s(REPLY),
        range: Range {
            first: s(first),
            count: 4,
        },
        wait: 0,
    }
}

fn rights() -> u32 {
    Rights::READ
        .union(Rights::WRITE)
        .union(Rights::SEND)
        .union(Rights::DERIVE)
        .bits()
}

/// Three nodes; node 0 sends node 1 one frame (slot `OBJ`) with `derive`;
/// node 1 receives it in slot `GOT`; settled.
fn granted() -> S {
    let mut m = S::on(&machine(Arch::X86_64, 3, &[&[0], &[1], &[2]]));
    for node in [0, 1] {
        let reply = m.retype(node, ObjectKind::Reply, 0, REPLY);
        m.ok(node, reply);
    }
    let frame = m.retype(0, ObjectKind::Frame, 1, OBJ);
    m.ok(0, frame);
    assert_eq!(m.call(1, recv(GOT)), WAITS);
    let message = Message {
        label: 7,
        flags: 0,
        words: vec![7],
        caps: vec![Transfer::Derive(s(OBJ), rights())],
        marks: 0,
    };
    let call = Syscall::NodeSend {
        node: node_cap(1),
        message,
        doorbell: SlotAddr::NONE,
    };
    assert_eq!(m.call(0, call), WAITS);
    m.settle();
    m
}

/// A message whose header names `sender`, as a faulty kernel writes it on
/// its own ring with plain stores.
fn forged(
    m: &S,
    kind: NodeMessage,
    sender: u16,
    to: u16,
    credit: Option<(u8, u32)>,
    body: Body,
) -> crate::rings::Message {
    let t = m.sys.canonical();
    let header = RingHeader::new(
        kind,
        body.entries() as u8,
        (sender, t.generation(sender)),
        t.generation(to),
        credit,
    );
    crate::rings::Message { header, body }
}

// A. A freed grant leaves its anchor in the kernel space; the index it
// leaves free is reused before the removal that reached it removed the
// anchor.

#[test]
fn a_grant_index_reused_after_a_revocation_overwrites_the_anchor_of_the_old_one() {
    let mut m = granted();
    // Node 1 maps the frame: the grant's use entry counts a leaf, so the
    // revocation cannot free the entry at once and must ask the holder.
    let map = Syscall::ASpaceMap(crate::Map {
        space: s(dodos_abi::START_SLOT_ASPACE),
        frame: s(GOT),
        untyped: SlotAddr::NONE,
        address: 1 << 30,
        first: 0,
        count: 1,
        rights: Rights::READ.union(Rights::WRITE).bits(),
    });
    assert_eq!(m.call(1, map), DONE);
    let grant = m.sys.node(0).grant_entries()[0].0;
    m.ok(0, place_first(0, 0));
    let other = m.thread_on(0, 300, 0);
    // Node 0 revokes its frame: the removal reaches the grant's anchor, a
    // `Revoke` goes to node 1, and the thread waits.
    assert_eq!(m.call(0, Syscall::CapRevoke(s(OBJ))), WAITS);
    m.run(20 * MS);
    // Node 1 removed its root and answered: the grant entry is freed, the
    // anchor stays in the kernel space, and the revoking thread has not run
    // the removal step that removes it.
    assert!(!m.sys.canonical().grants[0].contains_key(&grant));
    let anchor = m
        .sys
        .node(0)
        .anchor(grant)
        .expect("the anchor of the freed grant");
    // A second thread of node 0 grants the same frame again: the index is
    // free, so its anchor is written over the old one.
    let message = Message {
        label: 8,
        flags: 0,
        words: vec![8],
        caps: vec![Transfer::Derive(s(OBJ), rights())],
        marks: 0,
    };
    let call = Syscall::NodeSend {
        node: node_cap(2),
        message,
        doorbell: SlotAddr::NONE,
    };
    let outcome = m.call_by(0, other, call);
    assert!(!m.sys.node(0).caps.contains_key(&anchor) || outcome == DONE);
}

// B. The step counts entries, and a message that straddles the sixteenth
// entry carries it past the sixteen the contract allows.

#[test]
fn one_interrupt_serves_sixteen_entries_and_not_more() {
    let mut m = S::two();
    let reply = m.retype(0, ObjectKind::Reply, 0, REPLY);
    m.ok(0, reply);
    for i in 0..4u64 {
        // A `Send` of five entries: 3 + 30 words.
        let body = Body::Send {
            header: Header::new(7, 30, 0, 0).expect("a header"),
            stamp: (0, 0),
            grants: vec![],
            words: vec![i; 30],
        };
        let send = forged(&m, NodeMessage::Send, 1, 0, Some((16, i as u32 + 1)), body);
        assert_eq!(send.body.entries(), 5);
        m.sys.inject(1, 0, send);
    }
    let start = m.sys.canonical().beacons[0].consumed[1].1;
    m.sys.fire(crate::system::Event::Ipi { node: 0, core: 0 });
    let served = m.sys.canonical().beacons[0].consumed[1].1 - start;
    assert_eq!(served, dodos_abi::RING_USER_STEP);
}

// C. The values of the machine: a machine the start-up accepts must boot,
// one it does not must be refused, and neither may panic.

#[test]
fn random_values_of_the_machine_are_refused_or_accepted_but_never_panic() {
    let mut seed = 0x2026_1117_0000_0001u64;
    let mut next = move || {
        seed = seed
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        seed >> 33
    };
    for round in 0..300 {
        let mut machine = Machine::example();
        let chunk = machine.geometry.chunk();
        match round % 6 {
            0 => machine.phys_bits = 30 + (next() % 16) as u32,
            1 => machine.io_width = 20 + (next() % 50) as u32,
            2 => machine.iommus[0].domains = (next() % 70_000) as u32,
            3 => {
                // An overlapping or wrapping run of memory.
                let base = 1u64 << (next() % 40);
                machine.memory[1].base = base;
                machine.memory[1].len = (next() % 4) * chunk;
            }
            4 => {
                machine.crash.0 = (next() % 8) * chunk + (next() % 3);
                machine.crash.1 = Some((next() % 8) * chunk);
            }
            _ => {
                machine.cores[0].kind = (next() % 4) as u16;
                machine.boot_nodes = Some((2, vec![(next() % 1100, 1), (0, 2)]));
            }
        }
        let machine = machine.clone();
        let booted = std::panic::catch_unwind(move || crate::System::boot(&machine).is_ok());
        assert!(booted.is_ok(), "round {round} panicked");
    }
}

// D. Two values of the machine that the contract's list refuses: a kept
// range past MAXPHYADDR, and a crash area overlapping a kept range.

#[test]
fn a_kept_range_past_maxphyaddr_or_a_crash_area_over_a_kept_range() {
    // MAXPHYADDR 40 and a kept range at 2^45: the contract refuses it
    // ("MAXPHYADDR ... below the end of a usable or kept range").
    let mut machine = Machine::example();
    let chunk = machine.geometry.chunk();
    machine.phys_bits = 40;
    machine.memory.retain(|r| r.base + r.len <= 1 << 40);
    machine.kept = vec![(1 << 45, chunk)];
    let refused = crate::boot::Refusal::MachineValues;
    let kept_past = std::panic::catch_unwind(|| Model::boot(&machine).map(|_| ()));
    assert!(matches!(kept_past, Ok(Err(ref r)) if *r == refused), "{kept_past:?}");
    // A crash area overlapping a kept range: also refused by the contract.
    let mut machine = Machine::example();
    let crash = machine.crash.0;
    machine.kept = vec![(crash, chunk)];
    let overlap = std::panic::catch_unwind(|| Model::boot(&machine).map(|_| ()));
    assert!(
        matches!(overlap, Ok(Err(ref r)) if *r == refused),
        "{overlap:?}"
    );
}

#[test]
fn a_crash_area_over_a_kept_range_is_refused() {
    let mut machine = Machine::example();
    let chunk = machine.geometry.chunk();
    let crash = machine.crash.0;
    machine.kept = vec![(crash, chunk)];
    let outcome = std::panic::catch_unwind(|| Model::boot(&machine).map(|_| ()));
    assert!(
        matches!(outcome, Ok(Err(crate::boot::Refusal::MachineValues))),
        "{outcome:?}"
    );
}

// E. A faulty kernel writes its own words of the living part at random: the
// check must report, never panic (nor the model, when it steps after).

#[test]
fn random_words_of_the_living_part_never_panic_the_check() {
    let mut m = S::two();
    // Grant first, so that the grant and use tables hold entries to spoil.
    let mut seed = 0x5EED_2211_0000_0007u64;
    let mut next = move || {
        seed = seed
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        seed >> 31
    };
    for round in 0..300 {
        let base = m.sys.canonical().clone();
        let mut table = base.clone();
        let pick = |n: u64, next: &mut dyn FnMut() -> u64| (next() % n) as usize;
        match round % 5 {
            0 => {
                let index = pick(table.owners.len() as u64, &mut next);
                std::sync::Arc::make_mut(&mut table.owners)[index] = next();
            }
            1 => {
                let gsi = (next() % 32) as u32;
                table.lines.insert(gsi, next());
                table.identifiers.insert(gsi, next());
                table.attach.insert(gsi, next());
            }
            2 => {
                let index = pick(table.devices.len() as u64, &mut next);
                let mut entry = dodos_abi::DeviceEntry::unused();
                entry.owner = dodos_abi::Ownership::from_raw(next())
                    .unwrap_or_else(dodos_abi::Ownership::none);
                entry.range = next();
                std::sync::Arc::make_mut(&mut table.devices)[index] = entry;
            }
            3 => {
                let node = pick(table.uses.len() as u64, &mut next);
                let mut entry = crate::table::UseEntry {
                    granter: (next() % 2) as u16,
                    grant: (next() % 4096) as u16,
                    serial: next() as u32,
                    generation: next() as u32,
                    root: crate::ObjId((next() % 8) as u32),
                    leaves: next() % 3,
                    release_pending: next() % 2 == 0,
                    signal_pending: next() % 2 == 0,
                };
                entry.leaves = next() % 3;
                table.uses[node].insert((next() % 64) as u16, entry);
            }
            _ => {
                let node = pick(table.grants.len() as u64, &mut next);
                let mut entry = crate::table::GrantEntry {
                    anchor: crate::table::Anchor::test(),
                    grantee: (next() % 2) as u16,
                    generation: next() as u32,
                    serial: next() as u32,
                    state: crate::table::GrantState::Live,
                    use_index: Some((next() % 64) as u16),
                    answered: next() % 2 == 0,
                    doorbell: None,
                };
                entry.state = crate::table::GrantState::Pinned;
                table.grants[node].insert((next() % 64) as u16, entry);
            }
        }
        m.sys.edit_table(move |t| *t = table);
        let checked = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| m.sys.check()));
        assert!(checked.is_ok(), "round {round}");
        m.sys.edit_table(move |t| *t = base);
    }
}

// F. After such a fault the model keeps stepping: the events it offers, the
// answers it gives, must not panic on a body the check refuses.

#[test]
fn the_model_never_panics_after_a_faulty_kernel_spoils_its_table() {
    use crate::system::Rng;
    let mut m = S::two();
    let mut rng = Rng(0x2211_5EED);
    let base = m.sys.canonical().clone();
    let mut seed = 0x2211_5EED_0000_0001u64;
    let mut next = move || {
        seed = seed
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        seed >> 31
    };
    for round in 0..120 {
        let mut table = base.clone();
        let index = (next() % table.owners.len() as u64) as usize;
        std::sync::Arc::make_mut(&mut table.owners)[index] = next();
        let gsi = (next() % 32) as u32;
        table.lines.insert(gsi, next());
        table.identifiers.insert(gsi, next());
        let node = (next() % table.uses.len() as u64) as usize;
        table.uses[node].insert(
            (next() % 64) as u16,
            crate::table::UseEntry {
                granter: (next() % 2) as u16,
                grant: (next() % 4096) as u16,
                serial: next() as u32,
                generation: next() as u32,
                root: crate::ObjId((next() % 8) as u32),
                leaves: next() % 3,
                release_pending: next() % 2 == 0,
                signal_pending: next() % 2 == 0,
            },
        );
        m.sys.edit_table(move |t| *t = table);
        let stepped = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            for _ in 0..8 {
                if !m.sys.step(&mut rng) {
                    break;
                }
            }
            m.sys.check();
        }));
        assert!(stepped.is_ok(), "round {round}");
        let restore = base.clone();
        m.sys.edit_table(move |t| *t = restore);
    }
}

// G. What the continuation test sees: the area's sequence before the restart
// and after it, and whether the ring's last entry still names it.
#[test]
fn what_the_continuation_test_sees() {
    let mut next = 0;
    use super::units::three;
    let mut m = three();
    let kill = Syscall::NodeStop {
        node: node_cap(1),
        mode: dodos_abi::NODE_STOP_KILL,
        core: 0,
    };
    m.ok(2, kill);
    m.run(30 * MS);
    assert_eq!(m.state(1), MemberState::Dead);
    m.sys.edit_table(|t| {
        next = std::sync::Arc::make_mut(&mut t.crash).areas[1].next_kernel
    });
    let fresh = Syscall::NodeStart {
        node: node_cap(1),
        mode: dodos_abi::NODE_START_FRESH,
        image: 0,
        module: 0,
        window: 0,
        mask: 0b10,
    };
    m.ok(2, fresh);
    m.run(5 * MS);
    assert_eq!(m.state(1), MemberState::Live);
    let after = m.sys.canonical().crash.areas[1].next_kernel;
    eprintln!("before: {next}, after: {after}");
    assert!(after >= next);
}
