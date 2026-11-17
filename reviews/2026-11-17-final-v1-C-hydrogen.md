# Review report: lot C

Repository: `/private/tmp/dodos-pr3-final` (branch `model`, head `6312868`).

---

## `model/src/boot.rs`

### Finding 1 — Should be fixed: `start_page_bytes` hardcodes stale sizes for `StartBootTimes` and `StartMachine` (and overcounts `Kept` when there is no previous crash)

- **File and line**: `model/src/boot.rs:568, 577, 585, 591`
- **Code**:
```rust
    let kept = machine.kept.len() as u64 + 3 + machine.feedback.len() as u64;
...
        40,
...
        80,
...
        56 + 4 * 2,
```
- **What is wrong**:
  - Line 577 budgets `40` bytes for `StartBootTimes` (entry 7), whereas `size_of::<StartBootTimes>()` in `abi/src/start.rs:252-261` is `48` bytes (asserted in `abi/src/tests.rs:1066`).
  - Line 585 budgets `80` bytes for `StartMachine` (entry 17), whereas `size_of::<StartMachine>()` in `abi/src/start.rs:343-382` is `96` bytes (asserted in `abi/src/tests.rs:1094`; the comment on `abi/src/start.rs:339-340` notes it grew from 80 to 88 in D-135 and to 96 in D-137).
  - Line 568 adds `+ 3` to `kept` unconditionally (for image, current crash, and previous crash), even when `machine.crash.1` is `None` (compare `kept_ranges` at `model/src/boot.rs:613-622`, which only pushes `previous` when `Some`).
  - Line 591 budgets `56 + 4 * 2` for `StartDebug` plus 2 refused port pairs, whereas `Model::ports_refused` (`model/src/debug.rs:382-391`) also refuses `console_port` when `Some` and `PCI_CONFIG_PORTS` when `!self.platform_holder()`, and non-x86_64 architectures have no I/O ports.
  Because `start_page_bytes` determines whether `Model::start` returns `Err(Refusal::StartPage)` (`model/src/boot.rs:1063-1068`), the 24-byte underestimate (`8 + 16`) can accept a start-up page near the 63-page limit that actually exceeds 63 pages when serialized.
- **How I know**: Inspected `model/src/boot.rs:558-622` against `abi/src/start.rs:66-92, 252-261, 339-382`, `abi/src/tests.rs:1066, 1094`, and `model/src/debug.rs:382-391`.

### Finding 2 — Should be fixed: `Model::build` estimates copied module frames from a fixed physical base instead of the advancing watermark

- **File and line**: `model/src/boot.rs:1105-1111, 1238-1249`
- **Code**:
```rust
        let start_at = untypeds[0].0;
        let copied: usize = layout
            .modules
            .iter()
            .filter(|m| m.3)
            .map(|m| frames_of(start_at, m.1, m.2))
            .sum();
```
and later:
```rust
        for &(_, vaddr, len, copied) in &layout.modules {
            let Some(vaddr) = vaddr.filter(|_| copied) else {
                continue;
            };
            let untyped = &self.untypeds[&start_untyped];
            let at = untyped.base + untyped.watermark;
            for frame in module_frames(at, Some(vaddr), len, geometry) {
                let cap = child(self, frame.size, frame.pages, next());
```
- **What is wrong**: `module_frames(phys, virt, len, geometry)` (`abi/src/machine.rs:1300-1359`) picks frame sizes based on the simultaneous alignment of `phys + offset` and `virt + offset`. The pre-count in `copied` passes the initial chunk-aligned `start_at` for every copied segment, whereas the allocation loop passes the advancing `at = untyped.base + untyped.watermark`. If a first small copied segment advances `watermark` by e.g. one page (`0x1000`), a second copied segment of length `2 * chunk` at `vaddr = 2 * chunk + 0x1000` is counted as `2` frames at `start_at` (never large-page aligned, so two 512-page frames) but allocates `3` frames at `base + 0x1000` (511 small pages, 1 large page where both align, 1 small page). Thus `used` (lines 1118-1126) can underestimate the slots consumed and leave fewer than `START_FREE_SLOTS` (4,096) empty slots.
- **How I know**: Traced `module_frames` in `abi/src/machine.rs:1300-1359` and both loops in `model/src/boot.rs:1105-1128, 1238-1249`.

### Finding 3 — Should be fixed: `Machine::initial_nodes` and `Machine::layout` can panic or wrap on malformed `boot_nodes`, `kinds`, or `phys_bits`

- **File and line**: `model/src/boot.rs:411, 424, 434, 631-665, 791, 817`
- **Code**:
```rust
        match &self.boot_nodes {
            Some((_, nodes)) => nodes
                .iter()
                .map(|&(window, mask)| {
                    (0..64)
                        .filter(|i| mask >> i & 1 == 1)
                        .map(|i| (64 * window + i) as usize)
                        .collect()
                })
                .collect(),
```
```rust
    pub fn kind_of(&self, core: usize) -> dodos_abi::Kind {
        self.kinds[usize::from(self.core_list()[core].kind)]
    }
```
```rust
        let words = 1u64 << (self.phys_bits - geometry.chunk_shift());
...
        let device = without(&vec![(0, 1u64 << self.phys_bits)], &sorted(taken));
```
- **What is wrong**:
  - `Machine::layout` calls `self.initial_nodes()` at line 641 before validating `boot_nodes` windows; if `window >= 1 << 58`, `64 * window + i` overflows in debug (panicking) or wraps in release (potentially aliasing a valid core number).
  - `Machine::layout` never checks that `self.kinds` is non-empty or that every `core.kind` is `< self.kinds.len()`, so `state_kind` (called at lines 411 and 646) panics with an out-of-bounds index instead of returning `Err(Refusal::MachineValues)`.
  - `Machine::layout` never checks `geometry.chunk_shift() <= self.phys_bits < 64`, so lines 791 and 817 panic with arithmetic underflow or shift overflow instead of returning `Err(Refusal::MachineValues)`.
- **How I know**: Read `Machine::initial_nodes`, `Machine::kind_of`, and `Machine::layout` in `model/src/boot.rs:398-459, 625-865`.


---

## `model/src/cores.rs`

### Finding 4 — Stops the merge: `go_idle` runs `answer_pending` after `choose` and can leave a newly woken thread unscheduled on the current core, breaking invariant 46

- **File and line**: `model/src/cores.rs:501-514` (called from `model/src/sched.rs:277-286`)
- **Code**:
```rust
    pub(crate) fn go_idle(&mut self) {
        let at = *self.at;
        self.cores[at].loaded = None;
        if self.width() == 1 {
            return;
        }
        if !self.cores[at].idle.mark {
            self.pay(Cost::IdleWord);
            self.cores[at].idle.mark = true;
        }
        if !self.cores[at].pending.is_empty() {
            self.answer_pending();
        }
    }
```
- **What is wrong**: `Model::end` (`model/src/sched.rs:255-289`) runs `self.choose(entry)` first, then if `self.cores[at].thread` is `None`, calls `self.go_idle()`, and finally calls `self.reschedule_others()`, which skips `at` (`(0..self.width()).filter(|&c| c != at)` at `model/src/sched.rs:321`). If `answer_pending()` inside `go_idle()` completes another core's TLB invalidation request whose `waiter` thread has its context placed on core `at` (for instance because `sched_configure` moved that context to `at` while the thread was waiting in `Wait::Cores`), `complete()` wakes the waiter into core `at`'s ready queue after `choose()` has already set core `at` idle (`running = None`, `idle.mark = true`). Because `reschedule_others()` ignores `at`, core `at` stays idle with an eligible ready context and no `Ipi::Reschedule` pending, violating invariant 46 (`check/sched.rs:161`: `ensure(core.running == chosen || pending, "46: running context")`).
- **How I know**: Traced `Model::go_idle` (`model/src/cores.rs:501-514`), `Model::complete` (`model/src/cores.rs:458-483`), `Model::end` and `Model::reschedule_others` (`model/src/sched.rs:250-335`), `Model::sched_configure` (`model/src/sched.rs:762-787`), and `Model::check_choice` (`model/src/check/sched.rs:141-162`).

### Finding 5 — Should be fixed: `Model::spurious` invalidates only the small-page-aligned address and misses large-page TLB entries

- **File and line**: `model/src/cores.rs:585-620`
- **Code**:
```rust
        let Some(rights) = self.translated_in(space, address) else {
            return false;
        };
...
        let page = address / self.page() * self.page();
        let core = self.core_of(thread);
        let flush = Flush::Range {
            space,
            addresses: vec![page],
        };
        self.invalidate_on(core, &flush);
```
- **What is wrong**: `CorePart::tlb` stores entries keyed by each translation's base virtual address (`at` in `aspace.translations`, copied in `cache_here` at lines 567-575). When `address` lies inside a large-page translation (`Large1` or `Large2`) at an offset past the first small page, `address / self.page() * self.page()` differs from the translation's key `at`, so `invalidate_on` calls `cached.remove(&page)` and fails to remove the entry from `core.tlb`.
- **How I know**: Read `Model::invalidate_on` (`model/src/cores.rs:368-396`), `Model::cache_here` (`model/src/cores.rs:559-579`), and `Model::spurious` / `Model::translated_in` (`model/src/cores.rs:585-620`).


---

## `model/src/grants.rs`

### Finding 6 — Should be fixed: `grant_signal` does not check whether the granting node's generation is still current and can wedge `signal_pending` and `has_work`

- **File and line**: `model/src/grants.rs:554-574` (and `model/src/rings.rs:664-690`, `model/src/nodes.rs:1906-1908`)
- **Code**:
```rust
        let body = Body::Signal {
            grant: remote.grant,
            serial: remote.serial,
        };
        if self.write_message(remote.node, body, None, None).is_err() {
            let me = self.node as usize;
            if let Some(entry) = self.table.uses[me].get_mut(&remote.use_entry) {
                entry.signal_pending = true;
            }
        }
        Ok(Output::Done)
```
- **What is wrong**: `Model::grant_signal` does not check whether the use entry's granting node and generation are still current (`table.writes(entry.granter) && table.generation(entry.granter) == entry.generation`).
  1. If the granting node's generation is already over (it died and was reclaimed, so `nodes.rs:1024` already ran) and the user ring to `remote.node` is full, `grant_signal` sets `entry.signal_pending = true`. `Model::unit_send_queued` (`model/src/rings.rs:681`) only sends or clears `signal_pending` when `current` is true (`if entry.signal_pending && current`), unlike `release_pending` which deletes the entry when `!current` (`model/src/rings.rs:668-671`). As a result, `signal_pending` remains `true` forever, and `Model::has_work` (`model/src/nodes.rs:1906-1909`) stays `true` forever.
  2. When the ring is not full and the granting node is dead or has restarted on a new generation, `grant_signal` writes a `Body::Signal` addressed to the dead or new generation (`header.receiver_generation` is read from `table.generation(to)`), causing a `Refused` message on a restarted peer or writing to a dead node's ring.
- **How I know**: Inspected `Model::grant_signal` (`model/src/grants.rs:554-574`), `Model::unit_send_queued` (`model/src/rings.rs:664-690`), `Model::reclaim` (`model/src/nodes.rs:1016-1028`), and `Model::has_work` (`model/src/nodes.rs:1895-1922`).


---

## `model/src/irq.rs`

### Finding 7 — Should be fixed: `IrqSource::KIND_CORE_EVENT` is checked at `irq_claim` entry and then treated as an MSI on segment 0 (and has no test)

- **File and line**: `model/src/irq.rs:54-56, 62-64, 106-123, 157-171, 389-391, 447-513`
- **Code**:
```rust
        if source.is_core_event() && !self.machine.core_events {
            return Err(Error::Unsupported);
        }
```
followed by branches that only test `source.is_line()`:
```rust
        let segment = match source.is_line() {
            true => ...,
            false => source.segment(),
        };
...
        let (address, data) = match (source.is_line(), self.machine.remapping) {
            (true, _) => (0, 0),
            (false, true) => (dodos_abi::x86_64::msi_remapped(handle), 0),
            (false, false) => {
                dodos_abi::x86_64::msi_direct(apic as u32, vector).expect("checked above")
            }
        };
```
- **What is wrong**: `IrqSource::core_event` (`abi/src/lib.rs:963-965`) encodes a local core event (`KIND_CORE_EVENT = 3`) with `segment() == 0` and `is_line() == false`. After checking `self.machine.core_events` at line 62, `irq_claim` and `irq_removal` only distinguish `is_line()` vs MSI:
  1. Line 54 applies the MSI/APIC-ID/remapped-core bounds (`apic > 255` without remapping, `core >= 341` with remapping) to a core event.
  2. Lines 113–123, 168–171, and 183–198 treat a core event as an MSI on PCI segment 0, writing its handle into IOMMU remapping tables and sending `InterruptCache` unit requests on claim and removal (`msi_removal`, lines 389–391, 447–513).
  3. Lines 157–163 return an MSI `(address, data)` instead of `(0, 0)`.
  4. A repository search for `core_event` / `is_core_event` shows no test in `model/` exercises claiming or delivering a core event (`model/src/boot.rs:339` sets `core_events: false`, and only `abi/src/lib.rs` and `abi/src/tests.rs` test `IrqSource::core_event` encoding).
- **How I know**: Read `model/src/irq.rs` in full, `abi/src/lib.rs:931-1010`, and searched `model/` for `core_event` and `is_core_event`.


---

## `model/src/nodes.rs`

### Finding 8 — Stops the merge: `resume_step` transitions the node to `Live` and clears `sealed_view` before `drop_ended` has finished

- **File and line**: `model/src/nodes.rs:1662-1725, 1741-1769`
- **Code**:
```rust
            if let Some(old) = self.ended_while_sealed(node) {
                let ran = self.r0_runs.contains_key(&(node, old));
                if self.ended_done.insert((node, old)) && !ran {
                    self.r0_effects(node, old);
                }
                any |= self.drop_ended(node, old, units);
            }
        }
        if self.cores.iter().all(|c| !c.silent) {
            self.ready = true;
            self.resuming = false;
            self.sealed_view.clear();
            self.ended_done.clear();
            let live = Member::new(
                MemberState::Live,
                ...
```
- **What is wrong**: In `resume_step`, the loop handles `Fencing | Fenced | Unfenced` peers by checking `if !done { return any; }` (lines 1681–1688) so the node does not go `Live` until `reclaim_step` finishes. For a peer whose generation ended while this node was sealed (`ended_while_sealed(node)` at line 1702), `resume_step` calls `drop_ended(node, old, units)` without checking whether `drop_ended` actually completed. If `drop_ended` exhausts `units` (32 per step) or pauses on an incomplete `remove_root` (`remove_root(root) != Ok(Output::Done)` at line 1764, e.g. waiting on an unmapping IOMMU/TLB step), `resume_step` falls through to line 1710, sees all cores non-silent, sets `self.ready = true`, clears `self.sealed_view` and `self.ended_done`, and writes `MemberState::Live`. The remaining stale remote capabilities to the dead or restarted node are never removed by `drop_ended`, and pinned grants remain pinned while the node is already `Live`.
  (In addition, `resume_step`'s doc comment at lines 1660–1661 states "then the rings that waited are consumed under the check, and the node becomes live", whereas `reserve_step` calls `resume_step` at line 1940 and `serve_kernel_rings` at line 1956, so the node becomes `Live` before its waiting kernel rings are consumed.)
- **How I know**: Read `Model::resume_step`, `Model::drop_ended`, and `Model::reserve_step` (`model/src/nodes.rs:1662-1769, 1930-1962`).


---

## `model/src/rings.rs`

### Finding 9 — Stops the merge: `Model::refused` trusts `message.header.sender` instead of checking it against the ring's `from` node

- **File and line**: `model/src/rings.rs:376-399, 515-525, 609-612`
- **Code**:
```rust
    pub(crate) fn refused(&self, message: &Message) -> Option<u64> {
        let header = &message.header;
        let sender = header.sender;
        if sender >= self.table.nodes {
            return Some(0);
        }
        // The sender's member word is starting, live, sealing or sealed
        // with that generation: what a node wrote before its seal is
        // answered (D-131).
        let member = self.table.member(sender);
        let sending = matches!(
            member.state(),
            MemberState::Starting | MemberState::Live | MemberState::Sealing | MemberState::Sealed
        );
        if !sending || member.generation() != header.sender_generation {
            return Some(0);
        }
```
```rust
            match message {
                Some(message) => match self.refused(&message) {
                    None => self.receive_message(message),
```
```rust
    fn receive_message(&mut self, message: Message) {
        let sender = self.table.member(message.header.sender);
        self.applied.0.push((message.header, sender));
        let from = message.header.sender;
```
- **What is wrong**: `Model::consume` reads an entry from the ring `(from, me, user)`, where `from` is the hardware-isolated sender slot of that ring, and passes `&message` to `self.refused(&message)` without passing `from`. `refused` never checks `header.sender == from`; it validates `member(header.sender)` and `header.sender_generation` against whatever node slot the sender wrote in `header.sender`, and `receive_message` then dispatches the message using `from = message.header.sender`. Because `serve_user_rings` and `serve_kernel_rings` poll rings from every `from != self.node` (regardless of `from`'s state), a faulty or dead node `from` can place a message in its `from -> me` ring with `header.sender = victim` (another live node, or even `self.node`) and `victim`'s current generation: `refused` accepts it (for example, `Body::UnitRequest` passes unconditionally at line 454, and `Body::Send` with `stamp.0 == 0` passes at lines 458–461), causing the receiver to attribute the request/send to `victim` and send any answer to `victim`. When a message is refused, `consume` (line 520) also records `u64::from(from) | u64::from(message.header.sender_generation) << 32`, mixing the ring's `from` with `header.sender_generation`.
- **How I know**: Read `model/src/rings.rs` in full (`consume`, `refused`, and `receive_message`).


### Finding 10 — Should be fixed: `serve_user_rings` / `consume` bounds the step by message count instead of ring entries

- **File and line**: `model/src/rings.rs:478-514, 554-566` (and `abi/src/ring.rs:26-27`)
- **Code**:
```rust
    /// Consumes at most `step` messages of one ring into this node, each
    /// under the check; returns how many entries remain.
    fn consume(&mut self, from: u16, user: bool, step: u64) -> u64 {
...
        let mut served = 0;
        while served < step {
...
            self.set_consumed(from, user, consumed + length);
            served += 1;
```
```rust
    /// The user rings into this node, at the interrupt that signals them:
    /// at most 16 entries per ring; if entries remain, the core sends
    /// itself the interrupt again.
    pub(crate) fn serve_user_rings(&mut self) {
        if !self.consumes() {
            return;
        }
        let mut left = false;
        for from in 0..self.table.nodes {
            if from != self.node && self.consume(from, true, RING_USER_STEP) > 0 {
                left = true;
            }
        }
```
- **What is wrong**: `dodos_abi::RING_USER_STEP` (`16`, `abi/src/ring.rs:26-27`) and the doc comment on `serve_user_rings` (lines 554–556) specify consuming at most 16 **entries** per user ring per interrupt. However, `consume` increments `served += 1` per message (or unreadable entry) rather than by `length` entries. A `Body::Send` message can occupy up to 10 entries (`3 + 4 + 64` words), so `serve_user_rings` can process up to 16 `Send` messages (up to 160 ring entries, more than twice the 64-entry ring capacity) in a single interrupt instead of stopping after at most 16 entries.
- **How I know**: Read `model/src/rings.rs` in full and `abi/src/ring.rs:26-27`.


---

## `model/src/roles.rs`

### Finding 11 — Stops the merge: `rebuild_step` deletes a newly resumed node's `unit.entries` and `unit.lines`

- **File and line**: `model/src/roles.rs:452-514`
- **Code**:
```rust
        while rebuild.node < self.table.nodes {
            let z = rebuild.node;
            if z == self.node {
                let items = self.items(role);
                rebuild.items.extend(items.into_iter().map(|i| (z, i)));
                rebuild.node += 1;
                continue;
            }
            if !self.table.writes(z) {
                rebuild.node += 1;
                continue;
            }
...
        let sealed: Vec<u16> = (0..self.table.nodes)
            .filter(|&z| self.table.member(z).state() == MemberState::Sealed)
            .collect();
...
        for (device, (node, _)) in entries {
            let claimed = reported
                .iter()
                .any(|&(z, i)| z == node && matches!(i, Item::Device(d, _) if d == device));
            if !claimed && !sealed.contains(&node) {
                unit.entries.remove(&device);
            }
        }
        let lines: Vec<(u32, (u16, u32))> = unit.lines.iter().map(|(&l, &e)| (l, e)).collect();
        for (line, (node, _)) in lines {
            let claimed = reported
                .iter()
                .any(|&(z, i)| z == node && matches!(i, Item::Line(l, ..) if l == line));
            if !claimed && !sealed.contains(&node) {
                unit.lines.remove(&line);
            }
        }
```
- **What is wrong**: While `rebuild_step` scans nodes `0..self.table.nodes`, line 460 skips any node `z` whose `!self.table.writes(z)` (which includes `MemberState::Sealed`) without asking `z` for a `Report`. If a `Sealed` node `z` is skipped when `rebuild.node == z`, and `z` subsequently resumes (`Sealed -> Live`) while `rebuild_step` is still waiting on later nodes, then when `rebuild_step` reaches line 488: `z` is `MemberState::Live`, so `z` is not in `sealed`, and `z` is absent from `reported`. Both `!claimed && !sealed.contains(&node)` checks evaluate to `true` for every device and line owned by `z`, removing all of the live node's IOMMU context entries (`unit.entries`) and IOAPIC line entries (`unit.lines`).
- **How I know**: Read `model/src/roles.rs` in full (`rebuild_step`) and `model/src/nodes.rs:1662-1725` (`resume_step`, which transitions `Sealed -> Live` without checking ongoing rebuilds).


### Finding 12 — Should be fixed: `after_take` omits `MemberState::Dead` contrary to its comment, leaving stale `unit.remap` entries uncleaned

- **File and line**: `model/src/roles.rs:387-417, 547` (and `model/src/nodes.rs:1037-1069`)
- **Code**:
```rust
    /// R1 at every change of holder: the node that takes a unit role runs
    /// R1 on it for every node that is fencing, fenced, unfenced or dead
    /// before it serves any other request, and writes `acked` back to 0
    /// for each such node it had acknowledged, until that R1 is done.
    fn after_take(&mut self, role: usize) {
        let me = self.node as usize;
        let mine = self.node;
        for node in (0..self.table.nodes).filter(|&z| z != mine) {
            let member = self.table.member(node);
            if !matches!(
                member.state(),
                MemberState::Fencing | MemberState::Fenced | MemberState::Unfenced
            ) {
                continue;
            }
```
```rust
                Item::Handle(_) => {}
```
- **What is wrong**: `after_take`'s doc comment states that a node taking a unit role runs R1 on it for every node that is `fencing, fenced, unfenced or dead`, but line 398 only matches `Fencing | Fenced | Unfenced` and skips `MemberState::Dead`. If a prior holder died before running R1 for a node `D` and `D` reached `Dead` before the new holder took over, `r1` will not run for `(D, g_D)` on this unit; and because `rebuild_step` (`roles.rs:498-548`) only prunes `unit.entries` and `unit.lines` (and ignores `Item::Handle(_)` at line 547), stale `(D, g_D)` entries in `unit.remap` are left behind.
- **How I know**: Read `model/src/roles.rs` in full and `model/src/nodes.rs:1037-1069` (`r1`).


### Finding 13 — Should be fixed: Contradictory comment and unused `&mut self` on `rebuilt_attach` regarding `AttachState::Pinned`

- **File and line**: `model/src/roles.rs:518-525, 556-566`
- **Code**:
```rust
                // A context entry only for a device whose attach word reads
                // *attached*, or *pinned* (moved to *attached* first, as at
                // an attach), with the root the report names (D-137).
                Item::Device(device, root) => {
                    if self.rebuilt_attach(role, device, root) {
                        let unit = self.table.units.entry(role).or_default();
                        unit.entries.insert(device, (z, g));
                    }
                }
```
```rust
    /// A rebuild's check of a reported device: its attach word reads
    /// *attached* with the root (D-137). A device whose attach is in flight
    /// is in no header and no report; its kept attach is served once the
    /// rebuild ends (the attach word against every event, D-139).
    pub(crate) fn rebuilt_attach(&mut self, role: usize, device: u16, root: u64) -> bool {
        let Some(key) = self.attach_key(role, device) else {
            return false;
        };
        let word = self.table.attach_word(key);
        word.root() == root && word.state() == Some(dodos_abi::AttachState::Attached)
    }
```
- **What is wrong**: The comment at lines 518–520 says a reported device's attach word may be `*attached*, or *pinned* (moved to *attached* first, as at an attach)`, whereas `rebuilt_attach` and its own doc comment at lines 556–566 only accept `AttachState::Attached` and never move `Pinned` to `Attached` (though `rebuilt_attach` still takes `&mut self`). One of the two comments is stale and should match the actual rule.
- **How I know**: Read `model/src/roles.rs` in full.


### Finding 14 — Should be fixed: `rebuild_step` returns `true` (progress) when `write_message` fails

- **File and line**: `model/src/roles.rs:227-235, 472-480`
- **Code**:
```rust
            let asked = self.write_message(z, body, Some(Completes::Report { role }), None);
            rebuild.asked = asked.is_ok();
            self.rebuilds.insert(role, rebuild);
            return true;
```
- **What is wrong**: When `write_message` returns `Err(Full::Ring)` or `Err(Full::Credit)` on the first node `rebuild_step` checks, `rebuild.asked` remains `false` and `rebuild.node` does not advance, yet `rebuild_step` returns `true` as if it made progress. `reserve_step` (`model/src/nodes.rs:1954-1960`) loops `while *units > 0 && progressed`, so `roles_step` (`roles.rs:227-235`) will burn all remaining recovery `units` retrying the same failed `write_message` in one reserve call.
- **How I know**: Read `model/src/roles.rs` in full and `model/src/nodes.rs:1954-1960`.


---

## `model/src/system.rs`

### Finding 15 — Should be fixed: `System::boot` puts unowned spare cores into `Hardware::Stub` even on `Aarch64` and `Riscv64`

- **File and line**: `model/src/system.rs:121-131, 668-680, 690-696, 704-710`
- **Code**:
```rust
        let hardware = (0..machine.cores.len())
            .map(|core| {
                match table
                    .core_word(core)
                    .is_some_and(|w| w.state() == CoreState::Owned)
                {
                    true => Hardware::Running,
                    false => Hardware::Stub { window: false },
                }
            })
            .collect();
```
```rust
    fn wake(&mut self, core: usize) {
        match (self.machine.arch, self.hardware[core]) {
            (Arch::X86_64, Hardware::Stub { window: true }) => return,
            (Arch::X86_64, Hardware::Stub { window: false }) => {}
            (Arch::Aarch64 | Arch::Riscv64, Hardware::Off) => {}
            _ => return,
        }
```
- **What is wrong**: `System::park`, `System::stop`, and `System::wake` represent parked or unstarted cores on `Arch::Aarch64` and `Arch::Riscv64` as `Hardware::Off` (using `Hardware::Stub` only on `Arch::X86_64`). However, `System::boot` initializes every core whose initial core word is not `CoreState::Owned` to `Hardware::Stub { window: false }` regardless of `machine.arch`. On `Aarch64` and `Riscv64`, `wake(core)` ignores `Hardware::Stub { .. }` (`_ => return`), so a spare core on those architectures can never be started by `NodeStart`, and `stop(core)` on `Aarch64` misses the `(Arch::Aarch64, Hardware::Off)` arm and does not confirm `stopped[core]`.
- **How I know**: Read `model/src/system.rs` in full (`boot`, `stop`, `park`, `wake`) and searched `model/` for `Aarch64` / `Riscv64` tests.


---

## `model/src/units.rs`

### Finding 16 — Should be fixed: `operands_allowed` does not check that the role governs the operation's hardware kind or GSI, nor the line word's state/generation on mask

- **File and line**: `model/src/units.rs:252-265, 333-365, 465-476`
- **Code**:
```rust
            UnitOp::InterruptCache { handle } => names(handle_core(handle)),
            // Masked: operand 2 is 0, and the line's word is free or names
            // the requester (D-135).
            UnitOp::Redirection {
                claimed: false,
                gsi,
                target,
                ..
            } => {
                let word = self.table.line_word(gsi);
                let free = word.state() == dodos_abi::OwnState::Free;
                let names = word.owner() == dodos_abi::Owner::Node(node);
                target == crate::rings::Target::Masked && (free || names)
            }
```
- **What is wrong**:
  1. `UnitOp::InterruptCache` only checks `names(handle_core(handle))` and never checks `record.governs == Governs::IommuUnit` (or `self.machine.remapping`), so an IOAPIC role holder accepts `InterruptCache` requests.
  2. `UnitOp::Redirection` never checks `record.governs == Governs::IoApic` or `self.ioapic_role(gsi) == Some(role)`. A faulty requester can send a `Redirection` request for `gsi` to an IOMMU role or to a different IOAPIC's role, and `submit_for` (lines 465–476) inserts or removes `gsi` in that wrong unit's `lines` / `masked` sets.
  3. When `claimed == false`, `names` only checks `word.owner() == Owner::Node(node)` without checking `word.state() == OwnState::Taken` and `word.generation() == generation` (unlike `claimed: true` at lines 350–351).
- **How I know**: Read `model/src/units.rs` in full (`operands_allowed` and `submit_for`).


### Finding 17 — Should be fixed: Kept `unit_service` requests during a rebuild clash with `hand_step` / `role_hand` / `hand_all_units`

- **File and line**: `model/src/units.rs:520, 535-555` and `model/src/roles.rs:141-149, 195-207, 273-289, 570-584`
- **Code**:
```rust
        let submitted = match self.rebuilds.contains_key(&role) {
            true => None,
            false => {
...
            }
        };
        self.unit_service.insert(
            (from, index),
            Served {
                role,
                op,
                serial,
                submitted,
            },
        );
```
```rust
        let begun =
            self.unit_service.values().any(|s| s.role == role)
                || self.unit_requests.iter().flatten().any(|e| {
                    e.role == role && matches!(e.stage, crate::units::Stage::Local { .. })
                });
```
- **What is wrong**: While a unit role is rebuilding (`self.rebuilds.contains_key(&role)`), `unit_requested` (`units.rs:535-555`) stores incoming requests in `self.unit_service` with `submitted: None`, to be submitted later by `serve_kept` (`roles.rs:570-584`) when `rebuild_step` finishes. Neither `role_hand` (`roles.rs:97-153`) nor `hand_all_units` (`roles.rs:181-210`) checks `!self.rebuilds.contains_key(&role)` (and `role_hand` also does not check `!self.handing.contains_key(&role)`, so a second `role_hand` overwrites `self.handing[&role]` and strands the first caller thread in `Wait::Hand`). If a hand-over begins while `role` is rebuilding:
  1. `hand_step` (`roles.rs:273-289`) treats kept `unit_service` entries (`submitted: None`) as `begun = true`, waits while the rebuild collects remote reports, and if the rebuild takes `IOMMU_WAIT_NS`, calls `self.fail_unit(role)` — falsely marking a working unit as failed.
  2. If the rebuild finishes first, `serve_kept` (`roles.rs:578`) calls `submit_for` and starts new unit submissions after `self.handing` is already active.
- **How I know**: Read `model/src/units.rs` and `model/src/roles.rs` in full.


---

## Files read and not read

### Files read whole

Lot C target files (read whole, in order):
1. `model/src/boot.rs` (1369 lines)
2. `model/src/cores.rs` (871 lines)
3. `model/src/grants.rs` (830 lines)
4. `model/src/irq.rs` (615 lines)
5. `model/src/nodes.rs` (2016 lines)
6. `model/src/rings.rs` (722 lines)
7. `model/src/roles.rs` (686 lines)
8. `model/src/system.rs` (853 lines)
9. `model/src/units.rs` (827 lines)

Guidance and supporting files read whole:
- `AGENTS.md`
- `model/README.md`
- `.claude/skills/dodos-rust/SKILL.md`
- `.claude/skills/rust-1-100/SKILL.md`
- `abi/src/start.rs` (455 lines)
- `model/src/check/cores.rs` (71 lines)

### Files read partially

- `abi/src/lib.rs`: lines 324–359, 931–1010
- `abi/src/machine.rs`: lines 235–275, 600–720, 1090–1180, 1300–1365
- `abi/src/ring.rs`: lines 1–320
- `abi/src/tests.rs`: lines 1046–1104, 1582–1632
- `abi/src/x86_64.rs`: around line 150
- `model/src/caps.rs`: lines 663–703, 1050–1100
- `model/src/check/node.rs`: lines 57–140
- `model/src/check/sched.rs`: lines 1–180
- `model/src/debug.rs`: lines 115–155, 250–315, 375–410
- `model/src/ipc.rs`: lines 22–61, 143–193, 593–633
- `model/src/locks.rs`: lines 148–173
- `model/src/memory.rs`: lines 970–1085
- `model/src/sched.rs`: lines 33–83, 120–350, 732–787
- `model/src/table.rs`: lines 86–260
- `model/src/scenarios/crossing.rs`: lines 620–725
- `model/src/scenarios/pass17.rs`: lines 95–155
- `model/src/scenarios/pass18.rs`: lines 45–90, 195–255
- `model/src/scenarios/pass21.rs`: lines 170–210, 550–620
- `model/tests/boot.rs`: lines 1–120, 505–535

### Files and directories not read

- Remaining `abi/` files (`Cargo.toml`, `Cargo.lock`, `verify`, `abi/src/aarch64.rs`, `abi/src/debug.rs`, `abi/src/features.rs`, `abi/src/riscv64.rs`, `abi/tests/review6.rs`, and unread parts of `abi/src/lib.rs`, `abi/src/machine.rs`, `abi/src/ring.rs`, `abi/src/tests.rs`, `abi/src/x86_64.rs`).
- Remaining `model/src/` files (`model/Cargo.toml`, `model/src/blocks.rs`, `model/src/check.rs`, `model/src/faults.rs`, `model/src/lib.rs`, `model/src/tasks.rs`, `model/src/threads.rs`, and unread parts of `model/src/caps.rs`, `model/src/debug.rs`, `model/src/ipc.rs`, `model/src/locks.rs`, `model/src/memory.rs`, `model/src/sched.rs`, `model/src/table.rs`).
- `model/src/check/` files not read (`model/src/check/debug.rs`, `model/src/check/machine.rs`, `model/src/check/memory.rs`, `model/src/check/table.rs`, `model/src/check/tasks.rs`, `model/src/check/tests.rs`, and unread parts of `model/src/check/node.rs` and `model/src/check/sched.rs`).
- `model/src/scenarios/` files not read (`checker.rs`, `cores.rs`, `explore.rs`, `membership.rs`, `mistral.rs`, `mod.rs`, `pass19.rs`, `pass20.rs`, `reviews.rs`, `units.rs`, and unread parts of `crossing.rs`, `pass17.rs`, `pass18.rs`, `pass21.rs`).
- `model/tests/` directory (all files except the partial reads in `model/tests/boot.rs`).
- Note: No test suite or build command was executed; all findings are from static inspection of the repository files listed above.
