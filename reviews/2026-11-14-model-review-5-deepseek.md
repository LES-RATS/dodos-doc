# Review 5 of the one-core model (deepseek)

Date: 14 November 2026. Branch `model`, commit `4554d26` ("thread_cancel: two
tests that the mutation check asked for"). Review only: nothing in
`dodos-kernel` or `Docs` was changed, committed or pushed.

Read completely: `Docs/architecture/kernel-interface.md`,
`dodos-kernel/AGENTS.md`, `.agents/skills/dodos-rust/SKILL.md`,
`abi/src/lib.rs`, `model/src/{lib,caps,ipc,check}.rs`,
`model/src/check/tests.rs`, `model/tests/{calls,property}.rs`, decision D-106 in
`Docs/decisions/README.md`. I did not open `Docs/reviews/`.

How I worked: every claim marked "run" was made by running code; "read" means
the sources; "suspected" means neither. The mutation run and the probes ran in
`/tmp/mut` and `/tmp/probe`, copies of the repository outside it.

Baseline, run first: `nix develop -c cargo test -p dodos-model` passes, 405
tests (104 in `check/tests.rs`, 292 in `calls.rs`, 9 in `property.rs`), 76 s. The property suite with `SEEDS` raised from 24 to 50 (100,000
more random calls, 176 s) also passes, so the invariants of `check` hold for
twice the coverage the repository claims (run).

## Verdict

**The model agrees with the call reference in every sentence I could break: I
found no wrong behaviour.** Of the 142 mutants, 133 fail a test and 4 make the
test binary run for ever; the 5 survivors are two real test gaps (one rule),
one duplicate of them, and two behaviour-preserving rewrites of mine.

What is right, in one line each:

- The `thread_cancel` rule and the four sentences after it (taken out of the
  queue and `cancelled`, the reply object idle, nothing remembered, a wait that
  is already over, a suspended target) are each pinned by a test, and the six
  mutants aimed at them were all killed (fifteen tests cover `thread_cancel`).
- The order of checks, including the exceptions (the header right after the
  capability the call acts on, `grant` before the header's limits, the kind
  before the size, the depth checks last of the plain arguments, `no_slot`
  before `no_memory`) is pinned sentence by sentence.
- The three artefacts agree on all twelve errors, the eight rights, the 46
  calls, every limit and every size except the four numbers in F10, and the
  table of constants below is pinned by a test everywhere but F10.
- Removal terminates: the sweep index only grows and every step either removes
  a capability, wakes a thread or spends the slot budget, so I could not build
  a removal that never ends when no other thread acts.

## Findings, by severity

### F1 — `yield` is a call of the Threads group with no rule in the call reference; the model answers `unsupported` (contract error)

Where: `kernel-interface.md`, "System calls", Threads row
(`thread_configure`, `thread_read_regs`, `thread_write_regs`,
`thread_resume`, `thread_suspend`, `thread_cancel`, `yield`) against "Call
reference, one core", "Threads", whose table has no `yield` row;
`model/src/lib.rs`, `modelled()` and `Syscall::Other`.

What is wrong: the one-core reference names `thread_read_regs` and
`thread_write_regs` as `unsupported` and says nothing about `yield`. An
author writing the one-core kernel from the call reference implements `yield`
(one core still has a scheduler, and `yield` needs nothing from another
core): `ok`. The oracle answers `unsupported`, so that kernel disagrees with
the oracle on a call that exists in `abi::Call` and in the system-calls table.

How I know: read (`Call::Yield` is in `abi`, it is in `modelled()`'s negative
set, and `Syscall::Other(Call::Yield)` returns `Unsupported`); run
(`calls_outside_the_one_core_model_are_unsupported`). Mutant T15
(`Other` returning `Done`) is the only test of that path.

Suggestion: add a row to the Threads table in the call reference: "`yield` |
(none) | none. The caller gives up the processor; it returns `ok`. With one
thread ready this changes nothing." Otherwise say in that section that
`yield` is `unsupported` in the one-core reference, as `thread_read_regs` is.

### F2 — a frame is not an object in "Object sizes", but the call reference and the model make it one (contract error)

Where: `kernel-interface.md`, "Object sizes", row `frame`: "No object: the
capability slot holds the mapping record"; against "The derivation tree": "An
object lives exactly as long as the capability that `untyped_retype` returned
for it … When the root capability is removed the object is destroyed and its
memory goes back to the untyped it came from"; and against
`model/src/caps.rs`, `create` and `destroy` (`ObjectKind::Frame` gets an
`Object { kind, root, from }`, takes memory from the untyped, and gives it back
when the root capability goes).

What is wrong: the two sentences cannot both be true of a frame. Either the
frame is an object and the table row is wrong (and its size must be stated, at
least the memory it reserves), or it is not an object, in which case
`untyped_retype` to a `frame` does not produce a root capability, the rule
"the object is destroyed … its memory goes back" has no subject for frames, and
the 32-byte slot must hold the mapping record *as well as* object, rights,
badge and the links of the tree — which the next row already spends.

How I know: read. The model takes the object reading (frames are objects with
no per-kind state — `check_objects`, `has_state`), so the oracle cannot tell a
kernel which of the two it is.

Suggestion: decide, then make "Object sizes", the `frame` row and the sentence
about the root capability agree. If a frame is an object, give its size (0
bytes of its own, the mapping record in the slot) and say that the 32-byte slot
holds the mapping record; if it is not, say how its memory returns to the
untyped (`cap_delete` on a frame capability, presumably) and whether
`untyped_retype` "returns" anything for it.

### F3 — a thread's `aspace` and `fault` endpoint are checked and then dropped (undefined)

Where: "Threads", `thread_configure`; `model/src/lib.rs`, `thread_configure`
(the comment marked `CONTRACT-GAP`).

What is wrong: the call takes a capability space, an address space and a fault
endpoint, and the contract fixes only the effect of the capability space (the
`busy` rule mentions "a receive range of the old capability space"). Nothing
says what a thread does when its address space or its fault endpoint is
destroyed — a fault has nowhere to go, and a thread may be bound to an aspace
whose object is gone. The model keeps neither, so the oracle is silent; the
kernel must keep both references and decide. This is the open point raised by
the fourth review and still open.

How I know: read (the model's `Thread` has `cspace: Option<ObjId>` and nothing
else); run (mutant T04 changes the right on the fault endpoint to `manage` and
is killed, so the *check* is pinned but not the *effect*).

Suggestion: settle it before the kernel is written (D-107's rule says a feature
is not deferred): either the thread keeps the two references and a destroyed
object becomes `gone` for every use of the thread (so `thread_resume` is
`busy`), or `thread_configure` copies nothing and the aspace and fault capacity
is a design choice of the layer above.

### F4 — the marks and the task identifier of a message are not modelled, so the oracle cannot check them (undefined)

Where: "Messages", "The receiver gets, with the message and set by the kernel:
the **badge** … the **marks** of the sender's task … and the **task
identifier**, for the log"; `model/src/ipc.rs`, `received()` sets
`Marks::NONE` and `task: 0`.

What is wrong: the model documents this as out of scope, which is honest, but
the consequence is that a kernel which stamps nothing, or stamps the wrong
marks, passes every test of the oracle. The one place where a kernel could get
the marks wrong invisibly (the whole of `task_mark` and sticky marks) is
therefore outside the oracle.

How I know: read.

Suggestion: state in the call reference that the one-core reference stamps
marks 0 and task 0 (or a fixed value), so that the oracle's silence is the
contract's answer rather than a hole; or add the marks to the model's `Received`
from a per-thread field the tests can set.

### F5 — the start-up state of the oracle is private to the model (undefined)

Where: "Start-up information" ("the others start at slot 16 and the start-up
page gives the slot of each one"; "every `untyped`, ordinary and device"; "its
size is fixed by the boot image") against `model/src/lib.rs`, `boot()` and
`BOOT_UNTYPED_BYTES = 4 GiB`, `BOOT_DEVICE_BYTES = 1 MiB`.

What is wrong: the oracle's first process has one segment of 128 slots, the
ordinary untyped in slot 16 and the device untyped in slot 17, and nothing
else. The tests of `calls.rs` then use slots 20-22, 30-41, 50, 100 and 128-… as
free. A kernel built from the contract puts "every `untyped`" at "the others
start at slot 16" and the start-up page gives each slot: with three untypeds,
slots 16, 17 and 18 are taken, and the oracle's tests that write to slot 18, 20
or 21 would meet a live capability. The contract also fixes neither the size
nor the number of the start-up untypeds, which the oracle does (4 GiB and
1 MiB, and `start_up_untypeds_have_the_sizes_that_the_model_states` converts
the whole of each).

How I know: read; run (`start_up_untypeds_have_the_sizes_that_the_model_states`
pins both sizes, and `boot_state_is_deterministic_and_holds_the_start_up_slots`
pins slots 1-5, 16 and "slot 18 is `invalid`").

Suggestion: add to `abi/` a description of the boot image the oracle assumes
(kind, slot, size of the start-up capabilities, and the size of the start-up
space), and say in "Start-up information" that the one-core reference is tested
against that image. Otherwise the real kernel's start-up state has to be
invented to match the oracle, and the first test that writes to slot 20 will
fail for a reason the contract does not explain.

### F6 — the per-object state of a `cspace` and the links of a 32-byte slot have no home in the contract, and a kernel cannot fit the model's (undefined)

Where: "Object sizes", rows `Capability slot` ("32 bytes (object, rights,
badge, links of the derivation tree)") and `cspace` ("32 bytes per slot, grown
by supplying memory, plus the directory (8 bytes per 128 slots of the
maximum)"); `model/src/lib.rs`, `Cap` and `CSpace`.

What is wrong: two things a kernel needs are missing. First, a slot must hold
the removal order of "the most recently derived child first, and a capability
only after all its descendants", which needs a last-child link and a next-sibling
link; the model instead keeps `children: Vec<CapId>` per capability, which
cannot be 32 bytes and cannot be one write. Second, the `cspace` object needs
its maximum, its current length and the sweep index of "the dying space keeps
the index where the sweep stands"; "32 bytes per slot plus the directory" names
no room for any of the three. The model has them for free (`CSpace { max,
slots: Vec, sweep: Option<Sweep> }`), so the oracle cannot see the problem.

How I know: read; run (the property suite reaches the deepest tree and the
longest walk with these vectors, so they are exercised, not vacuous).

Suggestion: state the three words of a `cspace` (maximum, length, sweep index)
and the three links of a slot (parent, next sibling, last child), and say
whether the "links of the derivation tree" are those three. That is also what
makes `cap_revoke`'s "most recently derived child first" cheap for the kernel.

### F7 — a wait whose only `manage` capability is gone has no exit, and D-106's answer does not reach it (undefined)

Where: "The kernel has no time limit on a wait; `thread_cancel` is how one is
built (design choice, D-106)"; "Removal ends: a thread whose capability space is
dying gets `gone` from every call except `cap_delete`".

What is wrong: `thread_cancel` needs `manage` on the target. A capability that
carries `manage` can be removed without destroying the thread (a copy under
`cap_revoke`, a capability in a space that is deleted, a parent that is
deleted) — and then no thread can end the target's wait. If the target also
waits on a notify no one can signal, it waits for ever: the kernel has no
timeout, and the contract's answer to "a wait that must end" (D-106) is not
available. The removal path is worse in the same direction: the only holder of
the `manage` capability may be a thread whose own space is dying, and that
thread gets `gone` from every call, `thread_cancel` included.

How I know: read (the model enforces `manage` on `thread_cancel`, and the
`gone` rule applies to the canceller, not the target); suspected as a sequence
— I did not build the exact state in the model.

Suggestion: say that the creator of a thread must keep a `manage` capability
for it outside every space it can delete (the contract already says something
of this shape for memory in D-103: "it keeps the parent, and with it the right
to take everything back"), and note in the Threads section that the loss of
`manage` is the way to lose the ability to cancel.

### F8 — `cap_delete` and `cap_revoke` take a slot through a `cspace` capability without `write` and no test sees it (untested)

Where: "Slots and addresses": "changing a slot (placing, moving out, deleting,
revoking) needs `write`"; `model/src/caps.rs`, `cap_delete`
(`self.through(own, slot, Rights::WRITE)`) and `cap_revoke` (`self.cap(thread,
slot, Rights::WRITE)`); `model/tests/calls.rs`,
`changing_a_slot_through_a_cspace_capability_needs_write` uses a `read`-only
`cspace` capability, so `write` and `derive` are indistinguishable there.

What is wrong: the two calls could require `derive` (or `read`) on the `cspace`
capability instead of `write` and every test would still pass. The model is
right; the tests do not pin it.

How I know: run. Mutants C23 (`through` with `DERIVE` for `cap_delete`) and C24
(`cap` with `DERIVE` for `cap_revoke`) survive all 396 tests; C08, the same two
changes together, survives too.

Suggestion: add to `changing_a_slot_through_a_cspace_capability_needs_write` a
capability holding `read | derive` (no `write`) and expect `Denied` from
`cap_delete` and `cap_revoke` through it.

### F9 — an unknown bit in a rights word must be `invalid` before the subset, and the model cannot express it (untested)

Where: "Capabilities and objects", `cap_derive`: "a rights word with a bit that
names no right is `invalid`, here and in a message, and is judged before the
subset"; `abi/src/lib.rs`, `Rights::from_bits`.

What is wrong: `Syscall::CapDerive` takes a `Rights`, which cannot hold an
unknown bit, so the model never sees one and no test of the model or of `abi`
pins the error code of the call. `abi`'s `rights_reject_unknown_bits` pins
`from_bits(0x100) == None`, which leaves open whether the decoder answers
`invalid` before or after the destination and the subset — exactly the order the
contract spends a sentence on. A kernel that returns `denied` for an unknown
bit passes the oracle.

How I know: read; run (mutant O09 on the depth order is killed, so the order of
the *other* plain arguments is pinned).

Suggestion: either add a raw-rights path to the model (`Syscall::CapDeriveRaw
{ bits: u32, .. }` or a `Rights` constructor that keeps the bits) with two
tests, one for the code and one for the order against the destination, or say
in the contract that the caller's decoder answers and the kernel is not
involved.

### F10 — `task` 256 bytes, `timer` and `irq` 64 bytes and `iospace` "one root table (4 KB)" are numbers of the contract with nothing in `abi/` and no test (untested)

Where: "Object sizes", rows `task`, `endpoint`, `notify`, `reply`, `timer`,
`irq`, `aspace`, `iospace`; `abi/src/lib.rs`, which has `ENDPOINT_BYTES`,
`REPLY_BYTES`, `NOTIFY_BYTES`, `SCHED_BYTES`, `THREAD_BYTES`, `ASPACE_BYTES`
and nothing for `task`, `timer`, `irq` or `iospace`.

What is wrong: the values live only in prose. Since `abi/` is "the reference for
values" (Open points) and D-107 says the layout of objects is settled before the
one-core kernel is written, four of the contract's sizes are already not in the
code that is supposed to hold them. The oracle cannot check them either, because
those kinds are `unsupported` in the one-core reference.

How I know: read; run (`numbers_of_the_contract_are_those_of_the_interface` pins every
constant `abi` has, and `abi` has none for these four kinds).

Suggestion: add `TASK_BYTES`, `TIMER_BYTES`, `IRQ_BYTES`, `IOSPACE_BYTES` and
pin them in that test, as `abi` already does for the kinds the model makes.

### F11 — the cost of killing a process counts the two removal budgets twice (minor)

Where: "Removal ends": "The cost is bounded by what the process holds: for a
full space of 2^20 slots, 40,960 calls."

What is wrong: 40,960 is 2^20/32 + 2^20/128 — the two budgets added. The two
budgets are spent in the same call, so a full space goes in 2^20/32 = 32,768
calls: removing a capability also moves the sweep past its slot, and 32 slot
examinations per call is under the 128 allowed.

How I know: run. I measured the model (`cap_delete` on a space whose slots are
all full, 1 to 12 segments): 126 slots take 4 calls, 254 take 8, 766 take 24,
1534 take 48 — always `ceil(slots / 32)`, against `slots/32 + slots/128` in the
contract. As an upper bound 40,960 is still true, so this is accuracy, not a
false rule.

Suggestion: say 32,768, or "at most 40,960" if the sum is meant as a
deliberately loose bound.

### F12 — a call that never returns hangs the suite instead of failing it (minor)

Where: `model/tests/calls.rs`, `calls_to_delete_a_space` and
`three_layers_of_spaces_create_spaces_and_hand_memory_down` (loops
`while k.go(..) != DONE`); `model/src/caps.rs`, `next_removed`'s
`assert!(walk <= 2 * LONGEST_WALK)`.

What is wrong: the oracle's way of reporting "this call does not terminate" is
a test binary that never ends. Four of my mutants (D01, D24, D25, D26 — a
`cap_revoke` that removes its own capability, a `cap_delete` that refuses a
dying object, a `cap_revoke` that marks, a sweep that restarts) did exactly
that: `cargo test` ran for 60 s and had to be killed, and one of them printed a
failure first and then hung. A kernel that loops in `cap_delete` would show up
as a CI job that times out, not as a named failing test. The walk guard is an
assert inside `apply`, so a bad state panics instead of being reported by
`check`.

How I know: run (see the four rows of the mutation log).

Suggestion: bound the loops (`for _ in 0..1024`) and assert `again` more than
that many times is a failure; and let `next_removed` return a `Check`-style
error instead of asserting, so that `Model::check` names the state.

### F13 — `thread_cancel`'s own result is not stated, and a cancel that cancels and one that finds nothing look the same (minor)

Where: "Threads", the `thread_cancel` row: "`manage`. If the thread waits …
its call returns `cancelled`…"; the row has no Result column, unlike
`cspace_grow` and `cap_inspect`.

What is wrong: "its call" is the waiting thread's call; an author could read it
as the canceller's. The model returns `Output::Done` to the canceller in both
cases, so a caller cannot tell "I cancelled it" from "it was not waiting" — by
design ("nothing is remembered"), but the contract does not say the canceller
learns nothing.

How I know: read; run (mutant T09 on "changes nothing" is killed, so the model's
silence is pinned, not its return value).

Suggestion: add "Result: none" to that row and the sentence "the canceller
learns nothing: a thread that was not waiting and one that was cancelled answer
`ok` alike; the target's own call answers `cancelled`."

## Rules where two honest authors would write different behaviour

Each row: the two readings, then the one the model took, then how sure I am
that the contract leaves it open.

| # | Rule (section) | Reading A | Reading B | The model | Sure? |
|---|---|---|---|---|---|
| 1 | `thread_cancel`'s result ("Threads") | `ok`, the canceller learns nothing | `cancelled` to the canceller when it did cancel | A | read: the row has no result and does not say |
| 2 | `thread_cancel` of a caller whose message lists capabilities ("Threads", "Transfer") | nothing moves: the transfers happen at delivery | the listed capabilities move to the range at the moment of the cancel | A | read: silent; the model's test asserts A |
| 3 | `thread_cancel` of a receiver: when does its reply object become idle ("Threads") | at the cancel, so another thread may `recv` with it at once | when the target next runs | A | read: "becomes idle" has no time |
| 4 | `thread_cancel` of a thread whose wait has already been answered by a notification, while it is suspended ("Threads") | it keeps the word | the cancel wins | A (the contract says A for "a wait that is already over") | read: stated, but only for a thread "that has not run since" |
| 5 | `thread_cancel` of a thread in a dying capability space ("Threads", "Removal ends") | allowed: only the *caller*'s dying space makes a call `gone` | `gone`: the target's dying space taints the call | A | read: the sentence names the caller's own space only |
| 6 | a cancel and a pending word of the bound notify of the endpoint the target waits on ("Notifications") | the word stays pending, as for any other removal of a receiver | the word is consumed by the cancel | A | read: silent |
| 7 | a dead destination slot ("Slots and addresses") | `no_slot`: a dead slot is not empty | `invalid`: nothing can be placed in it, so it is not a slot | A (`vacant` returns `NoSlot` for `Dead`) | read: both sentences are in the file |
| 8 | "an object is dying from the first step of a removal that **reaches** its root capability" ("Removal ends") | "reaches" = the walk of a step visits the root capability, even if that step returns `again` on the slot budget | "reaches" = the step removes the root capability | A (the walk marks every root capability it visits) | read: "even when that step only removes a copy" hints at A |
| 9 | "the depth checks come last" ("Order of checks") | last of step 3, so before `no_slot` and `no_memory` | after the state of step 4 | A | read: the sentence is inside step 3, but "last" is easy to read as the whole list |
| 10 | a step that only moves the sweep spends one of the 32 ("Derivation tree") | yes: 32 steps, one walk each, whatever it did | no: it costs only the 128-slot budget, so up to 128 slots may move without a step | A (`remove` decrements `steps` once per walk) | read: "a step may end on the slot budget alone" implies A, but not plainly |
| 11 | the reply-object wake of a step ("Removal ends") | not counted in the 32, and not counted in the 128 either | it is a wake of the step, so the step is spent | A | read: "not counted in the 32" says nothing about the 128 |
| 12 | `cap_derive` on a source without a badge, asking for badge 0 ("Capabilities and objects") | the new capability has no badge, and a later derive may add one | the same, but the model cannot tell "asked for 0" from "no badge asked" | A | read: "Badge 0 means no badge" is stated; the model writes 0 either way |
| 13 | `thread_configure` binding a thread to a *dying* capability space ("Threads") | allowed: `busy` speaks of suspended and waiting only, and the space still exists | `gone`: the object is dying, so any use of it is `gone` | B | read: the two sentences do not meet |
| 14 | `cspace_grow` on a space whose maximum is reached ("Capabilities and objects") | `no_slot` | `invalid`, the maximum being a bad argument | A | read: the Errors table gives `no_slot` both meanings |
| 15 | `untyped_retype` of a kind not made, from a device untyped, with a bad size ("Order of checks") | `invalid` (the device rule comes first) | `unsupported` (the kind comes first) | A | read: the contract states it ("after the rule on device memory"), and it is the only place where two step-3 checks are ordered — easy to miss |
| 16 | `cap_revoke` on the root capability of a space ("Removal ends") | does not sweep: only what was derived from the root | sweeps, because the D-103 paragraph counts the edge from the root of a space to what the space holds | A | read: stated, but the "Why" of D-103 walks the other edge, which is why the 191 bound is conservative |
| 17 | the sweep's slot count when the budget runs out at a slot ("Derivation tree") | the slot is examined again next call, so a call can *look at* 129 slots | the call has examined 128 and must stop before looking | A (counts a movement, not a look) | read: "counts as examined when the sweep moves past it" is close to A |
| 18 | "A call makes at most 32 walks, so it wakes at most 64 threads" ("Removal ends") | 32 walks × 2 wakes | 32 walks, each of which may pass several root capabilities (the model wakes one reply thread per walk) | A, because a walk meets at most one reply object | read: the argument holds only with the "one reply object per walk" clause, which the contract gives |

## Constants, the three artefacts

"Contract" is the number as the contract words it; "`abi`" is the constant;
"Model" is how the model uses it; "Pinned" says what fails if the number
changes.

| Constant | Contract | `abi/` | Model | Pinned by |
|---|---|---|---|---|
| Errors | 12 codes, `ok`…`cancelled`, in this order | `Error` 0…11, `Cancelled = 11` | same | `numbers_of_the_errors_are_those_of_the_interface`, `error_codes_are_stable` |
| Rights | 8, in order read, write, exec, send, recv, grant, derive, manage | bits 0…7, `ALL = 0xff` | same | `bits_of_the_rights_are_those_of_the_interface`, `rights_reject_unknown_bits` |
| Calls | "about 46", ten groups | `Call`, 46 variants, `TraceEmit = 44`, `ThreadCancel = 45` | 19 modelled, the rest `unsupported` | `thread_cancel_comes_after_the_calls_that_were_there_before`, `numbers_of_the_contract_are_those_of_the_interface` |
| Slot address | 64 bits: low 32 index, high 32 `via`, 0 = none | `SlotAddr(u64)` | same | `slot_address_splits_into_via_and_index`, Kani `slot_address_reads_back` |
| Slot size | 32 bytes | `SLOT_BYTES = 32` | segment = 128 × 32 = 4 KB | the same test |
| cspace segment | 128 slots (4 KB) | `CSPACE_SEGMENT_SLOTS = 128` | `SEGMENT_BYTES = 4096` | same test, `segment_is_aligned_on_4_kb` |
| cspace maximum | 2^20 | `CSPACE_MAX_SLOTS = 1 << 20` | maximum of a new space | same test |
| cspace directory | 8 bytes per 128 slots, rounded up to a power of two | `CSPACE_DIRECTORY_BYTES = 8` | `(segments*8).next_power_of_two()` | `directory_of_one_segment_takes_8_bytes`, `directory_is_aligned_on_its_size` |
| Depth of the tree | 64, start-up at 1 | `TREE_DEPTH = 64` | `fits`, invariant 20 | `derivation_deeper_than_64_is_invalid`, `creation_deeper_than_64_is_invalid` |
| Longest walk | 191 (shorter than 192) | `LONGEST_WALK = 2*64 - 1 + 64 = 191` | `longest_walk`, invariant 24 | `longest_walk_that_the_depth_rule_allows_is_within_the_bound` |
| Removal step | 32 capabilities removed or threads woken | `REMOVAL_STEP = 32` | `remove` | `cap_revoke_removes_32_capabilities_then_returns_again`, `waking_a_thread_counts_as_one_step_of_removal` |
| Removal slots | 128 slots examined | `REMOVAL_SLOTS = 128` | `swept` | `removal_examines_at_most_128_slots_of_dying_spaces_per_call` |
| Removal cost of a full space | 40,960 calls | — | 32,768 measured | nothing (F11) |
| Message words | 6 in registers, 64 in all | `REG_WORDS = 6`, `MAX_WORDS = 64` | `Message::check` | `message_has_at_most_64_words_and_4_capabilities`, `fast_path_is_registers_without_capabilities` |
| Capabilities per message | 4 | `MAX_CAPS = 4` | `Message::check`, `window` | `receive_range_has_at_most_4_slots` |
| Header | label 32 bits, words, caps, flags | label 0-31, words 32-38, caps 39-41, flags 42-63 | `Header::new` | `header_round_trips_at_the_limits`, Kani `header_new_refuses_or_reads_back` |
| Header flags | `caps_dropped`, `notification` | 1 << 0, 1 << 1 | `deliver`, `notification()` | `header_with_a_flag_set_by_the_sender_is_invalid`, `send_returns_the_dropped_flag_at_once` |
| Marks | bit 0 private, bit 1 untrusted, others reserved | `Marks`, `KNOWN = 0b11` | always none (F4) | `marks_reject_reserved_bits`, `marks_only_add` |
| Start-up slots | 1 cspace, 2 aspace, 3 thread, 4 sched, 5 debug, others from 16 | `START_SLOT_* = 1,2,3,4,5,16` | `boot()` at 16 and 17 | `numbers_of_the_contract_are_those_of_the_interface`, `boot_state_is_deterministic_and_holds_the_start_up_slots` |
| Start-up untypeds | the boot image decides | — | 4 GiB, 1 MiB | `start_up_untypeds_have_the_sizes_that_the_model_states` (F5) |
| Object size: endpoint, notify, reply | 64 bytes | 64, 64, 64 | memory taken | `endpoint_reply_and_notify_take_64_bytes` |
| Object size: timer, irq | 64 bytes | — | not made | nothing (F10) |
| Object size: sched | 128 bytes | `SCHED_BYTES = 128` | memory taken | `sched_takes_128_bytes`, `sched_is_aligned_on_128_bytes` |
| Object size: task | 256 bytes | — | not made | nothing (F10) |
| Object size: thread | 1 KB (+ vector state) | `THREAD_BYTES = 1024` | memory taken | `thread_takes_1_kb`, `thread_is_aligned_on_1_kb` |
| Object size: aspace | one root table, 4 KB | `ASPACE_BYTES = 4096` | memory taken | the same numbers test |
| Object size: iospace | one root table, 4 KB | — | not made | nothing (F10) |
| Object size: frame | "no object" | none | an object (F2) | `frame_takes_a_page_size_and_a_number_of_pages` |
| Object sizes: cspace | 32 bytes per slot + directory | `SLOT_BYTES`, `CSPACE_DIRECTORY_BYTES` | both | `directory_of_one_segment_takes_8_bytes` |
| Smallest untyped, page | 4 KB; frames of 4 KB, 2 MB, 1 GB | `PageSize::bytes` | `PAGE`, `footprint` | `child_untyped_is_a_power_of_two_of_at_least_4_kb`, `frame_of_1_gb_pages_is_aligned_on_1_gb` |
| Watermark granularity | none stated | — | 8 bytes (invariant 18) | `watermark_that_is_not_a_multiple_of_8_bytes_is_reported` |
| Start-up page | versioned, entries (kind, offset, length) | `StartHeader`, `StartEntry` (24 bytes, with `reserved`), `StartKind` 0…8, `START_MAGIC` | not modelled | `layouts_are_fixed` |
| Object kinds | 16 built + `vcpu` reserved | 16, `Untyped` 0 … `Debug` 15 | 9 made | `kinds_of_the_groups_not_yet_specified_are_unsupported` |

Nothing in the contract's other sections contradicts the call reference that I
could find, and the system-calls count of 46 matches `abi`'s 46 variants exactly
(ten groups: 6, 4, 8, 7, 4, 2, 5, 5, 3, 2). The one contradiction across
sections is F2 (a frame is an object in the call reference and not in "Object
sizes").

## The mutation run

Copy of the repository in `/tmp/mut/repo`, each mutant applied alone to the
pristine sources, `cargo test -p dodos-model --lib --test calls` (396 tests: 104 in
`check/tests.rs`, 292 in `calls.rs`; the property suite left out as it is random
and 73 s per run), 60 s timeout per run. 142 mutants: 133 killed by a failing test, 4 killed by non-termination
(the run times out; the sentence is broken, the suite hangs), 5 survivors.

Survivors and what is missing:

| Mutant | Sentence | Why it survives |
|---|---|---|
| C23 | "deleting a slot through a `cspace` capability needs `write`" | the only negative test of that right uses a `read`-only capability, so `write` and `derive` are indistinguishable (F8) |
| C24 | "revoking a slot through a `cspace` capability needs `write`" | same (F8) |
| C08 | both of C23 and C24 together | same (F8) |
| C14 | "memory is taken at an aligned watermark" | behaviour-preserving: `(w + a - 1) / a * a` is `checked_next_multiple_of(a)` for every watermark the model can reach; equivalent mutant, not a gap |
| X09 | "the address of an empty range is not looked at" | my mutant was a no-op (the model clears the address before the check); the replacement X17, which refuses when the address is not 0, is killed by `address_of_an_empty_receive_range_is_not_looked_at` — the sentence is pinned |

The four that hang (D01, D24, D25, D26) all break removal termination; two of
them also print a failure before hanging. This is F12.

The mutants are aimed at sentences, not at lines: 13 for "Slots and addresses",
27 for "The derivation tree" and "Removal ends", 11 for "Order of checks", 23 for
"Capabilities and objects", 16 for "Threads", 13 for "IPC", 12 for
"Notifications", 17 for "Transfer of capabilities", 10 for the invariants of
`check`.

| # | Sentence of the call reference broken | Result | First test that failed |
|---|---|---|---|
| 1 | C01 cap_derive needs derive on the source | KILLED | cap_derive_checks_the_destination_before_the_rights_asked_for |
| 2 | C02 cap_derive takes only a subset of the rights of the source | KILLED | cap_derive_cannot_add_rights |
| 3 | C03 cap_derive accepts a badge only on an endpoint or a notify | KILLED | badge_is_accepted_only_on_an_endpoint_or_a_notify |
| 4 | C04 cap_derive refuses another badge as denied | KILLED | badged_capability_keeps_its_badge_and_refuses_another |
| 5 | C05 cap_derive: a capability that already has a badge keeps it | KILLED | badged_capability_keeps_its_badge_and_refuses_another |
| 6 | C06 cap_move needs no right on the capability itself | KILLED | cap_move_keeps_rights_badge_and_place_in_the_tree |
| 7 | C07 cap_inspect needs no right on the capability itself | KILLED | changing_a_slot_through_a_cspace_capability_needs_write |
| 8 | C08 cap_delete and cap_revoke need no right on the capability | SURVIVED | — |
| 9 | C09 untyped_retype needs write on the untyped | KILLED | new_capability_has_every_right |
| 10 | C10 untyped_retype: a child untyped is a power of two of at least 4 KB | KILLED | child_untyped_is_a_power_of_two_of_at_least_4_kb |
| 11 | C11 untyped_retype: a frame takes a number of pages, at least one | KILLED | frame_of_1_gb_pages_is_aligned_on_1_gb |
| 12 | C12 untyped_retype: a cspace takes at most 2^20 slots | KILLED | cspace_maximum_is_a_whole_number_of_segments_up_to_2_to_the_20 |
| 13 | C13 untyped_retype: the size argument is 0 for the other kinds | KILLED | size_argument_is_zero_for_the_other_kinds |
| 14 | C14 untyped_retype: memory is taken at an aligned watermark | SURVIVED | — |
| 15 | C15 untyped_retype: device memory becomes only a frame or a child untyped | KILLED | device_memory_becomes_only_a_frame_or_a_child_untyped |
| 16 | C16 untyped_retype: the watermark returns to the start when nothing is live | KILLED | cspace_that_holds_its_own_root_capability_can_be_deleted |
| 17 | C17 untyped_retype: exec only if the untyped capability has exec | KILLED | child_untyped_has_exec_only_if_the_untyped_capability_has_it |
| 18 | C18 untyped_retype: the new capability has every right | KILLED | attached_reply_object_whose_thread_does_not_wait_with_it_is_reported |
| 19 | C20 Object sizes: a child untyped is aligned on its size | KILLED | child_untyped_is_aligned_on_its_size |
| 20 | C21 Object sizes: a frame is aligned on its page size | KILLED | frame_of_1_gb_pages_is_aligned_on_1_gb |
| 21 | C22 Object sizes: a kernel object is aligned on 4 KB when larger | KILLED | kernel_object_larger_than_4_kb_is_aligned_on_4_kb |
| 22 | C23 Slots and addresses: deleting a slot through a cspace needs write | SURVIVED | — |
| 23 | C24 Slots and addresses: revoking through a cspace needs write | SURVIVED | — |
| 24 | D01 Derivation tree: cap_revoke keeps the capability | TIMEOUT | the test binary does not end (see F9) |
| 25 | D02 Derivation tree: cap_delete removes the capability last | KILLED | walk_of_a_removal_is_measured |
| 26 | D03 Derivation tree: an object lives as long as its root capability | KILLED | census_counts_what_the_state_holds |
| 27 | D04 Derivation tree: cap_move empties the slot it left | KILLED | root_capability_of_a_space_held_in_a_space_of_the_same_depth_is_reported |
| 28 | D05 Derivation tree: the tree is at most 64 deep | KILLED | creation_deeper_than_64_is_invalid |
| 29 | D06 Derivation tree: an untyped is placed where the depth is not smaller | KILLED | capability_derived_by_ipc_lands_in_a_space_that_is_not_deeper |
| 30 | D07 Derivation tree: a space root is placed only deeper than the space | KILLED | root_capability_of_a_space_is_placed_only_in_a_space_less_deep |
| 31 | D08 Derivation tree: removal removes at most 32 per call | KILLED | census_counts_what_the_state_holds |
| 32 | D09 Derivation tree: removal examines at most 128 slots per call | KILLED | slot_of_the_root_capability_of_a_dying_space_counts_as_examined |
| 33 | D10 Derivation tree: the sweep of a space starts at slot 1 | KILLED | slot_through_a_capability_for_a_dying_space_is_gone |
| 34 | D11 Derivation tree: a full slot is not counted while its capability is removed | KILLED | deleting_the_first_capability_space_destroys_everything_in_it |
| 35 | D12 Derivation tree: a step may end on the slot budget alone | KILLED | removal_examines_at_most_128_slots_of_dying_spaces_per_call |
| 36 | D13 Derivation tree: the most recently derived child is removed first | KILLED | capability_is_removed_after_its_descendants_the_most_recent_first |
| 37 | D14 Derivation tree: a capability goes only after all its descendants | KILLED | census_counts_what_the_state_holds |
| 38 | D15 Derivation tree: the step that removes the last capability returns success | KILLED | wake_of_the_step_that_marks_a_reply_object_is_not_counted |
| 39 | D16 Removal ends: a capability under cap_delete is dying from the first step | KILLED | copy_under_cap_delete_is_dying_and_its_object_is_not |
| 40 | D17 Removal ends: an object is dying when a removal reaches its root capability | KILLED | caller_of_a_dying_reply_object_is_reported |
| 41 | D18 Removal ends: a thread in a dying space gets gone from every call | KILLED | thread_cancel_by_a_thread_whose_capability_space_is_dying_is_gone |
| 42 | D19 Removal ends: cap_delete on its own slots is the one call left | KILLED | thread_whose_capability_space_is_dying_deletes_its_own_slots_only |
| 43 | D20 Removal ends: a delivery into a dying space drops the capabilities | KILLED | delivery_into_a_dying_capability_space_drops_the_capabilities |
| 44 | D21 Removal ends: the step that marks a reply object wakes its thread | KILLED | caller_is_woken_with_gone_when_a_sweep_destroys_its_reply_object |
| 45 | D22 Removal ends: at most 32 capabilities are removed or threads woken | KILLED | destroying_an_endpoint_wakes_its_callers_32_per_call |
| 46 | D23 Removal ends: destroying an object wakes every thread that waits on it | KILLED | destroying_an_object_wakes_the_threads_that_wait_on_it_with_gone |
| 47 | D24 Removal ends: cap_delete on a dying object acts on the slot | TIMEOUT | the test binary does not end (see F9) |
| 48 | D25 Derivation tree: cap_revoke leaves the capability working (not dying) | TIMEOUT | the test binary does not end (see F9) |
| 49 | D26 Derivation tree: a slot examined once is not examined again | TIMEOUT | the test binary does not end (see F9) |
| 50 | D27 Removal ends: a thread bound to a destroyed space gets gone | KILLED | removal_begun_inside_a_dying_space_is_finished_by_the_sweep |
| 51 | I01 call: the caller of a delivered message waits for the reply | KILLED | census_counts_what_the_state_holds |
| 52 | I02 call: the caller joins the queue of the endpoint, first in first out | KILLED | call_joins_the_queue_and_recv_takes_the_first_caller |
| 53 | I03 recv: a pending notification of the bound notify comes first | KILLED | binding_delivers_nothing_to_a_caller_in_the_queue |
| 54 | I04 recv: busy before anything is received | KILLED | census_counts_what_the_state_holds |
| 55 | I05 reply_recv: a reply object attached to another thread is busy | KILLED | arguments_of_reply_recv_are_checked_in_the_order_of_the_table |
| 56 | I06 reply_recv: an unarmed reply object drops the reply without an error | KILLED | client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped |
| 57 | I07 send never queues: no receiver is would_wait | KILLED | capability_on_the_path_of_a_removal_keeps_working_until_it_is_removed |
| 58 | I08 IPC: the receiver gets the badge of the capability the sender used | KILLED | receiver_gets_the_badge_of_the_capability_the_sender_used |
| 59 | I09 IPC: a reply carries badge 0 | KILLED | reply_of_reply_recv_carries_badge_0 |
| 60 | I10 IPC: when a caller disappears the reply object becomes idle | KILLED | call_is_delivered_to_a_suspended_receiver_which_does_not_run |
| 61 | I11 IPC: threads that wait on the same object are served first in, first out | KILLED | receivers_are_served_first_in_first_out |
| 62 | I12 IPC: the receiver gets the words of the message | KILLED | address_of_an_empty_receive_range_is_not_looked_at |
| 63 | I13 IPC: the reply object is armed with the caller | KILLED | address_of_an_empty_receive_range_is_not_looked_at |
| 64 | K01 Removal ends: the checker sees a removal that never ends | KILLED | capability_held_in_a_capability_space_that_descends_from_it_is_reported |
| 65 | K02 Derivation tree: the checker bounds the walk of a removal | KILLED | walk_of_a_removal_longer_than_192_capabilities_is_reported |
| 66 | K03 The checker names only gone and cancelled as the outcome of a wait | KILLED | outcome_of_a_wait_with_another_error_than_gone_or_cancelled_is_reported |
| 67 | K04 The checker refuses a word with a waiter | KILLED | notify_with_a_waiter_and_a_word_is_reported |
| 68 | K05 The checker refuses a capability space that holds what is deeper | KILLED | root_capability_of_a_space_held_in_a_space_of_the_same_depth_is_reported |
| 69 | K06 The checker refuses a full slot behind the sweep | KILLED | full_slot_behind_the_sweep_is_reported |
| 70 | K07 The checker refuses a new capability in a dying space | KILLED | capability_that_a_dying_space_did_not_hold_when_it_began_to_die_is_reported |
| 71 | K08 The checker refuses a thread queued twice | KILLED | thread_queued_twice_is_reported |
| 72 | K09 The checker refuses a capability whose object does not exist | KILLED | capability_whose_object_does_not_exist_is_reported |
| 73 | K10 The checker refuses a live count that is not the number of objects | KILLED | live_count_that_is_not_the_number_of_live_objects_is_reported |
| 74 | N01 Notifications: signal sets the bits of the badge, or bit 0 | KILLED | binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive |
| 75 | N02 Notifications: wait returns the word and clears it | KILLED | poll_returns_the_word_and_clears_it |
| 76 | N03 Notifications: poll is would_wait when the word is zero | KILLED | binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive |
| 77 | N04 Notifications: wait and poll need recv | KILLED | revoking_the_capability_a_thread_used_does_not_disturb_its_wait |
| 78 | N05 Notifications: signal needs send | KILLED | recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller |
| 79 | N06 Notifications: one notify per endpoint and one endpoint per notify | KILLED | notify_bind_is_busy_when_either_side_is_already_bound |
| 80 | N07 Notifications: endpoint 0 removes the binding and succeeds if there is none | KILLED | binding_to_a_dying_endpoint_is_removed_and_the_word_goes_elsewhere |
| 81 | N08 Notifications: a pending word is delivered at once to a waiting receiver | KILLED | binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive |
| 82 | N09 Notifications: a thread on the notify is served before a receiver of the endpoint | KILLED | outcome_of_a_wait_is_kept_until_the_next_call_of_the_thread |
| 83 | N10 Notifications: signal wakes the first thread, once | KILLED | signal_wakes_one_thread_with_the_whole_word_and_clears_it |
| 84 | N11 Notifications: the word is cleared when a thread is woken | KILLED | binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive |
| 85 | N12 Notifications: the header of a notification has the flag | KILLED | binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive |
| 86 | O01 Order of checks: the kind is judged before the rights | KILLED | kind_is_checked_before_rights |
| 87 | O02 Order of checks: the header is read right after the capability the call acts on | KILLED | grant_is_judged_before_the_limits_of_the_header |
| 88 | O03 Order of checks: the limits of the header before the other capability arguments | KILLED | header_is_read_right_after_the_capability_the_call_acts_on |
| 89 | O04 Order of checks: grant is judged with the number of capabilities the header states | KILLED | grant_is_judged_before_the_limits_of_the_header |
| 90 | O05 Order of checks: a flag bit set by the sender is invalid | KILLED | grant_is_judged_before_the_limits_of_the_header |
| 91 | O06 Order of checks: the plain arguments are judged before the state | KILLED | plain_arguments_are_checked_before_the_state |
| 92 | O07 Order of checks: the kind is judged before the size argument | KILLED | device_memory_refuses_a_kind_that_is_not_made_as_invalid_whatever_the_size |
| 93 | O08 Order of checks: a kind this version does not make is unsupported | KILLED | kinds_of_the_groups_not_yet_specified_are_unsupported |
| 94 | O09 Order of checks: the depth checks come last | KILLED | plain_arguments_of_cap_derive_are_judged_in_the_order_of_the_table |
| 95 | O10 Order of checks: no_slot is reported before no_memory | KILLED | dead_slot_is_not_free |
| 96 | O11 Derivation tree: cap_move checks the source before the destination | KILLED | cap_move_checks_the_source_before_the_destination |
| 97 | S01 Slots and addresses: a slot address is via=index, one level | KILLED | arguments_of_call_are_checked_in_the_order_of_the_table |
| 98 | S02 Slots and addresses: a destination that is slot 0 is invalid | KILLED | cap_derive_checks_the_destination_before_the_rights_asked_for |
| 99 | S03 Slots and addresses: address 0 means no capability (aspace may be 0) | KILLED | capability_space_state_of_an_object_of_another_kind_is_reported |
| 100 | S04 Slots and addresses: using an empty slot returns invalid | KILLED | boot_state_is_deterministic_and_holds_the_start_up_slots |
| 101 | S05 Slots and addresses: using a dead slot returns gone | KILLED | arguments_of_reply_recv_are_checked_in_the_order_of_the_table |
| 102 | S06 Slots and addresses: cap_delete on a dead slot makes it empty | KILLED | cap_delete_on_a_dead_slot_makes_it_empty |
| 103 | S07 Slots and addresses: a dead slot is not free | KILLED | dead_slot_is_not_free |
| 104 | S08 Slots and addresses: reading a slot through a cspace needs read | KILLED | arguments_of_reply_recv_are_checked_in_the_order_of_the_table |
| 105 | S09 Slots and addresses: changing a slot through a cspace needs write | KILLED | capability_arguments_are_checked_before_plain_arguments |
| 106 | S10 Slots and addresses: cspace_grow adds one segment of 128 slots | KILLED | cap_delete_through_a_cspace_capability_leaves_the_slot_empty |
| 107 | S11 Slots and addresses: a cspace grows only from its own untyped | KILLED | capability_space_given_at_start_up_never_grows |
| 108 | S12 Slots and addresses: a destination beyond the table is invalid | KILLED | cap_derive_takes_a_full_source_and_an_empty_destination |
| 109 | S13 Slots and addresses: cspace_grow is no_slot when the maximum is reached | KILLED | cspace_grow_checks_the_untyped_then_the_maximum_then_the_memory |
| 110 | T01 Threads: a new thread is suspended and bound to nothing | KILLED | armed_reply_object_whose_caller_does_not_wait_for_it_is_reported |
| 111 | T02 thread_configure: the thread must be suspended | KILLED | thread_configure_is_busy_unless_the_thread_is_suspended |
| 112 | T03 thread_configure: the thread must not wait | KILLED | thread_configure_is_busy_on_a_thread_that_waits |
| 113 | T04 thread_configure needs send on the fault endpoint | KILLED | thread_configure_needs_send_on_the_fault_endpoint |
| 114 | T05 thread_resume is busy when the thread is bound to nothing | KILLED | thread_resume_is_busy_for_a_thread_that_runs_in_a_destroyed_space |
| 115 | T06 thread_suspend succeeds on a thread bound to no capability space | KILLED | thread_suspend_succeeds_on_a_thread_bound_to_no_capability_space |
| 116 | T07 thread_cancel takes the thread out of its queue | KILLED | client_cancelled_in_a_call_calls_again_and_the_late_answer_is_dropped |
| 117 | T08 thread_cancel: a reply object it was attached to or armed with becomes idle | KILLED | call_is_delivered_to_a_suspended_receiver_which_does_not_run |
| 118 | T09 thread_cancel of a thread that does not wait changes nothing | KILLED | thread_cancel_leaves_the_outcome_of_a_wait_that_is_already_over |
| 119 | T10 thread_cancel: a wait that is already over keeps its result | KILLED | thread_cancel_of_a_thread_that_does_not_wait_changes_nothing_and_is_not_remembered |
| 120 | T11 thread_cancel: a suspended thread that is cancelled stays suspended | KILLED | suspended_thread_that_is_cancelled_stays_suspended_and_finds_cancelled |
| 121 | T12 thread_cancel needs manage on the thread | KILLED | thread_cancel_needs_manage_on_a_thread |
| 122 | T13 Suspension and waiting are independent: suspending cancels nothing | KILLED | call_is_delivered_to_a_suspended_receiver_which_does_not_run |
| 123 | T14 thread_resume: the busy of no space comes before the state asked for | KILLED | thread_resume_is_busy_for_a_thread_that_runs_in_a_destroyed_space |
| 124 | T15 Threads: thread_read_regs and thread_write_regs are unsupported | KILLED | calls_outside_the_one_core_model_are_unsupported |
| 125 | T16 Removal ends: a call outside the model is gone in a dying space | KILLED | thread_whose_capability_space_is_destroyed_gets_gone_from_every_call |
| 126 | X01 Transfer: a message lists up to 4 slot addresses | KILLED | listed_slot_is_checked_fully_before_the_next_one |
| 127 | X02 Transfer: a derived capability is a child of the sender's and keeps its badge | KILLED | derived_capability_is_a_child_of_the_sender_s_and_keeps_its_badge |
| 128 | X03 Transfer: the listed slots are checked when the call is made | KILLED | arguments_of_call_are_checked_in_the_order_of_the_table |
| 129 | X04 Transfer: checked again at delivery, the first slots of the range empty | KILLED | capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped |
| 130 | X05 Transfer: the header the receiver sees has caps_dropped and a count of 0 | KILLED | capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped |
| 131 | X06 Transfer: the flag in a reply header means the capabilities were dropped | KILLED | empty_range_refuses_every_capability_and_the_words_still_arrive |
| 132 | X07 Transfer: a slot listed twice in one message is invalid | KILLED | listed_slot_is_checked_fully_before_the_next_one |
| 133 | X08 Transfer: the depth of a capability to derive is checked with the slot | KILLED | capability_at_depth_64_is_moved_by_ipc |
| 134 | X09 Transfer: an empty range refuses every capability; its address is not looked at | SURVIVED | — |
| 135 | X10 Transfer: a receive range holds at most 4 slots | KILLED | arguments_of_call_are_checked_in_the_order_of_the_table |
| 136 | X11 Transfer: a range with slot 0 or beyond the table is invalid | KILLED | receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid |
| 137 | X12 Transfer: the receive range through a cspace needs write | KILLED | arguments_of_reply_recv_are_checked_in_the_order_of_the_table |
| 138 | X13 Order of checks: reply_recv checks the listed slots before the endpoint | KILLED | reply_recv_checks_the_listed_slots_before_the_endpoint |
| 139 | X14 Order of checks: send checks the listed slots before the state | KILLED | listed_slots_are_checked_when_the_call_is_made_and_nothing_is_sent |
| 140 | X15 Transfer: reply_recv needs send and recv on the reply object | KILLED | grant_is_judged_before_the_limits_of_the_header |
| 141 | X16 Transfer: a message whose slots fail at delivery still delivers the words | KILLED | capabilities_land_in_a_range_of_another_capability_space |
| 142 | X17 Transfer: the address of an empty range is not looked at | KILLED | address_of_an_empty_receive_range_is_not_looked_at |


## Sequences I looked for a bad state in

None of these reaches an inconsistent state in the model; I record what I tried.

- **A capability outliving its parent.** `cap_delete` removes descendants
  before the capability and only the root capability's removal destroys the
  object, so a copy in another space dies with the root. Invariant 21 (the edge
  graph of parent and holder has no cycle) is checked after every call of the
  property suite (100,000 calls at 50 seeds) and never failed.
- **Memory reused while an object still uses it.** The watermark only returns to
  zero when `live == 0`, and `live` counts a capability space once per segment
  (invariant 19). A space's segments go back when the space is destroyed, and a
  space is destroyed only after its slots are empty. No sequence I built got a
  live object and a reset watermark at once.
- **A removal that never ends with no other thread acting.** The sweep index
  only grows and a call either removes a capability, wakes a thread or spends
  the slot budget, so `cap_delete`/`cap_revoke` always finish; I measured a full
  2^20-slot space at 32,768 calls. The one way to keep it from ending is the
  accepted limit of the contract (a competing thread deriving 33 capabilities
  per step), which the repository tests.
- **Unbounded work in one call.** At most 32 walks per call, each bounded by 191
  capabilities and 128 slots. `unlink` is a scan of a vector in the model where
  the contract promises one step (the model says so); `check` is linear in the
  state, which is a test oracle, not a call.
- **A thread that waits for ever with nothing that can wake it.** Every wait in
  the model has a wake path — delivery, `signal`, an answer, the destruction of
  what it waits on, or `thread_cancel` — but `thread_cancel` needs `manage`, and
  the loss of the last `manage` capability (a copy revoked, a space deleted, a
  parent deleted) leaves a waiting thread with no exit and no timeout: F7. The
  case the contract does cover (a killed server's callers wait until the removal
  reaches their reply objects) needs the supervisor to repeat the call, which
  the contract says.

## What I left behind

- `dodos-kernel` is on branch `model` at `4554d26`, `git status` empty (checked
  after the review; the mutation copy is `/tmp/mut/repo`, the probe copy
  `/tmp/probe/repo`, both outside the repository).
- `Docs` is on `main` at `048f20f`, `git status` shows only this report.
- No test binary of mine is still running (`ps` checked).
