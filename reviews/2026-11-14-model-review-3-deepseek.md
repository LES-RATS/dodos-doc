# Model review 3 — the one-core model against the contract, read from the contract alone

Reviewer: deepseek (independent review sub-agent). Date: 14 November 2026.
Repository: `/Users/btw/Documents/repos/dodos-kernel`, branch `model`.
Contract: [`Docs/architecture/kernel-interface.md`](../architecture/kernel-interface.md), above all *Call reference, one core* (D-099, revised D-100, D-101), *Rules*, *Objects*, *System calls*, *Rights*, *Errors*.
Also read: `dodos-kernel/AGENTS.md`, `.agents/skills/dodos-rust/SKILL.md`, `abi/src/lib.rs`, and the model — `model/src/lib.rs`, `caps.rs`, `ipc.rs`, `check.rs`, `check/tests.rs`, `model/tests/calls.rs`, `model/tests/property.rs`.

I did not read `Docs/reviews/`. The review is independent: I read the contract first, wrote down what a kernel author would build from each sentence, then read the model and compared.

## How the review was done

- **Reading.** Every bullet of *Call reference, one core* and every row of its tables was turned into an observable statement (result, error code, order of errors, number of `again`), then located in the model and in a test.
- **Probing.** Where I could not tell from the code alone what the model does, I wrote throwaway probe tests (`probe.rs`, `probe2.rs`, `probe3.rs`) in a **copy** of the repository at `/tmp/rev3/dodos-kernel`, never in the original. Probe outputs are quoted below as `P*`, `Q*`, `R*`.
- **Mutants.** 79 mutants, one per rule, run in four further copies (`/tmp/rev3/w0..w3`), 100 s each, `cargo test -p dodos-model --lib --test calls --test property`. Every mutant that survives is listed in part 4.
- **Original tree.** `git status` in `/Users/btw/Documents/repos/dodos-kernel` was clean before and after; nothing was written, staged, committed or pushed there. The baseline run there is 68 unit tests + 207 `tests/calls.rs` + 4 `tests/property.rs`, all passing.

Headline: I found **no unambiguous deviation from the contract**. Every rule that the contract states plainly is implemented as written and defended by a test. What follows is a list of places where the contract does not settle the answer, where the model answers something the contract does not cover, where a comment cites the contract wrongly, and where no test defends a rule. Two of those places (F1, F2) would make the oracle teach the real kernel the wrong thing.

---

# Part 1 — Findings, by severity

## F1. `untyped_retype` checks the destination before the kind and the size — the contract's table says the opposite order

**Severity: contract error** (contract ambiguity with an observable difference; the model took the less literal reading).
**Where:** [`model/src/caps.rs:189`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:189) — `let place = self.destination(thread, destination)?;` sits above the device rule and `footprint`; the comment on `destination` in [`model/src/lib.rs:594`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:594) classifies it as *"Order of checks, step 2"*.
**What the contract says:** the row is `untyped_retype | untyped, kind, size argument, destination`, and *Order of checks* step 3 says "the plain arguments, in the order of the table (`invalid`)". Step 2 covers "the other **capability** arguments". A destination is a slot address, not a capability; the only capability in it is a `via` capability. Read literally, the destination is the **last** plain argument of `untyped_retype`, so its `invalid` comes after `unsupported` for the kind and after `invalid` for the size.
**The two readings:**

| Call | model | table-order reading |
|---|---|---|
| `untyped_retype(UT, IoPorts, 0, slot 0)` | `invalid` (destination first) | `unsupported` (kind first) |
| `untyped_retype(UT, Timer, 5, slot 0)` | `invalid` | `invalid` (size) — same code, different reason |
| `untyped_retype(UT, IoPorts, 0, via(read-only cspace, 5))` | `denied` (write on the `via` capability) | `unsupported` |

**How I know:** read in the code, and confirmed by run — probe `P1a` `Err(Invalid)`, `P1b` `Err(Denied)`, `P1d` `Err(Unsupported)` (the same call with a good destination).
**Why it is not clear-cut in the model's favour either way:** the model's reading treats the destination as a capability argument because its `via` needs `read`/`write`, and it is consistent with `cap_derive`, whose row says the rights are "checked with the plain arguments, **so after the destination**" — but for `cap_derive` the table already puts the destination before the rights, so that sentence does not establish a general rule. `untyped_retype` is the only call where the two readings part.
**Test that pins it:** `untyped_retype_judges_the_kind_before_the_size` ([`calls.rs:2697`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:2697)) ends with the comment *"All of it after the destination"* and asserts `invalid`; `capability_arguments_are_checked_before_plain_arguments` ([`calls.rs:495`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:495)) kills the opposite mutant.
**Suggestion:** add one sentence to *Order of checks* — "the destination is checked with the capability arguments, before the plain ones" (the model's reading, which I believe is what was meant) or the opposite — and align `caps.rs:189` and the two tests with it. An oracle that disagrees with the kernel on this returns `unsupported` where the kernel returns `invalid`, and the kernel test fails for the wrong reason.

## F2. `thread_read_regs` and `thread_write_regs` cannot be called in the model at all

**Severity: contract error** (the row and the sentence that follows it contradict each other; the model resolves it by skipping the whole call).
**Where:** [`model/src/lib.rs:148`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:148) — `Other(Call)` carries **no arguments** — and [`lib.rs:486`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:486), which returns `unsupported` after a single caller-space check.
**What the contract says:** the *Threads* table has a row for them — arguments "thread, register block", rights "`read`, respectively `write`. The thread must be suspended (`busy`)" — and the sentence after the table says only that *the register block* "is defined by the architecture layer; it is not part of the one-core model". The checks of the row are part of the one-core model.
**What the model does:** `Syscall::Other(Call::ThreadReadRegs)` has no slot and no block, so none of the checks can run; the call is `unsupported` whatever the state.
**How I know:** by run — `P4a` on an empty slot `Err(Unsupported)` (a kernel author's step 1 gives `invalid`), `P4b` after a `cap_revoke` `Err(Unsupported)` (`gone` or `invalid`). And by reading `lib.rs:148`: the variant cannot carry a slot.
**Why it matters:** the oracle cannot test the two calls of the table; worse, an oracle driving the model with `Other(ThreadReadRegs)` silently accepts a kernel that returns `invalid`, `gone` or `busy` for them.
**Suggestion:** either (a) give the two calls typed variants carrying `thread` and the block's slot address so that steps 1–4 run and `unsupported` is returned only for the block itself, or (b) move the two rows out of the one-core table into an architecture-layer table. The contract should also say where `unsupported` sits in *Order of checks* (it does, in step 3 — see F6a).

## F3. `grant` is decided before the header is validated

**Severity: undefined** (both readings are defensible; the model picked one and no test pins it).
**Where:** [`model/src/ipc.rs:83`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:83) `self.held(thread, endpoint, ObjectKind::Endpoint, message.rights())?` — `Message::rights()` ([`ipc.rs:31`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:31)) adds `grant` when `caps` is non-empty — comes before `message.check()` ([`ipc.rs:22`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:22)). Same in `reply_recv` ([`ipc.rs:136`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:136)) and `send` ([`ipc.rs:161`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:161)).
**What the contract says:** step 1 checks the rights of the capability the call acts on (`denied`); step 2 has the exception that "a message header is read right after the capability the call acts on … a header beyond the limits, or with a flag bit set by the sender, is `invalid` before any other capability argument is looked at". `grant` is a right of the acting capability, not another capability argument — so the model's reading is literal. The other reading: whether `grant` is required depends on the *number of capabilities*, which only the header knows, so the header must be read before `grant` can be judged.

| Call | model | header-first reading |
|---|---|---|
| `call(EP with send but no grant, message with 5 caps)` | `denied` | `invalid` (5 > 4) |
| `call(EP with send but no grant, message with a sender flag set and 1 cap)` | `denied` | `invalid` |
| `send(EP with send but no grant, flagged message)` | `denied` | `invalid` |

**How I know:** by run — `P2a`…`P2c` all `Err(Denied)`.
**Test:** none. The nearest, `header_is_read_right_after_the_capability_the_call_acts_on` ([`calls.rs:2611`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:2611)), pins rights-before-header only for a right (`send`) that does not depend on the header.
**Suggestion:** one sentence in step 2 — "`grant` is judged with the header, after it" or "`grant` is judged with the acting capability, before the header" — and a test. I would keep the model's answer and write it down, because it keeps step 1 uniform.

## F4. `recv` returns `busy` when the reply object is not idle, even though a notification is waiting

**Severity: undefined** (small; the model's reading follows *Order of checks*, the other reading follows the word "In order").
**Where:** [`model/src/ipc.rs:110`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:110) — the idle check is made before `self.receive(...)`, so the pending notification is not returned.
**What the contract says:** the `recv` row: "`recv` on the endpoint, `recv` on the reply object, which must be idle (`busy`). **In order:** a pending notification of the bound `notify`; the first caller in the queue; otherwise the thread waits". A reader who takes "In order" as the body of the call returns the notification; a reader who takes `busy` as a check of step 4 (state) returns `busy` first. The model does the second.
**How I know:** by run — `P3a` `Err(Busy)` with the reply object armed and the word pending; `P3b` the word is still there (`Ok(Word(1))`), so nothing is lost and the next `recv`/`poll` gets it.
**Test:** `recv_is_busy_when_the_reply_object_is_armed` / `…_attached` ([`calls.rs:1729`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:1729), `1738`) do not involve a notification; `state_is_checked_after_every_argument` ([`calls.rs:2655`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:2655)) covers the range, not the word.
**Suggestion:** say it in the `recv` row ("the state of the reply object is judged before anything is returned"), and add one test. The model's answer is the one I would keep: `busy` is a check, not a result.

## F5. `untyped_retype` makes only 9 of the 15 kinds; the contract does not say which

**Severity: undefined.**
**Where:** [`model/src/caps.rs:68`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:68) — everything outside `Untyped, Frame, CSpace, ASpace, Thread, Sched, Endpoint, Reply, Notify` is `unsupported`.
**What the contract says:** the *Objects* table lists 15 kinds, and the `untyped_retype` row says the size argument is "0 for the other kinds" — which reads as if every kind can be made. The model refuses `Timer`, `Task`, `Irq`, `Debug`, `IoPorts`, `IoSpace`, `Core` (and `Vcpu`), although `boot()` itself creates a `Debug` object ([`lib.rs:377`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:377)).
**How I know:** by run — `P1d` `retype(UT, Timer, 0, …)` → `Err(Unsupported)`, `P1e` `IoPorts` → `Err(Unsupported)`; by reading the `_` arm.
**Test:** `kinds_outside_the_one_core_model_are_unsupported` ([`calls.rs:1333`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:1333)) covers `Timer, Task, Irq, Debug`; `IoPorts`, `IoSpace`, `Core`, `Vcpu` are untested.
**Suggestion:** the contract should name the kinds `untyped_retype` makes in the one-core model (or say "the kinds of the calls this model covers"). Until it does, a kernel author makes a `Timer` and the oracle says `unsupported`. Note this also changes the watermark and `no_memory` behaviour: a refused kind takes no memory.

## F6. Five `CONTRACT-GAP` markers claim gaps the contract does not have

**Severity: minor** each, but this is the documentation an author of the real kernel reads, and each one teaches that the contract is silent where it is explicit.

| # | Marker | Claim | What the contract actually says |
|---|---|---|---|
| a | [`caps.rs:63`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:63) | "nor place `unsupported` in the order of checks" | Step 3: "a kind that this version does not make is `unsupported` there, after the rule on device memory". |
| b | [`caps.rs:114`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:114) | treats "the depths come last" as a gap | Step 3: "the depth checks (the limit of 64 and the rule on what a space holds) come last". |
| c | [`caps.rs:469`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:469) | "the contract does not say where the sweep starts" | "The sweep of a space starts at slot 1". |
| d | [`caps.rs:515`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:515) | "the contract does not say when a slot counts as examined" | "a slot counts as examined when the sweep moves past it, so a full slot is not counted while its capability is being removed". |
| e | [`lib.rs:385`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:385) | "says 'never `exec` on device memory' of new capabilities only" | "it has `exec` only if the untyped capability has `exec`, and never on device memory (the start-up capabilities for device memory have no `exec`)" — the parenthetical says exactly what `boot()` does. |

**How I know:** read in both files, sentence against sentence.
**Suggestion:** delete the five, or turn them into citations. The markers that do describe real gaps — `ipc.rs:43` (the rest of a notification header), `lib.rs:486`, `lib.rs:655` (what becomes of a thread whose aspace or fault endpoint is destroyed), `caps.rs:58` (the exact size of a thread) — are right and worth keeping.

## F7. `Syscall::Other(Call)` accepts the call numbers the model *does* implement

**Severity: minor.**
**Where:** [`lib.rs:486`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:486).
**What is wrong:** `Syscall::Other(Call::CapInspect)` returns `unsupported` although `cap_inspect` is modelled. An oracle harness that maps call numbers to `Syscall` wrongly therefore passes. Nothing in the type or the check prevents it.
**How I know:** by run — `P4c` `Err(Unsupported)`.
**Suggestion:** `debug_assert!` (or a `check()` invariant) that an `Other` number is one of the calls outside the model, or name the variant `Outside(Call)` and document the excluded set.

## F8. `boot()` omits start-up capabilities the contract lists, and the omission is not marked

**Severity: minor.**
**Where:** [`lib.rs:366`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:366) — the start-up space gets `cspace`, `aspace`, `thread`, `sched`, `debug`, one ordinary untyped, one device untyped.
**What is missing:** the contract's *Start-up information* section (marked *Proposed*) also gives the first process a `core`, `irq`/`ioports`/`iommu` and frames. The one-core model has no `core`/`iospace` calls, so leaving them out is defensible — but, unlike the other omissions, it is not marked `CONTRACT-GAP`, and the section is *Proposed*, so a kernel author cannot tell whether the model is silent or disagreeing.
**How I know:** read.
**Suggestion:** one marker, or one sentence in the contract that the one-core model's start-up space is exactly these six slots and two untypeds.

## F9. The 128-slot removal budget lives in the model, the 32-step one in `abi`

**Severity: minor.**
**Where:** [`caps.rs:18`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:18) `const REMOVAL_SLOTS: usize = 128` against [`abi/src/lib.rs:27`](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:27) `pub const REMOVAL_STEP: usize = 32`.
**What is wrong:** the contract pairs the two numbers in one sentence ("at most 32 capabilities are removed or threads woken and at most 128 slots … examined"). A kernel author takes both from `abi`; here one is invisible to them. A test that asserts the bound must import it from the model.
**How I know:** read.
**Suggestion:** move `REMOVAL_SLOTS` into `abi` beside `REMOVAL_STEP`, and `LONGEST_WALK` beside both.

## F10. A citation to "Revision D-105", which the contract does not carry

**Severity: minor.**
**Where:** [`model/tests/calls.rs:2546`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:2546).
**What is wrong:** the contract's revisions are D-099, D-100, D-101, D-103. Anyone following the citation finds nothing; it looks like a decision that was taken and recorded, and it was not.
**How I know:** read, and a search for `D-10` in the contract.
**Suggestion:** correct the number, or drop it.

## F11. Rules the contract fixes that no test defends

**Severity: untested.** Each item below is a behaviour I could break without a test failing or had to probe to learn. All of them, when probed, were **correct**.

| # | Rule/behaviour | Model | How I know it is untested |
|---|---|---|---|
| a | "a thread bound to a dying space can be resumed" | correct | mutant `resume-of-a-dying-space-is-busy-2` is killed only by the *destroyed* test (`thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed`); no test resumes a thread in a dying space |
| b | a `call` delivered to a **suspended** receiver (suspension keeps the queue place, a message still arrives) | correct (`Q2`: delivered, the server does not run) | no test; `suspended_thread_keeps_its_place_in_its_queue_and_still_gets_its_message` covers the queue side only |
| c | the caller is woken `gone` when its reply object is destroyed by a **space sweep** (not by `cap_delete` on the reply) | correct (`Q1`: woken `Gone`, `cap_inspect` of the reply `Gone`) | only the direct `cap_delete` path is tested |
| d | `reply_recv` with an **idle** reply object that carries a capability to move | correct (`R2`: the capability stays, the receive goes on) | `reply_recv_drops_the_reply_without_an_error_when_the_object_is_not_armed` uses a message without capabilities |
| e | delivery into a **destroyed** receive range (not a dying one) | correct (`R1`/`R4`: words arrive, `caps_dropped`) | only the dying case is tested (`delivery_into_a_dying_capability_space_drops_the_capabilities`) |
| f | a slot address **through a capability for a dying space** is `gone` | correct (`full` sees `dying(object)`, `lib.rs:538-551`) | the dying tests use the caller's *own* space |
| g | `IoPorts`, `IoSpace`, `Core`, `Vcpu` as kinds | `unsupported` (`P1e`) | the test lists only `Timer, Task, Irq, Debug` |
| h | `recv` busy before a pending notification (F4) and `grant` before the header (F3) | see F3, F4 | no test |

## F12. Termination of one removal call rests on a single guard inside the sweep

**Severity: minor** (the bound is proved *and* checked; there is no belt-and-braces cap).
**Where:** [`caps.rs:507`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:507) — `Slot::Full(held) if held != cap => return Some(Some(held))`; the walk itself is `for walk in 1..` ([`caps.rs:465`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:465)), unbounded by construction.
**What is wrong:** a removal ends only because (i) each visited slot either yields work or decrements the 128-slot budget, and (ii) the space's own root capability is skipped and counted as examined. Nothing caps the walk itself. The mutant `sweep-eats-the-self-slot` (drop the `!= cap` guard) makes the **whole suite hang** — it is killed by the 100 s timeout, not by an assertion. The contract's own proof (at most 192) is what makes this safe, and the model does check it: `longest_walk` is bounded by `LONGEST_WALK = 3 * TREE_DEPTH` ([`lib.rs:353`](/Users/btw/Documents/repos/dodos-kernel/model/src/lib.rs:353)) in invariant `24: walk of a removal` ([`check.rs:179`](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:179)), invariant `21: removal that never ends` ([`check.rs:178`](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:178)) checks the sweep state, and `longest_walk_that_the_depth_rule_allows_is_within_the_bound` ([`calls.rs:2883`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:2883)) reaches the worst case 1 + 63 + 62 + 64 = 190.
**Suggestion:** add a defensive counter — if the walk exceeds `LONGEST_WALK`, panic with a message naming the invariant — so a future change fails loudly instead of hanging a test run. Cheap, and it turns a 100 s timeout into a one-line diagnosis.

---

## Pairs of rules that meet in one call

Each pair was checked against the model; **all of them resolve consistently with the contract** unless noted.

| Pair | State | Both readings agree? | Model |
|---|---|---|---|
| dying capability × suspended thread | a suspended thread whose capability is dying calls through it | yes: "any other use of it returns `gone`" wins over "suspension cancels nothing" — suspension is about queues, not rights | `full()` → `Gone` |
| dead slot × dying space | a dead slot inside a dying space | yes: `gone` either way | `space()` → `Gone` first (`lib.rs:504`) |
| empty receive range × dying space | `recv` with an empty range from a thread whose space is dying | **no**: "the address of an empty range is not looked at" vs "a thread whose space is dying gets `gone` from every call" | model takes the second (the `space()` check runs before the empty-range shortcut) — I agree: the thread rule is about the thread, and it wins. Worth one sentence in the contract |
| empty receive range × `via` capability | empty range given through a `cspace` capability without `write` | yes: the address is not looked at, so no right is needed | `window` sets `first = NONE` before resolving (`lib.rs:617`); `address_of_an_empty_receive_range_is_not_looked_at` |
| armed reply object × destroyed caller | the caller is destroyed while the reply is armed | yes: "when a caller disappears while its request is being served, the reply object becomes idle" | `destroy` → `unlink` → `answer`; `reply_object_becomes_idle_when_its_caller_disappears` |
| armed reply object × destroyed server thread | the server thread is destroyed, the reply stays armed | yes: "a caller is not woken when the server thread alone is destroyed" | `caller_is_not_woken_when_the_server_thread_alone_is_destroyed` |
| marking a reply dying × its wake | the reply object is reached by a removal while the caller waits | yes, and the wake is not in the 32 | `wake_of_the_step_that_marks_a_reply_object_is_not_counted`, `waking_a_thread_counts_as_one_step_of_removal` |
| 32 removals × 128 slots, both exhausted | one call that runs out of both | yes: both give `again`; the model returns `Again` from either budget, and finishes when nothing remains | `remove` (`caps.rs:414`) |
| `cap_revoke` on a space root × the sweep | revoking the root of a space | yes: "`cap_revoke` on the root capability of a space does not sweep the space" | `Removal::Descendants` starts at the root's children; `cap_revoke_on_the_root_capability_of_a_space_does_not_sweep_the_space` |
| a space holding its own root × the removal order | the space is destroyed while holding its own root | yes: "it is removed last" | the `held != cap` guard; `cspace_that_holds_its_own_root_capability_can_be_deleted` |
| dying space × `cap_delete` through a `via` into another space | caller in a dying space, target in a live space | yes: the thread rule wins (`gone`) | `thread_whose_capability_space_is_dying_deletes_its_own_slots_only` |
| `thread_resume` of a thread in a dying space × "gone from every call" | the *caller* is in a live space, the target in a dying one | yes: the two rules are about different threads | resume succeeds; untested (F11a) |

One note on the paired budgets: a call never returns `again` when nothing is left, because `remove` checks `steps == 0` *after* asking whether descendants remain (`caps.rs:418-424`). A kernel author who checks the step budget first returns `again` on the last call of a 33-capability revoke. That difference is invisible to a test that only counts `again`s until `ok`, so it is worth a sentence in the contract: "the last step returns `ok`, never `again` with nothing left to do".

---

# Part 2 — The contract, rule by rule

Classes: **C+T** correct and tested · **C−T** correct but untested · **≠** differs from the contract (see finding) · **?** the contract does not define it · **n/a** nothing observable in the model.

## Slots and addresses

| # | Rule | Model | Test (`tests/calls.rs` unless said) | Class |
|---|---|---|---|---|
| 1 | slot address = index in the low 32 bits, `via` in the high, one level of indirection | `lib.rs:522-537` `through`; `abi::SlotAddr` | `via_reaches_a_slot_of_another_capability_space` (321), `via_must_name_a_live_cspace_capability` (331) | C+T |
| 2 | slot 0 is never used; address 0 means "no capability" | `lib.rs:596-604` `destination`, `615-631` `window`; `is_none()` | `slot_zero_is_never_used` (269), `receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid` (2000) | C+T |
| 3 | empty / full / dead; dead → `gone`, empty → `invalid`; `cap_delete` on a dead slot empties it; a dead slot is not free | `lib.rs:538-551` `full`; `caps.rs:552-565` `remove_cap` leaves `Slot::Dead`; `lib.rs:605-613` `vacant` | `empty_or_out_of_range_slot_is_invalid` (277), `slot_of_a_revoked_capability_is_dead_and_using_it_is_gone` (285), `dead_slot_is_not_free` (295), `cap_delete_on_a_dead_slot_makes_it_empty` (305), `cap_delete_on_an_empty_slot_is_invalid` (316) | C+T |
| 4 | no right for the thread's own space; through a `cspace` capability, reading needs `read` and changing needs `write` | `lib.rs:504-520` `space`/`own`, `526-533` (`Access::Read`/`Write`) | `reading_a_slot_through_a_cspace_capability_needs_read` (342), `changing_a_slot_through_a_cspace_capability_needs_write` (355), `thread_needs_no_right_and_no_capability_for_its_own_capability_space` (371), `receive_range_through_a_cspace_capability_needs_write` (1695) | C+T |
| 5 | `cspace` created with a maximum (multiple of 128, ≤ 2^20), a directory of 8 bytes per 128 slots rounded to a power of two, no slot; `cspace_grow` adds 128 slots (4 KB); indexes never change | `caps.rs:215-243` `cspace_grow`; `caps.rs:52-57` (directory); `abi::SLOT_BYTES`, `CSPACE_SEGMENT_SLOTS` | `cspace_is_created_with_no_slot_and_grows_by_one_segment` (385), `growing_a_cspace_does_not_change_slot_indexes` (396), `cspace_maximum_is_a_whole_number_of_segments_up_to_2_to_the_20` (1312), `cspace_directory_is_rounded_up_to_a_power_of_two` (1436) | C+T |
| 6 | a `cspace` grows only from the untyped it was created from; any capability for that untyped; its segments die with it and with that untyped; no object depends on two untypeds | `caps.rs:215-243`; `caps.rs:567-589` `destroy`; `275-299` `take`/`release` | `cspace_grow_takes_only_the_untyped_the_cspace_was_created_from` (426), `capability_space_given_at_start_up_never_grows` (441), `cspace_grow_is_no_memory_when_the_untyped_is_exhausted` (446), `segments_go_back_to_the_untyped_when_the_cspace_is_destroyed` (456), `segments_that_were_never_added_are_not_examined` (2574) | C+T |
| 7 | a destination that is slot 0 or beyond the table is `invalid` | `lib.rs:596-604` | `receive_range_with_slot_0_…` (2000), `arguments_of_call_are_checked_in_the_order_of_the_table` (2320) | C+T |

## The derivation tree

| # | Rule | Model | Test | Class |
|---|---|---|---|---|
| 8 | one parent per capability, except the start-up roots; `untyped_retype` makes a child of the untyped, `cap_derive` a child of the source; no separate copy | `caps.rs:300-357` `create`, `358-386` `new_cap`, `387` `derive` | `new_capability_is_a_child_of_the_untyped_capability` (1391), `object_lives_as_long_as_its_root_capability_wherever_it_is_moved` (638), `derived_capability_is_a_child_of_the_sender_s_and_keeps_its_badge` (1883) | C+T |
| 9 | a capability never outlives its parent; `cap_revoke` removes the descendants and keeps the capability; `cap_delete` removes the descendants then the capability | `caps.rs:414-461` `remove`, `139`/`164` | `cap_revoke_removes_the_descendants_and_keeps_the_capability` (607), `cap_delete_removes_the_descendants_instead_of_handing_them_up` (627), `capability_is_removed_after_its_descendants_the_most_recent_first` (803) | C+T |
| 10 | an object lives exactly as long as its root capability, wherever moved; no reference count; the memory goes back to the untyped | `caps.rs:552-565` `remove_cap`, `567` `destroy`, `289` `release`; `lib.rs:554` `dying` | `object_lives_as_long_as_its_root_capability_wherever_it_is_moved` (638), `segments_go_back_to_the_untyped_…` (456), `watermark_returns_to_zero_only_when_the_last_object_is_destroyed` (1454) | C+T |
| 11 | `cap_move` moves to an empty slot; tree place, rights and badge unchanged | `caps.rs:125-138`, `399` `place` | `cap_move_keeps_rights_badge_and_place_in_the_tree` (574), `cap_move_takes_a_full_source_and_an_empty_destination` (592) | C+T |
| 12 | the tree is at most 64 deep; a start-up capability is depth 1; deeper is `invalid`, checked with the plain arguments | `caps.rs:244-252` `depth`, `253-274` `fits`; `abi::TREE_DEPTH` | `creation_deeper_than_64_is_invalid` (1250), `derivation_deeper_than_64_is_invalid` (1233), `spaces_nest_no_deeper_than_the_tree` (1106) | C+T |
| 13 | a space holds only what is deeper than itself; an untyped whose depth is not smaller; `invalid` with the plain arguments; on every placement (`cap_move`, `cap_derive`, `untyped_retype`, IPC) — for IPC a refusal drops the capabilities | `caps.rs:253-274` `fits` (`Placing`); `caps.rs:82-123`, `125-138`, `178-214`; `ipc.rs:274-305` `listed`, `371-429` `deliver` | `untyped_capability_is_placed_only_in_a_space_that_is_not_deeper` (1007), `…_is_derived_or_created_only_…` (1022), `root_capability_of_a_space_is_placed_only_in_a_space_less_deep` (1048), `copy_of_a_space_capability_is_derived_into_any_space` (1070), `space_is_created_only_in_a_space_less_deep` (1081), `spaces_nested_at_the_same_depth_are_refused` (1091), `capability_of_another_kind_moves_into_any_capability_space` (1036), `capability_moved_by_ipc_into_a_space_that_cannot_hold_it_is_dropped` (1193), `capability_derived_by_ipc_…` (1207), `capability_derived_by_ipc_lands_in_a_space_that_is_not_deeper` (1219), `refused_move_is_invalid_before_no_slot` (1183), `refused_derivation_or_creation_is_invalid_before_no_slot` (2710) | C+T |
| 14 | the walk is at most 192 capabilities (the "Why") | `caps.rs:463-505` `next_removed` counts `longest_walk`; `lib.rs:353`; `check.rs:179` | `longest_walk_that_the_depth_rule_allows_is_within_the_bound` (2883) — reaches 190 | C+T |
| 15 | a space may hold its own root, removed last; the start-up space came from no untyped and never grows | `caps.rs:507-531` `swept` (`held != cap`); `lib.rs:366` `boot` | `cspace_that_holds_its_own_root_capability_can_be_deleted` (988), `capability_space_given_at_start_up_never_grows` (441) | C+T |
| 16 | a derived capability has a subset of its parent's rights; one made by `untyped_retype` gets the rights of its kind | `caps.rs:82-123` (subset), `209-213` (`Rights::ALL` minus `exec` when the untyped lacks it) | `cap_derive_cannot_add_rights` (537), `new_capability_has_every_right` (1357), `new_capability_has_exec_only_if_the_untyped_capability_has_it` (1371) | C+T |
| 17 | removal in bounded steps: 32 removed-or-woken and 128 slots examined, `again` while work remains; segments never added are not examined; the sweep starts at slot 1; a slot counts as examined when the sweep moves past it; a step may end on the slot budget alone; order fixed (most recent child first, a capability after its descendants); well formed between steps | `caps.rs:18`/`415` (budgets), `414-461` `remove`, `463-505` `next_removed`, `507-531` `swept`; `abi::REMOVAL_STEP` | `cap_revoke_removes_32_capabilities_then_returns_again` (653), `cap_revoke_of_32_descendants_is_one_call` (667), `cap_delete_returns_again_while_descendants_remain` (676), `waking_a_thread_counts_as_one_step_of_removal` (855), `removal_examines_at_most_128_slots_of_dying_spaces_per_call` (2564), `slot_examined_once_is_not_examined_again` (2580), `segments_that_were_never_added_are_not_examined` (2574) | C+T (the 128 constant is not in `abi`: F9) |
| 18 | removal ends: a capability under `cap_delete` is dying from the first step and every other use is `gone`; an object is dying from the first step of a removal that reaches its root, even a step that only removes a copy; a capability on the path but not the root keeps working; a thread whose space is dying gets `gone` from every call except `cap_delete` on its own slots (a slot through a capability for a dying space is `gone`); a delivery to a receiving range in a dying or destroyed space drops the capabilities; the step that marks a reply object wakes its one thread with `gone`, not counted in the 32; `cap_delete` on a capability whose object is dying works as on any other | `caps.rs:463-505`, `540-551` `waiter`; `lib.rs:504-514` `space`, `538-551` `full`, `554-557` `dying`; `ipc.rs:371-429` `deliver` | `dying_capability_is_gone_for_every_call_but_cap_delete` (688), `copy_under_cap_delete_is_dying_and_its_object_is_not` (703), `capability_is_not_dying_after_cap_revoke_returns_again` (716), `every_call_on_a_dying_object_is_gone` (736), `object_is_dying_as_soon_as_a_removal_reaches_its_root_capability` (753), `recv_with_a_dying_reply_object_is_gone_and_the_caller_stays_queued` (768), `marking_a_reply_object_as_dying_wakes_the_receiver_attached_to_it` (781), `…_the_caller_it_is_armed_with` (793), `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` (899), `…_deletes_its_own_slots_only` (917), `delivery_into_a_dying_capability_space_drops_the_capabilities` (932), `capability_on_the_path_of_a_removal_keeps_working_until_it_is_removed` (2430), `wake_of_the_step_that_marks_a_reply_object_is_not_counted` (2458) | C+T except three untested branches: the `via`-into-a-dying-space case (F11f) and the destroyed-range case (F11e) |
| 19 | accepted limit: competing derivations during `cap_revoke` | nothing to implement | — | n/a |
| 20 | destroying an object wakes every thread that waits on it with `gone`, the receiver with a reply object and the armed caller included; the caller is not woken when the server thread alone is destroyed; destroying a `cspace` removes its capabilities in index order by the same steps, keeps the sweep index, never examines a slot twice; `cap_revoke` on a space root does not sweep; a thread whose space is destroyed gets `gone` from every call | `caps.rs:414-461` + `540-551`, `ipc.rs:452` `unlink`, `lib.rs:638` `wake`; `lib.rs:516-521` `own` | `destroying_an_object_wakes_the_threads_that_wait_on_it_with_gone` (818), `destroying_a_reply_object_wakes_its_caller_and_its_receiver_with_gone` (839), `destroying_a_cspace_removes_its_capabilities_in_index_order` (886), `destroying_a_cspace_destroys_the_objects_whose_root_it_holds` (948), `thread_whose_capability_space_is_destroyed_gets_gone_from_every_call` (959), `cap_revoke_on_the_root_capability_of_a_space_does_not_sweep_the_space` (2446), `reply_object_becomes_idle_when_its_caller_disappears` (1826), `caller_is_not_woken_when_the_server_thread_alone_is_destroyed` (1838) | C+T |
| 21 | rights are checked when the call is made; a waiting thread is not disturbed by a revocation, only `gone` when the object is destroyed | `lib.rs:559-577` `cap`/`is`; `ipc.rs:452` | `revoking_the_capability_a_thread_used_does_not_disturb_its_wait` (975) | C+T |

## Order of checks

| # | Rule | Model | Test | Class |
|---|---|---|---|---|
| 22 | step 1: the capability the call acts on — slot (`invalid`/`gone`), kind (`invalid`), rights (`denied`) | `lib.rs:538-551` `full`, `559-582` `cap`/`is`/`held` | `capability_arguments_are_checked_in_the_order_of_the_table` (2358), `first_capability_is_checked_before_the_others` (477), `kind_is_checked_before_rights` (487) | C+T |
| 23 | step 2: the other capability arguments in table order; the header read right after the acting capability; a bad header before any other capability argument | `ipc.rs:22-29` `check`, `76-108` `call`, `127-152` `reply_recv`, `274-305` `listed`; `lib.rs:615-631` `window` | `header_is_read_right_after_the_capability_the_call_acts_on` (2611), `header_limits_are_checked_before_the_listed_slots` (2308), `listed_slot_is_checked_fully_before_the_next_one` (2339), `capability_arguments_are_checked_before_plain_arguments` (495) | C+T except F3 (`grant` vs the header) |
| 24 | step 3: the plain arguments in table order; for `untyped_retype` the kind before the size, `unsupported` after the device rule; the depth checks last | `caps.rs:178-214`; `82-123` (depths last); `253-274` `fits` before `vacant` | `arguments_of_call_are_checked_in_the_order_of_the_table` (2320), `plain_arguments_are_checked_before_the_state` (503), `untyped_retype_judges_the_kind_before_the_size` (2697), `size_argument_is_zero_for_the_other_kinds` (1322), `kinds_outside_the_one_core_model_are_unsupported` (1333), `device_memory_becomes_only_a_frame_or_a_child_untyped` (1346), `refused_derivation_or_creation_is_invalid_before_no_slot` (2710) | **≠** on the position of the destination (F1); everything else C+T |
| 25 | step 4: the state — `busy`, `no_slot`, `no_memory`, `would_wait` | `lib.rs:605-613` `vacant`, `caps.rs:275-299` `take` (`no_memory`), `ipc.rs` busy / `IfZero::WouldWait` | `plain_arguments_are_checked_before_the_state` (503), `no_slot_is_reported_before_no_memory` (510), `state_is_checked_after_every_argument` (2655), `cspace_grow_checks_the_untyped_then_the_maximum_then_the_memory` (2672), `send_on_an_idle_reply_object_would_wait_and_moves_nothing` (2507) | C+T |

## Capabilities and objects

| # | Row / rule | Model | Test | Class |
|---|---|---|---|---|
| 26 | `cap_derive`: `derive` on the source; rights a subset (`denied`, after the destination); badge only on an `endpoint` or a `notify` (`invalid`); another badge `denied`, the same accepted; badge 0 means none | `caps.rs:82-123` | `cap_derive_makes_a_capability_with_the_rights_asked_for` (519), `cap_derive_needs_derive_on_the_source` (530), `cap_derive_checks_the_destination_before_the_rights_asked_for` (2297), `badge_is_accepted_only_on_an_endpoint_or_a_notify` (552), `badged_capability_keeps_its_badge_and_refuses_another` (563) | C+T |
| 27 | `cap_move`: no right on the capability | `caps.rs:125-138` | `cap_move_needs_no_right_on_the_capability` (585) | C+T |
| 28 | `cap_delete`: no right; `again` while descendants remain | `caps.rs:139-163` | `cap_delete_and_cap_revoke_need_no_right_on_the_capability` (2420), `cap_delete_returns_again_while_descendants_remain` (676) | C+T |
| 29 | `cap_revoke`: no right; `again` while descendants remain; keeps the capability | `caps.rs:164-168` | `cap_revoke_removes_32_capabilities_then_returns_again` (653), `cap_revoke_takes_a_live_capability` (618) | C+T |
| 30 | `cap_inspect`: no right; kind, rights, badge | `caps.rs:169-177` | `cap_inspect_needs_no_right_on_the_capability` (600) | C+T |
| 31 | `untyped_retype`: `write`; one object; the size argument per kind; a size that does not fit is `invalid`; device memory only a `frame` or a child `untyped` | `caps.rs:178-214`, `41-80` `footprint` | `untyped_retype_needs_write_on_an_untyped` (1268), `untyped_retype_needs_an_empty_destination` (1277), `child_untyped_is_a_power_of_two_of_at_least_4_kb` (1283), `frame_takes_a_page_size_and_a_number_of_pages` (1293), `size_argument_is_zero_for_the_other_kinds` (1322), `device_memory_becomes_only_a_frame_or_a_child_untyped` (1346), `untyped_retype_is_no_memory_when_the_untyped_is_exhausted` (1400) | C+T except the position of the destination (F1) and the set of kinds (F5) |
| 32 | `cspace_grow`: `manage` on the cspace, `write` on the untyped it was created from (`invalid`); `no_slot` at the maximum; new number of slots | `caps.rs:215-243` | `cspace_grow_needs_manage_on_the_cspace_and_write_on_the_untyped` (415), `cspace_grow_is_no_slot_at_the_maximum` (407), `cspace_grow_checks_the_untyped_then_the_maximum_then_the_memory` (2672) | C+T |
| 33 | watermark: moves up while an object lives, returns to the start when the last one is destroyed; aligned on the size of a child untyped, the page size for a frame, the object size or 4 KB | `caps.rs:275-299`; `caps.rs:70-79` | `watermark_returns_to_zero_only_when_the_last_object_is_destroyed` (1454), `memory_is_aligned_on_the_size_of_the_object` (1408), `child_untyped_is_aligned_on_its_size` (1417), `kernel_object_larger_than_4_kb_is_aligned_on_4_kb` (1426), `frame_is_aligned_on_its_page_size` (1445), `large_frame_is_aligned_on_its_page_size` (2517), `segment_is_aligned_on_4_kb` (2686) | C+T |
| 34 | a new capability has every right, `exec` only if the untyped has it, never on device memory | `caps.rs:207-213`; `lib.rs:385-392` | `new_capability_has_every_right` (1357), `new_capability_has_exec_only_if_the_untyped_capability_has_it` (1371), `new_capability_never_has_exec_on_device_memory` (1379) | C+T |
| 35 | the kernel clears kernel objects, not frames | no representation of object contents in the model | — | n/a |
| 36 | a new thread is suspended and bound to nothing | `caps.rs:300-357` (Thread), `lib.rs:396` | `new_thread_is_suspended` (1468) | C+T |
| 37 | `thread_configure`: `manage` on the thread, cspace, aspace, `send` on the fault endpoint; 0 allowed for aspace and fault; suspended and not waiting (`busy`) | `lib.rs:644-676` | `thread_configure_binds_the_capability_space` (1484), `…_needs_manage_…` (1496), `…_needs_send_on_the_fault_endpoint` (1510), `…_checks_the_kind_of_each_capability` (1522), `…_is_busy_unless_the_thread_is_suspended` (1534), `…_is_busy_on_a_thread_that_waits` (2381), `…_binds_a_suspended_thread_to_another_capability_space` (2395) | C+T |
| 38 | `thread_resume`/`thread_suspend`: `manage`; succeed in the state asked for; resume `busy` for no capability space or a destroyed one; a dying space can be resumed | `lib.rs:678-691` | `thread_resume_and_suspend_succeed_in_the_state_asked_for` (1545), `thread_resume_and_suspend_need_manage_on_a_thread` (1560), `thread_resume_is_busy_when_the_thread_is_bound_to_no_capability_space` (1475), `…_when_the_capability_space_of_the_thread_is_destroyed` (2408), `thread_that_suspends_itself_stops_running` (1571) | C+T except "a dying space can be resumed" (F11a) |
| 39 | `thread_read_regs`/`thread_write_regs`: `read`/`write`; `busy` unless suspended | `lib.rs:486` — `unsupported` | `calls_outside_the_one_core_model_are_unsupported` (1593) | **≠** (F2) |
| 40 | suspension and waiting are independent; a waiting thread leaves its queue only when it or its object is destroyed | `lib.rs:687-691`; `ipc.rs:306-471` | `suspended_thread_keeps_its_place_in_its_queue_and_still_gets_its_message` (1578), `outcome_of_a_wait_is_kept_until_the_next_call_of_the_thread` (2284) | C+T |

## IPC

| # | Row / rule | Model | Test | Class |
|---|---|---|---|---|
| 41 | thread states; reply object idle / attached / armed | `lib.rs:240-…` `Wait`; `ipc.rs` `ReplyState`; `check.rs:266` `check_waits` | invariants after every call (`property.rs:560`); the `Busy` tests below | C+T |
| 42 | `call`: `send`, `grant` when the message lists capabilities; delivered at once to a waiting receiver and its reply armed; otherwise queued FIFO | `ipc.rs:76-108` | `call_joins_the_queue_and_recv_takes_the_first_caller` (1608), `call_is_delivered_at_once_to_a_thread_that_waits_to_receive` (1620), `call_needs_send_on_an_endpoint` (1663), `message_with_capabilities_needs_grant` (1910) | C+T (F3 is about the order) |
| 43 | `recv`: `recv` on the endpoint and on the reply object, which must be idle (`busy`); a pending notification first, then the first caller, else wait with the reply attached | `ipc.rs:110-125`, `306-328` `receive` | `recv_needs_recv_on_the_endpoint_and_on_the_reply_object` (1718), `recv_is_busy_when_the_reply_object_is_armed` (1729), `…_attached` (1738), `recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller` (2143) | C+T except the busy-vs-word order (F4) |
| 44 | `reply_recv`: `send` on the reply object, then as `recv`; armed or idle (attached is `busy`); an unarmed reply is dropped without an error and the receive goes on | `ipc.rs:127-152` | `reply_recv_answers_the_caller_then_receives` (1747), `reply_recv_drops_the_reply_without_an_error_when_the_object_is_not_armed` (1760), `reply_recv_needs_send_and_recv_…` (1769), `reply_recv_returns_a_pending_notification_of_the_bound_notify` (2158), `reply_recv_transfers_capabilities_both_ways_and_is_not_told_of_a_drop` (2471) | C+T except F11d |
| 45 | `send`: `send`, `grant` when the message lists capabilities; on an endpoint delivered only to a waiting receiver, else `would_wait`, nothing queued; on a reply object answers and makes it idle, `would_wait` if not armed | `ipc.rs:154-185`, `352-370` `answer` | `send_on_a_reply_object_answers_the_caller_with_badge_0` (1645), `send_on_an_endpoint_is_delivered_to_a_thread_that_waits_to_receive` (1782), `send_never_queues` (1798), `send_does_not_reach_a_caller_in_the_queue` (1806), `send_needs_send_on_an_endpoint_or_a_reply_object` (1815), `send_on_an_idle_reply_object_would_wait_and_moves_nothing` (2507) | C+T |
| 46 | `send` on a reply object is the way to answer without receiving; `send` never queues; threads that wait on the same object are served FIFO | `ipc.rs:154-185`, `440-451` `take_caller` | `send_on_a_reply_object_answers_the_caller_with_badge_0` (1645), `send_never_queues` (1798), `signal_wakes_one_thread_…` (2112), `destroying_an_object_wakes_its_waiters_first_in_first_out` (818) | C+T |
| 47 | the receiver gets the header, the words and the badge; a reply carries badge 0 | `ipc.rs:371-429` `deliver`, `64-74` `Parcel` | `receiver_gets_the_badge_of_the_capability_the_sender_used` (1630), `send_on_a_reply_object_answers_the_caller_with_badge_0` (1645), `moved_capability_leaves_the_sender_for_the_first_slot_of_the_range` (1873) | C+T; the marks and the task identifier belong to tasks (*Messages*, *Proposed*) and are absent, which I read as correct for one core |
| 48 | when a caller disappears while its request is served, the reply object becomes idle | `ipc.rs:352-370`, `caps.rs:567-589` | `reply_object_becomes_idle_when_its_caller_disappears` (1826), `destroyed_thread_leaves_its_queue` (1854) | C+T |

## Transfer of capabilities

| # | Rule | Model | Test | Class |
|---|---|---|---|---|
| 49 | up to 4 slot addresses, each move or derive with rights; a derived capability is a child of the sender's and keeps its badge | `ipc.rs:274-305` `listed`, `371-429`; `caps.rs:387` `derive` | `derived_capability_is_a_child_of_the_sender_s_and_keeps_its_badge` (1883), `slot_listed_twice_is_invalid` (2044) | C+T |
| 50 | checked when the call is made: each listed slot, `derive` on each derived capability, `grant`; a failure returns an error and sends nothing | `ipc.rs:76-108`, `127-152`, `274-305` | `listed_slots_are_checked_when_the_call_is_made_and_nothing_is_sent` (1923), `message_with_capabilities_needs_grant` (1910), `moving_a_capability_through_a_cspace_capability_needs_write` (1947) | C+T |
| 51 | checked again at delivery: the same checks, the first slots of the range empty, one per capability; if not, nothing moves, the words still arrive, `caps_dropped`, count 0 | `ipc.rs:371-429` `deliver` | `transfer_is_all_or_nothing` (1978), `transfer_is_dropped_when_the_range_is_shorter_than_the_list` (1990), `transfer_is_dropped_when_a_listed_capability_no_longer_exists_at_delivery` (2012), `transfer_is_dropped_when_the_listed_slot_fails_a_check_at_delivery` (2068), `delivery_transfers_what_the_listed_slot_holds_then` (2057), `empty_range_refuses_every_capability_and_the_words_still_arrive` (1957) | C+T |
| 52 | the sender learns it: `send` returns the flag at once, `call` sets it in the reply header; a server answering with `reply_recv` is not told | `ipc.rs:154-185` (flag), `371-429`, `127-152` | `send_returns_the_dropped_flag_at_once` (1968), `reply_whose_capabilities_are_dropped_tells_both_sides` (2033), `reply_header_has_the_dropped_flag_of_the_request_with_the_capabilities_of_the_reply` (2497) | C+T |
| 53 | a slot listed twice is `invalid`; that, and the depth of a derived capability, are checked with the slot, before the next listed slot | `ipc.rs:274-305` | `slot_listed_twice_is_invalid` (2044), `listed_slot_is_checked_fully_before_the_next_one` (2339) | C+T |
| 54 | the receive range: first slot and count (at most 4); an empty range refuses every capability and its address is not looked at; slot 0 or beyond is `invalid` when the call is made; emptiness only at delivery | `lib.rs:615-631` `window` | `receive_range_has_at_most_4_slots` (1688), `address_of_an_empty_receive_range_is_not_looked_at` (1707), `receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid` (2000), `arguments_of_call_are_checked_in_the_order_of_the_table` (2320) | C+T |

## Notifications

| # | Row / rule | Model | Test | Class |
|---|---|---|---|---|
| 55 | `signal`: `send`; sets the bits of the badge, or bit 0; wakes the first waiter with the whole word and clears it | `ipc.rs:186-197`, `198-217` `hand_over` | `signal_sets_bit_0_or_the_bits_of_the_badge` (2085), `signal_wakes_one_thread_with_the_whole_word_and_clears_it` (2112), `signal_needs_send_and_wait_and_poll_need_recv` (2125) | C+T |
| 56 | `wait`: `recv`; returns the word and clears it, or waits if zero | `ipc.rs:218-232` | `wait_returns_the_word_and_clears_it` (2095), `wait_waits_when_the_word_is_zero_and_poll_would_wait` (2103) | C+T |
| 57 | `poll`: `recv`; as `wait`, `would_wait` if zero | `ipc.rs:218-232` (`IfZero::WouldWait`) | `wait_waits_when_the_word_is_zero_and_poll_would_wait` (2103) | C+T |
| 58 | `notify_bind`: `recv` on the notify, `manage` on the endpoint; endpoint 0 removes the binding and succeeds if there is none; one notify per endpoint and one endpoint per notify (`busy`, also for the pair already bound); a pending word with a waiting receiver is delivered at once | `ipc.rs:233-273` | `notify_bind_needs_recv_on_the_notify_and_manage_on_the_endpoint` (2202), `notify_bind_is_busy_when_either_side_is_already_bound` (2213), `notify_bind_with_endpoint_0_removes_the_binding` (2226), `binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive` (2251), `binding_delivers_nothing_when_the_word_is_zero` (2264) | C+T |
| 59 | `recv`/`reply_recv` return a pending notification before any caller: flag `notification`, the word in the badge field, the word cleared | `ipc.rs:306-328`, `371-429`, `43-52` `notification` | `recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller` (2143), `reply_recv_returns_a_pending_notification_…` (2158), `binding_delivers_nothing_to_a_caller_in_the_queue` (2533) | C+T |
| 60 | a `signal` on a bound notify wakes the first thread that waits to receive on the endpoint if no thread waits on the notify itself; that thread's reply object becomes idle | `ipc.rs:198-217` `hand_over` | `signal_on_a_bound_notify_wakes_a_thread_that_waits_to_receive` (2167), `signal_on_a_bound_notify_prefers_a_thread_that_waits_on_the_notify` (2181), `signal_on_an_unbound_notify_leaves_receivers_alone` (2193) | C+T |
| 61 | `wait` and `poll` take a `notify` only | `ipc.rs:218-232` | `signal_wait_and_poll_take_a_notify_only` (2135) | C+T |
| 62 | one thread is woken per `signal` | `ipc.rs:198-217` | `signal_wakes_one_thread_with_the_whole_word_and_clears_it` (2112) | C+T |

## Rules, Rights, Errors (checked because they bind every call)

- Rule 1 (everything a capability, no ambient right): C+T — `thread_needs_no_right_and_no_capability_for_its_own_capability_space` is the only exemption the contract grants.
- Rule 2 (any call can fail with `gone`): C+T, with the exception of F2's two calls, which cannot return `gone` for their own slot.
- Rule 3 (no kernel heap): n/a in a model.
- Rule 4 (every call bounded): C+T — see F12 for the one guard that carries it, and the 32/128 budgets.
- Rule 5 (a call never blocks): C+T — `Output::Waits` and `Model::woken`; `check.rs` verifies queues and waits.
- Rule 7 (objects belong to one core): n/a for one core.
- Rights table: C+T — `derive`, `send`, `recv`, `grant`, `manage`, `read`, `write`, `exec` all used exactly as the table says; no right is required where the table says "no right".
- Errors: every code of the table is produced except `ok` (never occurs, as documented) and `budget` (admission is `sched_configure`, outside the one-core model) — `not defined` rather than a gap.

---

# Part 3 — No sequence reaches a bad state

I looked for each of the bad states the review asked about, using the probes, the property tests (24 seeds × 5000 random calls with the full invariant check after every call) and the invariant list in `check.rs` (25 invariants: tree, slots, objects, waits, memory, removal, walk).

| Bad state | Result |
|---|---|
| a capability outliving its parent | not reachable: parent/children lists plus the invariant in `check.rs:107`; mutants `derivation-adds-rights` and `cap-delete-in-a-dying-space-refused` die |
| memory reused while an object uses it | not reachable: `take`/`release` and the watermark; `destroy` releases after the object is gone; invariants in `check.rs:382` |
| a removal that never ends | not reachable: every step consumes a removal or a slot; the self-slot guard makes the sweep progress; invariants `21` and `24`. The *only* way to hang the suite is to remove that guard (`sweep-eats-the-self-slot`) — a mutant, not a reachable state |
| unbounded work in one call | not reachable: 32 removals, 128 slots, 192 walk, 4 capabilities per message, 64 words, 64 depth; `window` and `listed` are O(4) |
| a thread that waits with nothing that can wake it | **not reachable in the model** — but one case is closed by the contract, not by the code: a caller waits for a reply whose reply object is armed, the server thread is destroyed, and no thread holds a capability to the answer path. The contract accepts this ("a caller is not woken when the server thread alone is destroyed": the reply object is the handle and another thread can still answer). If nobody holds the reply object, destroying the reply object's root capability wakes the caller with `gone`; the caller is stuck only if the object is reachable from no space at all, which cannot happen, because its root capability sits in some space and that space is either swept (waking the caller) or destroyed. I could not build a case |
| a suspended thread that never runs again with a message delivered to it | by design (*suspension and waiting are independent*), not a bad state; probe `Q2` confirms the message is delivered and the thread runs only after a resume |

One honest caveat: the model has no notion of a budget or of time, so "a thread that waits for ever" is only observable as "no call can ever wake it"; that is what I checked.

---

# Part 4 — Mutation log

79 mutants, one per rule, applied to a scratch copy of `model/src`, each run with `cargo test -p dodos-model --lib --test calls --test property` (timeout 100 s). "killed" means a named test failed; the killer is the first test to fail.

## The surviving or abnormal mutants — all four, with the verdict

1. `destination-after-the-kind` — **SURVIVED, but equivalent.** It moved `let place = self.destination(...)` below `let device = …`, a pure read: no observable change. Not a coverage hole. The version with the real reordering (`destination-after-the-kind-2`, the destination moved below the device rule and the size) **is killed** by `capability_arguments_are_checked_before_plain_arguments`. So the model's order is defended — it is the order itself that F1 disputes.
2. `reply-rec-replies-to-an-unarmed-object` — **SURVIVED, but equivalent.** It wrapped the existing `self.answer(...)` in `let _ = …` and left the call in place: same behaviour. The real mutation (not calling `answer`) is killed by `reply_recv_drops_the_reply_without_an_error_when_the_object_is_not_armed`.
3. `removal-does-not-mark-dying` — **invalid mutant**: the pattern occurred twice, so the harness applied nothing and recorded `BAD-PATTERN`. Dropped from the log; its role is taken by `next-removed-does-not-mark-dying`, which **is killed** by `object_is_dying_as_soon_as_a_removal_reaches_its_root_capability`.
4. `sweep-eats-the-self-slot` — **killed by timeout only** (the suite hangs; no assertion fires). The only mutant whose death is not a test failure; see F12.

No other mutant survived. The other 75, each killed by the test named:

| Mutant | Result | Killer |
|---|---|---|
| `badge-on-any-kind` | killed | `badge_is_accepted_only_on_an_endpoint_or_a_notify` |
| `binding-does-not-deliver-at-once` | killed | `binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive` |
| `binding-may-be-replaced` | killed | `notify_bind_is_busy_when_either_side_is_already_bound` |
| `binding-needs-no-manage` | killed | `notify_bind_needs_recv_on_the_notify_and_manage_on_the_endpoint` |
| `call-does-not-wait-for-the-reply` | killed | `address_of_an_empty_receive_range_is_not_looked_at` |
| `caller-keeps-its-reply-armed-when-destroyed` | killed | `caller_is_not_woken_when_the_server_thread_alone_is_destroyed` |
| `cap-delete-in-a-dying-space-refused` | killed | `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` |
| `cap-delete-of-a-dead-slot-is-gone` | killed | `cap_delete_on_a_dead_slot_makes_it_empty` |
| `child-untyped-is-not-device` | killed | `device_memory_becomes_only_a_frame_or_a_child_untyped` |
| `child-untyped-need-not-be-a-power-of-two` | killed | `child_untyped_is_a_power_of_two_of_at_least_4_kb` |
| `configure-a-waiting-thread` | killed | `thread_configure_is_busy_on_a_thread_that_waits` |
| `cspace-grows-from-any-untyped` | killed | `capability_space_given_at_start_up_never_grows` |
| `cspace-max-above-2-to-the-20` | killed | `cspace_maximum_is_a_whole_number_of_segments_up_to_2_to_the_20` |
| `dead-slot-becomes-full-again` | killed | `arguments_of_call_are_checked_in_the_order_of_the_table` |
| `dead-slot-is-free` | killed | `dead_slot_is_not_free` |
| `dead-slot-is-invalid` | killed | `arguments_of_call_are_checked_in_the_order_of_the_table` |
| `delivery-does-not-check-empty-slots` | killed | `delivery_into_a_dying_capability_space_drops_the_capabilities` |
| `delivery-does-not-check-the-depths` | killed | `capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped` |
| `derivation-adds-rights` | killed | `cap_derive_cannot_add_rights` |
| `derive-needs-read-not-derive` | killed | `cap_derive_checks_the_destination_before_the_rights_asked_for` |
| `derived-badge-is-not-kept` | killed | `badged_capability_keeps_its_badge_and_refuses_another` |
| `destination-after-the-kind` | **SURVIVED** | equivalent mutant (see above) |
| `destination-after-the-kind-2` | killed | `capability_arguments_are_checked_before_plain_arguments` |
| `device-takes-any-kind` | killed | `device_memory_becomes_only_a_frame_or_a_child_untyped` |
| `dying-capability-still-works` | killed | `copy_under_cap_delete_is_dying_and_its_object_is_not` |
| `empty-range-counts-as-a-full-range` | killed | `capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped` |
| `empty-range-looks-at-its-address` | killed | `address_of_an_empty_receive_range_is_not_looked_at` |
| `exec-always-given` | killed | `device_memory_becomes_only_a_frame_or_a_child_untyped` |
| `frame-of-zero-pages` | killed | `frame_of_1_gb_pages_takes_the_number_of_pages_too` |
| `grow-past-the-maximum` | killed | `cspace_grow_checks_the_untyped_then_the_maximum_then_the_memory` |
| `move-ignores-the-depths` | killed | `refused_move_is_invalid_before_no_slot` |
| `next-removed-does-not-mark-dying` | killed | `object_is_dying_as_soon_as_a_removal_reaches_its_root_capability` |
| `no-64-deep-limit` | killed | `creation_deeper_than_64_is_invalid` |
| `no-caps-dropped-flag` | killed | `capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped` |
| `no-dup-slot-check` | killed | `listed_slot_is_checked_fully_before_the_next_one` |
| `no-rule-on-what-a-space-holds` | killed | `capability_derived_by_ipc_into_a_space_that_cannot_hold_it_is_dropped` |
| `no-slot-before-no-memory` | killed | `dead_slot_is_not_free` |
| `notify-waiters-last-in-first-out` | killed | `signal_wakes_one_thread_with_the_whole_word_and_clears_it` |
| `object-not-destroyed-with-its-root` | killed | `binding_ends_when_either_object_is_destroyed` |
| `poll-waits` | killed | `binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive` |
| `range-count-not-checked` | killed | `arguments_of_reply_recv_are_checked_in_the_order_of_the_table` |
| `range-of-5-slots` | killed | `arguments_of_call_are_checked_in_the_order_of_the_table` |
| `range-shorter-than-the-list-is-partial` | killed | `empty_range_refuses_every_capability_and_the_words_still_arrive` |
| `read-needs-write` | killed | `changing_a_slot_through_a_cspace_capability_needs_write` |
| `receive-caller-before-notification` | killed | `binding_delivers_nothing_to_a_caller_in_the_queue` |
| `recv-needs-no-recv-on-the-reply` | killed | `recv_needs_recv_on_the_endpoint_and_on_the_reply_object` |
| `removal-does-not-wake-the-queue` | killed | `destroying_an_object_wakes_the_threads_that_wait_on_it_with_gone` |
| `removal-slots-127` | killed | `removal_examines_at_most_128_slots_of_dying_spaces_per_call` |
| `removal-slots-129` | killed | `removal_examines_at_most_128_slots_of_dying_spaces_per_call` |
| `removal-step-31` | killed | `cap_revoke_of_32_descendants_is_one_call` |
| `reply-header-drops-the-request-flag` | killed | `empty_range_refuses_every_capability_and_the_words_still_arrive` |
| `reply-rec only-idle-is-busy` | killed | `arguments_of_reply_recv_are_checked_in_the_order_of_the_table` |
| `reply-rec-replies-to-an-unarmed-object` | **SURVIVED** | equivalent mutant (see above) |
| `reply-wake-not-done` | killed | `destroying_a_reply_object_wakes_its_caller_and_its_receiver_with_gone` |
| `resume-of-a-dying-space-is-busy` | invalid | does not compile (`E0599`); replaced by `-2` |
| `resume-of-a-dying-space-is-busy-2` | killed | `thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed` |
| `resume-without-a-cspace` | killed | `thread_resume_is_busy_when_the_thread_is_bound_to_no_capability_space` |
| `revoke-oldest-child-first` | killed | `cap_revoke_removes_32_capabilities_then_returns_again` |
| `second-badge-accepted` | killed | `badged_capability_keeps_its_badge_and_refuses_another` |
| `sender-flags-accepted` | killed | `header_with_a_flag_set_by_the_sender_is_invalid` |
| `signal-ignores-the-notify-waiters` | killed | `outcome_of_a_wait_is_kept_until_the_next_call_of_the_thread` |
| `signal-needs-recv` | killed | `recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller` |
| `signal-prefers-the-endpoint` | killed | `signal_on_a_bound_notify_prefers_a_thread_that_waits_on_the_notify` |
| `signal-without-a-badge-sets-nothing` | killed | `binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive` |
| `size-ignored-for-the-other-kinds` | killed | `size_argument_is_zero_for_the_other_kinds` |
| `slot-0-is-a-destination` | killed | `cap_derive_checks_the_destination_before_the_rights_asked_for` |
| `suspend-a-waiting-thread-cancels-it` | killed | `suspended_thread_keeps_its_place_in_its_queue_and_still_gets_its_message` |
| `sweep-counts-a-full-slot-while-removing` | killed | `deleting_the_first_capability_space_destroys_everything_in_it` |
| `sweep-eats-the-self-slot` | killed by timeout | the suite hangs (F12) |
| `sweep-starts-at-0` | killed | `three_layers_of_spaces_create_spaces_and_hand_memory_down` |
| `thread-in-a-destroyed-space-works` | killed | `thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed` |
| `thread-in-a-dying-space-works` | killed | `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` |
| `unbind-fails-when-unbound` | killed | `notify_bind_with_endpoint_0_removes_the_binding` |
| `untyped-must-be-strictly-deeper` | killed | `capability_derived_by_ipc_lands_in_a_space_that_is_not_deeper` |
| `wait-does-not-clear-the-word` | killed | `wait_returns_the_word_and_clears_it` |
| `wake-not-counted-in-the-32` | killed | `destroying_an_object_wakes_its_waiters_first_in_first_out` |
| `watermark-never-returns` | killed | `cspace_that_holds_its_own_root_capability_can_be_deleted` |
| `watermark-not-aligned` | killed | `child_untyped_is_aligned_on_its_size` |

Mutants I expected to survive and did not, worth noting because they are the rules I thought least defended: `signal-prefers-the-endpoint` (the reverse of the "notify waiter first" rule) is killed by a dedicated test; the bind/unbind pairs, the badge on a `notify_bind`, and the 128-slot boundary in both directions (127 and 129) are all killed; the three order-of-checks mutants (`dead-slot-is-invalid`, `dead-slot-becomes-full-again`, `removal-step-31`) die on the first failing assertion, so the count of `again`s is genuinely pinned.

What no mutant can test, because the model is right and the *contract* is unclear: F1 (the position of the destination), F3, F4, F5. Those are contract work, not model work.

---

# Part 5 — What is right, in one line each

For the author of the real kernel, these are the parts I read sentence by sentence and found faithful, with the tests that defend them:

- Slot states (empty/full/dead) and the rule that a dead slot is not free (`277`, `295`, `305`, `316`).
- `via`, one level of indirection, and `read`/`write` through a `cspace` capability (`321`, `331`, `342`, `355`, `1695`).
- `cspace` creation, directory rounding, growth from one untyped, index stability, `no_slot` at the maximum, `no_memory` (`385`, `396`, `407`, `415`, `426`, `446`, `456`, `1312`, `1436`, `2672`).
- The derivation tree: one parent, no capability outliving its parent, `cap_revoke` keeps the capability, `cap_delete` removes the descendants, an object lives as long as its root, the memory returns (`607`, `627`, `638`, `653`, `676`, `456`, `1454`).
- Depth 64 and "a space holds only what is deeper", on every placement — `cap_move`, `cap_derive`, `untyped_retype`, IPC delivery — with the own-root exception (`988`, `1007`–`1091`, `1183`–`1219`, `1106`).
- The removal order (most recent child first, a capability after its descendants, a space in index order), the 32/128 budgets, `again`, the sweep index kept between calls, a slot examined once (`653`, `667`, `676`, `803`, `855`, `886`, `2564`, `2574`, `2580`).
- Dying capabilities versus dying objects, the capability on the path that keeps working, the wake of the step that marks a reply object, and that wake not counted in the 32 (`688`, `703`, `716`, `736`, `753`, `768`, `781`, `793`, `2430`, `2458`).
- Destroying an object wakes every waiter with `gone`; destroying a space sweeps it; `cap_revoke` on a space root does not sweep; a thread in a dying space gets `gone` except `cap_delete` on its own slots (`818`, `839`, `886`, `899`, `917`, `932`, `948`, `959`, `2446`).
- Threads: new thread suspended and unbound, `thread_configure` (three `manage`, `send` on the fault endpoint, 0 allowed, `busy` unless suspended and not waiting), resume and suspend, suspension independent of waiting (`1468`, `1484`–`1534`, `1545`, `1560`, `1571`, `1578`, `2284`, `2381`, `2395`, `2408`).
- IPC: `call`/`recv`/`reply_recv`/`send` with their rights, the queue, delivery to a waiting receiver, the badge, badge 0 on a reply, `send` never queues, the reply object idle/attached/armed, a caller that disappears (`1608`, `1620`, `1630`, `1645`, `1663`, `1782`, `1798`, `1806`, `1815`, `1826`, `1838`, `2507`).
- Transfer: up to 4, move and derive, checked when the call is made and again at delivery, all or nothing, `caps_dropped` with count 0, the flag in the reply header, the server not told, a slot listed twice (`1873`–`2068`, `2320`, `2339`, `2471`, `2497`).
- Notifications: the bits of the badge or bit 0, one waiter woken with the whole word, the word cleared, `wait`/`poll`, `notify_bind` and its `busy`, the binding ending with either object, the pending word delivered to a waiting receiver, a notification returned before any caller, the notify waiter preferred over the endpoint (`2085`, `2095`, `2103`, `2112`, `2125`, `2143`, `2158`, `2167`, `2181`, `2193`, `2202`, `2213`, `2226`, `2239`, `2251`, `2264`, `2533`).
- The order of checks 1 → 4, with the header read right after the acting capability, the number of `again`s, `no_slot` before `no_memory`, the depth checks last (`477`, `487`, `495`, `503`, `510`, `2308`, `2320`, `2339`, `2358`, `2597`, `2611`, `2633`, `2655`, `2672`, `2697`, `2710`).
- The 25 invariants of `check.rs` (including `21: removal that never ends` and `24: walk of a removal`), re-checked after every random call in `property.rs` (24 seeds × 5000 calls).

---

# Summary of the findings

| # | Title | Severity | Confidence |
|---|---|---|---|
| F1 | `untyped_retype` checks the destination before the kind and the size; the table order says otherwise | contract error | confirmed by run (`P1a`, `P1b`, `P1d`) |
| F2 | `thread_read_regs`/`thread_write_regs` cannot carry arguments; `Other(Call)` returns `unsupported` before any check | contract error | confirmed by run (`P4a`, `P4b`) and by reading `lib.rs:148` |
| F3 | `grant` judged before the message header is validated | undefined | confirmed by run (`P2a`–`P2c`); untested |
| F4 | `recv` returns `busy` although a notification is pending | undefined | confirmed by run (`P3a`, `P3b`); untested |
| F5 | `untyped_retype` makes 9 of the 15 kinds; the contract names none | undefined | confirmed by run (`P1d`, `P1e`) |
| F6 | five `CONTRACT-GAP` markers claim gaps the contract does not have | minor | read |
| F7 | `Syscall::Other` accepts modelled call numbers | minor | confirmed by run (`P4c`) |
| F8 | `boot()` omits start-up capabilities without a marker | minor | read |
| F9 | the 128-slot budget is a private const, the 32-step one is in `abi` | minor | read |
| F10 | citation to "Revision D-105" | minor | read |
| F11 | eight behaviours the contract fixes that no test defends | untested | mutants and probes |
| F12 | termination of a removal rests on the `held != cap` guard alone | minor | the mutant hangs the suite |

Nothing in the model contradicts a contract sentence that is unambiguous. The model is a sound oracle for the one-core calls, with the reservations above; the two that would teach the real kernel the wrong thing are F1 (one call, wrong order of two errors) and F2 (two calls of the table that the oracle cannot exercise at all).
