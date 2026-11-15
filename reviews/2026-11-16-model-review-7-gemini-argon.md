# Review 7 — Reference Model & Contract (`gemini-4-argon`)

- **Contract reviewed:** [`Docs/architecture/kernel-interface.md`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) at `3bc7597` (`git diff 5d93e8f..3bc7597`, decision D-124)
- **Model reviewed:** [`dodos-kernel`](/Users/btw/Documents/repos/dodos-kernel) on branch `model` at `2afc901` (`git diff d4e883b..2afc901`, "pass 13")
- **Angle:**
  1. **Part 1 — Mutation of Pass 13 (`git diff d4e883b..2afc901 -- model/src abi/src`):** Single-rule mutation campaign across all 20 modified source files (`170` mutants total, executed with process-group `SIGKILL` timeouts), writing missing tests for every non-equivalent survivor, and proving which guards are genuinely unreachable.
  2. **Part 2 — What Was Cut to Make `./verify` Fast (`git diff d4e883b..2afc901 -- model/tests verify`):** Audit of all declared and undeclared test cuts/weakenings, construction of concrete mutants caught by the pre-Pass-13 checks that escape the Pass 13 checks, and execution of the 7 omitted test binaries under `DODOS_PAGE=16k` and `DODOS_PAGE=32k`.
  3. **Part 3 — Determinism:** 10 full `./verify` runs and 60 runs each of `property` and `liveness` across `--test-threads=1`, `2`, and default, plus a static audit of shared state (`OnceLock`, `Mutex`, `Arc`) for test-order dependencies.

---

## Verdict

Pass 13 brings the reference model into close alignment with decision D-124, makes the parallel `property` and `liveness` suites completely deterministic across thread counts (`60/60` identical `Reached` state vectors, `0` failures), and keeps the 7 test binaries omitted from the `16k`/`32k` runs page-clean when executed under both larger page geometries (`176/176` tests passing per geometry). However, our 170-mutant campaign (`103` killed by the existing suite, `67` survivors; `59` non-equivalent survivors killed by new tests we wrote and verified, `8` proven unreachable/equivalent) uncovered a **high-severity contract and model bug in device identifier ownership across node death and fresh restart**, where a PCIe device attached by a node that dies and restarts fresh (`CORE_START_FRESH`) before any survivor reclaims the device leaves `table.identifiers[key]` permanently wedged (`Err(Error::Denied)` for every other live node). In addition, three of the `./verify` speed-up cuts (plus an undeclared `K::ok` helper change in [`model/tests/calls.rs:249`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:249)) create concrete blind spots — most notably in [`model/tests/recovery.rs:94`](/Users/btw/Documents/repos/dodos-kernel/model/tests/recovery.rs:94), where checking `sys.check()` every `1_000_000` ns instead of every `100_000` ns allows per-event write-log invariants (`52`, `83`, `84`, `85`) to be wiped by `Model::begin` at intermediate 100 µs ticks before `sys.check()` ever runs.

---

## 1. Contract & Model Bug Found by Mutation Analysis

### 1.1 [HIGH] PCIe Device Identifier Word Permanently Wedged When Owner Node Dies and Restarts Fresh Before Takeover

- **Contract citations:**
  - [`Docs/architecture/kernel-interface.md:330`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:330): *"Taking an identifier word uses the same three rules and the same atomic compare-and-exchange as taking a memory block."*
  - [`Docs/architecture/kernel-interface.md:976-982`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:976): Three rules for taking an ownership/identifier word:
    1. `(Unclaimed, 0)`
    2. `(X, g')` with $g' \ne g_X$ (taken by an **earlier generation of the calling node $X$ itself**)
    3. `(Y, g_Y)` where node $Y$'s node-status word is `Dead`
  - [`Docs/architecture/kernel-interface.md:1094-1102`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1094) (R1) and [`Docs/architecture/kernel-interface.md:1138-1159`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1138) (R6): neither R1 (`block_devices`) nor R6 (`barrier_unit`) frees `table.identifiers[key]` when a node dies, nor does [`drop_dead`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs:448) clear `table.identifiers` when a dead node restarts fresh (`CORE_START_FRESH`).
- **Model citations:**
  - [`abi/src/machine.rs:341-351`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:341) (`Ownership::may_take`)
  - [`model/src/check/table.rs:103-107`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:103) (`Table::may_take`)
  - [`model/src/memory.rs:487`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:487), [`model/src/memory.rs:509-513`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:509), [`model/src/memory.rs:539-549`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:539) (`iospace_attach`, `holds_identifier`)
  - [`model/src/system.rs:448-475`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs:448) (`System::drop_dead`)
- **Mechanism:**
  1. Node $X$ (in generation $g$) attaches a PCIe device (`dev_key`) via `iospace_attach`, writing `table.identifiers[dev_key] = Ownership::taken(Owner::Node(X), g)` ([`model/src/memory.rs:510`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:510)).
  2. Node $X$ crashes and its peers complete R1–R6, transitioning node $X$'s status word to `Dead` (`generation = g`). During R1, `block_devices(X)` disables bus-mastering and blocks the device in `iommu_devices`, and during R6 `barrier_unit` frees memory blocks and roles — **but `table.identifiers[dev_key]` remains `Ownership::taken(Owner::Node(X), g)`**.
  3. While node $X$ is `Dead`, rule 3 of `may_take` (`Owner::Node(X) => self.dead(X)`) allows another live node $Y$ to take `dev_key`. **However**, if node $X$ is restarted fresh via `core_start(..., CORE_START_FRESH)` before any node $Y$ re-attaches `dev_key`, node $X$'s node-status word transitions to `Starting` and then `Live` with `generation = g + 1`.
  4. Now `self.table.dead(X)` is `false`, while `table.identifiers[dev_key]` still holds `Ownership::taken(Owner::Node(X), g)`!
  5. When another live node $Y \ne X$ calls `iospace_attach` to attach (or detach with `iospace = 0`) that device, [`holds_identifier`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:539) evaluates:
     ```rust
     let mine = word.state() == OwnershipState::Taken
         && word.owner() == Owner::Node(self.node)
         && word.generation() == self.table.generation(self.node);
     mine || self.table.may_take(word, self.node)
     ```
     For node $Y \ne X$:
     - `mine` is `false` (`word.owner()` is `Owner::Node(X)`).
     - `self.table.may_take(word, Y)` calls `word.may_take(Y, gen_Y, self.dead(X))` ([`model/src/check/table.rs:103-107`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:103)), which evaluates `Owner::Node(X) => dead` ([`abi/src/machine.rs:347`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:347)). Because node $X$ is now `Live` in generation $g+1$, `self.dead(X)` is `false`!
     - Why doesn't this happen for memory blocks? Because for memory blocks, R6 (`reclaim_blocks` in [`model/src/recovery.rs:845-872`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:845)) actively sweeps every block owned by `(X, g)` and CASes it to `Free` **before** the R6 barrier marks node $X$ `Dead` (and Invariant 38 in [`model/src/check/table.rs:285-294`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:285) enforces that no `Taken` memory block has `word.generation() != node_gen` once a node is live). No such R6 sweep or invariant exists for `table.identifiers`!
  6. Consequently, **`dev_key` is permanently unclaimable by every node $Y \ne X$ (`Err(Error::Denied)`)**, even though generation $g$ of node $X$ died, its iospaces were destroyed in `drop_dead`, and generation $g+1$ of node $X$ has never touched the device.
- **Fix (Contract & Model):** Either:
  - **(Preferred, symmetric with memory blocks):** Have R6 (`barrier_unit` / a new `reclaim_identifiers` step before the barrier, or `block_devices` in R1) release `table.identifiers[key]` owned by `(dead_node, g)` back to `Ownership::free(Owner::Unclaimed)` (and enforce the analogue of Invariant 38 on `table.identifiers`); or
  - Have `may_take` check `self.dead(n) || word.generation() != self.generation(n)` for `Owner::Node(n)`.

---

## 2. Part 1 — Mutation Campaign on Pass 13 (`git diff d4e883b..2afc901 -- model/src abi/src`)

### 2.1 Methodology & Per-File Summary

We inspected every hunk of `git diff d4e883b..2afc901 -- model/src abi/src` (20 modified files) and constructed **170 single-rule mutants** in proportion to the rules added or modified in each file. Each mutant modifies exactly one check, state transition, constant, check ordering, or bound, and was executed against the relevant package/integration test binaries with a hard timeout that kills the entire process group (`os.killpg(pgid, signal.SIGKILL)`).

| File | Diff Stat (`d4e883b..2afc901`) | Mutants Tested | Killed by Pass 13 Suite | Survived Pass 13 Suite | Killed by Our New Tests | Proven Equivalent / Unreachable |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| [`abi/src/debug.rs`](/Users/btw/Documents/repos/dodos-kernel/abi/src/debug.rs) | `+6 / -1` | 1 | 1 | 0 | 0 | 0 |
| [`abi/src/lib.rs`](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs) | `+97 / -82` | 8 | 5 | 3 | 1 | 2 (`#013, #014`) |
| [`abi/src/machine.rs`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs) | `+173 / -30` | 16 | 11 | 5 | 4 | 1 (`#027`) |
| [`abi/src/start.rs`](/Users/btw/Documents/repos/dodos-kernel/abi/src/start.rs) | `+2 / -2` | 1 | 0 | 1 | 1 | 0 |
| [`abi/src/x86_64.rs`](/Users/btw/Documents/repos/dodos-kernel/abi/src/x86_64.rs) | `+20 / -18` | 5 | 5 | 0 | 0 | 0 |
| [`model/src/blocks.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/blocks.rs) | `+2 / -2` | 1 | 1 | 0 | 0 | 0 |
| [`model/src/boot.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/boot.rs) | `+48 / -5` | 10 | 10 | 0 | 0 | 0 |
| [`model/src/caps.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs) | `+34 / -22` | 4 | 3 | 1 | 1 | 0 |
| [`model/src/check.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs) | `+18 / -6` | 4 | 2 | 2 | 2 | 0 |
| [`model/src/check/table.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs) | `+69 / -14` | 8 | 1 | 7 | 7 | 0 |
| [`model/src/faults.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/faults.rs) | `+13 / -11` | 2 | 2 | 0 | 0 | 0 |
| [`model/src/ipc.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs) | `+21 / -5` | 3 | 1 | 2 | 1 | 1 (`#061`) |
| [`model/src/irq.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/irq.rs) | `+15 / -3` | 2 | 2 | 0 | 0 | 0 |
| [`model/src/memory.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs) | `+265 / -111` | 28 | 19 | 9 | 7 | 2 (`#080, #092`) |
| [`model/src/moves.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs) | `+22 / -31` | 4 | 3 | 1 | 1 | 0 |
| [`model/src/recovery.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs) | `+226 / -181` | 30 | 19 | 11 | 11 | 0 |
| [`model/src/remote.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs) | `+166 / -98` | 24 | 7 | 17 | 17 | 0 |
| [`model/src/roles.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs) | `+55 / -4` | 7 | 4 | 3 | 2 | 1 (`#153`) |
| [`model/src/sched.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs) | `+31 / -17` | 5 | 2 | 3 | 2 | 1 (`#161`) |
| [`model/src/system.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs) | `+35 / -23` | 7 | 5 | 2 | 2 | 0 |
| **Total (20 files)** | **`+1318 / -666`** | **170** | **103 (`60.6%`)** | **67 (`39.4%`)** | **59 (`88.1%` of survivors)** | **8 (`4.7%` of total)** |

### 2.2 Redundant / Unreachable Guards in Pass 13 (Including Pass 13's Own 2 Survivors)

Pass 13 commit `403b8cd` reported killing 33 of 35 of its own mutants and called the 2 survivors "redundant guards." We identified both of Pass 13's redundant guards in [`model/src/recovery.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs) as well as **8 genuinely unreachable/redundant guards** among our 170 mutants:

1. **Pass 13's 2 reported "redundant guards" in [`model/src/recovery.rs:500`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:500) and [`model/src/recovery.rs:554`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:554) (`observe_needed`):**
   - **Line 554:** Inside `observe_needed`, lines 547–551 build `let successors: Vec<u16> = (1..n).map(|step| (self.node + step) % n).filter(|&z| self.table.writes(z)).take(2).collect();` and then line 554 checks `if self.table.core_beacons[core].idle_until.0 == u64::MAX && self.table.writes(z)`. Because `z` is drawn from `successors`, `self.table.writes(z)` is **100% tautological** (`true` by construction 5 lines earlier).
   - **Line 500:** `if !self.table.writes(node) { continue; }` in `observe_needed`. In normal multi-node execution, `remote_call` (`remote.rs:94`) rejects sending a call to a non-`Live` target (`!self.table.live(target_node)`), and when a `Live` node transitions to `Failing`/`Sealing`, R1 (`isolate`) or R2 (`sealing_unit`) clears/processes incoming calls before R3 (`observe_needed`) checks peers. Thus, through normal syscalls this guard is unreachable unless a `Request::Call` is synthetically injected while `peer` is already non-writing (our synthetic unit test kills `#106` by injecting `Request::Call { peer: 1, .. }` while node 1 is `Sealed` and calling `recovery_step()`).
2. **Mutant `#013` ([`abi/src/lib.rs:471`](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:471), `self.levels >= 2 && self.levels <= 8`) & Mutant `#014` ([`abi/src/lib.rs:472`](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:472), `self.address_bits() <= 64`):**
   - **Mathematical proof of unreachability:** Pass 13 added `self.entries as u64 == 1 << (s[0] - 3)` ([`abi/src/lib.rs:480`](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:480)) alongside `s[0] >= 12` and uniform stride $d = s_0 - 3 \ge 9$. Therefore, for any geometry that reaches line 472 after passing stride/entry validation,
     $$\text{address\_bits()} = s_0 + \text{levels} \cdot (s_0 - 3) = (\text{levels} + 1)(s_0 - 3) + 3.$$
     - For `#013` (`levels <= 8` vs `levels < 8`): Since $s_0 \ge 12 \implies s_0 - 3 \ge 9$, any $\text{levels} \ge 6$ gives $\text{address\_bits()} \ge 12 + 6 \times 9 = 66 > 64$, which is already rejected by `address_bits() <= 64`! Thus `levels` can only ever be $2, 3, 4,$ or $5$; `levels = 6, 7, 8` are mathematically impossible.
     - For `#014` (`address_bits() <= 64` vs `address_bits() < 64`): Equality $\text{address\_bits()} = 64$ requires $(\text{levels} + 1)(s_0 - 3) = 61$. Because **61 is a prime number**, the only positive integer factorizations of 61 are $1 \times 61$ and $61 \times 1$, neither of which satisfies $\text{levels} + 1 \ge 3$ and $s_0 - 3 \ge 9$. Thus `address_bits()` can never equal 64 for any valid geometry!
3. **Mutant `#027` ([`abi/src/machine.rs:429`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:429), `if raw >> 45 != 0 || (raw >> 32) as u16 > 1 << 12` in `GateWord::from_raw`):**
   - **Bit-level proof of equivalence:** `(raw >> 32) as u16` extracts bits `32..=47` of `raw`. Whenever bit `45` (or bit `46` or `47`) of `raw` is `1`, bit `13` (or `14` or `15`) of `(raw >> 32) as u16` is `1`, so `(raw >> 32) as u16 >= (1 << 13) = 8192 > (1 << 12) = 4096`. Thus the second disjunct `(raw >> 32) as u16 > 1 << 12` **already rejects every `u64` with bits `45..=47` set**, making `raw >> 45 != 0`, `raw >> 46 != 0`, and `raw >> 48 != 0` 100% equivalent across all $2^{64}$ inputs!
4. **Mutant `#061` ([`model/src/ipc.rs:696`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:696), `Request::Move { caller, .. }` in `unlink`):**
   - `unlink` is only called from `destroy_thread` ([`model/src/caps.rs:1165`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:1165)). While a thread is the `source` of an in-flight `Request::Move`, `in_move(source)` is `true` ([`model/src/caps.rs:738-747`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:738)), which causes `delete_one` / `revoke_step` ([`model/src/caps.rs:245`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:245)) to return `Err(Error::Busy)` before `destroy_thread` can ever be called on `source`.
5. **Mutant `#080` ([`model/src/memory.rs:368`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:368), `self.table.kept.iter().any(...)` in `class_of`):**
   - `class_of` checks `if self.frames.values().any(|f| f.kept && ...) || self.table.kept.iter().any(...)`. Because `Model::boot` ([`model/src/boot.rs:151-162`](/Users/btw/Documents/repos/dodos-kernel/model/src/boot.rs:151)) creates a `FrameObject` with `kept: true` for every entry in `self.table.kept`, and [`memory_take`](/Users/btw/Documents/repos/dodos-kernel/model/src/blocks.rs:58) refuses to take any block overlapping `self.table.kept` (so those `FrameObject`s can never be destroyed), the first disjunct in `class_of` always covers `self.table.kept`.
6. **Mutant `#092` ([`model/src/memory.rs:547`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:547), `&& word.generation() == self.table.generation(self.node)` in `holds_identifier`):**
   - In `holds_identifier`, `mine || self.table.may_take(word, self.node)` is returned. If `word.state() == OwnershipState::Taken && word.owner() == Owner::Node(self.node)` but `word.generation() != self.table.generation(self.node)`, then `mine` is `false`, **and** Rule 1 of `may_take` ([`abi/src/machine.rs:344`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:344): `Owner::Node(n) if n == node => self.generation() != generation`) immediately returns `true`. Thus `mine || may_take` has the exact same truth value with or without the generation equality check in `mine`.
7. **Mutant `#153` ([`model/src/roles.rs:54`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs:54), `&& self.table.generation(word.holder()) == w.generation()` in `reserve_taken`):**
   - `reserve_taken` is only called in `role_claim` ([`model/src/roles.rs:94`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs:94)) **after** line 84 has already checked `if self.blocks(word.holder()) { return Err(Error::Busy); }`. For a `Reserve` role (`word.state() == RoleState::Held`), `blocks(holder)` is `!self.table.dead(holder)` ([`model/src/roles.rs:41`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs:41)). Therefore, whenever execution reaches `reserve_taken(role)` with `word.state() == RoleState::Held`, `self.table.dead(word.holder())` is guaranteed to be `true`, making `!self.table.dead(word.holder())` in `reserve_taken` already `false` before the generation comparison is reached.
8. **Mutant `#161` ([`model/src/sched.rs:617`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs:617), `if self.in_move(context) || self.scheds[&context].home.is_some()` in `sched_bind`):**
   - `in_move(context)` is `true` for a `Sched` capability only when it was passed as `sched` to `thread_move` ([`model/src/moves.rs:92`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs:92)). However, `thread_move` ([`model/src/moves.rs:70-71`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs:70)) requires `moved.home == Some(sched_id)` (which by scheduler invariant means `self.scheds[&sched_id].home == Some(thread_id)`) and does not clear `scheds[&sched_id].home` until `moved()` completes on the source node ([`model/src/moves.rs:212`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs:212)). Hence `self.scheds[&context].home.is_some()` is always `true` whenever `self.in_move(context)` is `true`.

---

### 2.3 All 59 Non-Equivalent Survivors and the New Tests That Kill Them

Every one of the remaining **59 surviving mutants** is non-equivalent (behaviour-changing) and survived because the Pass 13 test suite lacked a boundary test, negative invariant test, or multi-node message-tampering/race test for that rule. We wrote 4 self-contained test functions (`r7_abi_survivors` in `abi/src/lib.rs`, `r7_aspace_map_partial_and_gate_chunks_boundaries` in `model/tests/memory.rs`, `r7_move_in_flight_freezes_sched_and_revocation_and_checks_dying_target` in `model/tests/adversarial_nodes.rs`, and `r7_system_unit_survivor_tests` in `model/src/system.rs`), verified that all 4 pass on the unmodified `2afc901` codebase (`rc = 0`), and verified by re-running each of the 59 mutants against the new tests that **all 59 are killed (`rc != 0`)**:

#### Group A — ABI Geometry, Start Flags & Hardware Word / Transition Survivors (`6` mutants killed by `r7_abi_survivors`)
- **`#002`** ([`abi/src/start.rs:274`](/Users/btw/Documents/repos/dodos-kernel/abi/src/start.rs:274)): `START_MEMORY_UNFENCED_ACCEPTED` bit constant (`1 << 4 -> 1 << 5`). Killed by asserting `START_MEMORY_UNFENCED_ACCEPTED == 1 << 4`.
- **`#015`** ([`abi/src/lib.rs:480`](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs:480)): `Geometry::valid` boundary `self.user_end <= 1 << (self.address_bits() - 1)` (`<= -> <`). Killed by testing a valid `Geometry` whose `user_end` equals `1u64 << (g.address_bits() - 1)`.
- **`#016`** ([`abi/src/machine.rs:95`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:95)): `SLOT_RECORD_PARTIAL` bit constant (`1 << 5 -> 1 << 4`). Killed by asserting `SLOT_RECORD_PARTIAL == 1 << 5`.
- **`#017`** ([`abi/src/machine.rs:114`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:114)): `PageClass::table` range `1..=8 -> 1..=7`. Killed by asserting `PageClass::table(8).is_some()` and `PageClass::table(8) != PageClass::table(7)`.
- **`#023`** ([`abi/src/machine.rs:265`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:265)): `PageClass::permits` on `GLOBAL_READ_ONLY` dropping `!leaf.device_type`. Killed by asserting `!PageClass::GLOBAL_READ_ONLY.permits(Leaf { write: false, exec: false, device_type: true })`.
- **`#030`** ([`abi/src/machine.rs:582`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:582)): `member_transition` `HostSealed` dropping the `cleared` check (`after.evidence() == Evidence::None && after.driver() == DRIVER_NONE`). Killed by asserting `member_transition(live, Member::new(MemberState::Sealed, Evidence::Host, 0, 1)) == None`.

#### Group B — Checker Invariant Survivors (`9` mutants killed by `r7_system_unit_survivor_tests`)
- **`#048, #050`** ([`model/src/check.rs:856, 862`](/Users/btw/Documents/repos/dodos-kernel/model/src/check.rs:856)): `check_identifiers` PCIe key calculation (`segment << 16 -> segment << 8`) and set equality (`held == attached -> held.is_subset(&attached)`). Killed by attaching a device on `segment = 1` and testing both a mismatched `attached` set and a non-zero segment in `check_identifiers`.
- **`#051, #052, #053, #054`** ([`model/src/check/table.rs:272-279`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:272)): `check_table` R6 barrier reserve-role and ownership checks (`state == 2`, `owner == after_owner`, `RoleKind::Reserve`, `m.generation() == g`). Killed by mutating `Table` role/block words across an R6 transition and asserting `check_table` rejects each invalid R6 transition.
- **`#056, #057, #058`** ([`model/src/check/table.rs:344-345, 376`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:344)): `check_table` Invariants 56 and 57 (`runs`, `zero == table.none.len()`, `none`). Killed by injecting a violating `table.none` / `runs` state and asserting `check_table` returns `Err("56: ...")` / `Err("57: ...")`.

#### Group C — Memory Partial Continuation, Step Budget, Gate Chunks & Device Identifier Key Survivors (`7` mutants killed by `r7_aspace_map_partial_and_gate_chunks_boundaries` and `r7_system_unit_survivor_tests`)
- **`#066, #067, #069, #070`** ([`model/src/memory.rs:146-152`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:146)): `aspace_map` partial-continuation checks (`m.partial`, `m.space == space`, `m.first == map.first`, `m.rights == rights`). Killed by starting a multi-step `aspace_map` (> 64 pages so `Outcome::Continue` sets `m.partial = true`) and invoking a second step with mismatched `space`, `first`, `rights`, or non-partial state.
- **`#072`** ([`model/src/memory.rs:220`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:220)): `aspace_map` step budget boundary `spent + c > budget` (`> -> >=`). Killed by mapping exactly `MAP_STEP_PAGES` (64 pages) in a single call and asserting it completes in 1 step (`Outcome::Done`) rather than 2 (`Outcome::Continue`).
- **`#083`** ([`model/src/memory.rs:384`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:384)): `aspace_protect` gate chunk boundary `touched > gate_chunks` (`> -> >=`). Killed by protecting a region spanning exactly `gate_chunks` (64 chunks) and asserting `Ok(Output::Done)`.
- **`#089`** ([`model/src/memory.rs:512`](/Users/btw/Documents/repos/dodos-kernel/model/src/memory.rs:512)): `identifier_key` shift `segment << 16 -> segment << 8`. Killed by attaching a device on `segment = 1` and verifying `check_identifiers` and `table.identifiers` key indexing.

#### Group D — In-Flight `ThreadMove` & Role Verification Survivors (`6` mutants killed by `r7_move_in_flight_freezes_sched_and_revocation_and_checks_dying_target` and `r7_system_unit_survivor_tests`)
- **`#045`** ([`model/src/caps.rs:245`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:245)): `remove_unit` `in_move` check removed. Killed by attempting to revoke a capability while it is in flight in `Request::Move` and asserting `Err(Error::Busy)`.
- **`#063`** ([`model/src/ipc.rs:699`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs:699)): `destroy_thread` `Request::Revoke` failing to clear `*waiting = None`. Killed by destroying a thread waiting on a remote `Request::Revoke` and verifying `waiting` is cleared.
- **`#096`** ([`model/src/moves.rs:141`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs:141)): `accept_move` dropping `self.dying(target)` check. Killed by initiating a `ThreadMove` and marking `target` dying before `accept_move` runs.
- **`#152`** ([`model/src/roles.rs:41`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs:41)): `check_roles` Reserve owner word check ignoring holder dead/generation check. Killed by corrupting a Reserve role's owner word in `table.roles` and asserting `check_roles` fails.
- **`#160, #163`** ([`model/src/sched.rs:584, 650`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs:584)): `sched_configure` and `sched_set_cores` skipping `self.in_move(context)` check. Killed by calling `SchedConfigure` and `SchedSetCores` on a `Sched` capability while a `ThreadMove` using that `Sched` is in flight (`Err(Error::Busy)`).

#### Group E — Recovery (`R1`–`R6`), Remote Misdirected-Packet Validation & System Orchestration Survivors (`31` mutants killed by `r7_system_unit_survivor_tests`)
- **`#100, #101, #103`** ([`model/src/recovery.rs:289, 323`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:289)): `parked_block` dropping `save_seal` or `running != node`, and `core_stop` `stays` dropping co-hosted `stops_core`.
- **`#105, #106, #108`** ([`model/src/recovery.rs:478, 500, 614`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:478)): `needed()` sweep filter `.filter(|&z| self.table.writes(z))` vs `!self.table.dead(z)`, `observe_needed()` skipping `!self.table.writes(node)` when a `Sealed` node is in `requests`, and `recovery_unit` preserving `member.state()` (`Unfenced` vs forcing `Fencing`) when redriving a fence whose driver is gone.
- **`#116, #119, #120, #121, #127`** ([`model/src/recovery.rs:857, 949, 962, 1004, 1094`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:857)): `fenced` checking `Handing` target on a co-hosted unit role, `isolate` resetting an armed `Transfer` reply to `Idle`, `isolate` not waking `Move` `source` thread with `Error::Gone`, `barrier_unit` rejecting `RoleState::Handing` in `units_clear`, and `drop_stale_remotes` checking `!self.table.writes(r.node)`.
- **`#130, #131, #133, #134, #136, #137, #138, #139, #140, #141, #143, #144, #145, #146, #147, #148, #151`** ([`model/src/remote.rs:202-662`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs:202)): `misdirected` validation for `grantee` (`e.serial == serial`, `e.grantee == from`), `granter` (`r.serial == serial`, `u.generation == generation`), `asked` (`Revoke` `e.grantee == from && e.generation == generation`, `Unit` `*sent_to == Some(from)`), `Body::Answer`, `Body::TransferAsk`, `Body::TransferGrant`, `Body::Revoke`, `Body::Refused`, `Body::Returned`, `Body::Move` (sched grant check), `Body::Moved`, `Body::Handed`, `Body::UnitAnswer`, and `revoke_anchor` freeing a `Pinned` grant when `grantee_over`.
- **`#156`** ([`model/src/roles.rs:141`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs:141)): `take_handed` dying filter excluding `Sealed` nodes.
- **`#164, #166`** ([`model/src/system.rs:442, 483`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs:442)): `System::runs` checking `unloaded` (`!member.writes() && parked_block`) and `HwAction::ParkSelf` setting `save_seal = true` on co-hosted nodes.

---

## 3. Part 2 — What Was Cut to Make `./verify` Fast (`git diff d4e883b..2afc901 -- model/tests verify`)

### 3.1 Inventory of Declared Cuts and Undeclared Weakenings

Comparing `d4e883b..2afc901` across [`verify`](/Users/btw/Documents/repos/dodos-kernel/verify) and `model/tests/*.rs`:

| Category | File & Lines | Pre-Pass-13 (`d4e883b`) | Pass 13 (`2afc901`) | Impact / Blind Spot |
| :--- | :--- | :--- | :--- | :--- |
| **Declared Cut 1** | [`model/tests/blocks.rs:431-437`](/Users/btw/Documents/repos/dodos-kernel/model/tests/blocks.rs:431) (`eight_thousand_blocks_reclaim_in_bounded_steps`) | Ran `k.ok(take(...))` (1 `check()`) and `k.ok(split(...))` (8,191 `check()` calls, one per split). | Runs raw `k.m.apply(k.t, take(...))` (**0 `check()` calls after `take`!**) and calls `k.m.check()` only when `spare % 512 == 0 \|\| spare >= 8190` (17 `check()` calls). | **Misses per-event `table.writes` invariants (`52`)** on `memory_take` and on all 8,174 unchecked intermediate `memory_split` calls because `Model::begin` clears `table.writes` at the start of every `apply()`. |
| **Declared Cut 2** | [`model/tests/recovery.rs:94-104`](/Users/btw/Documents/repos/dodos-kernel/model/tests/recovery.rs:94) (`S::run`) | Checked `self.sys.check().unwrap()` after **every** `100_000` ns `advance()` step (`10 * ms` checks per run). | Checks `self.sys.check().unwrap()` only when `step % 10 == 9 \|\| step + 1 == steps` (every `1_000_000` ns) and once at `steps == 0`. | **Misses transient and per-event write-log invariants (`52`, `83`, `84`, `85`)** at 9 out of every 10 ticks (`100_000` ns–`900_000` ns) because `Model::begin` ([`model/src/sched.rs:100-102`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs:100)) clears `writes`, `role_writes`, and `member_writes` at the start of each tick. |
| **Declared Cut 3** | [`verify:16-20`](/Users/btw/Documents/repos/dodos-kernel/verify:16) | Ran `cargo test --workspace` on `4k`, `16k`, and `32k` (all 19 test targets on all 3 page sizes). | Runs full workspace on `4k`, but on `16k` and `32k` runs only `dodos-abi` + 10 integration test binaries, **omitting 7 binaries**: `cores`, `debug`, `irq`, `liveness`, `recovery`, `sched`, `tasks`. | **`debug.rs` is NOT page-independent!** [`model/tests/debug.rs:297, 584, 764`](/Users/btw/Documents/repos/dodos-kernel/model/tests/debug.rs:297) is the **only** test file in the entire repository that tests `REG_DR0..=REG_DR3 < user_end` in `thread_write_regs` ([`model/src/faults.rs:183`](/Users/btw/Documents/repos/dodos-kernel/model/src/faults.rs:183)). |
| **Declared Cut 4** | [`model/tests/property.rs:1169`](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs:1169), [`model/tests/liveness.rs:1158, 2356`](/Users/btw/Documents/repos/dodos-kernel/model/tests/liveness.rs:1158), [`Cargo.toml:26`](/Users/btw/Documents/repos/dodos-kernel/Cargo.toml:26) | Sequential loop over 1,000 seeds in `property.rs` and 15 scenarios in `liveness.rs`; full debug info. | Parallel `std::thread::scope` workers cached in `OnceLock` / `Mutex`; `debug = "line-tables-only"`. | See **Undeclared Weakening 5** below for `same_seed_gives_the_same_state`. |
| **Undeclared Weakening 4** | [`model/tests/calls.rs:249-253`](/Users/btw/Documents/repos/dodos-kernel/model/tests/calls.rs:249) (`K::ok`) | `K::ok` asserted single-step `DONE` (`self.m.apply(...) == Ok(Outcome::Done)`) for every syscall including `UntypedRetype` of small objects ($\le 64\text{ KB}$). | `K::ok` intercepts **all** `Syscall::UntypedRetype { .. }` and redirects them to `self.made_in(call, 64)`, allowing up to 64 steps even for 1-page / 2-page non-`Frame` objects! | **Masks step-count regressions** in `untyped_retype` (`CLEAR_STEP_BYTES = 65_536`) across all 190+ `k.ok(retype(...))` calls in `calls.rs`, especially on `32k` pages where a 2-page `ASpace` is `65_536` bytes (must finish in 1 step, not 2). |
| **Undeclared Weakening 5** | [`model/tests/property.rs:2607-2616`](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs:2607) (`same_seed_gives_the_same_state`) | Ran seeds `0`, `1`, `2` **twice each from scratch** (`6` independent `run_seed` executions) and compared both state hashes and `Reached` sets for all 3 seeds. | Reuses the cached `SEEDS_RUN` (`OnceLock`) for `first`, re-runs `0, 1, 2` once (`3` runs instead of `6`), and only compares `Reached` for `seed = 0` (`1` comparison instead of `2`). | Cuts determinism self-check executions in `same_seed_gives_the_same_state` from 6 runs to 3 and drops the `seed = 1` `Reached` equality check. |

*(No assertions, loop bounds, seed counts (`1,000`), step counts (`2,000`), or scenario counts (`15` liveness scenarios) were lowered in the remaining test files.)*

---

### 3.2 Concrete Mutants Caught by the Old Checks and Missed by the New Checks

We constructed and executed concrete single-line mutants for each cut to verify whether the old check caught them and the new check misses them:

1. **Mutant for Declared Cut 1 (`blocks.rs:431-437`):**
   - **Mutant in [`model/src/blocks.rs:233`](/Users/btw/Documents/repos/dodos-kernel/model/src/blocks.rs:233) (`memory_split`):**
     Omit `self.table.to_mut().writes.push(self.node)` when `self.blocks.len() == 100` (which occurs at split `spare = 100`, between the `spare = 0` and `spare = 512` checks), or write `Ownership::free(Owner::Unclaimed)` transiently on `spare == 100`.
   - **Verified Result:** **Pass 13's `blocks.rs` passes (`rc = 0`)** because `Model::begin` clears `self.table.writes` on split `101` before `k.m.check()` runs at `spare == 512`. Restoring the pre-Pass-13 per-split `k.ok(...)` **immediately kills the mutant (`rc = 101`, `Err("52: write of an ownership word")`)**.
2. **Mutant for Declared Cut 2 (`recovery.rs:94-104`):**
   - **Mutant in [`model/src/recovery.rs:566`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs:566) (`recovery_step`):**
     At an intermediate 100 µs tick (e.g., `self.now == 11_500_000` ns, which is step `4` of a 1 ms `S::run` loop), perform a bogus ownership write or omit recording `self.table.to_mut().writes.push(self.node)` while modifying an ownership/role/member word.
   - **Verified Result:** **Pass 13's `recovery.rs` passes completely (`102 passed; 0 failed`, `rc = 0`)** because `Model::begin` ([`model/src/sched.rs:100-102`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs:100)) clears `writes`, `role_writes`, and `member_writes` at `11_600_000` ns before `sys.check()` runs at `12_000_000` ns! Restoring the pre-Pass-13 per-100-µs `self.sys.check().unwrap()` in `S::run` **kills the mutant in 29 tests (`rc = 101`, `Err("node 0: 52: write of an ownership word")`)**.
   - **Recommended Fix without Losing Speed:** Instead of clearing `writes`, `role_writes`, and `member_writes` blindly in `Model::begin`, accumulate them across ticks until `check()` clears them (or assert Invariants `52`, `83`, `84`, `85` before clearing).
3. **Mutant for Declared Cut 3 (`verify:16-20`, omitting `debug` from `16k` and `32k`):**
   - **Mutant in [`model/src/faults.rs:183`](/Users/btw/Documents/repos/dodos-kernel/model/src/faults.rs:183) (`thread_write_regs`):**
     ```rust
     // Replace:
     let user_end = self.machine.geometry.user_end;
     // With hardcoded 4 KB user_end:
     let user_end = (1u64 << 47) - (1u64 << 39);
     ```
   - **Verified Result:** Because **only `model/tests/debug.rs` tests `REG_DR0..=REG_DR3`** (`debug.rs:297, 584, 764`) and `debug` is omitted from the `16k` and `32k` loops in `./verify`, **this mutant survives the entire `./verify` script (`rc = 0`)**! Running the omitted `DODOS_PAGE=16k cargo test -p dodos-model --test debug` **immediately kills it in 2 tests (`rc = 101`, `hardware_watchpoint_fires_and_catches_write`, `watchpoint_validates_registers_and_survives_clear`)**.
   - **Recommended Fix:** Add `--test debug` (which takes only `0.02s` to run!) to the `for page in 16k 32k` loop in [`verify:17`](/Users/btw/Documents/repos/dodos-kernel/verify:17).
4. **Mutant for Undeclared Weakening 4 (`calls.rs:249-253`, `K::ok` redirecting all `UntypedRetype` to `made_in(call, 64)`):**
   - **Mutant in [`model/src/caps.rs:443`](/Users/btw/Documents/repos/dodos-kernel/model/src/caps.rs:443) (`untyped_retype`):**
     ```rust
     // Replace:
     let step = CLEAR_STEP_BYTES.min(bytes);
     // With:
     let step = if bytes == 65536 { CLEAR_STEP_BYTES - 1 } else { CLEAR_STEP_BYTES.min(bytes) };
     ```
   - **Verified Result:** On `DODOS_PAGE=32k`, an `ASpace` object is 2 pages = `65_536` bytes (`<= CLEAR_STEP_BYTES`), so `untyped_retype` must complete in **1 step (`Outcome::Done`)**. Because `K::ok` in `calls.rs:251` now routes all `UntypedRetype` calls through `self.made_in(call, 64)`, **`DODOS_PAGE=32k cargo test -p dodos-model --test calls` passes (`rc = 0`)** even though every `ASpace` retype in `calls.rs` illegally took 2 steps (`Outcome::Continue` then `Outcome::Done`)! Restoring single-step `DONE` in `K::ok` for non-`Frame` objects **kills the mutant in 17 tests in `calls.rs` (`rc = 101`)**.

---

### 3.3 Running the 7 Omitted Test Binaries Under `DODOS_PAGE=16k` and `DODOS_PAGE=32k`

We ran all 7 integration test binaries left out of the `16k` and `32k` loops in [`verify:16-20`](/Users/btw/Documents/repos/dodos-kernel/verify:16) (`cores`, `debug`, `irq`, `liveness`, `recovery`, `sched`, `tasks`) with `DODOS_PAGE=16k` and `DODOS_PAGE=32k`:

| Omitted Binary | `DODOS_PAGE=16k` Result | `DODOS_PAGE=16k` Time | `DODOS_PAGE=32k` Result | `DODOS_PAGE=32k` Time | Truly Page-Independent? |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `cores` | `15 passed; 0 failed` | `0.06s` | `15 passed; 0 failed` | `0.06s` | Mostly, except [`cores.rs:16`](/Users/btw/Documents/repos/dodos-kernel/model/tests/cores.rs:16) uses `m.machine.geometry.page_size()` (`p`) for `core_start`. |
| `debug` | `8 passed; 0 failed` | `0.02s` | `8 passed; 0 failed` | `0.02s` | **No** — [`debug.rs:297, 584, 764`](/Users/btw/Documents/repos/dodos-kernel/model/tests/debug.rs:297) explicitly tests `m.machine.geometry.user_end` (`REG_DR0..=REG_DR3`), which varies by page size (`4k` vs `16k` vs `32k`) and is tested nowhere else! |
| `irq` | `9 passed; 0 failed` | `0.02s` | `9 passed; 0 failed` | `0.02s` | Yes. |
| `liveness` | `16 passed; 0 failed` | `1.39s` | `16 passed; 0 failed` | `1.39s` | Yes. |
| `recovery` | `102 passed; 0 failed` | `2.65s` | `102 passed; 0 failed` | `2.83s` | Yes. |
| `sched` | `14 passed; 0 failed` | `0.04s` | `14 passed; 0 failed` | `0.04s` | Yes. |
| `tasks` | `12 passed; 0 failed` | `0.04s` | `12 passed; 0 failed` | `0.04s` | Yes. |
| **Total (7 binaries)** | **`176 passed; 0 failed`** | **`4.22s`** | **`176 passed; 0 failed`** | **`4.42s`** | All pass on `16k` and `32k`; `debug` (`0.02s`) and `cores` (`0.06s`) depend on `geometry`. |

---

## 4. Part 3 — Determinism & Shared-State Audit

### 4.1 10x Full `./verify` Campaign

We ran `./verify` **10 consecutive times** under a process-group timeout (`task-98`):

| Run | Exit Code | Wall Time (s) | Notes |
| :---: | :---: | :---: | :--- |
| `#1` | `0` | `43.35s` | Includes initial compilation of `16k`/`32k` artifacts |
| `#2` | `0` | `31.46s` | Warm run |
| `#3` | `0` | `31.34s` | Warm run |
| `#4` | `0` | `31.41s` | Warm run |
| `#5` | `0` | `31.36s` | Warm run |
| `#6` | `0` | `31.23s` | Warm run (min) |
| `#7` | `0` | `31.65s` | Warm run |
| `#8` | `0` | `31.33s` | Warm run |
| `#9` | `0` | `31.30s` | Warm run |
| `#10` | `0` | `31.70s` | Warm run (max warm) |
| **Summary** | **`10 / 10` passed** | **Warm: `31.23s – 31.70s` (spread `0.47s`, mean `31.42s`, stdev `0.15s`); All 10: `31.23s – 43.35s` (mean `32.61s`)** | **0 failures, 0 timeouts** |

### 4.2 60x `property` and 60x `liveness` Across `--test-threads` (`1`, `2`, Default)

We ran `cargo test --release -p dodos-model --test property -- --nocapture` and `cargo test --release -p dodos-model --test liveness -- --nocapture` **60 times each** (`20` runs at `--test-threads=1`, `20` runs at `--test-threads=2`, and `20` runs at default thread count) under a per-run process-group timeout (`task-181`) and captured the printed `Reached: ...` line from every run:

| Suite | `--test-threads` | Runs | Failures | Distinct `Reached` Outputs | Min Time (s) | Max Time (s) | Spread (s) | Mean Time (s) | Stdev (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `property` | `1` | 20 | `0` | `1` (byte-identical) | `2.600s` | `3.175s` | `0.575s` | `2.707s` | `0.130s` |
| `property` | `2` | 20 | `0` | `1` (byte-identical) | `2.459s` | `2.705s` | `0.247s` | `2.567s` | `0.068s` |
| `property` | `default` | 20 | `0` | `1` (byte-identical) | `2.238s` | `2.548s` | `0.310s` | `2.393s` | `0.064s` |
| **`property` Total** | **All (`1, 2, default`)** | **60** | **`0`** | **`1` across all 60 runs** | **`2.238s`** | **`3.175s`** | **`0.937s`** | **`2.556s`** | **`0.159s`** |
| `liveness` | `1` | 20 | `0` | N/A (`16 passed`) | `4.197s` | `4.316s` | `0.119s` | `4.236s` | `0.025s` |
| `liveness` | `2` | 20 | `0` | N/A (`16 passed`) | `2.369s` | `2.559s` | `0.190s` | `2.425s` | `0.044s` |
| `liveness` | `default` | 20 | `0` | N/A (`16 passed`) | `1.394s` | `1.547s` | `0.153s` | `1.441s` | `0.045s` |
| **`liveness` Total** | **All (`1, 2, default`)** | **60** | **`0`** | **Identical pass set** | **`1.394s`** | **`4.316s`** | **`2.922s`** | **`2.701s`** | **`1.168s`** |

Every one of the 60 `property` runs produced the exact same `Reached` summary:
```text
Reached: 33 syscalls, 152 call/error pairs, 7faults, 6plans, 10objects, 27states, 14events
```

### 4.3 Audit of Shared State for Test-Order Dependencies

We audited every piece of shared state introduced in Pass 13:

1. **[`model/tests/property.rs:1169-1197`](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs:1169) (`SEEDS_RUN: OnceLock<Reached>`):**
   - `seeds_reached()` spawns up to 8 worker threads over `0..SEEDS`, where thread `t` processes seeds `s = t, t + threads, ...`.
   - Each seed `s` runs `run_seed(s, STEPS_PER_SEED)` on a fresh, thread-local `Model` instance with deterministic PRNG state `Rng::new(seed)` and returns a local `Reached` struct.
   - After all threads join, the main thread reduces the per-thread `Reached` structs via `Reached::merge`, which performs set union (`BTreeSet::extend`) and logical OR (`bool |= bool`). Because set union and boolean OR are associative and commutative, `SEEDS_RUN` is **strictly invariant to thread count, thread scheduling, and test execution order**.
2. **[`model/tests/liveness.rs:1158-1191`](/Users/btw/Documents/repos/dodos-kernel/model/tests/liveness.rs:1158) (`Mutex<usize>` work queue in `all_fifteen_scenarios_pass_at_every_fault_tick`) & [`model/tests/liveness.rs:2356-2376`](/Users/btw/Documents/repos/dodos-kernel/model/tests/liveness.rs:2356) (`TRANSCRIPT_RUN: OnceLock<...>`):**
   - In `all_fifteen_scenarios_pass_at_every_fault_tick`, `next = Mutex::new(0usize)` hands out scenario indices `idx \in 0..15` dynamically to worker threads. Each scenario `SCENARIOS[idx]` creates its own isolated `System` and checks its own assertions independently; no state is shared between scenarios.
   - In `TRANSCRIPT_RUN`, 4 fixed scenario runs (`s01`, `s02`, `s06`, `s12`) execute in parallel in `std::thread::scope` on independent `System` instances and store their resulting `System` snapshots in a 4-tuple inside `OnceLock`. The 4 consumer tests (`s01_...`, `s02_...`, `s06_...`, `s12_...`) only take shared `&System` references from `TRANSCRIPT_RUN`. There is **no order dependence** between which test initializes or reads `TRANSCRIPT_RUN` first.
3. **[`model/src/check/table.rs:26-73`](/Users/btw/Documents/repos/dodos-kernel/model/src/check/table.rs:26) (`Arc<Vec<...>>` Copy-on-Write arrays in `Table`):**
   - `Table` wraps `blocks`, `identifiers`, `roles`, `members`, `nodes`, and `kept` in `Arc<Vec<...>>` and mutates them exclusively through `Arc::make_mut` inside `TableMut` (`Drop` re-packs into `self.table`). Because `Arc::make_mut` clones the underlying `Vec` whenever strong count $> 1` (i.e. whenever a snapshot was cloned), mutations never alias across snapshots or threads.
4. **One Subtle Latent Coupling Note in `property.rs`:**
   - All 29 `thousand_seeds_cover_*` tests call `seeds_reached()`, which calls `run_seed(s, STEPS_PER_SEED)` where `run_seed` itself calls `m.check()` on every step (`property.rs:1148`). Whichever test happens to run first initializes `SEEDS_RUN` (taking `~2.3s`), and the remaining 28 tests complete in `< 1ms` by reading `&Reached`. If any single `run_seed` panics, the `OnceLock` initialization panics on the first test and is not poisoned (`OnceLock::get_or_init` retries on subsequent callers if the initializer panics), so no test can falsely pass because another test ran first.
