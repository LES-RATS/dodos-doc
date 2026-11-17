# Review of lot F1, by deepseek

Repository `/private/tmp/dodos-pr3-final` (branch `model`, head `6312868`),
pull request `origin/main...HEAD`. My lot: `model/tests/calls.rs`,
`model/tests/common/mod.rs`, `model/tests/property.rs`, read whole and in
that order, after `AGENTS.md`, `model/README.md`,
`.claude/skills/dodos-rust/SKILL.md` and `.claude/skills/rust-1-100/SKILL.md`.

I worked in a copy, `/private/tmp/dodos-pr3-F1-deepseek`; the clone the
reviewers share was left untouched. Commands and results are quoted under
each finding; the two suites I touch are green as they stand:

```
$ cargo test -p dodos-model --test calls      -> 347 passed; 0 failed (0.40 s)
$ cargo test -p dodos-model --test property   -> 15 passed; 0 failed (7.79 s)
$ DODOS_PAGE=32k cargo test -p dodos-model --test calls --test property
   -> both binaries pass (property: 15 passed, 35.85 s)
```

---

## 1. `Reached::dying` is an array of 19 indexed by a kind that has 21 values: an out-of-bounds panic in the middle of a run — should be fixed

`model/tests/property.rs:1631-1632`

```rust
/// Steps after which an object of each kind was dying, by kind.
dying: [u32; 19],
```

`model/tests/property.rs:1729-1734`

```rust
let mut kinds = census.dying;
kinds.dedup();
kinds
    .iter()
    .for_each(|&kind| self.dying[kind as usize] += 1);
```

`ObjectKind` in `abi/src/lib.rs:324` has 21 variants, `MemoryControl = 19`
and `Role = 20` (`ObjectKind::ALL: [Self; 21]`, `abi/src/lib.rs:355`).
`Census::dying` is "the kind of each object that is dying"
(`model/src/check.rs:26-27`), for every kind: any object can be marked
dying, because `cap_delete` marks the capability it is given
(`model/src/caps.rs:246-249`) whatever the kind of its object. So the
first step of a `cap_delete` on the root capability of a `memory_control`
or of a `role` that has children puts `ObjectKind::MemoryControl` or
`ObjectKind::Role` into that vector, and `self.dying[19]` or
`self.dying[20]` panics with "index out of bounds". `MADE`
(`model/tests/property.rs:171-181`) reads only the first nine entries, so
the array size and the kinds it means to count do not agree.

How I know, in the copy, with a scratch test (`model/tests/f1probe.rs`,
deleted afterwards). First, the start-up state of `property.rs`
(`start()`: `SchedConfigure` of the boot context, `take_run(chunk + 5)` into
slot 107, `take_device` into slot 64, then `CapMove` of that capability to
slot 108),
40 endpoints retyped from the block in slot 107, then
`CapDelete(own(START_SLOT_MEMORY_CONTROL))`:

```
cap_delete of the memory_control root: Err(Again)
dying [MemoryControl, Untyped], deduped [MemoryControl, Untyped]
   kind MemoryControl = 19 (array is [u32; 19])
   kind Untyped = 0 (array is [u32; 19])
```

Second, 33 copies of the `role` capability in slot 19, then
`CapDelete(own(19))`:

```
cap_delete of the role root: Err(Again)
dying [Role] deduped [Role]
   kind Role = 20 -> dying[20]
thread 'probe_role_root_with_33_copies' panicked at model/tests/f1probe.rs:33:9:
index 20 is beyond [u32; 19]
```

The property generator can walk into the first of these two states without
any help:
`4 if self.rng.below(300) == 0 => Syscall::CapDelete(own(self.rng.below(26) as u32))`
(`model/tests/property.rs:826`) names slot 12, the memory control, among
26 possible ones, and a `derive` of that capability (`held(class)`,
`bound()`) gives it children, so the removal returns `again` instead of
finishing in one call. The 24 seeds of the branch do not happen to draw it
— I ran them, they pass (see the top) — so this is a latent crash, not one
that the branch ships broken: a different `SEEDS`, one more arm in the
generator, or one different random path turns the whole suite into an
index-out-of-bounds panic, and no count can ever be recorded for those two kinds. The fix is the size of the array (`ObjectKind::ALL.len()`,
or a counted map) rather than a wider constant.

## 2. `dedup` on `Census::dying` counts one step twice for a kind — should be fixed

`model/tests/property.rs:1729-1731`

```rust
let mut kinds = census.dying;
kinds.dedup();
```

The comment on the field says "steps after which an object of each kind was
dying". `Census::dying` is built from `self.objects.iter()`
(`model/src/check.rs:98`, `109`), and `objects` is a `BTreeMap` keyed by
`ObjId`, so the vector is in object order, not in kind order: two dying
objects of one kind are adjacent only if nothing else died between them in
creation order. `Vec::dedup` removes consecutive repeats only, so a step
whose dying objects are, in `ObjId` order, an untyped, an endpoint and
another untyped adds 2 to `dying[Untyped]` instead of 1.

How I know, in the copy, with a scratch test: two blocks taken with
`MemoryTake`, ten endpoints retyped from the first and 33 from the second,
33 copies of one endpoint of the first block, then `CapDelete` of the two
blocks' root capabilities:

```
cap_delete 120: Err(Again); dying [Untyped, Endpoint]; deduped [Untyped, Endpoint]
cap_delete 121: Err(Again); dying [Untyped, Endpoint, Untyped]; deduped [Untyped, Endpoint, Untyped]
counted by kind: [2, 0, 0, 0, 0, 0, 1, 0, 0]
```

The last line is exactly what `Reached::count` does with that state, and it
reports two "steps" of a dying untyped for one step. Every floor of
`objects_of_every_kind_are_seen_dying` (`model/tests/property.rs:2472`) is a
measured count of this same number, so the floors for the kinds that are
often dying together (untyped, frame, endpoint, reply) are measured on an
inflated count and guard less than they claim. A `BTreeSet` of the kinds,
or sorting before dedup, or counting per object instead, fixes it.

## 3. `caps_without` has two arms that always return the same value, and a doc line that describes a difference that does not exist — should be fixed

`model/tests/calls.rs:684-692`

```rust
/// Every right but one.
/// Every right but `right`, and without `exec` but for an `exec` asked
/// for: the start-up capabilities of the tests have no `exec`.
fn caps_without(right: Rights) -> Rights {
    match right == Rights::EXEC {
        true => Rights::ALL.without(right),
        false => NOT_EXEC.without(right),
    }
}
```

`NOT_EXEC` is `Rights::ALL.without(Rights::EXEC)` (`model/tests/calls.rs:27`)
and `without` is `Self(self.0 & !other.0)` (`abi/src/lib.rs:276-278`), so
the first arm is `ALL.without(EXEC)` = `NOT_EXEC` and the second is
`NOT_EXEC.without(right)`; for `right == EXEC` the two are the same value,
and for every other input the second arm is the only one that runs.
`caps_without(r)` is therefore `NOT_EXEC.without(r)` for every argument, the
`match` decides nothing, and the clause "and without `exec` but for an
`exec` asked for" tells a reader that asking for `EXEC` yields something
with `EXEC` in it, which it does not — the `EXEC` bit is cleared either way.
The first doc line is also a left-over: two doc sentences, the first one
replaced by the second and still there.

I did not find a caller that depends on the difference: the callers at
`model/tests/calls.rs:1668`, `1675`, `1677`, `1686`, `1689`, `3658`, `3663`
assert `caps_without(Rights::EXEC)` and would pass with the simplification.
Writing `NOT_EXEC.without(right)` alone, with one sentence of comment, says
what the tests rely on.

## 4. Two functions map a logical slot number to a real one and disagree — question

`model/tests/common/mod.rs:28-36`

```rust
pub const fn slot(index: u32) -> u32 {
    match index {
        0..=18 => index,
        19 => START_UNTYPED,
        20 => UNTYPED,
        21 => DEVICE,
        _ => index + 64,
    }
}
```

`model/tests/calls.rs:32-39`

```rust
const fn shifted(index: u32) -> u32 {
    match index {
        0..16 => index,
        16 => common::UNTYPED,
        17 => common::DEVICE,
        _ => index + 64,
    }
}
```

Both files number the slots of the same start-up space, and they disagree
on every input from 18 to 21: `common::slot(18) = 18`, `shifted(18) = 82`;
`common::slot(19) = 24`, `shifted(19) = 83`; `common::slot(20) = 25`,
`shifted(20) = 84`; `common::slot(21) = 64`, `shifted(21) = 85`. `calls.rs`
only ever feeds its own `shifted`, so nothing is broken today, but
`common::slot` exists for exactly this and six other test files use it
(`faults.rs:17`, `irq.rs:17`, `memory.rs:25`, `sched.rs:25`, `tasks.rs:20`,
`verify7_deepseek.rs:25`). A reviewer who has read `common/mod.rs` — whose
module comment gives the layout of the same space — then reads
`via(30, 5)` in `calls.rs` and has to unlearn the mapping. Either `calls.rs`
uses `common::slot` with its own numbering written down, or the two
numberings are given names that cannot be confused (`class of the calls
file` against `class of the shared module`).

## 5. The comment on the sweep of a dying space is off by one slot — question

`model/tests/calls.rs:3469`

```rust
    // Slot 130 is the 129th that the sweep reaches.
    k.ok(retype(UT, Notify, 0, via(30, 130)));
```

The sentence below it, at `model/tests/calls.rs:3475-3476`, says "The first
call examined 128 slots, its own among them, and stopped before the
notify". `Model::swept` starts the sweep at slot 1 and spends one of the
128 for every slot it moves past, its own slot included
(`model/src/caps.rs:848-872`), so the first call moves past slots 1 to 128
and the next slot it looks at is 129. Slot 130 is the 130th, not the 129th.
The neighbouring test says the same thing the other way: "Slots 1 to 128
are the 128 the call examines" (`model/tests/calls.rs:4965-4966`). The
assertion of the test is right either way — with slots 1 to 128 spent, the
notify at 130 is not reached, and if the space's own slot did not count the
sweep would spend slots 1-4 and 6-129 and reach it — so only the comment
misleads.

## 6. The base of ordinary memory is `memory[4]`, unverified, in two files — question

`model/tests/common/mod.rs:62`

```rust
    let machine = dodos_model::Machine::example_on(geometry);
    let ram = machine.memory[4].base;
    // Floors of 2 × 3 chunks and 2 reserves of 1 chunk: 8 chunks.
    let free = ram + 8 * chunk;
```

`model/tests/property.rs:102-105`

```rust
/// The base of the ordinary memory of the machine past its floors' start.
fn ram() -> u64 {
    Machine::example_on(geometry()).memory[4].base
}
```

`Machine::memory` is a `Vec<Region>` and each `Region` carries its
`RegionKind` (`model/src/boot.rs:109-115`, `260-292`); the fifth entry is the
usable one today, and nothing in either place says why, or checks it. A
region inserted before it in `Machine::example` moves all of these places
onto another region with no error, only a `MemoryTake` that either fails or
succeeds somewhere else. The same holds for the "+ 8 chunks" ("Floors of
2 × 3 chunks and 2 reserves of 1 chunk") and for the duplicate of this
lookup in `property.rs`. `memory.iter().find(|r| r.kind == RegionKind::Usable && r.len > ...)`
would keep the two files honest, and the offset belongs next to the machine
that defines the floors. Not a defect of this branch: a trap for the next
one.

## 7. `Generator::spawn` takes a `&mut Plan` it never uses — question

`model/tests/property.rs:1277` and `1291`

```rust
    fn spawn(&mut self, plan: &mut Plan) -> Vec<Syscall> {
...
        let _ = plan;
```

Every other script takes the plan and writes to it; this one takes it and
throws it away, which is why the `let _ = plan;` is there. Either the script
should record the slots it fills (`plan.used`, as `spare` does for the
others) so that `tidy` empties them, or it should take no plan at all. As it
stands the `let _ = plan;` is the only place in the file that suggests a
parameter was added and then not used.

## 8. Call names are compared to bare integers in the middle of the run — question

`model/tests/property.rs:2216`, `2227`, `2228`, `2237`, `2252-2253`

```rust
        if name == 19 {
...
        reached.retype_unsupported += (name == 5 && outcome == Err(Error::Unsupported)) as u32;
        if name == 2 || name == 3 {
...
            (Some(_), Ok(_)) if name == 10 => reached.called += 1,
            (Some(_), Ok(_)) if name == 12 => reached.answered += 1,
```

`19` is `thread_cancel`, `5` is `untyped_retype`, `2`/`3` are `cap_delete`
and `cap_revoke`, `10`/`12` are `call` and `reply_recv` — the reader has to
count the entries of `NAMES` (the 64-line array at
`model/tests/property.rs:184`) to check each one, and the file already has
the mechanism to avoid that: `BLOCKING: [usize; 4] = [10, 11, 12, 15]`
(`model/tests/property.rs:255`). A wrong number here switches off a
coverage count silently — a `name == 11` where `12` was meant loses
`answered` with no test failing, unless the floor catches it. Named
constants next to `BLOCKING` would make these lines readable and checkable.

## 9. A debug print of the whole `Reached` is left in the seeds' initialiser — question

`model/tests/property.rs:2424`

```rust
        println!("{reached:#?}");
```

`seeds()` runs the 24 seeds once and prints the whole derived `Reached`
structure, some two hundred lines, on every `cargo test -- --nocapture` and
in CI's log. The README documents `DODOS_COUNTS` for the explorations
(`model/README.md`, "Tests"); the counters here have no such switch. Low
weight, but it is the one line of the file that exists for a debugging
session rather than for a check.

---

## What I read whole

- `model/tests/calls.rs` (all 5,574 lines)
- `model/tests/common/mod.rs` (74 lines)
- `model/tests/property.rs` (all 2,652 lines)
- `AGENTS.md`, `model/README.md`, `.claude/skills/dodos-rust/SKILL.md`,
  `.claude/skills/rust-1-100/SKILL.md`

## What I read only in part, to understand my own files

`model/src/caps.rs` (the removal, the sweep, `cap_delete`,
`untyped_retype`'s size rules), `model/src/check.rs` (the census and the
invariants), `model/src/boot.rs` (`Machine::example`), `abi/src/lib.rs` and
`abi/src/start.rs` (`ObjectKind`, `FaultKind`, `Rights`, the start-up slot
numbers), `verify`, and the `grep`s of the other test files that showed who
else uses `common::slot`. I did not read whole: the rest of `model/src`
(`rings.rs`, `nodes.rs`, `units.rs`, `roles.rs`, `locks.rs`, `system.rs`,
`memory.rs`, the scenarios, and the fourteen other files of `model/tests`),
`abi/` in full, or any file of the repository outside my lot.

## What I could not understand

Nothing in my lot resisted reading. The two places where I had to go back
and forth are the arithmetic of the sweep budget of a dying space
(`slot_of_the_root_capability_of_a_dying_space_counts_as_examined`,
`wake_of_a_reply_object_does_not_count_as_an_examined_slot`,
`removal_examines_at_most_128_slots_of_dying_spaces_per_call`), which mixes
"32 units" with "128 slots" and is only clear after reading
`Model::remove`, `next_removed` and `swept`; and the interaction of
`Reached::count`'s census-based counters with the per-call bookkeeping in
`run()`, where the value of `dying_copies`, `served`, `lost` and friends
is a count of steps, not of events, and the comment on each field is what
tells them apart.
