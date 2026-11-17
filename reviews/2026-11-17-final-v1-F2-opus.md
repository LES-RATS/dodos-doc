# Review of lot F2 (Opus), repository `dodos-pr3-final` at `6312868`

Work copy for runs and mutations: `/private/tmp/dodos-pr3-F2-opus`
(the shared clone was not changed).

## Findings

### model/tests/blocks.rs

**1. Should be fixed. `model/tests/blocks.rs:196-208`, the order the test is named after cannot be observed.**

```rust
fn depth_checks_of_memory_take_come_after_the_plain_arguments() {
    ...
    k.no(take_through(162, 2, free, shift, 40), Error::Invalid);
    k.no(take_through(162, 0, free, shift, 40), Error::Invalid);
```

The depth check (`Model::fits`, `model/src/caps.rs:411-413`) returns
`Error::Invalid`, and so does the bad kind (`model/src/blocks.rs:62`).
The first assertion therefore passes whichever check runs first: if the
depth check were moved before the plain arguments, the test would still
pass. The name promises an order the test cannot see. The same holds for
`plain_arguments_of_memory_take_are_judged_in_order` (line 169): "The
kind, before the size and the place" (line 173) — every plain argument
returns `Invalid`, so no assertion there tells two orders apart; only the
last pair (`Invalid` before `Busy`) is an observable order. Either the
names say less ("are each refused") or the order is checked another way
(it cannot be through the return value alone). See the mutation result
at the end of this file (M1).

### model/tests/boot.rs

**2. Should be fixed. `model/tests/boot.rs:730-742` (and `:609-612`), the refusal of a 64 KB granule is tested with a geometry that is refused for another reason.**

```rust
/// Mistral F4: a machine of 64 KB pages (a table page of 8,192 entries) is
/// refused at start.
    machine.geometry = Geometry {
        page_shift: [16, 29, 0, 0],
        entries: 4096,
        levels: 3,
        user_end: 63 << 42,
    };
```

The comment says "a table page of 8,192 entries", the code says
`entries: 4096`. With `entries: 4096`, `Geometry::valid`
(`abi/src/lib.rs:493-521`) fails twice before it reaches the rule the
test is about: `s[1] == s[0] + per_level` is `29 == 16 + 12`, false, and
`entries == 1 << (s[0] - 3)` is `4096 == 8192`, false. The rule
"*E* at most 4,096" (`self.entries <= TABLE_ENTRIES_MAX`, line 514) is
never what refuses this machine. `kernel_refuses_machine_values_out_of_range`
(line 611, `m.geometry.entries = 8192` on the example's 4, 16 or 32 KB
page) has the same defect: 8192 entries with a 4 KB page breaks
`entries == 1 << (s[0] - 3)` first. The only consistent 64 KB geometry
(`page_shift: [16, 29, 0, 0], entries: 8192`) is the one no test boots.
See M2 at the end for the mutation that removes the `TABLE_ENTRIES_MAX`
clause.

**3. Should be fixed. `model/tests/boot.rs:298-304`, two lines that do nothing, and a value set then overwritten.**

```rust
    let machine = with(|m| {
        ...
        m.image_base = 8 << 20;
        m.kept.push((8 << 20, 0));
        m.kept.pop();
    });
    ...
    let machine = Machine {
        image_base: image,
        ..machine
    };
```

`kept.push(x)` followed by `kept.pop()` removes the element just pushed:
`kept` is unchanged. `m.image_base = 8 << 20` is replaced three lines
later by `image_base: image`. The reader is left to wonder what the test
meant to set up (a kept range at 8 MB of length 0? the image at 8 MB?).
The same set-then-overwrite of `image_base` is in
`no_module_is_refused_for_its_size` (lines 327-333). Dead code in a test
of the start-up layout; either remove it or make it do what was meant.

**4. Should be fixed. `model/tests/boot.rs:234-236`, the comment says more than the assertion.**

```rust
    // An endpoint goes right after the message page.
    let endpoint = retype(24, Endpoint, 0, 40);
    assert_eq!(m.apply(t, endpoint), Ok(Output::Done));
```

Only the success of the retype is checked, not where the object lands.
The test's name ("the start-up untyped is taken after the message page")
is about the watermark; a watermark left anywhere below the end of the
untyped passes. A frame retyped there and read with `frame_at` (as the
lines above do for slots 9, 10, 26) would show its base is
`message + page`.

**5. Question. `model/tests/boot.rs:684-690`, "runs one node" is checked on `Machine::nodes`, but on the booted `System` only the presence of node 0.**

```rust
    assert_eq!(machine.nodes(), 1);
    let (sys, _) = System::boot(&machine).unwrap();
    assert!(sys.has(0));
```

`sys.has(0)` is true on the example machine too (two nodes). Nothing
asserts `!sys.has(1)` after `System::boot`, so a `System::boot` that
ignored `nodes()` and started node 1 anyway would pass.

**6. Question. `model/tests/boot.rs:714-728`, a check duplicated from the test above, and only for one geometry.**

```rust
    // #119: when DODOS_PAGE=16k, Machine::example() uses 16 KB pages
    if std::env::var("DODOS_PAGE").as_deref() == Ok("16k") {
        assert_eq!(Machine::example().geometry.page(), 16_384);
    }
```

This repeats `the_geometry_of_the_tests_is_the_one_dodos_page_names`
(line 705) for 16 KB only, inside a test named after the 63-page start-up
page. It tests nothing the earlier test does not; the `#119`, `#122`
references are mutant numbers of a review the repository does not hold.

### model/tests/cores.rs

**7. Should be fixed. `model/tests/cores.rs:1-3` and `:378-380`, the file and one test promise `thread_move`, and no line of the file calls it.**

```rust
//! Unlike cores: feature masks and the size of a thread,
//! `thread_set_features`, what a core enables, instructions retired on
//! demand, and `thread_move` between the two nodes of `Machine::example`.
...
/// Argon F3: the order of the checks of thread_set_features and sched_count,
/// sched_count on a counted context, and thread_move with a context still
/// lent (mutants 20, 21, 24, 26, 31).
```

`grep -n "ThreadMove\|thread_move" model/tests/cores.rs` finds only the
two comments. The body of `unlike_cores_rules_that_no_test_pinned`
holds `#20`, `#21`, `#24`, `#26` and stops: mutant 31 ("thread_move with
a context still lent") has no code. Either the case was lost or it lives
elsewhere; in both cases the two comments are false, and a reader who
trusts them believes a rule is pinned here that is not.

**8. Should be fixed. `model/tests/cores.rs:172-179`, an assertion that cannot fail.**

```rust
    // The untyped gives a thread of mask AMX 16 KB: two of them and one of
    // mask 0 leave the next 2 KB object at 32 KB + 2 KB.
    ...
    let at = |k: &K, slot: u32| k.m.object_at(k.t, s(slot)).unwrap();
    assert!(at(&k, 100) < at(&k, 101) && at(&k, 101) < at(&k, 102));
```

`object_at` returns an `ObjId`, an identity taken from a counter that
only grows (`model/src/caps.rs:541-542`, `ObjId(self.next_id); self.next_id += 1`),
not an address. Three objects created one after another always compare
in that order, whatever size the untyped gave each. The comment's claim
(where the next object lands) is not checked; the first half of the
test (`thread_bytes` = 2048, 2048, 16384) is what actually pins the
sizes. Also the comment's arithmetic does not match the code's order
(AMX, mask 0, AMX: with natural alignment the third object lands at
32 KB and the next one at 48 KB, not "32 KB + 2 KB"); I could not make
the sentence agree with any placement rule, which is a sign it was
never checked.

**9. Question. `model/tests/cores.rs:413-421`, "preserves count and hw_class", only the count is read.**

```rust
    // #26: sched_count(SCHED_COUNT_ON) on an already counted context preserves count and hw_class
    ...
    let (_, _, after) = read(&mut k.m, k.t, SCHED);
    assert_eq!(after, before);
```

The machine is `Machine::example()` (no classifier), so the class is 0
before and after; the state word is discarded (`_`). The class half of
the comment is not tested; `the_class_is_read_when_a_counted_context_stops_running`
(line 314) has the classifier but never turns counting on twice.

**10. Question. `model/tests/cores.rs:383-385`, a first assertion that shows no order.**

```rust
    // #20: thread_set_features checks target capability before mask
    let mut k = K::new();
    k.no(features(999, 1u64 << 63), Error::Invalid);
```

An empty slot and a bad mask both give `Invalid`; this line passes in
either order. The next assertion (`Denied` before `Invalid`, line 392)
is the one that shows the order. Harmless, but it reads as a check.

### model/tests/debug.rs

**11. Should be fixed. `model/tests/debug.rs:618-658`, the name and the comment claim two things the test does not check.**

```rust
fn destroying_a_thread_with_every_link_takes_one_step_of_at_most_8_units() {
    ...
    k.ok(Syscall::CapDelete(s(101)));
    ...
    // Every link is undone: the page can bind another thread, the task
    // lists no thread, the context has no home.
```

(a) "at most 8 units": the test only sees that one `cap_delete` returns
`Done`. One step holds up to `REMOVAL_STEP` = 32 units
(`abi/src/lib.rs:108`), so a destruction of 9 to 32 units passes as
well; nothing counts the units. (b) "the page can bind another thread":
no line binds the frame in slot 103 to another thread; only the task
and the context are read. The page link, the fault endpoint link, the
wait on the endpoint, the address space and the capability space are
not checked after the delete (the check after every call is the only
guard on them).

**12. Should be fixed. `model/tests/debug.rs:809-825`, "mixes all 4 words" varies only the fourth.**

```rust
    // #96, #97, #99: entropy_read mixes all 4 words and keeps all 8 * left bits in the last word
    ... mix: [0, 0, 0, 1], ...
    ... mix: [0, 0, 0, 2], ...
    assert_ne!(w1, w2);
```

Words 0 to 2 of `mix` are 0 in both calls. A generator that mixed only
`mix[3]` passes this test, and no other test of the lot checks the
other three words (`entropy_read_changes_no_state_but_the_generators_and_pads_the_last_word`
only checks lengths and padding). Mutation M3 at the end:
`for word in mix` replaced by `for &word in &mix[3..]` in
`model/src/debug.rs:498`; result given there.

**13. Question. `model/tests/debug.rs:468-479`, the test of "no state changes" passes because the generator is declared equal to anything.**

```rust
    let before = k.m.clone();
    ... EntropyRead ...
    assert_eq!(k.m, before);
```

The read does change the generator (`model/src/debug.rs:497-509`). The
assertion holds only because the generator is an `Ephemeral<u64>`
(`model/src/cores.rs:161`) whose `PartialEq` returns `true` always
(`model/src/lib.rs:965-969`). `Ephemeral` is documented as "bookkeeping
of the current or last event: what the invariants read to judge an
event"; a generator's state is not that, it is state that decides every
later read. Consequences for the lot: this test cannot see a change to
any other `Ephemeral` field either, and `boot_is_deterministic`
(`model/tests/boot.rs:383`) compares two boots with the generator left
out. Is the generator meant to be outside the state the model compares?

**14. Question. `model/tests/debug.rs:116-177`, the order in the name is only half observable.**

```rust
fn debug_write_is_judged_rights_then_length_then_the_message_page() {
    ...
    let weak = Syscall::DebugWrite { debug: s(100), length: 8, words: vec![1] };
    k.no(weak, Error::Denied);
    k.no(write(513), Error::Invalid);
```

The weak capability is tried with a valid length, so "rights before
length" is not shown here (it is shown in `#59`, line 697). "Length
before the message page" cannot be observed: both refusals are
`Invalid`.

**15. Question. `model/tests/debug.rs:296` and `:564`, statements that exist only to silence the compiler.**

```rust
    let _ = b;
    ...
    let _ = (Endpoint, Task);
```

`Endpoint` and `Task` are used elsewhere in the file (lines 579, 625),
so the second line silences nothing; the first could be `k.spawn();`
without the binding.

### model/tests/faults.rs

**16. Question. `model/tests/faults.rs:183-193`, an unexplained object.**

```rust
    // 33 copies of the endpoint: its removal takes two calls.
    for slot in 50..83 { ... }
    k.make(Endpoint, 49);
    assert_eq!(k.go(Syscall::CapDelete(s(EP))), Err(Error::Again));
```

Nothing reads slot 49 later and no comment says why a second endpoint is
made between the copies and the delete. If it matters (for example to
keep the untyped's watermark or the slot of a removal), a line saying so
would help; if not, it is dead.

**17. Question. `model/tests/faults.rs:504-530`, the order "canonical words then the state" has no assertion.**

```rust
fn thread_write_regs_checks_the_size_then_the_canonical_words_then_the_state() {
```

The test shows size before state (lines 527-529). Size before the
canonical words cannot be observed (both `Invalid`). Canonical words
before the state is never tried: no non-canonical block is written to a
running thread. `debug.rs:722-740` shows "words before `Busy`" only for
the breakpoint and user-interrupt words, not for `rip`, `rsp` and words
18, 19.

**18. Question. `model/tests/faults.rs:611-622`, a test whose last assertion is decided before the step it names.**

```rust
fn resuming_a_thread_that_runs_keeps_nothing_to_clear() {
    ...
    k.ok(Syscall::ThreadResume(s(40)));
    assert!(k.can_run(thread));
    k.ok(Syscall::ThreadResume(s(40)));
    k.ok(Syscall::ThreadSuspend(s(40)));
    assert_eq!(k.record(40)[0], 0);
```

The first resume already clears the record (that is what
`fault_without_a_handler_is_recorded_and_read_after_the_block`, line 596,
pins). The second resume, the one the name is about, cannot change the
outcome of `record(40)[0] == 0`. I could not tell what behaviour of a
resume on a running thread this test guards.

### model/tests/gate_attack.rs

**19. Stops the merge. `model/tests/gate_attack.rs:243-265`, the last check of the first test reads a chunk the grant never touched, and a count that is 0 whatever R6 does.**

```rust
    // And the next generation of node 0 takes the chunk without a trace of
    // the holder's leaf: the map count is 0 after R6.
    ...
    let place = free_run(geometry, log2 as u32);
    m.ok(0, Syscall::MemoryTake { ..., place, ... });
    assert_eq!(m.sys.node(0).map_count(place / geometry.chunk()), 0);
```

The granted frame `OBJ` is retyped from slot 25 (`UT`), the untyped of
node 0's floor; `free_run` is the first chunk past the floors and
reserves. They are different chunks. I checked with a throw-away test
in my copy (`model/tests/zz_probe.rs`, removed after): a frame retyped
from slot 25 on `Model::boot(&Machine::example())` lies in chunk 2050,
`free_run` is chunk 2056 (4 KB pages; 16 KB: 2050 and 2056; 32 KB: 4098
and 4104). Command:
`DODOS_PAGE=<p> nix develop -c cargo test -p dodos-model --test zz_probe -- --nocapture`.
So the chunk that is "taken" was never mapped by anyone, and its count is
0 before R6 as after. Second, by the file's own next test (lines
300-302: "The granter's map count of the chunk is 0: the holder's leaf
counts in its use entry"), the holder's leaf never enters the granter's
map count, so even the right chunk would read 0 with or without R6. The
sentence "takes the chunk without a trace of the holder's leaf" is not
tested by anything in this test; only the restart is. The first half of
the test (R2 unmaps, the capability is gone) is sound.

**20. Should be fixed. `model/tests/gate_attack.rs:437-450`, the test of a 1 GB frame returns silently on two of the three geometries `verify` runs it on.**

```rust
    let Some(bytes) = geometry.bytes(PageSize::Large2) else {
        return;
    };
    ...
    if place / chunk + chunks > 4000 {
        return;
    }
```

`verify` runs `--test gate_attack` with `DODOS_PAGE=16k` and `32k`. The
same probe printed `place/chunk + chunks` = 3072 on 4 KB pages, 6144 on
16 KB and 12288 on 32 KB: the test returns at line 449 on 16 KB and
32 KB and passes having checked nothing. The bound 4000 is not explained
(it is neither a constant of the model nor of the machine). A test that
can pass without running should say so when it skips, or use a machine
large enough on every geometry; at minimum the 4000 needs a name and a
reason.

**21. Should be fixed. `model/tests/gate_attack.rs:368-390`, the test never checks that the device was attached, nor the context entry it is named after.**

```rust
fn a_node_that_dies_with_an_attached_device_leaves_no_context_entry() {
    ...
    assert_eq!(m.on_node(0, Syscall::IoSpaceAttach { ... }), WAITS);
    m.settle();
    // Node 1 kills node 0, ...
    m.ok(1, stop(0, NODE_STOP_KILL));
    m.run(5 * MS);
    assert_eq!(m.state(0), MemberState::Dead);
}
```

The only assertion is that node 0 is dead. Unlike the test above it
(line 352, `assert_eq!(m.woken(0), Some(&DONE))`), it does not check the
attach completed, so a refused or lost attach passes too. Nothing reads
the unit's context entry after R1. If an invariant run by `sys.check()`
is meant to catch a context entry left naming the dead generation, the
test should say which one; I looked in `model/src/check/machine.rs` and
`model/src/check.rs` (invariant 88, `check_identifiers`, which is a check
of one node's own generation) and could not find one that judges a dead
node's entries in another node's unit.

**22. Question. `model/tests/gate_attack.rs:303-313`, the comment says which rule refuses; the return value cannot say it.**

```rust
    // The give is refused, and by the rule of the pieces, not by the gate's
    // check of the map count: a piece of the block lives.
    m.no(0, Syscall::MemoryGive { ... }, Error::Busy);
```

Both refusals are `Busy` (`model/src/blocks.rs:189-193` and `:212-215`),
and in this state the first `Busy` is the descendant check (the frame
capability in slot 211 is a child of the block), not "a piece lives".
The map count read as 0 on line 302 shows the gate check could not
fire, which is enough; the comment names a third reason.

### model/tests/gate_classes.rs

**23. Question. `model/tests/gate_classes.rs:138-174`, the assertion was already true before the step the test is named after.**

```rust
fn a_table_taken_again_from_the_free_list_takes_the_class_of_its_new_level() {
    ...
    ok(&mut m, t, map(ASpace, s(160), BLOCK, AT, 1));
    ok(&mut m, t, Syscall::ASpaceUnmap(s(160)));
    ...
    ok(&mut m, t, map(ASpace, s(161), BLOCK, far, 1));
    ...
    for level in 2..levels as u8 {
        let class = PageClass::table(level).unwrap().raw();
        assert!(classes.contains(&class), "{classes:?}");
    }
```

After the first map and unmap, the three table pages at `base + 2..`
hold the classes of levels 1 to L − 1, and keep them on the free list
(the previous test, line 121-126, pins exactly that). So "levels 2 to
L − 1 are among the classes" holds before the second map; a gate that
re-took a free table without giving it the class of its new level would
pass this assertion. Mutation M4 (set the class of a table taken from
the free list only if it has none yet, `model/src/memory.rs:202`) is
killed, but at line 163, inside the `ok` helper (the call's outcome or
the `m.check()` it runs), not by the loop at lines 169-172. So the rule
is guarded by an invariant of the whole check; the assertion the test
adds is decorative, and the comment on lines 167-168 says it checks
something it does not. Severity lowered to question for that reason.

**24. Question. `model/tests/gate_classes.rs:269-281`, a trait with one implementation for one call.**

```rust
trait ForKind {
    fn clone_for(self, kind: ObjectKind) -> Syscall;
}
```

It is used once (line 213) to turn `ASpaceUnmap` into `IoSpaceUnmap`. A
`match kind` at the call, as `map` does at line 63, says the same with
no trait. The `.clone_for` name also suggests a clone that does not
happen.

### model/tests/gate_words.rs

**25. Should be fixed. `model/tests/gate_words.rs:82` and `:119`, an assertion that cannot fail, and a dead binding.**

```rust
    let chunk = 1u64 << shift;
    ...
    let _ = role;
    ...
    assert_eq!(chunk, 1 << shift);
```

`chunk` is defined as `1 << shift` and never changed; the last line of
the test compares it with itself. It exists only to use the variable.
`let _ = role;` (line 94) the same for `role`. Neither checks anything.

### model/tests/generations.rs

**26. Question. `model/tests/generations.rs:209-227`, "before or after a fresh start" — only after is tried.**

```rust
/// What rule 3 keeps: a run given to a live node is free with that node
/// as owner, and no other node takes it, before or after a fresh start of
/// the giver.
```

The test gives the run, kills and restarts node 1, then tries the take.
No take by node 1 is tried between the give and the kill (the "before"
case). `blocks.rs:235-243` covers it on one node, so the rule is not
untested, but this comment promises it here.

### model/tests/irq.rs

**27. Should be fixed. `model/tests/irq.rs:167-191` and `:204-227`, two more test names about an order that the return values cannot show.**

```rust
fn source_then_vector_are_judged_after_the_destination() {
    // The destination first: slot 0.
    k.no(raw(0, 0, 0), Error::Invalid);
...
fn irq_claim_checks_the_depth_last() {
    ...
    k.no(deep(300), Error::Invalid);
    k.no(deep(48), Error::Invalid);
```

`raw(0, 0, 0)` has a bad destination, a bad source (0) and a bad vector
(0): all three are `Invalid`, so the line passes in any order. The rest
of the first test never combines a good destination with two bad
arguments of different kinds; every refusal there is `Invalid`. In the
second, the bad vector and the depth are both `Invalid`; "the depth
last" would be shown by a state error (`Busy`, a claimed vector) or
`NoSlot` winning over the depth through the deep capability, and neither
is tried. Same class as finding 1.

### model/tests/memory.rs

**28. Should be fixed. `model/tests/memory.rs:374-388`, the comment describes a setup the test does not have.**

```rust
fn tables_come_from_the_free_list_then_from_the_untyped() {
    let (mut k, _) = with_aspace();
    // An untyped of 16 KB that the aspace is not made from cannot help;
    // with its own untyped exhausted, mapping needs the free list.
    k.small(1, 40);
    k.small(1, 41);
```

No untyped of 16 KB is made, and the aspace's own untyped (`UT`, one
chunk) is not exhausted. What the test does is: map with `UT`, unmap
(the tables go to the free list), map with untyped 0 (served from the
free list), map again with untyped 0 (`NoMemory`). The name's "then
from the untyped" is never exercised: no map in this test takes a table
from an untyped after the free list ran dry.

**29. Question. `model/tests/memory.rs:722-731`, a slot comment that does not match the layout.**

```rust
    // The second unit's capability is in slot 19, then the roles (one more
    // unit role), then the untypeds: the second one in slot 26.
    k.ok(Syscall::UntypedRetype {
        untyped: SlotAddr::own(26),
```

With a second IOMMU unit the roles take slots 20 to 25 and the two
untypeds are in 26 and 27. I checked with a throw-away probe in my copy
(`CapInspect` of slots 16 to 35 on that machine): 26 and 27 are
`Untyped`, 28 the copied segment. By the order of `tests/common/mod.rs`
(start-up untyped first, then the one of one chunk), 26 is the first
untyped, the start-up one, not "the second". The test works with either
(both have a chunk to spare), but the comment is wrong by one.

**30. Question. `model/tests/memory.rs:975-977`, a comment that disagrees with the code next to it.**

```rust
    // 2-page device frame (cost = 1 per page, so count: 2 takes 2 steps with gate_chunks = 1)
    k.frame(DEV, PageSize::Page, 3, MemoryType::Uncached, 41);
```

The frame has 3 pages; 2 of them are mapped.

**31. Question. `model/tests/memory.rs:819-954`, a test that skips the whole check the rest of the suite runs after every call.**

`tables_follow_the_page_and_e_of_the_sixteen_kb_geometry` calls
`m.apply` nine times and never `m.check()`, unlike every other test of
the file (through `K::go`). `model/README.md` says "a whole check of the
contract's invariants runs after every step of every test". Also
`use dodos_model::{Map, SIXTEEN_KB};` repeats names the glob import of
line 9 already brings.

**32. Question. `model/tests/memory.rs` (lines 243-255, 258-271, 290-312), more orders between refusals of the same code.**

```rust
    // The frame before the untyped: a wrong kind is `invalid` even with an
    // untyped that is not the aspace's.
    k.no(map(30, 42, IMAGE, AT, 0, 1, R), Error::Invalid);
    ...
    // Judged right after its three checks, before the plain arguments.
    k.no(map(30, 41, IMAGE, AT + 1, 0, 9, X), Error::Invalid);
```

Both candidates are `Invalid` in each case, so these two lines pass in
either order; so do the first seven refusals of
`plain_arguments_of_aspace_map_are_judged_in_order`. The other
assertions of the same tests (`Invalid` before `Denied`, lines 253-254
and 311) are the ones that show an order. Same class as findings 1
and 27.

### model/tests/sched.rs

**33. Should be fixed. `model/tests/sched.rs:289-295`, "three thirds do not fit" because of the recovery reserve, not because of the rounding the comment names.**

```rust
    // The bandwidth is rounded up: three thirds of a core do not fit.
    k.ok(configure(FIRST, 0, 0, 1));
    k.ok(configure(41, 0, 0, 1));
    k.ok(configure(40, 10 * US, 30 * US, 1));
    k.ok(configure(41, 10 * US, 30 * US, 1));
    k.make(Sched, 42);
    k.no(configure(42, 10 * US, 30 * US, 1), Error::Budget);
```

The same test says the recovery reserve holds 1/64 of the core (line
281). Three thirds plus 1/64 exceed one core whether each third is
rounded up or down, so the last line is `Budget` either way. Mutation
M5: `bandwidth` (`abi/src/lib.rs:873-877`) made to round down
(`quotient + 1` → `quotient`). `nix develop -c cargo test -p dodos-model`:
every test passes, this one included. `cargo test -p dodos-abi` kills
it (`bandwidth_is_the_rounded_up_quotient_of_128_bits`,
`bandwidth_is_rounded_up_and_a_whole_core_for_a_full_budget`), so the
rule is tested, but not here; the comment claims this test shows it.

**34. Should be fixed. `model/tests/sched.rs:1-4`, `:196-206` and `:313`, the first context is called "10 ms every 10 ms"; it is 9.84375 ms.**

```rust
//! `Machine::example`. Its first thread runs on the context in slot 4
//! (10 ms every 10 ms, class 1); ...
fn first_thread_runs_on_a_context_of_10_ms_every_10_ms() {
    ...
    // r became min(10 ms, 4 ms); d stays 10 ms.
```

`START_SCHED_BUDGET_NS` is `9_843_750` (`abi/src/lib.rs:841`, "63/64 of
the core, the recovery reserve holding the other 1/64"). The test body
uses the constant, so it passes, but its name and the file's header say
10 ms; `boot.rs:369` names the same context "63/64 of the core". Two
names for one value, one of them false.

**35. Question. `model/tests/sched.rs:314-317`, an equality written as a comparison of two one-element ranges.**

```rust
    assert_eq!(
        k.read(FIRST).1..=k.read(FIRST).1,
        4 * MS as i64..=4 * MS as i64
    );
```

This is `assert_eq!(k.read(FIRST).1, 4 * MS as i64)` with two calls of
`sched_read` instead of one. It took me a moment to be sure it checks
nothing more.

**36. Question. `model/tests/sched.rs:647`, `:659`, `:692`, `:918`, `:923`, the census of fault kinds read by bare index, and index 8 is not only *no context*.**

```rust
    assert_eq!(k.m.census().fault_kinds[8], 1);
```

`fault_kinds` is `[usize; 9]` filled with `kinds[(parcel.label as usize).min(8)]`
(`model/src/check.rs:128-133`). `FaultKind::HardwareBreakpoint` is 9
(`abi/src/lib.rs:766`), so index 8 counts *no context* and hardware
breakpoints together, and index 0 is never a kind. In these tests no
breakpoint fault is queued, so the numbers are right, but
`fault_kinds[FaultKind::NoContext as usize]` would say what is meant,
and the `.min(8)` folding (outside this lot) looks like an array one
too short for the kinds that exist.

### model/tests/tasks.rs

**37. Should be fixed. `model/tests/tasks.rs:529-531` and `:333-334`, two comments contradict the rule the same file asserts.**

```rust
    // The first call detaches the 32 others; the early one stays attached
    // to the revoked task, and is suspended when the choice takes it.
    k.no(Syscall::TaskRevoke(s(40)), Error::Again);
...
    k.no(Syscall::TaskRevoke(s(40)), Error::Again);
    // The first one attached is still attached and runnable.
    let last = threads[0];
```

`task_revoke_stops_its_threads_32_per_call` (lines 282-286) asserts the
opposite: "The first call writes the flag ...: its whole step, it
detaches nothing (D-137)", and `read(40)` still lists 33 threads after
it. So after the first call of both tests every thread is still
attached, not "the early one" or "the first one" alone. The assertions
of both tests still hold (they only look at the one thread), but a
reader is told the wrong rule. In the second test the variable holding
`threads[0]` is called `last`.

### model/tests/verify7_deepseek.rs

**38. Should be fixed. `model/tests/verify7_deepseek.rs:746-791`, a block that can only run when the test is about to fail.**

```rust
    if weird.valid() {
        let machine = Machine::example_on(weird);
        ...
        k.ok(aspace_map(...));
    }
    assert!(
        !weird.valid(),
        ...
    );
```

The `if` body runs only when `weird.valid()` is true, that is exactly
when the assertion after it fails. Today it never runs (dead code), and
if the rule regressed it would boot a model on a geometry the assertion
is about to reject, and could panic inside `k.ok` with a message that
hides the real one. The two lines `assert!(!weird.valid())` say all the
test checks.

**39. Should be fixed. `model/tests/verify7_deepseek.rs:256-300`, `:544-579` (and the headers of F4, F6, N4), comments that describe the old bug as the present behaviour.**

```rust
    // Resuming with a smaller count equal to the done count (1) returns Busy,
    // but resuming with count = 3 (smaller than original 4, larger than done 1)
    // wrongly succeeds with Ok(Done) and produces a 3-page mapping.
```

The model was fixed in pass 14 (the file header says so); the comment
says it "wrongly succeeds". F6's header ("Device leaves and global
read-only (kept) leaves are counted in `table.maps[chunk]`"), N4's
("write the gate word of `*none*` chunk 0 from BOTH nodes") and N5's
("`Model::boot` accepts this geometry") are the same: each states as
fact what the test now proves false. The comments cite contract line
numbers (139, 282, 342, 346, 887, ...) that the contract repository is
free to move; a section name, as `AGENTS.md` asks, would survive. Also
the F2 and N2 checks are `assert_ne!(retry_short, Ok(Output::Done))`,
which accepts any error; `gate_attack.rs:540-580` checks the same rule
with `Busy`.

**40. Question. `model/tests/verify7_deepseek.rs` as a whole, tests that repeat others of the suite.**

F1 is `faults.rs:535-552` (same geometry, same `rip`, same upper-half
`rsp` idea); F2 and N2 are `gate_attack.rs:539-580`; F5 is
`gate_classes.rs:89-136`; F6 is `gate_classes.rs:195-237`; N4 is
`gate_classes.rs:242-267` together with 195-216. The skill
`dodos-rust` asks for one test per behaviour. Keeping the file as the
record of a review is a choice, but then it should say which test is
the reference for each rule. Also F9 part B (lines 482-502) returns
without checking anything on 16 KB and 32 KB pages (`large2 <= 1 << 30`
is false there), silently, like finding 20.

**41. Question. `model/tests/verify7_deepseek.rs:237-238` and `:249`, small redundancies in F1.**

```rust
    let mut machine = Machine::example_on(low_geom);
    machine.geometry = low_geom;
    ...
    regs[0] = high_lower; // REG_RIP = 0
```

`example_on(low_geom)` already gives that geometry (other tests use it
without the second line, e.g. `faults.rs:543`), and `REG_RIP` exists
(`faults.rs:7` imports it) instead of the literal 0 and a comment.

## Mutations run

All in `/private/tmp/dodos-pr3-F2-opus`, each reverted with
`git checkout` before the next (`git status --short` empty after each).
Command for each: `nix develop -c cargo test -p dodos-model` (M2 also
`-p dodos-abi` via `--workspace`; M5 also `-p dodos-abi` separately).

| # | Change | Result |
|---|---|---|
| M2 | `abi/src/lib.rs:514`, `&& self.entries <= TABLE_ENTRIES_MAX` → `&& true` | Model tests (boot.rs included) all pass; killed only by `dodos-abi` `tests::the_geometry_reads_page_sizes_from_the_machine` (`abi/src/tests.rs:249`), whose list holds the consistent 64 KB geometry. Finding 2. |
| M3 | `model/src/debug.rs:498`, `for word in mix` → `for &word in &mix[3..]` | Survives: every model test passes (523 lib, all integration tests). Finding 12. |
| M4 | `model/src/memory.rs:202`, set a reused table's class only if it has none | Killed at `gate_classes.rs:163` inside `ok` (outcome or `m.check()`), not by the test's own assertion. Finding 23. |
| M5 | `abi/src/lib.rs:876`, `quotient + 1` → `quotient` (round down) | Survives every model test, `sched.rs` included; killed by two `dodos-abi` tests. Finding 33. |

M1 (moving the depth check of `memory_take` before the plain arguments)
was not run: the argument of finding 1 rests on both refusals returning
`Invalid`, which is read directly from `model/src/blocks.rs:62` and
`model/src/caps.rs:411-413`; no assertion of the test can tell the two
orders apart.

Baseline before any change: `nix develop -c cargo test -p dodos-model --tests`
passed everything (523 lib tests; blocks 14, boot 33, calls 347, cores 13,
debug 20, faults 25, gate_attack 10, gate_classes 6, gate_words 4,
generations 5, irq 16, memory 37, property 15, sched 45, tasks 20,
verify7_deepseek 12). I did not run `./verify` whole (format, clippy,
the 16 KB and 32 KB runs); the geometry facts of findings 19 and 20 come
from the probe run with `DODOS_PAGE=4k`, `16k`, `32k`.

## Files read whole

In the order of the brief, every line:

- `model/tests/blocks.rs`
- `model/tests/boot.rs`
- `model/tests/cores.rs`
- `model/tests/debug.rs`
- `model/tests/faults.rs`
- `model/tests/gate_attack.rs`
- `model/tests/gate_classes.rs`
- `model/tests/gate_words.rs`
- `model/tests/generations.rs`
- `model/tests/irq.rs`
- `model/tests/memory.rs`
- `model/tests/sched.rs`
- `model/tests/tasks.rs`
- `model/tests/verify7_deepseek.rs`

Also read whole: `AGENTS.md`, `model/README.md`,
`.claude/skills/dodos-rust/SKILL.md`, `model/tests/common/mod.rs`,
`verify`, `model/src/blocks.rs` lines 1-360.

Read in part, only as far as a finding needed: `abi/src/lib.rs`
(`TREE_DEPTH`, `MemoryType`, `Geometry::valid`, `FaultKind`,
`START_SCHED_*`, `bandwidth`), `abi/src/tests.rs` (around 225-250),
`model/src/boot.rs` (`Machine`, `Refusal`, `layout` to the start of the
ordinary memory), `model/src/caps.rs` (`fits`, `take`), `model/src/debug.rs`
(`entropy_read`), `model/src/lib.rs` (`ObjId`, `object_at`, `Ephemeral`),
`model/src/threads.rs` (`thread_set_features`), `model/src/memory.rs`
(table classes, 180-215), `model/src/table.rs` (`set_class`),
`model/src/sched.rs` (`Sched::bandwidth`), `model/src/check.rs`
(`Census`, invariant 88's comment), `model/src/check/machine.rs` (the
list of `ensure` lines), `model/src/ipc.rs` (the message-page rule).

Not read: `.claude/skills/rust-1-100/SKILL.md` (listed by the brief as a
starting point; I judged the lot needed no compiler-version detail), the
rest of `model/src/`, `model/src/scenarios/`, `model/tests/calls.rs` and
`property.rs`, and the rest of `abi/`.
