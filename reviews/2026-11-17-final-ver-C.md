# Verification of the two reviews of lot C

Model: PR 3 of `dodos-kernel`, head `6312868`, copied to
`/private/tmp/dodos-pr3-ver-C` and changed there only. Contract:
`Docs/architecture/kernel-interface.md`; decisions in `Docs/decisions/`.

What I ran, in that copy: two new test modules, `boot::ver_c` inside
`model/src/boot.rs` (7 probes) and `model/src/scenarios/ver_c.rs`
registered in `scenarios/mod.rs` (8 probes), with
`cargo test -p dodos-model --lib ver_c_ -- --test-threads=1 --nocapture`.
`cargo test -p dodos-model --lib` on the untouched copy: 523 passed. The
copy's diff is those probes, one `pub(crate)` on `Nodes::reserve_work`
(visibility only), and two temporary patches I applied and reverted
(`start_page_bytes`'s two sizes, `consume`'s step). No repository was
changed and nothing was committed.

Findings that both reports make are judged once, under the first number.

---

## `model/src/boot.rs`

### H1 = O2 — the sizes of two records in `start_page_bytes`: **real**, fix

Both reports say the 7th item (entry 7, `StartBootTimes`) is budgeted 40
bytes and the 15th (entry 17, `StartMachine`) 80, where the ABI says 48
and 96 (`abi/src/start.rs:252-261, 343-382`; asserted at
`abi/src/tests.rs:1066, 1094`). I counted the required kinds of
`StartKind` (`abi/src/start.rs:66-91`): 0, 1, 2, 3, 4, 6, 7, 9, 10, 11,
12, 13, 14, 15, 17, 18, 19, 20, 21, 22, 24 are the 21 items of the
vector, so vector index 6 is `BootTimes` and index 14 is `Machine`. The
mapping holds and both numbers are stale.

Reproduced, and run: `ver_c_start_page_bytes_agrees_with_the_record_sizes_of_the_abi`
recomputes the same list with `size_of::<StartBootTimes>()`,
`size_of::<StartProcess>()`, `size_of::<StartMemory>()` and
`size_of::<StartMachine>()`. It prints `model 2168 true 2192 delta 24`
and fails. With the two sizes put to 48 and 96 the test passes (`model
2192 true 2192 delta 0`).

The consequence was run too:
`ver_c_a_start_page_of_64_pages_is_refused` searches `Kinds` and
`descriptor_size` for a machine whose page the contract refuses ("the
start-up page would need more than 63 pages", Start-up state) and boots
it. It prints `kinds 1387 descriptor 187: model 258032 (63 pages) true
258056 (64 pages)`: `Model::boot` returns `Ok`, and the frame it puts in
slot 9 has 63 pages where the page needs 64. With the two sizes fixed the
same machine is refused (`Err(Refusal::StartPage)`) and the test passes.
So this is not a comment defect: a machine the contract refuses starts.

Correction: `start_page_bytes` in `model/src/boot.rs`, the vector at
lines 571-591: `40` at index 6 becomes
`size_of::<StartBootTimes>()` (48) and `80` at index 14 becomes
`size_of::<StartMachine>()` (96); write the other fixed items the same
way so the list cannot drift again. The test that fails without it is
the one above. Severity: fix.

One correction to both reports: the entry `FirmwareTables` is budgeted 8
bytes (line 574) and the model never lists a firmware table — `Machine`
has no such field — where `StartFirmwareTable` is 24 bytes and an empty
entry is 0. So the model is **16** bytes short of the page the contract
describes, not 24, and the two errors partly cancel. My probe machine
sits in the 16-byte window, so the test above is calibrated on the net
figure; a correction of 24 alone (without the 8) would overshoot by 8 and
let a page of 63 pages be counted as 64. The second half of the fix is
therefore to drop the 8 or to list the firmware tables.

### H2 — the copied frames counted from a fixed physical base: **real**, minor

`build` counts the frames of every copied module with
`frames_of(start_at, m.1, m.2)` (`boot.rs:1105-1111`), where `start_at`
is the first untyped's base, and allocates them at
`untyped.base + untyped.watermark` (`boot.rs:1238-1249`). `module_frames`
(`abi/src/machine.rs:1300-1359`) chooses a frame size by the joint
alignment of the physical and the virtual address, so the two can differ
once the watermark has advanced by less than a chunk. The reading is
right: the count and the allocation are computed from different
addresses.

Not run: I did not build a machine where the slot count differs. The
estimate feeds `slots = (used + START_FREE_SLOTS).next_multiple_of(128)`
(`boot.rs:1118-1128`), so a difference of a few frames changes nothing
unless it crosses a 128-slot boundary, and I found no such machine.
Opus's own probe reached the same place and found no harm.

Correction: `Model::build` in `model/src/boot.rs`, lines 1105-1111:
count the copied modules in the same loop that places them, or count
`frames_of(at, m.1, m.2)` with the running `at` of `Machine::layout`'s
placement (lines 705-713), which is what `build` reproduces. A test that
fails without it: a machine with two copied segments whose second
alignment changes with the watermark, asserting the number of free slots
in the start-up space is at least `START_FREE_SLOTS`. Severity: minor
(the estimate is only ever too small by a few slots, and the 128 rounding
hides it).

### H3 = O1 — machine inputs that panic instead of being refused: **real**, fix

I wrote O1's five edits as tests of `Model::boot`. All five panic, at the
line each report names:

| edit of `Machine::example()` | panic |
|---|---|
| `floors.floor_node = 0` | `boot.rs:1105: index out of bounds: the len is 0 but the index is 0` |
| `cores[1].kind = 7` (one kind) | `boot.rs:434: index out of bounds: the len is 1 but the index is 7` |
| `phys_bits = 20` | `boot.rs:791: attempt to subtract with overflow` |
| `phys_bits = 30` | `boot.rs:799: index out of bounds: the len is 512 but the index is 2054` |
| `boot_nodes = Some((2, [(0, 1), (u64::MAX/32, 1)]))`, `accept_unfenced` | `boot.rs:424: attempt to multiply with overflow` |

I did not run `phys_bits = 64`: as O notes, the process aborts on the
70 TB allocation of `vec![0; 1 << 43]` at line 792, which is the same
defect by another route.

Verdict: real. The model has a `Refusal` for exactly this ("the values of
the machine out of range", reason 6 of the stop record, Start-up state)
and `Machine::layout` (`boot.rs:625`) is where the contract's list of
refusals is applied; a panic is not a refusal, and in release the
multiply wraps and aliases core numbers instead of being seen at all.

Correction: `Machine::layout`, `model/src/boot.rs`, before
`initial_nodes()` at line 641: check `self.kinds` is not empty and every
`core.kind < kinds.len()`; check `geometry.chunk_shift() <=
self.phys_bits < 64`; check `floors.floor_node` is at least one chunk and
that the floor produces at least one untyped before `build` indexes
`untypeds[0]` (line 1105, or have `start` return `Refusal::Floors` when
`untypeds` is empty); check each `boot_nodes` window against
`CORE_WINDOWS` as `node_start` does (`nodes.rs:142`), or use
`checked_mul`/`checked_add` in `initial_nodes` (line 424) and refuse.
Every one of the five tests above is the test that fails without it.
Severity: fix.

### O3 — `Refusal::Floors` does not document one cause: **real**, trivial

`boot.rs:845` returns `Refusal::Floors` for
`plain_roles >= ROLES_PLAIN_MAX`, and the doc at `boot.rs:474-476` names
floors, reserves, kept memory, *k* and the times but not the number of
plain roles. Confirmed by reading both lines; the claim is about a
comment, so nothing to run. Correction: add the cause to the doc of
`Floors`, or return `Refusal::MachineValues` there, since the contract
lists the plain roles with the values of the machine, not with the floors.
Severity: trivial.

---

## `model/src/cores.rs`

### H4 — `go_idle` answers a request after `choose`: **real, unproven**

Read and traced: `Model::end` (`sched.rs:255-289`) runs `choose(entry)`
(setting `running` and `thread`), then calls `go_idle` when the core has
no thread, and `go_idle` (`cores.rs:501-514`) calls `answer_pending`,
which can call `complete(requester)` (`cores.rs:458-483`), which wakes a
thread (`lib.rs:1877`) and so places its context in a ready queue;
`reschedule_others` (`sched.rs:321`) skips the calling core, so no
`Ipi::Reschedule` is posted for it; and `check_choice`
(`check/sched.rs:161`) requires `core.running == chosen || pending`. I
found no rule that forbids `sched_configure` (`sched.rs:762`) from moving
a context of a thread that waits in `Wait::Cores` to the core that is
going idle, and `mark_leaving` does not satisfy the "46: running context"
check. So the state the check rejects is reachable in the code.

Not run, and the reason: reaching it needs one thread waiting on another
core's invalidation request, another thread of the same node moving the
first one's context with `sched_configure`, and the target core then going
idle in one event; I did not build that scenario in the time I had. I do
not refute it. Severity: stop if it is reached — it breaks invariant 46.

Correction, any of: in `Model::end` (`model/src/sched.rs`), call
`go_idle` before `choose`; or re-run `choose` after `go_idle` when
`answer_pending` woke something; or let `reschedule_others` consider the
calling core too. The test that fails without it is the scenario above.
Severity: fix.

### H5 — `spurious` invalidates a page, not the translation: **real**, fix

`Model::spurious` (`cores.rs:585-620`) computes
`address / self.page() * self.page()` and passes it to `invalidate_on`,
whose `Flush::Range` arm removes `cached.remove(at)` for exactly those
addresses (`cores.rs:377-384`), while `cache_here` (`cores.rs:559-579`)
keys the TLB by each translation's base `at`.

Run: `ver_c_a_spurious_fault_leaves_a_large_page_in_the_tlb` maps a
`PageSize::Large1` translation at `0x4000_0000`, caches it on core 0,
takes a spurious fault at `0x4000_1000` and reads the TLB. It prints
`cached at the translation's base: true; spurious at 0x40001000 handled:
true; still cached: true`. The stale entry the model promises to
invalidate stays, so a later write through it is invisible.

Correction: `Model::spurious` in `model/src/cores.rs`, lines 609-613: use
the base of the translation that `translated_in` found — return it from
`translated_in` (line 613-620) or look it up again with the same
`range(..=address).next_back()` — and flush that base. The test above is
the test that fails without it. Severity: fix.

### O4 — a duplicated statement and an arm that cannot run: **real**, trivial

Read: `cores.rs:779-781` binds `let part = &mut self.cores[position];`
twice; the second is dead. `cores.rs:394` is `Flush::Nothing => {}` inside
`invalidate_on`, after the `if *flush == Flush::Nothing { return; }` at
line 368-370. Both confirmed at the cited lines. Correction: delete the
second `let` and the `Flush::Nothing` arm (the enum needs the arm only if
the match is exhaustive elsewhere). No test: it is a style defect.
Severity: trivial.

---

## `model/src/grants.rs`

### H6 — `grant_signal` and a stuck `signal_pending`: **real**, minor

`grant_signal` (`grants.rs:554-574`) writes the `Signal` and, if the ring
has no room, sets `signal_pending` on the use entry, with no check that
the granting node's generation is still current; every other reader of a
use entry checks it (`send_pending`, `rings.rs:663-665`, and
`r0_effects`, `nodes.rs:1017-1020`). And `send_pending` will not clear
the flag unless the granter is current (`rings.rs:681`), unlike
`release_pending`, which removes the entry when it is not
(`rings.rs:666-671`).

Run: `ver_c_a_signal_pending_whose_granter_is_over_stays_for_ever` puts
one use entry with `signal_pending` on node 0, makes node 1 dead, calls
`send_pending`, and prints `the use entry present true, signal pending
true, reserve busy true`. `reserve_work` (`nodes.rs:1893-1922`) reads that
flag, so the node runs a step of its recovery reserve at every
opportunity for the life of the generation. The first half — that
`grant_signal` sets the flag for a granter that is not current — I
confirmed by reading only: the window is between R0 and R2, where
`r0_effects` clears the flag but keeps the entry and the remote
capability is still in `self.remotes`, and I did not build a scenario in
it.

Correction: in `model/src/rings.rs`, `send_pending`, line 681: treat a
non-current granter as `release_pending` does — clear `signal_pending`,
and remove the entry when nothing else holds it — and in
`model/src/grants.rs`, `grant_signal`, line 566, refuse when
`!self.table.writes(remote.node) || self.table.generation(remote.node) !=
self.table.uses[me][&remote.use_entry].generation`, as `release_pending`
does at `rings.rs:667`. The test above fails without the first; a test
that calls `grant_signal` through a remote capability whose granter died
fails without the second. Severity: minor (a permanent busy loop, not a
wrong answer).

### O5 — a check that can never be true: **real**, trivial

Read, both sites: `grants.rs:178` (`node_send`) and `irq.rs:224`
(`irq_bind`) test `self.remotes.contains_key(&object)` after
`held(…, ObjectKind::Notify, …)`. `self.remotes` is filled only by
`place_remote` (`grants.rs:476`), whose object is inserted with
`ObjectKind::Frame` (`grants.rs:469`). So the branch cannot run, and in
`irq_bind` it comes after the `busy` check as if its order mattered.
Correction: delete both tests, or write the check the code means (a
notify lent to another node) if one is meant. Severity: trivial.

### O6 — `release_received` and an anchor with descendants: **real**, question

`grants.rs:825-828` frees the entry only when the anchor is present and
its `children` is empty, while its own doc says "it frees the entry if
its anchor has no descendant, otherwise the anchor stays, held by
nobody" — and "held by nobody" is an entry that is freed with the anchor
kept, which `free_with_anchor` does. So the code does not free the entry
in the case the doc describes. Read only: `an anchor is made only in the
kernel space (`make_grant`)` and O could not find a `derive` from it, so
`children` is probably always empty and the branch is inert. I did not
run it. Correction: settle which reading is meant — either always
`free_with_anchor` after a `Release`, or change the doc — and add a test
that releases a grant whose anchor has a child. Severity: question.

### O7 — a comment that says "wait" where the code returns `again`: **real**, trivial

`grants.rs:667-675`: the comment reads "A `Revoke` already in flight for
this grant: wait for its answer", the code returns `Ok(false)`, which the
doc of `revoke_anchor` defines as `again` with no wait, and the thread
does not wait. Confirmed at the cited lines. Correction: change the
comment, or make the caller wait (the contract's `cap_revoke` has no such
wait, so the comment is what is wrong). Severity: trivial.

### O8 — the serial rule written twice with a magic mask: **real**, trivial

`grants.rs:115` and `nodes.rs:1434-1435` both write
`(entry.serial + 1) & 0x3FFF_FFFF`; the width's home is
`abi/src/ring.rs:56-59`. Confirmed by grep. Correction: one function
`next_serial(entry)` in `model/src/grants.rs` (or a
`dodos_abi::REVOKE_SERIAL_MASK`), called by both. Severity: trivial.

---

## `model/src/rings.rs`

### H10 = O9 — a user ring is served 16 **messages**, not 16 entries: **real**, fix

Both reports have it, with the same line. `consume` (`rings.rs:478-514`)
advances the consumer index by `length` entries (line 512) but counts
`served += 1` (line 513) against `step`. The contract says the user ring
is served "at most 16 entries per ring per interrupt" (What crosses
between nodes, processing), and `abi/src/ring.rs:26-27` says "Entries of
a user ring served per interrupt".

Run: `ver_c_one_interrupt_serves_sixteen_messages_not_sixteen_entries`
injects 17 `Send`s of 2 entries each (34 of the ring's 64 entries) from
node 1 to node 0 and fires one `Event::Ipi`. It prints `34 entries
injected, consumed in one interrupt 32` and fails against
`RING_USER_STEP`. With `served += length` the same test prints 16 and
passes, and `cargo test -p dodos-model --lib` still passes 523 tests
(524 with the probe), so the correction breaks nothing.

Both reports also name the test that cannot see it: F14
(`model/src/scenarios/mistral.rs:408-433`) injects 17 one-entry
`Signal`s, where messages and entries are the same. That is right and it
is why 523 tests pass on this defect.

Correction: `Model::consume` in `model/src/rings.rs`, line 513: `served
+= length` (the header's length, or the 1 an unreadable entry takes).
Severity: fix.

### H9 — `refused` trusts the header's sender: **intended**, none

`refused` (`rings.rs:376-399`) checks `header.sender`'s member word and
generation, and `receive_message` dispatches with `header.sender`; the
ring's `from` is used only in the code-11 trace word, as the contract's
trace table says: "word 5: the sending node (bits 0-15) and its
generation (32-63)". The contract's one check is stated on the sender the
message carries: "the sender's member word is starting, live, sealing or
sealed with that generation" (What crosses between nodes), and it then
says outright: "kernels trust each other's stamping as they trust each
other's checks; a kernel that lies about marks is faulty, which the gate
does not contain". A node that writes another node's identifier into its
own ring is the faulty kernel the contract excludes, and `Body::UnitRequest`
passing "whatever its epoch, which the holder judges" is that same
sentence. So the model follows the contract: intended, no severity.
Correction: none. If the contract should refuse a message whose header
sender is not the ring's owner, that is a change to the contract first,
not to the model.

---

## `model/src/irq.rs`

### H7 — a core event is claimed as an MSI: **the contract's fault**, minor

`irq_claim` (`irq.rs:20-130`) checks `machine.core_events` for kind 3
(line 62), then branches only on `is_line()`: the segment of a core event
is `source.segment()`, which is 0 (line 108-116), so `segment_roles(0)`
asks the IOMMU unit, the handle is put in `unit.remap` (line 165-168),
an `InterruptCache` request is submitted (line 187-190), and the result
is `(msi_remapped(handle), 0)` instead of the `(0, 0)` a line gets
(line 154-163).

Run: `ver_c_a_core_event_is_claimed_as_an_msi` boots a machine with
`core_events = true`, claims `IrqSource::core_event(1)` on vector 48 and
prints `a core event claimed: Ok(Waits), the IOMMU's remap entries
Some({0: (0, 1)})`. So the model writes the IOMMU's remapping entry for
an event no device raises, and hands out an MSI address for it.

Why the contract's fault: the contract says kind 3 "is claimed through
the `irq_control` … like any vector … It is an edge source" (Unlike
cores) and that "each claimable entry of each physical core has a fixed
remapping entry" (Interrupts, the source word), and the result is "the
two words a device must be given to raise the interrupt by a message, and
0 and 0 for a line". Nothing says which of the two a core event is, and
nothing says whether its remapping entry is written (its source
validation would need a requester ID it has not). Both reports are also
right that no test in `model/` claims or delivers a core event:
`boot.rs:339` sets `core_events: false` in `Machine::example()`.

Correction, if the owners read it as I do: `irq_claim` should return
`(0, 0)` for a source that is neither a line nor an MSI and skip
`segment_roles`, and the contract should say so in one sentence; the test
is `ver_c_a_core_event_is_claimed_as_an_msi`, which fails today. Until
the contract says it, the model's reading is defensible. Severity: minor.

### O11 — the remapping handle formula written four times: **real**, trivial

`irq.rs:77-78` (with `saturating_sub`), `155-156`, `288-289`
(`line_target`) and `434-435` (`handle_of`); its inverse at
`units.rs:259`. Confirmed by grep at each line, and `irq_claim` does
compute it twice under the name `handle` (77 and 155) from two different
values (`self.cores[position].number` and the argument `core`). They are
equal today. Correction: one `fn handle_of(&self, core, vector) -> u16` in
`model/src/irq.rs`, used at all four places (and its inverse named
beside it). Severity: trivial.

### O12 — the order of checks in `irq_claim`: **real**, trivial

The comment at `irq.rs:30-32` reads "the source as its format allows, a
GSI that an IOAPIC serves (judged with the source), then the vector",
while the core number is judged between them (lines 43-48). The contract's
order is "A source the format refuses is `invalid`, then a core number
that is not a core of the `irq_control`'s node, then a vector outside the
claimable range" (Interrupts, the call table), so the **code** is right
and the comment is what should change. Correction: name the core number
in the comment between the GSI and the vector. Severity: trivial.

---

## `model/src/nodes.rs`

### H8 = O10 — the resume and the rings it never consumes: **real**, fix

Two claims, both in the same function, and the contract settles both.
`resume_step` (`nodes.rs:1662-1725`) never consumes a ring, and its doc
(1660-1661) says it does; the contract says the resuming node "runs R0,
R2 and R3 for every node whose generation ended while it was sealed …,
R4 and R5 for those still fenced, and R2 to R4 for those unfenced …, in
steps of its recovery reserve, **then consumes what waited in its rings
under the check, and the node becomes live**" (The calls, `node_start`,
mode 1). And for a node whose generation ended while this node was
sealed, `resume_step` calls `drop_ended(node, old, units)` (line 1702)
without checking its result, unlike the `Fencing | Fenced | Unfenced`
arm three lines above (1681-1688), which returns until the reclaim is
done; then, if every core is non-silent, it sets `ready`, clears
`sealed_view` and `ended_done` and writes live (1706-1725).
`drop_ended` returns as soon as `units` runs out or `remove_root` is not
`Done` (`nodes.rs:1741-1769`), so the rest of R2/R3 is never done and the
node is live with stale remote capabilities and pinned grants.

Not run, and the reason: this needs a two-node scenario that seals one
node with a `Send` in its user ring and a dead peer whose generation
ended during the seal; I did not build it in the time I had. The code and
the contract sentence are unambiguous, and both reports read the same
lines. Severity: fix (the rings half can leave a message written before a
seal unanswered for ever, which is the class of fault the contract calls
out for the sealed sender in D-131).

Correction: `Model::resume_step` in `model/src/nodes.rs`: track, per node
whose generation ended, whether `drop_ended` returned with work left, and
return `false` from the loop while any does (as the fenced arm does); then
before `self.ready = true`, call `serve_kernel_rings` and consume the
user rings under the check (`rings_waiting` is already there, line
596-607), so that the live word is written after the rings are empty, as
the contract orders it. Tests: a node that resumes with a `Send` in its
user ring must answer it before any thread of the node runs; a node that
resumes with more stale remotes than one step's units must not be live
until the last one is removed.

### O13 — R1's unit wait is judged on the monotonic clock: **real**, fix

`submit_for` (`units.rs:439`) takes `let now = self.now;` and pushes
`(serial, now)` into the unit's queue (line 482-484); every other unit
wait takes `self.membership_now()` (`units.rs:403` for a request's start,
`units.rs:544` for its answer) and `unit_step` compares with
`self.membership_now()` (`units.rs:687, 702`). R1's failure is judged on
the queue's instant against `self.now` (`nodes.rs:1093-1096`), and
`unit_deadline` (`units.rs:738-752`) lists only `Stage::Local` and
`unit_service`, so R1's submission has no instant in `reserve_due`. The
README says the clock of membership leaves out the debugger stop "for the
observations, the seal, the evidence, the fence record, the waits (a
request's start, a unit's submission, a start, a hand-over) and
`idle_until`" (`model/README.md`), and a submission is on that list.

Not run: it needs a debugger stop (`System::stub_stop`) between R1's
submission and its check, which I did not build. O also reports it as
found by reading. Correction: `submit_for` in `model/src/units.rs` should
store `self.membership_now()` (or the queue should store both), R1's
check at `nodes.rs:1093-1096` should compare with `membership_now()`, and
`unit_deadline` should include the oldest instant of the queues of the
roles this node holds. The test that fails without it: a unit that does
not confirm R1 within `IOMMU_WAIT_NS`, with a debugger stop in between,
must not be marked failed by the stop's time. Severity: fix — it marks a
working unit failed, the fault D-135/D-140 spend sentences on.

### O14 — `start_image` is state nothing reads: **real**, trivial

`nodes.rs:257-260` writes `self.start_image = (image ==
NODE_IMAGE_REPLACEMENT, module)`; `start_image` (`lib.rs:1143`) is read
nowhere else and its `.1` (the module) nowhere at all — grep for
`start_image` returns those three lines. Correction: remove the field and
keep what line 259 needs (a bool), or model the rule the module is for.
Severity: trivial.

### O15 — the reserve step's doc: **real**, trivial

The doc at `nodes.rs:1925-1929` gives the order "the reclaims and R6, the
roles, the units, the kernel rings, the pending releases and signals" and
"at most 32 units of work"; the code runs `unit_step`, then
`serve_kernel_rings`, then `roles_step` (1955-1957), with an inline
comment that explains why, and `start_step`, `fence_step`, `unit_step`,
`send_pending` (up to `PENDING_STEP` more), `observe_needed` and
`accuse_with_evidence` take nothing from `units`. Confirmed at the cited
lines. Correction: the doc's order and its bound. Severity: trivial.

### O16 — R4's audit accepts any reserve's word: **real**, trivial

`audit_block` (`nodes.rs:1273-1287`) accepts `w.owner() == me ||
matches!(w.owner(), Owner::Reserve(_))` against its own doc ("still reads
taken by this node with its generation") and the contract's R4 ("It
checks that every ownership word covered by its own live blocks still
reads taken by it with its generation", Reclaim). `R6` does check the
node's own reserves (`nodes.rs:1393`). Inert in practice, since a block of
this node covers its floor's chunks and a reserve's chunks are not in
that floor, so I did not run it. Correction: drop the `Reserve(_)`
alternative, or check `holds_reserve(self.node, j)` as R6 does. Severity:
trivial.

---

## `model/src/units.rs`

### H16 — the operands of an operation, and the unit kind: **real** (the
generation half), the contract's fault (the rest), minor

`operands_allowed` (`units.rs:252-290`) has one path for an operation and
one for an operation whose operands are masked, and the masked path
judges the operands' words without checking that the generation they
carry is the reporting node's current one. It is the check behind both
`unit_request` (`units.rs:530`) and `role_take` (`roles.rs:538`).

Run: `ver_c_masked_operands_of_another_generation_are_refused` sends a
masked redirection whose words belong to a dead node's generation and
prints `allowed true`; the operation is accepted. So a holder applies an
operation that a node of an ended generation wrote, which is the fault
the contract's R1 exists to clear.

Not run, the other two parts of the finding, because the contract does
not decide them: which unit kinds admit which operation, and whether a
holder refuses an operation of another unit kind's device. The contract
lists the kinds and their modes (Interrupts, the remapping entry) without
saying which operations each admits, so the model's unrestricted reading
cannot be called wrong. Those two belong in the contract first.

Correction: in `operands_allowed`, judge the generation of the word the
operands are read from in the masked path as the unmasked path does (or
take the requester's generation as a parameter and compare it there); the
test above is the test that fails without it. Severity: minor.

### O20 — `confirmed` clears a submission of the same instant: **real**, minor

`confirmed` (`units.rs:490-505`) drops a submission of the role when
`serial` matches, and it is called from `unit_step` with the serial of
the queue's oldest entry. A submission recorded in the same step
(`unit_requested` stores it, `units.rs:520-535`) has an instant equal to
the check's, so a submission that has asked the unit nothing and a
confirmation for another submission of the same role can be matched on a
serial that only orders them within the step. Read only: I did not build
the two-submission scenario. Correction: confirm only a submission whose
instant is before the current check's, and compare the queue's position
as well as the serial. Severity: minor.

## `model/src/roles.rs`

### H11 — a rebuild deletes a resumed node's entries: **real**, fix

`rebuild_step` (`roles.rs:452-514`) skips a node `z` whose
`!self.table.writes(z)` (460) without asking it for a `Report`, then at
513-514 collects the nodes that read `Sealed` *now* and, for every entry
whose owner is neither `claimed` nor `sealed`, removes it (487-491 for
`entries`, 502-509 for `lines`). A node that was sealed when the scan
passed it and is live when the scan ends is therefore not in `sealed`,
has sent no report, and every context entry and line entry it owns is
removed from the unit. Read only; I did not build the scenario (a
rebuild that is waiting on a later node while a sealed node resumes).

Correction: `Model::rebuild_step` in `model/src/roles.rs`: record the
nodes it skipped as sealed in the rebuild (`Rebuild` in
`model/src/units.rs` already carries `node`, `key` and `items`; add the
set), and treat that set, not the state at the end, as the `sealed` list
at line 513. The test that fails without it: a unit with a device of a
sealed node, a rebuild that starts, the node resumed before the rebuild
ends, and its context entry still in the unit afterwards. Severity: fix.

### H12 — `after_take` omits a dead node: **real**, minor

The doc at `roles.rs:388-392` says R1 runs "for every node that is
fencing, fenced, unfenced or dead", and the contract agrees: "A node that
takes a unit role, at step 5 of a planned hand-over or at a take-over,
runs R1 … on that unit for every node that is already fencing, fenced,
unfenced **or dead**, before it serves any other request for the unit"
(Roles, R1 at every change of holder). The match at `roles.rs:397-403`
lists `Fencing | Fenced | Unfenced` only. So the code is what is wrong,
and its own comment and the contract both say so. Read only: it needs a
node that reaches Dead before the new holder takes over, which I did not
build. Correction: add `MemberState::Dead` to the match in
`after_take` (`model/src/roles.rs:397-403`), taking the generation the
member word holds for a dead node as `r0_effects` does
(`nodes.rs:1017`). Severity: minor on its own; with O17 it is more, see
the closing paragraph.

### H13 — the contradictory comment on `rebuilt_attach`: **real**, trivial

`roles.rs:518-520` says a reported device's attach word may read
"*attached*, or *pinned* (moved to *attached* first, as at an attach)",
while `rebuilt_attach` (`roles.rs:556-566`) accepts `Attached` only and
never moves `Pinned` to `Attached` (it takes `&mut self` for nothing).
Confirmed at both lines. The code matches D-137 ("A context entry only
for a device whose attach word reads *attached* … with the root the
report names") and the doc of `rebuilt_attach` says why a pinned device
is in no report, so the comment at 518-520 is the stale one. Correction:
delete "or *pinned* (moved to *attached* first, as at an attach)" and drop
the `&mut` if nothing else needs it. Severity: trivial.

### H14 — `rebuild_step` reports progress when the ask fails: **real**, minor

`roles.rs:472-480`: `let asked = self.write_message(z, body,
Some(Completes::Report { role }), None); rebuild.asked =
asked.is_ok(); self.rebuilds.insert(role, rebuild); return true;` — so a
`Full::Ring` or `Full::Credit` leaves `asked` false, `node` unchanged, and
the function reports progress. `roles_step` consumes a unit for it
(`roles.rs:227-234`), and `reserve_step` loops `while *units > 0 &&
progressed`, so one reserve step spends all 32 units rewriting the same
failed ask.

Run: `ver_c_a_rebuild_whose_report_ask_is_refused_reports_progress` puts a
rebuild on node 1, fills node 1's kernel ring to the holder, and prints
`one roles step: progressed true, asked false, units left 31`. Correction:
`Model::rebuild_step` in `model/src/roles.rs`, lines 478-480: return
`asked.is_ok()` (after storing the rebuild), so a failed ask is not
progress. The test above fails without it. Severity: minor (the reserve
step still terminates; only its units are wasted).

### H17 — a kept request during a rebuild counts as `begun`: **real**, fix

`hand_step` (`roles.rs:277-280`) computes `begun` as any `unit_service`
entry of that role, or any request of the role in `Stage::Local`.
`unit_requested` stores a request with `submitted: None` while the role
rebuilds (`units.rs:520-535`), and `serve_kept` submits it only when the
rebuild ends (`roles.rs:570-584`); such an entry has asked the unit
nothing, so the unit's queue can be drained, but `begun` is true, and
after `IOMMU_WAIT_NS` `hand_step` calls `fail_unit` ("falsely marking a
working unit as failed"). `role_hand`/`hand_all_units` do not check
`self.rebuilds` (and `role_hand` does not check `self.handing`, which is
the second half of the finding, judged as O18). Read only; I did not
build the scenario. Correction: in `hand_step`, count a `unit_service`
entry as `begun` only when `submitted.is_some()`, and either refuse
`role_hand` while `self.rebuilds.contains_key(&role)` with `busy` or have
`serve_kept` defer while `self.handing` holds the role. The test that
fails without it: a rebuild of a unit with a kept request, a hand-over of
the role begun meanwhile, and the unit not failed after
`IOMMU_WAIT_NS`. Severity: fix.

### O17 — `Item::Handle` is never built: **real**, fix

`Item` documents three kinds of item (`rings.rs:63-75`) and `items()`
(`roles.rs:590-630`) builds `Device` and `Line` only; `Item::Handle(_)`
appears only as a matched-but-empty arm (`roles.rs:547`), and grep finds
no construction of it in `model/src`. Run, as far as it goes:
`ver_c_a_report_item_is_never_a_handle` prints `the items of the IOMMU's
role: []` on a node with the IOMMU's role and no device, and finds no
handle item anywhere; the grep is the rest of the evidence. So the
remapping entries of a unit (`unit.remap`) are not rebuilt at all, and
with H12 they are not cleared for a node that died before the take-over
either. Correction: build `Item::Handle` in `items()` for the handles of
this node's cores (`table.irq_tables`), and handle it in `rebuild_step`
as `Item::Device` is handled — insert into `unit.remap` when the handle
is still claimed by the reporting node — and clear the entries no report
claims. Severity: fix.

### O18 — a second `role_hand` orphans the first caller: **real**, stop

`role_hand` for a unit role (`roles.rs:139-152`) inserts into
`self.handing` without checking that the role is already handing, and the
role word still reads held by this node until step 4 (`hand_step` writes
handing at `roles.rs:300-310`), so a second call passes every check of
`roles.rs:109-115`. `hand_step`'s `finish` wakes only `hand.caller`
(`roles.rs:256-267`), the second thread.

Run: `ver_c_a_second_role_hand_orphans_the_first_caller` gives node 1 two
threads, holds the unit undrained, and has both threads call `RoleHand`
to node 2. It prints `before: first Some(Hand(0)), second Some(Hand(0));
after: first Some(Hand(0)), first woken false, second woken true`. The
first call never returns, which the contract's own bound forbids: "Bound:
constant work, plus for a unit role one wait for the unit's queue of at
most `IOMMU_WAIT_NS`" (`role_hand`), and `hand_all_units` guards the same
case with `!self.handing.contains_key(&role)` (`roles.rs:195`).

Correction: `Model::role_hand` in `model/src/roles.rs`, before line 139:
`if self.handing.contains_key(&role) { return Err(Error::Busy); }` — the
contract's state line reads "busy if the role is not held by the caller's
node", and a role in hand-over is on its way out, so `busy` is the
reading the other paths use; `hand_all_units` already does it. The test
above fails without it, and the same guard on `self.rebuilds` closes
H17's second half. Severity: stop (a call that never returns).

### O19 — the rebuild keeps an entry whose report does not match: **real**, minor

`rebuild_step` (`roles.rs:487-491, 521-526`) keeps any old entry whose
owner's report names the device, whatever root the report gives, and
rewrites the entry only when `rebuilt_attach` holds; a report that names
a root the attach word does not hold leaves the old entry, with its old
generation, in place. The comment says "keep the entries that match,
rewrite those that differ … clear every other entry no report claims",
and the contract (D-137) says a claimed entry is kept when its word reads
attached with the root the report names. Read only; it needs a node that
reports a device with a root its attach word does not hold, which is a
faulty node. Correction: clear the entry when the report's root does not
hold, or state which reading is meant. Severity: minor.

---

## `model/src/system.rs`

### H15 — spare cores are `Stub` on ARM64 and RISC-V: **real, inert**, trivial

`System::boot` (`system.rs:121-131`) gives every core whose word is not
`Owned` `Hardware::Stub { window: false }` whatever the architecture,
while `stop`, `park` and `wake` (`system.rs:668-710`) treat a core that is
parked or not started on `Aarch64` and `Riscv64` as `Hardware::Off`.
Confirmed at the cited lines. No consequence is reachable: the model does
not model nodes that take cores at run time (`model/README.md`, "What it
does not model", and "Nodes that take and give cores at run time: the
contract only reserves words for it, and so does the model"), so no event
starts or stops a core that is in no node. Correction: pick one
representation per architecture in `boot` (the same one `stop`/`park`
use), or drop the architecture distinction. Severity: trivial.

### O21 — a duplicated comment paragraph: **real**, trivial

`system.rs:645-651` says the ARM64 SDEI duty twice. Confirmed by reading.
Correction: delete one of the two sentences. Severity: trivial.

### O22 — a refused start leaves the core `Entering`: **real**, minor

`enter_if_named` (`system.rs:786`) sets `self.hardware[core] =
Hardware::Entering` before calling `enter`, and `enter` (`system.rs:803-808`)
returns on `Model::start`'s `Err(Refusal::StartPage)` without writing
anything, so the core stays `Entering` with no model and nothing traces
it; the starter's `START_NS` ends the start, and no event leaves that
state. Confirmed by reading. Not run: my attempt to build such a machine
made the machine itself refuse to boot, and the model starts every node of
the layout at boot, so the state needs a start of a node slot that the
layout did not start, with a page slot 0's node could still build; I did
not construct it. Correction: in `System::enter`, on `Err` write the
refusal (a stop record as the machine start-up does, crash reason 8) and
put the core back to `Hardware::Off` (or park it on x86-64), so that no
core rests in a state no event leaves. Severity: minor.

---

## What both missed

Three things my reproductions turned up that neither report states. First, the start-up page is short
by 16 bytes, not 24: the entry `FirmwareTables` is budgeted 8 bytes
(`boot.rs:574`) for a table the model never lists, so the two stale
record sizes and this placeholder partly cancel, and a correction that
only fixes 48 and 96 would put a 63-page page over the limit it is
checking — the window where the model accepts a page the contract refuses
is 24 bytes wide in the model's arithmetic but 16 bytes wide in reality.
Second, this defect is invisible to every existing test for a reason
neither report draws: `Machine::example()`'s page is 2,168 bytes against
a limit of 258,048, so no test in `model/tests/boot.rs` comes near it,
and the check has no test at all — a machine of 1,387 kinds and a
descriptor size of 187 is what it takes to reach the edge. Third, from
the two findings both put in different files: H12 (R1 skipped for a dead
node) and O17 (`Item::Handle` never built) are the same hole from two
sides. A node that died before a take-over keeps its remapping entries
(`unit.remap`) on the unit, because no holder runs R1 for it and the
rebuild that is supposed to make up for R1 carries no handle item to
compare against; so the rebuild's consolation, which the contract names
in R1's parenthesis ("for an IOMMU unit, the rebuild of a take-over
already clears the context entries that no report claims"), does not hold
for the remapping entries at all, and a stale handle lets a device of the
old generation raise an interrupt on the new one. Neither report says
that, and the two corrections have to land together.

## Table

| Finding | Verdict | Severity | Correction |
|---|---|---|---|
| H1 = O2, `start_page_bytes` budgets 40 and 80 for 48 and 96 | real, run (2168 vs 2192; a 64-page page accepted) | fix | `boot.rs` `start_page_bytes`: `size_of::<StartBootTimes>()` and `size_of::<StartMachine>()`, and drop the 8 bytes of the empty `FirmwareTables` entry |
| H2, copied frames counted from `start_at`, allocated at the watermark | real (read); no machine found where the slot count differs | minor | `Model::build`: count with the running `at` of the placement loop, and a test on the free slots of a two-copied-segment machine |
| H3 = O1, five machine inputs panic instead of refusing | real, run (five panics at 424, 434, 1105, 791, 799) | fix | `Machine::layout`: kind index, `chunk_shift <= phys_bits < 64`, a non-empty floor, `BootNodes` windows bounded or `checked_mul` |
| H4, `go_idle` answers a request after `choose` | real in the code, unproven (not run) | stop if reached | `Model::end`: `go_idle` before `choose`, or re-choose after it, or let `reschedule_others` see the calling core |
| H5, `spurious` flushes the page, not the translation's base | real, run (the large page stays cached) | fix | `Model::spurious`: flush the base `translated_in` found |
| H6, `signal_pending` of an ended granter is never cleared | real, run (flag stays, reserve busy for ever) | minor | `send_pending` clears or removes it when the granter is not current; `grant_signal` checks the generation |
| H7, a core event claimed as an MSI on segment 0 | contract's fault, run (IOMMU remap `{0: (0,1)}`, `Waits`) | minor | the contract says which two words a kind-3 claim returns; if `(0,0)`, `irq_claim` skips `segment_roles` and the test is `ver_c_a_core_event_is_claimed_as_an_msi` |
| H8 = O10, the resume never consumes its rings and drops `drop_ended`'s remainder | real (read, contract quoted); not run | fix | `resume_step`: wait for `drop_ended` as for a reclaim, and consume the rings before `ready` and the live word |
| H9, `refused` trusts the header's sender | intended (the contract trusts the sender's stamping) | none | none |
| H10 = O9, 16 messages served per interrupt instead of 16 entries | real, run (32 entries), fix verified (16, suite green) | fix | `Model::consume`: `served += length` |
| H11, a rebuild deletes a resumed node's entries | real (read); not run | fix | `rebuild_step`: keep the set of nodes skipped as sealed, and use it as `sealed` |
| H12, `after_take` omits `Dead` | real (read, contract and its own doc agree); not run | minor | `after_take`: add `MemberState::Dead` |
| H13, the comment on `rebuilt_attach` mentions `pinned` | real (read) | trivial | delete "or *pinned* (moved to *attached* first)" |
| H14, `rebuild_step` returns true when the ask fails | real, run (`progressed true, asked false`) | minor | `rebuild_step`: return `asked.is_ok()` |
| H15, spare cores are `Stub` on ARM64 and RISC-V | real, inert (read) | trivial | one representation per architecture in `System::boot` |
| H16, the operands of a masked redirection and the unit kind | real, run (a word of another generation accepted); parts 1-2 the contract's fault | minor | `operands_allowed`: check state and generation in the masked arm; the contract should say whether a holder refuses an operation of another unit kind |
| H17, a kept request counts as `begun` and fails the unit | real (read); not run | fix | `hand_step`: count only `submitted.is_some()`, and refuse `role_hand` while a rebuild holds the role |
| O3, `Refusal::Floors`'s doc omits the plain roles | real (read) | trivial | add the cause to the doc, or refuse with `MachineValues` |
| O4, a duplicated `let` and an arm that cannot run | real (read) | trivial | delete `cores.rs:780` and the `Flush::Nothing` arm |
| O5, a check that can never be true in `node_send` and `irq_bind` | real (read) | trivial | delete both, or write the check that is meant |
| O6, `release_received` does not free the entry the doc describes | real (read), inert | question | settle the reading; a test with a grant whose anchor has a child |
| O7, "wait" in a comment where the code returns `again` | real (read) | trivial | fix the comment |
| O8, the serial rule written twice with a mask | real (read) | trivial | one `next_serial` in `grants.rs` |
| O11, the remapping handle computed four times | real (read) | trivial | one `handle_of`, used at `irq.rs:77, 155, 288, 434` |
| O12, the comment's order in `irq_claim` | real (read); the code matches the contract | trivial | name the core number in the comment |
| O13, R1's wait on the monotonic clock and not in `unit_deadline` | real (read, README quoted); not run | fix | `submit_for` stores the membership instant; R1 compares on it; `unit_deadline` includes the queues |
| O14, `start_image` read nowhere | real (read, grep) | trivial | remove it, or model the module it keeps |
| O15, the reserve step's doc order and bound | real (read) | trivial | fix the doc |
| O16, `audit_block` accepts any reserve's word | real (read), inert | trivial | drop the `Reserve(_)` alternative |
| O17, `Item::Handle` never built, so `unit.remap` is never rebuilt | real, run (no handle item; grep finds no construction) | fix | `items()` reports the node's handles and `rebuild_step` clears and rewrites `unit.remap` |
| O18, a second `role_hand` orphans the first caller | real, run (`first Some(Hand(0))`, never woken) | stop | `role_hand`: `busy` while `self.handing` holds the role (and while `self.rebuilds` does) |
| O19, a claimed entry whose report does not match is kept | real (read) | minor | clear it, or state the reading |
| O20, `confirmed` clears a submission of the same instant | real (read) | minor | confirm only what was submitted before this instant's check |
| O21, a duplicated comment paragraph in `system.rs` | real (read) | trivial | delete one sentence |
| O22, a refused start leaves its core `Entering` | real (read); not run | minor | `System::enter`: write the refusal and return the core to `Off` or the park stub |
