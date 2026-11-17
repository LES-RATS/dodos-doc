# Verification of report v2-B-hydrogen (lot B)

Report verified: `reports/v2-B-hydrogen.md` (10 findings).
Model: `dodos-kernel` pull request 3, head `6312868`, my copy at
`/private/tmp/dodos-pr3-ver2-B-hydrogen`. Contract:
`Docs/architecture/kernel-interface.md` and `Docs/decisions/README.md`,
branch `main`. My reproduction tests are in my copy, in
`model/src/scenarios/ver_b.rs` (registered in `scenarios/mod.rs`), named `ver_*`. The author's tests were read in
`/private/tmp/dodos-pr3-v2-B-hydrogen` and not run there.

Note on test inputs. `System::break_unit` (and the author's equivalent
`edit_table(|t| ... broken = true)`) is the model's declared test input for
"the unit of a role stops confirming" (`model/src/system.rs:517`): a hardware
event, not a write by the attacker. `System::inject` is the declared input for
"a faulty, late or forged message" from a sender (`system.rs:497`).

How I ran the tests. Each `ver_*` test asserts what the contract asks, so
against the unchanged model it fails and its message shows what the model did.
I ran them first on the unchanged model (results quoted below), then with the
corrections of this report applied in my copy, where all of them pass (section
"Corrections tried"). Command:
`nix develop /private/tmp/dodos-pr3-ver2-B-hydrogen -c cargo test --manifest-path /private/tmp/dodos-pr3-ver2-B-hydrogen/Cargo.toml -p dodos-model ver_b::`.

## Finding 1: a reserve chunk taken twice

**Lines.** `model/src/blocks.rs:161-172`, `taken_here`: for `Owner::Reserve(_)`
it returns `false`, whatever the generation in the word. Its own doc comment
says the opposite ("for a reserve's word, by a live block of this node").
`Table::may_take` then allows the word because the node holds the reserve role.

**Author's test.** `poc_blocks_1_reserve_chunk_can_be_taken_twice`: claims
reserve role 2 with `role_claim`, takes a reserve chunk twice with
`memory_take`. All calls are ones a user thread holding `memory_control` and the
role capability can make. Sound.

**My test.** `ver_f1_a_reserve_chunk_taken_by_this_generation_is_busy`: same
start, but between the two takes it makes an aspace in the first block (so a
page of the chunk is a table page), then asserts the second take is `busy`.
Result on the unchanged model:

```
left: (Ok(Done), Err("53: two blocks on a chunk"))
right: (Err(Busy), Ok(()))
```

The second take succeeds, makes a second block over the same chunk, and resets
the chunk's map count and page classes (lines 109-119) while the aspace of the
first block still uses its root page as a table.

**Contract.** `memory_take`, step 4: "`busy` if a word of the run ... is taken
by the current generation of the caller's node". For a reserve word, `role_claim`
says who took it: "a word with the reserve's code was taken by the node the role
word names, with the generation the word holds". Rule 4 of taking writes "*X*'s
generation in bits 32-63". So a reserve word *taken* with the caller's current
generation, while the caller holds the role, is taken by the current generation
of the caller's node, and the call must be `busy`.

**Verdict: real, the model's fault.** Severity: **high**. The two blocks are two
allocators over the same bytes: the second can make a frame over a page that the
first uses as a page table, and the reset page class (back to *data*) lets the
gate map that frame writable to user space. I ran that step:
`ver_f1b_a_second_block_cannot_map_the_first_blocks_page_table_writable` makes a
frame from the second block, which lands on the first block's aspace root, and
maps it writable into the start-up aspace. Unchanged model:
`frame Ok(Done) at Some(101200000), aspace root 101200000; writable map Ok(Done)`.
A user thread with `memory_control` and a reserve role then writes a live page
table by plain stores and reaches any physical memory, on an honest kernel. The gate does not stop it, since rule
4 of taking allows *taken* over *taken* for the role's holder: the gate leans on
step 4 of the kernel here. (A faulty kernel doing this hurts only its own chunk,
so the gate's promise is not at stake; the honest kernel's isolation of its own
users is.)

**Correction (model).** `Model::taken_here` in `blocks.rs`: for
`Owner::Reserve(j)` return `word.generation() == self.table.generation(self.node)
&& self.table.holds_reserve(self.node, j)` (the state is already *taken* there).
The test above fails without it and passes with it. No contract change needed;
an optional clarity sentence in step 4: "(for a reserve's word, *taken* with the
caller's generation while the caller holds the role)".

## Finding 2: `memory_split` on a device entry with frozen leaves

**Lines.** `model/src/blocks.rs:280-320`, `memory_split`: checks descendants
(`idle_block`) and the watermark, not `mapped_block`. `memory_give` (line 213)
and block destruction both check it.

**Author's test.** `poc_blocks_2_...`: takes device entry 0, makes an uncached
frame, maps it into an attached iospace, breaks the unit (`edit_table`, the same
as the declared input `System::break_unit`), unmaps (`busy`, leaf count frozen),
deletes the frame, splits. All calls are a user thread's; the unit failure is a
hardware event. Sound.

**My test.** `ver_f2_a_split_is_busy_while_the_entry_keeps_frozen_leaves`,
written with `break_unit`. It checks that `memory_give` is refused (`busy`),
then asserts the split is `busy`; when it is not, it goes on to the end of the
attack and prints it. Result on the unchanged model:

```
split Ok(Index(4)); take Ok(Done); leaves 1 -> 0; give Ok(Done); owner Node(1)
```

The split succeeds, the lower half is taken again and its leaf count reset from
1 to 0, and it is given to node 1, which now owns device memory that a device
behind the failed unit may still reach.

**Contract.** The `memory_split` row lists its states: "`busy` if the untyped
has a descendant or if a piece lives; `again` ... ; `busy` if no entry is
unused and unclaimed" (line 885). No leaf count there. But G5: "`memory_give`,
the destruction of a block and a change of page class require: map count 0 (for
a block of a device entry, the entry's leaf count 0)", and the destruction of a
block is "by any removal" (line 887); the split removes the block capability
("the capability is removed"). And the IOMMU rule for a failed unit: "the map
counts, leaf counts and use-entry counts of its leaves are never lowered, so the
chunks stay their node's and are never given, destroyed as a block or retyped
... until the machine restarts" (line 396). The split, then the take ("reset to
0 when the entry is taken", G4), lowers a frozen count.

**Verdict: real, the model's fault** (G5 and the failed-unit rule forbid it),
with a contract row that invites the mistake, since its explicit list of states
omits the check. Severity: **high** (needs a unit that fails while a device
frame is mapped; then device memory reachable by DMA moves to another node, the
very thing the frozen count exists to prevent).

**Correction.** Model: in `Model::memory_split`, after `return_watermark`, add
`if self.mapped_block(object) { return Err(Error::Busy); }`, as `memory_give`
has. The test fails without it and passes with it. Contract, `memory_split`
state (line 885), after the `again` clause: "`busy` if the entry's leaf count is
not 0 (G5: a split ends the block)". One word read, no new state, now.

## Finding 3: the pages of a pinned iospace go back to its untyped

**Lines.** `model/src/caps.rs:1142-1161` and `1193-1195`, `destroy` for
`ASpace | IoSpace`: when the root still counts a device (`pinned`), the page
classes are kept, but the untyped is released for the root and for every table
(`self.release`), so its live count can reach 0 and its watermark return.

**Author's test.** `poc_caps_1_pinned_iospace_released_to_untyped`: a child
untyped, an iospace in it, an attach answered done, the unit broken, then
`cap_delete` of the iospace until it succeeds, then `untyped_retype` of an aspace
from the same child untyped. All user calls; the unit failure is the declared
hardware input. Sound.

**My test.** `ver_f3_the_pages_of_a_pinned_iospace_are_not_reused`, with
`break_unit`. It checks the root keeps class 48 + 1 after the destruction, then
asserts that a new aspace from the same untyped does not land on the old root,
that the class stays 48 + 1 and that the node's check passes. Result on the
unchanged model:

```
retype Ok(Done); new root Some(100100000) (old 100100000); class Some(PageClass(20));
Err("88: an attach word with no identifier word or root beside it")
```

The new aspace's root is the old iospace root, whose class the retype overwrote
from 48 + 1 to 20 (page table of level 4) while the device's attach word still
reads *attached* with that root.

**Contract.** IOMMU, destruction of an iospace: "a detach answered *failed* ...
takes the device out of the header with its attach word *attached* and the count
above 0, so the destruction goes on and ends with the root and its tables
keeping their class, lost to the node until the machine restarts". Failed unit:
"the table pages of an iospace that served a device of the unit keep their class
... when the iospace is destroyed, so they are never reused before the machine
restarts". G2: "the root of an iospace is of class 48 + *n*, from its creation
(48 + 0) to its destruction, and is never on a free list", and "A page-table page
is drawn from a page of class *data*".

**Verdict: real, the model's fault.** Severity: **high**. The context entry of
the device on the failed unit may still name that root: once the page is a new
aspace's root (or, by the same path, a frame mapped writable to user space, or
part of a block given to another node), what the unit reads as the device's
tables is under someone else's control, so the device can reach any memory. Two
faults stack: the untyped is released, and the class write does not check that
the page was *data* before (G2's rule that tables are drawn from *data* pages,
which the gate should enforce as the second line).

**Correction (model).** In `Model::destroy`, `ASpace | IoSpace` arm: when
`pinned`, release nothing and return before the final `release` of
`object.from`; the pages stay live pieces of the untyped. The model needs one
field for its check to stay true: `Untyped::lost: u32`, raised by
`1 + space.tables` there, and check 19 becomes `untyped.live == live + lost`. I
applied exactly this; the test passes and the full suite stays green (below).
Second line, also worth adding: `Table::set_class` to a table class refuses a
page whose class is not *data* (G2). The contract needs no sentence: it already
says "lost to the node until the machine restarts". It is silent on what that
means for the untyped, though; a clause in the same sentence closes the
reading: "...lost to the node until the machine restarts: they stay counted as
live pieces of their untyped, whose watermark therefore never returns over them"
(no new state in the kernel: the count already exists).

## Finding 4: a failed explicit detach, then an unmap without invalidation

**Lines.** `model/src/memory.rs:1063-1068` (`detach_answered` takes the device
out of the header at an answer *failed*), `1116-1128` (`detach_local`), and the
unmap paths `memory.rs:321-325` and `677-689`, which invalidate on the unit only
if the iospace's header names a device.

**Author's test.** `poc_memory_1_...`: attach, map a frame into the iospace,
detach with iospace 0, the unit breaks while the detach is in flight, the answer
is *failed*, then `iospace_unmap` succeeds at once and lowers the map count. All
user calls plus the hardware input. Sound.

**My test.** `ver_f4_after_a_failed_detach_an_unmap_lowers_the_count_with_no_invalidation`,
with `break_unit`, asserts what the model does: the role word's *failed* bit is
set, the attach word stays *attached*, the header is empty, `iospace_unmap`
returns success at once, the map count goes back to its value before the map,
and the frame can be deleted. It **passes** on the unchanged model, and also with
my corrections.

**Contract.** Every step the model takes is written. The table of the attach
word, row "detach answered *failed*", column *attached*: "stays *attached*: *n*
and the identifier word stay; the device leaves the header; `busy`". The
`iospace_unmap` row (line 349): "If the iospace serves devices, the unit's
translation cache is invalidated ... If the unit is found failed, the call
returns `busy`, the record is emptied with its counts kept". Once the device left
the header the iospace serves no device, so the unmap invalidates nothing,
finds no unit failed, and lowers the counts.

But the guarantee of the failed unit is: "every record whose invalidation the
unit did not confirm is emptied with its counts kept ... so the chunks stay
their node's and are never given, destroyed as a block or retyped", and its
reason, "the memory a device behind it may still reach is kept out of use". The
device here sits behind a unit that failed, with its word *attached* naming the
iospace's root, and the frame's leaf was in that iospace's tables; its
translation may still be in the unit's cache, and the unit was never asked to
drop it. After the unmap, the frame's memory goes back to its untyped, can be
retyped, or (for a block) given to another node, while the device may still
write it.

**Verdict: real, the contract's fault.** The guarantee broken is the failed
unit's (line 396 and the "Why" after it): memory a device behind a failed unit
may still reach is kept out of use. Severity: **medium** (needs a unit failure
exactly while a detach is in flight, and a stale translation in a unit that has
failed; the outcome is DMA into memory reused or given away). The second part of
the author's finding, a domain number freed while the device is attached, does
not lead anywhere: the domain could be reused only by an attach on the same
unit, which is `busy` once the unit is failed; with a lying holder that answers
*failed* on a healthy unit, the holder could equally answer done to an unmap
without invalidating, which the contract already accepts ("A lying holder costs
the node its pages").

**Correction (contract).** In the IOMMU table, row "detach answered *failed*",
column *attached*, and in the paragraph on the destruction, replace "the device
leaves the header" by: "the device's entry stays in the header marked *lost*:
no step asks its detach again, no report names it, and an unmap on that iospace
is judged as on a failed unit (`busy`, the record emptied with its counts
kept)". Same for a refused detach at a step of a destruction. State: one more
bit beside the *detaching* mark of an entry the header already has; no new word.
Cost: the entry keeps one of the 16 places of the header until the iospace is
destroyed, on an iospace whose unit is failed anyway. When: now, it is a rule
of the kernel. A cheaper alternative with no bit: in the `iospace_unmap` row,
"If the iospace serves devices, **or its root's count of devices is above the
number of devices in its header with no attach in flight**, ..."; it reads the
class byte already read by the gate, but it is harder to state and to test. In
the model: keep the entry in `iospaces[iospace]` with a lost mark and let
`unmap`/`begin_unmap` find the unit through it. The test above, turned to assert
`busy` and the count kept, is the regression test.

## Finding 5: a remote frame as a message page

**Lines.** `model/src/threads.rs:69-82`, `message_page`: checks the kind, one
page, write-back and the rights; never `self.remotes`. With a remote frame,
`bind_page` binds it and no leaf is counted in the use entry, so the granter's
revocation finds a count of 0 and frees the grant at once
(`grants.rs:653-666`, which follows the contract's "If the count is 0, the entry
is freed at once").

**Author's test.** `poc_threads_1_...`: node 0 grants a frame to node 1 by
`node_send`; node 1 makes a thread and `thread_configure`s it with the remote
frame as page; node 0 deletes its frame and makes an aspace over the same page.
All user calls on two honest nodes. Sound.

**My test.** `ver_f5_a_remote_frame_is_refused_as_a_message_page`: the same
grant (through a helper that does `node_send` and the receive), then asserts
`thread_configure` is `invalid`; when it is not, it plays the rest and prints
it. Result on the unchanged model:

```
configure Ok(Done); leaves Some(0); grants left 0; page still bound true; check Ok(())
```

The thread keeps as its message page a frame whose grant is gone and whose page
is now node 0's aspace root, and the whole-machine check does not see it.

**Contract.** Grants, "Using a remote frame capability": "A call that needs a
frame of the caller's own node refuses a remote one (`invalid`, judged with its
kind): the message page of `thread_configure`, which the kernel reaches through
its own mapping of memory its node holds."

**Verdict: real, the model's fault.** Severity: **critical**. Two honest nodes
and an ordinary program: node 1's kernel writes every message delivered to that
thread into node 0's page table (a thread of node 1 chooses the words; by
reading: the model does not hold the bytes of pages, so this last step is not
run, while the binding to a page that is now node 0's aspace root is), so a user
program on node 1 writes another node's translations and reaches any memory. It
breaks the cross-node rule "*X*'s memory never returns to an untyped while *Y*
still translates to it", with no faulty kernel at all. The check missing it is a
second gap: no invariant ties a bound message page to a frame of the node's own
memory.

**Correction (model).** `Model::message_page` in `threads.rs`: after the
one-page check, `if self.remotes.contains_key(&object) { return
Err(Error::Invalid); }` (the contract's "judged with its kind"). The test fails
without it and passes with it. Worth adding to the check: a thread's `page` is
never a remote frame. No contract change.

## Finding 6: a grant of depth 0 stops the receiving kernel

**Lines.** `model/src/caps.rs:380-389`, `depth`: `remote.depth - 1` underflows
when a remote capability records depth 0. Nothing on the receiving path
(`rings.rs::refused`, `grants.rs::place_remote`) bounds the depth.

**Author's test.** `poc_caps_2_...`: writes a live grant entry in node 0's
grant table with `edit_table`, injects into ring 0 → 1 a `Send` naming it with
depth 0, then node 1 derives. The grant entry stands for what a faulty node 0
writes through its own gate in its own grant table, and the `Send` for what it
writes into its own ring (`System::inject`). Both are writes the faulty kernel
can make. Sound as a model of a faulty kernel.

**My test.** `ver_f6_a_grant_of_depth_0_does_not_stop_the_receiver`, built the
same way, but it settles with `System::settle` (the harness's check after each
step flags node 0's hand-written entry, which is the faulty node's own state),
and it calls the derive under `catch_unwind`. On the unchanged model the remote
capability is placed and the derive panics:

```
panicked at model/src/caps.rs:387:33: attempt to subtract with overflow
placed true; the derive panicked
```

**Contract.** "A remote frame capability ... its kind is `frame`, and its
rights, depth and by-kind fields are those of the anchor"; the anchor is in the
granting node's grant table, written by its gate. The `Send` carries only "its
index (0-11), its serial (12-41) and its rights (42-49)" per grant. The receive
check ("One check on every message received") judges for a `Send` only the
stamp; nothing bounds the anchor's depth, and the granter's gate cannot check
it, since the depth of the frame capability it derives from is in the granter's
own memory. So a faulty granter can write an anchor of depth 0 or above
`TREE_DEPTH`, and the receiver's kernel computes with it. The model carries the
depth in the message rather than reading the anchor, but the hole is the same.

**Verdict: real, the contract's fault** (the model does what the contract says:
it takes the anchor's depth as given). The guarantee broken is the gate's
containment: a faulty kernel reaches its own memory and devices only, and here
it stops another node's kernel (in a kernel built with overflow checks) or,
with wrapping arithmetic, makes it misjudge the depth bound, so one of its
capability spaces holds a chain deeper than `TREE_DEPTH`, whose removal
the bounds of the contract no longer cover. The text says of lying marks that
the faulty kernel damages "availability", but crashing another node is more
than the marks of what it sends. Severity: **medium**.

**Correction.** Contract, "One check on every message received", in the list
by kind, after the stamp of a `Send`: "and each grant it names is an entry of the
sender's grant table that is live, names this node with its current generation
as grantee, has that serial and is not *answered*, and whose anchor is a frame
of depth 1 to `TREE_DEPTH`". Cost: at most 4 grant entries read per `Send`, in
the living part every node already reads; no new state; now. The same sentence
closes the duplicate placement described under the forged header below. Model:
in `Model::refused`, `Body::Send` arm, refuse when a `Granted` has a depth
outside `1..=TREE_DEPTH` (I applied this; the test passes: the `Send` is refused
and node 1 keeps waiting), and add the entry checks of the sentence above.

## Finding 7: a previous crash area of sequence 2^64 − 1

**Lines.** `model/src/debug.rs:102-109`, `CrashArea::new`: `previous + 1`,
called from `boot.rs:962` with the previous area's sequence.

**Author's test.** `poc_debug_1_...`: builds a `Machine` whose
`previous_crash` has sequence `u64::MAX` and boots. `previous_crash` is the
boot input that stands for what the first stage hands over. Sound.

**My test.** `ver_f7_a_previous_crash_area_of_sequence_max_does_not_stop_the_boot`
(boot under `catch_unwind`). Unchanged model:

```
panicked at model/src/debug.rs:105:23: attempt to add with overflow
```

**Contract.** "How the record reaches the next boot", rule 3: "The previous
area is the one whose header has the right magic, version and the greater
sequence"; rule 4: "writes its header with sequence = previous sequence + 1".
The header of the crash area is written by the kernel that stops the machine
(the stop record), so a faulty kernel of the previous boot, or a bit flip in
kept memory across a warm reset, can leave any sequence there.

**Verdict: real, the contract's fault** (the model computes exactly the rule's
`+ 1`). At 2^64 − 1 the rule has no value: a kernel that wraps writes 0, and at
the next boot rule 3 picks the older area as previous (greater sequence), so the
records of this boot are overwritten unread; a kernel with overflow checks does
not boot. Guarantee broken: the record of a boot reaches the next one. Severity:
**low** (needs a corrupted header; costs one boot's records or one boot).

**Correction.** Contract, rule 3: "...the greater sequence, below 2^64 − 1; a
header of sequence 2^64 − 1 is not valid". The first stage then hands over "no
previous area" and the current area starts at 1. One comparison in the first
stage, no new state, now (it is in the contract of the first stage). Model:
`CrashArea::new` with `previous.checked_add(1).unwrap_or(1)` (applied; the test
passes); with the contract sentence, the cleaner place is where `boot.rs` takes
`previous_crash`, treating that header as none.

## Finding 8: a debug area left with a next sequence of 0

**Lines.** `model/src/debug.rs:262-276`, `enter_debug_areas`: keeps an area
whose magic and version are right, whatever its next sequences;
`DebugArea::write` then calls `abi::debug::trace_index(seq, ..)`, which is
`(seq - 1) % entries`, and does `seq + 1`.

**Author's test.** None ("Not run"). The author argued from the code.

**My test.** `ver_f8_a_debug_area_left_with_next_sequence_0_does_not_stop_the_next_node`.
Three nodes; node 2 kills node 1 (`node_stop` kill) and the machine reaches
dead; then the area of physical core 1 (node 1's core) gets `next_kernel = 0`
with magic and version unchanged. That edit stands for what node 1's faulty
generation wrote in its own core's area before it died: the contract has each
core write its own area, writable in its kernel. Then node 2 starts node 1 fresh
on core 1 (`node_start` fresh, mask `0b10`). Unchanged model:

```
panicked at abi/src/debug.rs:79:5: attempt to subtract with overflow
the start panicked or failed
```

The honest new generation dies at its first trace.

**Contract.** Debugging, "Across nodes and generations": "if the header's
magic and version are right it sets the node slot and generation and goes on
from the next sequences found there, otherwise it clears the area and starts at
1. It reads nothing else from the area". The rings index an entry by sequence
minus one (`trace_index`), and sequences start at 1, so 0 has no slot.

**Verdict: real, the contract's fault** (the model does what the sentence says:
it goes on from the sequence found). Guarantee broken: a faulty kernel reaches
only its own memory and devices; here a dead faulty generation stops the next
honest kernel on its core (with overflow checks), or with wrapping arithmetic
leaves sequences that readers cannot order. Severity: **medium-low** (the
attacker must have been the kernel of that core; the damage is availability of
the next node on that core and its trace, no memory).

**Correction.** Contract, same sentence: "if the header's magic and version are
right **and its two next sequences are neither 0 nor 2^64 − 1**, it ... goes on
from the next sequences found there, otherwise it clears the area and starts at
1". Two comparisons per core at a start, no new state, now. Model: the same test
in `enter_debug_areas` (applied; the test passes).

## Finding 9: `consumed` not reset when a context leaves the configured state

**Lines.** `model/src/sched.rs:818-827`, `sched_configure`: the branch `off`
does not set `consumed` to 0; `sched_read` hides it while not configured, and
the next configuration from not configured shows it again.

**Author's test.** `poc_sched_1_...`: a thread on core 1, time passes,
deconfigure, configure, read. User calls only. Sound (its assert checks the bug,
not the contract).

**My test.** `ver_f9_a_context_configured_again_from_not_configured_reads_consumed_from_0`:
the same steps, asserting the contract's values. Unchanged model: the read after
the deconfiguration gives 0 (masked), the read after the configuration gives

```
left: 200000
right: 0
```

**Contract.** `sched_configure`: "With budget 0: the context is not configured,
*r* = 0, *d* = 0, consumed = 0". `sched_read`: "becoming not configured sets
consumed to 0". The field: "Nanoseconds the context has run since it was last
configured from the state not configured".

**Verdict: real, the model's fault.** Severity: **low** (accounting read by
user space; no isolation at stake, though a supervisor that bills or judges
contexts by `consumed` reads the old total).

**Correction (model).** `Model::sched_configure`, branch `off`:
`sched.consumed = 0;` (applied; the test passes). No contract change.

## Finding 10: `attached_to` truncates its count to `u8`

**Lines.** `model/src/table.rs:708-716`: `.count() as u8`.

**Author's test.** None ("Not run"), with the reason that 256 attach words
naming one root need writes no call makes.

**My check.** Not run either, for this reason: no attacker can write a 17th
attach word naming one root. An attach word is written *pinned* with a root only
by the requester's gate, which raises the root's class in the same gate call
(class 48 + *n*), and page classes are written "only by the gate of the page's
owner" (G2), so a node names only its own roots; `iospace_attach` refuses at 16
("the iospace already serves 16 devices (`busy`)"), which the model applies at
`memory.rs:864` with `attached_to(root) >= IOSPACE_MAX_DEVICES`, and G2 bounds
the class: "*n* from 0 to 16". The holder's gate moves a word from *pinned* to
*attached* with the same root, adding none. The count never passes 16, far below
256.

**Verdict: refuted** (unreachable). Severity: none. A `u8::try_from(..)`
with an `expect` would state the bound, as a matter of style only.

## The header that names another node than the ring it came on

The brief asks to settle this. It is not one of the author's findings, but it
decides how far a faulty kernel reaches through the rings, so I tested it.

**What the model does.** `rings.rs::consume` knows the ring a message came on
(`from`), but calls `refused(&message)`, which judges everything on
`message.header.sender`, and `receive_message` then acts with
`let from = message.header.sender`. The ring's origin is never compared with the
header.

**What the contract says.** "One check on every message received": "Every
message carries ... its sender's node and generation ... The receiving kernel
checks ...: the sender's member word is starting, live, sealing or sealed with
that generation", and by kind, for a `Release`, "the grant entry naming the
sender as grantee with the generation it records and that serial". Nothing
compares the sender the message carries with the ring it was read from. The
rings: "A ring *X* → *Y* is mapped writable only in *X*'s kernel and read-only
in *Y*'s ... its writes are plain stores, not gate calls, since the receiver
checks every message." The sentence on trust: "The marks of a stamp are as the
sending kernel states them: kernels trust each other's stamping as they trust
each other's checks; a kernel that lies about marks is faulty, which the gate
does not contain (it damages the marks of what it sends and availability, never
another node's memory)."

**The scenario, run.** `ver_x_a_release_written_by_node_2_in_node_1s_name_is_refused`.
Three nodes. Node 0 makes a child untyped and a frame in it, and grants the
frame to node 1 by `node_send`; node 1 maps it (`aspace_map`, one leaf counted
in its use entry). Node 2, faulty, writes into its own ring 2 → 0 a `Release`
whose header names node 1 with node 1's generation, and the grant's index and
serial, all public words of the living part. On the unchanged model:

```
grant freed by a forged Release; delete Ok(Done); frame base 100010000;
retype Ok(Done), new root Some(100010000); node 1 leaves Some(1);
check Err("node 1: 58: translation under no grant")
```

Node 0 frees the grant entry (a `Release` frees it with no count read, by the
contract's rule), deletes its frame, and its next aspace's root is the very
page that node 1 still maps. With `write` in the mapping, node 1's user writes
node 0's page table. The same path works with a forged `Send` in another node's
name: the receiver places a second remote capability on a grant that node 0
made to it, with a use entry the granter never reads (the grant entry records
one use index), so node 0's revocation finds a count of 0 and frees the grant
while node 1 maps through the second capability.

**Does acting in another node's name stay inside what the gate promises? No.**
The gate promises that a faulty kernel reaches only its own memory and its own
devices. Here faulty node 2 writes nothing outside its own ring, yet node 0's
memory becomes reachable from node 1 after node 0 reuses it: node 2 can arrange
it together with a user program of its choice on node 1 (node 1's user only
needs a grant it already holds). The trust sentence does not cover it: it is
written about marks and bounds the damage to "the marks of what it sends and
availability, never another node's memory", and this damage is another node's
memory. The authentication the contract needs is already in the hardware: only
*X*'s kernel can write the ring *X* → *Y*.

**Verdict: real, the contract's fault** (the model follows the check as
written). Guarantee broken: the gate's containment of a faulty kernel, and the
grant rule "*X*'s memory never returns to an untyped while *Y* still translates
to it". Severity: **critical** (one faulty kernel; ordinary grants).

**Correction.** Contract, "One check on every message received", first item:
"the sender the message carries is the node whose ring it was read from (the
ring *X* → *Y* is writable only in *X*'s kernel), and its member word is
starting, live, sealing or sealed with that generation". One comparison per
message, no new state, now. Model: in `Model::consume`, refuse when
`message.header.sender != from` before `refused` (applied; the test passes:
the forged `Release` is refused and traced, the grant stays live).

## Observed in passing: a `Send` names a frame outside its grant's anchor

Not in the author's report; found while writing the test of finding 6. The
model carries a grant's frame (base, page size, pages) in the `Send`
(`grants::Granted`), and `place_remote` takes it as is; the map path
(`memory.rs:547`) checks only that the grant entry is live with that serial,
and the leaves of a remote frame count only in the use entry, so no ownership
word is read. `ver_y_a_send_cannot_name_a_frame_outside_its_grants_anchor`:
node 0 makes a real grant to node 1, then, faulty, writes into its own ring a
second `Send` naming the same grant and serial with the base of a frame of node
2. Unchanged model:

```
node 1 maps 100c06000, node 2's frame 100c06000, writable: Ok(Done); node 1 check Ok(())
```

In the contract the frame comes from the anchor, which only node 0's gate
writes, so the model's shape is a shortcut; but the contract does not close it
either: G3 (2) lets the grantee's gate map a frame that "a live grant to this
node covers", without reading the ownership word of the target chunk, and no
rule says the granter's gate checks that the anchor's frame lies in memory the
granter holds (the gate does not see the derivation list). **Verdict: real,
the contract's fault** (gate containment broken: a faulty node 0 makes node 1
map node 2's memory). Severity: **critical**. Correction: G3 (2), "or a live
grant to this node covers it **and the chunk's ownership word reads *taken* by
the granting node with the generation the use entry records (or the frame lies
in the granting node's floor, or is a device entry it owns)**": one word per
chunk, the read G3 already makes for local frames; no new state; now. Model: the
same test at the receive check (applied in `Model::refused` for `Send`, with
`Table::holds_page`; the test passes) or, closer to the contract, in the map
path. The model should also read depth and frame from the granter's anchor
rather than from the message, as the contract does.

## Corrections tried

In my copy (`git diff` there; nothing committed), I applied: `taken_here`
(finding 1), the leaf-count check in `memory_split` (2), no release of a pinned
iospace's untyped with `Untyped::lost` and check 19 (3), the remote refusal in
`message_page` (5), the depth bound in the `Send` check (6),
`checked_add(1).unwrap_or(1)` (7), the next-sequence test in
`enter_debug_areas` (8), `consumed = 0` (9), the ring-origin check (forged
header) and the frame-ownership check (observation). With them, every `ver_*`
test passes, and the whole `dodos-model` test run gives 1,157 passed, 0 failed
(the library's 535 tests among them). Without them, all but the finding 4 test
fail, as quoted above (finding 4's test asserts the model's present behaviour,
which is the contract's). I did not run `./verify` (format and clippy).

## Table

| Finding | Verdict | Severity | Correction |
|---|---|---|---|
| 1. Reserve chunk taken twice | Real, the model's fault | High | `taken_here`: a reserve word *taken* with this generation while holding the role is taken here (`busy`) |
| 2. `memory_split` with frozen leaves | Real, the model's fault (contract row unclear) | High | `memory_split`: `busy` if `mapped_block`; contract row: "`busy` if the entry's leaf count is not 0" |
| 3. Pinned iospace pages back to the untyped | Real, the model's fault | High | `destroy`: a pinned space releases nothing (`Untyped::lost`, check 19); `set_class` to a table only from *data* |
| 4. Failed detach, then unmap with no invalidation | Real, the contract's fault | Medium | Keep the device in the header marked *lost*; unmap on such an iospace is as on a failed unit (counts kept) |
| 5. Remote frame as message page | Real, the model's fault | Critical | `message_page`: refuse a remote frame (`invalid`), as the contract says |
| 6. Grant of depth 0 | Real, the contract's fault | Medium | Receive check of a `Send`: each grant live, to this node, that serial, not answered, anchor a frame of depth 1 to `TREE_DEPTH` |
| 7. Previous crash sequence 2^64 − 1 | Real, the contract's fault | Low | Rule 3: a header of sequence 2^64 − 1 is not valid |
| 8. Debug area next sequence 0 | Real, the contract's fault | Medium-low | Keep an area only if its next sequences are neither 0 nor 2^64 − 1 |
| 9. `consumed` kept across deconfiguration | Real, the model's fault | Low | `sched_configure` off: `consumed = 0` |
| 10. `attached_to` as `u8` | Refuted (unreachable, at most 16) | None | None needed; `u8::try_from` for style |
| Header naming another node than its ring | Real, the contract's fault | Critical | Receive check: the sender the message carries is the ring's writer |
| Observed: `Send` names a frame outside its anchor | Real, the contract's fault | Critical | G3 (2): the target chunk reads *taken* by the granter's recorded generation |
