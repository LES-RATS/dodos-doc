# Review of the one-core model against the call reference

Reviewer: deepseek (review sub-agent). Date: 14 November 2026.
Branch reviewed: `model` at `5572496` ("Follow revision D-103: a space holds only what is deeper").
Contract: `Docs/architecture/kernel-interface.md`, section "Call reference, one core".
Code: `dodos-kernel/model/` (`src/lib.rs`, `src/caps.rs`, `src/ipc.rs`, `src/check.rs`,
`src/check/tests.rs`, `tests/calls.rs`, `tests/property.rs`), interface `abi/src/lib.rs`.

## How I worked

Sentence by sentence through the call reference. For each rule I found the lines that apply it
and the test that pins it, then asked whether the suite notices if the rule is broken. Where I was
not sure I copied the repository to `/tmp/dk`, broke the rule there and ran
`nix develop -c cargo test -p dodos-model` (36 mutations in all, listed in the appendix). The
original tree was left untouched (`git status` clean before and after; nothing committed).

Baseline: 183 tests in `tests/calls.rs`, 53 in `check/tests.rs`, 4 in `tests/property.rs`, all green.

## What is right

The model is a faithful and unusually careful transcription of the call reference. The parts that
are hard to get right are right, and tested: the derivation tree and its removal order, the
"removal ends" marking with its uncounted reply wake, the slot states (empty/full/dead), the depth
rules of D-103 in all four places a capability is placed, the order of checks argument by
argument, the two-phase transfer of capabilities with `caps_dropped` on both sides, and the
notification binding. All 26 numbered invariants of `check.rs` check exactly what their comment
says, and every one of them has a test in `check/tests.rs` that fails if the check is removed (the
`spoiled` helper asserts `check()` is `Ok` before the state is broken, and each test asserts the
invariant's own string, so a test cannot pass for the wrong reason; I confirmed this by removing
invariants 5, 19, 21, 22, 23, 24 and 25). No sequence of calls I could build reaches a state that
`check()` accepts and that is wrong; in particular I could not build a capability that outlives its
parent, a use of an object whose root capability is gone, or a thread left queued on a destroyed
object.

The findings below are therefore mostly about rules the suite does not defend, and about
behaviour the contract leaves open but the model has already decided.

---

# Findings, by severity

## F1 — The untyped watermark is reset to zero; the contract says it only moves up

**Severity**: wrong behaviour (of the contract, and of the model's own comment) / contract error.
High impact: this is an oracle rule the contract does not fix.

**Where**: `model/src/caps.rs:270` (`release`: `if untyped.live == 0 { untyped.watermark = 0 }`),
its comment at `caps.rs:267` ("Rules of `untyped_retype`: the watermark returns to zero when the
last object taken from the untyped is destroyed"), and `model/src/check.rs:328`
(invariant 18: `(untyped.watermark == 0) == (untyped.live == 0)`).

**What is wrong**: the contract says "Memory is taken at a watermark that only moves up"
(Capabilities and objects, rules of `untyped_retype`). The model moves it back to zero as soon as
nothing taken from the untyped is live, and the comment presents that as a rule *of the
contract*, which it is not. The two contract sentences pull in opposite directions — "only moves
up" against "its memory goes back to the untyped it came from" (The derivation tree, object
lifetime) — and the model silently resolves the conflict, without a `CONTRACT-GAP` marker, and
then makes its choice mandatory through invariant 18.

**How I know**: read in the code; confirmed by running. Breaking the reset fails 13 tests
(`watermark_returns_to_zero_only_when_the_last_object_is_destroyed`,
`segments_go_back_to_the_untyped_when_the_cspace_is_destroyed`, the property tests, …), and
removing the segment release in `destroy` fails 12. A kernel that implements the contract's
"only moves up" sentence literally would fail the oracle.

**Suggestion**: fix the contract first, since both readings are defensible: either add "and
returns to zero when the last object taken from it is destroyed" to the watermark sentence, or
drop the reset from the model and from invariant 18. Mark the decision `CONTRACT-GAP` until it is
settled. As it stands, this is the single largest oracle risk in the model.

## F2 — The caller's receive range is lost on the fast path of `call`, and no test notices

**Severity**: untested (the model is right; the suite would not catch a wrong kernel).

**Where**: `model/src/ipc.rs:68-93` (`call`, the branch where a thread already waits to receive,
which passes the caller's `window` to `serve` at `ipc.rs:318`); no test in `tests/calls.rs`
covers it.

**What is wrong**: nothing, in the model. I replaced the caller's window with an empty one on that
branch only, and the whole suite still passed. Every existing test that checks a reply landing in
the caller's range (`reply_carries_capabilities_into_the_range_given_with_call`,
`reply_recv_transfers_capabilities_both_ways_and_is_not_told_of_a_drop`) has the caller *join the
queue* first, so it exercises the `Wait::Call { window }` path, never the immediate-delivery path.
The immediate path is the fast path of the whole design.

**How I know**: mutation Q5 (empty window in the `Some` branch) survived 240 tests; a probe then
showed the model does the right thing: the reply's capability arrives in the caller's slot 50 with
`caps = 1`.

**Suggestion**: one test — a server waits to receive; a caller calls with a one-slot range; the
server answers with `send` moving a capability; the caller finds it in its range and the header
says `caps = 1`.

## F3 — `invalid` before `no_slot` is tested for `cap_move` only

**Severity**: untested. The contract fixes this order (Order of checks: step 3 plain arguments
`invalid`, step 4 `no_slot`), and the model gets it right in all three places; only one of the
three is pinned.

**Where**: `caps.rs:106-107` (`cap_derive`), `caps.rs:182-183` (`untyped_retype`),
`caps.rs:121-122` (`cap_move`, the tested one). Test: `refused_move_is_invalid_before_no_slot`.

**What is wrong**: swapping `fits` (which returns `invalid` for a depth refusal) and `vacant`
(`no_slot`) in `cap_derive` or in `untyped_retype` leaves the suite green (mutations N2, Q2). A
kernel that answers `no_slot` first for `cap_derive` or `untyped_retype` would pass the oracle.

**Suggestion**: two lines in `tests/calls.rs`, mirroring `refused_move_is_invalid_before_no_slot`:
a depth-refused derive into a slot that is already full must be `invalid`, and the same for
`untyped_retype`.

## F4 — On device memory a size argument decides before the device rule, so `unsupported` can win over `invalid`

**Severity**: undefined (the contract does not order checks inside step 3) with a real divergence:
the contract's sentence says `invalid`.

**Where**: `caps.rs:175-181` — `footprint(kind, size, page)?` runs before the device check.

**What is wrong**: `untyped_retype(device_untyped, Timer, 0, slot)` returns `unsupported`, but
"Device memory can only become a `frame` or a child `untyped` (`invalid` otherwise)" says
`invalid`. Both are step-3 checks, so the contract allows either, but the model has picked one
without a marker, and a kernel author reading the device sentence will pick the other.

**How I know**: read in the code, and confirmed by a probe (`device timer: Err(Unsupported)`,
`ordinary timer: Err(Unsupported)`). Mutation M2 (device check moved first) survived the suite.

**Suggestion**: one test fixing the answer the kernel must give, and one clause in the contract.
If the intent is that a kind outside the one-core model is always `unsupported`, say so in the
device sentence too.

## F5 — The order of the plain-argument checks of `cap_derive` is decided by the model and untested

**Severity**: untested / undefined.

**Where**: `caps.rs:91-107`: rights subset (`denied`), then badge allowed on the kind only
(`invalid`), then "another badge" (`denied`), then the depths (`invalid`), then `vacant`.

**What is wrong**: moving the depth check before the rights check (M1) or the badge-kind check
before the rights check (N1) leaves the suite green, and the two orders return different errors
(`denied` against `invalid`) for the same call. The contract orders step 1 before step 2 and
step 3 after step 2, but says nothing inside the plain arguments, and nothing inside step 3.

**How I know**: mutations M1 and N1 both survived.

**Suggestion**: either one test that pins the order the two humans want, or a sentence in the
contract. Since the kernel must match the oracle exactly, an untested order here is a latent
mismatch.

## F6 — `notify_bind` on the pair it is already bound to returns `busy`; the contract does not say

**Severity**: undefined / untested.

**Where**: `ipc.rs:246` — `if bound.is_some() || self.endpoints[&endpoint].notify.is_some()`.

**What is wrong**: "One notify per endpoint and one endpoint per notify (`busy` otherwise)" reads
as a rule against *double* binding. Binding a notify to the endpoint it is already bound to is
arguably a no-op that should succeed; the model refuses it. A probe confirms `bind` twice →
`busy`. Allowing it (mutation M3) leaves the suite green, so nothing pins either answer.

**Suggestion**: decide it in the contract ("binding the same pair again is `busy`" or "succeeds"),
then one test. This matters to the real kernel because a restarting server may well rebind.

## F7 — `thread_read_regs` and `thread_write_regs` are in the one-core Threads table but the model returns `unsupported`

**Severity**: undefined.

**Where**: the model has no `Syscall` variant for them; any call goes through `Syscall::Other`
(`lib.rs:456`) → `unsupported`. Test: `calls_outside_the_one_core_model_are_unsupported`.

**What is wrong**: the Threads table gives both calls arguments, rights (`read` / `write`) and a
state rule ("The thread must be suspended (`busy`)"). Only a following sentence says the register
block is not part of the one-core model. A kernel that implements them as written, as the table
invites, is declared wrong by the oracle. Nor is this marked `CONTRACT-GAP` — the single marker in
the whole model is the list of kinds of `untyped_retype` (`caps.rs:58`).

**Suggestion**: add "not part of the one-core model" to both rows, as is done for the register
block; or model them (a `read`/`write` check plus `busy` when not suspended is four lines).

## F8 — "except `cap_delete`" for a dying capability space is unreachable through `via`, and the contract contradicts itself

**Severity**: minor, contract error.

**Where**: `caps.rs:127-133` (`cap_delete` uses `through(self.own(thread)?, …)`), `lib.rs:490`
(`through` → `full` → `gone` for a capability of a dying object).

**What is wrong**: two contract sentences collide. "A thread whose capability space is dying gets
`gone` from every call except `cap_delete`" against "every call on it, through any capability,
returns `gone`" (an object that is dying). Reaching the dying space at all needs a capability for
it, and that capability is `gone`; so `cap_delete` with `via` into the dying space returns `gone`.

**How I know**: a probe. With a capability space dying (`Err(Again)` from `cap_delete`), a thread
inside it gets `cap_delete` of a direct index → `ok`; `cap_delete` of `via(6, 6)` (through a copy
of the space's own root capability) → `gone`. The test
`thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` only uses direct
indexes.

**Suggestion**: say in the contract that the exception covers only slots reached without `via`
(or drop the exception), and add the probe as a test so the kernel matches.

## F9 — `no_slot` carries two meanings in the contract

**Severity**: contract error, minor.

**Where**: contest of the Errors table (`no_slot` = "No free capability slot") against Order of
checks step 4 (`no_slot` = "the destination slot is not empty").

**What is wrong**: the model uses the second meaning for a full destination
(`lib.rs:570`, `vacant`) and the first meaning for a full capability space (`caps.rs:216`,
`cspace_grow` → `no_slot` at the maximum). Both are defensible; the gloss "No free capability
slot" describes only the second use. A kernel author or a user-space reader will be misled.

**Suggestion**: gloss it as "The destination slot is not empty, or the capability space is full",
or split the code.

## F10 — `recv` requires an idle reply object, `reply_recv` is "as `recv`", yet must accept an armed one

**Severity**: contract error, minor.

**Where**: contract IPC table, rows `recv` and `reply_recv`; model `ipc.rs:102-142`.

**What is wrong**: the `recv` row says the reply object "must be idle (`busy`)". The `reply_recv`
row says "as `recv` with the same reply object" and then "If the reply object is not armed, the
reply is dropped without an error" — which only makes sense if an armed object is accepted. The
model accepts armed, and refuses an object *attached to another thread* with `busy`
(`ipc.rs:136`), which the contract never states. Correct behaviour, imprecise contract; a kernel
written from the `recv` row alone would be wrong.

**Suggestion**: state in the `reply_recv` row: "the reply object must be armed or idle; attached is
`busy`".

## F11 — The model has no sweep index, so one removal step rescans the whole capability space

**Severity**: minor (cost, not result).

**Where**: `caps.rs:465` (`swept` scans `space.slots` from index 0 on every step).

**What is wrong**: the contract says "the dying space keeps the index where the sweep stands, so
that a step does not scan it again from the start". The model does not keep an index; it rescans
from 0 and relies on the fact that removed capabilities leave *dead* slots, which are skipped.
The visible result is identical — I checked the ordering test and the dead/empty distinction — but
each of the 32 steps costs O(number of slots), so one `cap_delete` of a large space is O(32 ×
slots) of work in one call, which is what the contract's sentence exists to avoid.

**How I know**: read in the code; the ordering behaviour is pinned by
`destroying_a_cspace_removes_its_capabilities_in_index_order` (mutation N11, reverse order,
fails it).

**Suggestion**: note in the model that equivalence is by dead slots, or keep the index. For the
oracle it does not matter; for the kernel measurement it does.

## F12 — The 192 bound of a removal walk does not follow from the placement rules in this model

**Severity**: minor / suspected (not reproduced).

**Where**: `check.rs:159` (invariant 24: `longest_walk <= 3 * TREE_DEPTH`), `caps.rs:437`
(`next_removed`), contract "The derivation tree", the paragraph after the depth-64 bullet.

**What is wrong**: the contract derives 192 from "128 through `untyped` capabilities and roots,
then 64 through ordinary copies", which assumes the walk descends one chain. In the model
`next_removed` also *jumps* (`swept`) into the capability space a root capability belongs to and
starts descending again from whatever that space holds first, and a capability of any kind may be
placed in any space (the model proves this in
`capability_of_another_kind_moves_into_any_capability_space`). So a walk is bounded by
(number of nested `cspace` root capabilities on the path) × (depth of a derivation chain) — up to
about 64 × 64, not 192. If a legal state ever produced a longer walk, `longest_walk` would trigger
invariant 24 and the oracle would report a violation of a state that is legal.

**How I know**: read in the code and argued from the model's own rules; I did not build the
state — it needs a capability space at depth ~60 holding a 60-long derivation chain whose leaf is
another `cspace` root. The random runs (24 seeds × 5000 steps) never came near it, and in practice
the walk is at most 64 because a `swept` step is only taken from a `cspace` root, whose depth
strictly grows.

**Suggestion**: either bound the walk in the model by the real argument (the depth), or weaken
invariant 24 to "the walk did not repeat a capability" (which invariant 21 already gives). As
written, invariant 24 can only be broken by hand — its test sets `longest_walk = 193` directly,
and `walk_of_a_removal_is_measured` pins a value of 2 — so it is a defensive assertion, not a
checked property, and the contract's 192 is not the bound in force.

---

# The call reference, rule by rule

Verdicts: **C+T** correct and tested · **C−U** correct but untested · **DIFF** different from the
contract · **N/A** not defined by the contract.

## Slots and addresses

| Rule | Model | Test | Verdict |
|---|---|---|---|
| Slot address: low 32 index, high 32 `via`, one level only | `lib.rs:490` `through` | `via_reaches_a_slot_of_another_capability_space`, `via_must_name_a_live_cspace_capability` | C+T |
| Slot 0 never used; address 0 = none | `lib.rs:561` `destination`, `lib.rs:584` `window`, `boot` | `slot_zero_is_never_used`, `boot_state_…`, `check::tests::dead_slot_0_is_reported` | C+T |
| Slot empty / full / dead; dead → `gone`, empty → `invalid` | `lib.rs:505` `full` | `slot_of_a_revoked_capability_is_dead_and_using_it_is_gone`, `empty_or_out_of_range_slot_is_invalid` | C+T |
| `cap_delete` on a dead slot empties it; a dead slot is not free | `caps.rs:134-137`, `lib.rs:570` | `cap_delete_on_a_dead_slot_makes_it_empty`, `dead_slot_is_not_free` | C+T |
| No right needed for one's own space; `read` to read a slot through a `cspace`, `write` to change it | `lib.rs:469/490/561` | `thread_needs_no_right_and_no_capability_for_its_own_capability_space`, `reading_a_slot_…`, `changing_a_slot_…` | C+T |
| A `cspace` is created with a maximum (multiple of 128), a directory (8 B per 128 slots, power of two), no slot; `cspace_grow` adds 128 slots; indexes never change | `caps.rs:38` `footprint`, `caps.rs:199` | `cspace_is_created_with_no_slot_and_grows_by_one_segment`, `growing_a_cspace_does_not_change_slot_indexes`, `cspace_directory_is_rounded_up_to_a_power_of_two`, `cspace_maximum_is_…` | C+T |
| A `cspace` grows only from the untyped it was created from; any capability for that untyped is accepted; segments die with it | `caps.rs:206-214`, `caps.rs:508` `destroy` | `cspace_grow_takes_only_the_untyped_the_cspace_was_created_from`, `segments_go_back_to_the_untyped_when_the_cspace_is_destroyed`, `capability_space_given_at_start_up_never_grows` | C+T |
| A destination that is slot 0 or beyond the table is `invalid` | `lib.rs:561` | `slot_zero_is_never_used`, `empty_or_out_of_range_slot_is_invalid`, `receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid` | C+T |

## The derivation tree

| Rule | Model | Test | Verdict |
|---|---|---|---|
| One parent, except start-up roots; `untyped_retype` and `cap_derive` make children | `caps.rs:281` `create`, `caps.rs:367` `derive`, `new_cap` | `new_capability_is_a_child_of_the_untyped_capability`, `check::tests::parent_*` | C+T |
| A capability never outlives its parent; `cap_revoke` keeps it, `cap_delete` removes it | `caps.rs:393` `remove` | `cap_revoke_removes_the_descendants_and_keeps_the_capability`, `cap_delete_removes_the_descendants_instead_of_handing_them_up`, `cap_move_keeps_…` | C+T |
| An object lives exactly as long as the root capability, wherever it was moved; memory returns to the untyped | `caps.rs:493` `remove_cap`, `508` `destroy` | `object_lives_as_long_as_its_root_capability_wherever_it_is_moved`, `watermark_returns_to_zero_…` | C+T (see F1 for *how* the memory returns) |
| `cap_move` to an empty slot changes nothing about the tree, rights or badge | `caps.rs:113`, `379` `place` | `cap_move_keeps_rights_badge_and_place_in_the_tree` | C+T |
| Tree at most 64 deep; deeper is `invalid`, checked with the plain arguments | `caps.rs:235` `fits` (`depth <= TREE_DEPTH`), `ipc.rs:263` `listed` | `derivation_deeper_than_64_is_invalid`, `creation_deeper_than_64_is_invalid`, `check::tests::tree_deeper_than_64_is_reported` | C+T |
| A space holds only what is deeper: `cspace` root strictly deeper, `untyped` not smaller, `invalid`, on all four paths | `caps.rs:235` `fits`; called at `caps.rs:106`, `182`, `121`, `ipc.rs:271` (delivery) | `untyped_capability_is_placed_only_in_a_space_that_is_not_deeper`, `…_derived_or_created_…`, `root_capability_of_a_space_is_placed_only_in_a_space_less_deep`, `space_is_created_only_in_a_space_less_deep`, `spaces_nested_at_the_same_depth_are_refused`, `spaces_nest_no_deeper_than_the_tree`, `capability_moved_by_ipc_…`, `capability_derived_by_ipc_…` | C+T (the property test also refutes both directions: `moves_that_the_depths_rule_on_…`) |
| A space may hold its own root capability, removed last; the start-up space never grows | `caps.rs:239` (`moved_root`), `caps.rs:465` `swept` (`held != cap`) | `cspace_that_holds_its_own_root_capability_can_be_deleted` | C+T |
| Removal in bounded steps: 32 per call, `again`, most recent child first, a capability only after its descendants, well formed between steps | `caps.rs:393` `remove`, `437` `next_removed` | `cap_revoke_removes_32_capabilities_then_returns_again`, `cap_revoke_of_32_descendants_is_one_call`, `capability_is_removed_after_its_descendants_the_most_recent_first`, `cap_delete_returns_again_…` | C+T |
| Removal ends: dying capability `gone` from the first step; dying object `gone` through any capability; a cap on the path that is not a root keeps working | `caps.rs:141-142` (dying marker), `lib.rs:505` `full`, `519` `dying` | `dying_capability_is_gone_for_every_call_but_cap_delete`, `every_call_on_a_dying_object_is_gone`, `object_is_dying_as_soon_as_a_removal_reaches_its_root_capability`, `copy_under_cap_delete_is_dying_and_its_object_is_not`, `capability_on_the_path_of_a_removal_keeps_working_until_it_is_removed` | C+T |
| A thread whose space is dying gets `gone` from every call except `cap_delete` | `lib.rs:469` `space`, `caps.rs:127` | `thread_whose_capability_space_is_dying_gets_gone_from_every_call_but_cap_delete` | C+T for direct slots, **DIFF through `via`** (F8) |
| A delivery into a dying/destroyed space drops the capabilities, keeps the words; a dying space only shrinks | `ipc.rs:360` `deliver` (`empty` closure), `full` refuses a capability of a dying object | `delivery_into_a_dying_capability_space_drops_the_capabilities`, `check::tests::capability_created_in_a_dying_space_…` | C+T |
| The step that marks a reply object wakes the attached receiver or the armed caller with `gone`, not counted in the 32 | `caps.rs:443-451` | `marking_a_reply_object_as_dying_wakes_the_receiver_attached_to_it`, `…_the_caller_it_is_armed_with`, `wake_of_the_step_that_marks_a_reply_object_is_not_counted`, `check::tests::walk_of_a_removal_is_measured` | C+T |
| `cap_delete` acts on the slot, not the object; a dead slot becomes empty | `caps.rs:134`, `414` (`left`) | `cap_delete_on_a_dead_slot_makes_it_empty`, probe in F8 | C+T |
| Destroying an object wakes every thread that waits on it with `gone`; a caller is not woken when the server thread alone is destroyed; destroying a `cspace` removes its caps in index order and keeps the sweep position | `caps.rs:393/437/465/508`, `ipc.rs:441` `unlink` | `destroying_an_object_wakes_the_threads_that_wait_on_it_with_gone`, `destroying_a_cspace_removes_its_capabilities_in_index_order`, `caller_is_not_woken_when_the_server_thread_alone_is_destroyed`, `revoking_the_capability_a_thread_used_does_not_disturb_its_wait` | C+T; the *index* itself is not kept (F11) |
| `cap_revoke` on the root of a space does not sweep the space | `caps.rs:394-399` (`Removal::Descendants` starts at the last child) | `cap_revoke_on_the_root_capability_of_a_space_does_not_sweep_the_space` | C+T |
| Rights checked when the call is made; a waiting thread is not disturbed by a revocation | `lib.rs:505` `full` | `revoking_the_capability_a_thread_used_does_not_disturb_its_wait` | C+T |

## Order of checks

| Rule | Model | Test | Verdict |
|---|---|---|---|
| 1. the capability acted on: slot, kind, rights | `lib.rs:505/530` | `kind_is_checked_before_rights`, `first_capability_is_checked_before_the_others` | C+T |
| 2. the other capability arguments, in table order | see each call below | `capability_arguments_are_checked_in_the_order_of_the_table` | C+T |
| 3. the plain arguments (`invalid`) before 4. the state | `fits`/`footprint`/`window` before `vacant`/`take`/`busy` | `plain_arguments_are_checked_before_the_state`, `no_slot_is_reported_before_no_memory`, `refused_move_is_invalid_before_no_slot` | C+T for `cap_move`; **C−U** for `cap_derive` and `untyped_retype` (F3); order *inside* step 3 undefined (F5) |

## Capabilities and objects

| Rule | Model | Test | Verdict |
|---|---|---|---|
| `cap_derive`: `derive` on the source | `caps.rs:86-89` | `cap_derive_needs_derive_on_the_source` | C+T |
| `cap_derive`: rights a subset, checked with the plain arguments, after the destination | `caps.rs:91-95` | `cap_derive_cannot_add_rights`, `cap_derive_checks_the_destination_before_the_rights_asked_for` | C+T |
| `cap_derive`: a badge only on an endpoint or a notify | `caps.rs:96-100` | `badge_is_accepted_only_on_an_endpoint_or_a_notify` | C+T |
| `cap_derive`: another badge is `denied`, the same is accepted, the badge is kept | `caps.rs:101-105`, `108` | `badged_capability_keeps_its_badge_and_refuses_another` | C+T |
| `cap_move`: no right on the capability; empty destination | `caps.rs:113` | `cap_move_needs_no_right_on_the_capability`, `cap_move_takes_a_full_source_and_an_empty_destination` | C+T |
| `cap_delete`, `cap_revoke`, `cap_inspect`: no right on the capability | `caps.rs:127/149/154` | `cap_delete_and_cap_revoke_need_no_right_on_the_capability`, `cap_inspect_needs_no_right_…` | C+T |
| `untyped_retype`: `write` on the untyped, one object per call | `caps.rs:163-176` | `untyped_retype_needs_write_on_an_untyped` | C+T |
| `untyped_retype`: size argument per kind, a size that does not fit in 64 bits is `invalid` | `caps.rs:38` `footprint` | `child_untyped_is_a_power_of_two_of_at_least_4_kb`, `frame_takes_a_page_size_and_a_number_of_pages`, `cspace_maximum_is_…`, `size_argument_is_zero_for_the_other_kinds` | C+T |
| `untyped_retype`: device memory only a frame or a child untyped | `caps.rs:176-181` | `device_memory_becomes_only_a_frame_or_a_child_untyped`, `new_capability_never_has_exec_on_device_memory` | C+T, but the `invalid` is pre-empted by `unsupported` for other kinds (F4) |
| Kinds the one-core model does not make are `unsupported` | `caps.rs:58` | `kinds_outside_the_one_core_model_are_unsupported` | C+T, and the one `CONTRACT-GAP` marker |
| Memory at a watermark that only moves up, aligned (size / page size / 4 KB) | `caps.rs:257` `take` | `memory_is_aligned_on_the_size_of_the_object`, `child_untyped_is_aligned_on_its_size`, `frame_is_aligned_on_its_page_size`, `kernel_object_larger_than_4_kb_is_aligned_on_4_kb` | C+T; **DIFF** on "only moves up" (F1) |
| Every right, but `exec` only if the untyped capability has it, never on device memory | `caps.rs:186-193` | `new_capability_has_every_right`, `new_capability_has_exec_only_if_the_untyped_capability_has_it` | C+T |
| Frames are not cleared | not modelled (no memory contents) | — | N/A in the model (stated in the module doc) |
| `cspace_grow`: `manage` on the cspace, `write` on the untyped, the untyped it came from, `no_slot` at the maximum | `caps.rs:199-221` | `cspace_grow_needs_manage_…`, `cspace_grow_is_no_slot_at_the_maximum`, `cspace_grow_is_no_memory_when_the_untyped_is_exhausted` | C+T |

## Threads

| Rule | Model | Test | Verdict |
|---|---|---|---|
| A new thread is suspended and bound to nothing | `caps.rs:308` | `new_thread_is_suspended`, `thread_resume_is_busy_when_the_thread_is_bound_to_no_capability_space` | C+T |
| `thread_configure`: `manage` on the thread, the cspace and the aspace, `send` on the fault endpoint; aspace and fault may be 0; suspended and not waiting (`busy`) | `lib.rs:609` | `thread_configure_binds_the_capability_space`, `…_needs_manage_…`, `…_needs_send_on_the_fault_endpoint`, `…_checks_the_kind_of_each_capability`, `…_is_busy_unless_the_thread_is_suspended`, `…_is_busy_on_a_thread_that_waits` | C+T; the aspace and the fault endpoint are checked and **not kept** (model decision, see "decides alone") |
| `thread_resume` / `thread_suspend`: `manage`, idempotent; resume `busy` with no space or a destroyed one, allowed on a dying one | `lib.rs:641/650` | `thread_resume_and_suspend_succeed_in_the_state_asked_for`, `…_need_manage_on_a_thread`, `thread_resume_is_busy_when_the_capability_space_of_the_thread_is_destroyed` | C+T; "resume allowed on a dying space" is only implicit (a thread in a dying space runs in the property test) |
| `thread_read_regs` / `thread_write_regs` | `Syscall::Other` → `unsupported` | `calls_outside_the_one_core_model_are_unsupported` | **DIFF** / undefined (F7) |
| Suspension and waiting are independent | `lib.rs:650`, `runnable` | `suspended_thread_keeps_its_place_in_its_queue_and_still_gets_its_message` | C+T |

## IPC

| Rule | Model | Test | Verdict |
|---|---|---|---|
| `call`: `send`, `grant` if the message lists capabilities; deliver to a waiting receiver, arm its reply, the caller waits; else join the queue first in first out | `ipc.rs:68` | `call_joins_the_queue_and_recv_takes_the_first_caller`, `call_is_delivered_at_once_to_a_thread_that_waits_to_receive`, `call_needs_send_on_an_endpoint`, `message_with_capabilities_needs_grant` | C+T; the caller's range on the immediate path is **C−U** (F2) |
| Message limits: 64 words, 4 capabilities | `ipc.rs:21` | `message_has_at_most_64_words_and_4_capabilities` | C+T |
| `recv`: `recv` on the endpoint and on the reply object, which must be idle (`busy`) | `ipc.rs:102` | `recv_needs_recv_on_the_endpoint_and_on_the_reply_object`, `recv_is_busy_when_the_reply_object_is_armed`, `…_attached` | C+T |
| `recv`: in order — pending notification of the bound notify, first caller, otherwise wait attached | `ipc.rs:295` `receive` | `recv_returns_a_pending_notification_of_the_bound_notify_before_any_caller` | C+T |
| `reply_recv`: `send` on the reply then as `recv`; not armed → dropped without an error | `ipc.rs:119` | `reply_recv_answers_the_caller_then_receives`, `reply_recv_drops_the_reply_without_an_error_when_the_object_is_not_armed`, `reply_recv_needs_send_and_recv_…` | C+T; attached → `busy` is the model's reading (F10) |
| `send`: endpoint or reply object; `send`+`grant`; on an endpoint only to a waiting receiver, else `would_wait`, nothing queued; on a reply object it answers and idles it, `would_wait` if not armed | `ipc.rs:144` | `send_on_an_endpoint_is_delivered_to_a_thread_that_waits_to_receive`, `send_never_queues`, `send_does_not_reach_a_caller_in_the_queue`, `send_on_a_reply_object_answers_the_caller_with_badge_0`, `send_on_an_idle_reply_object_would_wait_and_moves_nothing`, `send_needs_send_…` | C+T |
| `send` on a reply object is the way to answer without receiving | `ipc.rs:144` | `send_on_a_reply_object_answers_the_caller_with_badge_0` | C+T |
| The receiver gets the badge of the capability the sender used; a reply carries badge 0 | `ipc.rs:71`, `341` | `receiver_gets_the_badge_of_the_capability_the_sender_used` | C+T (marks and task are stubbed: `Marks::NONE`, task 0 — stated in the module doc) |
| When a caller disappears the reply object becomes idle | `caps.rs:508` (`Thread` → `unlink`) | `reply_object_becomes_idle_when_its_caller_disappears` | C+T |

## Transfer of capabilities

| Rule | Model | Test | Verdict |
|---|---|---|---|
| Up to 4 slots, each move or derive with rights; a derived capability is a child and keeps its badge | `ipc.rs:263` `listed`, `397` | `moved_capability_leaves_the_sender_for_the_first_slot_of_the_range`, `derived_capability_is_a_child_of_the_sender_s_and_keeps_its_badge` | C+T |
| Checked when the call is made: each slot, `derive`, `grant`; a failure sends nothing | `ipc.rs:82`, `131`, `156` | `listed_slots_are_checked_when_the_call_is_made_and_nothing_is_sent` | C+T |
| A slot listed twice is `invalid`, checked with the slot before the next one | `ipc.rs:277` | `slot_listed_twice_is_invalid`, `listed_slot_is_checked_fully_before_the_next_one` | C+T |
| Header limits before the listed slots | `ipc.rs:76/84` | `header_limits_are_checked_before_the_listed_slots` | C+T |
| Checked again at delivery against what the slots hold then; all or nothing; `caps_dropped` and count 0 otherwise; the words still arrive | `ipc.rs:360` `deliver` | `delivery_transfers_what_the_listed_slot_holds_then`, `transfer_is_dropped_when_the_listed_capability_no_longer_exists_at_delivery`, `…_when_the_listed_slot_fails_a_check_at_delivery`, `transfer_is_all_or_nothing` | C+T |
| The first slots of the receiver's range must be empty, one per capability; a shorter range drops | `ipc.rs:389` | `transfer_is_all_or_nothing`, `transfer_is_dropped_when_the_range_is_shorter_than_the_list` | C+T |
| The depths are refused at delivery and drop the capabilities | `ipc.rs:382` `fits` | `capability_moved_by_ipc_into_a_space_that_cannot_hold_it_is_dropped`, `…_derived_…` | C+T |
| The sender learns it: `send` at once, `call` in the reply header; a `reply_recv` server is not told of a drop in its own reply | `ipc.rs:161`, `341-357` | `send_returns_the_dropped_flag_at_once`, `reply_whose_capabilities_are_dropped_tells_both_sides`, `reply_header_has_the_dropped_flag_of_the_request_with_the_capabilities_of_the_reply`, `reply_recv_transfers_capabilities_both_ways_and_is_not_told_of_a_drop` | C+T |
| Receive range: at most 4, given with `call`/`recv`/`reply_recv`; empty refuses everything and its address is not looked at; slot 0 or beyond the table is `invalid` when the call is made | `lib.rs:580` `window` | `receive_range_has_at_most_4_slots`, `address_of_an_empty_receive_range_is_not_looked_at`, `receive_range_with_slot_0_or_a_slot_beyond_the_table_is_invalid`, `receive_range_through_a_cspace_capability_needs_write` | C+T |

## Notifications

| Rule | Model | Test | Verdict |
|---|---|---|---|
| `signal`: `send`; sets the badge's bits, or bit 0 without a badge; wakes the first waiter with the whole word and clears it | `ipc.rs:176` | `signal_sets_bit_0_or_the_bits_of_the_badge`, `signal_wakes_one_thread_with_the_whole_word_and_clears_it`, `signal_needs_send_and_wait_and_poll_need_recv`, `signal_wait_and_poll_take_a_notify_only` | C+T |
| `wait`: `recv`, returns and clears, else waits | `ipc.rs:208` | `wait_returns_the_word_and_clears_it`, `wait_waits_when_the_word_is_zero_and_poll_would_wait` | C+T |
| `poll`: as `wait`, `would_wait` when zero | `ipc.rs:208` | same | C+T |
| `notify_bind`: `recv` on the notify, `manage` on the endpoint; endpoint 0 unbinds and succeeds if there is none; one each (`busy`) | `ipc.rs:223` | `notify_bind_needs_recv_on_the_notify_and_manage_on_the_endpoint`, `notify_bind_with_endpoint_0_removes_the_binding`, `notify_bind_is_busy_when_either_side_is_already_bound` | C+T; the same pair rebinding is undefined (F6) |
| A pending word is delivered at once on binding | `ipc.rs:255` | `binding_delivers_a_pending_word_at_once_to_a_thread_that_waits_to_receive`, `binding_delivers_nothing_when_the_word_is_zero`, `binding_delivers_nothing_to_a_caller_in_the_queue` | C+T |
| A bound notify: `recv`/`reply_recv` return the notification first, flag set, badge = the word, the word cleared; a `signal` wakes the first receiver if nobody waits on the notify, and its reply object becomes idle; one thread woken per `signal` | `ipc.rs:188` `hand_over`, `ipc.rs:46` | `recv_returns_a_pending_notification_…`, `reply_recv_returns_a_pending_notification_…`, `signal_on_a_bound_notify_wakes_a_thread_that_waits_to_receive`, `signal_on_a_bound_notify_prefers_a_thread_that_waits_on_the_notify`, `signal_on_an_unbound_notify_leaves_receivers_alone` | C+T |
| The binding ends when either object is destroyed | `caps.rs:508` | `binding_ends_when_either_object_is_destroyed`, `check::tests::binding_that_only_the_endpoint_names_is_reported` | C+T |

## Registers

Not modelled; `<arch>` data is out of the model's scope (stated in the module doc). N/A.

---

# `check.rs` invariants, one by one

Every one is checked as its comment says, and every one has a test that fails without it (I
removed 5, 19, 21, 22, 23, 24, 25 and saw the matching test fail each time; the other tests assert
their own invariant's string, so a test cannot pass for the wrong reason).

| # | Checked as the comment says? | Test that fails without it |
|---|---|---|
| 1 | yes (parent exists, older, lists it once) | `parent_that_does_not_exist_is_reported`, `parent_younger_than_its_child_is_reported`, `parent_that_does_not_list_its_child_is_reported` |
| 2 | yes (`is_sorted` = order of derivation, ids grow) | `child_that_names_another_parent_is_reported`, `children_out_of_the_order_of_derivation_are_reported` |
| 3 | yes, including "a root has every right but `exec`, no badge" | `derivation_with_more_rights_…`, `derivation_that_lost_the_badge_…`, `root_capability_without_every_right_is_reported`, `root_capability_with_a_badge_is_reported`, `badge_on_a_capability_that_is_not_for_an_endpoint_or_a_notify_…` |
| 4 | yes | `capability_that_is_neither_a_root_nor_a_derivation_is_reported` |
| 5 | yes | `dead_slot_0_is_reported`, `full_slot_0_is_reported` |
| 6 | yes, both directions | `capability_that_is_not_in_the_slot_it_names_is_reported`, `full_slot_whose_capability_names_another_slot_is_reported` |
| 7 | yes | `capability_space_with_a_partial_segment_is_reported`, `capability_space_over_its_maximum_is_reported` |
| 8 | yes | `capability_whose_object_does_not_exist_is_reported` |
| 9 | yes | `object_whose_root_capability_does_not_exist_…`, `…_names_another_object_…` |
| 10 | yes, both directions | `object_without_the_state_of_its_kind_…`, `state_without_an_object_…` |
| 11 | yes, both branches | `object_taken_from_an_untyped_that_does_not_exist_…`, `…_root_is_not_a_child_of_its_untyped_…`, `start_up_capability_with_a_parent_…` |
| 12 | yes, both halves | `thread_in_the_queue_of_an_endpoint_it_does_not_wait_on_…`, `caller_and_receiver_in_one_queue_…` |
| 13 | yes | `thread_in_the_queue_of_a_notify_it_does_not_wait_on_…`, `notify_with_a_waiter_and_a_word_…` |
| 14 | yes, both directions | `thread_queued_twice_…`, `waiting_thread_that_is_in_no_queue_…` |
| 15 | yes, both directions | `attached_reply_object_…`, `armed_reply_object_…`, `thread_that_waits_for_a_reply_through_an_idle_reply_object_…`, `thread_that_waits_to_receive_with_an_idle_reply_object_…` |
| 16 | yes | `outcome_of_a_thread_that_still_waits_…`, `thread_that_is_not_suspended_and_bound_to_nothing_…` |
| 17 | yes, both directions | `binding_that_only_the_endpoint_names_…`, `binding_that_only_the_notify_names_…` |
| 18 | yes — and it makes the watermark reset mandatory (F1) | `watermark_beyond_the_untyped_…`, `watermark_at_zero_while_something_is_live_…`, `watermark_above_zero_while_nothing_is_live_…` |
| 19 | yes (`1 + segments` per object, matching `take`) | `live_count_that_is_not_the_number_of_live_objects_…` |
| 20 | yes | `tree_deeper_than_64_is_reported` |
| 21 | yes (a topological sweep over "parent" and "root of the space holding it") | `capability_held_in_a_capability_space_that_descends_from_it_…` |
| 22 | yes | `thread_attached_to_a_dying_reply_object_…`, `caller_of_a_dying_reply_object_…` |
| 23 | yes (created-before-the-marker, by identity) | `capability_created_in_a_capability_space_after_it_began_to_die_…` |
| 24 | as written, but the bound cannot be reached by this model's rules (F12) | `walk_of_a_removal_longer_than_192_capabilities_…` (sets the counter by hand), `walk_of_a_removal_is_measured` |
| 25 | yes, both halves | `exec_on_device_memory_…`, `kernel_object_on_device_memory_…` |
| 26 | yes (caps only; every other state names an object checked by 10) | `identity_that_was_not_given_out_…` |

Nothing in `check.rs` claims more than it checks. One deliberate absence: no invariant requires a
thread's `cspace` to be live, which is right — the contract lets a thread be bound to a destroyed
space and every call then returns `gone`.

---

# Behaviour the model decides alone, without a `CONTRACT-GAP` marker

The model carries exactly one marker (`caps.rs:58`, the kinds that `untyped_retype` makes). These
are the other places where it decides, and a kernel written from the contract could differ:

1. The watermark returns to zero when the untyped is empty (F1) — and invariant 18 enforces it.
2. On device memory, a size argument is judged before the device rule, so a kind outside the
   model gives `unsupported` where the contract says `invalid` (F4).
3. The order among the plain arguments of `cap_derive`: rights, badge kind, badge kept, depths
   (F5).
4. `notify_bind` on the pair already bound → `busy` (F6).
5. `thread_read_regs`, `thread_write_regs` and `yield` → `unsupported`, though two of them are in
   the one-core Threads table (F7).
6. `cap_delete` through `via` into a dying space → `gone` (F8).
7. `thread_configure` checks the `aspace` and the fault endpoint and then keeps neither; the model
   documents this in its module header but not with a marker. Consequence: destroying an address
   space or a fault endpoint does not affect the thread at all, which a kernel would not match.
8. The `cap_delete` target slot is left *empty* (descendants are left *dead*). The contract implies
   it through "it acts on the slot" but never says it.
9. The start-up `device` untyped capability has no `exec` (`lib.rs`, `boot`: `all.without(EXEC)`),
   while the contract says the first process gets "every `untyped`, ordinary and device". Invariant
   25 ("no capability for device memory has `exec`") depends on this choice.
10. The header of a notification: label 0, 0 words, 0 capabilities.
11. `Output`'s shape and `Model::apply`'s panic when the thread cannot run are model API, not
    behaviour, but a harness must know them.

# Sequences I tried and could not break

- A capability outliving its parent: `cap_move` of a parent, `cap_delete` of a parent, a derived
  capability moved into another space, IPC move of a parent — all leave invariant 1 holding.
- Use of a freed object: a capability space destroyed while a copy of one of its capabilities sits
  in another space (the copy is `gone`); a reply object destroyed while armed or attached (the
  caller or the receiver is woken, and the object is only removed when its queue is empty); an
  endpoint destroyed with callers and receivers queued (woken one per step, the object destroyed
  last).
- A removal that never ends or does unbounded work: `next_removed` always finishes (a `swept` step
  only leaves a `cspace` root, whose depth the rule strictly grows), each call does at most 32
  steps, and every transition of the walk strictly grows the depth. The `destroy` of a `cspace`
  is O(segments) and `unlink` is O(queue) inside one step, which the contract does not bound (F11
  for the sweep).
- A thread waiting for ever with nothing that can wake it: I found no state where the *model*
  loses the means to wake a thread. Every queue entry can be reached by a call on the object it
  waits on or by destroying that object, and destroying a thread removes it from its queue. The
  waits that can last for ever (a caller whose server died but whose reply object is still held,
  a thread waiting for a signal) are exactly the ones the contract accepts on purpose.

---

# Appendix: mutations run in a scratch copy

`/tmp/dk` (a copy of the repository, original untouched). A mutation "succeeded" when the suite
still passed, i.e. when the rule is not defended by any test.

| # | Mutation | Tests that failed |
|---|---|---|
| M1 | `cap_derive`: depths checked before the rights asked for | **none** |
| M2 | `untyped_retype`: device rule before the size argument | **none** |
| M3 | `notify_bind`: rebinding the same pair allowed | **none** |
| M4 | `space()`: a dying capability space keeps working | 1 |
| M5 | untyped depth `>=` → `>` | 5 |
| M6 | cspace-root depth `>` → `>=` | 4 (incl. property) |
| M7 | depth of a derivation without the +1 | 5 |
| M8 | a slot listed twice accepted | 2 |
| M9 | delivery without the depth check | 4 (incl. property) |
| M10 | the watermark not aligned | 5 |
| M11 | the watermark never returns to zero | 13 (incl. property) |
| M12 | 33 capabilities per removal call | 8 |
| M13 | header limits after the listed slots | 1 |
| M14 | a caller before a pending notification in `recv` | 2 |
| M15 | `thread_configure` on a waiting thread | 1 |
| M16 | a dying capability keeps working | 1 |
| M17 | a capability of a dying object keeps working | 5 (incl. property) |
| M18 | `wait` does not clear the word | 1 |
| M19 | an empty receive range looks at its address | 100 |
| M20 | `thread_resume` without the missing-space check | 6 (incl. property) |
| N1 | `cap_derive`: badge kind before the rights | **none** |
| N2 | `cap_derive`: vacancy before the depths | **none** |
| N3 | a call outside the model `unsupported` before the space check | 2 |
| N4 | a removed capability leaves its slot full | 61 |
| N5 | `signal` prefers the endpoint receiver over a notify waiter | 1 |
| N6 | invariant 5 not checked | 2 |
| N7 | invariant 24 at 4 × 64 | 1 |
| N8 | invariant 21 not checked | 1 |
| N9 | the cspace directory not rounded up | 1 |
| N10 | the segments of a cspace not released | 12 |
| N11 | a space swept in reverse index order | 1 |
| N12 | the target removed before its descendants | 27 |
| N13 | `untyped_retype` without the depth check | 3 |
| N14 | `cspace_grow` past the maximum | 5 |
| N15 | (invalid mutation, no-op) | — |
| N16 | a receive range beyond the table accepted | 1 |
| N17 | the rights of the untyped capability ignored | 8 |
| N18 | any untyped accepted by `cspace_grow` | 6 |
| Q1 | `reply_recv` does not answer | 2 |
| Q2 | `untyped_retype`: vacancy before the depths | **none** |
| Q3 | `cap_move`: vacancy before the depths | 1 |
| Q4 | `cap_derive`: another badge accepted | 1 |
| Q5 | `call` keeps no receive range when it delivers at once | **none** |
| Q6 | `notify_bind` does not deliver a pending word | 1 |
| Q7 | a range shorter than the list accepted | 10 |
| Q8 | a non-empty receive range accepted | 6 |
| Q9 | invariant 22 not checked | 2 |
| Q10 | invariant 23 not checked | 1 |
| Q11 | invariant 19 not checked | 1 |
| Q12 | invariant 25 (device kind) not checked | 1 |
| Q13 | `thread_configure` without `manage` on the cspace | 2 |
| Q14 | a dying object does not stop a use | 7 |

The four mutations that survived are the four findings F3, F5 (twice) and F2, plus F4 and F6
(M2, M3). Everything else is defended.
