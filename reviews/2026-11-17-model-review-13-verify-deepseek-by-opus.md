# Verification of model review 13 (DeepSeek), by Opus

Reviewed: `reviews/2026-11-17-model-review-13-deepseek.md` (25 findings: 1
high, 8 medium, 16 low; 94 mutations, 23 said to survive) and its tests
`reviews/2026-11-17-model-review-13-tests/review22.rs` (read, not reused).

Setup. Contract: `architecture/kernel-interface.md` at `a0e5848`, saved as
`/private/tmp/ki-a0e5848-verify-model.md`. Model: pull request 3 of
`dodos-kernel` at `acecf8f`, copied from `/private/tmp/dodos-pr3-p22` to
`/private/tmp/dodos-pr3-verify13`. I read `AGENTS.md`, `dodos-rust` and
`rust-1-100` first. Every command ran in that copy, in the foreground,
through `nix develop -c`. My own tests are in
`model/src/scenarios/verify13.rs` (new file). The corrections and the tests
are one patch: `reviews/2026-11-17-model-review-13-verify.patch`.

Baseline before any change: `cargo test -p dodos-model --lib`, 591 passed;
`cargo test --workspace`, all green.

Line numbers below are those of `acecf8f` unless I say otherwise.

---

## 1. The high finding and the medium ones

### Finding 1 (high): a revocation frees the grant entry, its anchor stays, and the next `node_send` writes a second anchor into the slot. Confirmed. The model's fault, with a root cause wider than the review says.

What the code does. `revoke_answered` (`model/src/grants.rs:809`) frees the
entry with `free_grant` when the `RevokeStep` reports the root removed and
the holder's count is 0. The anchor stays in the kernel space; the
removing thread is woken with `again`, and only its next call removes the
anchor. `node_send` picks free indexes with
`!self.table.grants[me].contains_key(g)` (`grants.rs:238-241`): it looks at
the grant entry only, never at the anchor slot. `make_grant` then derives
the new anchor into `anchor_index(grant)`, a slot that still holds the old
one.

What the contract says (Grants, release by the holder): "the anchor of a
freed entry is removed if it has no descendant in X's list, and otherwise
stays, held by nobody, until an ancestor's removal reaches it (design
choice: ... the cost is an entry that stays used)"; and for the crossing,
"the removal step on X finds the entry freed at its next call and removes
the anchor". The anchor is part of the entry ("An entry is 128 bytes: the
anchor, a slot of 64 bytes ..."), and an entry whose anchor stays "stays
used". So the contract already keeps such an index out of reuse; the model
does not. Not the contract's fault.

Reproduction (calls only: a grant, a map by the holder, `cap_revoke` by the
granter, time, then a `node_send` from a second thread of the granter):
`verify13::a_grant_whose_anchor_stays_is_not_reused_by_the_next_node_send`.
Without the correction:

    assertion `left == right` failed: Ok(Waits)
      left: Err("node 0: 6: slot of a capability")
     right: Ok(())

The review's correction is wrong in place. It asks `revoke_answered` to call
`free_with_anchor`. That removes a capability under a removal that is in
progress (the woken thread's next call walks the same list), and it leaves
the other paths that free an entry and keep its anchor: `release_received`
on a *revoking* entry (`grants.rs:890`), `free_with_anchor` itself when the
anchor has a descendant (`grants.rs:130-138`), and `unpin`
(`nodes.rs:1548-1556`). All four can leave an anchor in a free index.

Correction (applied): `node_send` takes an index as free only if its entry
is absent and its anchor slot is empty
(`!self.table.grants[me].contains_key(&g) && self.anchor(g).is_none()`), one
guard where every path meets. The test passes with it; the whole suite
stays green.

### Finding 2 (low in the review): one interrupt serves past sixteen entries. Confirmed. The model's fault. Low.

`consume` (`model/src/rings.rs:583-645`) checks `served < step` before a
message and adds the message's length after it, so a message that straddles
the sixteenth entry is served whole. The contract (Processing): "at most 16
entries per ring per interrupt ... if entries remain, the core sends itself
the interrupt again". A message is at most 11 entries, so stopping before a
message that would cross the bound always leaves the next interrupt
something it can serve: the contract's rule can be met, and the model does
not meet it.

Reproduction (four 5-entry `Send`s written by node 1 into its own ring to
node 0, then one interrupt):
`verify13::one_interrupt_never_serves_more_than_sixteen_entries`. Without
the correction: `20 entries in one interrupt`.

Severity: low. The work of one interrupt is still bounded (at most 26
entries instead of 16), nothing is lost, and the next interrupt serves the
rest.

Correction (applied): in `consume`, before consuming a message, `if served
> 0 && served + length > step { store the consumer index; break }`. The
first message of an interrupt is always served, so the kernel rings (step
1) are unchanged. The pass's own test
`one_interrupt_serves_sixteen_entries_of_a_user_ring_not_sixteen_messages`
(2-entry messages) still passes.

### Finding 3 (medium in the review): a kept range above MAXPHYADDR is accepted. Confirmed. The model's fault. Low.

`values_in_range` (`model/src/boot.rs:688-697`) holds only `Usable` ranges
of the memory map to `1 << phys_bits`. The contract's list (Start-up state):
"the processor's physical address width (MAXPHYADDR) is ... below the end
of a usable or kept range". `Machine::kept` is never compared.

Reproduction (a value of the machine): the example machine plus a kept range
at `1 << phys_bits`, `verify13::a_kept_range_past_maxphyaddr_is_refused`.
Without the correction `System::boot` returns `Ok` (the test prints `None`
for the refusal and fails).

Severity: I put it at low, not medium. In the model a kept range is only
subtracted from ordinary memory, so a range past the width changes no
state; the fault is a missing refusal the contract lists, with no
observable consequence in the model. In a kernel it would be a range it
cannot address.

Correction (applied): `width` takes the usable ranges and `self.kept`
together, each end checked with `checked_add` against `1 << phys_bits`.

### Finding 4 (low): a crash area over a kept range is accepted. Confirmed, and wider than the review says. The model's fault. Low, but see N1.

`values_in_range` (`boot.rs:711-716`) checks each crash area's alignment and
that the second base differs from the first. The contract: "a crash area's
base is not on a chunk boundary, or its range overlaps another kept range".
The kept ranges, the feedback tables and the other crash area's range are
never compared with the crash area's range.

Reproduction: the example machine plus a kept range of one page inside the
crash area, `verify13::a_crash_area_over_a_kept_range_is_refused`; boot
returns `Ok` without the correction.

The review missed that the check between the two crash areas is wrong too:
see N1 in section 6.

Correction (applied, with N1): a `Machine::crash_len()` (the page plus a debug
area per core, in whole chunks, the formula `layout` already used, now
written once); each crash area's range must be clear of `self.kept`, of the
feedback tables, and the first of the second's range.

### Finding 5 (medium): the model has no ITS `Report` item. Confirmed as a fact; refuted as a fault of the model. No correction to the model.

True: `Item` (`model/src/rings.rs:70-75`) has three kinds, and `Item::key`
(`rings.rs:82-88`) shifts 0, 1 and 2 into bits 61-63. The contract's
`Report` row has five kinds: "0 a device, 1 a remapping handle, 2 a line, 3
an ITS device, 4 an ITS event".

What the review did not read: `model/README.md`, "What it does not model",
lists "The line controllers of ARM64 and RISC-V (the GIC distributor, an
APLIC domain) and the ITS: a line is an IOAPIC's input on every
architecture". The model has no ITS, so no node can claim an ITS device or
event, and there is nothing a `Report` could carry under kinds 3 and 4. The
absence is a declared limit, not a rule the model gets wrong; giving `Item`
two kinds that nothing can produce would be dead code.

What stands, at low: the contract's list "Changes for `abi/` and the model"
asks, since D-141, for "the kind of a key in bits 61-63, with the items of
an ITS device and an ITS event" in `abi/`. `abi/` has none of the five key
kinds (only `REPORT_END`), and its comment on `NodeMessage::Report`
(`abi/src/ring.rs:65-66`) does not even name the count word that D-141
added first. That is an `abi/` gap, which the oracle and the kernel will
need. Proposed correction, not applied (a change to `abi/` is "ask first"
in `AGENTS.md`, and nothing in the model would use the two new kinds): five
constants for the key kinds in `abi/src/ring.rs`, `Item::key` written with
the first three, and the comment brought to the contract's words.

### Finding 6 (medium): `a_debug_area_that_agrees_is_continued` does not test continuation. Confirmed for the named test; refuted as a hole. Low.

I re-applied p22-25 (`continues()` made false by `false && holds(...)` in
`model/src/debug.rs:84`) and ran the whole suite (`cargo test --workspace`,
not only `--lib`). The named test in `pass22.rs:705-710` stays green, as the
review says. But the mutation is killed by two tests in
`model/tests/debug.rs`:

    p22-25 RED a_node_started_fresh_keeps_its_rings_and_goes_on_from_their_sequences
               the_kernel_ring_starts_with_the_text_of_the_start

The first asserts that after a fresh start the kernel ring holds the start
entries of both generations (`[1, 2]`) and the area's generation pair: a
cleared area fails it. So continuation is held by the suite. The review ran
every "whole suite" round as `cargo test -p dodos-model --lib -- --skip
review22` (its own baseline line), which leaves out every integration test
in `model/tests/`. That one method gap explains this finding, finding 11,
and makes every "GREEN all" of the review a claim about the library tests
only. I re-ran all 23 survivors against the workspace and both page
geometries (section 3).

What stands: the named test cannot tell a continued area from a cleared
one. That is a weak test, not a missing guarantee. Low. Not corrected (the
rule is held twice already).

### Finding 12 (medium): the tie between the grant's recorded use index and the holder's root has no test. Confirmed. A real hole. Medium.

own-15 (`memory.rs:571`, the `use_index != Some(remote.use_entry)` check made
`if false`) survives the workspace suite and both geometries.

The state is reachable by a faulty holder writing its own ring: node 1's
kernel rewrites the use index in its `SendAnswer` (in ring 1 → 0) before
node 0 reads it. Node 0 records 4095; node 1's gate wrote its use entry at
another index. Then node 1 maps the frame. The contract (Grants, the count
says what the holder translates, D-141): "only an index the granting node
recorded before the first leaf ties the count to the leaves". The test
`verify13::a_map_under_a_grant_that_recorded_another_use_index_is_gone`
asserts the recorded index is 4095 and that the map is `gone`. Under
own-15 it fails (the map is done, and its leaf is counted in an entry node 0
never reads). This is the one check that makes D-141's release rule hold
against a holder's lying answer, so medium is right.

### Finding 14 (medium): a grant over a reserve chunk this generation does not hold is accepted, unseen. Confirmed in part: the hole is the other direction. Low.

The review's mutation own-02 replaces `holds_reserve(me, j)`
(`grants.rs:371`) with `false`. That does not let a node grant a reserve it
does not hold: it refuses every reserve frame, legitimate ones included.
The review describes the opposite case. I ran both directions:

- `false` (as the review applied it): survives. No test grants a frame of a
  reserve chunk the node holds. Real hole.
  `verify13::a_frame_of_a_reserve_chunk_the_node_holds_is_granted` (claim
  reserve role 0, take its chunk, retype a frame, `node_send` it, expect
  `waits`) is red under it.
- `true` (the case the review describes): survives too, but it is
  equivalent in every reachable state. The word must read *taken* with this
  node's current generation, and the contract (Roles) says "A reserve role
  cannot move while a word of its reserve is taken by a node that is not
  dead": a node that took a reserve chunk keeps the role while the word is
  taken, and after its death the generation no longer matches. No sequence
  of calls gives a taken word of this generation without the role.

So the guarantee the review worries about holds; what was untested is that
a legitimate reserve frame can be granted. Low.

### Finding 17 (medium): a `Revoke` that finds its release pending is untested; without the disjunct the model removes the root twice. Refuted. The mutation is equivalent.

own-05 drops `entry.release_pending ||` from `revoke_received`
(`grants.rs:774`), leaving `!self.objects.contains_key(&entry.root)`. Both
conditions pick the same branch in every checked state. A use entry has
*release pending* only after the holder removed the root remote capability
(Grants, release by the holder). Removing the root removes its object: the
check reports an object without a root capability (`lib.rs:1780-1781`, "An
object that does not exist, or has no root capability, is not: `check`
reports it"). Object identifiers come from `next_id`, which only grows
(`caps.rs:547-548`, `grants.rs:505-508`), so the root's identifier is
never reused. Hence *release pending* implies the root is absent, and the
second disjunct alone takes the same branch. There is no "second removal of
the same root". The mutation survives the workspace suite because no test
can kill it.

### Finding 19 (medium): the code-11 trace of a report item that fails its check has no test. Confirmed. A real hole. Low.

own-09 (`roles.rs:647`, the item's `refuse_trace` made `if false`) survives
everywhere. The contract (Roles, take-over after a death, D-141): "an item
that fails it being traced (code 11) and claiming nothing". The pass's test
`a_reported_device_whose_identifier_word_names_another_node_is_not_written`
asserts the item claims nothing, not the trace.
`verify13::a_reported_device_that_fails_its_check_is_traced` asserts that the
refusal count rises by one for the failing item and not for the good one;
it is red under own-09. I put it at low: the item is still refused, and
only the trace a human reads is lost.

### Finding 23 (medium): `grant_signal`'s `valid(&remote)` guard is untested; a stale remote capability still writes the message. Refuted. The mutation is equivalent.

`grant_signal` (`grants.rs:626-649`) reads the slot with `self.cap(...)`,
which ends in `full` (`lib.rs:1753-1777`): "a use of an invalid remote
capability is `gone`, judged with the slot", using the same `valid`. A stale
remote capability never reaches line 642. Nothing changes between the slot
check and the guard inside one call, so the guard is always true there and
own-16 changes nothing. A stale capability gets `gone` and writes no
message, with or without the guard.

---

## 2. The low findings

**Finding 7 (p22-23).** Confirmed: a real hole. Low. The pass's test
`a_debug_area_whose_next_sequence_is_2_to_the_63_is_cleared` is decided by
the ring's disagreement, not by the bound. A faulty dead generation can
write an area whose ring agrees with a next sequence of 2^63.
`verify13::a_debug_area_at_2_to_the_63_that_agrees_with_its_ring_is_cleared`
writes the matching entry and is red under p22-23.

**Finding 8 (p22-35).** Refuted: equivalent. An `ioports` word that names
no range cannot be built by calls. The start-up capability carries
`IoPortRange::ALL` (`boot.rs:1288-1291`); `cap_derive` refuses a badge on
anything but an endpoint or a notify and keeps the source's badge
(`caps.rs:196-209`); `ioports_issue` builds its range with
`IoPortRange::new(..).ok_or(Error::Invalid)` (`debug.rs:518`). The word sits
in the node's own capability space, which only its own kernel writes. The
`busy` branch is defensive code no call reaches.

**Finding 9 (p22-47).** Confirmed: a real hole. Low. Filled by calls only:
64 threads (minimum budget, so admission takes them), each with an iospace
map that must ask the unit in caching mode, fill node 0's unit request
table. The 65th map must be `again` with nothing recorded.
`verify13::an_iospace_map_that_must_ask_a_full_unit_request_table_is_again_with_nothing_changed`
is red under p22-47 (the mapping is recorded before the `again`).

**Finding 10 (p22-68).** Refuted: equivalent for every machine I could
judge. `module_frames` (`abi/src/machine.rs:1317-1385`) picks a size only
where the physical address `start_at + watermark` is aligned on it, and
`start_at` is the base of the first block of a floor, which is
chunk-aligned. So for every frame no larger than a chunk, the relative
watermark is already aligned and `next_multiple_of(bytes)` is a no-op. The
review's example (a 4 KB copy before a 2 MB one) is wrong: the 2 MB frame
is only chosen at an aligned address, where both forms agree. They could
differ only for a frame larger than a chunk (a 1 GB page on 4 KB pages,
from a writable segment of 1 GB or more), and there the relative rounding
is itself questionable. Not run.

**Finding 11 (p22-59).** Confirmed for the named test; the rule is held.
Low. Under p22-59 all of `pass22` stays green (I ran `pass22::` alone). The
mutation is killed only by `kernel_refuses_a_start_up_page_of_more_than_63_pages`
in `model/tests/boot.rs`, not by the `pass22` test the review names. The
review's attribution is not reproduced. Not corrected.

**Finding 13 (own-01).** Confirmed: a real hole. Low. The serial is 30 bits
(Grants, the grant table). An unmasked `serial + 1` would put 2^30 into a
`Revoke`, `Release` or `Signal`, where bits 12-41 hold it, and spill into
the next field. `verify13::a_grant_freed_at_the_largest_serial_comes_back_with_serial_0`
sets node 0's serial word to 2^30 − 1 (the state 2^30 − 1 reuses leave),
lets a grant be refused and freed, and expects 0. Red under own-01.

**Finding 15 (own-03).** Refuted: equivalent in reachable states. Serials
are never reset across generations ("a fresh start never resets it", the
freeing of R6 included). So a use entry naming this node, this grant and
this serial always names this node's current generation, and the
generation filter in `holder_count` never decides. It stays right as the
contract's wording. Argued by reading, not run.

**Finding 16 (own-04).** Confirmed: a real hole. Low. The model's one check
on every message (`rings.rs:381-445`) does not compare the body with the
header's length, so a faulty node can write a `Report` of 29 items (the
count word above 28). `verify13::a_report_of_29_items_is_refused_and_traced`
rewrites node 0's `Report` in its own ring during a rebuild and expects a
code-11 refusal naming `Report` at the rebuilding node. Red under own-04.

**Finding 18 (own-08).** Confirmed: a real hole, and more than a corner. A
`Report`'s next key is "the key of the next item", so the next ask's first
item has exactly the key asked. With `key > asked` every report that spans
two messages would be refused. `verify13::a_report_asked_from_a_key_takes_the_item_of_that_key`
makes node 0's first `Report` carry no item and name its first item as the
next key; the second `Report` then begins with that key. With the correct
code there are no `Report` refusals (as many as a plain rebuild, which is
none); under own-08 there is one. Low. A note for the contract: "its item
keys rise strictly from the key asked" can be read as "the first above the
key asked", which is the mutant. A wording such as "from the key asked
inclusive, then strictly" would remove the doubt.

**Finding 20 (own-10).** Refuted as a hole of the model: equivalent for every
state a correct model reaches. `last_event` only feeds invariant 62
(`check/sched.rs:238-244`). Dropping the sum makes that invariant count less,
which a test can see only on a model that already breaks the bound. It is
a weakening of the checker's own sensitivity; not corrected.

**Finding 21 (own-11).** Confirmed: a real hole. Low. Without the bound,
`*units -= 1` underflows when a resume has more waiting entries than a
step's units. `verify13::a_resume_with_more_waiting_entries_than_a_step_takes_them_in_several_steps`
leaves 60 entries in node 0's user ring while it is sealed (written by
node 1 in its own ring), resumes it, and expects it live with every entry
consumed. Red under own-11.

**Finding 22 (own-14).** Confirmed: a real hole. Low. The checker sums only
the leaves of running nodes (`check/machine.rs:120`), so a killed owner whose
kernel still exists counts nothing while the device entry's count stays
frozen until R6. `verify13::a_device_count_frozen_by_a_killed_owner_is_judged_at_least`
builds the pass's frozen device leaf, kills node 0 from node 2 and runs
30 ms under the check every 100 µs. Red under own-14 (the stricter check
fails a correct state).

**Finding 24 (own-17).** Refuted: equivalent in reachable states, argued by
reading. An attach is recorded only when the word reads *attached* with the
root (`memory.rs:1016-1024`). At every call of `detach_local`
(`memory.rs:950`, `:1096`), the word is either still *attached* (a failed
unit, or a refused detach) or was just swapped to 0 from *detached*, so
*pinned* or a stale *detached* never reaches line 1165. Not run.

**Finding 25 (own-19).** Confirmed: a real hole. Low.
`verify13::a_pinned_iospace_loses_its_root_and_its_tables` maps a frame into
an attached iospace (tables from the same untyped), breaks the unit,
destroys the iospace and expects the untyped's `lost` to grow by
`1 + tables`. Red under own-19.

---

## 3. The surviving mutations, run again

Method: `/private/tmp/claude-501/-Users-btw-Documents-repos/3693a70e-3a9c-452e-9f09-64c376c9a67c/scratchpad/mut.py` (with `mutations.json` beside it). It asserts that
the replaced text occurs exactly once, writes the mutant, runs `cargo test
--workspace --no-fail-fast -- --skip verify13` (so my own tests do not
count), runs the two page geometries of `./verify` (16 KB and 32 KB) only
when that stays green, then writes back the saved file. I did not use `git
checkout -- .` between experiments, because my corrections were already in
the copy and it would have erased them. Restoring the saved file does the
same job, and `git status` showed only my changes after every batch. None
of the mutated lines is one my corrections touch.

| Mutation | Whole suite (workspace + geometries) | Verdict | Killed now by |
|---|---|---|---|
| p22-23 `(1..1<<63)` → `(1..u64::MAX)` | survives | real hole | `verify13::a_debug_area_at_2_to_the_63_that_agrees_with_its_ring_is_cleared` |
| p22-25 `continues()` → false | **killed** by `model/tests/debug.rs` (two tests) | the rule is held; the named test is weak | — |
| p22-35 no range → `IoPortRange::ALL` | survives | equivalent (no call builds such a word) | — |
| p22-39 `size_of::<StartProcess>()` → 40 | survives | equivalent (40 bytes; `abi/src/tests.rs:1060` pins it) | — |
| p22-47 full-table guard → false | survives | real hole | `verify13::an_iospace_map_that_must_ask_a_full_unit_request_table_is_again_with_nothing_changed` |
| p22-59 start page refusal → false | **killed** by `model/tests/boot.rs::kernel_refuses_a_start_up_page_of_more_than_63_pages` | the rule is held | — |
| p22-68 watermark without `next_multiple_of` | survives | equivalent for frames up to a chunk; above, not run | — |
| own-01 serial unmasked | survives | real hole | `verify13::a_grant_freed_at_the_largest_serial_comes_back_with_serial_0` |
| own-02 `holds_reserve` → false | survives | real hole (a legitimate reserve grant refused) | `verify13::a_frame_of_a_reserve_chunk_the_node_holds_is_granted` |
| own-02b `holds_reserve` → true (mine) | survives | equivalent (the role cannot move while taken) | — |
| own-03 generation filter → true | survives | equivalent (serials never repeat across generations) | — |
| own-04 28-item bound dropped | survives | real hole | `verify13::a_report_of_29_items_is_refused_and_traced` |
| own-05 `release_pending ||` dropped | survives | equivalent | — |
| own-07 `first()` → `last()` | survives | equivalent (the list never holds two units), as the review says | — |
| own-08 `>=` → `>` | survives | real hole | `verify13::a_report_asked_from_a_key_takes_the_item_of_that_key` |
| own-09 item trace → `if false` | survives | real hole | `verify13::a_reported_device_that_fails_its_check_is_traced` |
| own-10 `n + entered` → `entered` (`sched.rs:380`; also `:394`, mine) | survives | equivalent for a correct model (the checker's own sensitivity) | — |
| own-11 resume bound → `if false` | survives | real hole | `verify13::a_resume_with_more_waiting_entries_than_a_step_takes_them_in_several_steps` |
| own-14 `running_node` dropped | survives | real hole | `verify13::a_device_count_frozen_by_a_killed_owner_is_judged_at_least` |
| own-15 use-index tie → `if false` | survives | real hole | `verify13::a_map_under_a_grant_that_recorded_another_use_index_is_gone` |
| own-16 `valid` guard dropped | survives | equivalent (`full` already says `gone`) | — |
| own-17 `== Attached` → `.is_some()` | survives | equivalent by reading | — |
| own-18 `next == REPORT_END ||` dropped | survives | equivalent, as the review says (`REPORT_END` is above every key) | — |
| own-19 `1 + tables` → `1` | survives | real hole | `verify13::a_pinned_iospace_loses_its_root_and_its_tables` |

Each "killed now by" test was run under its mutation and is red, and green
without it (`mut.py <id> only=<filter>`). Of the 23 survivors the review
counted, 2 are killed by the existing suite, 11 are real holes (each now
held by a test), and 10 are equivalent (own-02b is my extra mutation).

`a_debug_area_that_agrees_is_continued` with `continues()` forced to false,
as asked: the test itself stays green; the suite kills the mutant through
`model/tests/debug.rs`.

---

## 4. The Kani proof `a_header_reads_back_its_credit`

Kani is not in Nix; CI runs it through `model-checking/kani-github-action`
with `kani-version: "0.68.0"` and `args: "-p dodos-abi"`
(`.github/workflows/verify.yml`). Kani 0.68.0 is installed on this machine
outside Nix (`~/.cargo/bin/cargo-kani`), and it runs there. The review's
`gcc not found` came from running it inside `nix develop`.

    cargo-kani kani -p dodos-abi --harness a_header_reads_back_its_credit
    SUMMARY: ** 0 of 59 failed
    VERIFICATION:- SUCCESSFUL

    cargo-kani kani -p dodos-abi        (as CI)
    Complete - 41 successfully verified harnesses, 0 failures, 41 total.

(Run on aarch64 macOS; CI runs x86-64 Linux. The functions are integer
arithmetic only.)

The pass had to change the assumption. With the old one (`index <
CREDIT_NONE`) restored against the new `credit()`, the proof fails: `1 of 59
failed`, "assertion failed: header.credit() == Some((index, serial))",
because indexes 24 to 30 now read as no credit.

Is the new assumption the contract's? Yes. "the credit's index numbered
(0-15 requests, 16-23 sends, 31 none)" (Changes for `abi/`, D-141), and the
`credit()` comment says "no other value is a credit". The assumption is
exactly 0 to 23.

What it no longer covers: the round trip of indexes 24 to 30 through
`RingHeader::new`, which still stores any 5-bit index; `new(.., Some((24,
s)))` builds a header that reads as no credit. That is now the intended
meaning, and the pass's new harness `a_credit_is_one_of_the_credits` proves
that `credit()` never returns an index of 24 or more. No caller in the model
passes such an index. The narrowing is honest. The review's suggestion of a
`debug_assert` in `new` is reasonable but optional; not applied.

---

## 5. The corrections (patch `reviews/2026-11-17-model-review-13-verify.patch`)

| Where | Change | Test that fails without it |
|---|---|---|
| `model/src/grants.rs`, `node_send` | an index is free only if its entry is absent **and** its anchor slot is empty | `a_grant_whose_anchor_stays_is_not_reused_by_the_next_node_send` |
| `model/src/rings.rs`, `consume` | stop before a message that would carry the step past `step` entries (the first message always served) | `one_interrupt_never_serves_more_than_sixteen_entries` |
| `model/src/boot.rs`, `values_in_range` | kept ranges held to MAXPHYADDR | `a_kept_range_past_maxphyaddr_is_refused` |
| `model/src/boot.rs`, `values_in_range`, new `Machine::crash_len` | each crash area's range clear of the kept ranges, the feedback tables and the other crash area; `layout` uses the same `crash_len` | `a_crash_area_over_a_kept_range_is_refused` (both areas), `two_crash_areas_closer_than_their_length_are_refused` |
| `model/src/scenarios/mod.rs`, `machine()` | from 31 cores (4 KB pages) the test machines place the two crash areas apart by their length; `pass18::the_fence_record_keeps_the_last_stop_of_a_core_at_its_number_mod_64` (66 cores) booted with overlapping areas and is refused without this | that `pass18` test |
| `model/src/scenarios/pass22.rs` | five helpers made `pub(super)` for reuse; no test changed | — |
| `model/src/scenarios/verify13.rs` (new) | 16 tests: the 5 above, N1, and the 11 real holes of section 3 | each red under its mutation or without its correction |

I checked each correction by removing it with the tests in place: each turns
its own test red (`fix-1`, `fix-2`, `fix-3`, `fix-4`, `fix-4b`, `fix-N1`).

Final run, everything applied:

    nix develop -c ./verify
    rc=0 (format, clippy with warnings denied, cargo test --workspace,
    and both page geometries); the library suite 607 passed in each of
    the three runs.

The patch applies cleanly to `acecf8f` (`git apply --check` on a fresh
checkout).

---

## 6. What the review missed

**N1. Two crash areas closer than one area's length are accepted, and the
suite already boots such a machine. Confirmed. The model's fault. Low to
medium.** `values_in_range` checks only `p != self.crash.0`. A crash area is
`(4096 + cores × DEBUG_AREA_BYTES)` rounded up to a chunk (`boot.rs:821`):
two chunks from 31 cores on 4 KB pages. Two chunk-aligned bases one chunk
apart then overlap, which the contract refuses ("its range overlaps another
kept range"). The current generation's debug areas would then overwrite the
previous crash area the next start must read. `Machine::example()` places
the two areas one chunk apart, and the suite's 66-core machine
(`pass18::the_fence_record_keeps_the_last_stop_of_a_core_at_its_number_mod_64`)
boots with them overlapping; with the correction it is refused, which is
how I found it. Test: `verify13::two_crash_areas_closer_than_their_length_are_refused`
(on 4 KB pages; on 16 KB and 32 KB pages 32 debug areas fit in one chunk,
so two distinct chunk bases cannot overlap and the test returns early).
Correction: in the patch, with finding 4.

**N2. The review's method left out the integration tests.** Every "whole
suite" round of the review was `--lib`. Two of its survivors (p22-25 and
p22-59) are killed by `model/tests/`, and its finding 6 (medium) rests on
that gap. Its numbers of survivors are numbers for the library tests only.

**N3. The review's `review22.rs` does not match its own output.** Its
finding 1 quotes a panic at `review22.rs:133:21` with `left: Err("node 0: 6:
slot of a capability")`; the file it handed over asserts something else at
the end of that test (`!caps.contains_key(&anchor) || outcome == DONE`).
The fault is real (I reproduced it on my own), but the tests given are not
the ones that produced the quoted output.

---

## Summary table

| Finding | Verdict | Severity | Correction |
|---|---|---|---|
| 1 anchor left by a revocation, index reused | Confirmed (model); root cause in `node_send`'s free-index choice, four paths | high | `node_send` takes an index only when its entry and its anchor slot are both empty |
| 2 an interrupt serves past 16 entries | Confirmed (model) | low | `consume` stops before a message that would cross the step |
| 3 kept range above MAXPHYADDR accepted | Confirmed (model) | low | `values_in_range` checks kept ranges against the width |
| 4 crash area over a kept range accepted | Confirmed (model) | low | each crash area clear of kept ranges, feedback tables and the other area |
| 5 no ITS `Report` item | Confirmed as fact, refuted as fault (README: the ITS is not modelled); `abi/` lacks the five key kinds | low | proposed, not applied: key-kind constants in `abi/src/ring.rs` |
| 6 continuation test is blind | Named test weak; rule held by `model/tests/debug.rs` | low | none needed |
| 7 2^63 bound decided by another clause | Confirmed, real hole | low | test with an agreeing ring |
| 8 `ioports` word naming no range | Refuted, equivalent | — | none |
| 9 full unit-request table on a caching map | Confirmed, real hole | low | test filling 64 requests by calls |
| 10 watermark alignment | Refuted, equivalent up to chunk-sized frames (above: not run) | — | none |
| 11 start page refusal named test | Rule held by `model/tests/boot.rs`; review's attribution not reproduced | low | none needed |
| 12 recorded use index vs holder's root | Confirmed, real hole | medium | test with the holder's answer rewritten in its own ring |
| 13 serial wrap | Confirmed, real hole | low | test at serial 2^30 − 1 |
| 14 reserve-chunk anchor | Confirmed in part: the untested case is a legitimate reserve grant; the case described is unreachable | low | test granting a frame of a held reserve |
| 15 `holder_count` generation filter | Refuted, equivalent (argued) | — | none |
| 16 28-item bound | Confirmed, real hole | low | test with a 29-item `Report` in the reporter's own ring |
| 17 `Revoke` crossing a pending release | Refuted, equivalent | — | none |
| 18 inclusive first key | Confirmed, real hole (every two-message report); contract wording ambiguous | low | test of a report continued from a key; wording note |
| 19 item code-11 trace | Confirmed, real hole | low | test of the trace count |
| 20 `last_event` sum | Refuted for the model (checker sensitivity only) | — | none |
| 21 resume loop bound | Confirmed, real hole | low | test with 60 waiting entries |
| 22 device count of a non-running owner | Confirmed, real hole | low | test killing the owner of a frozen device leaf |
| 23 `grant_signal`'s `valid` guard | Refuted, equivalent (`full` already says `gone`) | — | none |
| 24 detach with a *pinned* word | Refuted, equivalent (argued) | — | none |
| 25 `lost` of a pinned iospace | Confirmed, real hole | low | test of `lost` growing by `1 + tables` |
| N1 two crash areas closer than their length | Confirmed (model), new | low–medium | same check as finding 4; test machines spaced by `crash_len` |
| N2 review ran `--lib` only | Method fault, new | — | — |
| N3 handed-over tests do not match quoted output | Report fault, new | — | — |
