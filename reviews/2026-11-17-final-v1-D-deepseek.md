# Review of lot D (deepseek): the check and its scenarios

Repository `/private/tmp/dodos-pr3-final` at head `6312868`, the diff
`origin/main...HEAD`. The thirteen files of the lot were read whole, in the
order the brief gives them.

Commands run, in a copy at `/private/tmp/dodos-pr3-D-deepseek` (the clone is
untouched): `cargo test -p dodos-model --lib scenarios::checker` → `41 passed;
0 failed`, and two scratch tests, each of them reverted afterwards.

## Findings

### 1. `ring_holds` panics instead of reporting when a ring's next sequence is 0 — should be fixed

`model/src/check/debug.rs:16-25`

```rust
fn ring_holds(ring: &[TraceEntry], next: u64, entries: u64) -> bool {
    let placed = ring.iter().enumerate().all(|(index, entry)| {
        entry.seq == 0
            || (entry.seq < next
                && entry.seq + entries >= next
                && (entry.seq - 1) % entries == index as u64)
    });
    let last = next == 1 || ring[((next - 2) % entries) as usize].seq == next - 1;
    next >= 1 && placed && last
}
```

The guard `next >= 1` is the last term of the returned conjunction, so it is
evaluated after `last`, and `last` computes `next - 2` as soon as `next != 1`.
For `next == 0` that subtraction underflows. The function is the body of
invariants `88: kernel ring` and `88: user ring`, and its only caller
`check_area` (`model/src/check/debug.rs:59-66`) exists to name a bad state; with
`next_* == 0` the check panics instead. Unreachable from a run of the model —
`DebugArea::write` (`model/src/debug.rs:82-93`) starts `next_*` at 1 and only
adds — but a check must not die on a state it was asked to judge, and the fix
is to put `next >= 1` first.

How I know. I appended this test to my copy of
`model/src/scenarios/checker.rs`:

```rust
#[test]
fn scratch_next_zero() {
    let mut m = S::two();
    m.sys.edit_table(|t| { std::sync::Arc::make_mut(&mut t.crash).areas[0].next_user = 0; });
    let report = m.sys.check();
    println!("SCRATCH: {report:?}");
}
```

`cargo test -p dodos-model --lib scenarios::checker::scratch_next_zero -- --nocapture`
gave `panicked at model/src/check/debug.rs:23:35: attempt to subtract with
overflow`. The test is not in the repository.

### 2. The G6 scenario never reaches G6, and a substring fallback hides it — should be fixed

`model/src/scenarios/checker.rs:541-547`

```rust
    let report = m.sys.check().expect_err("spoiled");
    assert!(
        report.ends_with("G6: a grant freed while its holder translates to it")
            || report.contains("58"),
        "{report}"
    );
    let _ = Member::new;
```

The test is `a_grant_freed_while_its_holder_translates_to_it_is_reported`
(`model/src/scenarios/checker.rs:520`); its comment (`:523-524`) says it spoils
"a use entry of node 1 that counts a leaf under a grant of node 0 that node 0
no longer has", so the machine's G6 (`model/src/check/machine.rs:163-178`) is
what the name promises and what the first branch asserts. It is never reached:
the node's own invariant 58 (`model/src/check/table.rs:431-434`, the leaves of a
use entry) fires first and the `|| report.contains("58")` accepts it. That
fallback is also a plain substring test on a number the report format carries as
an invariant number, so any report containing "58" anywhere satisfies it.

How I know. I printed the report from my copy and ran the same test with
`--nocapture`: `REPORT IS: node 1: 58: leaves of a use entry`. The first branch
is dead, and G6 is guarded by nothing in this test.

`let _ = Member::new;` on the next line is dead code — it references a
constructor for its own sake (the `Member` import at `:13` has no other use), so
the import can go with it.

### 3. Two checks in `check_tasks` can never fail — should be fixed

`model/src/check/tasks.rs:55`

```rust
        ensure(true, "50: running thread of a revoked task")
```

A literal `ensure(true, …)` at the end of the function, duplicating the message
raised at `:49-53`. It reads as a rule and is not one.

`model/src/check/tasks.rs:32`

```rust
        ensure(!ids.contains(&TaskId::NONE.raw()), "49: task identifier")?;
```

`ids.insert(...)` is the last conjunct of `given` (`:20-22`) and `&&`
short-circuits, so `ids` only ever holds raw identifiers whose `counter()` lies
in `1..=self.task_counter`. `TaskId::NONE.raw()` is 0 (`abi/src/lib.rs:1046`)
and `1..=counter` never contains 0: the line cannot fail. It also reuses the
message of `:23`, which the one test that names "49: task identifier" already
exercises, so nothing distinguishes them.

This matters more here than elsewhere: `model/src/scenarios/checker.rs:1-5`
says the file exists so that "a check that cannot fail is caught here", and both
lines cite an invariant number no bad state can produce.

### 4. Rules of this lot that no test feeds a bad state — should be fixed (one group)

`checker.rs`'s header promises one spoiled state per invariant of a node of
several cores and of the whole machine. I took every invariant message string of
the nine check files in the lot and looked for it anywhere else in the
repository; these occur only where they are raised:

- `model/src/check/node.rs:163` — `"TLB: the state word of a request"` (the
  state word reads *in use* exactly while the request is, D-135).
- `model/src/check/node.rs:173` — `"TLB: a barrier that invalidates, or an
  invalidation that is a barrier"`.
- `model/src/check/node.rs:182` — `"epoch: a barrier beyond the kernel epoch"`.
- `model/src/check/node.rs:319` — `"epoch: raised by more than one at a time"`.
- `model/src/check/node.rs:329` — `"epoch: the node's epoch is not its last raise"`.
- `model/src/check/node.rs:340` — `"epoch: word 6 of an untyped's root slot is
  not the epoch its watermark became ready at"`.
- `model/src/check/node.rs:360` — `"credits: more sends than SENDS_PER_PEER"`.
- `model/src/check/machine.rs:152` — `"G4: a leaf count below its leaves"`.
- `model/src/check/table.rs:331` — `"54: block of no entry"`.
- `model/src/check.rs:344` — `"88: an attach word with no identifier word or
  root beside it"`.
- `model/src/check.rs:827` — `"18: a watermark ready to return under a live
  object"`.

The list is not "pass 17 was skipped": WINDOW has a test
(`model/src/scenarios/cores.rs:68`) and two epoch messages do
(`model/src/scenarios/pass20.rs:143,155`). But the eleven above are unguarded,
and the first two are rules the model claims for D-135 and D-138.

### 5. The check re-implements `memory::tables`, and the two must agree by hand — question

`model/src/check/memory.rs:110-123`

```rust
            let span = |k: u32| u128::from(geometry.page()) * u128::from(geometry.entries).pow(k);
            let levels = match self.iospaces.contains_key(&id) {
                true => (1..=64)
                    .find(|&k| span(k) >= 1u128 << self.machine.io_width)
                    .unwrap_or(64),
                false => geometry.levels,
            };
            let mut hooked = BTreeSet::new();
            for (&at, t) in &space.translations {
                for k in (1..levels).filter(|&k| span(k) > bytes(t.size)) {
                    hooked.insert((k, u128::from(at) / span(k)));
                }
            }
            ensure(space.tables >= hooked.len() as u64, "37: tables of a space")?;
```

`model/src/memory.rs:30-45` computes the same set for the calls (`leaf` from the
page shifts, keys `at >> (page + per_level * level)`), and
`model/src/check/tests.rs:1569,1581` reach for *that* helper when they build
their bad state, so the two are meant to be one rule. They agree today: I
checked the inequality for the three geometries of `model/src/boot.rs:212-239`
(4 KB with *E* = 512, 16 KB with *E* = 2,048, 32 KB with *E* = 4,096), where
`span(k) > bytes(size)` and `k >= leaf` are the same condition. Nothing keeps
them in step, and `dodos-rust` says "a check that several operations share is
written once"; the check could call `crate::memory::tables(...)` with its own
`levels`.

### 6. `35`'s sentence says "1 to 512 pages"; the check holds 1 to *E* — question

`model/src/check/memory.rs:14-15`

```rust
    ///     size of the frame; a record maps 1 to 512 pages that are in its
    ///     frame, inside the user range, and no two translations overlap;
```

The check (`model/src/check/memory.rs:68-71`) is
`count >= 1 && first.checked_add(count).is_some_and(|end| end <= frame.pages)`,
and `frame.pages` is bounded by `geometry.entries` (*E*,
`model/src/check.rs:850`). 512 is *E* only on the 4 KB geometry: on the 16 KB
geometry *E* is 2,048 and on the 32 KB one 4,096
(`model/src/boot.rs:212-239`), and `verify` runs these tests on all three. The
doc of invariant `34` ten lines later in `check.rs` (`:285`) already says
"1 to *E* pages", so two neighbours in the same lot disagree.

### 7. A test whose name and comment describe a case it does not build — question

`model/src/check/tests.rs:2567-2578`

```rust
/// 88: the identifier word of an attached device names its node.
#[test]
fn an_attached_device_whose_identifier_word_is_not_its_nodes_is_reported() {
    let broken = spoiled(|m, _| {
        m.table
            .identifiers
            .insert(4, Ownership::free(Owner::Unclaimed).raw());
        let taken = Ownership::taken(Owner::Node(0), m.table.generation(0)).raw();
        m.table.identifiers.insert(7, taken);
    });
    assert_eq!(broken, "88: identifier words and attached devices");
}
```

`state()` (`model/src/check/tests.rs:25-96`) attaches no device: it takes a
*device block* from `memory_control` (`:28-35`) and never calls
`IoSpaceAttach`, so no device is in `m.iospaces` or `m.iommus` and no attach
word exists. The spoiling therefore trips the *set* branch of
`check_identifiers` (`model/src/check.rs:350-353`) — a word taken by node 0 with
nothing attached — and not the part the comment names ("the identifier word of
an attached device names its node"), which needs a device attached under another
node's generation. The `insert(4, free)` is inert: a free word never equals
`taken`. `scenarios/checker.rs:274-330` builds the attach/word state properly,
if a model is wanted.

### 8. `census().fault_kinds` has a slot nothing writes and a clamp that hides — question

`model/src/check.rs:49` and `model/src/check.rs:128-136`

```rust
    pub fault_kinds: [usize; 9],
...
                for thread in self.threads.values().filter(|t| t.faulting) {
                    if let Wait::Call { parcel, .. } = &thread.wait {
                        kinds[(parcel.label as usize).min(8)] += 1;
                    }
                }
```

Invariant 40 (`model/src/check.rs:790-798`) holds a faulting thread's label to
`1..=8`, so bucket 0 is never written, and bucket 8 is the one that would take a
label outside that range — which the `.min(8)` then does silently. The counters
are read as evidence: `model/tests/property.rs:1748-1749` reads
`fault_kinds[8]` as "a fault *no context* arrived", so a label of 9 or more,
should invariant 40 ever be relaxed, would be counted as a *no context* fault
with nothing to say so. Either the array is `[usize; 8]` indexed by `label - 1`,
or the clamp deserves the comment saying why it cannot fire.

### 9. `R0` and the line-word bound live in `check_lines`, which does not say so — question

`model/src/check.rs:356-374`

```rust
    /// 96. a line is claimed by an irq of this node exactly while its line
    /// word reads taken by this node's generation (Interrupts, the
    /// owner word of a line, D-135).
    fn check_lines(&self) -> Check {
        // The table of line words has at most `IRQ_LINES_MAX` words, kept
        // for the life of the machine (Interrupts, D-135; finding 9 of the
        // tenth model review).
        if self
            .table
            .lines
            .keys()
            .any(|&gsi| gsi as usize >= dodos_abi::IRQ_LINES_MAX)
        {
            return Err("96: a line word beyond the last");
        }
        // R0 once for each generation of each node (finding 8).
        if self.r0_runs.values().any(|&runs| runs > 1) {
            return Err("R0: run twice for one generation");
        }
```

Neither the bound of the line-word table nor the R0 rule belongs to lines: R0
is a reclaim step over grants and identifiers. The function's doc comment names
only "96", so a reader who wants to know what guards R0 has to find it inside
the interrupt check. Two rules in one function with one doc line is exactly what
"D-135's finding 8" left behind.

### 10. `check_requests` allows a request's waiter not to be waiting — question

`model/src/check/node.rs:200-205`

```rust
            if let Some(thread) = request.waiter
                && let Some(t) = self.threads.get(&thread)
            {
                let waits = t.wait == Wait::Cores(requester) || t.wait == Wait::None;
                ensure(waits, "TLB: the thread of a request waits for another")?;
            }
```

The doc above it (`model/src/check/node.rs:153`) says "its waiting thread waits
for it". The code accepts `Wait::None`, a waiter that waits for nothing, and
skips the rule altogether when the waiter is no longer a live thread.
`Model::start` (`model/src/cores.rs:357-362`) sets `Wait::Cores(at)` for the
waiter and the request is taken away by `Model::complete`
(`model/src/cores.rs:458-484`) before anyone is woken, so I could not find the
path that leaves `waiter = Some(t)` with `t.wait == Wait::None`. If it exists,
the sentence is wrong; if it does not, the rule is weaker than its name.

## Also seen, not worth a merge stop

- `model/src/scenarios/explore.rs:682,722`: `let other = m.thread_on(1, 300, 2);`
  and then `let _ = other;` — the value is thrown away to silence the unused
  variable lint; `let _ = m.thread_on(...)` says the same without a name.
- `model/src/check/tests.rs:1766-1770`: `let context = first_context(m, at);`
  then `let _ = context;` in a scenario that never uses it, inside a test whose
  name (`home_that_its_context_does_not_name_is_reported`) describes the first
  of its two halves.
- `model/src/check/tests.rs:480-495`: the two `assert_ne!` cases of the fault
  test pass on any report but `"16: outcome while waiting"`, so they assert
  "not 16" and not the invariant that does fire; the comment says "later
  invariants" without naming one.
- `model/src/check.rs:823,837`: the local `zero` of the clear-mark rule shadows
  the `zero` of the watermark rule four lines above — it compiles and reads
  badly in a function that carries four invariants at once.
- `model/src/scenarios/explore.rs:289,306`: `slots_of(...)` followed by `[0]`
  panics when the node holds no capability of that kind, which is what a
  forgotten setup would look like; `reviews.rs:268,300,481` and
  `mistral.rs:211,259` index the same way.

## Files read whole

`model/src/check.rs`, `model/src/scenarios/checker.rs`, `model/src/check/cores.rs`,
`model/src/check/debug.rs`, `model/src/scenarios/explore.rs`,
`model/src/check/machine.rs`, `model/src/check/memory.rs`,
`model/src/scenarios/mod.rs`, `model/src/check/node.rs`, `model/src/check/sched.rs`,
`model/src/check/table.rs`, `model/src/check/tasks.rs`,
`model/src/check/tests.rs`. Also read whole, outside the lot, because they say
how the repository's Rust is meant to be written: `AGENTS.md`, `model/README.md`,
`.claude/skills/dodos-rust/SKILL.md`, `.claude/skills/rust-1-100/SKILL.md`.

Other files of the repository I read only in the parts the lot led me to, never
whole: `model/src/lib.rs`, `caps.rs`, `cores.rs`, `memory.rs`, `units.rs`,
`table.rs`, `boot.rs`, `debug.rs`, `system.rs`, `nodes.rs`, `sched.rs`;
`model/tests/property.rs` (the two `fault_kinds` lines only);
`abi/src/lib.rs`, `abi/src/machine.rs`, `abi/src/ring.rs`, `abi/src/x86_64.rs`,
`abi/src/tests.rs`. Part of the lot's own neighbourhood I met only through
`grep`, for finding 4: `model/src/scenarios/{pass17,pass18,pass19,pass20,pass21,
reviews,mistral,cores,crossing,membership,units}.rs`.

## What I did not read

The other 66 files of the diff: the calls in
`model/src/{ipc,caps,memory,irq,roles,units,nodes,blocks,grants,faults}.rs`, the
machine in `model/src/system.rs`, most of `model/tests/`, and all of the scenario
files of other passes. So the contract sentences this lot quotes are judged here
as the model writes them; `architecture/kernel-interface.md` is out of reach by
the brief, and I did not compare a single check against the contract text.
