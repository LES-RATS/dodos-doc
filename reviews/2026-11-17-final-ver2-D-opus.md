# Verification of lot D's attack report (v2-D-opus)

Verifier: a sub-agent with the contract and the decisions in hand, owing the
author nothing. Copy: `/private/tmp/dodos-pr3-ver2-D-opus`, a fresh
`cp -R` of `/private/tmp/dodos-pr3-final` (head `6312868`), made after
deleting the earlier copy. I read `AGENTS.md`, the skills `dodos-rust` and
`rust-1-100` (the flake gives `rustc 1.100.0`, 9 November 2026), `decisions/README.md`
(D-117 and D-120 are the gate) and the sections of
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` each
finding needs. Every test below was written by me and run in my copy with
`nix develop -c cargo test -p dodos-model ...` (`nix` from
`/nix/var/nix/profiles/default/bin`). I read the author's probes in
`/private/tmp/dodos-pr3-v2-D-opus` and ran nothing there.

My probes (file, names; the copy holds them with the assertions in the
corrected form of each section, which is the form that fails while the
defect is there):

- `model/tests/ver2_probe.rs`: `the_start_up_accepts_any_io_width`, and the
  two that reached the panics of finding 2,
  `the_checker_panics_on_an_iospace_of_an_unchecked_width` and
  `a_user_iospace_map_panics_on_a_width_of_64` — run first, then replaced by
  the start-up test once the refusal was in place, since a copy that refuses
  the width cannot reach them;
- `model/src/check/tests.rs`: `ver2_a_take_journaled_in_the_old_owners_name_is_accepted`,
  `ver2_a_take_journaled_in_the_unclaimed_name_is_accepted`,
  `ver2_a_ring_with_next_sequence_zero_panics_the_checker`,
  `ver2_a_ring_with_next_sequence_at_the_maximum_panics_the_checker`,
  `ver2_a_lend_to_a_missing_receiver_panics_the_checker`;
- `model/src/scenarios/checker.rs`: `ver2_a_word_taken_in_a_live_nodes_name_is_reported_by_the_victim`,
  `ver2_a_word_taken_in_the_unclaimed_name_is_accepted`,
  `ver2_a_device_leaf_count_above_its_leaves_is_accepted`,
  `ver2_rights_of_a_remote_frame_beyond_the_grant_are_accepted`,
  `ver2_a_fresh_start_adopts_the_sequences_a_dead_generation_left`.

For findings 1, 2, 3, 5 and 6 I then wrote the correction into the copy and
ran the probes again, and the whole model suite, to show that the test fails
without the change and passes with it, and that the change breaks nothing
else. Last full run with all of them in:
`nix develop -c cargo test -p dodos-model --no-fail-fast` — 19 result lines,
every one `ok`, 1,156 tests passed, none failed. Finding 4's correction is
described and not patched; I say so there.

---

## Finding 1. Invariant 52 accepts a take written in the name of another node

**What the report says.** `judge_write` (`model/src/check/table.rs:38-48`)
accepts a take whose after-word names the *old* owner (`named =
after_owner == writer || after_owner == owner`) with the writer's generation,
and also a take that leaves *taken by unclaimed*. Its two tests journal such
a write and the check returns `Ok`.

**What I ran.** I wrote both journals again, with my own values, in
`model/src/check/tests.rs` (`with_block` for the chunk, the same journal call
as every other test of invariant 52):

```
test check::tests::ver2_a_take_journaled_in_the_old_owners_name_is_accepted ... g0 1 g1 1 node 1 Live
test check::tests::ver2_a_take_journaled_in_the_unclaimed_name_is_accepted ... ok
```

So the claim about the *journal* holds: 52 accepts a take that leaves the
word reading *taken* (node 1, 1) — node 1's current generation — or *taken*
(unclaimed, 1).

**What the contract says.** "Who may take a word (design choice). A node *X*
of current generation *g* may write *taken* (*X*, *g*) into a word that is
free or taken and whose owner is:" then four cases, of which the last is
reserve *j*, "the word then keeps the owner code of the reserve, with the
state *taken* and *X*'s generation in bits 32-63" — and the paragraph ends
"Any other owner is refused." (`kernel-interface.md:846`). The only permitted
write that keeps the old owner code is the reserve's; for a node's word the
write must name the writer. The model's `named` is therefore weaker than the
sentence.

**But the report's consequence is not reachable.** It says "a kernel that
made it would pass", and that is not what happens. I put the word in the
table of a machine of two live nodes and journaled the same write from node
0 (`ver2_a_word_taken_in_a_live_nodes_name_is_reported_by_the_victim`):

```
a chunk taken in node 1's name: Err("node 1: 57: kernel space and ownership")
```

Invariant 57 — "the node maps a chunk in its kernel space exactly when its
word reads *taken* by it with its generation" (`check/table.rs:340-372`) —
convicts node 1, which holds the word and cannot map it. No machine state
with a chunk in another *live* node's name passes the whole check. And the
unclaimed case is harmless by the same paragraph of the contract: case 2 lets
any node take a word whose owner is unclaimed, whatever its state, so a word
*taken* (unclaimed, *g*) stays takeable (`ver2_a_word_taken_in_the_unclaimed_name_is_accepted`
returns `Ok`, and no rule is broken by it).

**Verdict: real, the model's fault** — the contract forbids the write and the
model's rule accepts it — but the harm the report claims does not follow:
57 rejects the harmful state, and the harmless one is harmless. My severity:
**low** (informational), where the report says "hardening".

**Correction (model).** `judge_write` in `model/src/check/table.rs:45`, one
line:

```rust
let named = after_owner == writer || (reserve && after_owner == owner);
```

Test: `ver2_a_take_journaled_in_the_old_owners_name_is_accepted` asserts
`Err("52: write of an ownership word")` and fails without the change (it
returned `Ok(())` above); so does the unclaimed one; and the machine test
`ver2_a_word_taken_in_a_live_nodes_name_is_reported_by_the_victim` now
reports `Err("node 0: 52: write of an ownership word")` — the writer's own
invariant fires before node 1's 57, which is the right report. I ran the
three after the change: green, and the whole suite stays green.

---

## Finding 2. `io_width` of the boot image is never checked; the checker and a user call panic

**What I ran** (`model/tests/ver2_probe.rs`, written by me):

```
$ nix develop -c cargo test -p dodos-model --test ver2_probe -- --nocapture --test-threads=1
io_width 8: boot true
io_width 64: boot true
io_width 125: boot true
io_width 130: boot true

thread 'the_checker_panics_on_an_iospace_of_an_unchecked_width' panicked at model/src/memory.rs:377:5:
attempt to subtract with overflow
io_width 8: check Err(Any { .. })
thread '...' panicked at model/src/check/memory.rs:110:33:
attempt to multiply with overflow
io_width 125: check Err(Any { .. })
thread '...' panicked at model/src/check/memory.rs:113:43:
attempt to shift left with overflow
io_width 130: check Err(Any { .. })

thread 'a_user_iospace_map_panics_on_a_width_of_64' panicked at model/src/memory.rs:421:18:
attempt to shift left with overflow
iospace_map at width 64: Err(Any { .. })
```

Every step is one a boot image and a user can make: the image sets the value
before `Model::boot`, the user retypes an `iospace` (`Ok(Done)`) and, at
width 64, maps a frame. `Machine::layout` (`model/src/boot.rs:621-700`)
refuses geometry, cores, node slots, segments, floors, entropy — and reads
`io_width` nowhere.

**What the contract says.** "Its address width and page sizes are the ones
every unit supports, published in the start-up page (on x86-64, 48 bits if
every unit supports four levels, otherwise 39)" (`kernel-interface.md:344`).
The width is a value of the machine, from the hardware, and no processor has
an IOMMU of 8, 125 or 130 bits. The list of refusals at start-up
(`kernel-interface.md:1995-2005`) has no item on it: that list is exhaustive
as written ("The kernel refuses to start ... if:"), so the *contract* does not
tell a kernel what to do with such a value — a gap of one line, not a licence.

**Verdict: real, the model's fault.** The model takes a machine the contract
says no processor is, and then neither names an invariant nor survives: a
debug build panics in `iospace_map` on a user's call, and in the check on
every state that holds an `iospace`; a release build masks the shift, so
width 64 refuses every map of a page and width 8 wraps `io_levels` to some
2^32 levels, which makes the bound of 59 vacuous for that iospace. The stated
purpose of the check ("`Err` names the invariant that fails", `check.rs:11`)
breaks, and so does the model's claim that the whole check runs after every
step. My severity: **moderate** (debug-build panic; release, a wrong limit
and a weakened invariant; nothing reaches another node's memory).

**Correction (model).** `Machine::layout` in `model/src/boot.rs`, in the first
refusal (machine values):

```rust
let io_width_ok =
    self.io_width >= u32::from(geometry.page_shift[0]) && self.io_width < 64;
if !geometry.valid() || !io_width_ok || ... { return Err(Refusal::MachineValues); }
```

64 itself must be refused, not taken: the limit of a mapping is a `u64` in
`mapping_range` and in `check/memory.rs`, so `1 << 64` (`memory.rs:421`)
overflows in a debug build and masks to 1 in a release build; the widths real
units have (39, 48, 57) are all below 64, so nothing is lost, and the model's
own tests use 39, 47 and 48. With the refusal in place `1u128 << io_width`
(`check/memory.rs:74,113`) and `io_levels` (`memory.rs:377`) are safe with no
other change — and the user's map of finding 2's last paragraph is refused at
the start-up, so it can no longer panic. Test:
`the_start_up_accepts_any_io_width`, corrected to

```rust
for width in [8, 64, 125, 130] { assert!(Model::boot(&machine).is_err()); }
for width in [39, 48, 57, 63] { assert!(Model::boot(&machine).is_ok()); }
```

fails without the change (the boot returned `Ok` for all four of the report's
widths) and passes with it. I ran it, and the whole suite, after the change:
green. `io_page_sizes` needs no refusal: it is only masked against
`1 << frame.page` (`memory.rs:418`), so an absurd value refuses maps instead
of panicking.

**Correction (contract), the smallest.** One item of the list at
`kernel-interface.md:1995`: "or the address width of its iospaces is below
the page's, or above the one a mapping can express". Cost: one comparison at
machine start-up, paid never after it; no new state (the width is already in
the fixed part).

---

## Finding 3. A debug area left by a dead generation is adopted; its sequences panic the writer and the checker

Three claims, and I ran all three.

**The checker's ring test** (`check/debug.rs:16-25`). My tests, on the state
of `state()`:

```
thread '...' panicked at model/src/check/debug.rs:23:35:
attempt to subtract with overflow                      (next_kernel = 0)
thread '...' panicked at model/src/check/debug.rs:20:20:
attempt to add with overflow                           (next_kernel = u64::MAX, entry u64::MAX-1 in place)
```

The first is the guard `next >= 1` read after `next - 2`; the second is
`entry.seq + entries`. Both are the checker crashing where it should report
"88: kernel ring". One correction to the author's reproduction: with the area
as it stands after a boot, entries of low sequence stay in the ring and make
`placed` false *before* the overflowing entry, so `next = u64::MAX` alone
reports 88 (I got `Err("88: kernel ring")` before I cleared the ring); the
overflow needs the ring consistent with the sequence, which a hostile writer
can leave.

**The chain** (`model/src/debug.rs:262-276`, `:91-94`, outside the author's
lot). I killed node 1 in `S::two()`, waited for `Dead`, wrote `u64::MAX` as
`next_kernel` of core 1's area — standing for the last write of the hostile
generation, which the model itself cannot make because its own writes are
always `seq + 1` — and started node 1 fresh:

```
thread '...' panicked at model/src/debug.rs:94:17:
attempt to add with overflow
the fresh start: Err(Any { .. })
```

So a generation of node 1 leaves a value that makes *the next generation's
first trace entry* panic (debug) or wrap to 0 (release). The model's
`enter_debug_areas` keeps the area when magic and version are right, exactly
as `kernel-interface.md:1553` says: "a core that starts in a node keeps its
area, and if the header's magic and version are right it sets the node slot
and generation and goes on from the next sequences found there, otherwise it
clears the area and starts at 1."

**What the contract says and what breaks.** The sentence above is deliberate
— it keeps the record of a dead generation readable — and the header's two
next sequences are two words of that header (`kernel-interface.md:1548`),
written by the core alone ("Only the core writes its area",
`kernel-interface.md:1531`), so a faulty generation chooses them. The
contract's own writing rule ("The kernel writes word 0 to 0, then words 1 to
7, then word 0 to *s*, then the ring's next sequence to *s* + 1",
`kernel-interface.md:1550`) is undefined at *s* = 2^64 − 1, and its reading
rule ("for each *s* from max(1, *n* − *N*) to *n* − 1") is undefined at
*n* = 0; and "writing never fails and never waits" (same line) is the
guarantee that breaks: with a sequence of 0 the ring's own rule — the entry
of sequence *s* at index (*s* − 1) mod *N* — has no index for *s* = 0, so
every check of the new generation fails, and in the debug build the write
panics. The gate promise is *not* broken: the area is the core's, mapped
writable only by the node that runs there, so this is "availability" and the
record, not another node's memory. But the new generation inherits a state
the contract's own invariant 88 cannot hold — cross-generation damage inside
one node slot, or across nodes on the same core ("whatever node runs there").

**Verdict: real, the contract's fault** for the adoption (the model does what
`kernel-interface.md:1553` says and the guarantee "writing never fails and
never waits" breaks in the generation that comes after), and **real, the
model's fault** for the two checker panics, which are ordinary bugs in
`ring_holds` (order of evaluation, and no checked arithmetic). My severities:
**moderate** for the contract (a hostile or buggy generation makes every
later start on that core fail to trace, and the debug build panics), **low**
for `ring_holds` (the oracle loses the report; no state escapes).

**Correction (contract), the smallest.** The condition of the sentence at
`kernel-interface.md:1553` gains the one clause the model's `ring_holds`
already expresses: "and if the header's magic and version are right **and
each of its next sequences is at least 1 and the entry the ring holds at that
sequence is the one before it**, it sets the node slot and generation and
goes on from the next sequences found there, otherwise it clears the area and
starts at 1"; and one clause on `kernel-interface.md:1550` for the residual
case a consistent ring at 2^64 − 1 still reaches: "a write whose next
sequence would pass 2^64 − 1 starts the ring at 1 again, its entries
cleared". Cost: two comparisons and one header read at a core's start (rare),
one comparison per write, and a clear of one ring (16 KB of kernel entries, or
48 KB of user entries) once every 2^64 entries (never in a boot); the record of a dead generation that *is* consistent stays
readable, which is what the sentence is for. No new state: the sequences are
in the header.

**Correction (model), which follows it.** `CrashArea`/`DebugArea::write`
(`model/src/debug.rs:78-95`): compute the next sequence with
`checked_add(1)` and, when it is `None`, start the ring at 1 with its entries
cleared, so a write cannot fail; `Model::enter_debug_areas`
(`model/src/debug.rs:262`) clears the area when `next_kernel` or `next_user`
is 0 or the entry the ring holds at that sequence is not the one before it.
And `ring_holds` in `model/src/check/debug.rs`: `if next < 1 { return false; }`
first, and `entry.seq.checked_add(entries).is_some_and(|top| top >= next)`.
Tests: `ver2_a_ring_with_next_sequence_zero_panics_the_checker` and
`ver2_a_ring_with_next_sequence_at_the_maximum_panics_the_checker`, corrected
to `assert_eq!(model.check(), Err("88: kernel ring"))` — they failed with a
panic before the change; and
`ver2_a_fresh_start_adopts_the_sequences_a_dead_generation_left`, corrected
to assert that node 1 comes back `Live` with its check `Ok`, which fails with
the panic before the change and now prints

```
after the fresh start: node 1 Live, next kernel 2
```

I ran all of them plus the whole suite after the two changes: green.

---

## Finding 4. A remote root capability may hold any rights; a read-only grant becomes a writable mapping

**What I ran** (`ver2_rights_of_a_remote_frame_beyond_the_grant_are_accepted`,
my own grant: node 1 receives, node 0 sends one frame with
`Transfer::Derive(frame, READ)`):

```
the frame and its anchor on node 0 hold [(CapId(64), Rights(255)), (CapId(65), Rights(1))], its root CapId(64)
the root remote capability of node 1 holds Rights(1)
the translation of node 1: Some(Rights(3))
```

The anchor node 0 wrote carries `READ` (1); the root remote capability on
node 1 carries `READ` too. I then gave it `READ | WRITE | DERIVE` — a state
the contract forbids — and `System::check()` returned `Ok(())`; then a plain
`ASpaceMap` with `read | write` succeeded, and node 1 translates node 0's
frame with `Rights(3)`.

**What the contract says.** "**A remote frame capability** is a slot in state
3 ...: its kind is `frame`, and its rights, depth and by-kind fields are those
of the anchor" (`kernel-interface.md:911`). And `aspace_map`/`iospace_map`
make the rights word "a subset of the frame capability's rights"
(`denied`, `kernel-interface.md:287,349`) — a check the model does perform,
against the model's own slot, which is why widening the slot is enough.

**Verdict: real, the model's fault** — the contract forbids the state, the
model accepts it. Severity: **hardening**, and no more: the gate's promise is
not broken by it. The guarantee (G) says "every translation ... leads only
to: ... 2. memory granted to *X* by its owner and not yet revoked" and "Write
permission exists only in classes 1, 2 and 4 ... So a kernel bug in *X* can
corrupt *X*'s memory, *X*'s devices **and what *X* was granted**, and nothing
else" (`kernel-interface.md:1061-1068`): the frame was granted to node 1, so
node 1's faulty kernel writing it is inside the unit of failure the contract
already accepts. What is missing is the oracle's coverage of the words
"those of the anchor", not a security guarantee.

**Correction (model), not patched, and I say why.** In `model/src/grants.rs`,
`Remote` (line 21) gains the anchor's rights — `Granted` already carries them
(`grants.rs:33`), so the field is copied when the remote capability is made
and there is no new machine state. Then `check.rs:437` (invariant 3) judges a
root remote capability by equality
(`remote.is_some_and(|r| r.rights == cap.rights)`) instead of `remote ||`, and
the derivation rule above it already covers children; and
`check/table.rs:261-268` (invariant 58) judges a remote leaf with
`remote.rights.contains(t.rights)` instead of `continue`. I did not patch it:
the change touches the grant paths of `grants.rs` and two invariants, and its
test (`ver2_rights_of_a_remote_frame_beyond_the_grant_are_accepted`, asserting
`Err("node 1: 3: root capability")` after the widening) would need the whole
suite re-run to show nothing else depends on the loose rule; I ran neither.

---

## Finding 5. G4 for device entries is only "at least"

**What I ran** (`ver2_a_device_leaf_count_above_its_leaves_is_accepted`):
node 0 takes the device entry of the machine's 2 MB range with `memory_take`
(so its ownership word names node 0, live), then I add 5 to that entry's leaf
count, as a faulty gate of the owner would leave it:

```
entry 3 of node 0, leaf count 0: Ok(())
```

`System::check` accepts it after every step, for ever.

**What the contract says.** G4: "the **map count**: the number of leaves of
the owner's tables (CPU and IOMMU) that target pages of the chunk ... A leaf
of device memory is counted in the **leaf count of its device entry**, one
word of 64 bits per entry beside the device table, written only by the gate of
the entry's owner, reset to 0 when the entry is taken ..."
(`kernel-interface.md:1077`). The count *is* the number of leaves; a count
above the leaves is not that number. The model's own chunk rule is exact while
the owner runs (`check/machine.rs:127-150`), which shows the intent.

**Verdict: real, the model's fault.** Severity: **hardening**, as the author
says — it is a hole in the oracle, and the effect is a device entry that can
never return to its pool (its count never reaches the value a take resets),
which is availability inside the owner's own devices.

**Correction (model).** `check_counts` in `model/src/check/machine.rs:149-154`:
judge the entry's owner word, and require equality while that owner runs (the
count includes the leaves a failed unit keeps for ever, `frozen_entries`,
already counted in `entry_leaves`):

```rust
let owner = dodos_abi::Ownership::from_raw(table.devices[entry].owner.raw());
let alive = owner.is_some_and(|w| match (w.state(), w.owner()) {
    (dodos_abi::OwnState::Taken, dodos_abi::Owner::Node(n)) => {
        self.has_generation(n, w.generation()) && self.running_node(n)
    }
    _ => false,
});
let counted = match alive {
    true => held == table.device_leaves[entry],
    false => held <= table.device_leaves[entry],
};
ensure(counted, "G4: a leaf count below its leaves")?;
```

Test: `ver2_a_device_leaf_count_above_its_leaves_is_accepted`, corrected to
expect `Err` ending `"G4: a leaf count below its leaves"` — it returned
`Ok(())` before the change. Note the author's version of this test used entry
0, which no node owns, so it would still pass under this correction; the entry
must belong to a running node for the equality to bite. I ran the corrected
test and the whole suite with the change: green.

---

## Finding 6. The checker panics on bad states instead of naming the invariant

**Reproduced** (my tests, above and below):

- `check/sched.rs:40`, `runs(&self.threads[thread])` on the receiver of the
  top lend, before invariant 44 asks whether that thread exists:
  `panicked at model/src/check/sched.rs:40:72: no entry found for key`
  (state: the first thread suspended, a lend whose receiver is no thread).
- `check/debug.rs:23` and `:20`: finding 3.
- `check/memory.rs:74,110,113`, `memory.rs:377`, `memory.rs:421`: finding 2.

**The three "not run" items, judged.** I did not run them either, and here is
why, item by item:

- `check/debug.rs:57`, `self.table.crash.areas[core.number]`: `core.number` is
  by definition the position of the core in the machine's core list
  (`kernel-interface.md:88`), and `CrashArea::new` makes one area per core
  (`model/src/debug.rs:290`), so the index is in range for every machine the
  start-up accepts. Only a hand edit of `cores[i].number` reaches it. No
  finding.
- `check/table.rs:321`, `table.owners[chunk]` for a block past the table: the
  table's ownership words are laid out from the same memory map the untypeds
  come from (`Machine::layout`), so a block's chunk index is in range unless
  an untyped's `base`/`bytes` is written by hand. No finding.
- `check/debug.rs:169`, `regs[REG_DR0..=REG_DR3]`: **refuted.** `regs` is a
  `Vec<u64>` of `REGS_WORDS` = 26 words (`abi/src/x86_64.rs:63`,
  `model/src/caps.rs:588`) and `thread_write_regs` refuses a block of another
  length ("exactly the architecture's number of words", `model/src/faults.rs:190`),
  so `regs` is never shorter than 24; `REG_DR0..=REG_DR3` = 20..=23 is always
  in range. There is nothing here to fix.

**Verdict: real, the model's fault** for the four it reached (the check's
purpose is to name the invariant, and `AGENTS.md`/`model/README.md` sell the
check as the oracle; a panic is neither a report nor a check), severity
**low** — the states are ones only a faulty kernel makes, and the model's own
sequences never reach them. The register item is refuted.

**Correction (model).** `check_sched` in `model/src/check/sched.rs:40`:
`let runs = |thread: &ObjId| self.threads.get(thread).is_some_and(Self::runnable_thread);`
so a missing receiver is `false` and invariant 44 can name the lend; the
`ring_holds` change of finding 3. Test:
`ver2_a_lend_to_a_missing_receiver_panics_the_checker`, corrected to "the
check reports and does not panic" — it panicked before the change and reports
`Err("41: queue of a context")` after it (a state that reports 44 needs the
rest of the node consistent with the missing receiver, which the model's own
sequences cannot build either); and the two ring tests of finding 3. I ran
them and the whole suite: green.

---

## Finding 7. Messages no test makes fail, and one vacuous checker test

**Reproduced** (the report's 1,155 and my 1,158 differ only in whose probes
are counted: the base is 1,145 either way). I disabled the same
five checks at once (the 88 attach word in `check.rs:342-345`, G4's device
`held <=` in `machine.rs:151`, the state word of a request in `node.rs:162`,
word 6's epoch in `node.rs:339`, `sends <= SENDS_PER_PEER` in `node.rs:359`)
and ran the whole model suite:

```
$ nix develop -c cargo test -p dodos-model --no-fail-fast
19 test result lines, every one ok: 533 in the library, then 14, 33, 347, 13,
20, 25, 10, 6, 4, 5, 16, 37, 15, 45, 20, 3, 12 (1158 tests in all, my probes
included)
```

So none of the five is guarded: a check that cannot fail is a check that is
not a test, and `dodos-rust` says "A test fails without the code it guards".

**G6's vacuous test.** I made the same single change
(`ensure(true || held, "G6: ...")` at `machine.rs:177`) and ran the suite:
`scenarios::checker::a_grant_freed_while_its_holder_translates_to_it_is_reported`
**passed**, and
`scenarios::pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6`
**failed**. So the report is right: the checker's own test of G6 is vacuous
(the `|| report.contains("58")` disjunct, plus the dead `let _ = Member::new;`),
while `pass18` does guard the rule. Severity: **low** (a test, not the model).

**The fifteen messages.** I searched `model/src/check/tests.rs`,
`model/src/scenarios/` and `model/tests/` for each string of the report's
list: not one occurs. Confirmed as written (with my own probes added — they
touch none of them).

**`explore.rs` and a `DODOS_SEED` that does not parse.** Read, not run:
`seeds()` falls back to all seeds when the variable does not parse
(`explore.rs:31-39`) and `reached()` skips its floor whenever the variable is
*set* (`explore.rs:174-183`), so `DODOS_SEED=typo` runs every seed and checks
no floor, silently. Real, and the report's note stands; severity **low** (a
harness that can be silenced by a typo is a harness whose floors are
advisory). Correction: parse the variable once into an
`Option<u64>`/`Result` and let both `seeds()` and `reached()` use that value,
so a value that does not parse either panics at the start or counts as unset;
a test cannot guard it cheaply, and I did not write one.

**Verdict: real (the tests), severity low** for all three parts.

---

## One known disagreement: a message whose header names another node

This report has no finding on it — its finding 1 is the same question one
level down, a *write* in another node's name, and I settled it above (real,
contained by 57, inside the gate's promise because the writer gains no
translation). The message question deserves its own answer, because two
readings of the contract pull apart:

- the receive check is stated on the sender the message *carries*: "Every
  message carries its kind, its length, its sender's node and generation ...
  The receiving kernel checks ... the sender's member word is starting, live,
  sealing or sealed with that generation" (`kernel-interface.md:966`);
- the rings are per ordered pair of node slots, and G gives node *X* write
  permission on "the rings whose sender is *X*" (`kernel-interface.md:1063`).

So a faulty node *A* can put into ring *A*→*B* a message whose header names a
third node *C*, live with a generation *A* states; *B*'s check passes on *C*'s
member word. **This stays inside what the gate promises, and I would keep the
sentence as it is.** The scenario: every other rule of the eleven kinds takes
its identity from that same carried sender — a message that names a grant
matches "the grant entry naming the sender as grantee ... or the use entry
naming the sender as granting node" (`kernel-interface.md:966`), an answer
"names a credit of this node toward the sender", the unit requests of D-140
are "tied to the requester" by words that name *the carried sender* with its
generation (`kernel-interface.md:1040`). So *A* can only make *B* do, for *C*,
what *B* would do for *C*: *B* writes its own slots, its own use entries, its
own credits, and its own gate writes the machine-table words whose writer it
already is (the attach words, the context entries), each checked against words
that name *C*. What is left is *C*'s availability (a grant *B* releases, a
credit *B* frees, a role *B* takes from a `Handed`, a device attach *B*
performs for *C*) and the marks attributed to *C* — and the contract already
says what a lying sender is worth: "kernels trust each other's stamping as
they trust each other's checks; a kernel that lies about marks is faulty,
which the gate does not contain (it damages the marks of what it sends and
availability, never another node's memory)" (`kernel-interface.md:966`). No
message of any kind writes an ownership word or a map count, so no message
lets a node translate memory it does not own; that is the whole of G. Requiring
the header's sender to be the ring's sender would buy nothing: G makes the
sender the only writer of its own rings ("the rings whose sender is *X*" is
writable, `kernel-interface.md:1063`), so *A* always writes ring *A*→*B* and
the name in the header is never checked against anything *A* does not control.
The second reading adds a comparison and closes no lie.

---

## Notes on the report's notes, and what I did not run

- The report's notes stand as they are; I checked `check/tasks.rs:55`
  (`ensure(true, "50: running thread of a revoked task")` after the real check
  at line 50-54): dead code, no defect.
- Not run by me: finding 4's patch (said above); the three "not run" panics of
  finding 6 (judged, two are unreachable and one refuted); the `DODOS_SEED`
  typo (read).
- The report's severity of finding 1 is too high (its consequence is caught by
  57) and its severity of finding 3 as a whole is right but split: the
  contract's half is the serious one.

---

## Table

| # | Finding | Verdict | Severity (mine) | Correction in one line |
|---|---|---|---|---|
| 1 | Invariant 52 accepts a take that names the old owner or unclaimed | real, the model's fault | low | `check/table.rs:45`: `named = after_owner == writer \|\| (reserve && after_owner == owner)`; test `ver2_a_take_journaled_in_the_old_owners_name_is_accepted`; the harmful state is already caught by 57, the unclaimed one is harmless |
| 2 | `io_width` unchecked: start-up takes it, check and `iospace_map` panic | real, the model's fault | moderate | `boot.rs:621` refuses a width below the page shift or 64 and above; test `the_start_up_accepts_any_io_width`; contract gains one item in the refusal list at `kernel-interface.md:1995` |
| 3 | A fresh generation adopts a dead generation's ring sequences | real, the contract's fault (the guarantee "writing never fails and never waits" breaks) | moderate | one clause at `kernel-interface.md:1553` (sequences must be ≥1 and agree with the ring) and one at `:1550` (wrap to 1); model: `enter_debug_areas` clears such an area, `write` uses `checked_add`; tests `ver2_a_fresh_start_adopts_...`, and both ring tests |
| 3 | `ring_holds` panics on `next = 0` or at `u64::MAX` | real, the model's fault | low | `check/debug.rs:16`: `next >= 1` first, `checked_add` for `entry.seq + entries`; same two ring tests |
| 4 | A remote root capability may hold rights the grant never gave | real, the model's fault | hardening (the gate's promise still holds: "what *X* was granted") | `Remote` keeps the anchor's rights (`grants.rs:21`); 3 asks equality, 58 asks `remote.rights ⊇ t.rights`; test `ver2_rights_of_a_remote_frame_beyond_the_grant_are_accepted` (not patched by me) |
| 5 | G4 for a device entry is "at least", not the leaves | real, the model's fault | hardening | `check/machine.rs:149`: equality while the entry's owner runs, as for a chunk; test `ver2_a_device_leaf_count_above_its_leaves_is_accepted` (the entry must belong to a running node) |
| 6 | The checker panics where it should name the invariant (sched, rings, memory) | real, the model's fault | low | `check/sched.rs:40`: `runs` total via `self.threads.get`; ring and io_width panics as in 2 and 3; test `ver2_a_lend_to_a_missing_receiver_panics_the_checker` |
| 6 | `regs[REG_DR0..=REG_DR3]` panics for a short register block | refuted | — | `regs` is always `REGS_WORDS` = 26 words (`faults.rs:190` refuses another length); nothing to fix |
| 6 | `areas[core.number]` and `owners[chunk]` panic | not reachable by any call | — | defensive only; the indices come from the machine's own core list and memory map |
| 7 | Five checks that no test makes fail | real (the tests) | low | a `spoiled`-style test per message; verified: the five disabled together leave all 19 binaries green (1158 tests) |
| 7 | The checker's own test of G6 is vacuous; `pass18` guards it | real (the tests) | low | drop the `|| report.contains("58")` disjunct and the dead `let _ = Member::new;`; the mutation shows `pass18` fails and this test does not |
| 7 | `DODOS_SEED` that does not parse silences the exploration floors | real (the tests) | low | parse the variable once; `seeds()` and `reached()` use the parsed value |
