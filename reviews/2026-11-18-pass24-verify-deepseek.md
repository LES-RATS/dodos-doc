# Targeted verification of pass 24 (D-142), by DeepSeek

**Date:** 18 November 2026. **Verified:** D-142 as written in `architecture/kernel-interface.md` and `decisions/README.md` of `Docs` (`git diff 4446a12 HEAD`, HEAD `6137483`) and the reference model on branch `model` of `dodos-kernel` (`git diff b2ed55d HEAD`, HEAD `f1f74be`). **Where:** a clone at `/private/tmp/dodos-verify24`; the model was never edited in place. Line numbers are those of `kernel-interface.md` at `6137483`.

**Verdict in one paragraph.** I could not break claims 1 to 4. Every correction this pass makes turns at least one test red when I revert it by hand, and eleven tests of my own that hunt for reused memory, a lost node, a wait that never ends and a message that is harmful only on a resuming node all pass. I found no high finding. I found four low ones (two sentences that are wrong about what the model does, one rule with no test, one quotation that reads as a paraphrase) and one medium one: the new bound of the first map under a grant (C4) has code but no test, so nothing would fail if the sentence were deleted.

---

## 1. What I ran

| What | Result |
|---|---|
| `cargo test -p dodos-model` on the pristine clone (`model`, `f1f74be`) | 663 tests in `--lib` and 627 in the integration targets, all green, 1 ignored |
| `nix develop -c ./verify` (fmt, clippy `-D warnings`, all tests, three page geometries) on the pristine clone | passes |
| Seven hand reverts of the corrections, each with the whole suite (section 3) | each turns tests red |
| Eleven tests of my own against claims 1 to 4 and 6 (section 4) | 11 pass; the suite with them is 674 in `--lib`, green |

My tests are in the clone only, at `model/src/scenarios/verify24.rs`, with one line added to `model/src/scenarios/mod.rs` (`#[cfg(test)] mod verify24;`). Neither repository was modified; the only file I add to one is this report.

## 2. Findings

### Finding 1 (medium): the first map under a grant — C4 — has code and no test, and the model reaches the new half of the sentence only by accident

**The text.** Line 914, *Memory under a grant*: "and a first map of a frame just received waits until its sender has consumed the answer, at most the latency of a kernel ring (one period of the recovery reserve under full load) while the granting node is live; while it is sealed, until it resumes (at most `SEAL_NS`), and once it is accused the map returns `gone`".

**What holds it.** `model/src/memory.rs:572`: `if !entry.answered { return Err(Error::Again); }`. That code was written for D-141 and is unchanged by this pass (`git show b2ed55d:model/src/memory.rs` line 568 has it). The three cases of the sentence behave correctly: I proved them by run (section 4, `claim6_the_first_map_waits_while_the_granter_is_sealed_and_is_gone_once_accused`): `again` while the granting node is live and while it is sealed, `gone` at once once it is accused.

**Why it is a finding.** No test in the tree exercises `!entry.answered`: `grep` over `model/src/scenarios/` finds `answered` only in the `LEAK` invariant (`checker.rs:435`) and in states where it is true. The pass's own file `pass24.rs` settles every grant before its first map, so the sentence the pass *changed* (the sealed bound, and `gone` once accused) has nothing that would fail if it were deleted. The accused half is in fact not held by the grant entry at all: the map is `gone` because the remote capability is invalid once the member word leaves live, which no test ties to this sentence. Severity medium by the scale of the brief ("a missing test of a rule"), not high: the rule is safe, it is simply unpinned.

### Finding 2 (low): the changes list says the model's start-up layout reserves the VT-d tables; it does not

**The text.** Line 1794, *Since D-142*: "… and R2 not done while a use entry naming the dead granter's generation counts a leaf (`reclaim_step`, `audited`); the four failed-unit scenarios of D-142 and the granter's death after one; **the start-up layout reserving 1 MB and 4 KB per VT-d unit**."

**What holds it.** Nothing in the model. `abi/src/x86_64.rs:122` adds `VTD_UNIT_TABLE_BYTES = 4096 + 256 * 4096` with `abi/src/tests.rs:794` asserting it, which holds the *number*. But the model's start-up layout reserves no such memory: `Model::Iommu` (`model/src/lib.rs:690`) holds a unit index, its attached devices, their order and their detaching set, and no tables; `Machine::kept_ranges` (`model/src/boot.rs:663`) is the kept ranges, the image, the crash areas and the feedback tables. `grep -r VTD_UNIT_TABLE_BYTES` over the repository finds the constant and its test and nothing else. Proved by reading and by the search; no run can prove a sentence about a layout that is not modelled.

**Note.** The IOMMU sentence itself (line 341: "a root table of 4 KB and up to 256 context tables of 4 KB, 1 MB and 4 KB in all (D-142: \"1 MB in all\" left out the root table)") is now arithmetically right, and `abi/` holds it with a test. Only the claim that the *model*'s layout reserves it is wrong.

### Finding 3 (low): "with its check beside `x86_64::dr7_valid`" — the model has no such check

**The text.** Line 1794, the same list: "the ARM64 user mask of a breakpoint's and a watchpoint's control (`DBGBCR<n>_EL1` and `DBGWCR<n>_EL1`: HMC 0, SSCE 0, SSC 0b00, PMC or PAC 0b10, BT 0b0000, WT 0) with its check beside `x86_64::dr7_valid`".

**What holds it.** `abi/src/aarch64.rs` (new, `dbgbcr_valid`, `dbgwcr_valid`, the two user masks), `abi/src/tests.rs:798` and after (two tests) and `abi/src/lib.rs:1378` (two Kani proofs). That is `abi/`, not the model. The model's one check of a breakpoint control word is `model/src/faults.rs:201`, `REG_DR7 => !dr7_valid(word)`; the register block has no ARM64 breakpoint or watchpoint word at all (`REG_DR0..=REG_DR3`, `REG_DR7` are x86-64 words), so on ARM64 the model judges nothing beside `dr7_valid`. `grep -r dbgbcr_valid` outside `abi/src/aarch64.rs` finds only `abi/src/lib.rs` (the proofs) and `abi/src/tests.rs`. Proved by reading and search. Low: the rule is enforced where it is judged, and the sentence overstates where the check lives.

### Finding 4 (low): C11's `memory_split` half has no test, and cannot be reached from a run

**The text.** Line 1079, G6: "A chunk under a live grant is never `given` (the anchor is a descendant of the block's capability, so `memory_give` and `memory_split` are `busy` on it: D-142)."

**What holds it.** The `memory_give` half: `Model::idle_block` (`model/src/memory.rs`) refuses a block capability with a child or a live derivation, and `mapped_block` refuses a non-zero map count; tested by `pass24::pinned_for_ever` (a `memory_give` on the block of a grant that is pinned is `busy`) and by my `claim6_a_chunk_under_a_live_grant_is_never_given_or_split`. The `memory_split` half: `memory_split` refuses only through `mapped_block` (a device entry's leaf count), and it is `invalid` for any run (`if let Some(Block::Entry(index)) = … else { return Err(Error::Invalid) }`). A device entry that holds a granted frame's chunk *and* has a leaf count of its own needs the granting node to map device memory it granted — a state I could not build from user calls in the time of this verification, and no test builds it either. So D-142's reason ("the anchor is a descendant") is enforced for the give, through the frame capability's children, and not for the split, and neither half walks the anchor: the model refuses because a *child capability* exists, not because a grant entry is live. Proved by run (the split is `invalid` in the state I built, and my test records that) and by reading.

### Finding 5 (low, by reading only): a quoted SDM sentence reads as a paraphrase

**The text.** Line 1667: "(2) the `#DB` vector runs on a stack of its own, an IST entry of the core's TSS (\"the processor loads the value pointed by an IST pointer into the RSP\", §7.14.5)".

Two things make this worth flagging rather than passing: "pointed **by**" is not the SDM's English (it writes "pointed to by"), which suggests a hand-typed paraphrase presented as a quotation; and I could not open §7.14.5 of 325462-093 to check either the wording or the section (see section 6). Severity low — a citation whose form is wrong, not a rule that is wrong. The other four quotations of this pass I did verify (section 5).

## 3. The seven corrections, reverted one at a time

Each revert is one hand edit in the clone, then the **whole** suite (`cargo test -p dodos-model`, not only `--lib`), then a restore. "Red" counts failing test functions.

| # | Correction reverted | Edit | Red |
|---|---|---|---|
| a | a use entry is freed only at a count of 0 | `free_use` removes the entry whatever its count | **13** |
| b | a grant is pinned on a kept count | the two `pin(grant)` calls removed (`revoke_answered`, `release_received`) | **5** |
| c | R2 undone while a kept count names the generation | `|| self.kept_count(node, g)` removed from `reclaim_step` | **7** |
| d | a resume does not wait for such an R2 | `let held = false;` in `resume_step` | **4** |
| e | a resuming node reads its rings from the end of R0 on | `consumes()` returns `ready` only | **4** |
| f | no thread chosen during a resume | `.filter(|_| !self.resuming)` removed from `pick` | **1** |
| g | `node_send` does not reuse a grant whose anchor slot is still taken | `&& self.anchor(g).is_none()` removed | **1** |

The red tests:

- **(a)** `pass24::a_granter_dead_under_a_leaf_a_running_holder_counts_is_reported`, `pass24::a_granter_killed_under_a_count_a_failed_unit_kept_is_never_dead`, `pass24::a_holder_resumed_under_a_count_a_failed_unit_kept_runs_again_beside_a_fenced_granter`, `…_beside_an_unfenced_granter`, `pass24::a_pending_release_sent_at_a_count_above_0_keeps_the_use_entry`, `pass24::a_release_crossing_a_revoke_at_a_count_above_0_pins_and_keeps_the_credit`, `pass24::a_resume_whose_unit_request_is_answered_failed_runs_again_and_the_granter_never_dies`, `pass24::a_unit_failed_before_the_map_pins_the_grant`, `pass24::a_unit_failed_during_a_revocation_pins_the_grant`, `pass24::a_unit_failed_under_a_remote_frame_pins_the_grant_at_the_holders_removal`, `pass24::a_use_entry_kept_without_a_root_is_never_written_for_another_grant`, `pass24::r0_drops_a_pending_release_at_a_count_above_0_and_keeps_the_use_entry`, `explore::a_unit_fails_under_a_granted_frame_at_any_step_of_its_use`.
- **(b)** `pass24::a_release_crossing_a_revoke_at_a_count_above_0_pins_and_keeps_the_credit`, `pass24::a_unit_failed_before_the_map_pins_the_grant`, `pass24::a_unit_failed_during_a_revocation_pins_the_grant`, `pass24::a_unit_failed_under_a_remote_frame_pins_the_grant_at_the_holders_removal`, `explore::a_unit_fails_under_a_granted_frame_at_any_step_of_its_use`.
- **(c)** `pass24::a_granter_dead_under_a_leaf_a_running_holder_counts_is_reported`, `pass24::a_granter_killed_under_a_count_a_failed_unit_kept_is_never_dead`, `pass24::a_holder_resumed_under_a_count_a_failed_unit_kept_runs_again_beside_a_fenced_granter`, `pass24::a_resume_whose_unit_request_is_answered_failed_runs_again_and_the_granter_never_dies`, `pass24::a_revoke_in_flight_when_the_granting_node_is_killed_leaves_a_credit_no_check_judges`, `pass24::r0_drops_a_pending_release_at_a_count_above_0_and_keeps_the_use_entry`, `explore::…`.
- **(d)** `pass24::a_holder_resumed_under_a_count_a_failed_unit_kept_runs_again_beside_a_fenced_granter`, `…_beside_an_unfenced_granter`, `pass24::a_resume_whose_unit_request_is_answered_failed_runs_again_and_the_granter_never_dies`, `explore::…`.
- **(e)** `pass24::a_resume_reads_the_answer_of_another_nodes_unit_during_r2_and_ends`, `pass24::a_resume_whose_unit_request_is_answered_failed_runs_again_and_the_granter_never_dies`, `pass24::an_answer_read_during_the_resumes_r2_wakes_its_thread_which_runs_only_after_the_resume`, `explore::…`.
- **(f)** `pass24::an_answer_read_during_the_resumes_r2_wakes_its_thread_which_runs_only_after_the_resume`.
- **(g)** `verify13::a_grant_whose_anchor_stays_is_not_reused_by_the_next_node_send`.

No correction of the seven is green when reverted. Two remarks that are not findings. The last one, (g), is held only by a test of the *previous* pass's file: no test written in `pass24.rs` covers the anchor slot in the free list, so the correction lives on a test written for another rule's reason. And (b) and (c) overlap on four tests, which is expected: a pinned entry and a blocked R2 are two faces of the same state, and (b) is the only one of the two that `a_release_crossing_a_revoke_…` sees.

## 4. My own tests, and what they attack

All eleven are in the clone at `model/src/scenarios/verify24.rs`; the suite is green with them (`674 passed` in `--lib`). Each names the claim of the brief it goes after.

| Test | Claim | Result |
|---|---|---|
| `claim1_killing_the_holder_under_a_failed_unit_never_lets_it_die` | 1: "a death of either side" | passes |
| `claim1_a_fresh_start_of_the_holders_slot_is_refused` | 1: "a fresh start of the holder" | passes |
| `claim1_a_release_before_a_revoke_at_a_count_above_0_ends_pinned` | 1: "a crossing of the two", in the order no pass-24 test uses | passes |
| `claim1_two_grants_under_one_failed_unit_are_both_pinned` | 1: "a second failed unit" | passes |
| `claim2_a_sealed_holder_never_lets_the_frozen_granter_die` | 2: another path lets the barrier hold | passes |
| `claim2_killing_the_holder_and_the_granter_leaves_the_granter_frozen` | 2: "its chunks be taken", the strongest form | passes |
| `claim3_a_resumed_holder_never_lets_the_dead_granter_memory_be_taken` | 3: "the resumed holder is live and the memory is reused" | passes |
| `claim4_a_send_of_an_ended_generation_read_during_the_resume_is_refused` | 4: "a message about a grant from a generation that ended during the seal" | passes |
| `claim4_a_revoke_of_a_live_granter_read_during_the_resume_is_served` | 4: a message that is harmless on a live node, served during R2 | passes |
| `claim6_the_first_map_waits_while_the_granter_is_sealed_and_is_gone_once_accused` | 6: C4's sentence, the three states | passes (finding 1) |
| `claim6_a_chunk_under_a_live_grant_is_never_given_or_split` | 6: C11's sentence | passes for the give; the split is `invalid` (finding 4) |

What they show, in the terms of the brief:

- **Claim 1, "a death of either side".** The holder of a granted frame is the node that mapped it in an iospace of its own, so the failed unit is one its device sits behind; `R1` on that unit is never done for it (`had_device`, `r1_done` in `model/src/nodes.rs`), so its barrier never holds and it never dies. I killed it, ran a second of machine time, and it stays fenced, its use entry keeps its count with no root, the granting node is untouched, and neither chunk can be taken. The fresh start of its slot is `busy` for the same reason, so the use table that counts the leaf cannot be cleared under the granting node's generation. That closes the two paths of the brief that looked most likely to me ("a death of either side", "a fresh start of the holder").
- **Claim 2.** A sealed holder counts as a node that is running for the checker's new rule (`running_node` includes `Sealed`) and acknowledges nothing, so the granting node stays fenced; killing the holder too does not help the granting node, because the second protection is the `maps_of` bit a fenced node's `acked` cannot stand in for. Both facts are asserted by run.
- **Claim 3.** The resumed holder runs threads again (a notify is retyped on it, and its first thread's call does work), and after a further second of machine time the dead granting node is still fenced, no `acked` for it is written, and neither its chunk nor the holder's is handed out. No reuse.
- **Claim 4.** A `Send` from a generation that ended during the seal, read during R2, is refused (one trace, no use entry, no remote capability); a `Revoke` from a *live* granting node, read during the same resume, is served and the granting node's removal ends pinned. Neither runs a thread before the resume ends (the pass's own test covers the wake, and I did not duplicate it).

## 5. What I checked and found sound

- **Claim 1.** A use entry is freed only at a count of 0 in every path the brief lists: `remote_destroyed`, `revoke_received`, the pending-release sender in `rings.rs`, `r0_effects`, and the fresh copy of a use entry written by a `Send` (a kept entry is not in the free list, which `pass24::a_use_entry_kept_without_a_root_is_never_written_for_another_grant` proves, and my two-grant test proves again). A grant whose holder reported its root removed at a count above 0 is `pinned` and traced (`revoke_answered`, `release_received`); a `Revoke` in flight keeps its credit until its answer; a `Release` on a *live* entry at a count above 0 leaves it as it was and traces it (line 917).
- **Claim 2.** R2 stays undone while a use entry of the holder names the dead generation and counts a leaf (`kept_count`), so R3, R4 and R5 are not reached and `acked` is never written. The barrier needs either that `acked` from every live node or, for a fenced or sealed holder, `maps_of` clear — and the holder's `maps_of` bit is set at its map and cleared only by its own R5. The two together are why killing both sides changes nothing.
- **Claim 3.** The resume's `held` is exactly the contract's condition: no remote capability of the node left and a kept count naming its generation; a record left *unmapping* still ends the step before it, and the node becomes live with R2 to R5 undone, as a live node's would be. The model's comment on `audited` (that a guard there would be equivalent) is right: `reclaim_step` writes R3 only after R2.
- **Claim 4.** `consumes()` is false until the end of R0 and true afterwards, and `pick` chooses nothing while `resuming`, so the two halves of the sentence (read from the end of R0, run no thread) are separate switches, each held by a test that fails when reverted (e, f). The drain is bounded by the producer index read at the end of R0, so a peer that keeps writing cannot hold the resume.
- **The checker's new rule** (`check/machine.rs`: "G6: a granting generation over while a running holder counts a leaf") fires on the state a faulty barrier would write: `pass24::a_granter_dead_under_a_leaf_a_running_holder_counts_is_reported` builds it and it is reported. Invariant 58 counts a frozen use entry (`frozen_uses`), which is what lets the frozen record be modelled at all.
- **The `Release`/`Revoke` crossing table** (line 929) and the message table (lines 915, 1079) match the code path by path; the four rows I traced by run are the ones in `pass24.rs` plus my `claim1_a_release_before_a_revoke_…`.
- **The numbers and the `abi/` side of the pass**: `FENCE_RANGE_NS = (23_000_000, 1_000_000_000)` with a test and a reason that matches the row of line 1505 (two rounds of 11.2 ms and the stub); the five kinds of a `Report` key as 0 to 4 with `REPORT_KIND_SHIFT = 61` and a test; `1 MB + 4 KB` as `VTD_UNIT_TABLE_BYTES` with a test; the ARM64 breakpoint and watchpoint masks with two tests and two Kani proofs. Every one of these is a `const fn` in `abi/`, so the model's use of them (`Item::key` in `rings.rs`) cannot drift from the numbers.
- **The four quotations of the SDM I could check** (below) are the SDM's words, and the x86-64 rule of C3 is, as far as I can push it by reading, the right rule: TF cannot single-step the kernel except through `SYSCALL`, and `IA32_FMASK` closes that; a thread cannot set an execution breakpoint outside the user range, and the kernel touches no user memory through a user address, so no data breakpoint of a thread fires on a kernel access. I looked for a second way a thread could make the kernel accuse itself through a debug exception — a `MOV SS` whose next instruction faults, so that the held `#DB` is delivered inside the page-fault handler of the same thread; a breakpoint at the last user page with a length that crosses into the kernel's range; `DR7.GD`; `INT n` from user mode — and found none that the text does not already classify as the thread's fault. The one thing the text does not say is the order of the two faults in the `MOV SS`-then-fault case (the debug fault of kind 9 and the original fault of the same thread); that is a sentence missing, not a rule broken, and I did not raise it to a finding because it accuses nobody falsely.

## 6. What I could not check

- **The Intel SDM itself.** I could not open 325462-093 (its PDF cannot be read with the tools I have). I verified four of the pass's quotations against pages that reproduce the SDM's text: `SWAPGS` ("exchanges the current GS base register value with the value contained in MSR address C0000102H (IA32_KERNEL_GS_BASE)", and "When using SYSCALL to implement system calls, there is no kernel stack at the OS entry point"), `SYSCALL` with `IA32_FMASK` ("the processor clears in RFLAGS every bit corresponding to a bit that is set in the IA32_FMASK MSR"), and DR6 ("They may or may not be set if the breakpoint is not enabled by the Ln or the Gn flags in register DR7"). I could **not** verify, at their cited places: "Any data breakpoint on the MOV to SS instruction or POP to SS instruction is inhibited until the instruction boundary following the next instruction" and "The suppression and inhibition ends after delivery of an exception or the execution of the next instruction" (§7.8.3), "the processor loads the value pointed by an IST pointer into the RSP" (§7.14.5, finding 5), and the sentence behind "as `INT n` and `INT3` clear it themselves" (§20.3.1.4). Note for whoever opens it: the MOV/POP-SS sentence is cited as §6.8.3 in the public description of CVE-2018-8897; §7.8.3 may be right for a later edition, but I could not settle which section holds it in 325462-093.
- **VT-d D51397-019 §3.4.2 and §6.1** and **Arm DDI 0487 M.d D2.3.1, D2.8.4, D2.9.4, D24.3.2, D24.3.11**: not opened by me (the previous verification of the contract reports reading them, and the `abi/` tests encode their content).
- **`nix develop -c ./verify` with my tests in the tree**: I ran it on the pristine clone only. My tests are new code with new comments; `cargo fmt --check` and `clippy -D warnings` have not been run over `verify24.rs`, so the clone I left is green for `cargo test` and unverified for the style gates.
- **The model's exploration of the new state** (`explore::a_unit_fails_under_a_granted_frame_at_any_step_of_its_use`) was left in place and passed; I did not extend it or run other seeds.
- **Anything about nodes of several cores, or the ARM64 and RISC-V paths**: outside the two diffs, and not reviewed.
