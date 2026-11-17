# Review of lot B (model: blocks, caps, debug, faults, ipc, lib, locks, memory, sched, table, tasks, threads)

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
Work copy `/private/tmp/dodos-pr3-B-deepseek`; no file of the clone was changed.
I read `AGENTS.md`, `model/README.md`, `.claude/skills/dodos-rust/SKILL.md`
and `.claude/skills/rust-1-100/SKILL.md` first.

## 1. `memory.rs:531` with `memory.rs:190`: an address-space map panics when a record's invalidation is still in flight

Severity: stops the merge. It is a panic reachable from public calls
on a healthy machine, and I ran it.

`model/src/memory.rs:531-532`, in `aspace_map`:

```
        let free = aspace.tables - hooked.len() as u64;
        let missing = (wanted - hooked.len() as u64).saturating_sub(free);
```

`aspace.tables` counts every table page the space ever took; the pages it
counts are, at any moment, the hooked ones, the free list, **and** the
`unhooked` ones, which are pages unhooked by the clearing of a record and
kept off the free list until the invalidation that covers them completes
(`lib.rs:656-660`, `memory.rs:182-186`, `finish_unmapping` at
`memory.rs:263-267`). So `aspace.tables - hooked.len()` is the free list
*plus* `unhooked`, and `missing` under-counts the pages the space has to
supply. `rehook_by` then pops one page per newly needed table
(`memory.rs:189-192`):

```
        for key in new {
            let page = aspace.free.pop().expect("a table on the free list");
```

and the `expect` fires.

How I know: I copied the clone and wrote two tests in the copy.

* `model/src/scenarios/units.rs`, test
  `breview_public_a_map_after_a_removal_that_waits_for_the_unit_pops_an_absent_table`,
  uses only public calls on a `three()` system whose node 0 has an iospace
  with a device: `IoSpaceMap` a one-page frame at 1 MiB, `IoSpaceMap` a
  second at 1 GiB (the first needs three tables on x86-64, the second two
  more), then
  `CapDelete` on the first frame capability (the removal waits for the
  unit, so `Error::Again`, its two tables land in `unhooked`, `free` is
  empty), then `IoSpaceMap` a third frame at 1 TiB. Result:

  ```
  thread 'scenarios::units::breview_public_a_map_after_a_removal_that_waits_for_the_unit_pops_an_absent_table' panicked at model/src/memory.rs:190:42:
  a table on the free list
  ```

  `cargo test -p dodos-model --lib breview_public` in
  `/private/tmp/dodos-pr3-B-deepseek`.

* `model/src/scenarios/pass20.rs`, test
  `breview_a_map_after_a_cleared_record_pops_a_table_the_free_list_does_not_hold`,
  reaches it with `clear_mapping_pub` and then one `ASpaceMap`; same panic
  at `memory.rs:190`.

The state is not exotic: `scenarios/pass19.rs:523`
(`a_table_unhooked_by_an_unmap_joins_the_free_list_only_at_the_completion_of_its_request`)
and `scenarios/pass20.rs:769` build the same `unhooked`-full, `free`-empty
state through `IoSpaceUnmap` and assert it.

A fix has to make the estimate ignore the unhooked pages, for example
`aspace.tables - hooked.len() as u64 - aspace.unhooked.len() as u64`, or
have `rehook_by` return a shortage that `aspace_map` turns into
`no_memory`. Note that nothing else guards it: `check` invariant 37 only
requires `tables >= hooked.len()` (`check/memory.rs:123`), which the state
satisfies.

## 2. `debug.rs:6-11`: the module doc says code 4 is never traced, and `fail_unit` traces it

Severity: should be fixed (a comment that is false).

`model/src/debug.rs:6-11`:

```
//! What the kernel traces in the model: its start (code 1), a fault
//! recorded in a thread (5), a failure of the node (6), a transition of a
//! member or role word it made (9), an ownership word that failed its
//! check when the gate read it (10), and the entries suppressed (3). DMA
//! faults (2), units that do not confirm (4), hardware errors (7) and
//! interrupts on unclaimed vectors (8) have no source in the model.
```

`model/src/units.rs:781-791` is the source of code 4 — its own comment is
"A unit that has not confirmed within `IOMMU_WAIT_NS` has failed ... writes
code 4 in its kernel ring":

```
            self.trace(TraceCode::UnitTimeout, None, [unit, 0, 0]);
```

`TraceCode::UnitTimeout` is 4 (`abi/src/debug.rs:48`). Code 11 (`Refused`)
is traced too, at `rings.rs:496`, `rings.rs:522`, `rings.rs:530` and
`units.rs:532`, and the list does not mention it at all.

How I know: `grep -rn "TraceCode::" model/src/ | grep -v "^./debug.rs"`
gives those five call sites; `grep -rn "DmaFault\|HardwareError\|StrayVector"
model/src/` gives nothing, so 2, 7 and 8 really have no source and the
sentence is right for those three only. The enum has thirteen variants
(`abi/src/debug.rs:45-63`); the paragraph accounts for ten of them and
leaves `Refused` out even though the model emits it, and `UserText` and
`UserEmit` out even though they are the two codes of the user ring that
`debug_write` (`debug.rs:351`) and `trace_emit` (`debug.rs:373`) write.

## 3. `lib.rs:1` and `lib.rs:15-21`: the crate doc still describes a model of one core and one node

Severity: should be fixed (false comments on the front page of the crate).

```
//! Executable reference model of the DodOS kernel, for one core.
...
//! Not modelled: ... the kernel's own time,
//! taken as zero; more than one node (the waiting-for-the-core-group state
//! is never entered); and the groups not specified (cores, debugging,
//! `ioports`), whose calls return `unsupported`.
```

Three claims are false against the code in the same file and its
neighbours:

* "for one core": `Model` holds `cores: Vec<cores::CorePart>`
  (`lib.rs:1059`), `width()`, and `Model::check` has rules for a node of
  several cores (`check/node.rs`). `model/README.md` opens with the shape
  of D-128, D-129 and D-131.
* "more than one node ... is never entered": `model/src/nodes.rs` (2016
  lines) and `model/src/system.rs` implement nodes, `node_start`,
  membership, the fence and the registers, and `Wait::Cores(usize)`
  (`lib.rs:787`) is entered — `cores.rs:359` marks the wait.
* "the groups not specified (cores, debugging, `ioports`), whose calls
  return `unsupported`": `dispatch_call` (`lib.rs:1456-1640`) routes
  `NodeStart`, `NodeStop`, `NodeStatus`, `NodeIdle`, `NodeWatch`,
  `NodePerf`, `DebugWrite`, `TraceEmit`, `IoportIn`, `IoportOut`,
  `IoportsIssue` and `EntropyRead` to implementations; `debug_write` and
  `trace_emit` (`debug.rs:319-368`) return `Done` on every architecture,
  and `ioport` returns `Unsupported` only when the architecture is not
  x86-64 (`debug.rs:426-428`).

`model/Cargo.toml:6` repeats the first line: `description = "Executable
reference model of the DodOS kernel, one core"`.

## 4. `sched.rs:1090-1104` against `lib.rs:453`: `timer_set` returns 0 for a timer that was armed

Severity: question.

The result type says (`lib.rs:452-454`):

```
    /// `timer_set`, `timer_cancel`: 1 if the timer was armed, 0 otherwise.
    WasArmed(u64),
```

`disarm`, which both calls use (`sched.rs:1093-1104`):

```
    /// `timer_set` and `timer_cancel`: an armed timer whose firing instant
    /// is not after now fires first; then the arming, if any, is cancelled.
    /// Returns 1 if the timer was still armed.
    fn disarm(&mut self, timer: ObjId) -> u64 {
        if self.timers[&timer].is_some_and(|armed| armed.instant <= self.now) {
            self.fire(timer);
        }
        let Some(armed) = live(&mut self.timers, timer).take() else {
            return 0;
        };
```

When the timer was armed and its instant is not after now, `fire` takes
it and `disarm` returns 0, so `timer_set` answers `WasArmed(0)` for a
timer that *was* armed. The two doc comments disagree ("armed" against
"still armed"), and a kernel that checks the answer — "a `timer_set` on an
armed timer is refused" — would read the opposite of the contract's word.
I did not find the contract's sentence, so I report the disagreement
rather than the choice.

## 5. `memory.rs:593-599` against `memory.rs:622`: `class_of` reads one page's class, its doc says every page

Severity: question.

```
    /// ... A leaf
    /// smaller than a chunk reads the class byte of each page it covers; ...
```

```
        match classes.range(start / small..end.div_ceil(small)).next() {
            Some((_, &class)) => class,
            None => PageClass::DATA,
        }
```

`.next()` is the first stored class in the leaf's range, not the class of
each page it covers. The two agree today only because `Table::classes`
stores nothing but table classes and iospace roots (`table.rs:306-310`)
and every one of those refuses a leaf (`PageClass::permits`,
`abi/src/machine.rs:230-237`); the day a permitting class is stored — a
read-only page, which `permits` would allow for a read-only leaf — the
first-page read accepts a leaf whose later pages it should refuse. The
coupling is not stated anywhere near the code.

## 6. `blocks.rs`: the chunks of a run are computed in three places, one of them unchecked

Severity: question (duplication, and an unchecked addition that only its
callers keep safe).

`blocks.rs:17-21`:

```
    fn run(&self, place: u64, size: u64) -> std::ops::Range<u64> {
        let shift = self.table.geometry.chunk_shift();
        place >> shift..(place + (1 << size)) >> shift
    }
```

`blocks.rs:331-333`, inside `mapped_block`, by hand:

```
                let chunks = untyped.base >> shift..(untyped.base + untyped.bytes) >> shift;
```

`blocks.rs:431-433`, `FreedRun::chunks`:

```
        (self.base >> shift..(self.base + self.bytes) >> shift).collect()
```

`dodos-rust` ("a check that several operations share is written once")
asks for one. `run` also adds `place + (1 << size)` without a check; every
call of it happens after the `checked_add` of `memory_take`
(`blocks.rs:46-49`), so it is safe today, but neither its signature nor
its comment says so, and it is the function a new caller would reach for
first.

## 7. `blocks.rs:403-407`: `remove_block_cap` is `remove_leaf` under another name

Severity: question (a wrapper that adds nothing; two call sites,
`blocks.rs:212` and `blocks.rs:315`).

```
    /// The capability of a block, removed by `memory_give` or
    /// `memory_split`: its slot becomes empty and the untyped is destroyed.
    fn remove_block_cap(&mut self, cap: crate::CapId) {
        self.remove_leaf(cap);
    }
```

`remove_leaf` (`caps.rs:1061`) is already crate-visible and its own doc
already says "Removes a capability that has no descendant, and empties its
slot", which is the sentence the wrapper repeats.

## 8. `caps.rs:1019-1029` and `caps.rs:1042-1052`: the detach bookkeeping of an iospace is written twice

Severity: question (duplication, inside one `match`).

In `undo`, the arms `(None, Some(cap))` and `(None, None)` of the iospace
match open with the same five lines:

```
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

They differ only after that, so the wait belongs before the match on
`(device, records.last())`.

## 9. `caps.rs:391-395`: the comment on `fits` is wider than the check

Severity: question.

```
    /// The derivation tree, checked with the plain arguments each time a
    /// capability is placed in a slot of `space`: the tree is at most 64
    /// deep, and a capability space holds only what is deeper than itself.
```

`caps.rs:406-410`:

```
        let deep_enough = match kind {
            ObjectKind::Untyped => depth >= self.depth(own),
            ObjectKind::CSpace if root => depth > self.depth(own),
            _ => true,
        };
```

Only a child untyped and the root capability of another capability space
are compared with the space's own depth; every other kind is accepted at
any depth. The next sentence of the comment ("The root capability of
another space must be deeper than the root capability of `space`, and an
untyped capability not less deep") is exactly what the code does, so the
first sentence is what a reader will get wrong. If the contract says only
that, the sentence should go; if it does not, `_ => true` is the bug.

## 10. `debug.rs:523-525`: a port range word that fails its check becomes every port

Severity: question (a fail-open default; unreachable through the calls I
found, so a matter of what happens the day it is reachable).

```
pub(crate) fn range_of(badge: u64) -> IoPortRange {
    IoPortRange::new(badge & 0xFFFF, badge >> 16 & 0xFFFF).unwrap_or(IoPortRange::ALL)
}
```

`IoPortRange::new` is `None` when `first > last`
(`abi/src/machine.rs:1398-1404`) and `ALL` is `0xFFFF << 16`, the whole
port space (`abi/src/machine.rs:1395`), so a word that does not decode
gives the widest range instead of the narrowest. The two places that set
the badge, `ioports_issue` (`debug.rs:460-480`) and the start-up capability
of `boot.rs:1143`, write only `IoPortRange::new(..).raw()` or `ALL.raw()`,
whose round trip is total, so I could not build a state that reaches the
`unwrap_or`; the contrast is `Table::line_word` (`table.rs:719-723`),
which turns a word that fails its check into a *refused* word.

## 11. `table.rs:656-665`: the gate on a device entry does not compare and swap, the gate on a chunk does

Severity: question.

```
    pub(crate) fn write_entry(&mut self, writer: u16, index: usize, entry: DeviceEntry) -> bool {
        if !self.member(writer).writes() {
            return false;
        }
        let before = self.devices[index].owner.raw();
        let write = self.journal(writer, Word::Entry(index), before, entry.owner.raw());
        Arc::make_mut(&mut self.devices)[index] = entry;
        self.writes.push(write);
        true
    }
```

against `table.rs:621-635`, `write_owner(writer, chunk, before, after)`,
which refuses when `self.owners[chunk] != before`. The two are both "the
write gate on the ownership word of ..." and both are asserted on by their
callers (`blocks.rs:387`, `blocks.rs:393`), but only the chunk one can
fail on a word that changed under the writer, so `assert!` on
`write_entry` can only ever test the member-word rule. Either the entry
write is not a compare-and-swap in the contract (say so in its doc) or the
model does not check the rule it claims for the gate.

## 12. `locks.rs:117-135`: one gate lock for the whole event, where the module doc says one per gate call

Severity: question.

`locks.rs:6-10` says "what it records is what a kernel takes: the node lock
from the entry of the event (after its lock-free part) to its exit, and
the gate lock inside it for each gate call".

`end_locks` computes `let gate = !self.table.writes.is_empty() || ... ||
*self.table.gated;` and pushes a single `Lock(Gate)`/`Unlock(Gate)` pair
before the event's steps. An event with one gate call and an event with
forty are the same trace, so the trace cannot judge the count of gate
locks that D-042 talks about; only their presence. The pair is also
recorded before the event's steps, not where the gate call happened.

## 13. `faults.rs:99-104`: an endpoint object is used as the capability space of the fault window

Severity: question (a fallback a reader has to prove harmless).

```
        // An empty receive range names no slot; its space is not looked at.
        let window = Window {
            cspace: faulting.cspace.unwrap_or(endpoint),
            first: 0,
            count: 0,
        };
```

If the faulting thread has no capability space, `window.cspace` is an
*endpoint* identity, and `Window.cspace` is typed as a capability space.
It is harmless while the range is empty: `deliver` reads
`self.cspaces.get(&window.cspace)` (`ipc.rs:524-530`) and takes the `None`
branch towards "not empty", and with `caps.is_empty()` the `filter` on the
count `caps.len() <= window.count as usize` is `0 <= 0` (`ipc.rs:549-553`),
so no slot is looked at and no capability is placed. But the comment
states the conclusion and not why the type is broken there, which is what
a newcomer has to reconstruct.

## Files read whole

`model/src/blocks.rs`, `caps.rs`, `debug.rs`, `faults.rs`, `ipc.rs`,
`lib.rs`, `locks.rs`, `memory.rs`, `sched.rs`, `table.rs`, `tasks.rs`,
`threads.rs` — the whole lot, in the order of the brief. Also whole:
`AGENTS.md`, `model/README.md`, `.claude/skills/dodos-rust/SKILL.md`,
`.claude/skills/rust-1-100/SKILL.md`.

## Read only in part, to understand the lot

`model/src/boot.rs` (the start-up build, `add`, the frames),
`model/src/check/node.rs` (`check_locks`, `check_epoch`),
`model/src/check/memory.rs` (invariants 35-39), `model/src/cores.rs`
(`post`, `start_request`, `pay`), `model/src/grants.rs` (the remote's
depth), `model/src/rings.rs` and `units.rs` (the trace calls),
`model/src/scenarios/mod.rs` (`N`), `scenarios/pass19.rs`,
`scenarios/pass20.rs`, `scenarios/units.rs`, and from `abi/`:
`lib.rs`, `machine.rs`, `debug.rs`, `features.rs`, `x86_64.rs`, by
sections.

## Not read whole, and mostly not read at all

Everything else of the two crates: `boot.rs`, `check.rs` and `check/`,
`cores.rs`, `grants.rs`, `irq.rs`, `nodes.rs`, `rings.rs`, `roles.rs`,
`system.rs`, `units.rs` and the scenarios folder whole, `abi/` whole, and
`model/tests/` — they are other lots. I did not run `nix develop -c ./verify` (about six
thousand lines of tests I cannot judge); I built the crate and ran the two
tests I added, in the copy, as quoted in finding 1.
