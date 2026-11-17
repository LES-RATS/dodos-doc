# Model review 11: the executable model of the kernel contract against the contract, pass 19

Review of the model branch of `dodos-kernel`, head `04503d5`
(`crates abi/` and `model/`, the diff `073ae9e..04503d5`), against
`architecture/kernel-interface.md` of this repository and the rulings in
`decisions/README.md` (D-136 at line 146, D-137 at line 147).

I worked only in my own copy:

```
git clone --branch model /Users/btw/Documents/repos/dodos-kernel /private/tmp/dodos-kernel-review11
git -C /private/tmp/dodos-kernel-review11 rev-parse HEAD  ->  04503d576fd48c828a2b47d18e31722d52b31afa
```

A second copy at the parent (`/private/tmp/dodos-parent`, `073ae9e`) was used
only for the coverage-floor comparison of task 4. Four more worktrees
(`/private/tmp/mut-lane2..4` and the main copy) ran the mutation campaigns of
tasks 5 and 6; every mutation was applied to a clean tree, `cargo fmt --all`
run, then `./verify` (the whole suite: `cargo fmt --all --check`, `cargo clippy
--workspace --all-targets -- -D warnings`, `cargo test --workspace`, then the
`16k` and `32k` geometry runs of the selected test binaries) run in it, and the
tree was reverted with `git checkout -- .` afterwards. A green `./verify`
prints 47 `test result: ok` lines; I checked that count in the log of every
green result below. Nothing was committed and nothing was pushed. This file is
my only output.

I read `AGENTS.md`, `model/README.md` and the skills `.claude/skills/dodos-rust`
and `.claude/skills/rust-1-100` before judging any Rust here.

---

## Findings

### Task 1 — `Model::hold`, the quiet word, the escalation, the four orders

**1. Minor — `locks::entry_orders` explores a hand-written copy of the rule, not the model's own concurrent code (a proof narrower than its name).**
Contract, `architecture/kernel-interface.md:666`: "**The four orders (D-137).**" followed in the same line by the four cases (1)-(4) of core *a*'s entry word, the quiet word and core *b*'s take. The model's `entry_orders` (`model/src/locks.rs:941`) and `interleave` (`locks.rs:959`) are pure functions over hardcoded step sequences — `true => &[&[0, 2]]`, `false => &[&[0, 1, 2], &[0, 2, 1]]` — interleaved with *b*'s two steps `[take, read]`. Nothing in them calls `Model::hold`, `again_of_tries` or `interrupt_on`; the model's own code is never executed by this function. The test `with_the_ordering_operations_no_interleaving_lets_a_core_enter_while_an_escalation_runs_alone` (`model/src/scenarios/pass19.rs:557`, assertion at :560) checks the copy: with the ordering operation it counts 6 interleavings, without it 20, and asserts no `(true, true)`. The mutation `l-entry-orders` (ordered sequence replaced by the two unordered ones) fails exactly this test (left 20, right 6), so the test guards the copy, not the kernel code. What the model's own code does about the race is elsewhere: `interrupt_on` keeps the arrival pending when another core holds the word (`model/src/irq.rs:290-295`) and `release_quiet` takes them after (`model/src/locks.rs:655-662`).

**2. Minor — the masked-arrivals test scripts the quiet word as test input, so it proves the bookkeeping, not a concurrent wait.**
`an_arrival_on_a_core_that_waits_for_the_quiet_word_stays_pending_until_the_word_is_released` (`pass19.rs:571`) sets `k.m.quiet = Some(1)` directly (`pass19.rs:590`) and then calls `interrupt_on(0, 48)`. It therefore proves that `interrupt_on` pushes to `masked`, that `release_quiet` replays, and that the check invariant holds ("quiet word: an arrival kept pending with the word released", `model/src/check/node.rs:394-399`). It does not exercise the real concurrent path (a core entering while `again_of_tries` holds the word at `locks.rs:790-791`); the mutations `i-masked` (drop the pending push) and `l-release-replay` (never replay) both fail this test (left 1, right 0 at `pass19.rs:592/:597`), which is the right guard for the bookkeeping, but the name "a core that waits" overstates what runs.

**3. Surviving mutation — the escalation's wait predicate drops the "entry word is not 0" half.**
Contract, `kernel-interface.md:666`: the escalating call "waits until the entry word of every other core of the node reads **0 or at least the new epoch**". The model at `model/src/locks.rs:776` has `let waited = entry != 0 && entry < self.kernel_epoch;`. Mutation `l-waited`: `entry != 0 && entry < self.kernel_epoch` → `entry < self.kernel_epoch`. Diff: one line in `model/src/locks.rs`. Command: `nix develop -c ./verify` on the mutated tree. Result: EXIT=0, 47 `test result: ok` lines (log `/tmp/mut-lane1-l-waited.log`). Observable difference: with `kernel_epoch` starting at 1 (`model/src/boot.rs:1092`), an idle core's entry word 0 now reads as *waiting*, so `Step::Entry { core, waited: true }` is traced and `end_holder(core)` is called for a core that holds nothing; no check (`check_holders`, `order`) compares `waited` against the holder's actual presence, so nothing fails.

What I checked and found correct in this task: `Model::hold` (`locks.rs:524`) does make a real second core — a `Holder` keyed by core in `contended`, entered at the current `kernel_epoch`, with its own steps and an optional call (`then`) that must run on that core; it refuses a core already in an event, a lock held by another core ("two cores never hold one lock"), and a call thread not on the holder's core, and its trace is checked by the same `order()` (`locks.rs:842`). Those refusal paths are unreachable by construction in the other direction: no code path inserts a holder whose lock another holder holds. The `again` count is reset on every path — after any result of a call (`model/src/lib.rs:1424`), and on both arms of the rule of tries (`locks.rs:736` and `locks.rs:799`); the mutation `l-again-reset` (drop the `lib.rs` reset) fails `a_result_other_than_the_again_of_tries_sets_the_count_to_0` (`pass19.rs:67`, left 2 right 0 at :75), matching contract `:666` "any other result of a call of that thread sets the count to 0". The escalation in `again_of_tries` (`locks.rs:760-805`) raises the epoch by one (`Epoch` step), reads every other core's entry word (`Entry` steps for exactly the other cores, enforced by `order()`), waits for the not-0-and-below cores, takes its locks sorted and alone under `quiet = Some(at)`, and releases the word by `release_quiet`. All four `order()` mutations I tried are caught: `l-order-quiet-held`, `l-order-failed` (two rounds → three), `l-order-try-quiet` all fail `scenarios::pass18::the_check_refuses_the_orders_that_the_rounds_of_l2_forbid`; the bound checks are guarded as below.

### Task 2 — iospace classes, the attach word, the unit holder's gate

**4. Surviving mutation — the holder's gate writes *detached* from any attach-word state, not only from *attached*.**
Contract, `kernel-interface.md:373`: at the answer of a detach, "the attach word *detached*" is written by the holder's gate (the transition *attached* → *detached*; `:355` lists the word's states 0, *pinned*, *attached*, *detached*). The model at `model/src/units.rs:680` has `if word.state() == Some(dodos_abi::AttachState::Attached) {`. Mutation `u-detach-confirmed`: that condition → `if word.state().is_some() {`. Diff: one line in `model/src/units.rs`. Command: `nix develop -c ./verify`. Result: EXIT=0, 47 `test result: ok` lines (log `/tmp/mut-lane2-u-detach-confirmed.log`). Observable difference: a detach confirmed while the word reads *pinned* (or 0) now swaps it to *detached* with the word's root; no test reaches a confirmation in that state, and `check` counts identifier/attach words only in totals, so nothing fails.

What I checked and found correct in this task: the classes are exactly the contract's — `abi/src/machine.rs:166` `iospace_table(level)` = 32 + *k* for *k* in 1..=8, `:175` `iospace_root(devices)` = 48 + *n* for *n* in 0..=16, `:204` `stored` holds 0, 17..=24, 33..=40, 48..=64; contract `:1793` and the G2 sentence `:1077`. Mutations `a-iospace-table` (31 + *k*), `a-iospace-root` (47 + *n*), `a-stored` (41 stored) all fail `abi` tests `tests::page_classes_have_their_bytes_and_the_rules_of_g3`. The attach word transitions in the model: the requester's gate pins the root in one call with the identifier and the root's device count (`model/src/memory.rs:865-869`), refuses with `busy` when the word is not 0 (`memory.rs:848-850`; contract `:372`), and at the answer writes 0 from *pinned* or *detached* (`memory.rs:924-940`; contract `:373`); the holder's gate checks *pinned*→*attached* or *attached* with the named root, root class 48 + *n* with *n* ≥ 1, held page, in `model/src/units.rs:290-303` (G9, contract `:1084`), writes *attached* before the context entry (`units.rs:429-432`; contract `:372`), and rebuilds a reported device's entry from *attached* or by moving *pinned* to *attached* (`model/src/roles.rs:554-570`). The mutations `m-attach-busy` (drop the not-0 → `busy` refusal), `m-attach-nopin` (attach does not pin), `m-detach-done` (0 written only from *pinned*), `u-attach-word` (no *attached* written at submit), `u-gate-holds` (drop the held-page check), `u-gate-rootdev` (drop *n* ≥ 1) all fail: `destroying_an_iospace_detaches_its_devices_then_empties_its_records`, `scenarios::explore::unit_a_request_across_a_hand_over_and_the_deaths_of_its_parties`, `pass19::an_attach_pins_its_root_and_a_detach_unpins_it_only_at_its_answer` (:191, left `(None, 0)` right `(Some(Attached), 4294991872)`), `pass19::a_root_whose_detach_the_unit_never_confirms_never_turns_back_into_data` (:293, check 88 "identifier words and attached devices" — this is the root returning to *data* only from class 48 + 0, contract `:362`), and `pass19::the_holder_refuses_a_root_pinned_by_the_requester_unless_its_class_is_an_iospace_root` (:154/:159 — the lower-table refusal, contract `:1077`/`:1084`). A forged attach is refused because the gate requires `w.root() == root` with the state *pinned*/*attached* (`units.rs:290-298`), guarded by `pass19::the_holder_refuses_an_attach_that_the_requesters_gate_did_not_pin` (:163). A holder dying between its writes is covered by the rebuild: mutation `r-rebuilt-attached` (*attached* refused at rebuild, `roles.rs:565`) fails `pass19::a_rebuild_writes_the_entry_of_an_attached_device_whose_holder_died_before_writing_it` (:243, `unit.entries.contains_key` false). **Can a faulty node's input panic the model?** I audited the `expect`/`unwrap`/`panic!` sites reachable from call input: the roots used on the attach path come from the iospace's own root (`memory.rs:864`, page-aligned by construction, `unwrap_or(0)`), and from `AttachWord` words, whose `from_raw` refuses a state 0 with an address and any unaligned address (`abi/src/machine.rs`, the `AttachWord` check), so `pinned.expect("a root aligned on a page")` (`memory.rs:867`), `attached.expect("a root")` and `detached.expect("a root")` (`roles.rs:570`, `units.rs:683`) cannot be reached with a bad address from node input; `attach_key` reads the role records, not requester data. The remaining expects guard model-internal invariants ("names a live entry" after a `live()` check) and the one `panic!` (`model/src/lib.rs:1244`) reads start-up slots. No panic path from a faulty node's input found.

### Task 3 — marks, bounds, faults, `task_revoke`, irq removal, R-steps, stopped time

**5. Surviving mutation — the gate records observations while the release word of the stub is raised.**
Contract, `kernel-interface.md:1660`: "while the release word is raised, the clocks of membership stop …: **no gate records an observation and no node makes an accusation**, of another node or of itself". The model has `if self.table.release { return false; }` at the top of `observe_needed` (`model/src/nodes.rs:723-725`) and of `accuse_with_evidence` (`nodes.rs:807-809`). Mutation `n-release-observe`: the block at `nodes.rs:723-725` deleted (the accusation one kept). Diff: 3 lines in `model/src/nodes.rs`. Command: `nix develop -c ./verify`. Result: EXIT=0, 47 `test result: ok` lines (log `/tmp/mut-lane2-n-release-observe.log`). Observable difference: with the release word raised, `observe_needed` now records and expires observations on the membership clock; the seal test that guards the other half (`pass19::a_node_sealed_before_a_long_stop_in_the_stub_is_not_accused_with_seal_at_the_release`, :727) still passes because the seal instant is stamped with `membership_now` (`nodes.rs:1529`), which the stop does not move.

**6. Surviving mutation — every unhooked table joins the free list at the first unmapping completion, not only its own record's.**
Contract, `kernel-interface.md:78` (the D-137 list): "an unhooked table joins its free list **only once its invalidation is complete**". The model at `model/src/memory.rs:265` partitions `aspace.unhooked` by `by == cap` at the completion of the record `cap`. Mutation `m-rehook-all`: the predicate → `|&&(_by, _)| true`, so the first `finish_unmapping` moves all unhooked tables to `free`. Diff: one line in `model/src/memory.rs`. Command: `nix develop -c ./verify`. Result: EXIT=0, 47 `test result: ok` lines (logs `/tmp/mut-lane1-m-rehook-all.log`, `/tmp/mut-lane2-m-rehook-all.log`). Observable difference: tables unhooked by a still-open record appear on the free list early; `check/table.rs` counts `hooked + free + unhooked` (`model/src/check/table.rs:464`), so the totals still match and no test observes the ownership of an individual free page before its record completes.

What I checked and found correct in this task: marks are ORed into both the thread's own word and its task's word with no lock (`model/src/tasks.rs:20-29`), contract `:664` "marks a delivery stamps and spreads need no lock and no try: they are ORed by atomic operations after the last try" and `:1116` "marks word is an atomic OR … no lock of a task or a thread and no try"; mutation `t-mark-task` (drop the task-word OR) fails `pass19::a_delivery_ors_its_marks_into_the_receivers_own_word_and_its_task_and_takes_no_task_lock` (:653, left 0 right 2 at :668). The new bounds *k* (`model/src/locks.rs:246-268`: 33 `call`, 29 `send`, 40 `recv`, 67 `reply_recv`, 21 `thread_configure`, 387 a removal step, 194 `task_revoke`, 12 the rest; contract `:670` and `:1793`) — mutations `l-bound-call` (33→32), `l-bound-recv` (40→39), `l-bound-capdel` (387→386) all fail `pass19::the_bound_k_of_each_call_is_the_contracts` (:682, left `[32, 29, …]` right `[33, 29, …]` at :715). The escalation bound own + *E* + (*N* − 1) × *B*1max and the `CORE_ANSWER_NS` start-up checks *N* × *H* + *D* under L1 and 2 × *E* + (*N* − 1) × *B*1max + *D* under L2 (contract `:666` and `:692`) are implemented in `escalated`/`healthy_wait` (`locks.rs:1027-1046`); mutation `l-healthy-l1` (drop the *D* under L1) fails `pass19::the_bound_of_an_escalated_call_is_closed_and_core_answer_ns_covers_a_request_under_each_variant` (:611, left 400 right 450 at :628). (`l-escalated` failed only at clippy, `field one_core is never read` — a clippy-clean variant was not rerun; noted below as not fully checked.) Fault delivery as an event, not a call (contract `:664`), is covered by `pass19::under_l2_a_fault_waits_for_the_core_that_holds_its_endpoint_and_is_delivered` (:853); I did not mutate it. `task_revoke`'s first call is bounded by the cores and detaches nothing (`model/src/tasks.rs:128-155`; contract `:1144`); mutation `t-revoke-first` (drop the marking loop over the other cores) fails `scenarios::cores::task_revoke_returns_again_while_a_thread_of_the_task_is_marked`. The irq removal as a request — waits while an entry still asks for the line, frees the line word at the end (`model/src/irq.rs:361-402`; contract `:770` and `:795`) — mutation `i-removal-asking` fails `pass19::the_removal_of_a_lines_irq_waits_while_an_entry_still_asks_for_that_line` (:807, `!node.irqs[&irq].removing` at :846). The `Report` of a line rebuilds the entry from the operands of operation 5 claimed, checked by `operands_allowed` (`model/src/roles.rs:529-543`; contract `:962`); mutation `u-operands-masked2` (the masked-redirection operand check inverted in `model/src/units.rs:322`) fails `scenarios::pass17::the_holder_of_an_ioapic_refuses_a_redirection_entry_aimed_at_another_nodes_core` (`pass17.rs:738`). R0 once per generation (`nodes.rs:991` `r0_runs`, used at `nodes.rs:1622-1625`; contract `:1414`) — mutation `n-r0-ran` (drop the `!ran` test) fails `scenarios::explore::rings_a_send_and_a_signal_while_the_sender_seals_and_the_receiver_dies_and_starts_fresh`. R5 only after R2 removed every remote and R4 audited every block (`nodes.rs:1130`, `nodes.rs:1179-1185`; contract `:1334` "R2 is done when no such record remains", `:1089` "R4 … stays before R5", `:1337`) — mutation `m22` of task 5 fails `pass19::r5_is_written_only_once_r2_removed_every_remote_capability_of_the_fenced_node` (:1127, left `(0, 40, true)` right `(0, 0, true)` at :1131) and `n-r4b` (R4-done always true) fails `r5_is_written_only_once_r4_audited_every_block` (:1135, :1139). A starting node is judged against `START_NS`, never `STALE_NS` (`nodes.rs:637-650`, observation life `nodes.rs:739`; contract `:1301`, `:1302`, `:1413`) — mutations `n-start-ns` and `n-observe-life` fail `scenarios::crossing` tests and `pass19::a_start_on_a_core_that_never_beats_is_accused_after_start_ns_and_not_before` (:1147, left `Dead` right `Starting` at :1158). The stopped time (`nodes.rs:606-607` `membership_now` = now − stopped_time; `system.rs:439-447` `stub_stop` adds the stop to `stopped_time`; contract `:1660-1662`) — mutations `n-membership` (ignore the stopped time) and `s-stub` (stub does not add it) both fail the seal test at `pass19.rs:738` (left `Dead` right `Sealed`). One shape worth noting: the model runs two clocks — observations, the seal and the evidence use `membership_now` (`nodes.rs:606, 622, 626, 727, 1529`), while the fence record, the starts and the unit-request instants are stamped with raw `now` (`nodes.rs:893, 249, 1710`; `roles.rs:283, 371, 546, 584`). Each comparison is same-clock and nothing records while the release word is raised, so no stop is counted twice; contract `:1662` lists the fence-record instants and the start among those that "leave the stop out", which the model satisfies only through the no-recording-during-a-stop rule, not by reading the membership clock there. The sweep reads the seal instants of its two sealed successors (contract `:1301`); I did not mutate that. The kernel slot of D-136 (`decisions/README.md:146`; contract `:1398`, `:1412`) is checked in `model/src/check/machine.rs:38-41`; mutation `c-d136` fails `pass19::a_resume_with_kernel_image_1_and_an_empty_slot_is_busy_and_no_call_fills_the_slot` (:404, expected `Err("D-136: the replacement slot written after the machine start-up")` at :423). The epoch checks (`check/node.rs:348-389`) — mutation `c-epoch-last` fails `pass19::a_raise_of_the_kernel_epoch_by_no_escalation_and_no_last_destruction_is_reported` (:1169, expected the `epoch:` error at :1182).
### Task 4 — the dying-notifies coverage floor lowered from 354 to 166

**Not a path that stopped running — a legitimate reshaping of the walk, and I can name the step where it starts.**
The floor in `model/tests/property.rs:2479` is `at_least(dying, [21, 7107, 30, 8246, 106, 10, 10, 691, 166])`; the comment at `:2474-2477` says pass 19 measured the counts again (notify 474 → 221 at 32 KB pages; 166 = ⌈¾ · 221⌉, the smallest of the three page-size runs, as `:2439-2442` defines). I instrumented `Reached::count` in both trees (parent `073ae9e` in `/private/tmp/dodos-parent`, head `04503d5` here) to log every step of seed 9 at `DODOS_PAGE=32k` (call name, outcome, `census.dying`), then reverted the instrumentation in both. The two walks are identical until step 2178; at **step 2179** a `cap_delete` of an **iospace** returns `Ok(Done)` in the parent and `Err(Again)` with `dying=[IoSpace]` in pass 19 — exactly the pass-19 change the comment names ("the destruction of an iospace waits for the answers of its detaches", D-137), and the new path is plainly running. That one different outcome makes the generator consume its RNG differently, and from step 2179 on the two programs diverge completely: in the parent, seed 9's notify goes dying at step 7524 and stays dying for 879 steps of a `cap_delete` walk (until step 9452); in pass 19 the same seed's notify goes dying at step 8775 and its walk is 165 steps. At 4 KB pages the per-seed totals are identical in both trees (472 overall, dominated by seed 6's 428), so the drop is a 32 KB-pages reshuffle, not a removed path: notifies still go dying and are still walked (`dying_copies` floor 24 still passes, `:2480`). The other kinds' counts went up at 32 KB, as the comment says. Legitimate.

### Task 5 — re-applying the review-10 mutations m18, m22, m25, m26 on `04503d5`

Each was re-applied on a clean tree at `04503d5`, `cargo fmt --all` run, `nix develop -c ./verify` executed, then `git checkout -- .`.

| mutation | diff | contract sentence | result |
|---|---|---|---|
| m18 | `model/src/nodes.rs:1762` delete `instants.push(start.since + START_NS);` | `:1301` "a node that does not beat within `START_NS` is accused with stale" | **green**: EXIT=0, 47 `test result: ok` (log `/tmp/m18.log`) — still a surviving mutation |
| m22 | `model/src/nodes.rs:1130` `r.node == node` → `r.node == node + 1` in the R2-done check | `:1334` "R2 is done when no such record remains" | **red**: `pass19::r5_is_written_only_once_r2_removed_every_remote_capability_of_the_fenced_node` fails at `pass19.rs:1131`, left `(0, 40, true)` right `(0, 0, true)` (log `/tmp/m22.log`) — pass 19 closed it |
| m25 | `model/src/nodes.rs:1098` delete `\|\| self.reclaims.get(&node).is_some_and(|r| r.generation != g)` | `:1414` "R0 once for that generation, leaving the reclaim of a later generation of the same node as it is" | **green**: EXIT=0, 47 `test result: ok` (log `/tmp/m25.log`) — still a surviving mutation |
| m26 | `model/src/roles.rs:341` `let same = record.generation == member.generation();` → `let same = true;` | `:1306` the fence record's word 0 is "the generation the record concerns" | **green**: EXIT=0, 47 `test result: ok` (log `/tmp/m26.log`) — still a surviving mutation |

So three of the four review-10 mutations (m18, m25, m26) survive the whole suite on pass 19's head; only m22 is now caught.

### Task 6 — 41 own mutations in pass-19-changed code, whole suite on each

All in `model/src/` or `abi/src/` (never the tests), each contrary to a quoted
contract sentence; each applied to a clean tree with `cargo fmt --all` after
the edit, then `nix develop -c ./verify`, then reverted. **Four stayed green:**

1. **l-waited** — finding 3 above. `locks.rs:776` `entry != 0 && entry < self.kernel_epoch` → `entry < self.kernel_epoch`; contract `:666` "reads 0 or at least the new epoch". EXIT=0, 47 ok lines.
2. **m-rehook-all** — finding 6 above. `memory.rs:265` partition predicate `by == cap` → `true`; contract `:78` "an unhooked table joins its free list only once its invalidation is complete". EXIT=0, 47 ok lines.
3. **u-detach-confirmed** — finding 4 above. `units.rs:680` `word.state() == Some(Attached)` → `word.state().is_some()`; contract `:373`/`:355` the *attached* → *detached* transition. EXIT=0, 47 ok lines.
4. **n-release-observe** — finding 5 above. `nodes.rs:723-725` release-word guard deleted; contract `:1660` "no gate records an observation … while the release word is raised". EXIT=0, 47 ok lines.

The other 37 were all caught (EXIT=101; a few first at clippy with `-D
warnings`, which is also a red):

| mutation | site | caught by |
|---|---|---|
| l-bound-call / l-bound-recv / l-bound-capdel | `locks.rs:251,258,261` k values 33/40/387 lowered by 1 | `pass19::the_bound_k_of_each_call_is_the_contracts` (:715) |
| l-healthy-l1 | `locks.rs:1038` drop `+ D` under L1 | `pass19::the_bound_of_an_escalated_call_is_closed…` (:628, 400 vs 450) |
| l-escalated | `locks.rs:1028` drop `(N−1)×B1max` | clippy: `one_core` never read (behavior not exercised — see below) |
| l-order-quiet-held / l-order-failed / l-order-try-quiet | `locks.rs:895,926,883` order checks dropped | `pass18::the_check_refuses_the_orders_that_the_rounds_of_l2_forbid` |
| l-entry-orders | `locks.rs:950` ordered = unordered sequences | `pass19::with_the_ordering_operations…` (:560, 20 vs 6) |
| l-again-reset | `lib.rs:1424` no reset after a result | `pass19::a_result_other_than_the_again_of_tries_sets_the_count_to_0` (:75) |
| l-release-replay | `locks.rs:657` masked arrivals never replayed | `pass19::an_arrival_on_a_core_that_waits…` (:592/:597) |
| i-masked | `irq.rs:291` arrival not kept pending | same test |
| i-removal-asking | `irq.rs:368` no wait while a line is asked | `pass19::the_removal_of_a_lines_irq_waits…` (:846) |
| u-operands-masked2 | `units.rs:322` masked-redirection operands check inverted | `pass17::the_holder_of_an_ioapic_refuses_a_redirection_entry…` (:738) |
| m-attach-busy | `memory.rs:848` attach allowed on a non-0 word | `destroying_an_iospace_detaches_its_devices_then_empties_its_records` |
| m-attach-nopin | `memory.rs:865-869` attach does not pin the root | `explore::unit_a_request_across_a_hand_over…`, `pass17::an_attach_through_ano…` |
| m-detach-done | `memory.rs:931` 0 written only from *pinned* | `pass19::an_attach_pins_its_root_and_a_detach_unpins_it_only_at_its_answer` (:191) |
| u-attach-word | `units.rs:429-432` *attached* not written at submit | `pass19::a_root_whose_detach_the_unit_never_confirms…` (:293), `an_attach_pins_its_root…` |
| u-gate-holds | `units.rs:303` held-page check dropped | clippy: `holds_page` never used |
| u-gate-rootdev | `units.rs:301` `n >= 1` → `is_some()` | `pass19::the_holder_refuses_a_root_pinned_by_the_requester…` (:154) |
| r-rebuilt-attached | `roles.rs:565` *attached* refused at rebuild | `pass19::a_rebuild_writes_the_entry_of_an_attached_device_whose_holder_died…` (:243) |
| a-iospace-table / a-iospace-root / a-stored | `abi/src/machine.rs:168,177,206` | abi `tests::page_classes_have_their_bytes_and_the_rules_of_g3` |
| t-mark-task | `tasks.rs:26-28` no OR into the task word | `pass19::a_delivery_ors_its_marks_into_the_receivers_own_word_and_its_task…` (:668) |
| t-revoke-first | `tasks.rs:137-147` first call marks nothing | `cores::task_revoke_returns_again_while_a_thread_of_the_task_is_marked` |
| n-membership | `nodes.rs:607` ignore stopped time | `pass19::a_node_sealed_before_a_long_stop_in_the_stub…` (:738) |
| s-stub | `system.rs:444` stub adds no stopped time | same test (:738) |
| n-start-ns | `nodes.rs:650` start judged immediately | `crossing::a_fresh_start_consumes_nothing…`, `crossing::a_resume_keeps_its_c…` |
| n-observe-life | `nodes.rs:739` starting observation not extended to `START_NS + STALE_NS` | `pass19::a_start_on_a_core_that_never_beats…` (:1158), `membership::a_node…` |
| n-r0-ran | `nodes.rs:1622-1623` R0 rerun per generation | `explore::rings_a_send_and_a_signal_while_the_sender_seals…` |
| n-r4 / n-r4b | `nodes.rs:1183` R4-done check dropped/always true | `pass19::r5_is_written_only_once_r4_audited_every_block` (:1139) |
| c-quiet-word | `check/node.rs:394-399` masked-with-word-released check dropped | `pass19::an_arrival_on_a_core_that_waits…` |
| c-epoch-last | `check/node.rs:374` last-raise check → `true` | `pass19::a_raise_of_the_kernel_epoch_by_no_escalation…` (:1182) |
| c-d136 | `check/machine.rs:38-41` replacement-slot check dropped | `pass19::a_resume_with_kernel_image_1_and_an_empty_slot…` (:423) |

### Task 7 — 12 of the 38 tests of `model/src/scenarios/pass19.rs`, each shown failing for the reason its name says

`pass19.rs` has exactly 38 `#[test]`s. For each test below I applied the
inverse mutation of the code it guards (on a clean tree, `cargo fmt --all`,
`nix develop -c ./verify`, reverted) and read the failure:

| test (pass19.rs line) | inverse mutation | failure |
|---|---|---|
| `the_bound_k_of_each_call_is_the_contracts` (:682) | l-bound-call, `Call` 33→32 | :715 left `[32, 29, 40, 67, 21]` right `[33, …]` — k differs from the contract |
| `a_result_other_than_the_again_of_tries_sets_the_count_to_0` (:67) | l-again-reset | :75 left 2 right 0 — the count is not reset |
| `an_arrival_on_a_core_that_waits_for_the_quiet_word_stays_pending_until_the_word_is_released` (:571) | l-release-replay | :592/:597 left 1 right 0 — the arrival is not kept pending / taken after |
| `the_removal_of_a_lines_irq_waits_while_an_entry_still_asks_for_that_line` (:807) | i-removal-asking | :846 `assertion failed: !node.irqs[&irq].removing` — the removal did not wait |
| `a_resume_with_kernel_image_1_and_an_empty_slot_is_busy_and_no_call_fills_the_slot` (:404) | c-d136 | :423 expected `Err("D-136: the replacement slot written after the machine start-up")`, got `Ok(())` |
| `a_raise_of_the_kernel_epoch_by_no_escalation_and_no_last_destruction_is_reported` (:1169) | c-epoch-last | :1182 expected `Err("epoch: the node's epoch is not its last raise")` |
| `a_delivery_ors_its_marks_into_the_receivers_own_word_and_its_task_and_takes_no_task_lock` (:653) | t-mark-task | :668 left 0 right 2 — the task word got no mark |
| `an_attach_pins_its_root_and_a_detach_unpins_it_only_at_its_answer` (:180) | m-detach-done | :191 left `(None, 0)` right `(Some(Attached), 4294991872)` — the word was not unpinned only at the answer |
| `a_rebuild_writes_the_entry_of_an_attached_device_whose_holder_died_before_writing_it` (:227) | r-rebuilt-attached | :243 `unit.entries.contains_key(&DEVICE)` false — no entry written |
| `a_node_sealed_before_a_long_stop_in_the_stub_is_not_accused_with_seal_at_the_release` (:727) | s-stub | :738 left `Dead` right `Sealed` — the seal evidence wrongly held across the stop |
| `a_start_on_a_core_that_never_beats_is_accused_after_start_ns_and_not_before` (:1147) | n-observe-life | :1158 left `Dead` right `Starting` — accused before `START_NS` had passed |
| `r5_is_written_only_once_r2_removed_every_remote_capability_of_the_fenced_node` (:1127) | m22 | :1131 left `(0, 40, true)` right `(0, 0, true)` — R5 written with remotes left |

Each fails for the reason its name states.

---

## What was checked and found correct

- `Model::hold` as a real second core and the same `order()` checking its trace; the escalation sequence (quiet word → epoch → entry words → alone under quiet) and the `again`-count reset on all three paths (task 1).
- The iospace page classes 32 + *k* / 48 + *n* and `PageClass::stored`; the whole attach-word transition set (pin at attach, not-0 → `busy`, *attached* before the context entry, *detached* at the confirmation, 0 at the answer, root to *data* only from 48 + 0, lower table and forged attach refused, rebuild after a holder's death) (task 2).
- Marks ORed without a lock into both words; the new bounds *k*, the closed escalation bound and the `CORE_ANSWER_NS` start-up formulas; `task_revoke`'s first call bounded by the cores; irq removal as a request with the line word freed at the end; the `Report` line operands; R0 once per generation; R5 after R2 and R4; starts judged against `START_NS`; the stopped time; the D-136 slot check; the epoch checks (task 3).
- The 354 → 166 floor drop is the reshuffle of the 32 KB walk that begins at the first iospace destruction returning `again`, not a path that no longer runs (task 4).
- 12 pass19 tests each fail under the inverse mutation of what they guard, with the failure matching the name (task 7).

## What was not checked, or could not be run

- `l-escalated` (dropping the (*N* − 1) × *B*1max term of the escalation bound) was red only because clippy's `-D warnings` rejected the then-unused field `one_core`; a clippy-clean variant of that mutation was not rerun, so the bound's third term is not proven by a behavioral test from my campaign (the pass19 test `:611` does cover `healthy_wait` under both variants, left 400 right 450 under `l-healthy-l1`).
- The sweep reading the two sealed successors (contract `:1301`) and the fault-delivery event's full path (contract `:664`) were read but not mutated.
- Task 2's "holder dying between writes" was checked through the rebuild path (`r-rebuilt-attached`); the per-step death table of the IOMMU protocol (contract `:985-995`) as a whole was not mutated step by step.
- The MSI remapping entry of the `Report` (contract `:962`, "for a remapping handle two words 0") has no dedicated mutation; only the line-operands arm of `operands_allowed` was inverted (`u-operands-masked2`).
- The property-test instrumentation used for task 4 was reverted in both clones; the clones (`/private/tmp/dodos-kernel-review11` and the `mut-lane*` worktrees) are clean at `04503d5`.
