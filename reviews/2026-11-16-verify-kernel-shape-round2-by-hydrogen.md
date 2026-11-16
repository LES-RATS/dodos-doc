# Second verification of C* and `kernel-shape-explorer.py` (Hydrogen)

Reviewed 16 November 2026 against [kernel-shape-opus.md](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md) (especially Part 9, lines 479–681), [kernel-shape-explorer.py](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py), [kernel-interface.md](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md), [kernel.md](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md), [decisions/README.md](file:///Users/btw/Documents/repos/Docs/decisions/README.md), and [the round-1 review](file:///Users/btw/Documents/repos/Docs/reviews/2026-11-16-verify-kernel-shape-opus-by-hydrogen.md). All exploratory scripts were written to disk in a separate `/tmp` scratch directory and run with `timeout` and `python3 -B -I`.

## Verdicts

| # | Area | Verdict | Summary |
|---|---|---|---|
| 1 | Explorer vs. text (`R-1`–`R-16` & Part 9) | **Partial** | `R-1`–`R-5`, `R-7`–`R-10`, `R-12`–`R-15` map to `Moves`, `Seal`, and `Credits`; `R-6`, `R-11`, `R-16`, and `R-5` sentence 2 are unmodelled, and key multi-word steps are atomic (`TI == 0`, `give`, `settle`, `R6`, `role` takeover, `seal`). |
| 2 | Refined exploration & unproven cases | **6 real faults, 2 artefacts** | Splitting atomic reads/writes and adding restarts/skew breaks **P2** (`CoreWord` ABA on `LEAVING`, `R-1` epoch wrap), **STALE** (`R-9` skipping `R0`), **LIVENESS** (`R-13` shared FIFO ring head-of-line block), **IOMMU** (`R-10` omitting `.floor`), and **P6-SKEW** (`R-5` without `G12` lock, plus 1-core `R-5` deadlock); 24/24 non-vacuity checks pass. |
| 3 | Hardware confirm-parked & stop semantics | **Conditionally implementable** | None of ARM64 PSCI `AFFINITY_INFO`, x86-64 `INIT`, or RISC-V `sbi_hart_get_status` alone implements `R-1` safely; x86 `SETTLE_NS` (1 ms) after `INIT` is **unsafe** under SMM and `10 ms` SDM `INIT–SIPI` delay; RISC-V requires custom `fence_hart` ordering `STOPPED` after quiesce. |
| 4 | Stage-1 list (`9.4`) & hot-path cost | **Incomplete & leaks cost** | `9.4` omits multi-core kernel stacks/trap frames, trace-ring/crash-record/debugger concurrency, `task_revoke` sibling IPI, `R0–R6`/`aspace`/`irq` multi-core updates, and the `CoreWord`/two-ring fixes; items 7, 8, and 11 add Stage-1 hot-path cost unless compiled out when `CORES_PER_KERNEL_MAX == 1`. |
| 5 | Staged plan (`Stage 1` -> fixed `Stage 2` -> elastic `Stage 2`) | **Conditional Yes** | Build Stage 1 first, fix `R-1..R-16` and `9.4` gaps in `abi/`, and gate Stage 2 behind G12 Verus proof, `D-042` lock/latency bounds, and hardware stop tests. |

### Per-rule status (`R-1`–`R-16`)

| Rule | Modelled in `kernel-shape-explorer.py` | Verification result under refinement |
|---|---|---|
| `R-1` park request | `Moves` (`PKC`, `PKA` at `:183, :299, :303, :337, :399, :404`) | **Fault:** omits monotonic non-wrapping `park_request` epoch (1-bit toggle breaks `P2` in 19 steps). |
| `R-2` fence mark | `Moves` (`WM`, `SIG` at `:296–303, :312, :410, :431`) | **Holds** when split (`MovesSplitR6(deaths=1)` passes), subject to `R-1`/ABA fixes and TSO/Armv8 ordering. |
| `R-3` entry stub | `Moves` (`ST`, retry `:303, :454–466`) | **Holds** in model; real hardware relies on `R-1` and unmasking before reading `CoreWord`. |
| `R-4` static cores | `Moves` (`bsp`, `:392–397, :421`) | **Holds** in model; RISC-V `fence_hart` post-stop `STOPPED` guarantee is unverified firmware code. |
| `R-5` class at commit | `Moves` (`:423, :435–437`) — sentence 2 unmodelled (`:581`) | **Fault:** cross-word write skew breaks `P6-SKEW` in 6 steps unless `G12` gate lock serializes `core_take` and `role_hand`; sentence 2 cannot run with 1 core. |
| `R-6` lock bounds | **Not modelled** (`:521, :587`) | Unproven; `D-042` bound grows with `k` and slowest core kind (`heterogeneous-cores.md:157`). |
| `R-7` idle kernels | `Seal` only models replacement, not idle sealing (`:537`) | Consistent as withdrawal of zero-core idle state. |
| `R-8` `SEAL_NS` | `Seal` (`S_SEALED_OLD` at `:625–626, :592–593`) | **Holds** in `Seal` once `SEAL_NS` is a transition; exact timeout vs. `CoreWord` races unmodelled. |
| `R-9` resume | `Seal` (`:630–641`) | **Fault:** `R-9` text omits `R0` (`R-14` counter reset + signal purge), breaking `STALE` in 6 steps. |
| `R-10` rebuild | `Seal` (`:612–618`) | **Fault:** `R-10` text omits `.floor` (whose ownership words read `0`), clearing valid IOMMU entries (`IOMMU` in 3 steps). |
| `R-11` sealed vectors | **Not modelled** (`:526, :584`) | Unverified; per-physical-core `irq` table (`9.4` #13) needs sealed-kernel masking rules. |
| `R-12` retirement | `Seal` (`:661–667`) | **Holds** in `Seal` (give memory before last core leaves). |
| `R-13` two credit classes | `Credits` (`QU`, `QK`, `BU`, `BK` at `:728, :754, :760`) | **Fault:** two credit classes on *one* FIFO ring (`:528`, `kernel-interface.md:862`) deadlocks kernel requests behind unconsumed user messages (`LIVENESS` in 8 steps). |
| `R-14` gen counters & purge | `Credits` (`YG`, `PS`, `PSG`, `:768–777`) | **Holds** in `Credits` for live sender `X`, fails when `X` resumes from `SEALED` unless `R-9` adds `R0`. |
| `R-15` shootdown | `Shootdown` (`:367–376, :403`) | **Holds** under split unmap (`MovesSplitUnmap(deaths=1)` passes in 803,726 states). |
| `R-16` `core_give` steps | **Not modelled** (`:531, :583`) | Unverified; non-one-shot `core_give` state transitions and death during vector retargeting are not explored. |

---

## 1. The explorer against the text

### Where `R-1`–`R-16` are modelled and what is abstracted

In [kernel-shape-explorer.py](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py), rules map to three separate finite models (`MovesNoFrame`, `Shootdown`/`MovesFull`, `Seal`, `Credits`):

- **`R-1` (park request, [kernel-shape-opus.md#L516](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L516)):** Modelled by 1-bit flags `PKC` (current confirmation) and `PKA` (ever parked) at [kernel-shape-explorer.py#L183](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py#L183), cleared to `0` at mark (`:299`), stop send (`:303`), and `core_give` (`:399`), and set to `1` on stop landing (`:337, :347`), park (`:404`), and entry-stub power-off (`:464`). *Abstraction:* clearing `PKC` and updating `CoreWord`/`WM` happen in one step; there is no monotonic `park_request` counter/epoch across restarts, so stale `parked == 1` cannot collide with a fresh request unless `PKA` is forced on (`stale_parked`).
- **`R-2` (fence mark, [kernel-shape-opus.md#L517](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L517)):** Modelled by `WM` (`0/1`) and in-flight stop `SIG` (`0..nk`) at `:296–303, :312, :410, :431`. *Abstraction:* `SETTLE_NS` is replaced by `SIG != k` (`:312`); `R6` (`:313–328`) clears every core word, cancels `TI`/`TO`, clears `FOWN`/`AMAP`/`PD`, and writes `M[k] = DEAD` in one atomic step rather than the per-unit incremental walk in [`R6`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1118).
- **`R-3` (entry stub, [kernel-shape-opus.md#L518](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L518)):** Modelled by `ST` (`1` masked, `2` unmasked, `0` running) and fence stop retries while `SP` or `EX == k` (`:303, :308, :331–347, :450–466`). *Abstraction:* `start` (`:450–455`) assumes `SP` is immediately consumed without queueing or overlapping SIPIs, and `core c checks its word and enters` (`:459–461`) checks `M[ex] == LIVE` and `CoreWord == JOINING` atomically with TLB flush and entry (`ST = 0`).
- **`R-4` (static cores, [kernel-shape-opus.md#L519](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L519)):** Modelled by `bsp[c]` guarding `give` (`:392–397`) and `take` (`:421`). *Abstraction:* class-0 cores (e.g., Trusted OS or RISC-V without `fence_hart`) are absent (`cls` uses only `FORCED=2` and `SIGNALLED=1`, `:201`), and `fence_hart`'s post-stop `STOPPED` invariant is not checked.
- **`R-5` (class at commit, [kernel-shape-opus.md#L520](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L520)):** Sentence 1 is modelled in `Moves` at `take` step 1 (`:423`) and step 2 (`:435–437`). *Abstraction:* (1) `TI == 0` (`:410`) imposes a global per-core **single-taker mutex**, forbidding two kernels from holding concurrent read snapshots for CAS on the same core; (2) step 2 reads `ROLE`, re-checks `CoreWord`, and writes `JOINING + SP` in **one atomic transition** (`:431–446`), making cross-word write skew with `ROLE` impossible; (3) `unit role moves to best` (`:350–353`) atomically computes `max(live)` without `HANDING -> HELD` or `SETTLE_NS`; (4) sentence 2 is completely unmodelled (`:581`).
- **`R-7`, `R-8`, `R-9`, `R-10`, `R-12` (`Seal` scenario, [kernel-shape-explorer.py#L532-L707](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py#L532-L707)):** `Seal` tracks 3 kernels (`A, B, C`), 4 cores, 1 granted frame `H` (`G`, `BM`, `RP`, `ACKB`), 1 device `BDEV`/`DEVE`, 1 extra block `MEMA`, `SUP`, `WAKE`, and `deaths=2`. *Abstraction:* core moves (`:645–649`), `B` sealing (`:623–624`), `B` resuming with `R2` + pending revocation (`:630–641`), unit rebuild (`:611–618`), and fresh starts (`:669–677`) are all **single atomic steps** with no `SEALING` state, no `CoreWord`, no `LEAVING`/`JOINING`, no fences/stops, and only `B` ever seals. `R-8` (`SEAL_NS`) is modelled as a single transition `S_SEALED -> S_SEALED_OLD` (`:625–626`).
- **`R-13`, `R-14` (`Credits` scenario, [kernel-shape-explorer.py#L714-L793](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py#L714-L793)):** Models one direction `X -> Y` with 4 user tasks (`QU=4`), kernel requests (`QK=2`), `AU/BU`, `AK/BK`, 1-bit toggle generation `YG` (`0/1`), `deaths=2`, and 1 pending signal `PS`/`PSG`. *Abstraction:* (1) `X` and `Y` share no FIFO ordering queue—`AU` and `AK` decrement independently (`:763–764`), hiding head-of-line blocking on a single FIFO ring; (2) `X` never dies or seals; (3) `YG` wraps every 2 deaths (`1 - YG`, `:777`); (4) `Credits` is disconnected from `Moves` and `Seal`.
- **`R-15` (shootdown, [kernel-shape-explorer.py#L356-L377](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py#L356-L377)):** Modelled in `Shootdown` (`deaths=1`) and `MovesFull`. *Abstraction:* `A unmaps F` (`:359–366`) writes `AMAP = 0`, `UNMAP = WAIT`, and every `PD[c]` atomically; `core_give` atomically checks `>= 2` `OWNED` cores (`:389–390`); `settle` atomically verifies `W == LEAVING`, `WM == 0`, `conf(s, c)`, `SP == 0` before writing `FREE` (`:407–408`).

**Bounds across all three scenarios:** `nk = 3` (`Moves`, `Seal`) or `2` (`Credits`), `nc = 4` (`Moves`, `Seal`), `deaths <= 2` (`Shootdown`: `deaths <= 1`), last live kernel never fails (`len(live) >= 2`), and no kernel restarts or generation numbers exist in `Moves`, `Shootdown`, or `MovesFull`.

### Rules of the text NOT modelled at all in `kernel-shape-explorer.py`

1. **`R-5` sentence 2** ([kernel-shape-opus.md#L520](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L520), confirmed `:581`): new holder giving away weaker cores after `HELD` and before mapping the unit.
2. **`R-6`** (`:521`, `:587`): per-kernel lock hold bounds `(k - 1) * hold_slowest`, non-blocking thread wait states.
3. **`R-11`** (`:526`, `:584`): masking/unmasking claimed interrupt vectors when sealing and resuming.
4. **`R-16`** (`:531`, `:583`): multi-step `core_give` (vector retargeting, kernel wait for unit holder's `UnitAnswer`, deferred `LEAVING`).
5. **Cross-ring overtaking** ([kernel-interface.md#L862](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L862)): reordering between `(X->Y)` and `(Z->Y)` or reverse rings `(Y->X)`.
6. **Multi-frame grants & full `M1–M9` protocol** (`kernel-shape-opus.md:291–299, :585`): `Send` with up to 4 grants, `Revoke`/`RevokeStep`, `Release` / *release pending*, `Call1`/`Answer1`, `UnitRequest`/`UnitAnswer`, `ReportAsk`/`Report`.
7. **Core moves + kernel restarts/generations in `CoreWord`** (`:580`), and admission `budget` checks during `core_give`.
8. **`SEALING` state, `role_hand` two-step hand-over (`HANDING -> HELD`), and `unfenced` expiry (`FENCE_NS`)** (`kernel-interface.md:1029, :1033, :1221`).
9. **Memory ordering** under x86-TSO and Armv8 (`kernel-shape-opus.md:579`), plus intra-kernel concurrency (`cspace` slot read, cross-core thread suspension, `:587`).
10. **Scale beyond `nk=3, nc=4, D=2`** (`:585`).

---

## 2. Refinements, unproven cases, and non-vacuity checks

### 2(c). Non-vacuity checks (24/24 PASS)

All 19 built-in broken variants in [kernel-shape-explorer.py](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-explorer.py) plus 5 new property mutants (`test_nonvacuity.py`) were executed and every invariant/liveness check was verified non-vacuous:

- **Built-in 19 broken variants:** all 19 failed as expected in 1–13 steps (`stale_parked` 9 steps `-> P2`, `no_mark` 7 steps `-> P7`, `giver_live_only` 7 steps `-> P7`, `r6_inflight` 13 steps `-> P7`, `take_any_class` 4 steps `-> P6`, `role_at_read` 10 steps `-> P6`, `bsp_moves` 8 steps `-> P8`, `free_early` 1 step `-> P2`, `fence_owned` 7 steps `-> P2`, `no_flush` 7 steps `-> P5`, `acks_owned` 6 steps `-> P4`, `park_no_ack` 10 steps `-> LIVENESS`, `no_seal_timeout` 3 steps `-> LIVENESS`, `resume_any` 3 steps `-> BUDGET`, `rebuild_live_only` 4 steps `-> IOMMU`, `retire_then_give` 3 steps `-> RETIRE`, `shared_credit` 11 steps `-> LIVENESS`, `no_gen_reset` 6 steps `-> LIVENESS`, `no_purge` 5 steps `-> STALE`). Baseline `:correct` runs all pass (`moves:correct` 601,259 states / 24.2 s; `shootdown:correct` 331,860 states / 14.5 s; `seal:correct` 66,352 states / 0.99 s; `credits:correct` 1,050 states / 0.01 s).
- **5 added mutants covering previously untested checks:** `mutant:P1` (start on executing core: **P1** in 2 steps, 12 states), `mutant:P3` (execute while dead: **P3** in 1 step, 7 states), `mutant:RING` (unchecked send: **RING** overflow in 4 steps, 247 states), `mutant:Seal LIVENESS` (no resume/kill: **LIVENESS** in 2 steps, 11,322 states), `mutant:Credits LIVENESS` (no consume: **LIVENESS** in 10 steps, 1,050 states).

### 2(a)–(b). Violations found under refinement and added cases

| Test & Configuration | Outcome | States / Time | Classification |
|---|---|---|---|
| `MovesMultiTakerABA(leave_epoch_in_word=False, deaths=0)` | **VIOLATION P2** (10 steps) | 279 / 0.01 s | **Real protocol fault (`CoreWord` ABA)** |
| `MovesMultiTakerABA(leave_epoch_in_word=True [mod 4], deaths=0)` | **VIOLATION P2** (31 steps) | 795,380 / 39.02 s | **Real fault if epoch wraps** |
| `FreeOnlyTakeMultiTaker(allow_leaving_take=True, deaths=0)` | **VIOLATION P2** (10 steps) | 353 / 0.01 s | **Real protocol fault (1 taker + split `settle` ABA)** |
| `FreeOnlyTakeMultiTaker(allow_leaving_take=False, deaths=0)` | **OK** | 3,749 / 0.22 s | **Verified fix (`FREE -> JOINING` only)** |
| `MovesRestartsClean(deaths=3, gmax=4, monotonic_req)` | **OK** | 241,704 / 8.00 s | Baseline with non-wrapping epochs |
| `MovesRestartsClean(deaths=3, gmax=2 [gen-wrap], monotonic_req)` | **VIOLATION P2** (38 steps) | 204,071 / 6.07 s | **Real fault if `g` wraps** (mitigated by 32-bit `g`) |
| `MovesRestartsClean(deaths=2, gmax=4, emax=2 [toggle-wrap])` | **VIOLATION P2** (19 steps) | 5,011 / 0.11 s | **Real spec fault (`R-1` lacks monotonic epoch)** |
| `CreditsRefined: sealed_x_resume_r2_only(deaths=1)` | **VIOLATION STALE** (6 steps) | 775 / 0.00 s | **Real spec fault (`R-9` omits `R0`)** |
| `CreditsRefined: single_fifo_hol(deaths=2)` | **VIOLATION LIVENESS** (8 steps) | 2,646 / 0.01 s | **Real spec fault (`R-13` single FIFO ring HoL)** |
| `CreditsRefined: two_rings_correct(deaths=3)` | **OK** | 2,153 / 0.01 s | **Verified fix (two separate rings per pair)** |
| `SealRefinedFast(deaths=2, gmax=4, r10_includes_floor=False)` | **VIOLATION IOMMU** (3 steps) | 192 / 0.00 s | **Real spec fault (`R-10` omits `.floor`)** |
| `MovesWriteSkewClean(gate_lock=False)` | **VIOLATION P6-SKEW** (6 steps) | 1,741 / 0.05 s | **Real spec/G12 requirement (`R-5` write skew)** |
| `MovesWriteSkewClean(gate_lock=True)` | **OK** | 436,770 / 21.54 s | **Verified fix (`G12` gate lock across check+CAS)** |
| `MovesSplitSettle(settle_uses_cas=False)` | **VIOLATION P2** (7 steps) | 827 / 0.02 s | **Refinement artefact** (confirms CAS rule) |
| `MovesSplitSettle(settle_uses_cas=True)` | **OK** | 149,134 / 7.13 s | Verified with CAS |
| `MovesConcurrentGive(lock=False)` | **VIOLATION ZERO-CORES** (7 steps) | 5,719 / 0.16 s | **Refinement artefact** (confirms kernel lock) |
| `MovesConcurrentGive(lock=True)` | **OK** | 601,259 / 26.06 s | Verified with kernel lock |
| `MovesSplitUnmap(deaths=1)` & `MovesSplitR6D1(deaths=1)` | **OK** | 803,726 / 38.03 s; 75,039 / 3.31 s | Holds under split unmap / split R6 (`deaths=1`) |

#### Real Protocol Fault 1: `CoreWord` ABA on `LEAVING` (Multi-taker AND 1-taker + split `settle`)
The explorer's `TI == 0` guard (`:410`) forced takers to run one at a time, hiding ABA on [CoreWord](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L595) (`state, check, slot, gen` — no leave epoch). Even with a single taker (`A`) and split `settle` (`FreeOnlyTakeMultiTaker(allow_leaving_take=True)`):
```text
VIOLATION P2: core 0 runs A but its word no longer names it after 10 steps (353 states, 0.01s)
1. A gives core 0              2. core 0 parks
3. settle reads core 0 LEAVING(A)+parked
4. A reads core 0 (W=2, WK=1) to register
5. A CAS takes core 0          6. core 0 starts in A's entry stub
7. core 0 checks its word and enters A   8. core 0 joined A
9. A gives core 0              10. core 0 CAS settles free   <-- matches stale LEAVING(A) from step 3!
```
With two takers (`MovesMultiTakerABA`), `B` wins the stale `LEAVING(A)` CAS while `A` just wrote `LEAVING(A)` and `core 0` is still executing `A` (10 steps `-> P2`). Adding a 2-bit leave epoch (`mod 4`) still fails after 4 leaves in 31 steps. **Fix verified:** disallow `core_take` from `LEAVING` (`allow_leaving_take=False`, `OK` in `3,749` states): only `settle` transitions `LEAVING -> FREE` by CAS, and `core_take` transitions `FREE -> JOINING` only. (Note: `MovesRestartsClean(gmax=2)` shows the analogous generation-wrap ABA if `g` wraps in 1 bit while a taker holds a stale `FREE` or `LEAVING` snapshot, failing `P2` in 38 steps; 32-bit `g` makes wrap practically unreachable, whereas without a leave epoch ABA happens in 0 deaths and 1 leave cycle.)

#### Real Spec Fault 2: `R-1` omits monotonic non-wrapping `park_request`
`R-1` (`:516`) specifies "writes a new value of that core's park request", which `Moves` implements as a 1-bit `0/1` toggle (`PKC`). In `MovesRestartsClean(deaths=2, gmax=4, emax=2)`:
```text
VIOLATION P2 after 19 steps (5,011 states, 0.11s):
1–12. A(g=0) fenced, restarted as A(g=1), fenced (fence cancels start req -> core 0 stays parked from step 3, req=1)
13–17. B takes core 0 -> core 0 enters B -> joined B
18. B gives core 0 (toggles park_request 1 -> 0, which matches stale parked=0 or wrapped epoch!)
19. core 0 settles free while core 0 is STILL running B!
```
**Fix:** [abi/](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L620) must define `park_request` and `parked` as a monotonic non-wrapping counter (64-bit, or 32-bit epoch incremented per fence/give), as `kernel-interface.md:1060` already terms it "the fence epoch", rather than an alternating flag. (`MovesRestartsClean` with monotonic epochs and `deaths=3` passes in `241,704` states.)

#### Real Spec Fault 3: `R-9` on resume omits `R0` (`CreditsRefined`)
`R-9` (`:524`) requires a resuming kernel to serve pending revocations and run `R2` for every peer whose generation ended while it was sealed, omitting `R0`. In `sealed_x_resume_r2_only(deaths=1)`:
```text
VIOLATION STALE: pending signal from gen 0 delivered to Y(g=1) after 6 steps (775 states, 0.00s)
1. X signals Y(g=0) -> pending signal table    2. X seals (maps_of[Y]=0)
3. Y(g=0) dies                                 4. Y starts fresh (g=1)
5. X resumes (runs R2 only, skips R0)          6. deliver pending signal (psg=0) to Y(g=1)
```
Additionally, `R-9` conflicts with [the reclaim barrier](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1127) if sealed `X` held `maps_of[Y] = 1` (not modelled in `CreditsRefined`): `Y` cannot leave `fenced` until `X` is resumed or killed. **Fix:** `R-9` must mandate running both `R0` (clearing `R-14` credits and purging stale pending signals) and `R2` before any thread runs.

#### Real Spec Fault 4: `R-13` shares one FIFO ring (`CreditsRefined`)
`kernel-interface.md:862` prescribes *one FIFO ring per ordered pair*, and `R-13` (`:528`) puts two credit classes (`Qu`, `Qk`) on "The ring of each ordered pair". In `single_fifo_hol(deaths=2)`:
```text
VIOLATION LIVENESS after 8 steps (2,646 states, 0.01s):
1. X needs to send kernel request   2. Y(g=0) dies   3. X runs R0   4. Y starts fresh (g=1)
5. Y(g=1) dies                       6. X runs R0   7. Y starts fresh (g=2)
8. task 0 sends user message to Y(g=2)   <-- fills shared FIFO / user unread message blocks kernel request!
```
Once user tasks fill the ring and `Y`'s user threads never consume them, `Y`'s kernel consumer cannot dequeue a kernel `Revoke` or `UnitRequest` sitting behind unread user entries in a single FIFO ring. **Fix verified:** two separate rings (kernel ring + user ring) per ordered pair (`two_rings_correct(deaths=3)` passes in `2,153` states).

#### Real Spec Fault 5: `R-10` IOMMU rebuild omits `.floor` (`SealRefinedFast`)
`R-10` (`:525`) preserves context entries whose root table lies in memory "the ownership table gives to a starting, live, sealing or sealed kernel". Unlike `R1` (`kernel-interface.md:1107`), `R-10` forgets `.floor` chunks (whose ownership words stay `0` *none* after boot). In `SealRefinedFast(r10_includes_floor=False)`:
```text
VIOLATION IOMMU: B owns device without IOMMU context entry after 3 steps (192 states, 0.00s)
1. accuse C(st=0)   2. fence C confirmed   3. unit role moves to A, rebuild unit
```
Because `B`'s `iospace` root sits in `B.floor` (`own=0`) while `B` is live/sealed, `R-10` clears `B`'s active IOMMU entry. **Fix:** explicitly include kernel floors (or follow `kernel-interface.md:1222` live/sealed reports + floor check).

#### Real Spec / `G12` Fault 6: `R-5` cross-word write skew + 1-core contradiction (`MovesWriteSkewClean`)
Because `ROLE` and `CoreWord` are two separate 64-bit words, splitting `core_take`'s `ROLE` check from its `CoreWord` CAS (`MovesWriteSkewClean(gate_lock=False)`) fails in 6 steps:
```text
VIOLATION P6-SKEW: A holds mapped unit while naming weaker core 1 (state=3) after 6 steps (1,741 states, 0.05s)
1. A reads core 1 free to take              2. A re-reads ROLE (not A) before CAS on core 1
3. role_hand step 1: B writes HANDING(B->A) 4. role_hand step 2: A writes HELD(A)
5. A checks no weaker core & maps unit      6. WRITE-SKEW CAS: A commits JOINING on core 1
```
**Two consequences for the spec:** (1) `R-5` **requires** `G12`'s gate lock to serialize `core_take` with `role_hand` step 2 / takeover (`gate_lock=True` passes in `436,770` states; in Stage 2, a single-core kernel taking a second core is already racing a multi-core `ROLE` update); (2) `R-5` sentence 2 ("A new holder, after it writes held and before it maps the unit, gives away any core of a weaker class") is **impossible** if `A` holds only 1 core (which is weaker, e.g. via `core_give` requiring `>= 2` owned cores at `:390`, Part 4.2 `:253`), so `role_hand` (`kernel-interface.md:1230`) must reject targets holding any weaker core *before* `HANDING`.

#### Refinement Artefacts
- **`MovesSplitSettle(settle_uses_cas=False)` (`VIOLATION P2`, 7 steps, 827 states):** If `settle` writes `FREE` blindly after reading `LEAVING+PKC=1`, a concurrent `take` (`JOINING`) + `start` is overwritten with `FREE`. Passes (`149,134` states) once `settle` uses CAS against `(LEAVING, WK, g)` — confirming [Part 4.1](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L240) (all living-part words change by CAS).
- **`MovesConcurrentGive(lock=False)` (`VIOLATION ZERO-CORES`, 7 steps, 5,719 states):** Two cores of `A` concurrently observe `>= 2` owned cores and both commit `LEAVING`, leaving live `A` with 0 cores. Passes (`601,259` states) under the per-kernel lock — confirming [Part 4.3](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L263).

---

## 3. Hardware sources for "taken only once confirmed parked"

### ARM64: PSCI (`CPU_OFF`, `AFFINITY_INFO`)
- **Sources:** Arm Power State Coordination Interface Specification **DEN 0022E** (PSCI v1.2) / **DEN 0022F.b** (PSCI v1.3), §§4.3, 5.1.3, 5.1.5, 5.5 (`CPU_OFF`, §§5.5.1–5.5.2), 5.7 (`AFFINITY_INFO`, §§5.7.1–5.7.2), 6.6 (*Implementation CPU_ON/CPU_OFF races*, Fig. 9), 6.9 Table 18; Trusted Firmware-A `lib/psci/psci_off.c` (`psci_do_cpu_off`, lines 38–190).
- **What `AFFINITY_INFO` guarantees:** Returning `0` (`OFF`) guarantees that the target PE has completed `pwr_domain_off` (`psci_off.c:138`), flushed its caches (`psci_flush_cpu_data`, `:164`), written `AFF_STATE_OFF` (`:165`), executed `dsb ish` (`:166`) and invalidated local CPU data (`:167`), and entered `pwr_domain_pwr_down` (`:181–186`). That is, the PE has exited coherency and no longer executes Non-secure instructions. It provides **no generation/epoch**, and **DEN 0022 §6.6** explicitly documents a firmware race if another PE calls `CPU_ON` concurrently with `CPU_OFF` completion. Furthermore, `CPU_OFF` returns `DENIED` (§5.5.2) when a Trusted OS is pinned to the core.
- **Implementability & latency:** **Conditionally implementable** if (1) the gate is the sole caller of `CPU_ON`, `CPU_OFF`, and `AFFINITY_INFO` and forbids `CPU_ON` until `CoreWord` is `FREE` (never issuing `CPU_ON` while `CPU_OFF` is in flight), and (2) Trusted-OS / class-0 cores are excluded by `MIGRATE_INFO_TYPE`/`MIGRATE_INFO_UP_CPU` at boot (`kernel-interface.md:1094`) or retired on `DENIED`. **Latency:** unmeasured in the repository; firmware power-down and cluster cache clean typically take hundreds of microseconds to milliseconds, tight against `FENCE_NS = 10 ms`.

### x86-64: `INIT` / `SIPI` / `NMI` sequence
- **Sources:** Intel 64 and IA-32 Architectures Software Developer's Manual Vol. 3 (Order No. **325384**): §§10.4.3–10.4.4 (Dec 2024+ eds.; §§9.4.3–9.4.4 in 2022–2023; §§8.4.3–8.4.4 in 2016–2021) — *MP Initialization Protocol*; §§12.4.7.3–12.4.7.4 — wait-for-SIPI state; §§25.8, 27.2 (June 2025+ eds.; §§23.8/25.2 in 2016–2022; §§24.8/26.2 in 2023–2024) — `INIT` blocked in VMX root, causes VM exit in VMX non-root; §§33.5, 33.14.1–33.14.4, 33.15 (June 2025+ eds.; Ch. 34 earlier) — `INIT` inhibited inside SMM and delivered on `RSM` (remaining blocked only if returning to VMX root).
- **Can an `INIT` be pending or delivered after another kernel restarts the core?** **Yes, in two scenarios:**
  1. If a fence driver sends `INIT` while the target core is inside **SMM** (invisible to the `vmx` beacon flag), the CPU latches the pending `INIT` and delivers it when `RSM` returns outside VMX root (§33.14.2).
  2. If [kernel-interface.md#L1092](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1092)'s alternative confirmation (`SETTLE_NS` = **1 ms** after `INIT` with `vmx == 0`) is used, the `1 ms` timer expires **9 ms before** Intel SDM §10.4.4's mandatory **10 ms** `INIT -> SIPI` delay (followed by SIPI, **200 µs**, SIPI). Worse, if `INIT` was latched during SMM and fired after `core_start` or `RSM`, the core restarts or resets under the new kernel.
- **Implementability & latency:** **Implementable only if** the `SETTLE_NS` fallback (`kernel-interface.md:1092`) is **removed**: fence confirmation must come *exclusively* from `parked == park_request` written by the park stub (`CLI; HLT`) after the two SIPIs, and voluntary `core_give` must self-park directly into the stub without `INIT`. **Latency:** SDM §10.4.4's protocol already imposes `10 ms + 200 µs = 10.2 ms` minimum delay between `INIT` and the second `SIPI`—exceeding `FENCE_NS = 10 ms` (`kernel-interface.md:1242`) before the park stub even runs.

### RISC-V: SBI HSM (`sbi_hart_stop`, `sbi_hart_get_status`)
- **Sources:** RISC-V Supervisor Binary Interface Specification v1.0.0 / v2.0 Ch. 9 §§9.2–9.3, v3.0 §§9.1.2–9.1.3 (HSM Extension, EID `0x48534D` `"HSM"`); OpenSBI `lib/sbi/sbi_hsm.c` (`sbi_hsm_exit`).
- **What it confirms:** `sbi_hart_stop` (FID 1) stops only the calling hart (with S-mode interrupts disabled); `sbi_hart_get_status` (FID 2) returns `0 STARTED..6 RESUME_PENDING`, and the SBI spec explicitly warns that the returned state may already be stale by return time if another hart calls `sbi_hart_start`/`stop`/`suspend` concurrently. Critically, in **OpenSBI** `lib/sbi/sbi_hsm.c`, `sbi_hsm_exit` transitions `SBI_HSM_STATE_STOP_PENDING -> SBI_HSM_STATE_STOPPED` via `__sbi_hsm_hart_change_state` **before** invoking `hsm_device_hart_stop()` or `jump_warmboot()`. Thus standard `STOPPED` can be observed while the stopping hart is still running M-mode code or draining platform power-down.
- **Implementability & latency:** **Not implementable with standard SBI HSM alone.** It requires the custom M-mode `fence_hart` extension (`kernel-interface.md:1095`), engineered to execute the hart stop/quiesce and memory barrier **before** publishing `STOPPED` (and updating `parked`), with the gate serializing `sbi_hart_start` and voluntary `sbi_hart_stop` self-parks confirming `parked == park_request` before `sbi_hart_stop`. **Latency:** platform-specific (`WFI` loop vs. hotplug controller); unmeasured.

---

## 4. Completeness of Stage-1 list (`9.4`) and hot-path cost

### Missing from `9.4` ([kernel-shape-opus.md#L589-L656](file:///Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md#L589-L656))

1. **Per-core execution & trap state (Item 6):** Item 6 copies [kernel-interface.md#L608](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L608) plus flush epoch/TLB/shootdown slots, but omits per-core kernel trap stacks, x86-64 GDT/TSS/IST/`GS_BASE`, ARM64 `TPIDR_EL2`/`EL1`, RISC-V `sscratch`, and per-core gate save areas when the gate uses a window ([kernel.md#L146](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L146)).
2. **Debug trace rings (`kernel-interface.md:1279`):** Single-writer serial trace writes break when *k* cores of one kernel log concurrently (`debug_write`, `trace_emit`, IOMMU/gate codes); Stage 2 needs either per-core ring areas (changing `StartDebug` and `69,632`-byte node debug layout at `:1260`) or serialized slot reservation.
3. **Node crash record (`kernel-interface.md:1325–1341`):** Two cores failing/handling fence NMIs at once will race on `commit` and the 32 detail words unless serialized or given a first-writer CAS on `commit`/lock.
4. **Debugger stub (`kernel-interface.md:1389`):** Needs per-core register save slots per kernel (not one slot per node) and cross-core stop/release coordination inside a multi-core kernel.
5. **Scheduler cross-core mechanics (`kernel-interface.md:561–573, :612, :1566`):** Item 12 adds home core to `sched`, but omits how `sched_set_cores`, cross-core wakeup IPIs, and direct-switch passive lends update queues/timers safely across cores of one kernel.
6. **`task_revoke` sibling halting (`kernel-interface.md:959`):** Setting `revoked` is no longer "at once" across cores without sending an IPI and waiting (via Item 11's *leaving its core* state) for sibling threads currently executing in user or kernel mode on other cores of the kernel.
7. **Multi-core updates to `R0–R6`, `aspace`, and `irq`:**
   - `stale` detection (`:1071`) and `beacons` (`9.4` E): `9.4` forgets removing `save_seal` (`:1061`), and must specify monitoring *all* core-beacon heartbeats naming `(K, g)`.
   - `R4` audit (`:1113`): in Stage 2, auditing chunk map counts must hold the kernel + gate locks or tolerate concurrent mapping/shootdown epochs.
   - `aspace` / G7 (`9.4` Item 10, `:899`): Stage-2 shootdowns need per-core acknowledgement slots and multi-core ASID/PCID epoch allocation (avoiding global ASID leaks across moves).
   - `irq` (`9.4` Item 13) + `R-11`: making the `12 KB` interrupt table per physical core requires defining how `core_give` retargets/migrates claimed `irq` entries (`irq_control` ownership), how `irq_ack` from another core locks that core's controller state, and how `R-11` masks all physical-core vectors of a sealing kernel.
8. **Point-2 contract/ABI repairs:** `abi/` in `9.4` (`D`) must already enforce `FREE -> JOINING`-only takes (closing the `LEAVING` ABA bug), monotonic non-wrapping `park_request` (`R-1`), two distinct rings per ordered pair (`R-13`), `.floor` inclusion (`R-10`), `R0` on resume (`R-9`), and `G12`-serialized `R-5` + pre-`HANDING` class checks.

### Stage-1 hot-path cost (`D-117`: no payment at every access/IPC)

- **Item 7 (`cspace` 16-byte directory + seqlock read, `:604`):** Doubles directory size and puts a seqlock sequence check + retry loop on **every capability lookup** (`call`, `send`, `reply_recv`). Unless compiled out at build time when `CORES_PER_KERNEL_MAX == 1`, it violates [D-117](file:///Users/btw/Documents/repos/Docs/decisions/README.md#L127) on every Stage-1 syscall (`M5:650` tail latency).
- **Item 8 (`notify` atomic OR, `:605`):** Turns single-core `signal` and interrupt delivery into an atomic `LOCK OR` / `LDSET` instruction on every signal unless replaced by a plain store when `CORES_PER_KERNEL_MAX == 1`.
- **Item 11 (`thread` `"leaving its core"` state, `:608`):** Reserving the enum variant is free, but checking cross-core suspension on dispatch/IPC hot paths adds branch cost unless gated out at compile time for `CORES_PER_KERNEL_MAX == 1`.
- **Items 6, 9, 10, 12:** Reserve struct fields/space cleanly with zero hot-path instructions when Stage 1 skips the locks (`kernel-shape-opus.md:237, :601`). `[Suspicion: Items 7 and 8 are left ambiguous in 9.4 because 9.4 says "stage 1 reserves the fields and never contends them" only under Item 6/B's heading while stating 7/8's multi-core operations directly.]`

---

## 5. Judgement

1. Yes: the three-stage plan (Stage 1 one-core kernels with one-shot calls; fixed-size Stage 2; elastic Stage 2) is sound **only** if `abi/` fixes Point 2's six faults first.
2. Stage 1 gives the project a working single-core verification target, gate prototype, and `model` oracle without waiting on unfinished concurrent `VerusSync` gate proofs (`gate-page-tables.md:602`).
3. Deferring `core_give`/`core_take` and `LEAVING`/`settling` until Stage 2b cleanly avoids shipping untested `R-16` complexity while keeping `CoreWord` and two rings in `abi/`.
4. Fixed-size multi-core kernels (Stage 2a) directly solve the `4,096`-grant ceiling for multi-threaded apps without `thread_move` or cross-kernel page-table copies (`:121`).
5. However, Stage 1 must compile out Items 7, 8, and 11's runtime checks under `CORES_PER_KERNEL_MAX == 1` to respect `D-117`'s zero-overhead fast-path rule.
6. The two-lock/shootdown risks (`kernel.md:59`, `M5:377–386`) and `G12` proof burden sit inside Stage 2a, not Stage 1, so Stage 1 stays reversible.
7. **First thing that would make me abandon Stage 2 (and stay on Stage 1):** failure to prove `G12` cleanly in Verus or the single kernel/gate lock violating `D-042` latency bounds (`heterogeneous-cores.md:157`, `M5:377–386`) on real desktop traces.
8. A close second abort trigger is hardware-stop verification showing that `INIT` + `SMM` delays exceed `FENCE_NS = 10 ms` across cores, freezing large shared kernels on fence failure.
9. If either trigger fires on the reference desktop, Stage 1's one-core kernels + two-ring/one-shot ABI already form a complete `B` architecture with no wasted kernel work.
10. Do not reopen `D-026`/`D-108` for multi-core kernels until `G12`, desktop `WRSSQ` + lock measurements (`kernel-shape-opus.md:441–451`), and Point 2's fixes pass.
