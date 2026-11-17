# Review of lot B (model/src: blocks, caps, debug, faults, ipc, lib, locks, memory, sched, table, tasks, threads)

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
Reviewer: Opus, working alone. Runs were made in a copy,
`/private/tmp/dodos-pr3-B-opus`.

Severities: **stop** (stops the merge), **fix** (should be fixed),
**question** (want an answer first).

## blocks.rs

### 1. fix — `memory_split` does not refuse a block whose device entry still has leaves (G5), unlike `memory_give`

`model/src/blocks.rs:296-297`

```rust
        self.idle_block(cap, object)?;
        self.return_watermark(object)?;
        let unclaimed = Ownership::free(Owner::Unclaimed);
```

`memory_give` runs the same two checks and then
`if self.mapped_block(object) { return Err(Error::Busy); }`
(`blocks.rs:213`), whose doc says "Whether ... the leaf count of its device
entry, is not 0 (G5)". `memory_split` skips it. The state "idle block, leaf
count not 0" is reachable: `memory.rs:294` adds a record's leaves to
`frozen_entries[index]` when a failed unit never confirms their
invalidation, and clears the record (`Record::Empty`), so the frame and its
capability can go while `device_leaves[index]` stays above 0. A split then
succeeds: the lower half keeps `index` and the frozen count, the upper half
moves to the spare entry with whatever leaf count that entry had, so the
frozen leaves of pages in the upper half no longer pin anything, and the
upper half can be given. Either the split needs the same `mapped_block`
check (and a test), or a comment saying why the contract lets a split go
with leaves outstanding. How I know: reading; I did not build the
failed-unit state to run it.

### 2. stop — a reserve chunk can be taken twice: `taken_here` returns `false` for every reserve word, against its doc

`model/src/blocks.rs:159-171` (used at `blocks.rs:83`)

```rust
    /// Whether a word is taken by this node's current generation: for a
    /// reserve's word, by a live block of this node.
    ...
            Owner::Reserve(_) => false,
```

```rust
            if self.taken_here(word) || !self.table.may_take(word, self.node) {
                return Err(Error::Busy);
            }
```

The doc says a reserve's word counts as taken here when a live block of
this node holds it; the code never says so. `memory_take` keeps the
reserve's code in a word it takes (`blocks.rs:98-101`:
`Ownership::taken(Owner::Reserve(j), generation)`), and
`Ownership::may_take` answers `holds_reserve` for any reserve word, *taken*
or *free* (`abi/src/machine.rs:619`: `Owner::Reserve(_) => holds_reserve`).
So for the holder of the reserve's role, nothing refuses a second
`memory_take` of a chunk its own live block already covers: two untypeds
over the same memory.

How I know: a test in my copy (`model/tests/zz_review.rs`,
`review_reserve_chunk_taken_twice`), built like the existing
`gate_words.rs:77` test (find a reserve chunk, claim the reserve role from
slot 21 or 22), takes the same chunk into slot 120 and then slot 121:

```
$ nix develop -c cargo test -p dodos-model --test zz_review review_reserve -- --nocapture
first take: Ok(Done); second take of the same reserve chunk: Ok(Done); check: Err("53: two blocks on a chunk")
```

The model's own invariant 53 catches the state after the fact, which shows
the call should have been `busy`. The branch needs to answer "taken here"
for a *taken* reserve word whose chunk is in a live block of this node (for
example `self.kernel_runs.contains(&index)`, or a scan of the untypeds with
`Block::Run`), and the test above should become a regression test. No
existing test takes a reserve chunk twice; the random walk of
`property.rs` evidently never reaches it.

### 3. fix (small) — the chunk range of a run is computed in three places

`blocks.rs:18-21` (`Model::run`), `blocks.rs:331-332` (inside
`mapped_block`), `blocks.rs:431-433` (`FreedRun::chunks`) each compute
`base >> shift .. (base + bytes) >> shift`. The skill `dodos-rust` asks that
a check several operations share be written once. Also
`remove_block_cap` (`blocks.rs:405-407`) is a one-line wrapper over
`remove_leaf` with no other content.

## lib.rs

### 4. fix — the crate's top doc describes a model this file no longer is

`model/src/lib.rs:1-21`

```rust
//! Executable reference model of the DodOS kernel, for one core.
...
//! written); the hardware (translations are a map; the invalidations of the
//! TLB and of the IOMMU are done before a call returns; masking, the end of
//! interrupt and the entropy pool are not seen); the kernel's own time,
//! taken as zero; more than one node (the waiting-for-the-core-group state
//! is never entered); and the groups not specified (cores, debugging,
//! `ioports`), whose calls return `unsupported`.
```

Each of these is false in this branch:
- "for one core": `Model` holds `cores: Vec<cores::CorePart>` (`lib.rs:1059`)
  and its own doc says "The whole state of the kernel of one node: ... the
  part of each of its physical cores" (`lib.rs:1013-1014`); README says *N*
  cores.
- "the invalidations ... are done before a call returns": `memory_give`
  returns `Output::Waits` when `start_request` gives `Started::Asked`
  (`blocks.rs:235-236`), and `Record::Unmapping` exists for exactly this
  (`lib.rs:503-506`).
- "more than one node": `System` (`system.rs`), rings, grants, fences.
- "the groups not specified (cores, debugging, `ioports`), whose calls
  return `unsupported`": `debug_write`, `trace_emit`, `ioport`,
  `ioports_issue` are implemented in `debug.rs:319-486`; the node calls
  (`node_start`, `node_stop`, ...) are dispatched at `lib.rs:1513-1535`.
This is the first page a newcomer reads (`cargo doc`).

### 5. fix — `chunked_or_kept` answers `true` for an address past the ownership table, so its only test cannot see a page dropped there

`model/src/lib.rs:1337-1343`

```rust
        self.table.owners.get((at >> shift) as usize) != Some(&dodos_abi::Ownership::none().raw())
```

`get` returns `None` for a chunk index beyond `owners`, and `None != Some(..)`
is `true`: an address the table does not cover is reported as lying "in a
chunk of ordinary memory". Its one caller is the test at
`model/tests/boot.rs:655-658` ("usable page ... dropped"), which therefore
cannot catch a usable page dropped because the ownership table is too short.
Write `.is_some_and(|&w| w != none)`.

## caps.rs

### 6. fix (small) — the "detach still pending on one of the iospace's units" test is written twice in `undo`

`model/src/caps.rs:1019-1027` and `caps.rs:1042-1050`

```rust
                        let units = self.aspaces[&object].units.clone();
                        let roles: Vec<usize> = units.iter().map(|&u| self.unit_role(u)).collect();
                        let pending = self.unit_requests.iter().flatten().any(|e| {
                            roles.contains(&e.role)
                                && matches!(e.op, crate::rings::UnitOp::Detach { .. })
                        });
                        if pending {
                            return Undone::Wait;
                        }
```

The same nine lines appear in the `(None, Some(cap))` and `(None, None)`
arms. Both arms start with it, so it can be done once before the `match`
(when `device` is `None`), or put in a helper. `dodos-rust`: "a check that
several operations share is written once."

### 7. fix (small) — two comments in `undo` sit on the wrong arm or list the wrong things

`model/src/caps.rs:973-991`

```rust
            // Destroying a context clears its lends from the top of the
            // chain down; destroying a notify disarms its armed timers.
            ObjectKind::Sched if self.clear_lend(object) => {}
            // Destroying a notify: its armed timers are disarmed, then its
            // bound irqs unbound; destroying a task detaches its threads.
            // Then its watch slots, one unit each (Cores).
            ObjectKind::Notify
                if self.disarm_one(object)
                    || self.unbind_one_irq(object)
                    || self.unwatch_one(object)
                    || self.undoorbell_one(object) => {}
            ObjectKind::Task if self.detach_one(object) => {}
            // IOMMU: the destruction of an iospace first detaches each of its
            // devices, ...
            ObjectKind::Irq => return self.irq_removal(object),
            ObjectKind::IoSpace => {
```

The notify is described twice; the second description puts "Then its watch
slots" after the task, and does not name the fourth unit, the grant
doorbells (`undoorbell_one`). The iospace paragraph is above the `Irq` arm,
so a reader takes it for the irq's rule. Not a behaviour bug; it costs a
newcomer time.

### 8. question — a block whose run keeps frozen leaf counts can never be removed: `cap_delete` returns `again` forever

`model/src/caps.rs:959-962`

```rust
            ObjectKind::Untyped if self.untypeds[&object].block.is_some() => {
                if self.mapped_block(object) {
                    return Undone::Wait;
                }
```

`mapped_block` reads the map counts, which include the counts in `frozen`
that "are never lowered" (`lib.rs:1166-1170`, `memory.rs:276-296`). Once a
failed unit froze a leaf in a run, every removal that reaches the block's
root capability returns `again` on every call, and so does the removal of
any capability space that holds it (the sweep cannot pass it). If that is
the contract's reading (the memory stays frozen until restart), a comment
here and a test that pins it would help; if a frozen block should instead
be removable with its words left taken, the branch is missing. I found no
test that reaches this state (`grep -rn frozen model/src model/tests` shows
only the field, `memory.rs` and the checker).

## debug.rs

### 9. fix — `ioport_out` asks for `write` on the capability space it is addressed through, though it changes no slot

`model/src/debug.rs:410-413`

```rust
    fn ports_of(&self, thread: ObjId, slot: SlotAddr, right: Rights) -> Result<IoPortRange, Error> {
        let cap = self.cap(thread, slot, right)?;
        let held = self.is(cap, ObjectKind::IoPorts, right)?;
```

`right` is `WRITE` for `ioport_out`. It is used twice: as the right on the
`ioports` capability (correct) and as the `right` argument of `cap`, which
`addressed_space` documents as "Through a `cspace` capability, `right` is
the right needed: `READ` to look at a slot, `WRITE` to change it"
(`lib.rs:1681-1682`). Every other call looks at its capability slot with
`READ` (`held`, `lib.rs:1787`); the only other callers of `cap` with
`WRITE` are `cap_move`, `cap_revoke` and the move of a transfer, which do
change the slot. So a port write through a read-only `cspace` capability is
`denied`, and a port read through the same capability succeeds.

How I know: a test in my copy (`model/tests/zz_review.rs`) makes a cspace
(slot 100), grows it, derives the start-up `ioports` capability with
`read|write` into `through(100, 1)`, derives a `read`-only copy of the
cspace capability into slot 101, and then calls through slot 101:

```
$ nix develop -c cargo test -p dodos-model --test zz_review -- --nocapture
in through read-only cspace: Ok(Value(0)); out: Err(Denied)
```

The fix is `self.cap(thread, slot, Rights::READ)` in `ports_of`.

### 10. fix (small) — `range_of` silently widens a malformed badge to every port

`model/src/debug.rs:523-525`

```rust
pub(crate) fn range_of(badge: u64) -> IoPortRange {
    IoPortRange::new(badge & 0xFFFF, badge >> 16 & 0xFFFF).unwrap_or(IoPortRange::ALL)
}
```

Every `ioports` badge is made valid (`boot.rs:1145`, `ioports_issue`), so the
fallback is never taken today; but if a future path stores a badge with
`first > last`, the capability would grant all 65,536 ports instead of
failing. In a reference model a broken invariant should panic (`expect`)
or be refused, not widen authority.

### 11. question — where the rate limit is counted: per core or in the node block?

`model/src/debug.rs:1-3` says "the rate limit of the kernel ring, counted
per core", and the code keeps it per core (`self.here().limits`,
`cores.rs:156-160`). The type's own doc says the opposite:

```rust
/// The rate limit of one code of the kernel ring, in the node block: the
```

(`debug.rs:136`), and so does invariant 91 in `check/debug.rs:38-39`
("still counted in the node block"). One of the two texts is stale.

## faults.rs

### 12. fix (small) — `raise`'s doc says an undeliverable fault is dropped; the code records it

`model/src/faults.rs:55-58` and `75-77`

```rust
    /// ... Without a fault endpoint, or with
    /// a dying one, the thread is suspended at once and the fault dropped.
    ...
        let Some((endpoint, badge)) = endpoint else {
            self.record(thread, kind as u32, words);
```

`record` keeps the kind and five words in `Thread::recorded`, readable by
`thread_read_regs`, and writes a trace entry of code 5 — the fault is
recorded, not dropped (`record`'s own doc, line 110: "a fault that is not
delivered is recorded in the thread"). "Dropped" is the right word only for
the other case, a fault wait that ends without an answer (`lib.rs:1874-1876`).

### 13. question — a fault of a thread with no capability space gets a receive window whose "cspace" is the endpoint's identity

`model/src/faults.rs:100-104`

```rust
        let window = Window {
            cspace: faulting.cspace.unwrap_or(endpoint),
            first: 0,
            count: 0,
        };
```

`Window::cspace` is meant to name a capability space; here it may name an
endpoint. It is harmless only because every reader skips a window of count
0 or looks it up with `get` (`check.rs:713-721`, `ipc.rs:527-531`). A
`Option<ObjId>` or a comment that the value is a placeholder would remove
the trap.

## ipc.rs

### 14. fix (small) — `Message::check_header` is a wrapper that adds nothing

`model/src/ipc.rs:42-44`

```rust
    pub(crate) fn check_header(&self, page: bool) -> Result<(), Error> {
        self.check(page)
    }
```

Its only caller is `grants.rs:185`; making `check` `pub(crate)` removes the
second name for one function. Otherwise I found no defect in ipc.rs: the
order of checks, the all-or-nothing delivery (the short-circuit that keeps
`fits` from reading a destroyed space, lines 545-553), the marks stamp and
the header built before truncation agree with their comments.

## locks.rs

### 15. question — `Step::Spin` is never produced by the model, so the check "no event spins" can fail only on a planted trace

`model/src/locks.rs:80-81`

```rust
    /// The event waited inside its hold (never, in a correct kernel).
    Spin(WaitKind),
```

`grep -rn "Spin" model/src model/tests` finds it only in the check
(`check/node.rs:284`) and in two checker tests that write it by hand
(`scenarios/cores.rs:536`, `scenarios/checker.rs:219`). No code path of the
model pushes `Step::Spin`, so the invariant is a check no state reached by
calls can fail. README ("What it does not model") removed the check of the
sequence words for exactly this reason ("a step that recorded it would be a
check no state can fail"). Either the variant and its check go, or say why
this one is kept.

## memory.rs

### 16. stop — `aspace_map`/`iospace_map` count tables still waiting for their invalidation as free, and the model panics

`model/src/memory.rs:531`

```rust
        let free = aspace.tables - hooked.len() as u64;
        let missing = (wanted - hooked.len() as u64).saturating_sub(free);
```

`ASpace::tables` counts every lower table taken: hooked, on the free list,
and unhooked waiting for an invalidation (`check/table.rs:479`:
`taken = hooked + free + unhooked`). The free list is therefore
`tables - hooked - unhooked`, not `tables - hooked`. When a space has
unhooked tables (D-137: an unmap or a removal step whose invalidation needs
other cores or a unit), `missing` comes out too small, nothing is taken
from the untyped, and `record_mapping` → `rehook` pops an empty free list:

```rust
            let page = aspace.free.pop().expect("a table on the free list");   // memory.rs:190
```

Reached by two ordinary calls of one thread: a `cap_delete` of a mapped
frame in an iospace that serves a device (the removal step clears the
record, starts the unit's invalidation and returns `again`, leaving its
tables unhooked), then an `iospace_map` of another frame at an address that
needs new tables. How I know: a scenario added to my copy of
`model/src/scenarios/pass19.rs`
(`review_map_after_a_removal_step_left_tables_unhooked`, built on the
existing `three()` and `attached()` helpers):

```
$ nix develop -c cargo test -p dodos-model --lib review_map_after -- --nocapture
delete: Err(Again); tables 3 hooked 0 free 0 unhooked 3
thread 'scenarios::pass19::review_map_after_a_removal_step_left_tables_unhooked' panicked at model/src/memory.rs:190:42:
test result: FAILED. 0 passed; 1 failed; ...
```

The same holds on x86-64 or RISC-V in a node of several cores with an
`aspace` whose tag another core loaded. The fix is
`let free = aspace.free.len() as u64;` (or subtract `unhooked.len()`), with
this scenario as its regression test. No existing test maps into a space
while it has unhooked tables (the two tests of D-137,
`pass19.rs:523` and `pass20.rs:769`, stop before).

### 17. fix (small) — `detach_local` and `detach` say they free the identifier word; neither does

`model/src/memory.rs:1113-1116`

```rust
    /// The node's own record of a detach, and its report; the identifier
    /// word becomes free and unclaimed. Returns the iospace's domain
    /// number, freed with its last device.
    fn detach_local(&mut self, iommu: ObjId, device: u16) -> u16 {
```

The body never touches `table.identifiers` (the free write is in
`detach_answered`, line 1056), and both callers (`memory.rs:921`, `1067`)
drop the returned domain, so the return value is dead. Likewise `detach`'s
doc (`memory.rs:907-910`) says "the device leaves the header of its
iospace, its identifier word becomes free", but since D-139 the device
leaves the header only at the answer (`detach_answered`), and on a failed
unit the identifier word stays as it is (`memory.rs:918-919`).

### 18. fix (small) — `clear_mapping_pub` exists only to make a private function public

`model/src/memory.rs:249-252`

```rust
    /// `clear_mapping` for the destruction of an iospace whose unit failed.
    pub(crate) fn clear_mapping_pub(&mut self, cap: CapId) {
        self.clear_mapping(cap);
    }
```

Its doc names one use, but it is also how the scenario at
`scenarios/pass20.rs:797-798` builds a state. Making `clear_mapping`
`pub(crate)` removes the alias; same remark as findings 3 and 14.

## sched.rs

### 19. fix (small) — the doc of `hardware` is glued onto `request_due`, and `hardware` has none

`model/src/sched.rs:595-613`

```rust
    /// Due events and the hardware timer of a core: after the choice, the
    /// earliest of the instant the running context's budget ends, ...
    /// beats (D-131). An idle core with nothing armed sets no timer.
    /// The due event of the core's invalidation request, on the hardware
    /// clock: ...
    pub(crate) fn request_due(&self, core: usize) -> Option<u64> {
    ...
    pub(crate) fn hardware(&self, core: usize) -> Option<u64> {
```

The first seven lines describe `hardware` (the minimum of budget,
replenishments, timers, request, beat), but rustdoc attaches them to
`request_due`; `hardware` itself is undocumented. The text also omits one
of the instants `hardware` takes: the recovery reserve's due step on core 0
(`reserve`, line 635). Otherwise I found no defect in sched.rs: the
admission arithmetic (`bandwidth(0, 0)` is 0, `abi/src/lib.rs:864-867`),
the wake-up rule in `u128`, exhaustion and replenishment, and the bound of
the choice loop hold as written.

## table.rs

### 20. fix (small) — `write_member` says "by compare-and-swap" and writes unconditionally

`model/src/table.rs:472-477`

```rust
    /// The gate writes a member word, by compare-and-swap.
    pub(crate) fn write_member(&mut self, writer: u16, node: u16, to: Member) {
        let before = self.members[node as usize];
        self.members[node as usize] = to;
```

There is no expected value and no refusal; `write_owner`, `write_core` and
`swap_attach` in the same file do compare. Either the doc goes, or the
function takes the `before` its callers read and refuses a changed word (a
race the kernel must handle, which the model then cannot show).

### 21. question — the gate refuses a writer that is not starting, live or sealing for chunk and entry words, but not for identifier and line words

`model/src/table.rs:628` and `657` check `self.member(writer).writes()`;
`write_identifier` (`table.rs:670-680`) and `write_line` (`table.rs:728-738`)
do not, and return nothing a caller could test. Both are the same gate on
words of the living part (their docs say "The write gate on ..."). If the
contract lets a fencing or dead node's gate write these two kinds of words
(R6's clearing of a line word is named, at line 726), say so; otherwise
the check is missing, and invariant 52's journal records a write the gate
would have refused.

### 22. fix (small) — `started_node` decodes `NodeGen` by hand

`model/src/table.rs:459-461`

```rust
        (raw >> 63 == 1).then_some(((raw >> 32) as u16, raw as u32))
```

`start_request` encodes with `NodeGen::new(node, generation).raw()` (line
455); the decode repeats `NodeGen::node` and `NodeGen::generation`
(`abi/src/lib.rs:1087-1092`) instead of calling them. They agree today
(node in bits 32-47, generation in 0-31); one place to change the layout
is the point of `abi/`.

## tasks.rs

### 23. fix (small) — `stop`'s comment lists three bounded waits; `bounded()` has four

`model/src/tasks.rs:175-178`

```rust
        // A thread that waits for another node, a unit or its node's cores
        // is stopped when its call returns: its wait is not ended.
        let wait = &self.threads[&thread].wait;
        if *wait != Wait::None && !self.threads[&thread].bounded() {
```

`Thread::bounded` (`lib.rs:750-755`) also counts `Wait::Hand`, the drain of
a planned hand-over; the code is right, the comment omits it (the same list
in `thread_cancel`, `threads.rs:147-149`, does name the hand-over).
Otherwise I found no defect in tasks.rs: the first `task_revoke` call
detaches nothing and marks only threads running on other cores, later calls
wait for the marks and detach at most `REMOVAL_STEP`, as the comments say.

## threads.rs

### 24. fix — `thread_set_features` accepts a thread marked *leaving its core*, whose state is still on another core

`model/src/threads.rs:171-174`

```rust
        let changed = &self.threads[&target];
        if !changed.suspended || changed.wait != Wait::None {
            return Err(Error::Busy);
        }
```

Every other call that changes or reads a thread's saved state refuses the
mark: `thread_configure` ("a marked thread's registers are still on another
core", `threads.rs:44-50`), `thread_read_regs` (`faults.rs:164`),
`thread_write_regs` (`faults.rs:211`). `thread_set_features` changes the mask
and "the vector state is reset" (its doc), so it touches the same saved
state, and a `thread_suspend` that returned `again` leaves exactly this
state (suspended, not waiting, marked).

How I know: a scenario added to my copy of `model/src/scenarios/cores.rs`,
next to `the_registers_and_the_configuration_of_a_marked_thread_are_busy`
and built with the same `two_threads(Arch::X86_64, 2)`:

```
$ nix develop -c cargo test -p dodos-model --lib review_set_features -- --nocapture
set_features on a thread marked leaving its core: Ok(Done)
```

The existing test of the marked thread (`scenarios/cores.rs:165`) checks
read, write and configure but not set-features, so nothing pins this.

## Summary

Four findings stop the merge, or need a fix before it, because the model
does something wrong when given ordinary calls. Each was run:

- **2 (stop)**: a reserve chunk can be taken twice by the holder of the
  reserve's role (`blocks.rs:169`); the model's own invariant 53 then fails.
- **16 (stop)**: `aspace_map`/`iospace_map` count unhooked tables as free
  (`memory.rs:531`); after a removal step leaves tables unhooked, the next
  map panics at `memory.rs:190`.
- **9 (fix)**: `ioport_out` asks for `write` on the cspace capability it is
  addressed through (`debug.rs:411`).
- **24 (fix)**: `thread_set_features` accepts a thread marked *leaving its
  core* (`threads.rs:172`).

Finding 1 (split without the G5 check) and 8 (a block with frozen counts
can never be removed) were reasoned from the code, not run. The rest are
false or misplaced comments, duplicated code, and pointless wrappers.

### What I ran

- `nix develop -c ./verify` on an unchanged copy
  (`/private/tmp/dodos-pr3-B-opus`): exit 0. My test file was added after
  the run started and is not in its log (`grep -c zz_review` on the log
  gives 0).
- The four experiments named in findings 2, 9, 16 and 24, in that copy only:
  `model/tests/zz_review.rs` (findings 2 and 9), one test appended to
  `model/src/scenarios/pass19.rs` (16), one to
  `model/src/scenarios/cores.rs` (24). The shared clone was not changed.

### Files read whole

`model/src/blocks.rs`, `caps.rs`, `debug.rs`, `faults.rs`, `ipc.rs`,
`lib.rs`, `locks.rs`, `memory.rs`, `sched.rs`, `table.rs`, `tasks.rs`,
`threads.rs`, as well as `AGENTS.md`, `model/README.md`,
`.claude/skills/dodos-rust/SKILL.md`, `.claude/skills/rust-1-100/SKILL.md`
and `verify`.

### Read in part, as needed

`model/src/cores.rs` (`Started`, `start_request`, `others_hold`,
`complete`, `request_free`, `mark_leaving`, the debug fields of
`CorePart`), `model/src/check.rs` (around 700-730), `check/debug.rs`
(30-130), `check/table.rs` (200-225, 460-480), `model/src/boot.rs`
(1120-1160), `model/src/scenarios/pass19.rs` (510-560),
`scenarios/pass20.rs` (760-830), `scenarios/cores.rs` (140-195),
`model/tests/boot.rs` (635-662), `model/tests/gate_words.rs` (74-125), and
in `abi/src`: `IoPortRange`, `Ownership::may_take`, `MemoryType::for_memory`,
`bandwidth`, `firing_instant`, `FaultKind`, the x86-64 register indices,
`NodeGen`.

### Not read

The other files of `model/src` (`grants.rs`, `irq.rs`, `nodes.rs`,
`rings.rs`, `roles.rs`, `system.rs`, `units.rs`, `check/`, `scenarios/`
beyond the parts above), `model/tests/` beyond the parts above, and `abi/`
beyond the items named. Those belong to other lots.
