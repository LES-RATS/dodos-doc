# Model review 12: the model of pass 22 against the contract, and its tests

Reviewer: DeepSeek. Copy of the model: `/private/tmp/dodos-pr3-review22`, made
from `/private/tmp/dodos-pr3-p22` at `acecf8f` (the pass's second commit; the
pass runs from `6312868` to `acecf8f`). Contract read:
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` at
`a0e5848`, D-141 last. I read `AGENTS.md` and the two skills before starting.
I never read or edited `/Users/btw/Documents/repos/dodos-kernel`.

Method. Everything below was run in that copy. The baseline, before any
mutation, is the whole library suite:

    nix develop -c cargo test -p dodos-model --lib -- --skip review22
    -> test result: ok. 591 passed; 0 failed; 8 filtered out

Every mutation is applied by a script that asserts the replaced text occurs
exactly once, then the named test is run, then the whole library suite with my
own tests skipped (`-- --skip review22`), then the file is restored from a
pristine copy and `git status` is checked. Nothing was committed; the only
tracked edit in the copy is my `mod review22;` line, and nothing outside the
copy was written except this file.

**Headline.** The pass is careful and the model follows D-141 almost
everywhere it can be run. Two things it gets wrong: a revocation that reports
the root removed frees the grant entry but leaves the grant's anchor in the
granting node's kernel space, so the next grant reuses that slot and writes a
second anchor into it, after which the checker reports the space inconsistent
(finding 1, the only state-corrupting one). And the model has no ITS `Report`
item at all: kinds 3 and 4 of D-141's key scheme, and the words that go with
them, are modelled nowhere (finding 5). Four clauses of the contract's
start-up list and ring step are also unenforced or over-enforced (findings
2 to 4). The tests are the weaker half: of 74 mutations of the pass's own
tests, 7 leave the whole suite green (findings 6 to 11), and of my 20
mutations on the changed code, 16 survive, three of them on rules no test
touches at all (findings 12 to 25). One legacy test that was vacuous was deleted and its replacement does
bite; one new Kani assumption is correct against the contract but the proof
covers less than it did.

---

## 1. The model against D-141, point by point

**1.1 The sender is the ring's writer.** `model/src/rings.rs:381-389`
(`refused`) refuses a message whose header names a node other than the one
whose ring it was read from, and a generation or a member state that does not
match. Three of the pass's tests fail when that check is removed
(p22-01, p22-02, p22-03), so it is both present and tested. Holds.

**1.2 The grant entry's anchor, and what a holder maps.** The anchor is the
capability in the granting node's kernel space at `anchor_index(grant)`
(`grants.rs:46`), and `Anchor` (`table.rs:220-237`) carries the frame, the
rights and the depth. What a holder maps comes from the anchor and not from
the message: `grants.rs:519-550` takes `anchor.frame`, `anchor.rights` and
`anchor.depth` for the remote root, and `grants.rs:325-333` writes the anchor
that the gate's own capability names. Mutations p22-07 (rights from the
message), p22-08, p22-09 (a depth of 0), p22-64 (rights beyond the anchor)
and p22-11 (a frame the gate does not hold) all turn the named test red.
Holds — except that freeing a grant does not always free its anchor
(finding 1).

**1.3 The release rule, and the map before an answer.** `revoke_answered`
(`grants.rs:795-815`) frees the entry only when `holder_count` is 0, and
`holder_count` (`grants.rs:397-409`) reads the use entry the holder's gate
wrote — filtered on granter, grant, serial and the granting node's
generation. `send_received` refuses a map of a received frame before the
sender's answer (`p22-06` red). Holds in the code; two clauses of it are
untested (findings 12 and 15).

**1.4 `memory_control` in `fits` and invariant 28.** `caps.rs` places a
`memory_control` at a depth not smaller than the space's root, and the check
reports a `memory_control` that is shallower (`chk-01` red on
`memory_control_capability_less_deep`). Holds.

**1.5 Kept debug areas and crash headers read as a faulty kernel's data.**
The checker does not trust a crash header's own counts: `check/table.rs:255-284`
recounts the leaves from the translations themselves, and the debug area is validated against its ring by
`debug.rs:81-88` before it is continued. The start-up side is where it fails
(findings 3 and 4).

**1.6 The credit ranges, the reserve of answers, the producer behind the
consumer.** `rings.rs:418-434` holds a request to 0-15 and a send to 16-23
and refuses a `UnitRequest` whose unit-service entry is taken;
`rings.rs:435-441` refuses a request whose answer would not fit, the answer's
own entry count included; `ring_room` (`rings.rs:290-305`) keeps
`RING_ANSWER_RESERVE` for answers only. `rings.rs:594-608` moves a consumer
index that is behind the producer to it, and one that is more than the ring
ahead to producer minus the entries. p22-12, p22-13 and p22-14 are red when
each is removed. Holds; the step's count is wrong (finding 2).

**1.7 `Report`: its count, its keys, its ITS items, its tie to the device's
owner.** `Item` (`rings.rs:70-75`) has three kinds and `Item::key`
(`rings.rs:82-88`) shifts 0, 1 and 2 into bits 61-63. Contract
`kernel-interface.md:960` has five kinds and says so in as many words: "0 a
device, 1 a remapping handle, 2 a line, 3 an ITS device, 4 an ITS event".
`REPORT_ITEMS = 28` (`rings.rs:92`) matches the contract's count. p22-28 (the
device's owner), p22-29 (a key that does not advance) behave; the ITS gap is finding 5.

**1.8 A context marked *moving*.** `sched.rs` excludes a moving context from
the eligible ones and the check reports a moved context whose holder changes
(`p22-32` red). Holds.

**1.9 A level line on another node held by the controller.** `irq.rs` masks a
level source at the controller before the end of its interrupt and holds it
on the controller's Remote IRR otherwise (`p22-45` red). Holds.

**1.10 The orders of the rings, the slot read, the clock, the interrupts
between cores.** The slot read's re-read, the clock page and the interrupt
between cores are covered by p22-14, p22-26, p22-44 and p22-59; the last shows
that one of the pass's own tests does not test its clause (finding 11).

**1.11 The fence's waits as due events.** p22-40 (a debugger stop during R1),
p22-54, p22-55, p22-56, p22-57 and p22-58 all turn red when the rule they
name is removed, and none of them waits without a due event. Holds.

**1.12 RMRR devices on the unit's own domain.** `boot.rs` attaches each RMRR
device to the kernel's own domain, the unit's last number; the split of the
numbers is `(D - 2) / n` at `boot.rs:753-756`, exactly the contract's
`d = ⌊(D − 2) / n⌋` with `d = 0` refused, and `pass17`'s rewritten test
covers `d = 0` (15 slots, 16 domains) and `d = 1` (14 slots, 16 domains).
Holds.

**1.13 `memory_split`, pinned iospace pages, and the `Report` of a line.**
p22-17, p22-18 and p22-19 are red when the pinned entry's count, the pages a
failed unit keeps or the kept unit after a failed detach are broken. Holds;
one count is untested (finding 25).

**1.14 The start-up refusals of D-141.** `boot.rs:675-718`
(`values_in_range`) refuses overlapping ranges, a `phys_bits` under the chunk
or above 63, an unknown core kind, a window of 1024, an io width out of
range, a unit's domains outside 16 to 65,536, and a crash base off a chunk
boundary (`p22-37`, `own-12` red). Two refusals of the same sentence list are
missing: findings 3 and 4.

**1.15 The identity of the `Report`'s device and its owner's table.**
`roles.rs` reports a device whose identifier word names another node
(p22-28), whose root differs from the record's (p22-51), and refuses a report
whose keys do not rise (p22-29); three clauses of it are untested
(findings 16, 18 and 19).

---

## 2. The attacks

Seven attacks (§2.1 to §2.7) and one measurement (§3.4) in
`model/src/scenarios/review22.rs`, in my copy only (the file is
untracked and never part of the pull request). Each reaches its state by calls
a user can make, by boot-image values, or by words a faulty kernel writes into
its own rings with plain stores. Four of them find a bad state; three find
none, and they are reported because a negative result is a result.

### 2.1 A grant index reused after a revocation. Finding 1.

`a_grant_index_reused_after_a_revocation_overwrites_the_anchor_of_the_old_one`
takes two nodes and a granted frame, has the holder map it so that the use
entry counts a leaf, revokes the grant from node 0, and lets the revocation
complete: the holder removes its root and answers, `revoke_answered` frees the
grant entry — but not the anchor (`grants.rs:809` calls `free_grant`, while
the removal path at `grants.rs:584` calls `free_with_anchor`). Then a second
thread of node 0 sends the same frame to a third node: the index is free, so
its anchor is written into the slot the old anchor still occupies.

    nix develop -c cargo test -p dodos-model --lib \
      review22::a_grant_index_reused_after_a_revocation -- --nocapture
    thread '...a_grant_index_reused_after_a_revocation_overwrites_the_anchor_of_the_old_one'
      panicked at model/src/scenarios/review22.rs:133:21:
    assertion `left == right` failed
      left: Err("node 0: 6: slot of a capability")
     right: Ok(())

Two capabilities claim one slot, so the space the model keeps is no longer a
tree, and every later removal, revoke and check of node 0 reads it. The state
is reached by calls alone: `cap_revoke` on the frame, then `node_send`.

### 2.2 One interrupt serves more than sixteen entries. Finding 2.

`one_interrupt_serves_sixteen_entries_and_not_more` writes four `Send`
messages of five entries each into node 0's user ring from node 1 (a faulty
kernel's own ring: `m.sys.inject`), then fires one interrupt:

    nix develop -c cargo test -p dodos-model --lib \
      review22::one_interrupt_serves_sixteen_entries -- --nocapture
    panicked at model/src/scenarios/review22.rs:160:5:
    assertion `left == right` failed
      left: 20
     right: 16

`consume` (`rings.rs:624`) adds the length of the message it just served, and
the loop condition is checked before the message, not after it, so a message
that straddles the sixteenth entry is served whole. The contract bounds the
interrupt, not the message: "at most 16 entries per ring per interrupt"
(`kernel-interface.md:971`).

### 2.3 The values of the machine, fuzzed. No panic.

`random_values_of_the_machine_are_refused_or_accepted_but_never_panic` builds
300 machines from `Machine::example()` with one value drawn at random each
round — `phys_bits` 30 to 45, `io_width`, a unit's domains up to 70,000, an
overlapping or wrapping memory range, a crash area off alignment or over the
previous one, an unknown core kind, a `BootNodes` window and a boot core the
machine may not have — and boots each inside `catch_unwind`:

    test scenarios::review22::random_values_of_the_machine_are_refused_or_accepted_but_never_panic ... ok

No refusal of the list panics; the model's start-up is total on these.

### 2.4 Two refusals of the list that do not happen. Findings 3 and 4.

`a_kept_range_past_maxphyaddr_or_a_crash_area_over_a_kept_range` builds the
example machine with `phys_bits = 40`, all usable memory below 2^40, and a
kept range at 2^45; the contract refuses it ("MAXPHYADDR ... below the end of
a usable or kept range", `kernel-interface.md:2004`):

    panicked at model/src/scenarios/review22.rs:217:5:
    Ok(Ok(()))

`values_in_range` (`boot.rs:689-698`) filters `RegionKind::Usable` only, so a
kept range is never held to the physical width. The same test's second half,
and `a_crash_area_over_a_kept_range_is_refused` on its own, put the crash
area over a kept range, which the same sentence of the contract refuses
("its range overlaps another kept range"):

    panicked at model/src/scenarios/review22.rs:236:5:
    Ok(Ok(()))

`values_in_range` (`boot.rs:712-716`) checks only that the two crash areas
differ (`p != self.crash.0`); it never compares either with `kept` or
`feedback`.

### 2.5 A faulty kernel's own words, fuzzed into the live table. No panic.

`random_words_of_the_living_part_never_panic_the_check` spoils, in 300 rounds,
one part of the table a node's gate writes — an ownership word, a line's
word, a device entry with a random ownership word and range, a use entry with
a random root and leaves, a grant entry with a pinned state and a random use
index — then calls the checker inside `catch_unwind`:

    test scenarios::review22::random_words_of_the_living_part_never_panic_the_check ... ok

Every one of the 300 bodies is reported rather than panicking. The checker
does not index with an unvalidated word.

### 2.6 The model after such a fault. No panic.

`the_model_never_panics_after_a_faulty_kernel_spoils_its_table` does the same
to 120 tables but then steps the model eight events with a seeded generator
before checking:

    test scenarios::review22::the_model_never_panics_after_a_faulty_kernel_spoils_its_table ... ok

The events offered on a body the check refuses do not panic either.

### 2.7 What I could not break.

A message in another node's name: refused by `rings.rs:387` and the receiver
counts it (`p22-01..03`). A holder that maps outside its grant's anchor: the
map takes the anchor's frame, rights and depth, and there is no way to name a
frame the anchor does not hold (`p22-07..09`, `p22-64`). A grant freed while
translated: G6 reports it, and the pass's own mutation shows the test bites
(§4.2). A cycle or an endless removal: every removal step is bounded and the
`again` returns to the user; I found no removal that neither ends nor
returns. A wait that never ends: the waits I could reach (a `Revoke` step, a
unit request, a resume, a park) all have a due event or an answer that ends
them; the resume loop's bound is finding 21.

---

## 3. Do the new tests test what they name?

Two rounds per mutation. First the test named for the rule, then the whole
library suite with my own tests skipped, so that a clause another test also
covers is not counted as a hole. The harness asserts each mutation applies
exactly once, restores the file from a pristine copy afterwards, and
`git status` is empty but for my `mod review22;` line between runs.

### 3.1 The size of it.

The pass adds 68 scenarios in `pass22.rs` and changes tests in `abi/src`
(4), the checker scenarios (1) and `model/tests/property.rs` (1). I mutated
each rule they are named for: 74 mutations. 66 turn their test red on the
first round. Seven survive both rounds (six are findings, one is equivalent),
and one does not compile, so it is not a mutation at all.

Red on its own test, in order of the file: p22-01 (the sender on a third
node's ring), p22-02 (a send in another's name), p22-03 (a detach in
another's name), p22-04 (the holder's count of a release), p22-05 (a revoke
step that reports the root removed), p22-06 (a map before the sender's
answer), p22-07 (the anchor's rights), p22-08 (a send stating other rights),
p22-09 (a depth of 0), p22-10 (a second send naming an answered grant),
p22-11 (a frame the gate does not hold), p22-12 (a send credit on a unit
request), p22-13 (an answer that would not fit), p22-14 (a producer behind
the consumer), p22-15 (the sixteen entries of a step), p22-16 (a reserve
chunk taken by this generation), p22-17 (`memory_split`), p22-18 (pages a
failed unit pins), p22-19 (a kept unit after a failed detach), p22-20 (a
remote frame as a message page), p22-21 (the previous crash area at
sequence max), p22-22 (a next sequence of 0), p22-24 (a disagreement with
the ring), p22-26 (consumed from 0), p22-27 (`memory_control` in `fits`),
p22-28 (a device naming another node), p22-29 (a report whose key does not
advance), p22-30 (a second hand), p22-31 (the entries of a dead generation),
p22-32 (*moving*), p22-33 (an unhooked table's free list), p22-34 (ioport
through a capability), p22-36 (a thread leaving), p22-37 (the values of the
machine), p22-38 (a segment without read), p22-40 (a debugger stop during
R1), p22-41 (a spurious fault), p22-42 (a signal to a generation that is
over), p22-43 (a signal to a sealed granter), p22-44 (a core event),
p22-45 (a level line on another node), p22-46 (APIC ID 255), p22-48 (a
failing unit on a map), p22-49 (the holder's judgement of a masked line),
p22-50 (a unit of the wrong kind), p22-51 (a rebuild naming another root),
p22-52 (a rebuild over a passed-over node), p22-53 (the remapping handles a
rebuild keeps), p22-54 and p22-55 (a core going idle), p22-56 (a spare core
parked), p22-57 (a resume consuming its user ring), p22-58 (a resume after a
peer died sealed), p22-60 (an address past the ownership words), p22-61 (a
gate whose node does not write), p22-62 (a take in the old owner's name),
p22-63 (a leaf count above the leaves), p22-64 (a remote root with rights
beyond the anchor), p22-65 (a send's words against its header), p22-66 (a
reserved mark bit), p22-67 (a send answer not delivered), abi-01 (a geometry
shift near 255), abi-02 (`dr7` and an I/O breakpoint), abi-03 (a credit
index past the credits), abi-04 (a clock page shift of 128), chk-01
(`memory_control` less deep).

### 3.2 The survivors that are equivalent, and the mutation that does not compile.

**p22-39.** `the_start_up_page_counts_its_records_at_the_sizes_of_the_abi`
(`pass22.rs:1165`) asserts the total and two record sizes; the mutation
replaces `size(std::mem::size_of::<dodos_abi::StartProcess>())` in
`boot.rs` with `40`. `StartProcess` (`abi/src/start.rs:167-174`) is four
`u64` and two `u32`, which is 40 bytes, so the mutant computes the same
number: no observable state differs. Not a hole, and no test could catch it.

**own-18.** `roles.rs`'s `advances` is `next == REPORT_END || last.map_or(next
> asked, |l| next > l)`. Dropping the first disjunct changes nothing:
`REPORT_END` is all ones, so `next > asked` and `next > l` hold for it
whenever they hold at all, and when `last` is `None` the comparison is
`REPORT_END > asked`, true for every key. Equivalent.

**own-07.** `memory.rs:885`'s `served.first().is_some_and(|&(other, _)|
other != iommu)` is the rule that an iospace serves the devices of one unit
only; the mutation takes `.last()`. Equivalent in every state the gate
reaches: an iospace gets a second unit only if this check lets it, so the list
never has two units and `first()` and `last()` are the same entry. It would
differ only on a body a faulty kernel writes, and no invariant judges that
list. Not a hole; the check needs no test, though a comment saying why would
save the next reviewer the same hour.

**prop-01.** Reversing the pass's `dying: [u32; ObjectKind::ALL.len()]` to
`[u32; 19]` does not compile against the current `ObjectKind::ALL`, so it is
not a mutation of behaviour. The pass's change is a compile-time bound, which
is the right way to make it; no mutation of it can be meaningful.

### 3.3 A test that is red, but for another test's clause. Finding 11.

**p22-59** (`the_start_up_refuses_the_values_of_the_machine_out_of_range`).
The mutation removes the "start-up page does not fit" refusal from
`boot.rs`; `a_start_whose_page_does_not_fit` stays green, and the whole
suite catches it through a different test:

    python3 mutall.py 5 1
    p22-59-start-page	RED	all	scenarios::pass22::the_start_up_refuses_the_values_of_the_machine_out_of_range

So the refusal is covered, but not by the test named for it. Severity: low.
Where: `model/src/scenarios/pass22.rs`, `a_start_whose_page_does_not_fit`,
which builds a machine whose failure it does not distinguish from the other
values of the list. Correction: assert the refusal code and the trace of that
refusal in `a_start_whose_page_does_not_fit` itself (as
`the_start_up_refuses_the_values_of_the_machine_out_of_range` does), so that
the test fails when the page rule alone is removed.

### 3.4 Six tests of the pass that stay green. Findings 6 to 10.

**Finding 6, p22-25: `a_debug_area_that_agrees_is_continued`
(`pass22.rs:704-710`) does not test that the area is continued.** The
mutation makes `continues()` (`debug.rs:81-88`) return `false`, so no area is
ever continued; the test stays green in both rounds:

    p22-25-continued	GREEN	all

The test records the area's `next_kernel` before the restart, asserts it is
above 1, then asserts the area after the restart is `>= next`. I measured both
sides. Unmutated, the same machine reads `before: 2, after: 3`; with
`continues()` forced false it reads `before: 3, after: 3`
(`review22::what_the_continuation_test_sees`, a copy of the test with the two
numbers printed). Both satisfy `next > 1` and `after >= next`, so "cleared"
and "continued" are indistinguishable to the assertion. Severity: medium, because the continuation of the
debug area is the rule the pass exists to add and nothing tests it. Where:
`pass22.rs:704-710`. Correction: assert what continuation means — the
entries the ring held before the restart are still there and the area's
sequence is that of the last entry, so write one entry with a known sequence,
restart, and assert the area still names it; the mutation above then fails.

**Finding 7, p22-23: `a_debug_area_whose_next_sequence_is_2_to_the_63_is_cleared`
(`pass22.rs:689-692`) is decided by another clause.** The mutation widens
`(1..1 << 63).contains(&next)` (`debug.rs:83`) to `(1..u64::MAX)`, so a next
sequence at or above 2^63 passes the bound; the test stays green:

    p22-23-next-seq-2-63	GREEN	all

It stays green because the area's ring still holds a sequence of 2, so the
area is cleared for the disagreement, not for the bound. Severity: low.
Correction: make the ring agree with the value under test (write the entry
whose sequence is the area's next, as the pass's other area tests do), so the
bound is the only reason left to clear it.

**Finding 8, p22-35: `an_ioports_word_that_names_no_range`
(`pass22.rs`) tests the helper, not the call.** The mutation makes a word
that names no range fall back to `IoPortRange::ALL` instead of `busy`
(`debug.rs`, `range_of(held.badge).ok_or(Error::Busy)`), which admits every
port; green:

    p22-35-no-range	GREEN	all

The test asserts on `range_of` directly, so the call that uses it is not
exercised: no `ioport_in` or `ioport_out` goes through the changed line with
a badge that names nothing. Severity: low. Correction: claim an I/O source
with such a badge and assert `busy` from the call, not the helper's `Err`.

**Finding 9, p22-47: `an_iospace_map_where_units_cache_absent_entries`
(`pass22.rs`) does not test the `again` of a full unit-request table.** The
mutation removes the `if asks && self.unit_requests.iter().all(Option::is_some)`
guard (`memory.rs`), so the mapping is recorded before the requests that
must cache it are in flight; green:

    p22-47-caching-map	GREEN	all

Severity: low. Correction: fill the unit-request table (64 entries) and
assert that the `iospace_map` returns `again` and writes no record, then run
the requests and assert the map is recorded.

**Finding 10, p22-68: `the_start_up_space_counts_the_copied_frames`
(`pass22.rs`) does not test the watermark's alignment.** The mutation
replaces `watermark = watermark.next_multiple_of(bytes) + frame.pages * bytes`
(`boot.rs:1232`) with a plain addition; green:

    p22-68-copied-watermark	GREEN	all

It is not equivalent in principle — `module_frames` (`abi/src/module.rs`,
tested at `abi/src/tests.rs:1608`) chooses the frame size from the
alignment of the physical base it is given, so a watermark left at 4 KB
before a 2 MB copy changes what is copied — but the test's machine has
modules of one size, where the two forms agree. Severity: low. Correction:
give the machine two writable segments whose copied lengths are 4 KB and
2 MB in that order, and assert the second copies one large page.

### 3.5 My own twenty mutations. Findings 12 to 25.

Chosen where a wrong implementation is likely: the grant's serial and anchor
(the two things that make a use entry meaningful), the counts a removal
depends on, the report's keys, the events the scheduler accumulates, and the
guards that keep a stale capability out. Four are caught (`own-06`, an
eight-byte record of the start page; `own-12`, the io-width floor;
`own-13`, a check word written by a gate; `own-20`, a cleared area traced).
Sixteen survive both rounds; fourteen are findings and two are
equivalent (own-07 and own-18, §3.2). Each entry below is the mutation, then the run, then what it
means.

**Finding 12, own-15:** `memory.rs` `if entry.use_index != Some(remote.use_entry)
{ return Err(Error::Gone) }` → `if false`. Rule it removes: D-141's "a grant
is freed only on the count of the use entry the holder's gate wrote, whose
index the granting node recorded before the first leaf" — the tie between
the granting node's recorded index and the index the holder's root names.

    own-15-use-index-tying	GREEN	all

So no test reaches a remote capability whose root names another use entry
than the one the grant recorded. Severity: medium: this is the one check
that stops a holder from making the granting node act on another entry's
leaves. Correction: a test that maps a received frame, hand-writes a remote
`Remote` whose `use_entry` differs from the grant's, and asserts `Gone`.

**Finding 13, own-01:** `next_serial` (`grants.rs:923-925`) `(serial + 1) &
0x3FFF_FFFF` → `serial + 1`. Rule: the serial is 30 bits (contract, `Report`
and `Send` fields, bits 12-41).

    own-01-serial-wraps	GREEN	all

No test drives a serial to 2^30 and watches it wrap to 0. Severity: low (the
ABI truncates the field, so a wrong model would show only under a wrapped
serial), but the wrap is the only place a stale use entry and a live one can
share a serial. Correction: a test that sets the serial near the mask, frees
and re-grants, and asserts the new serial is 0.

**Finding 14, own-02:** `grants.rs`'s `Owner::Reserve(j) =>
self.table.holds_reserve(me, j)` → `false`, i.e. a gate's anchor may be a
frame from a reserve chunk not taken by this generation.

    own-02-anchor-reserve	GREEN	all

`p22-11` covers the ordinary memory case (`node_send_refuses_a_frame_whose_chunk`)
but not the reserve case. Severity: medium: a node granting a frame from a
reserve it does not hold is exactly the fault the pass's sentence forbids.
Correction: a test that builds a reserve chunk owned by another generation
and asserts `busy` from the send.

**Finding 15, own-03:** `holder_count`'s filter `&& u.generation ==
generation` → `&& true` (`grants.rs:406`).

    own-03-count-generation	GREEN	all

No test builds a use entry of another generation with the same granter,
grant and serial, so a count that crosses a generation is untested.
Severity: low. Correction: after a holder's generation is over, leave its
use entry in place with its leaves and assert the granting node's revocation
does not treat it as its own holder's count.

**Finding 16, own-04:** `roles.rs`'s `let good = items.len() <= REPORT_ITEMS
&& rising && advances` → `let good = rising && advances`.

    own-04-report-at-most	GREEN	all

Nothing tries a `Report` of 29 items, so the contract's "at most 28" and the
model's `REPORT_ITEMS` (`rings.rs:92`) are unguarded by tests. Severity: low.
Correction: a test that hand-writes a `Report` of 29 items and asserts it is
refused and traced.

**Finding 17, own-05:** `revoke_received`'s `entry.release_pending ||
!self.objects.contains_key(&entry.root)` → `!self.objects.contains_key(...)`
(`grants.rs:774`). Rule it removes: "a `Revoke` that finds the root already
removed (its release pending) answers removed, drops the pending release and
frees the use entry" (`grants.rs:759-765`).

    own-05-release-crossing	GREEN	all

With the disjunct gone the model removes a root whose release is already
pending — a second removal of the same root. No test has a `Revoke` arrive
after the holder's `Release`. Severity: medium: it is the one crossing
between the holder's release and the granting node's revocation, and the
contract states it in as many words. Correction: a test that has the holder
release (root removed, `Release` sent) and then the granting node's revoke
arrive, and asserts `RevokeStep { removed: true }` and the entry freed.

**Finding 18, own-08:** `roles.rs` `let above = last.map_or(key >= asked, |l|
key > l)` → `map_or(key > asked, ...)`.

    own-08-report-rises	GREEN	all

No test asks a report from a key that is present, so the inclusive first
comparison is untested. Severity: low. Correction: ask from a key that
exists and assert it is the first item reported.

**Finding 19, own-09:** `roles.rs`'s `if !good {
self.refuse_trace(reporter, NodeMessage::Report, device) }` → `if false`.

    own-09-report-item-traced	GREEN	all

The code-11 trace of a report item that fails its own check is required —
code 11 is "a message between nodes refused by the check of What crosses
between nodes ... naming a grant, a role or a request that does not match"
(`kernel-interface.md:1570`) — and no test reads it. Severity: medium (a trace
the contract names, dropped silently). Correction: a test that has a report
item fail its check and asserts the trace ring's code 11 with the reporter
and the device.

**Finding 20, own-10:** `sched.rs` `*self.last_event = self.last_event.map(|(kind, n)| (kind, n + entered))`
→ `(kind, entered)`.

    own-10-last-event-adds	GREEN	all

No test reads `last_event` after two events of the same kind in one window,
so the accumulation is untested. Severity: low. Correction: two events of one
kind and assert the sum.

**Finding 21, own-11:** `nodes.rs`'s `if *units == 0 { return any; }` →
`if false`.

    own-11-resume-bounded	GREEN	all

The bound of the resume loop (no unit left to wait for) has no test: nothing
resumes a node whose units are all done. Severity: low. Correction: resume
after every unit confirmed and assert the loop ends in one pass.

**Finding 22, own-14:** `check/machine.rs`'s `self.has_generation(n,
word.generation()) && self.running_node(n)` → `self.has_generation(n, ...)`.

    own-14-device-running-node	GREEN	all

A device leaf count on a node that is not running is untested, so the check
does not distinguish a dead node's device from a live one in any test.
Severity: low. Correction: a check on a table whose device owner names a
stopped node.

**Finding 23, own-16:** `grants.rs`'s `if self.valid(&remote) &&
self.write_message(...)` → `if self.write_message(...)`.

    own-16-signal-valid	GREEN	all

A signal aimed at a remote capability that is no longer valid (its generation
over, its use entry gone) is untested; the model would write the message
anyway. Severity: medium: `valid` is what keeps a stale remote capability from
reaching another node. Correction: a test that lets the generation pass and
asserts the signal is refused and no message written.

**Finding 24, own-17:** `memory.rs`'s `if self.table.attach_word(key).state()
== Some(AttachState::Attached)` → `.state().is_some()`.

    own-17-detach-attached	GREEN	all

The detach's condition is untested for the *pinned* state. Possibly
equivalent in the model's reachable states — a detach can only be called on
an attached device, since the earlier state checks refuse the rest
(`kernel-interface.md:390`) — but nothing shows that, and the mutation is not
provably a no-op. Severity: low. Correction: a test that calls a detach while
the attach word is *pinned* and asserts `busy` is reached by the earlier
state check and not by this one; or drop the redundant clause.

**Finding 25, own-19:** `caps.rs`'s `lost += 1 + space.tables as u32` →
`lost += 1`.

    own-19-lost-count	GREEN	all

The chapters an iospace's destruction loses (its root plus its tables) are
compared in no test, so the count the owner waits for is untested. Severity:
low. Correction: destroy an iospace with two tables and assert the untyped's
`lost`.

---

## 4. What the pass weakened

### 4.1 The Kani proof `a_header_reads_back_its_credit` (`abi/src/ring.rs:355-377`).

The pass changed the assumption from

    kani::assume(index < CREDIT_NONE && serial <= CREDIT_SERIAL_MASK);

to

    kani::assume((index as usize) < REQUESTS_PER_PEER + SENDS_PER_PEER);
    kani::assume(serial <= CREDIT_SERIAL_MASK);

and changed `credit()` (`abi/src/ring.rs:227-234`) from `if index ==
CREDIT_NONE { None }` to `if index as usize >= REQUESTS_PER_PEER +
SENDS_PER_PEER { None }`, which is the contract: "0 to 15 are the request
credits, 16 to 23 the send credits, 31 none, and no other value is a credit
(D-141)" (`abi/src/ring.rs:224-226`, `kernel-interface.md:960`). The new
assumption is exactly that set (0 to 23, `REQUESTS_PER_PEER = 16`,
`SENDS_PER_PEER = 8`), so it is the contract's and not a way around a
counter-example. What the pass gave up is the older, wider claim: the proof
used to cover 0 to 30 and now covers 0 to 23. The gap it no longer covers is
real in the code — `RingHeader::new` (`abi/src/ring.rs:211`) still masks the
index with `0x1f` and stores 24 to 31 verbatim, so `new(.., Some((24, s)))`
builds a header whose `credit()` is `None`. No test passes an index outside
0 to 23 to `new`, and the model never does, so nothing is wrong today; the
narrowing is honest, not a weakening of what is claimed. Two things I would
ask for: a `debug_assert` or a refusal in `new` for an index it cannot read
back, and a sentence in the proof saying why 24 is the bound.

**Not run.** The proof was not executed: `cargo kani` cannot preprocess in
this environment.

    nix develop -c cargo kani -p dodos-abi --harness a_header_reads_back_its_credit
    Kani Rust Verifier 0.68.0 (cargo plugin)
    CBMC 6.11.0
    error: tool 'gcc' not found
    preprocessing has failed
    error: goto-cc exited with status exit status: 1

Everything I say about the proof above is reading, not a run.

### 4.2 The test that was deleted, and the one that replaces it.

`model/src/scenarios/checker.rs`'s `a_grant_freed_while_its_holder_
translates_to_it_is_reported` was removed and replaced by three lines of
comment (`checker.rs:521-523`). The deletion is right: the test accepted
`report.ends_with("G6: a grant freed while its holder translates to it") ||
report.contains("58")`, so it passed whichever invariant fired, and on a
running holder node invariant 58 names a fault first — the pass's own
verification (`reviews/2026-11-17-final-ver2-D-opus.md`, item 7) found it
vacuous. Its replacement is
`pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6`
(`pass18.rs:558`). To show the replacement bites, I turned G6 itself into no
check:

    model/src/check/machine.rs:185
      ensure(held, "G6: a grant freed while its holder translates to it")?;
    ->
      ensure(true, "G6: the same string")?;
    nix develop -c cargo test -p dodos-model --lib -- --skip review22
    -> test result: FAILED. 590 passed; 1 failed
       failures:
         scenarios::pass18::a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6

One test in the suite, and it is the replacement. Nothing was lost with the
deletion.

### 4.3 The rewrites that are legitimate.

`pass17::the_start_up_refuses_a_unit_with_fewer_domain_numbers_than_node_slots`
had to be rewritten, because 16 is now the floor of a unit's domains
(D-141) and its old values (4 and 5) are refused by the new width check
before the node-slot rule is reached. Its new form (15 node slots against 16
domains refused, 14 slots against 16 domains accepted) is exactly the
contract's `d = ⌊(D − 2) / n⌋ ≥ 1`, and it now goes through
`machine.layout()` rather than `System::boot`, which is one step of the path
no longer exercised end to end — a note, not a fault. The rest of the diff's
edits to other files are mechanical and correct: `clear_mapping_pub` becomes
`clear_mapping` (`pass20.rs:797`), `Anchor::test()` is added to every
hand-written grant entry (`checker.rs:442`, `mistral.rs:163` and `363`, `reviews.rs:405`), `Remote` gains `rights` (`mistral.rs:193`), `rebuilt_attach`
gains the owner pair (`pass21.rs:580`), and `crossing.rs`'s `refused` gains
the ring's sender as its first argument (`crossing.rs:579-584`), which is
D-141's own rule and the reason the function changed. None of these hides a
rule.

`model/tests/property.rs`'s `dying: [u32; 19]` became
`dying: [u32; ObjectKind::ALL.len()]`, a compile-time bound that cannot drift
from the enum. Good change; no mutation of it can be meaningful (§3.2).

### 4.4 The assertions that got weaker, in order of how much they cost.

The pass's suite leaves these clauses unguarded, and the mutations above show
it: the continuation of a debug area (finding 6, the pass's own new rule); the
tie between a grant's recorded use index and the holder's root (finding 12);
the anchor over a reserve chunk (finding 14); the `Revoke` that finds its
release pending (finding 17); the code-11 trace of a report item (finding 19);
`grant_signal`'s `valid` guard (finding 23); the `Report`'s 28-item bound
(finding 16). None of these is a wrong line of code; each is a rule that would
go wrong in a later pass with nothing to say so.

---

## Findings

| # | Where | Finding | Reproduction | Output | Severity | Correction |
|---|---|---|---|---|---|---|
| 1 | `model/src/grants.rs:809` against `:584` | `revoke_answered` frees a grant with `free_grant`, so the anchor stays in the granting node's kernel space; the next `node_send` reuses the index and writes a second anchor into the slot | `review22::a_grant_index_reused_after_a_revocation_overwrites_the_anchor_of_the_old_one` | `left: Err("node 0: 6: slot of a capability")` / `right: Ok(())` | high | call `free_with_anchor` where `revoke_answered` frees the entry; the test above |
| 2 | `model/src/rings.rs:624` | the step adds the length of the message it just served, so one interrupt can serve past sixteen entries | `review22::one_interrupt_serves_sixteen_entries_and_not_more` | `left: 20` / `right: 16` | low | stop before a message that would cross the step's last entry, leaving it for the next interrupt; the test above |
| 3 | `model/src/boot.rs:689-698` | `values_in_range` holds only usable ranges to MAXPHYADDR, so a kept range above it is accepted | `review22::a_kept_range_past_maxphyaddr_or_a_crash_area_over_a_kept_range` | `Ok(Ok(()))` | medium | filter every range, usable and kept, in `width`; a machine with `phys_bits = 40` and a kept range at 2^45 must be refused |
| 4 | `model/src/boot.rs:712-716` | the crash area is compared only with the previous crash area, never with `kept` or `feedback` | `review22::a_crash_area_over_a_kept_range_is_refused` | `Ok(Ok(()))` | low | compare both crash areas with `kept_ranges` minus themselves; the test above |
| 5 | `model/src/rings.rs:70-88`, `:92` | the `Report` has no ITS item: kinds 3 and 4 of the key scheme and their words are modelled nowhere, so the 86-word bound cannot be reached | reading; `Item::key` shifts only 0, 1, 2 | not run (no code to run) | medium | add `Item::ItsDevice` and `Item::ItsEvent` with their keys and three words each, and a rebuild test that issues one of each |
| 6 | `model/src/scenarios/pass22.rs:704-710` | `a_debug_area_that_agrees_is_continued` does not test continuation: unmutated it reads 2 then 3, cleared it reads 3 then 3, and both satisfy `after >= next` | p22-25 mutation, `continues()` → `false`, whole suite | `p22-25-continued GREEN all` | medium | assert the entries the ring held before the restart are still there and the area names the last one |
| 7 | `model/src/scenarios/pass22.rs:689-692` | the 2^63 clause of a debug area is masked: the area is cleared for disagreeing with its ring, not for the bound | p22-23 mutation, `(1..1<<63)` → `(1..u64::MAX)` | `p22-23-next-seq-2-63 GREEN all` | low | make the ring agree with the value under test so the bound is the only reason left |
| 8 | `model/src/scenarios/pass22.rs:1020` | `an_ioports_word_that_names_no_range_admits_no_port` tests `range_of` and not a call, so `ok_or(Error::Busy)` may become `IoPortRange::ALL` unseen | p22-35 mutation | `p22-35-no-range GREEN all` | low | claim with such a badge and assert `busy` from `ioport_in` |
| 9 | `model/src/scenarios/pass22.rs:1392` | `an_iospace_map_where_units_cache_absent_entries_waits_for_their_invalidation` does not test the `again` when the unit-request table is full; the mutation records the mapping first | p22-47 mutation, the `all(Option::is_some)` guard → `false` | `p22-47-caching-map GREEN all` | low | fill the 64 unit requests, assert `again` and no record, then run them |
| 10 | `model/src/scenarios/pass22.rs:2044` | `the_start_up_space_counts_the_copied_frames_at_their_place` never has two copied sizes in a row, so the watermark's alignment is untested | p22-68 mutation, `next_multiple_of(bytes)` dropped | `p22-68-copied-watermark GREEN all` | low | one 4 KB segment then a 2 MB one, and assert the second copies one large page |
| 11 | `model/src/scenarios/pass22.rs:1814` | `a_start_whose_page_does_not_fit_parks_its_core_again` stays green when the page rule is removed; another test catches the mutation | p22-59 mutation, whole suite | `RED … the_start_up_refuses_the_values_of_the_machine_out_of_range` | low | assert the refusal code and trace in the test named for the clause |
| 12 | `model/src/memory.rs:571` | the tie between the grant's recorded use index and the holder's root (`use_index != Some(remote.use_entry) → Gone`) has no test | own-15 mutation, the check → `false` | `own-15-use-index-tying GREEN all` | medium | a `Remote` whose `use_entry` differs from the grant's must be `gone` |
| 13 | `model/src/grants.rs:923-925` | the serial's 30-bit wrap is untested: `serial + 1` without the mask leaves the suite green | own-01 mutation | `own-01-serial-wraps GREEN all` | low | drive the serial to the mask and assert it wraps to 0 |
| 14 | `model/src/grants.rs:367` | a grant over a reserve chunk this generation does not hold is accepted, unseen | own-02 mutation, `holds_reserve(me, j)` → `false` | `own-02-anchor-reserve GREEN all` | medium | a reserve owned by another generation must give `busy` |
| 15 | `model/src/grants.rs:406` | `holder_count`'s generation filter is untested | own-03 mutation, `u.generation == generation` → `true` | `own-03-count-generation GREEN all` | low | a use entry of an older generation must not count for the new grant |
| 16 | `model/src/roles.rs:786` | the `Report`'s 28-item bound is untested | own-04 mutation, `items.len() <= REPORT_ITEMS` dropped | `own-04-report-at-most GREEN all` | low | a `Report` of 29 items must be refused and traced |
| 17 | `model/src/grants.rs:774` | a `Revoke` that finds its release pending is untested: the disjunct dropped, the model removes the root twice | own-05 mutation | `own-05-release-crossing GREEN all` | medium | release first, then revoke; expect `RevokeStep { removed: true }` and the entry freed |
| 18 | `model/src/roles.rs:781` | the inclusive first key of a report (`key >= asked`) is untested | own-08 mutation, `>=` → `>` | `own-08-report-rises GREEN all` | low | ask from a key that exists and assert it is reported first |
| 19 | `model/src/roles.rs:648` | the code-11 trace of a report item that fails its check has no test | own-09 mutation, the trace → `if false` | `own-09-report-item-traced GREEN all` | medium | a failing item must leave trace code 11 with the reporter and the device |
| 20 | `model/src/sched.rs:380` | `last_event`'s accumulation over two events of one kind is untested | own-10 mutation, `n + entered` → `entered` | `own-10-last-event-adds GREEN all` | low | two events of one kind in one window and assert the sum |
| 21 | `model/src/nodes.rs:1744` | the resume loop's `*units == 0` bound is untested | own-11 mutation, the bound → `false` | `own-11-resume-bounded GREEN all` | low | resume with every unit done and assert one pass |
| 22 | `model/src/check/machine.rs:157` | the device leaf count's `running_node` clause is untested | own-14 mutation, the clause dropped | `own-14-device-running-node GREEN all` | low | a check whose device owner names a stopped node |
| 23 | `model/src/grants.rs:638` | `grant_signal`'s `valid(&remote)` guard is untested: a stale remote capability still writes the message | own-16 mutation, the guard dropped | `own-16-signal-valid GREEN all` | medium | let the generation pass and assert no message is written |
| 24 | `model/src/memory.rs:1165` | a detach that finds the attach word *pinned* keeps the iospace wrongly, and no test or invariant distinguishes it | own-17 mutation, `== Attached` → `.is_some()` | `own-17-detach-attached GREEN all` | low | reachable only from a faulty kernel's word; drop the clause or add the invariant |
| 25 | `model/src/caps.rs:1162` | the chapters an iospace's destruction loses (`1 + space.tables`) are compared in no test | own-19 mutation, `+= 1 + space.tables` → `+= 1` | `own-19-lost-count GREEN all` | low | destroy an iospace of two tables and assert the untyped's `lost` |
