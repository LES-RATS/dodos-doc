# Verification of `kernel-shape-opus.md` (Elastic Kernels, C*)

- **Reviewed report:** [`Docs/research/drafts/kernel-shape-opus.md`](/Users/btw/Documents/repos/Docs/research/drafts/kernel-shape-opus.md) (baseline `Docs` `b15f37c`, `dodos-kernel` `model` `2afc901` and `trial-multicore` `f9933bd`).
- **Explorer checked:** `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/pass14/elastic_opus.py` (copied to `/tmp/verify-opus-shape/elastic_opus.py`) and adversarial extensions in `/tmp/verify-opus-shape/verify_elastic.py`.
- **Reviewer:** gemini-4-hydrogen, following `pass14/XSHAPE.md` and `pass14/ELASTIC.md`.

---

## Summary Table of Verdicts

| Claim or Mechanism | Verdict | Detail |
|---|---|---|
| Repo fault counts & families (`:46-49`) | `CONFIRMED` | Rounds 6–7 split and 7 fault families match `verify-opus:36-37`, `verify-hydrogen:65-73`. |
| M5 trial numbers (`:53-71`, `:425-435`) | `CONFIRMED` (with caveats) | Individual numbers match `results-mac-m5.md`; `:28, 429` mix fine/range-lock results into C* v1, where Candidate 1 beats single-lock Candidate 3 on `br` (`ipi=0`), `a2`, `a3`. `:58` omits Candidate 1's `p99.9 = 1.1 × W` (`M5:748`). |
| `remote.rs` removed function line count (`:372`) | `WRONG` | The 11 named functions span **174 lines** (`fn` to `}`), or **197 lines** with `///` doc comments (`2afc901:model/src/remote.rs`), not 211. Total `1,424` and `moves.rs` `269` are `CONFIRMED`. |
| External systems & hardware quotes (Appendix B) | `CONFIRMED` | All 6 primary URLs (`5618.pdf`, `hive.pdf`, `zellweger-decoupling-cores.pdf`, Arm `TLBI ASIDE1IS`, Arm `TTBR0_EL1`, RISC-V SBI v3.0 `ext-rfence.html`) verify verbatim. |
| `elastic_opus.py` non-lifecycle runs (`:483-484`) | `CONFIRMED` | `0` diff vs Appendix A; `correct` (`1,819,997` states, `9,015,693` transitions) and all 5 broken variants (`free_early --no-p2` included) reproduced under `timeout`. |
| `elastic_opus.py correct --lifecycle` (`:485`, `54.97M` states) | `NOT VERIFIED` | Timed out (`exit 124`) at `120 s` even with `--deaths=1 --lifecycle`; full 47-minute run not executed within budget. |
| Core leave/join "confirmed parked" (`:115, 129-130, 249-251`) | `BROKEN` | On x86-64, `core_beacon.parked` holds a fence epoch written only by the fence's park stub (`:1052`), never cleared by `core_start`, so a stale non-zero `parked` passes `confirmed parked` immediately after step 1 (`leaving`) while the core still runs `J` (`/tmp/verify-opus-shape/verify_elastic.py` Test 1, 8 steps). On ARM64 with Trusted OS (`:1086`), `CPU_OFF` fails so `AFFINITY_INFO` never returns `OFF` and `CPU_ON` fails. |
| Dying giver mid-`core_give` vs `leaving -> free` (`:134, 250-251, 736`) | `BROKEN` | Table 4.2 (`:250-251`) allows `leaving(J) -> free` or `joining(K)` without checking `J` is live; an in-flight `INIT`/`NMI`/`SDEI` dispatched under `G10` while `word[c] == leaving(J)` lands after `K` takes and starts `c` (`verify_elastic.py` Test 4, 6 steps). |
| Multi-core fence when one core has weaker class (`:194-197, 249, 259, 340`) | `BROKEN` | Table 4.2 (`:249`) omits checking whether `K` holds (or is handing target of) a unit role before `core_take`, letting a unit-role holder take a class-1 core and violate Invariant 10 (`:340`; `verify_elastic.py` Test 2, 1 step). On ARM64, a core booting during `core_take` step 3→4 has SDEI masked until `SDEI_PE_UNMASK`, creating an `unfenced` window for all of `K`. |
| Zero-core sealed kernel (`:24, 167, 258, 324`) | `BROKEN` | Deadlocks `X`'s reclaim barrier (`:1119`, `verify_elastic.py` Test 3a), deadlocks `M4 Revoke` (`:294`, Test 3b), loses IOMMU entries in `roles::rebuild()` (`roles.rs:446`, `:1214`), has no wake path for incoming `M1`/`M2`/`M3`, bypasses per-core admission (`budget`) across multi-core seal → 1-core resume, and `retire` (`:325`) cannot execute `memory_give` after the last core leaves. |
| Single lock vs D-042 & slow E-core (`:32, 177, 263-265`) | `BROKEN` / `WRONG` | Queue lock makes latency `k × W_max`, serializes P-cores behind E-cores (`heterogeneous-cores.md:157`), and holding the lock across `aspace_unmap` IPIs / `thread_suspend` breaks `D-042`, while releasing it breaks `"every event of a node runs alone"` (`:263`, `system.rs:5-7`). |
| Shared `Q` credit & `M1`/`W7` bounds (`:285, 291-298`) | `BROKEN` | `M2`, `M3`, `M4`, `M6`, `M8` share one credit pool `Q`: 4 user tasks sending unread `M2`s starve kernel `M6 UnitRequest` / `M4 Revoke` (`verify_elastic.py` Test 6, 5 steps). `W7` `consumed` counter has no reset/drain rule across `Y` death; `M1` pending table has no purge on `Y` death. |
| `aspace_unmap` x86-64 shootdown prose (`:133` vs `elastic_opus.py:705`) | `BROKEN` (in prose) | `:133` waits only for in-memory acks; if a `leaving` core masks interrupts and parks before the shootdown IPI, unmap deadlocks (`verify_elastic.py` Test 5, 3 steps) unless `c1` checks `core_word`/`parked` as `elastic_opus.py:705` silently assumes. |
| Case against A, B, C, D1–D4 & `G12` proof cost (`:26-30, 119, 264, 393`) | `WRONG` (in part) | Omits `Run-Grant` (`kernel-shape-hydrogen.md:14`), overstates Wasm 0.3 multithreading (`wasm-abi.md:128`), and ignores `gate-page-tables.md:602` (`VerusSync` for `G12` is unfinished even in Asterinas). |

---

## 1. Repository, Decisions, `model`, and `trial-multicore`

- **Contract and decisions (`Docs` `b15f37c`):** Citations to `architecture/kernel-interface.md` (`:9-18`, `:316-320`, `:593-681`, `:742-866`, `:868-905`, `:991-1245`, `:1743-1755`, `:1872-1894`), `architecture/kernel.md` (`:24-181`), and `decisions/README.md` (`D-026..D-124`) match `b15f37c`. Working-tree edits made after Opus took its citations (e.g., I/O ports added after `:1388`) do not alter `b15f37c`.
- **Trial fairness (`f9933bd:trials/multicore/results-mac-m5.md`, `README.md`):** Every cited metric in `:55-70` and `:425-435` appears at the cited lines (`M5:80-82`, `145-149`, `205-235`, `377-402`, `647-652`, `905-917`, `1056-1060`, `1081-1092`, `1113`). Three fairness issues weaken `:28-32`:
  1. `:28` headlines `2.3 to 9.6×` (`M5:651`, 3rd series fine locks) and `1.55 to 2.0×` (`M5:1060`, 4th series range locks), even though C* v1 uses **one group lock** + seqlock slot reads (`:17, 263`). Under one group lock at `k = 4, ipi = 0`, Candidate 1 **beats** Candidate 3 by `6–21%` on `br` (`M5:383-386, 943-945`).
  2. `:58` writes `"p99 1.04 × W against 1.7 × W; p99.9 against 2.1 × W"`, omitting Candidate 1's own `p99.9 = 1.1 × W` (`1.1 µs` at `W = 1 µs`, `M5:748`).
  3. `:71` notes `k = 6, 8` mixed P/E cores (`M5:40-44`), and `:433` notes core moves are `0.2 µs` lock hand-overs (`M5:224-235`), not physical core stops/starts; `:429` cites `M5:402` (`2.3 to 11×`) as "with one lock" (series 2 used whole-call seqlock reads + one lock).
- **`model` (`dodos-kernel` `2afc901`):**
  - `remote.rs` total (`1,424`), `moves.rs` (`269`), `system.rs:5-7`, `table.rs:186-191`, and `lib.rs:19-20` are exact.
  - **Wrong count at `:372`:** The 11 functions listed (`proxy_index`, `serve_request`, `proxy_at`, `answer_proxy`, `cancel_proxy`, `cancel_remote`, `defer_transfer`, `transfer_wait`, `transfer_reply`, `refused`, `returned`) measure **174 lines** strictly (`fn` to `}`), or **197 lines** including preceding `///` comments, not `211`.

---

## 2. External Systems and Hardware Claims (Appendix B)

All six primary sources were fetched on 16 November 2026 into `/tmp/verify-opus-shape/refs/` and converted (`pdftotext -layout`).

- **von Tessin 2012 (`5618.pdf`):** Confirmed verbatim: `§3` (`"Instead of running one node per CPU, multiple CPUs can be clustered into (assigned to) a node. Within each node, we apply the big-lock design..."`; `"IPC only works within a node, communication across nodes has to be implemented via shared userlevel memory"`), `§4.4.1` (`"only 80 LOC of C code"`, `"two thread states and 8 preemption points had to be added"`, `"1000-LOC proof"`), `§6.1.1` (two correspondence proofs missing: kernel bootstrapping and thread-deletion). Important omitted context: seL4::CMK is **event-based with no recovery** and had no scalability evaluation yet (`§6.1.2`).
- **Chapin et al., Hive 1995 (`hive.pdf`):** Confirmed verbatim: `§3` (`"When the system boots, each cell is assigned a range of nodes that it owns throughout execution. Each cell manages the processors, memory, and I/O devices on those nodes..."`) and `§4.2` (`"Write access to a page is granted to all processors of a cell as a group... allows it to freely reschedule the process on any of its processors without sending RPCS to remote cells"`). Note that Hive still implements cross-cell `spanning tasks` (`§3.2`) and hardware FLASH firewalls (`§2`).
- **Zellweger et al., Barrelfish/DC 2014 (`zellweger.pdf`):** Confirmed verbatim: `§4` (`"we do not consider fault tolerance and isolation for now"`), `§5.1` Table 2 (`idle` `down`: `0.8` Haswell to `3.5 µs` SandyBridge, `3.6 µs` under load, `3.7 µs` cross-socket; `up core`: `0.5` Haswell to `1.2 ms` Santa-Rosa; `up driver`: `7` Haswell to `29 ms` Santa-Rosa, up to `46 ± 76 ms` under load on Shanghai, dominated by loading the kernel image from storage).
- **Arm `TLBI ASIDE1IS` (`AArch64-tlbi-aside1is.html`):** Confirmed verbatim (`"The invalidation applies to all PEs in the same Inner Shareable shareability domain as the PE that executes this System instruction"`, and `HCR_EL2.{E2H, TGE} = {1, 1}` selects the `EL2&0` translation regime).
- **Arm `TTBR0_EL1` (`AArch64-ttbr0_el1.html`):** Confirmed verbatim (`CnP == 0b0` `"are permitted to differ from corresponding entries ... for other PEs"`; `CnP == 0b1` mismatch is `"CONSTRAINED UNPREDICTABLE"`).
- **RISC-V SBI v3.0 RFENCE (`ext-rfence.html`):** Confirmed `sbi_remote_sfence_vma_asid(hart_mask, hart_mask_base, start_addr, size, asid)` signature and Table 3 (`SBI_ERR_INVALID_PARAM` if any targeted `hartid` is `"not enabled by the platform or is not available to the supervisor"`).

---

## 3. Breaking C* Step by Step & Auditing `elastic_opus.py`

### 3.1 Verification of `elastic_opus.py`
Diffing `/private/tmp/.../elastic_opus.py` against Appendix A (`:537-941`) yielded `0` lines of difference. Runs executed under `timeout`:
- `timeout 300 python3 -I /tmp/verify-opus-shape/elastic_opus.py` → `exit 0`: `correct: OK, 1819997 states, 9015693 transitions`, plus exact reproduction of `old_no_settle` (3 steps), `fence_owned` (5 steps), `free_early` (1 step), `no_flush` (5 steps), and `acks_owned` (6 steps).
- `timeout 120 python3 -I /tmp/verify-opus-shape/elastic_opus.py free_early --no-p2` → `exit 0`: `P1` violation after 3 steps.
- `timeout 120 python3 -I /tmp/verify-opus-shape/elastic_opus.py correct --lifecycle --deaths=1` → `exit 124` (timed out at `120 s`); thus `correct --lifecycle` (`54,971,344` states, 47 min) is `NOT VERIFIED`.

### 3.2 Mandatory Focus Areas & Adversarial Tests (`/tmp/verify-opus-shape/verify_elastic.py`)
All 7 tests in `/tmp/verify-opus-shape/verify_elastic.py` ran cleanly under `timeout 60 python3 -I /tmp/verify-opus-shape/verify_elastic.py`. Each test's exact failure trigger is stated below.

1. **Leave/join protocol & "confirmed parked" per architecture (`:115, 127-134, 249-251`):**
   - **x86-64 (`:1052, 1081-1084`):** Contract `:1052` defines `core_beacon.parked` as `"the fence epoch written by the park stub, never by a kernel"`. Voluntary `core_give` (`:129`) has no fence epoch, and neither `core_start` (`:1174`) nor `core_take` (`:249`) clears `core_beacon.parked`. Once core `0` survives a fence (`parked != 0`), restarts in `A`, and later enters `leaving(A)` in step 1 of `core_give`, `B` immediately observes stale `parked != 0`, overwrites `word[0] = joining(B)`, and queues `Start` while core `0` still executes `A`.
     - *Test 1 (`test_stale_parked_x86`):* Fails if a core executes `K` when `word` no longer names `K` (`P2`) or `startp` is non-None while executing `K` (`P1`). Failed in 29 states (8 steps).
     - *BSP (`:1081, 1084`):* `INIT` cannot stop BSP, its NMI handler loops with interrupts masked (`:1080`, never enters the real-mode park stub or writes `parked`), and `:1084` excludes BSP from `SETTLE_NS`—so neither fence nor `core_give` has valid hardware `parked` confirmation on BSP if BSP does not explicitly jump into the park stub, and `core_start` (`:1174`) assumes the core sits halted in that stub.
   - **ARM64 (`:1086, 1088`):** A core hosting a resident Trusted OS refuses `CPU_OFF` (`:1086`) and loops in its handler writing `parked`. Calling `CPU_OFF` in `core_give` step 2 fails (`AFFINITY_INFO` never becomes `OFF`), wedging `leaving(J)` forever, and `CPU_ON` (`:130`) cannot start a core that never turned `OFF`. Worse, during `core_take` step 3→4 (`:130-131`), `CPU_ON` turns the core `ON` (`AFFINITY_INFO != OFF`) **before** the joining core runs `SDEI_PE_UNMASK` (`:1086`). If `K` is accused in that window, `SDEI_EVENT_SIGNAL` cannot stop the new core, turning the entire `k`-core kernel `unfenced`. Also `SDEI_PE_MASK` remains unguarded (`verify-opus` H4).
   - **RISC-V (`:1087`, `ext-rfence.html`):** Without `fence_hart`, `sbi_hart_get_status == STOPPED` is class `0`; with `fence_hart` (class `2`), confirmation is `fence_hart`'s answer (`:1087`), which never states whether `fence_hart` transitions HSM state to `STOPPED` so `sbi_hart_start` can reuse the hart. Additionally, `sbi_remote_sfence_vma_asid` (`ext-rfence.html` Table 3) returns `SBI_ERR_INVALID_PARAM` if any hart in `hart_mask` is `"not available to the supervisor"`—which includes a `leaving` hart that concurrently executes `sbi_hart_stop`.
   - **Giver `J` dying mid-`core_give` (`:134, 250-251`):** Table 4.2 allows `leaving(J) -> free` or `joining(K)` whenever `confirmed parked` holds, **without checking `member[J] == live`**. If `J` is accused after `c` parks, `G10` (`:194`) lets `J`'s fence driver issue `INIT`/`NMI`/`SDEI` to `c` while `word[c] == leaving(J)`, concurrently with `K` taking and starting `c`.
     - *Test 4 (`test_fence_vs_take_race`):* Fails if an in-flight `INIT/SDEI` dispatched while `word[0] == leaving(J)` lands on core `0` after `K` owns/starts it. Failed in 18 states (6 steps).
   - **Contradiction in `core_give` step 1 (`:128` vs `:273, 301`):** `core_give` is listed as a synchronous one-shot `M3` call (`:301`), yet `:128` sends `M6 UnitRequest` (up to `192` IRQ remapping invalidations `"as core_place does today"`). In `roles.rs:193`, `unit_request` enters `Wait::Node`, which waits for `UnitAnswer`—either violating the bounded non-waiting one-shot rule (`:273`) or releasing `c` to `K` while live `J` devices still target `c`'s APIC ID.
   - **Prose omission in x86-64 shootdown (`:133` vs `elastic_opus.py:705`):** `:133` states unmap `"waits for their acknowledgements in K's memory"`, omitting `elastic_opus.py:705` (`"A core that no longer runs A counts as acknowledged"`).
     - *Test 5 (`test_shootdown_park_deadlock`):* Fails if `unmap` stays in `"wait"` forever (cannot reach quiescent) when `c0` masks interrupts and parks before receiving the shootdown IPI. Failed in 18 states (3 steps).

2. **Fencing a multi-core kernel with a weaker fence class (`:194-197, 249, 259, 340`):**
   - `:259` and Invariant 10 (`:340`) require unit roles to be held only by kernels whose cores are all of the best class (`2` when available). Table 4.2 (`:249`) checks only `"the fence-class rule of the image"` on `core_take`, not whether `K` holds (or is `handing` target of) a unit role.
     - *Test 2 (`test_unit_role_class1_take`):* Fails if the unit-role holder's minimum core fence class falls below the best available live kernel's class. Failed in 2 states (1 step).
   - Keeping BSP in a 1-core kernel is marked `"Policy"` (`:197`), not enforced by the gate; if violated, or if any 1 core enters VMX root (`:1081`) or fails its ARM64 SDEI handler (`:195`), the **entire** `k`-core kernel ends `unfenced` (`:1091`), freezing all `k` cores' memory until reboot.

3. **Zero-core sealed kernel ("seals with none": `:24, 167, 258, 324`):**
   - **Reclaim barrier deadlock (`:1119`):** A sealed kernel `B` (`0` cores) that holds a mapping to dead kernel `A` (`maps_of[B]` bit `A` set) blocks `A`'s reclaim barrier until `B` resumes (`R2+R5`) or is killed—neither of which happens automatically because `B` wakes only `"when its supervisor needs it"` (`:167`).
     - *Test 3a (`test_sealed_reclaim_deadlock`):* Fails if `A` reaches `fenced` and no transition reaches `A = dead`. Failed in 6 states (1 step).
   - **`M4 Revoke` deadlock (`:294`):** `G` calling `cap_revoke` on a mapped frame grant held by sealed `B` waits forever (`again`) because `B` has `0` cores to drain its ring and send `RevokeStep`. (`verify-hydrogen` line 121 only bypasses `fencing/fenced/dead`, not `sealed`.)
     - *Test 3b (`test_sealed_revoke_deadlock`):* Fails if `grant_state` remains `"revoking"` with no quiescent state reachable. Failed in 6 states (2 steps).
   - **IOMMU rebuild drop (`roles.rs:446`, `:1214`):** `:167` forbids armed timers and claimed interrupts on a sealed kernel, not attached `iospace` devices/DMA mappings. On a unit role holder's death, `M8 ReportAsk` (`:298`) asks `"live kernels"`, and `roles::rebuild()` (`roles.rs:446`) skips `!writes(node)` (`Sealed`), silently clearing `S`'s DMA translations.
   - **No wake-up on `M1`/`M2`/`M3` (`:167, 291-293`):** Who wakes `S` when a client writes to a shared ring and sends `M1 Signal`, or sends `M2 Send` / `M3 Call1`? C* has zero-core kernels with no owner core executing their rings (`M1` is a ring message in C*, unlike a direct memory atomic OR from another core), stalling callers indefinitely.
   - **Over-admission on 1-core resume & impossible `retire` (`:167, 266, 324-325`):** `core_stop(seal)` evacuates all `k` cores at once without checking `budget` (`:128`); resuming `S` on `1` core via `core_start(resume)` (`:324`) loads `k` cores' worth of admitted bandwidth (`k × ADMISSION_WHOLE_CORE`) onto `1` core. In `retire` (`:325`), `"its last core leaves, its memory is given back with memory_give"` cannot run `memory_give` after the last core leaves, and cannot give away the kernel's floor (`:755`).

4. **Single lock inside a kernel vs `D-042` & slow E-core (`:32, 177, 263-265`, `decisions/README.md:52`, `kernel.md:44`):**
   - `D-042` requires every syscall to have a bounded, verified duration with resumption points (`kernel.md:44` explicitly rejected shared-kernel locks under `D-026` for this reason). A single queue lock (`:263`) adds `(k - 1) × W_max` waiting; if `K` spans P and E cores, an E-core holding the lock stalls P-cores (`heterogeneous-cores.md:157`). Furthermore, `:263` says the lock is `"held for one kernel event"` so `"every event of a node runs alone"` (`system.rs:5-7`), while `:133` (`aspace_unmap` waiting for `k-1` IPI acks) and `:265` (cross-core `thread_suspend` interrupting another core and waiting) either hold the global lock across cross-core IPIs (violating `D-042` bounds) or release it across resumption points (invalidating `system.rs:5-7` atomicity).

5. **Inter-kernel credit starvation & counters (`:285, 291-298`):**
   - `M2`, `M3 Call1`, `M4 Revoke`, `M6 UnitRequest`, and `M8 ReportAsk` all share the same per-peer credit `Q` (`:292-298`). Four tasks sending `M2` (`Q/4` each) exhaust `Q` and starve kernel `M6` (IOMMU invalidation) and `M4` (revocation).
     - *Test 6 (`test_credit_starvation`):* Fails if `4` tasks consume all `Q=4` credits via `M2` while kernel `M6/M4` needs a credit. Failed in 32 states (5 steps).
   - `W7`'s `consumed` counter (`:285`) resets when `Y` restarts fresh (`g+1`), with no rule reconciling `X`'s `sent_to[Y]` or preventing `Y@g+1` from counting stale ring drops against `X`'s new credits; `M1`'s sender-side pending table (`:291`) has no purge when `Y` dies.

6. **What `elastic_opus.py` does not model (`:415`, `elastic_opus.py:585-768`):**
   - Generations in core words (line 633 artificially blocks `start kernel k` until R6 clears every reference to `k`, masking ABA bugs);
   - Non-atomic hardware signals (`INIT`/`SDEI` in flight) and `core_beacon.parked` epochs vs `execs[c] is None` (hiding Tests 1 and 4);
   - `sealed` kernels holding `fown`/`amap`/grants with 0 cores (line 642 forbids retiring while `fown == k or amap == k`, hiding Tests 3a and 3b);
   - Unit roles, fence classes (1 vs 2), and `core_take` class checks (hiding Test 2);
   - `M1..M9` rings, `Q` credits, `W7` `consumed` counters (hiding Test 6);
   - Multi-core `G12` gate lock, seqlock slot reads, cross-core thread suspend/delete preemption points (`§4.4.1` of `5618.pdf`), IRQ retargeting (`unit_request`), and memory ordering (TSO/Armv8).

---

## 4. The Case Against Shapes A, B, C, and D1–D4 (with `kernel-shape-hydrogen.md`)

- **Wasm vs native multithreading (`wasm-abi.md:128`, `web.md:17-33`, `agent.md:11, 44`):** WASI 0.3 has **no** threads; Wasm apps scale via separate component instances (`wasm-abi.md:128`), and agent actions intentionally run in isolated fresh instances (`agent.md:44`). Only native code (Ladybird `web.md`, `llama.cpp` `agent.md:11`) needs shared-`aspace` threads—and Ladybird itself splits processes (`Hub`, `RequestServer`, `AudioServer`, one `WebContent` per site, `web.md:19-33`), which still cross kernels unless co-located in one failure domain.
- **Comparison against `Shape D` (`kernel-shape-hydrogen.md:10-22, 260-271`):**
  - *A repaired:* Correctly shown heavy (`30,720 > 4,096` grants for 4 GiB × 16 nodes, unwritten core-group protocol `:1877`, 18 `Body` variants, D-108 co-hosting bugs).
  - *B:* Sound base, but pushing `aspace` coherence to user agents adds double crossings and still hits `GRANTS = 4096`.
  - *D1–D4:* Opus's rejection of D1 (fixed clusters), D2 (cross-kernel shared table hazards: Arm A/D bits, BBM, ASIDs), and D3 (co-hosting) holds. Rejecting D4 (`:107`, a process never changes kernel) is coherent only while processes fit one static kind/size: a long-lived service trapped in a kernel grown to 16 cores (or wanting P↔E migration) must be killed and restarted.
  - *C* vs Hydrogen's `Shape D`:* `Shape D` keeps `1` core = `1` node = `1` failure unit, eliminates proxies/`Move`/`Carry`/D-108 parking, and solves `A`'s grant ceiling via `Run-Grant` (`60` entries vs `30,720`), notify revocation via `NotifyGenTable` (`Stateless Signal`), and map broadcasts via `Adds::Lazy` (`kernel-shape-hydrogen.md:14-16`). However, `Shape D` trades away intra-kernel shared page tables (`aspace_unmap` across `16` active peers still pays peer IPIs + `AspaceAck`) and introduces three unprototyped/unmodelled mechanisms (`Run-Grant`, `NotifyGenTable`, kernel minor-fault `Adds::Lazy`).
- **Failure unit, `D-042`, gate proofs, P/E, 2 vs 64 cores, owner's two wishes:**
  - *Failure unit:* C* expands crash blast radius from `1` core (`A/B/D`) to `k` cores (all co-located processes/drivers), and any 1 class-1/unmasked core makes all `k` cores `unfenced` (`:1091`).
  - *Gate proofs (`gate-page-tables.md:601-602`, `verification.md:59-74`):* Sequential Verus verification suffices on one core (`:601`). Adopting `G12` (`:264`) requires concurrent `VerusSync`-style reasoning over locks and flush epochs, which `gate-page-tables.md:602` states is **unfinished even in Asterinas**. Opus never weighs this proof discontinuity.
  - *P/E cores, 2 cores, 64 cores:* On `2` cores C* degenerates to `B` and **loses to A** (`:179`), whereas `Shape D` allows a 2-core shared process. On `64` cores C* must still shard into `8–16` kernels (`:183`), reintroducing cross-kernel IPC. On `6P+8E`, C* cannot span P and E without E-core lock delays (`heterogeneous-cores.md:157`).
  - *Owner's wishes (`ELASTIC.md:33-36`):* C* meets both wishes on paper for `4–8` homogeneous cores, at the cost of ms-scale core moves (`zellweger.pdf` Table 2), broken `D-042` bounds, concurrent gate proofs, and the §3.2 protocol defects.

---

## 5. Cost to Build and Verify vs Present Contract and `model` (`2afc901`)

Opus's diff table (`:348-380`) accurately maps most deleted protocols (`PROXIES_PER_PEER`, `TransferAsk..Returned`, `Move/Moved`, `Carry`, `core_place`, parked co-hosting), **but understates code and verification cost in four places:**
1. **`model` line count (`:372`):** `174` (`fn..}`) / `197` (with docs), not `211`.
2. **Omitted `abi/src/machine.rs` and `core_start` diff (`:370-379`):** `abi/src/machine.rs` must add `CORE_WORDS`, `parked`/consumed `W7` counters, `SIGNAL_PENDING`, `Q` credits, and `core_start` signature changes (`:357` notes the physical-core parameter, absent from `5.3`).
3. **Contract keep-errors (`:356-357`):** Keeping `:1119` (reclaim barrier) and `:1214` (`roles::rebuild` / `roles.rs:446`) unchanged breaks 0-core sealed kernels (Tests 3a, 3b).
4. **Net verification cost is higher, not lower (`:374, 393`):** Deleting `moves.rs` (`269` lines) + `174` lines of `remote.rs` removes sequential code, while adding concurrent `G12` gate locking (`VerusSync`), seqlock slot reads, non-atomic x86-64 shootdowns, cross-core thread suspend/delete (`5618.pdf §4.4.1`: 2 thread states, 8 preemption points, 1,000-LOC invariant proof), and breaking the single-threaded `seL4` differential oracle (`verification.md:57`).

---

## 6. What C* Missed, and Whether a Hybrid Beats Both

- **What C* missed:** (1) The 7 protocol breaks in §3.2 (`core_beacon.parked` lifecycle, ARM64 Trusted OS / `SDEI_PE_UNMASK` window, `leaving(J)` fence race, unit-role class-1 `core_take`, 0-core sealed deadlocks/wake/over-admission, `Q` credit starvation, and x86-64 `leaving` shootdown wait); (2) `Run-Grant` and `NotifyGenTable` (`kernel-shape-hydrogen.md:14-15`), which solve A's `4,096` grant ceiling and revoke bursts **without** multi-core locks; (3) the `VerusSync` barrier at `gate-page-tables.md:602`; (4) that WASI 0.3 has no threads (`wasm-abi.md:128`).
- **Hybrid evaluation:**
  - **Stage 1 per-core (`Shape D` / pruned `B`) → Stage 2 homogeneous `C*` if proven needed: YES, beats both.** Keep `1 core = 1 node` for Alpha using C*'s clean one-shot cross-kernel ring boundary (augmented with `Run-Grant` + `Stateless Signal` and minus D-108 co-hosting). This preserves sequential `P_gate` Verus proofs (`gate-page-tables.md:601`), `seL4` differential testing, `D-042` syscall bounds, `2`-core recovery, and P/E isolation. Only if bare-metal `i5-14600KF` benchmarks on Ladybird / `llama.cpp` prove peer `AspaceInvalidate` unacceptable, add fixed/elastic **homogeneous single-lock P-only islands** underneath the *same* cross-kernel `M1–M9` ABI (`C*` with §3.2 fixes).
  - **Elastic kernels with a lock-free core: NO.** Removing the big lock inside a multi-core kernel requires per-endpoint, per-range, and cross-tree revocation locking (`M5:971-980` left subtree `cap_revoke` unresolved) plus full concurrent `VerusSync` across every kernel structure—strictly harder to verify than either per-core or single-lock clusters.

---

## Judgement (Ten Lines)

1. Do **not** build C* as Stage 1 of DodOS: its gain (`shared aspace` for native 16-thread apps) is real only where WASI 0.3 does not yet go, while its cost breaks sequential `Verus` gate proofs (`gate-page-tables.md:602`) and `D-042` bounds immediately.
2. C*'s core-move and zero-core seal specs currently fail concrete checks: stale x86-64 `core_beacon.parked` violates P1/P2, `leaving` races with `J`'s fence, `core_take` can drop a unit-role holder to class 1, `sealed` deadlocks `:1119` and `M4 Revoke`, and shared `Q` credits let `M2` starve kernel control.
3. Build **per-core lock-free kernels first** (keeping C*'s elimination of Rule-7 proxies, `thread_move`, `Transfer`, and D-108 co-hosting, plus `Run-Grant` and `NotifyGenTable` from `Shape D`).
4. Before finalizing whether Stage 2 ever adds elastic P-core clusters, **measure on the `i5-14600KF`**: bare-metal P→P and P→E IPI latency, `INVLPG`/`INVPCID`, `WRSSQ` gate throughput, `core_give`/`core_take` park+NMI ms cost, `MWAIT` idle package power vs parked cores, and real `munmap`/`mprotect` rates in Ladybird and `llama.cpp`.
5. Also **model before any elastic code**: extend `elastic_opus.py` with core-word generations, non-atomic `parked` / in-flight fence signals, `sealed` barrier/`Revoke` states, unit-role class guards, separated `Q` credits, and cross-core thread deletion (`5618.pdf §4.4.1`).
6. Fix `:1052` (dedicated per-core voluntary park sequence cleared on `core_start`) and `:250-251` (forbid `leaving -> free/joining` while `J` is fencing/unfenced) before reusing the core-move state machine.
7. Fix `:167, 1119, 1214` (either disallow `0`-core sealing while holding grants/mappings/`iospace`s, or auto-wake/reclaim `sealed` on `M4`/`R2`/`M8`) before shipping zero-core sealing.
8. Gate `core_take` against unit roles (`Invariant 10`) and enforce `BSP` exclusion in the gate, not policy.
9. Separate kernel control credits (`M4`, `M6`, `M8`) from user `M2` credits (`Q`), and reconcile `W7` `consumed` counters on peer death.
10. Keep `C*` in reserve as an optional **homogeneous** Stage-2 tier whose cross-kernel ABI matches Stage 1, never as an unmeasured Stage-1 bet.
