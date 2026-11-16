# Review 7: verification of new findings (Hydrogen's N1 to N5, Argon's 1.1), by Opus

Verifier: Claude Opus 5.5. Date: 16 November 2026. I worked alone, without subagents.

- Contract: `Docs/architecture/kernel-interface.md` at `3bc7597`. It is unchanged up to the current Docs `HEAD`; the line numbers below are those of `3bc7597`.
- Model: `dodos-kernel` at `2afc901`, copied to `/tmp/review7-verify-new-opus`. `System::deliver` there panics when an older message of the same `(from, to)` ring is still in flight (`ring_order.patch`).
- Findings judged: N1 to N5 of `2026-11-16-model-review-7-verify-deepseek-by-hydrogen.md` (tests in `verify7_deepseek.rs`), and section 1.1 of `2026-11-16-model-review-7-gemini-argon.md`.
- My tests are in `model/tests/verify_new_opus.rs`, copied with both patches to `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/review7/tests/verify-new-opus/`. **Convention:** each test passes on `2afc901` and asserts the behaviour that makes the finding, or that refutes it. The name says what the model does. All 12 pass at the default page size, at `DODOS_PAGE=16k` and at `DODOS_PAGE=32k`.
- I ran Hydrogen's `n1` to `n5` at all three page sizes. N1, N2, N4 and N5 fail as the report says; N3 passes. The messages match the report's numbers. Hydrogen's figures for N4 at 4 KB are `[(0, 32, 33), (1, 33, 34)]`.

## Summary table

| Finding | Verdict | Side | Severity | How you know |
|---|---|---|---|---|
| N1: `Geometry::valid` accepts a user range end that leaves no root entry for the reserved slot | CONFIRMED | abi | wrong result (machines of the tests only) | run: `n1_valid_accepts_a_user_range_end_that_leaves_no_root_entry_for_the_reserved_slot`; read: lines 258 and 95, `abi/src/lib.rs:451-478`. Hydrogen's `<` correction is not enough |
| N2: a partial `iospace_map` goes on with another page count | CONFIRMED (same fault as F2, not an independent one) | contract (model follows it) | wrong result | run: `n2_a_partial_iospace_map_resumed_with_three_pages_ends_with_three_leaves`; read: lines 282 and 887, and `iospace_map` "As `aspace_map`" (line 333) |
| N3: more state `denied`s falsify line 284; `iospace_attach` has `busy` before and after `denied` | NOT A FAULT (part 1); part 2 only restates F4 | — | — | run: `n3_a_rebadge_is_denied_before_the_state_of_the_destination_is_judged`; read: lines 139, 147, 284, 929. Hydrogen's test passes and shows only what the contract asks |
| N4: device leaves and both nodes' kept leaves write the gate word of a *none* chunk | CONFIRMED IN PART | model | breaks isolation between nodes, availability only (in the model) | run: `n4_both_nodes_count_kept_leaves_in_a_none_chunk_and_one_fills_it_for_the_other` and `n4_an_iospace_leaf_of_device_memory_is_counted_in_a_none_chunk`; broken rules: G4 (line 888) and G2 (line 886). It is F6's fault; no write reaches a word that another node owns |
| N5: `Geometry::valid` accepts page sizes that are not one per level | CONFIRMED | abi | wrong result (machines of the tests only) | run: `n5_valid_accepts_page_sizes_that_one_entry_of_a_level_does_not_map`; read: line 95 |
| Argon 1.1: an identifier word stays taken by a dead generation after a fresh start | CONFIRMED IN PART | contract (model follows it) | wrong result: the device is refused to every other node while the owner's later generation lives | run: `b_after_a_fresh_start_of_its_owner_the_identifier_word_is_denied_to_others` (legal ring order) and the patched copy; read: lines 339, 342, 769-776, 1124. "Permanently" is not true, the claim that memory blocks are swept is wrong, and his second correction as written is wrong (run) |

Count per verdict: CONFIRMED 3 (N1, N2, N5); CONFIRMED IN PART 2 (N4, Argon 1.1); NOT A FAULT 1 (N3); IMPOSSIBLE SCENARIO 0; NOT REPRODUCED 0. New findings: S1 and S2 (siblings of Argon 1.1, confirmed by running), S3 (sibling of N4, confirmed by reading), X1 (a model checker fault found while writing a test, confirmed by running).

---

## N1: CONFIRMED (abi, wrong result)

- **Test:** `n1_valid_accepts_a_user_range_end_that_leaves_no_root_entry_for_the_reserved_slot`.
- **What it asserts:**
  1. The three geometries the model is tested with (x86-64, `SIXTEEN_KB`, `THIRTY_TWO_KB`) all have `user_end == half − (what one root entry maps)`. So the model's own intent is one free root entry below the half.
  2. `Geometry::valid()` accepts `user_end = half` and also `user_end = half − chunk`, and `Model::boot` boots on both. In both cases no whole root entry lies between the user range and the half.
- **Contract:** line 258 says "The range that the next root entry maps forms the reserved slot … the last root entry of the lower half". `abi/src/lib.rs:477` checks `user_end <= 1 << (address_bits − 1)`.
- **Hydrogen's correction falls short.** Hydrogen proposes `<`, which still accepts `half − chunk`. The check that follows line 258 is `user_end <= (1 << (address_bits − 1)) − (1 << (page_shift[0] + (levels − 1) × log2 E))`.
- **Severity:** the validator gives a wrong result for machines that tests build. On real hardware the architecture layer fixes the geometry, so no real machine reaches this.

## N2: CONFIRMED, the same fault as F2 (contract, wrong result)

- **Test:** `n2_a_partial_iospace_map_resumed_with_three_pages_ends_with_three_leaves`.
- **What it asserts:**
  - With `gate_chunks = 1`, an `iospace_map` of a 4-page frame returns `again` after writing part of it.
  - The same call with a page count of 3 goes on and ends with success.
  - The map count of the frame's chunk then holds the leaves of 3 pages, and a further call with count 4 is `busy`: the record is full and no longer partial.
- **Contract:** line 282 defines the resumption identity as "(this aspace, address, first page and rights …)", and G3 (line 887) as "same frame capability, space, address, first page and rights". Neither names the page count. `iospace_map` is "As `aspace_map`, with these differences" (line 333) and lists no difference here.
- **Model:** `Syscall::IoSpaceMap` goes through the same function (`model/src/memory.rs:196-206`).
- **Why it is not independent:** F2's correction, written into the identity sentence, covers both calls, and the model has one function to change. One more point: the model accepts only a count larger than what is already written (`m.count < map.count`). The contract states no such rule.

## N3: NOT A FAULT (part 1); part 2 restates F4

Part 1 claims that five sites falsify line 284 ("the only `denied` judged with the state"). Line 284 sits in the state checks of `aspace_map`, and within that call it is true. None of the five sites is a third kind of state `denied` beside the two that line 139 lists:

| Site | What it is |
|---|---|
| `aspace_protect` (292), `iospace_map` (333) | The class check of a mapping. Line 139 lists it |
| `iospace_attach` with iospace 0 (349) | The owner of a device identifier. Line 139 lists it |
| `cap_derive` re-badge (147) | "`denied` (checked with the plain arguments)": not a state check |
| `task_exempt` (929) | "`denied` otherwise, judged as a right of that slot": not a state check |

- **Test:** `n3_a_rebadge_is_denied_before_the_state_of_the_destination_is_judged`. It derives into a full destination. The same badge gives `no_slot`: the call reaches the state. Another badge gives `denied`: the call stopped at the plain arguments. So the re-badge `denied` is not judged with the state.
- **Hydrogen's test** asserts that the model returns `denied` in each case and `busy` for a kernel device. That is exactly what the contract asks, so the test shows no fault.
- **Part 2** (`busy` before and after `denied` in `iospace_attach`) is F4 again. That rule order is written per call (lines 340-347), and N3 adds nothing to it.
- **What does hold:** the re-badge and `task_exempt` are two more places where line 1540 ("A right is missing") is not literally true. That belongs to F3 (wording).

## N4: CONFIRMED IN PART (model; breaks isolation between nodes, availability only)

**What holds.** Every leaf of device memory or of the global read-only set adds 1 to the map count at index `address >> chunk_shift`. This happens in `aspace_map` and `iospace_map` alike, and at boot. Both nodes then write the same word: the gate word of a chunk whose ownership word is *none*, which no node owns.

- **Rules broken** (both in the contract, broken by the model):
  - G4 (line 888): "It is written only by the owner's gate (or cleared after the owner's death by step R6 …); … so each count has one writer". A *none* chunk has no owner, so no gate may write its count.
  - G2 (line 886): "A page of device memory or of the global read-only set lies in no chunk". So such a leaf belongs in no count at all.
- **Model code:** `count_leaves` and `leaf_chunks` (`model/src/memory.rs:74-108`) take no account of the kind of memory. This is F6's root cause. The `iospace_map` half of N4 is F6 in the sibling call.
- **Correction to Hydrogen:** boot writes the word at all three page sizes, not only at 16 KB and 32 KB as Hydrogen says. At 4 KB the count at boot is 32, as Hydrogen's own output shows. My test asserts a non-zero count at boot on all three geometries.

**The isolation break, shown.** Test `n4_both_nodes_count_kept_leaves_in_a_none_chunk_and_one_fills_it_for_the_other`:

1. It first checks that both nodes' frames over the living part of the machine table lie in one chunk whose ownership word is *none*.
2. It boots with `map_count_max` set to the count at boot + 2.
3. Node 0 maps two leaves of kept memory. Its third mapping is `busy`.
4. Node 1, which has mapped nothing since its start, is refused (`busy`) the mapping of its own kept frame, because of node 0's leaves.
5. Node 0 unmaps one leaf, and node 1's mapping then succeeds.

So one node's user space decides whether another node's mapping succeeds, through a word that belongs to neither. Under the contract (G2) a correct kernel counts no such leaf, and this interference does not exist.

**What falls, or is limited.**

- **No write reaches a word another node owns.** Kept and device pages always fall in *none* chunks: line 768 says *none* "marks a chunk that is not ordinary memory, or is kept". In the example machine these are chunks 0 and 1 at 4 KB, and chunk 0 at 16 KB and 32 KB. Device pages past the end of the table are skipped (`get_mut(chunk) … continue`, `memory.rs:96-99`). So no node's taken chunk or floor, and no node's G14 audit, is touched.
- **On the real maximum the interference is hard to reach.** At `MAP_COUNT_MAX` = 2^32 − 1 it needs about 2^32 leaves summed over all nodes, tens of GiB of table pages. In the model it shows with the reduced maximum that the contract itself names for tests.
- **Suspected, not run:** a kernel written from the model would need atomic read-modify-write on a word that the contract gives one writer. With plain stores it would lose updates.

**Contract wording.** G3 (5), "adjusts the map counts (G4)", reads as if it applied to every entry. Proposed: "(5) for a leaf of ordinary memory, adjusts the map counts of the chunks it touches (G4); a leaf of device memory or of the global read-only set is counted in no word."

## N5: CONFIRMED (abi, wrong result)

- **Test:** `n5_valid_accepts_page_sizes_that_one_entry_of_a_level_does_not_map`.
- **What it asserts:** a geometry with `page_shift [12, 18, 28, 0]`, `entries` 512 and `levels` 3 passes `valid()`, and `Model::boot` boots on it. The first large page is 256 KB, while one entry of the second level maps 2 MB. I set the user range end to `2^38 − 2^30`, so that only the page sizes are at fault.
- **Contract:** line 95 says "A large page is the size one entry of a higher table maps". `valid()` (`abi/src/lib.rs:459-478`) checks only that the sizes increase.
- **Correction:** `page_shift[i] == page_shift[i − 1] + log2 E` for every large page present.
- **Remarks on Hydrogen's report:**
  - Hydrogen's geometry, with `user_end = 1 << 38`, also fills the whole lower half, which is N1.
  - The sub-claim "Large2 > E × chunk" is F10.
  - The level arithmetic is as Hydrogen says, by reading: `(18 − 12) / 9 + 1 = 1` in `tables()` (`model/src/memory.rs:39`).
  - Severity: as for N1, machines of the tests only.

## Argon 1.1: CONFIRMED IN PART (contract; the model follows it)

### The scenario, in legal ring order

I wrote it from the contract. My tests run it on `System` with the ring-order patch, so any out-of-order delivery would panic.

1. Node 1 (generation 1) holds the IOMMU unit role. It makes an iospace and attaches device `0x0010`. Its identifier word becomes *taken* (1, 1) (line 339).
2. Node 0 kills node 1 (`core_stop` kill). The machine runs through the fence, R0 to R5, the take-over of the unit roles by node 0, the barrier and R6. Node 1 is dead (1). R1 cleared the context entry and node 1's iospace died with its generation, but nothing rewrites the identifier word. R6 (line 1110) lists chunks, the grant table and the use table, not identifier words.
3. **Control:** if node 0 attaches the device now, it succeeds by rule 3, because the owner is dead. Test: `b_while_its_owner_is_dead_another_node_takes_the_identifier_word`.
4. Instead, node 0 starts node 1 fresh. Node 1 is live (2).
5. Node 0 attaches the device: `denied`. Node 0 detaches it (iospace 0): `denied`.
6. Node 1, in generation 2, attaches the device and detaches it. Rule 1 allows this, and the word becomes *free*, unclaimed. Node 0 then attaches it.

Test: `b_after_a_fresh_start_of_its_owner_the_identifier_word_is_denied_to_others`, which asserts steps 4 to 6.

### Contract or model?

The contract. The model applies the contract's rules exactly: `Ownership::may_take` (`abi/src/machine.rs:413-432`) and `holds_identifier` (`model/src/memory.rs:547-557`). The contract contradicts itself:

- Line 339: attaching "leaves it *taken* while the device is attached to an iospace of the node; detaching writes it *free*, unclaimed". Line 769: "if the generation is not the owner's current one, or the owner is dead, the block died with that generation and the chunk counts as free". Line 1124: "**After dead**, every ownership word and device entry owned by *X* is free for any live node".
- Against these, lines 771-776 (rules of taking): "1. *X* itself, if the word is free, or taken by a generation of *X* other than *g*; … 3. a node whose member word is **dead** … Any other owner is refused". Line 342: "the device's identifier word is taken by another node that is not dead … (`denied`)".

After the fresh start, no attachment exists, yet the word still reads *taken*, and the rules give it to the owner's later generation alone. R1 to R6 are not at fault: they block the device and clear what they list. The fault is the rule of taking, which judges "dead" and not "this generation is over".

### What falls in Argon's text

- **"Permanently unclaimable"** is not true. A later generation of the owner can take the word and free it (rule 1; step 6 of my test). If that generation dies, rule 3 applies again. What is true: every other node is refused for as long as a later generation of the owner lives, unless that node itself attaches and detaches the device.
- **"Why doesn't this happen for memory blocks? Because R6 (`reclaim_blocks`, `recovery.rs:845-872`) … CASes it to Free … Invariant 38 …"** is wrong.
  - There is no `reclaim_blocks` at `2afc901`. R6 in the model frees only reserve chunks (`free_reserves_of`, `recovery.rs:1056`), as the contract's R6 does.
  - Invariant 38 is "rights of a mapping" (`model/src/check/memory.rs:22`).
  - Chunk words and device entries behave exactly like identifier words: S1 and S2 below.
  - Argon's line numbers (`memory.rs:487/509/539`, `machine.rs:341-351`) do not match `2afc901`. They probably come from a mutated copy.
- **The second correction as written** ("`may_take` checks `self.dead(n) || word.generation() != self.generation(n)` for `Owner::Node(n)`") is wrong. `memory_give` and the destruction of a block write *free* with a node as owner and generation 0 (line 777). With that test, any node could take memory just given to a live node. I ran it in a patched copy (`experiment_rule3_generation.patch` with `ONLY_TAKEN = false`). It breaks the existing `blocks.rs` test `a_word_given_to_another_live_node_is_refused`, the checker's unit test `check::tests::take_of_a_word_the_rules_of_taking_refuse_is_reported`, and my `c_a_run_given_to_a_live_node_is_busy_to_every_other_node`.

### The two corrections

- **(1) R6 frees the identifier words of (X, g).** This works for identifier words, but:
  - it adds a walk of 65,536 words per PCI segment to every R6 and changes R6's bound ("visits each chunk … once");
  - it needs a new gate exception for a non-owner's writes;
  - it leaves S1 and S2 as they are.
- **(2) The rule of taking judges the generation, limited to *taken* words.** This costs one comparison with a word the gate already reads (the owner's member word, which rule 3 needs). It repairs the identifier word and S1 and S2 in one sentence. It writes into the rule what the contract already says in three places:
  - line 769, "counts as free";
  - R3 (line 1104), "Generation *g* is over when *X*'s member word reads dead, or names a generation other than *g*";
  - `role_claim` (line 1221), "taken by a node that is not dead while that node is not dead with that generation".

  **It is safe.** A node gets a new generation only by fresh start from dead, and dead needs the barrier (no context entry names the old generation) and R6. So a word *taken* by a generation that is not the owner's current one belongs to a generation that has passed the barrier and R6: the same justification as rule 3.

  **Run:** in the patched copy with `ONLY_TAKEN = true`, `cargo test --workspace --no-fail-fast` fails exactly my two tests that assert the current behaviour (step 5 now succeeds, and S1/S2's takes now succeed). It fails no existing test, except the three that the ring-order patch alone fails (see "Also seen").

**I would write correction (2) into the contract.** Text ready to paste, replacing rule 3 at line 773:

> 3. a node whose member word is **dead** ([Cores](#cores)), whatever the state and the generation in the word; or, for a word in state *taken*, a node whose member word names a generation other than the one in the word, whatever its state: that generation is over, since a node gets a new generation only after it was dead, past the barrier and R6 (as for a pinned grant, R3);

Two sentences follow from it:

- Line 342: "the device's identifier word is taken, and the rules of taking refuse it to this node, or fails its check (`denied`);".
- Line 1124, the end of the "After dead" sentence: "… and for *X*'s next generation (rule 3 of taking), and a word still *taken* by generation *g* stays so after *X* starts again."

In the model the change goes into `Table::may_take` (`model/src/table.rs:280`) and invariant 52 (`model/src/check/table.rs:112`), as in the experiment patch. The proper form gives `abi::Ownership::may_take` the owner's member word instead of a `dead` flag, together with its Kani proof.

---

## New findings

### S1: a chunk taken by a dead generation is refused to every other node after its owner's fresh start (contract; sibling of Argon 1.1)

- **Test:** `c_after_a_fresh_start_of_its_owner_its_chunk_and_device_entry_are_busy_to_others`.
- **Scenario:** node 1 (generation 1) takes a run; node 0 kills it; node 1 is dead; node 0 starts it fresh.
- **What it asserts:**
  - The chunk's ownership word still reads *taken* (1, 1). R6 clears its map count and page classes, not its word (line 1110).
  - Node 0's `memory_take` is `busy` (line 801, "an owner the rules of taking refuse").
  - Node 1 in generation 2 takes it (rule 1).
- **Control:** `c_while_its_owner_is_dead_another_node_takes_its_chunk_and_device_entry` (rule 3).
- **Severity:** wrong result, weaker than for the identifier word. The memory is not lost: the owner's next generation can take it, and user space reads the ownership table through slot 13. But lines 769 and 1124 say "counts as free" and "free for any live node", and the rules say otherwise. Correction (2) above repairs it.
- **What correction (2) leaves alone:** words *free* with a node as owner. These are memory released or given to that node, and they stay that node's by line 777, as `c_a_run_given_to_a_live_node_is_busy_to_every_other_node` checks.

### S2: a device-table entry taken by a dead generation, the same (contract; sibling of Argon 1.1)

- **Test:** the same test as S1. The device entry of the 2 MB range, taken by node 1 in generation 1, still reads (1, 1) after the fresh start. Node 0's `memory_take` of kind 1 is `busy`, and node 1 in generation 2 takes it.
- **Effect:** a device whose driver node died and was restarted cannot have its registers taken by a new driver on another node. Correction (2) repairs it.

I checked the other words of the living part (line 751), and the per-node state, for the same leftover. None has it:

- **Reserve-coded chunk words:** R6 frees them (line 1110; `free_reserves_of`).
- **Gate words and page classes:** R6 clears them for chunks taken by X's generation and for X's floor; G13 resets them when a chunk is taken.
- **Member words:** owned by no generation.
- **Role words:** fresh start requires "No role word names the node" (line 1031); the barrier vacates reserve and plain roles.
- **Grant and use tables:** R6 frees them, and the serial grows.
- **Context entries:** the barrier requires that none names the generation (line 1124).
- **Pinned grants:** R3 already uses "names a generation other than *g*".
- **Remapping entries and IOAPIC inputs:** R1 clears them, and the rebuild masks inputs that no live node claims.

### S3: G5 cannot refuse the give or destruction of a device entry that is still mapped (contract; sibling of N4; read)

- **What is missing:** G5 (line 889) makes "`memory_give`, the destruction of a block …" require "map count 0". A device page "lies in no chunk" (G2) and has no count (G4). So for a device entry, the gate has nothing to check.
- **Model:** the same gap. `mapped_block` returns `false` for every block that is not a run (`model/src/blocks.rs:253-263`). The counts the model wrongly keeps for device leaves (N4) do not help.
- **What can go wrong:** the local capability tree normally prevents the case. But G is stated against a kernel bug. A buggy node could give its device entry while its leaves to it remain. Its translations would then reach device memory whose entry it no longer owns, which breaks clause 4 of G.
- **Severity:** breaks isolation between nodes under a kernel bug, the case G is written for. Read only; not runnable in the model.
- **Correction:** a leaf count per device entry, written only by its owner's gate, beside the device table (8 bytes per entry, 8,192 + start-up entries). G5 then reads it for a device block.

### X1: invariant 52 fails on node 1 when node 0 legally gives or destroys a block (model checker; panic of the model's check)

- **Test:** `x1_a_give_or_a_destruction_by_node_0_fails_invariant_52_on_node_1`. Node 0 takes a run and gives it to node 1. `System::check()` returns `Err("node 1: 52: write of an ownership word")`. A destruction (`cap_delete` of a block) by node 0 does the same.
- **Cause:**
  - The write log of the current event (`table.writes`) is part of the table that `System` shares with every node.
  - In `check_table`, the branch for a release (`after_state == 1`, `model/src/check/table.rs:119-143`) asks `mine(write.before)`. That judges the word against `node`, the node that runs the check, and not against `write.writer`. The branch for a take uses `write.writer`.
- **Why nothing caught it:** no existing `System` test makes a give or a destruction succeed. The one in `gate_attack.rs:304` is refused.
- **Correction:** judge the release against `write.writer` and its generation.

## Also seen

The ring-order patch makes three existing tests panic with "ring order: an older message from 1 to 0 is still in flight":

- `nodes.rs`: `a_stale_remote_capability_sent_home_is_dropped` and `revoking_a_mapped_grant_waits_for_the_holder_then_returns_again`;
- `recovery.rs`: `a_holder_refuses_a_request_of_another_epoch_even_when_it_holds_the_role_again`.

Their scenarios use a delivery order that one ring per ordered pair of nodes cannot produce. I did not judge whether the property each of them guards can be reached in a legal order.

## Appendix: full text of `model/tests/verify_new_opus.rs`

```rust
//! Verification of N1 to N5 (review 7, DeepSeek verified by Hydrogen), of
//! section 1.1 of Argon's report (an identifier word held by a generation
//! that no longer exists), and of the siblings of the latter.
//!
//! Convention: every test PASSES on `2afc901` (with the ring-order patch of
//! `System::deliver`) and asserts the observed behaviour that the report
//! names as the finding, or as its refutation. Where a test shows a fault,
//! its name says what the model does, not what it should do.

mod common;

use dodos_abi::ObjectKind::{ASpace, Endpoint, Frame, IoSpace};
use dodos_abi::*;
use dodos_model::*;

const DONE: Outcome = Ok(Output::Done);
const WAITS: Outcome = Ok(Output::Waits);
const MS: u64 = 1_000_000;
const UT: SlotAddr = SlotAddr::own(common::UNTYPED);
const CONTROL: SlotAddr = SlotAddr::own(START_SLOT_MEMORY_CONTROL);
const LIVING: SlotAddr = SlotAddr::own(START_SLOT_MACHINE_LIVING);
const IOMMU: SlotAddr = SlotAddr::own(18);
const VADDR: u64 = 1 << 30;
/// A device identifier no kernel uses (the kernel's own is 0x00f8).
const DEV: u64 = 0x0010;

const fn s(index: u32) -> SlotAddr {
    SlotAddr::own(index)
}

fn retype(kind: ObjectKind, size: u64, destination: u32) -> Syscall {
    Syscall::UntypedRetype {
        untyped: UT,
        kind,
        size,
        page: PageSize::Page as u64,
        memory: MemoryType::WriteBack as u64,
        destination: s(destination),
    }
}

fn map(kind: ObjectKind, space: u32, frame: SlotAddr, at: u64, count: u64) -> Syscall {
    let map = Map {
        space: s(space),
        frame,
        untyped: UT,
        address: at,
        first: 0,
        count,
        rights: Rights::READ.bits(),
    };
    match kind {
        ASpace => Syscall::ASpaceMap(map),
        _ => Syscall::IoSpaceMap(map),
    }
}

fn attach(iospace: SlotAddr, device: u64) -> Syscall {
    Syscall::IoSpaceAttach {
        iommu: IOMMU,
        iospace,
        device,
    }
}

fn take(kind: u64, place: u64, size: u64, destination: u32) -> Syscall {
    Syscall::MemoryTake {
        control: CONTROL,
        kind,
        place,
        size,
        destination: s(destination),
    }
}

/// The machine of `System`, every invariant after every event. `System`
/// carries the ring-order patch: `deliver` panics when an older message of
/// the same ring is still in flight.
struct S {
    sys: System,
    t: Vec<ObjId>,
}

impl S {
    fn on(machine: &Machine) -> Self {
        let (sys, t) = System::boot(machine).unwrap();
        Self { sys, t }
    }

    #[track_caller]
    fn call(&mut self, node: u16, call: Syscall) -> Outcome {
        let outcome = self.sys.apply(node, self.t[node as usize], call);
        assert_eq!(self.sys.check(), Ok(()));
        outcome
    }

    /// A call that succeeds, at once or after the role holder answers.
    #[track_caller]
    fn ok(&mut self, node: u16, call: Syscall) {
        let outcome = self.call(node, call);
        assert!(outcome == DONE || outcome == WAITS, "{outcome:?}");
        self.run(MS);
    }

    #[track_caller]
    fn run(&mut self, ns: u64) {
        let to = self.sys.now() + ns;
        while self.sys.now() < to {
            let at = (self.sys.now() + MS / 10).min(to);
            self.sys.run(at, MS / 10);
            assert_eq!(self.sys.check(), Ok(()));
        }
    }

    /// Node 0 kills node 1 (generation 1); the machine runs until it is dead.
    #[track_caller]
    fn kill_1(&mut self) {
        let stop = Syscall::CoreStop {
            core: s(17),
            mode: CORE_STOP_KILL,
        };
        assert_eq!(self.call(0, stop), DONE);
        self.run(10 * MS);
        let member = self.sys.member(1);
        assert_eq!((member.state(), member.generation()), (MemberState::Dead, 1));
    }

    /// Node 0 starts node 1 fresh: generation 2, its own start-up state.
    #[track_caller]
    fn restart_1(&mut self) {
        let start = Syscall::CoreStart {
            core: s(17),
            mode: CORE_START_FRESH,
            image: 0,
            module: 0,
        };
        assert_eq!(self.call(0, start), DONE);
        let member = self.sys.member(1);
        assert_eq!((member.state(), member.generation()), (MemberState::Live, 2));
        self.t[1] = self.sys.node(1).object_at_start(START_SLOT_THREAD);
    }
}

// ---------------------------------------------------------------------------
// Argon 1.1: the identifier word of a dead generation, after a fresh start.
// ---------------------------------------------------------------------------

/// Node 1 (generation 1, holder of the IOMMU unit role) attaches `DEV`;
/// node 0 kills it; the barrier holds and node 1 is dead (generation 1).
fn device_attached_by_node_1_which_dies() -> S {
    let mut m = S::on(&Machine::example());
    m.ok(1, retype(IoSpace, 0, 100));
    m.ok(1, attach(s(100), DEV));
    m.kill_1();
    m
}

#[test]
fn b_while_its_owner_is_dead_another_node_takes_the_identifier_word() {
    let mut m = device_attached_by_node_1_which_dies();
    m.ok(0, retype(IoSpace, 0, 100));
    // Rule 3 of taking: the owner's member word reads dead.
    m.ok(0, attach(s(100), DEV));
}

#[test]
fn b_after_a_fresh_start_of_its_owner_the_identifier_word_is_denied_to_others() {
    let mut m = device_attached_by_node_1_which_dies();
    m.restart_1();
    m.ok(0, retype(IoSpace, 0, 100));
    // Generation 1 of node 1 is over, but its word still reads taken
    // (1, 1), and node 1 is not dead: rule 3 no longer applies.
    assert_eq!(m.call(0, attach(s(100), DEV)), Err(Error::Denied));
    assert_eq!(m.call(0, attach(SlotAddr::NONE, DEV)), Err(Error::Denied));
    // Rule 1: generation 2 of node 1 may take it, and only it; attaching
    // and detaching there frees the word, and then node 0 attaches.
    m.ok(1, retype(IoSpace, 0, 100));
    m.ok(1, attach(s(100), DEV));
    m.ok(1, attach(SlotAddr::NONE, DEV));
    m.ok(0, attach(s(100), DEV));
}

// ---------------------------------------------------------------------------
// Siblings: the ownership word of a chunk, the word of a device entry.
// ---------------------------------------------------------------------------

/// A run of one chunk well past the floors and the reserves.
fn free_run(m: &S) -> (u64, u64) {
    let geometry = m.sys.node(0).geometry();
    let chunk = geometry.chunk();
    let ram = Machine::example_on(geometry).memory[4].base;
    (ram + 64 * chunk, u64::from(chunk.trailing_zeros()))
}

fn device_index(m: &S) -> u64 {
    let node = m.sys.node(0);
    (0..node.device_count())
        .find(|&i| node.device_entry(i).base() == 2 << 20)
        .unwrap() as u64
}

#[test]
fn c_while_its_owner_is_dead_another_node_takes_its_chunk_and_device_entry() {
    let mut m = S::on(&Machine::example());
    let (place, size) = free_run(&m);
    let index = device_index(&m);
    m.ok(1, take(0, place, size, 101));
    m.ok(1, take(1, index, 0, 102));
    m.kill_1();
    m.ok(0, take(0, place, size, 101));
    m.ok(0, take(1, index, 0, 102));
}

#[test]
fn c_after_a_fresh_start_of_its_owner_its_chunk_and_device_entry_are_busy_to_others() {
    let mut m = S::on(&Machine::example());
    let (place, size) = free_run(&m);
    let index = device_index(&m);
    let chunk = place >> m.sys.node(0).geometry().chunk_shift();
    m.ok(1, take(0, place, size, 101));
    m.ok(1, take(1, index, 0, 102));
    m.kill_1();
    m.restart_1();
    // The words still read taken by generation 1 of node 1 (R6 clears the
    // map counts and page classes of the chunk, not its ownership word).
    let word = Ownership::from_raw(m.sys.node(0).ownership(chunk)).unwrap();
    assert_eq!(
        (word.state(), word.owner(), word.generation()),
        (OwnState::Taken, Owner::Node(1), 1)
    );
    let entry = m.sys.node(0).device_entry(index as usize).owner;
    assert_eq!((entry.owner(), entry.generation()), (Owner::Node(1), 1));
    // Node 0 is refused both (`busy`, rules of taking); generation 2 of
    // node 1 takes both (rule 1).
    assert_eq!(m.call(0, take(0, place, size, 101)), Err(Error::Busy));
    assert_eq!(m.call(0, take(1, index, 0, 102)), Err(Error::Busy));
    m.ok(1, take(0, place, size, 101));
    m.ok(1, take(1, index, 0, 102));
}

// ---------------------------------------------------------------------------
// N4: the gate word of a chunk that no node owns, written by both nodes.
// ---------------------------------------------------------------------------

#[test]
fn n4_both_nodes_count_kept_leaves_in_a_none_chunk_and_one_fills_it_for_the_other() {
    let machine = Machine::example();
    let probe = S::on(&machine);
    let shift = probe.sys.node(0).geometry().chunk_shift();
    let page = probe.sys.node(0).geometry().page();
    let base = |m: &S, n: u16| m.sys.node(n).frame_at(m.t[n as usize], LIVING).unwrap().2;
    // The living part of the machine table is one range, kept: both nodes'
    // frames over it lie in the same chunk, whose ownership word is none.
    let chunk = base(&probe, 0) >> shift;
    assert_eq!(base(&probe, 1) >> shift, chunk);
    assert_eq!(probe.sys.node(0).ownership(chunk), Ownership::none().raw());
    // Both nodes' start-up spaces already count kept leaves in it.
    let at_boot = probe.sys.node(0).map_count(chunk);
    assert!(at_boot > 0, "boot counts kept leaves: {at_boot}");

    // The maximum the model is tested with, two leaves above the count of
    // the start-up spaces.
    let mut m = S::on(&Machine {
        map_count_max: at_boot + 2,
        ..machine
    });
    for (n, space) in [(0, 100), (1, 100)] {
        m.ok(n, retype(ASpace, 0, space));
    }
    for copy in 110..113 {
        let derive = Syscall::CapDerive {
            source: LIVING,
            destination: s(copy),
            rights: Rights::READ.bits(),
            badge: 0,
        };
        m.ok(0, derive);
    }
    let count = |m: &S| m.sys.node(0).map_count(chunk);
    // Node 0 maps two leaves of kept memory: its gate writes the word.
    m.ok(0, map(ASpace, 100, s(110), VADDR, 1));
    m.ok(0, map(ASpace, 100, s(111), VADDR + page, 1));
    assert_eq!(count(&m), at_boot + 2);
    assert_eq!(
        m.call(0, map(ASpace, 100, s(112), VADDR + 2 * page, 1)),
        Err(Error::Busy)
    );
    // Node 1, which has mapped nothing since its start, is refused the
    // mapping of its own kept frame: `busy`, because of node 0's leaves.
    assert_eq!(m.call(1, map(ASpace, 100, LIVING, VADDR, 1)), Err(Error::Busy));
    // Node 0 unmaps one leaf; node 1's mapping now succeeds, and its gate
    // writes the same word.
    m.ok(0, Syscall::ASpaceUnmap(s(110)));
    m.ok(1, map(ASpace, 100, LIVING, VADDR, 1));
    assert_eq!(count(&m), at_boot + 2);
}

#[test]
fn n4_an_iospace_leaf_of_device_memory_is_counted_in_a_none_chunk() {
    let (mut k, t) = Model::boot(&Machine::example()).unwrap();
    common::take_device(&mut k, t);
    let frame = Syscall::UntypedRetype {
        untyped: SlotAddr::own(common::DEVICE),
        kind: Frame,
        size: 1,
        page: PageSize::Page as u64,
        memory: MemoryType::Uncached as u64,
        destination: s(101),
    };
    assert_eq!(k.apply(t, frame), DONE);
    assert_eq!(k.apply(t, retype(IoSpace, 0, 100)), DONE);
    let base = k.frame_at(t, s(101)).unwrap().2;
    let chunk = base >> k.geometry().chunk_shift();
    assert_eq!(k.ownership(chunk), Ownership::none().raw());
    let before = k.map_count(chunk);
    assert_eq!(k.apply(t, map(IoSpace, 100, s(101), VADDR, 1)), DONE);
    assert_eq!(k.check(), Ok(()));
    assert_eq!(k.map_count(chunk), before + 1);
}

// ---------------------------------------------------------------------------
// N1: a user range end with no root entry left for the reserved slot.
// ---------------------------------------------------------------------------

#[test]
fn n1_valid_accepts_a_user_range_end_that_leaves_no_root_entry_for_the_reserved_slot() {
    let base = Machine::example().geometry;
    let bits = base.address_bits();
    let half = 1u64 << (bits - 1);
    // What one root entry maps.
    let root = 1u64 << (u32::from(base.page_shift[0]) + (base.levels - 1) * base.entries.trailing_zeros());
    // The geometries the model is tested with leave exactly one root entry.
    for g in [dodos_abi::x86_64::GEOMETRY, SIXTEEN_KB, THIRTY_TWO_KB] {
        let h = 1u64 << (g.address_bits() - 1);
        let r = 1u64 << (u32::from(g.page_shift[0]) + (g.levels - 1) * g.entries.trailing_zeros());
        assert_eq!(g.user_end, h - r);
    }
    // The whole lower half, and the lower half less one chunk (which the
    // `<` that Hydrogen proposes would still accept): both valid, and in
    // both no whole root entry lies between the user range and the half.
    for user_end in [half, half - base.chunk()] {
        let g = Geometry { user_end, ..base };
        assert!(g.valid());
        assert!(user_end > half - root);
        assert!(Model::boot(&Machine::example_on(g)).is_ok());
    }
}

// ---------------------------------------------------------------------------
// N2: a partial `iospace_map` goes on with another page count.
// ---------------------------------------------------------------------------

#[test]
fn n2_a_partial_iospace_map_resumed_with_three_pages_ends_with_three_leaves() {
    let mut machine = Machine::example();
    machine.gate_chunks = 1;
    let (mut k, t) = Model::boot(&machine).unwrap();
    for call in [retype(IoSpace, 0, 100), retype(Frame, 4, 101)] {
        // The clearing of 64 KB per step: a frame of 4 pages of 32 KB
        // takes two calls.
        let mut outcome = Err(Error::Again);
        for _ in 0..8 {
            outcome = k.apply(t, call.clone());
            if outcome != Err(Error::Again) {
                break;
            }
        }
        assert_eq!(outcome, DONE);
    }
    let chunk = k.frame_at(t, s(101)).unwrap().2 >> k.geometry().chunk_shift();
    let before = k.map_count(chunk);
    // One chunk checked per call: the first call writes part of it.
    assert_eq!(k.apply(t, map(IoSpace, 100, s(101), VADDR, 4)), Err(Error::Again));
    let first = k.map_count(chunk) - before;
    // The same call with three pages goes on, and ends.
    let mut outcome = Err(Error::Again);
    for _ in 0..64 {
        outcome = k.apply(t, map(IoSpace, 100, s(101), VADDR, 3));
        if outcome != Err(Error::Again) {
            break;
        }
    }
    assert_eq!(outcome, DONE);
    assert_eq!(k.check(), Ok(()));
    // Three quarters of the leaves of four pages.
    let all = k.map_count(chunk) - before;
    assert!(first < all && all % 3 == 0, "first {first}, all {all}");
    // The record is full and not partial: the first count is gone.
    assert_eq!(k.apply(t, map(IoSpace, 100, s(101), VADDR, 4)), Err(Error::Busy));
}

// ---------------------------------------------------------------------------
// N3: the `denied` of a re-badge is judged with the plain arguments.
// ---------------------------------------------------------------------------

#[test]
fn n3_a_rebadge_is_denied_before_the_state_of_the_destination_is_judged() {
    let (mut k, t) = Model::boot(&Machine::example()).unwrap();
    assert_eq!(k.apply(t, retype(Endpoint, 0, 100)), DONE);
    let derive = |source, destination, badge| Syscall::CapDerive {
        source: s(source),
        destination: s(destination),
        rights: Rights::ALL.bits(),
        badge,
    };
    assert_eq!(k.apply(t, derive(100, 101, 7)), DONE);
    // Destination 100 is full: the same badge reaches the state (no_slot),
    // another badge stops at the plain arguments (denied).
    assert_eq!(k.apply(t, derive(101, 100, 7)), Err(Error::NoSlot));
    assert_eq!(k.apply(t, derive(101, 100, 8)), Err(Error::Denied));
}

// ---------------------------------------------------------------------------
// N5: page sizes that are not one per level.
// ---------------------------------------------------------------------------

#[test]
fn n5_valid_accepts_page_sizes_that_one_entry_of_a_level_does_not_map() {
    // 4 KB pages, 512 entries: one entry of the second level maps 2 MB,
    // yet the first large page is 256 KB. The user range end leaves one
    // root entry, so that only the page sizes are at fault (Hydrogen's
    // geometry, with 1 << 38, also fills the lower half: N1).
    let g = Geometry {
        page_shift: [12, 18, 28, 0],
        entries: 512,
        levels: 3,
        user_end: (1 << 38) - (1 << 30),
    };
    assert_ne!(g.page_shift[1] - g.page_shift[0], 9);
    assert!(g.valid());
    assert!(Model::boot(&Machine::example_on(g)).is_ok());
}

/// What the second correction of Argon must keep: a run given to a live
/// node is free with that node as owner and generation 0, and no other
/// node takes it (rules of taking: only rule 1, for the node named).
#[test]
fn c_a_run_given_to_a_live_node_is_busy_to_every_other_node() {
    let mut m = S::on(&Machine::example());
    let (place, size) = free_run(&m);
    m.ok(0, take(0, place, size, 101));
    let give = Syscall::MemoryGive {
        control: CONTROL,
        untyped: s(101),
        node: 1,
    };
    // X1: the event of the give fails invariant 52 on node 1 (below).
    assert_eq!(m.sys.apply(0, m.t[0], give), DONE);
    m.run(MS);
    let chunk = place >> m.sys.node(0).geometry().chunk_shift();
    let word = Ownership::from_raw(m.sys.node(0).ownership(chunk)).unwrap();
    assert_eq!(
        (word.state(), word.owner(), word.generation()),
        (OwnState::Free, Owner::Node(1), 0)
    );
    assert_eq!(m.call(0, take(0, place, size, 101)), Err(Error::Busy));
    m.ok(1, take(0, place, size, 101));
}

/// X1: invariant 52 judges a release in the write log of the event (shared
/// by every node of `System`) against the node that checks, not the node
/// that wrote: a legal give, or a legal destruction of a block, by node 0
/// fails the check of node 1.
#[test]
fn x1_a_give_or_a_destruction_by_node_0_fails_invariant_52_on_node_1() {
    let mut m = S::on(&Machine::example());
    let (place, size) = free_run(&m);
    let broken = Err("node 1: 52: write of an ownership word".to_string());
    m.ok(0, take(0, place, size, 101));
    let give = Syscall::MemoryGive {
        control: CONTROL,
        untyped: s(101),
        node: 1,
    };
    assert_eq!(m.sys.apply(0, m.t[0], give), DONE);
    assert_eq!(m.sys.check(), broken);
    m.run(MS);
    m.ok(1, take(0, place, size, 101));
    m.ok(0, take(0, place + (2 << m.sys.node(0).geometry().chunk_shift()), size, 102));
    assert_eq!(m.sys.apply(0, m.t[0], Syscall::CapDelete(s(102))), DONE);
    assert_eq!(m.sys.check(), broken);
}
```
