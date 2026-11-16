# Contract Review 8 (Hydrogen): Cross-Node Messages, Rings, Multi-Core Failure, Sealing, and D-128 Points 4, 5, and 10

Target: [kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) (with cross-references to [kernel.md](/Users/btw/Documents/repos/Docs/architecture/kernel.md)) at commit `d0916a9` ("pass 14B").

Two executable state explorers in `/tmp/review8_hydrogen/` accompany this review:
- `/tmp/review8_hydrogen/explore_cross_node_rings.py` (Scenarios A–G)
- `/tmp/review8_hydrogen/explore_cores_failure_sealing.py` (Scenarios H–M)

---

## Summary of Findings

| # | Severity | Lines | Summary |
|---|---|---|---|
| 1 | `blocks for ever` | [:885](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L885), [:897](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L897), [:1317](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1317), [:1328-1329](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1328-L1329) | `UnitRequest` messages from an old epoch or during a `handing` transition are dropped silently with code 11 by `:897`, contradicting `:885`/`:1328` ("answered elsewhere") and hanging callers forever. |
| 2 | `blocks for ever` | [:874](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L874), [:909](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L909), [:1238](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1238), [:1293](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1293) | `node_start` mode `resume` drops live generation-`g` messages by setting `consumer = producer` (`:909`) and omits R3–R5 (`:1293`), leaving stale grants and `maps_of`/`acked` blockers forever. |
| 3 | `blocks for ever` | [:864](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L864), [:869-870](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L869-L870), [:872](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L872), [:884](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L884), [:897](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L897), [:1614](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1614) | A concurrent `Release` and `Revoke` deadlocks the revoking thread forever when `Release` frees `use_entry` before `Revoke` arrives; additionally, `grant_entry` omits `use_index`. |
| 4 | `wrong result` | [:134](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134), [:897](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L897), [:904-905](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L904-L905), [:907](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L907), [:922](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L922) | Destroying a thread in `waiting for another node` (`:134`) leaves `:897` dropping its late `SendAnswer`, permanently leaking undelivered grants and `SENDS_PER_PEER` credits (or overflowing the answer reserve). |
| 5 | `breaks isolation` | [:255](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L255), [:327](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L327), [:347](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L347), [:365](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L365), [:644-645](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L644-L645), [:878](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L878), [:882](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L882), [:885](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L885), [:888-889](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L888-L889), [:902](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L902), [:906](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L906), [:1249](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1249), [:1330](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1330), [:1366](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1366) | `:878`'s "one bounded step, no receiver state" claim breaks on `ReportAsk`/`Report` (single cursor overwrites concurrent rebuilds and omits `sealing` nodes, clearing live DMA), `Revoke` (cannot wait for multi-core TLB shootdown or remote IOMMU `UnitRequest`), and `UnitRequest` (`IOMMU_WAIT_NS` = 1 ms inside a 156 µs/10 ms reserve). |
| 6 | `blocks for ever` | [:897](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L897), [:899](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L899), [:909](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L909), [:980](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L980), [:1229](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1229) | Nothing resets a dead node `Y`'s outgoing rings `Y -> X` across `R6` or fresh reload, letting a corrupted `length = 0` or inflated `producer` persist across generations. |
| 7 | `blocks for ever` | [:1243](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1243), [:1317](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1317), [:1321](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1321), [:1327](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1327), [:1329](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1329), [:1338](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1338) | When planned `role_hand` target `Y` dies after step 4, `holder` stays live `X` (`:1317`), blocking take-over (`:1321`), blocking `role_hand` (`:1338`), and freezing the reclaim barrier (`:1243`) forever. |
| 8 | `breaks isolation` | [:1148-1161](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1148-L1161), [:1151](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1151), [:1154-1155](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1154-L1155), [:1257](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1257), [:1299-1301](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1299-L1301) | `:1301` writes `sealed` before raising `park_request` (letting `node_start(resume)` start a second kernel concurrently), `:1154` skips checking `panic == 0`, and a 2-node `sealing` machine deadlocks if the sole `live` peer fails. |
| 9 | `blocks for ever` | [:1120](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1120), [:1186](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1186), [:1199-1202](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1199-L1202) | x86-64 BSP park stub enters `hlt` directly from the NMI handler with no `IRET`, tripping the SDM §7.7.1 hardware NMI-blocking latch so restart NMIs never deliver, and ignores `park_request` when a `sealed` BSP is accused. |
| 10 | `blocks for ever` | [:1120](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1120), [:1205](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1205), [:1306](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1306); [kernel.md:149](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L149) | ARM64 SDEI lifecycle omits `SDEI_EVENT_ENABLE`, ignores TF-A wiping private events on `CPU_ON` and masking the PE on `CPU_SUSPEND` power-down wakeup, and calls `CPU_OFF` from an uncompleted SDEI handler context. |
| 11 | `wrong result` | [:483](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L483), [:557](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L557), [:564](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L564), [:651](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L651), [:1171](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1171), [:1181-1182](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1181-L1182) | `u64::MAX + STALE_NS` wraps around in `:1182` causing false `stale` accusations on idle cores, while slack execution (`:557`) and long budgets (`:483`) without a kernel-tick timer cap trigger false `stale` and self-accusations (`:651`). |
| 12 | `blocks for ever` | [:907](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L907), [:921-922](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L921-L922), [:939](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L939), [:1281](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1281), [:1308](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1308), [:1357](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1357), [:2091-2092](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L2091-L2092), [:2097](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L2097) | Attack on D-128 Points 4, 5, and 10: while the architectural shifts are D-128 prices, `:939` contradicts `:1281` ("must name the caller's node"), `NODE_WATCH_SLOTS = 4` (`:1357`) and `:1308` TOCTOU break peer monitoring, `SENDS_PER_PEER = 8` (`:907`) is node-wide and starvable, and `node_send` cannot distinguish a permanently dead mailbox agent. |

---

## Finding 1: Old-epoch and `handing`-epoch `UnitRequest` messages are dropped by `:897`

**Severity:** `blocks for ever`

**Quotes:**
- Line `:885`:
  > `| 4 | UnitRequest | kernel | any node → holder of a unit role | ... | The requester's thread waits; an old epoch is answered "elsewhere" and the requester sends again to the holder the role word names; at R0 it is kept for the next holder |`
- Line `:897`:
  > `The receiving kernel checks, in one function and before anything changes: ... a role message (UnitRequest, Handed, ReportAsk, Report) names the role's current epoch, and comes from the node the step requires (the role word's holder or target, a requester for a request, a live node for a report); ... A message that fails any of these changes nothing, is consumed, and is traced (code 11 of What the kernel traces).`
- Line `:1317`:
  > `for handing, the node that hands: it stays the holder the word names until the target writes held`
- Lines `:1328-1329`:
  > `A request carries the role's epoch; the holder refuses a request with another epoch (an answer between kernels that never reaches user space), and the requester reads the role word again and sends it to the holder it names.` (`:1328`)
  > `Planned hand-over of a unit role u from X to Y ... (1) X stops accepting new requests for u and finishes those it began; ... (4) it writes handing (X → Y, e + 1) ... (5) Y maps the unit ... and writes held (Y, e + 2).` (`:1329`)

**Scenario:**
1. Role `u` is `held(X, e1)`. Node `R` reads `e1` and queues `UnitRequest(u, e1)` in `R -> X` (`waiting for another node`).
2. Before `X` drains `R -> X`, `X` performs `role_hand(u, Y)` steps 1–4: it stops accepting requests and writes `handing(X -> Y, e2)` (so the current epoch is now `e2`, or `e3` once `Y` writes `held(Y, e3)`).
3. `X` receives `UnitRequest(u, e1)` in `:897`. Because `e1 != current_epoch` (`e2`/`e3`), `:897` rejects the message **"before anything changes"**, consumes it, emits trace code 11, and **sends no `UnitAnswer("elsewhere")`**.
4. `X` is still `live`, so `R` never runs `R0` (`:1215`) and `thread_cancel` does not end `waiting for another node` (`:194`). `R`'s thread is blocked forever. (Additionally, `:1329` step 1 says `X` stopped accepting requests before step 4, so if `R` sends `UnitRequest(e2)` while `handing(X -> Y, e2)` is in force—where `holder` is still `X` by `:1317`—`X` must still answer `"elsewhere"` rather than dropping it.)

**Mechanical Check (`explore_cross_node_rings.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cross_node_rings.py`
```
=== A1: UnitRequest epoch (contract): VIOLATION (9 states) ===
  Error: Requester R blocked forever in waiting_for_another_node: UnitRequest silently dropped by :897
  1. R reads held(X,e1) & sends UnitReq(e1) -> X -> ('held_X_e1', 'waiting_X_e1', (('UnitReq', 1),), (), (), ())
  2. X step 4: writes handing(X->Y, e2) -> ('handing_X_Y_e2', 'waiting_X_e1', (('UnitReq', 1),), (), (), ())
  3. X recv check (:897) drops UnitReq(e1) [cur=e2] with code 11, no answer -> ('handing_X_Y_e2', 'stuck_dropped', (), (), (), ())
=== A2: UnitRequest epoch (fixed): HOLDS (20 states) ===
=== A3: UnitRequest epoch (vacuity): VIOLATION (13 states) ===
  Error: Requester R blocked forever in waiting_for_another_node: UnitRequest silently dropped by :897
  1. X step 4: writes handing(X->Y, e2) -> ('handing_X_Y_e2', 'idle', (), (), (), ())
  2. R reads handing(X->Y,e2) & sends UnitReq(e2) -> X -> ('handing_X_Y_e2', 'waiting_X_e2', (('UnitReq', 2),), (), (), ())
  3. BROKEN: X drops UnitReq(e2) -> ('handing_X_Y_e2', 'stuck_dropped', (), (), (), ())
```
**Non-vacuity:** `A3` flips `fixed` so `X` drops epoch-`e2` requests during `handing(X -> Y, e2)`, causing `R` to hang in 3 steps; `A2` only holds when `:897` passes `UnitRequest` of any epoch through and `X` answers `"elsewhere"` whenever `role != held(X, req.epoch)`.

**Smallest Fix:**
In `:897`, change:
> `a role message (UnitRequest, Handed, ReportAsk, Report) names the role's current epoch, and comes from the node the step requires (the role word's holder or target, a requester for a request, a live node for a report)`
to:
> `a role message (Handed, ReportAsk, Report) names the role's current epoch and comes from the node the step requires (the role word's holder or target, a live node for a report); a UnitRequest names any epoch and comes from any node that is starting, live or sealing (a request whose epoch does not match, or that arrives while the role is handing or not held by this node, is answered "elsewhere" by the rule of Roles, never dropped silently).`

---

## Finding 2: `node_start` mode `resume` drops valid queued messages (`:909`) and omits R3–R5 (`:874`, `:1293`)

**Severity:** `blocks for ever`

**Quotes:**
- Line `:909`:
  > `When Y starts again (a fresh start with generation g + 1, or a resume with g), before it runs any thread, it sets the consumer index of every ring into it to that ring's producer index, so it consumes nothing sent before; the receiver generation that every message carries stops any written later to an earlier generation. A sealed node sends and consumes nothing: messages to it wait in its rings until it resumes or is accused`
- Line `:874`:
  > `when it resumes (node_start mode resume), before it runs any thread, it runs R0 and R2 for every node whose generation ended while it was sealed`
- Line `:1293`:
  > `Effect, mode 1: the member word becomes starting (g); the node's cores are started from their park; the core at position 0 loads the sealed block, checks that the block's format version is one the kernel image reads, runs R0 and R2 for every node whose generation ended while it was sealed and serves its pending revocations, and the node becomes live with the same generation, its objects as they were.`
- Line `:1238`:
  > `| sealed | maps_of bit X clear (a sealed node that maps X's memory delays X until it is resumed, and acknowledges before it runs any thread, or killed) |`

**Scenarios:**
1. **Ring drop (`:909` self-contradiction):** Node `X` sends `node_send` (or `UnitRequest` / `Revoke`) to live `Y`, then `X` enters `sealing`/`sealed` (`g`). While `X` is sealed, `Y` writes `SendAnswer` (or `UnitAnswer`, `RevokeStep`, `Revoke`, `Release`) into `Y -> X` with `receiver_gen = g`. `:909` states `"messages to it wait in its rings until it resumes"`, yet the immediately preceding sentence forces `node_start(resume)` (`g`) to set `consumer = producer`, discarding that `SendAnswer` / `UnitAnswer` / `RevokeStep` / `Release`. `X`'s waiting thread (or `X`'s grant entry) stays blocked forever.
2. **Missing R3 (`:874`, `:1293`):** While `X` is `sealed`, grantee `Y(1)` dies, is reclaimed, and restarts as `Y(2)`. `X` resumes at `g` and runs **only R0 and R2** (`:874`, `:1293`), leaving `X`'s grant entry to `Y(1)` in state `live` (never running **R3** to pin/free it). Later `X` runs `cap_revoke`: `:870` reads `Y(1)`'s stale count (if > 0) or sends `Revoke` to slot `Y` (`Y(2)`), which `:897` drops with code 11. `X` hangs forever in `waiting for another node`.
3. **Missing R4–R5 (`:1238` vs `:1293`):** While `X` (`maps_of[Z] = 1`) is `sealed`, `Z(1)` is accused and enters `fenced`. `Z` waits at `:1238` (`"acknowledges before it runs any thread"`). When `X` resumes, `:1293` runs R0 and R2 (clearing remote caps/mappings to `Z(1)`), **but omits R4 (audit) and R5 (clearing `maps_of[Z]` and writing `acked[Z] = 1`)**, leaving `Z` stuck in `fenced` forever even after `X` resumes `live`.

**Mechanical Check (`explore_cross_node_rings.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cross_node_rings.py`
```
=== B1: Resume consumer=producer (contract): VIOLATION (6 states) ===
  Error: Resumed node X discarded its queued SendAnswer via :909 consumer=producer; waiter hung forever
  1. Y puts SendAnswer in Y->X before X seals -> ('live1', 'live1', ('SendAnswer',), 'waiting_send_ans')
  2. X seals (same generation 1) -> ('sealed1', 'live1', ('SendAnswer',), 'waiting_send_ans')
  3. X resumes (mode 1): :909 sets consumer=producer, dropping queued SendAnswer -> ('live1', 'live1', (), 'stuck_discarded')
=== B2: Resume consumer=producer (fixed): HOLDS (5 states) ===
=== B3: Resume consumer=producer (vacuity): VIOLATION (6 states) ===
...
=== B4: Resume missing R3/R4/R5 (contract): VIOLATION (9 states) ===
  Error: Resumed X missed R3 (:1293/:874), kept stale grant to Y(1), sent Revoke to Y(2), blocked forever
  1. X seals (holding grant to Y(1) and mapping to Z(1)) -> ('sealed1', 'live1', 'live1', 'live_g1', 1, 0, False)
  2. Y(1) dies -> fenced -> dead -> restarts as Y(2) while X is sealed -> ('sealed1', 'live2', 'live1', 'live_g1', 1, 0, False)
  3. X resumes (:1293 runs R0+R2 only, omits R3/R4/R5) -> ('live1', 'live2', 'live1', 'live_g1', 1, 0, False)
  4. X revokes grant -> sends Revoke to Y(2), Y(2) drops via :897 -> X stuck -> ('live1', 'live2', 'live1', 'stuck_revoking', 1, 0, False)
=== B5: Resume missing R3/R4/R5 (fixed): HOLDS (18 states) ===
=== B6: Resume missing R3/R4/R5 (vacuity): VIOLATION (9 states) ===
```
**Non-vacuity:** `B3` drops the queued ring on resume while keeping R3–R5; `B6` keeps rings on resume while omitting R3. Only preserving valid generation-`g` messages **and** running R0, R2, R3, R4, and R5 (`B2`, `B5`) satisfies all invariants.

**Smallest Fix:**
1. In `:909`, replace `"When Y starts again (a fresh start with generation g + 1, or a resume with g), before it runs any thread, it sets the consumer index of every ring into it to that ring's producer index, so it consumes nothing sent before"` with:
   > `When Y starts fresh with generation g + 1, before it runs any thread, it sets the consumer index of every ring into it to that ring's producer index, so it consumes nothing sent before; at a resume with generation g it keeps its consumer indexes and drains the messages waiting in its rings under the receive check (messages from dead generations are refused by the check).`
2. In `:874` and `:1293`, change `"runs R0 and R2 for every node whose generation ended while it was sealed"` to:
   > `runs R0 for every node whose generation ended while it was sealed, and R2 to R5 for every node that became fenced, unfenced or dead while it was sealed (and R3 freeing for grants whose grantee's generation is already dead or superseded)`

---

## Finding 3: `Release` crossing `Revoke` deadlocks the revoking thread, and `grant_entry` omits `use_index`

**Severity:** `blocks for ever` (`use_index` omission: `unspecified`)

**Quotes:**
- Line `:864`:
  > `The grant table of a node has GRANTS entries (4,096, provisional) ... An entry is 128 bytes: the anchor ...; then the grantee node (16 bits), the grantee's generation (32 bits), a serial (30 bits ...) and a state (2 bits: free, live, revoking, pinned ...); the doorbell ... and the links of that notify's list of doorbells (two grant indexes). The use table of a node has GRANTS entries of 32 bytes: the granting node, the grant index, the serial, the granting node's generation, the address of the root remote capability on this node, the number of leaves of this node's tables under the grant (G6), and two flags, release pending and signal pending`
- Lines `:869-870`:
  > `when X revokes, it first writes revoking, then reads that count.` (`:869`)
  > `if the count of Y's use entry is then 0, the entry is freed at once (its serial grows); otherwise X sends Y a Revoke naming the grant and its serial, and the calling thread waits in waiting for another node.` (`:870`)
- Line `:872`:
  > `When Y removes the root remote capability of a grant (by any removal), it sends X a Release that names the grant and its serial, and frees its use entry once the message is in the ring ... X acts on the message only if the entry has that serial and names Y, with the generation Y sent it from, as its grantee ...; it then frees the entry if its anchor has no descendant in X's list; otherwise the anchor stays, held by nobody`
- Line `:897`:
  > `a message that names a grant (Revoke, RevokeStep, Release, Signal) matches the entry it names, which is ... the use entry naming the sender as granting node with that generation and serial (on the holder) ... A message that fails any of these changes nothing, is consumed, and is traced (code 11)`

**Scenarios:**
1. **Crossing deadlock:** `Y` holds a mapped frame under grant `(G, s)`.
   - Step 1: On `X`, `cap_revoke` reaches `G`'s anchor, writes `state = revoking`, reads `Y`'s use-entry count (`> 0`), puts `Revoke(G, s)` into `X -> Y`, and puts the caller in `waiting for another node` (`RevokeStep`).
   - Step 2: Concurrently on `Y`, `cap_delete` removes `Y`'s root remote capability, unmaps it, puts `Release(G, s)` into `Y -> X`, and **frees `Y`'s use entry** (`:872`).
   - Step 3: `Y` drains `X -> Y` and reads `Revoke(G, s)`. Because `Y` already freed the use entry in step 2, `:897` rejects `Revoke` with code 11 and sends **no `RevokeStep`**.
   - Step 4: `X` drains `Y -> X` and processes `Release(G, s)` per `:872`/`:884`. Because `G` has `state == revoking` and matches `(Y, s)`, `X` frees `G`, **but `:872`/`:884` never wakes the thread waiting for `RevokeStep`**. The revoking thread stays blocked in `waiting for another node` forever (`thread_cancel` cannot wake it, `:194`).
2. **Missing `use_index` in `grant_entry` (`unspecified`):** `:869-870` requires `X`'s gate/kernel to read the leaf count of `Y`'s use entry in `O(1)` time after writing `revoking`, yet `:864` and `:1614` (`"the grantee's slot address leaves the grant entry"`) removed the pointer to `Y`'s use table: `grant_entry` stores `grantee node`, `grantee generation`, `serial`, `state`, `anchor`, `doorbell`, and links—**no `use_index`**. Without `use_index` (12 bits, or `use_entry` indexed or carried in `grant_entry`), `X` cannot locate `Y`'s use entry without a 4,096-entry scan (`GRANTS`) inside a kernel call.

**Mechanical Check (`explore_cross_node_rings.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cross_node_rings.py`
```
=== C1: Release/Revoke crossing (contract): VIOLATION (9 states) ===
  Error: Revoke/Release crossing deadlocked X's revoking thread forever (grant freed, waiter never woken)
  1. X starts cap_revoke -> sets grant revoking, reads count=1, sends Revoke -> waits -> ('revoking_wait', 'used_mapped', ('Revoke',), ())
  2. Y deletes root remote cap -> sends Release, frees use_entry (:872) -> ('revoking_wait', 'freed', ('Revoke',), ('Release',))
  3. Y receives Revoke after freeing use_entry -> :897 drops Revoke (code 11), NO RevokeStep -> ('revoking_wait', 'freed', (), ('Release',))
  4. X receives Release while waiting for RevokeStep -> :872 frees grant, NEVER wakes waiter! -> ('stuck_wait', 'freed', (), ())
=== C2: Release/Revoke crossing (fixed): HOLDS (8 states) ===
=== C3: Release/Revoke crossing (vacuity): VIOLATION (9 states) ===
```
**Non-vacuity:** `C3` keeps the same interleaving without waking the `RevokeStep` waiter on `Release`, triggering the exact same deadlock.

**Smallest Fix:**
1. In `:872` and `:884`: add:
   > `If the grant entry is in state revoking with a thread waiting for RevokeStep on it, Release also wakes that waiting thread with again (or success if this step completed the removal) when it frees the entry.`
   (Also decrement `X`'s `REQUESTS_PER_PEER` in-flight count for the cancelled `Revoke`.)
2. In `:864` and `:1614`: record the 16-bit (12 bits used) `use_index` on `Y` inside `grant_entry` (sent back to `X` in `SendAnswer(delivered)` before `X` can ever revoke it, or allocated by `X`? Wait: `Y` chooses its `use_entry` at `Send` delivery, so `SendAnswer(delivered)` carries the `use_index` and `X` writes it into `grant_entry` under `SendAnswer`—or `use_entry` carries `use_index` in `Release`/`RevokeStep`? Even simpler: while `use_index` is unknown before `SendAnswer`, `Send` is still in flight; once `SendAnswer(delivered)` arrives, `X` writes `use_index` into the grant entry, and `X` treats an unconfirmed `Send` grant as revocable only after `SendAnswer`).

---

## Finding 4: Destroyed waiter in `waiting for another node` vs `:897` leaks grants and `SENDS_PER_PEER` credits

**Severity:** `wrong result` (leaks grant entries and `SENDS_PER_PEER` slots permanently; breaks `:905` reserve bound if worked around naively)

**Quotes:**
- Line `:134`:
  > `a wait for an answer of another node ends, and the answer, when it comes, finds no thread and is dropped`
- Line `:922`:
  > `At the answer, the sender frees the grant entries that were not delivered. ... A thread destroyed while it waits drops the answer, and the grants end as the answer says.`
- Line `:897`:
  > `an answer (RevokeStep, UnitAnswer, SendAnswer) answers a request this node sent to that sender and still waits for ... A message that fails any of these changes nothing, is consumed, and is traced (code 11 of What the kernel traces).`
- Lines `:905`, `:907`:
  > `Answers (RevokeStep, UnitAnswer, SendAnswer) always have room: the kernel ring Y → X keeps REQUESTS_PER_PEER + SENDS_PER_PEER entries for the answers to X, which X bounds by its own limits.` (`:905`)
  > `Send: a node has at most SENDS_PER_PEER (8) sends in flight to each peer` (`:907`)

**Scenario:**
1. A thread on `X` calls `node_send` to `Y` with 1–4 frame grants. `X` writes the grant entries (`live`), increments its `SENDS_PER_PEER` in-flight count (`1`), writes `Send` into `X -> Y`, and waits.
2. Before `SendAnswer` arrives, the thread is destroyed (`:134`).
3. Two incompatible behaviours exist under the current wording:
   - **If `X` follows `:897` strictly** ("still waits for" = waiting thread exists): `SendAnswer` arrives (even `would_wait`), finds no waiting thread (`:134`), is **dropped unchanged with code 11** (`:897`), and never runs `:922` ("and the grants end as the answer says"). Those `live` grant entries, their frames/anchors, and the `SENDS_PER_PEER` in-flight slot are **permanently leaked** until `Y` dies (or forever if `SENDS_PER_PEER = 8` fills up, wedging all `node_send` to `Y` on node `X`).
   - **If `X` tries to free the `SENDS_PER_PEER` credit when the thread is destroyed** so other threads aren't blocked: `X` can now issue a new `node_send` while `Y` still holds the previous undelivered `Send` / `SendAnswer`, exceeding `REQUESTS_PER_PEER + SENDS_PER_PEER` (24) reserved answer slots in `Y -> X` (`:905`).

**Mechanical Check (`explore_cross_node_rings.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cross_node_rings.py`
```
=== D1: Destroyed waiter strict :897 (contract): VIOLATION (6 states) ===
  Error: Undelivered grant entry and SENDS_PER_PEER credit permanently leaked (:897 vs :922)
  1. X calls node_send(1 frame) -> grant created, Send queued -> ('waiting', 1, 'live', 0, 1, 0)
  2. Thread destroyed while waiting (:134) -> no waiter on X -> ('destroyed', 1, 'live', 0, 1, 0)
  3. Y processes Send (no mailbox receiver) -> puts SendAnswer(would_wait) in Y->X -> ('destroyed', 1, 'live', 1, 0, 1)
  4. X drops SendAnswer via :897 (waiter gone) -> grant leaked & credit leaked! -> ('destroyed', 1, 'leaked', 0, 0, 0)
=== D2: Destroyed waiter free early (contract): VIOLATION (10 states) ===
  Error: Undelivered grant entry and SENDS_PER_PEER credit permanently leaked (:897 vs :922)
...
=== D3: Destroyed waiter (fixed): HOLDS (5 states) ===
=== D4: Destroyed waiter (vacuity): VIOLATION (6 states) ===
```
**Non-vacuity:** `D4` keeps the in-flight slot across thread destruction but drops `SendAnswer` via `:897`, immediately leaking both grant and credit. `D3` holds only when the node's own in-flight `Send` table (size `SENDS_PER_PEER`) tracks the pending send independently of the thread, keeps the credit until `SendAnswer` arrives, and `:897` accepts `SendAnswer` for an in-flight `Send` of the node even if its originating thread is gone.

**Smallest Fix:**
In `:897`, replace `"answers a request this node sent to that sender and still waits for"` with:
> `answers an in-flight request or send this node sent to that sender and has not yet resolved (even if the calling thread was since destroyed, in which case SendAnswer still completes the grant cleanup and frees the node's in-flight send slot before discarding the thread wake-up)`
And in `:134`, replace `"a wait for an answer of another node ends, and the answer, when it comes, finds no thread and is dropped"` with:
> `a wait for an answer of another node ends, leaving the node's in-flight slot active until the answer comes to clean up any undelivered grants and free the slot, without waking a thread`

---

## Finding 5: The claim "only one-shot operations cross; one bounded step, nothing kept on behalf of the sender" (`:878`) fails on `ReportAsk`/`Report`, `Revoke`, and `UnitRequest`

**Severity:** `breaks isolation` (also `blocks for ever` and `unbounded kernel operation`)

**Quotes:**
- Line `:878`:
  > `only one-shot operations cross between nodes; the receiving kernel finishes each in one bounded step and keeps nothing on behalf of the sender.`
- Lines `:888`, `:906`, `:1330`, `:1366`:
  > `| 7 | ReportAsk | kernel | new holder of a unit role → each live node | Starts its reports on the unit: as many Report messages as it has items, sent as its ring has room (a cursor in its node block) |` (`:888`)
  > `the reports of a rebuild as a cursor in the node block` (`:906`)
  > `asks every live node for its report on the unit (ReportAsk ...), keeps the context entries that match ... keeps without a report the entries whose root table lies in memory the ownership table gives to a sealed node or in its floor ... and clears every other entry no live node claims` (`:1330`)
  > `its cursor of reports for a rebuild` (`:1366`, singular in node block)
- Lines `:882`, `:327`, `:347`, `:365`:
  > `| 1 | Revoke | kernel | granting node → holder | Removes at most 32 units of its root remote capability of the grant, undoing mappings with its own cores' invalidations; answers RevokeStep |` (`:882`)
  > `x86-64 and RISC-V: an interrupt of the kernel's own to each other core of the set ... the caller waits in the state waiting for its node's cores, holding no lock` (`:327`)
  > `If the iospace serves devices, the unit's translation cache is invalidated before the call returns, by the holder of the unit's role: a call made on another node waits for it` (`:347`)
- Lines `:885`, `:902`, `:910`, `:1249`, `:1356`:
  > `The kernel ring is served in the receiver's recovery reserve (The recovery reserve), since a unit request may wait for its unit (at most IOMMU_WAIT_NS). ... under full load a message of the kernel ring waits at most one period of the recovery reserve (10 ms) before it is served, an answer included` (`:902`)
  > `recovery reserve: bandwidth 1/64 of a core ... period 10 ms ... 156 µs of each 10 ms` (`:1249`, `:1356`)

**Five concrete defects across the 12 kinds:**
1. **`ReportAsk`/`Report` — multi-message state overwritten by a singular cursor (`breaks isolation`):** Node `X` stores a **single** rebuild cursor (`:888`, `:906`, `:1366`). If two unit holders die around the same time (`S0` takes over unit `u0`, `S1` takes over unit `u1`), `ReportAsk(u1)` overwrites `X`'s cursor for `u0`, dropping `X`'s `Report(u0)` to `S0`. Without `X`'s report, `S0` clears `X`'s **live** IOMMU context entry (`:1330`), detaching an active DMA device or freeing/re-assigning its domain number while `X`'s DMA is running!
2. **`ReportAsk`/`Report` — `sealing` node skipped and cleared (`breaks isolation`):** `:888` sends `ReportAsk` only to **`live`** nodes; `:1330` preserves without report only entries whose root table belongs to a **`sealed`** node (and its floor). A node `X` in state **`sealing`** (`:1301`: still finishing requests and not yet `sealed`) receives no `ReportAsk` (or its `Report` is dropped by `:897`? Actually `:897` checks `"a live node for a report"`—so even if `X` sent `Report`, `:897` drops reports from `sealing`/`starting` nodes!), AND `:1330` does not exempt `sealing` nodes from clearing. So `S0` clears `X`'s live DMA context entries while `X` is `sealing` and still actively running DMA!
3. **`ReportAsk`/`Report` — no end-of-report sentinel (`blocks for ever` / `unspecified`):** Nothing defines a `ReportDone` message or item count. A node with 0 items on unit `u` sends nothing, so `S0` cannot distinguish "node `X` has 0 items" from "`ReportAsk` / `Report` is still delayed across a full ring (`:906`)" or "`X` hasn't drained its cursor yet". And if `S0 -> X` ring is full beyond its 24-entry answer reserve (`:905`), `:906` forgets to add a per-peer pending-`ReportAsk` flag on `S0`, unlike `release pending` / `signal pending`.
4. **`Revoke` — cannot be one bounded step when undoing multi-core CPU or remote IOMMU mappings (`breaks isolation` / contradicts `:878` & `:644`):** Removing a root remote capability (`:255`, `:882`) undoes its `aspace` and `iospace` mappings (`:327`, `:347`). On x86-64/RISC-V multi-core nodes, `aspace_unmap` sends TLB shootdown IPIs and waits asynchronously in `waiting for its node's cores` (`:327`, `:644`, up to `CORE_ANSWER_NS` = 10 ms), explicitly **"holding no lock"** (`:644`, incompatible with running a kernel-ring handler inside L1's node lock or waiting in one step). On any architecture, `iospace_unmap` waits for a remote `UnitRequest` to the unit role holder `U` (`:347`, `:365`). Therefore `Revoke` **cannot** synchronously wait for shootdown / `UnitRequest` inside `:878`'s single kernel-ring step without either:
   - keeping multi-step async unmap state (`unmapping` / `revoking`) on `Y` on behalf of `X` and returning `RevokeStep(again)` after kicking off the shootdown/`UnitRequest` (`G3`), or
   - answering `RevokeStep(done)` *before* TLBs/IOMMU caches are flushed, letting `X` free the grant and retype the frame to an untyped while `Y`'s cores or devices still hold active writable translations to it (`breaks isolation`, `G1`).
5. **`UnitRequest` — `IOMMU_WAIT_NS` = 1 ms inside a `156 µs / 10 ms` recovery reserve (`unbounded` / violates `:902` & `:645`):** A single `UnitRequest` may spin up to `IOMMU_WAIT_NS` = **1 ms** (`:902`, `:365`, `:1566`), which is **6.4× the entire 10 ms recovery reserve budget** (`156 µs`, `:1356`), breaking the reserve's 10 ms admission guarantee (`:1249`) and stalling other kernel-ring messages (`RevokeStep`, `SendAnswer`, `Release`) behind it for over 10 ms (`:902`'s bound of "at most one period ... 10 ms" under full load fails with even one slow unit wait, let alone 16 in-flight requests).

**Mechanical Check (`explore_cross_node_rings.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cross_node_rings.py`
```
=== E1: Rebuild concurrent cursors (contract): VIOLATION (9 states) ===
  Error: Live/sealing node X had its active IOMMU context entry cleared during rebuild (breaks DMA isolation/correctness)
  1. S1 sends ReportAsk(u1) -> X overwrites single cursor with (u1, 1)! -> ('asked', 'asked', ('u1', 1), 'live_mapped', 0, False)
  2. X sends Report(u1) to S1 (u0 report dropped!) -> ('asked', 'done', None, 'live_mapped', 0, False)
  3. S0 finishes rebuild of u0 without X report -> CLEARS X live IOMMU entry! -> ('corrupted_dma', 'done', None, 'cleared_while_live', 0, False)
=== E2: Rebuild sealing node (contract): VIOLATION (3 states) ===
  Error: Live/sealing node X had its active IOMMU context entry cleared during rebuild (breaks DMA isolation/correctness)
  1. X enters sealing while live S0 rebuilds u0 -> skipped by ReportAsk (:888) and not preserved as sealed (:1330) -> S0 clears! -> ('corrupted_dma', 'idle', None, 'cleared_while_live', 0, False)
=== E3: Rebuild concurrent cursors (fixed): HOLDS (4 states) ===
=== E4: Rebuild concurrent cursors (vacuity): VIOLATION (9 states) ===
...
=== G1: Revoke early done (contract): VIOLATION (5 states) ===
  Error: Frame freed & retyped by X while Y cores/IOMMU still hold translations (breaks isolation)
  1. X starts cap_revoke -> sets revoking, sends Revoke -> Y -> ('revoking', 'mapped', False, ('Revoke',), ())
  2. Y clears PTEs, sends RevokeStep(done) BEFORE shootdown/IOMMU inv completes! -> ('revoking', 'unmapping', False, (), ('RevokeStep_done',))
  3. X receives RevokeStep(done) -> frees grant & retypes frame to untyped! -> ('retyped', 'unmapping', False, (), ())
=== G2: Revoke block in step (contract): VIOLATION (3 states) ===
  Error: Revoke handler blocked/kept state inside one-shot step (contradicts :878)
...
=== G3: Revoke async/again (fixed): HOLDS (8 states) ===
=== G4: Revoke async/again (vacuity): VIOLATION (10 states) ===
  Error: Frame freed & retyped by X while Y cores/IOMMU still hold translations (breaks isolation)
```
**Non-vacuity:** `E4` overwrites the single cursor on a second `ReportAsk`; `G4` sends `RevokeStep(done)` before async shootdown/IOMMU invalidation completes. Both fail isolation immediately.

**Smallest Fix:**
1. For rebuild (`:888`, `:897`, `:906`, `:1330`, `:1366`): store a per-unit report bitmap/cursor (indexed by IOMMU/unit count, fixed at start) and a per-unit pending-`ReportAsk` flag; include **`sealing` (and `starting`)** nodes alongside `live` nodes in `ReportAsk`, `:897`'s report acceptance, and `:1330`'s preservation rule; and add a `ReportDone` (or an explicit `end` flag on the last `Report` / 0-item `Report`).
2. For `Revoke` (`:878`, `:882`, `:902`): amend `:878` to reflect reality—`Revoke` on `Y` records async `unmapping`/IOMMU-invalidation progress in `Y`'s `use_entry` (already fixed per node) and answers `RevokeStep(again)` while cores' TLB shootdowns or `UnitRequest` IOMMU invalidations are still in flight, returning `RevokeStep(done)` only after every translation under the grant has finished invalidating.
3. For `UnitRequest` (`:902`, `:1249`, `:1356`): state that IOMMU polling does not spin blocking the recovery reserve for up to 1 ms—instead the unit request polls once per reserve slice (or signals/re-arms a 100 µs timer), keeping each kernel-ring handler step strictly within the 156 µs budget.

---

## Finding 6: Outgoing ring `Y -> X` producer/entries are unreset across `Y` crash and reload

**Severity:** `blocks for ever` (`wrong result`)

**Quotes:**
- Line `:899`:
  > `The producer index is in the ring's header, written by X only; the consumer index of each ring into Y is in Y's node beacon, written by Y only; both are 64-bit counts that never go back. A ring X → Y is mapped writable only in X's kernel and read-only in Y's (the guarantee of The gate over page tables); its writes are plain stores, not gate calls, since the receiver checks every message.`
- Lines `:909`, `:980`:
  > `When Y starts again (a fresh start with generation g + 1, or a resume with g), before it runs any thread, it sets the consumer index of every ring into it to that ring's producer index` (`:909`)
  > `It sets the consumer index of every ring into it to the ring's producer index` (`:980`)
- Line `:1229`:
  > `R6. Clear. What X's gate wrote in the living part is cleared by the node that reclaims X's memory ... every entry of X's grant table ... every entry of X's use table ... and every core word`

**Scenario:**
`Y(1)` writes its outgoing rings `Y -> X` with **plain stores** (`:899`, not gate-checked). If a buggy `Y(1)` kernel fails after writing a message header with `length = 0` (or `length > 11`) at `producer = 5` and advancing `producer = 6`, or writes `producer = X.consumer + 500`, `Y(1)` dies and `R6` clears `Y(1)`'s living-part entries—**but `R6` never touches `Y`'s outgoing rings `Y -> X`** (`:1229`, and cannot write them if `Y -> X` is mapped writable only to `Y`), and `:909`/`:980` only reset `Y`'s **incoming** rings (`consumer = producer`).
When `Y(2)` boots fresh (`node_start` mode `fresh`):
- If `Y(2)` keeps the existing `producer` header in `Y -> X`, `Y(2)` inherits `Y(1)`'s poisoned `producer` (permanently filling/breaking `Y -> X` if `producer > X.consumer + 64`, or leaving a `length = 0` entry at `X.consumer` if `X` wasn't running yet).
- If `Y(2)` zeroes `producer = 0` while `X.consumer == 5`, `producer < consumer`, breaking `"both are 64-bit counts that never go back"` and `X`'s in-flight / unread ring calculation (`producer - consumer` underflows `u64`).

**Mechanical Check (`explore_cross_node_rings.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cross_node_rings.py`
```
=== F1: Outgoing ring reload (contract): VIOLATION (4 states) ===
  Error: Y(2) inherited corrupt len=0 entry at X.consumer (infinite consume loop on X)
  1. Buggy Y(1) writes bad header (len=0) and advances prod to 6 -> ('Y_dying_1', 6, 5, True)
  2. Y(1) dead -> Y(2) fresh start keeping old ring header (prod/bad preserved) -> ('Y_live_2', 6, 5, True)
=== F2: Outgoing ring reload (fixed): HOLDS (4 states) ===
=== F3: Outgoing ring reload (vacuity): VIOLATION (4 states) ===
  Error: Y(2) outgoing ring Y->X has prod=0 < X.consumer=5 (unsigned wrap / lost messages)
```
**Non-vacuity:** `F3` resets `producer = 0` while `X.consumer = 5`, triggering `prod < cons`. Only aligning `Y -> X`'s `producer` to `X`'s `consumer` (or having `X` ignore invalid lengths by advancing 1 entry and `Y(2)` syncing `producer = max(prod, X.consumer)` during start-up before writing) prevents both failure modes.

**Smallest Fix:**
In `:897` (consumption rule), state explicitly that a message with an invalid length (`0` or `> 11`, or spanning past `producer`) advances `consumer` by `1` entry (or to `producer`), never by `length` (`0`); and in `:909` / `:980`, add:
> `For each outgoing ring Y → X, Y at a fresh start sets its producer index to the greater of the header's current value and X's consumer index[Y → X], and waits to write to X until X's R0 for Y's old generation has drained X's consumer up to that producer.`
(Or place the outgoing rings of `Y` in `Y`'s clearable area or let `X` advance `consumer[Y -> X]` to `producer[Y -> X]` in `R0` before `Y` starts, with `Y(2)` reading `max(header.producer, X.consumer[Y -> X])`—note `X` only needs `X.consumer = producer` in `R0` once `Y` is `fenced`/`dead` so `Y` can no longer advance `producer`!).

---

## Finding 7: Planned `role_hand` of a unit role deadlocks permanently if target `Y` dies after step 4

**Severity:** `blocks for ever`

**Quotes:**
- Line `:1317`:
  > `bits 2-17 the holder (for handing, the node that hands: it stays the holder the word names until the target writes held, so wherever a rule speaks of the holder of a role, a handing word names the node that hands, and a seal of that node waits until the target has taken the role); bits 18-33 the target (handing only, otherwise 0xFFFF)`
- Table `:1321`:
  > `| unit | The kernel: planned by role_hand, after a death by the successor automatically | The holder is fenced or dead, and SETTLE_NS has passed since the stop was confirmed; or the holder is unfenced and FENCE_NS + SETTLE_NS have passed since the first fence action |`
- Line `:1329`:
  > `(4) it writes handing (X → Y, e + 1), its last act on u, and sends Y a message ... (5) Y maps the unit through its gate ... and writes held (Y, e + 2). If X dies before step 4, the take-over applies; after step 4, Y completes step 5; if Y dies after step 4, the successor of Y takes over with a rebuild.`
- Line `:1338`:
  > `role_hand | ... State, in order: busy if the role is not held by the caller's node`
- Line `:1243`:
  > `That is known from the role table and the beacons: every unit role is held, not handing, by a node that is live or sealing, and that holder has acked[X] = g.`

**Scenario:**
1. Live node `X` starts `role_hand(u, Y)` (or seals). Step 4 writes `handing(X -> Y, e2)`. By `:1317`, `holder` in the role word is `X`, and `X` has already unmapped `u` in step 3 (`:1329`).
2. `Y` dies before completing step 5 and reaches `fenced` + `SETTLE_NS`.
3. `:1329` claims `"if Y dies after step 4, the successor of Y takes over with a rebuild"`, **but table `:1321` only allows take-over without the holder when `"The holder is fenced or dead ... or the holder is unfenced"`**. Here the holder (`X`) is **`live`** (or `sealing`), so the gate refuses every take-over!
4. Nor can `X` recover the role by calling `role_hand` again (`:1338` requires the role to be `held`, returning `busy` while `handing`), nor can `X` seal (`:1154` says no unit role may name `X` as holder), nor can **any other dead node `Z` in the machine finish its reclaim barrier** (`:1243` requires every unit role to be **`held, not handing`**). The entire unit and machine reclaim freeze permanently.

**Mechanical Check (`explore_cores_failure_sealing.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cores_failure_sealing.py`
```
=== H1: role_hand target dies (contract): VIOLATION (5 states) ===
  Error: Unit role wedged in handing(X->Y) forever and Z's reclaim barrier (:1243) deadlocked
  1. X calls role_hand(u, Y) -> step 4 writes handing(X->Y, e2) [holder=X] -> ('handing_X_Y_e2', 'live', 'fenced', 'running')
  2. Y dies -> fenced + SETTLE_NS elapsed -> ('handing_X_Y_e2', 'fenced_settled', 'fenced', 'running')
  3. S checks :1321 (holder=X is live -> take-over refused); X checks :1338 (not held -> refused); Z barrier waits for not-handing (:1243) -> ('handing_X_Y_e2', 'fenced_settled', 'deadlocked_barrier', 'deadlocked_handing')
=== H2: role_hand target dies (fixed): HOLDS (5 states) ===
=== H3: role_hand target dies (vacuity): VIOLATION (5 states) ===
```
**Non-vacuity:** `H3` checks only whether `holder` (`X`) is fenced/unfenced/dead (omitting `target` in `handing`), immediately hitting the permanent `handing(X -> Y)` and barrier deadlock.

**Smallest Fix:**
In table `:1321` (and the gate rule for unit take-over), change `"The holder is fenced or dead ..."` to:
> `For held: the holder is fenced or dead, and SETTLE_NS has passed since the stop was confirmed; or the holder is unfenced and FENCE_NS + SETTLE_NS have passed since the first fence action. For handing (X → Y): either the holder X, or the target Y (after the same delay on Y), is no longer starting, live or sealing (with the successor computed from whichever of X or Y failed, or Y's successor when both remain not live).`
(If `Y` had not yet mapped `u` when it died, `S` can safely rebuild after `Y` is `fenced`/`unfenced` + delay—note `X` already unmapped `u` in step 3 and stopped using it, though adding `X` must not use `u` once `handing` is written keeps mutual exclusion airtight.)

---

## Finding 8: `sealed` written before raising `park_request` (`:1301`), missing `panic == 0`, and 2-node `sealing` deadlock (`:1153-1155`, `:1299`)

**Severity:** `breaks isolation` (dual kernel execution on the same core) and `blocks for ever` (2-node deadlock)

**Quotes:**
- Line `:1301`:
  > `Effect, mode 1: the member word becomes sealing. The node hands each unit role it holds to its successor (Roles), finishes or refuses with gone the requests it serves (it answers what is in its kernel rings), saves and seals its block, writes the instant of its seal in its node beacon, writes sealed, and parks every core after raising its park request; their words stay owned.`
- Line `:1151`:
  > `| sealed (g) | starting (g) | the node that calls node_start mode resume | Every core whose word names the node is confirmed parked by the seal's park request |`
- Line `:1154`:
  > `| sealing (g) | sealed (g) | the node itself, as its last write before its last core parks | No role word of a unit role names it, as holder or as target. ... its other cores have parked |`
- Lines `:1153`, `:1155`, `:1299`:
  > `| live (g) | sealing (g) | the node that calls node_stop mode seal | At least one other node is live |` (`:1153`)
  > `| starting, live, sealing, sealed (g) | fencing (g) | any live node, with evidence | The evidence holds; at least one other node is live (except for evidence self) |` (`:1155`)
  > `Then, for every mode, busy if no other node would be live afterwards (a phantom node does not count: Roles).` (`:1299`)

**Scenarios:**
1. **`sealed` before `park_request` (`breaks isolation`):** Step sequence `:1301` explicitly writes `sealed` **before** raising `park_request` and parking its cores! Prior to raising `park_request`, every core's `parked` in its core beacon *already equals* its stale `park_request` (both equal `0` from boot, or equal the count from an earlier seal/resume). Meanwhile another node `Z` calls `node_start(X, resume)`. `:1151` sees `member == sealed` and `parked == park_request` on every core, flips `X` to `starting(g)`, and launches the replacement kernel on `X`'s physical cores **while the old `X` kernel is still running `:1301`**—violating the core invariant ("nothing starts a node that might still be running", `:1163`).
2. **Missing `panic == 0` check (`wrong result` / `breaks isolation`):** Neither `:1154` nor `:1151` checks `node_beacon.panic == 0`. A multi-core node where core 1 wrote `panic != 0` (`self`) concurrently with core 0 executing `sealing -> sealed` can enter `sealed` and be resumed instead of fenced.
3. **2-node / last-live-node `sealing` deadlock (`blocks for ever`):** On a 2-node machine (`X, Y` live; or `n` nodes with `n-2` sealed/dead), `X` calls `node_stop(Y, seal)`. `:1299` checks `"no other node would be live afterwards"` -> `X` is live -> succeeds, putting `Y` in `sealing`. Now `X` is the **sole `live` node**. Suppose `X` fails (`panic != 0` or hangs) before `Y` finishes sealing:
   - **Zero `live` nodes remain** on the machine (`Y` is `sealing`, still running kernel code!).
   - `Y` cannot accuse `X` with `self`/`stale` because `:1155` requires the accuser to be **`any live node`**!
   - `Y` cannot complete its seal (`:1154`) if it holds any unit role (hand-over step 4 requires a `live` target, `:1327`/`1329`), and even if `Y` held no unit role and became `sealed`, nothing `live` exists to resume `Y`.
   - And `:1148-1161` has **no `sealing -> live` transition**, so `Y` cannot abort its seal to become `live` and recover `X`! The whole machine is deadlocked with a live-running `sealing` kernel unable to recover or finish.

**Mechanical Check (`explore_cores_failure_sealing.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cores_failure_sealing.py`
```
=== I1a: sealed before park_request (contract): VIOLATION (3 states) ===
  Error: Two kernels executing on same physical core concurrently (sealed written before park_request at :1301)
  1. X writes member=sealed BEFORE raising park_request (:1301) -> ('sealed', 'old_executing_1301', 1, 1, False)
  2. Supervisor calls node_start(X, resume) -> :1151 sees parked==park_request, starts NEW kernel while old X still runs! -> ('starting', 'dual_kernels', 1, 1, True)
=== I1b: sealed before park_request (fixed): HOLDS (3 states) ===
=== I1c: sealed before park_request (vacuity): VIOLATION (3 states) ===
...
=== I2a: 2-node sealing last-live-fails (contract): VIOLATION (4 states) ===
  Error: Sole live node X failed while Y was sealing: zero live nodes remain, Y cannot accuse X or abort seal
  1. X calls node_stop(Y, seal) (:1299 allows since X is live) -> Y enters sealing -> ('live', 'sealing', 'Y', 'ok')
  2. Sole live node X fails with panic!=0 (self) while Y is sealing -> ('panicked_running_self', 'sealing', 'Y', 'ok')
  3. Y(sealing) cannot accuse X (:1155 requires live accuser), cannot transition sealing->live (:1148-1161), cannot finish seal -> whole machine wedged -> ('panicked_running_self', 'sealing', 'Y', 'deadlocked_no_live_node')
=== I2b: 2-node sealing last-live-fails (fixed): HOLDS (4 states) ===
=== I2c: 2-node sealing last-live-fails (vacuity): VIOLATION (4 states) ===
```
**Non-vacuity:** `I1c` raises `park_request` after writing `sealed`; `I2c` denies `sealing -> live` when the sole `live` peer fails. Both fail immediately.

**Smallest Fix:**
1. In `:1301` and `:1154`: specify that before writing `sealed`, `X` parks all non-last cores first (raising each core's `park_request` and confirming it parked), checks `panic == 0`, **raises its own last core's `park_request` first**, then in the gate's last write checks `panic == 0` and writes `sealed`, and enters the park stub which writes `parked = park_request` and halts. In `:1151`, also require `park_request > 0` (every core was requested at least once) or confirm `parked == park_request` after `park_request` was incremented by the seal.
2. For 2-node sealing (`:1148-1161`, `:1299`): either add a transition **`sealing (g) -> live (g)`** made by the sealing node itself when no other node is `live` (so `Y` aborts the seal and accuses `X` as a `live` node), or require `node_stop` mode `seal` (`:1299`) to see at least one other `live` node that is not the sole survivor—wait: even with 2 live nodes, aborting `sealing -> live` when the sole other `live` node fails lets 2-node replacement stay safe! (Note: once `Y` reaches `sealed` with 0 `live` nodes, the whole machine has 0 running nodes anyway; aborting `sealing -> live` closes the live-`sealing` deadlock window cleanly.)

---

## Finding 9: x86-64 BSP park stub hits the SDM §7.7.1 hardware NMI-blocking latch (`:1199-1200`) and leaves a `sealed` BSP `unfenced` (`:1202`)

**Severity:** `blocks for ever` (`unfenced` on a `sealed` BSP also freezes all its memory until reboot)

**Quotes:**
- Line `:1120`:
  > `Each physical core has a start request in the living part, beside its park request, written through the gate by the node that starts it; then x86-64 sends an NMI, which wakes the halted stub`
- Lines `:1199-1202`:
  > `1. Send an NMI to p. If X's kernel can still run its NMI handler, the handler sees its member word in fencing, writes what it can of its core's crash record (The crash record), leaves VMX root operation if it is in it, writes the park request it reads into parked, and enters the park stub's loop with interrupts masked.` (`:1199`)
  > `2. Send INIT to p, unless p is the core firmware booted (the bootstrap processor) ... The bootstrap core is stopped and confirmed by the NMI of step 1 alone: its handler parks it and writes parked` (`:1200`)
  > `4. The park stub ... writes the park request it reads into parked of the core beacon, and halts with interrupts masked. An NMI wakes it: it reads its start request and, if one names a node, goes to the entry stub; otherwise it halts again.` (`:1202`)

**Hardware Proof & Two Failure Modes:**
Verified directly in **Intel® 64 and IA-32 Architectures Software Developer's Manual, Order `325384-086US` (December 2024), Vol. 3A, §7.7.1 ("Handling Multiple NMIs")**:
> When an NMI is delivered, *"the processor masks further NMIs until the `IRET` instruction is executed."* (Earlier editions numbered this §6.7.1; Order `325384-086US` places it in §7.7.1.)

1. **BSP permanently unstartable after an NMI fence (`:1199` + `:1200` + `:1120`):** When the fence sends an NMI to the BSP (`:1199`), the CPU latches hardware NMI-blocking. The BSP's NMI handler **"enters the park stub's loop with interrupts masked"** without executing `IRET` (`:1199`). Because `:1200` **skips `INIT` on the BSP** (which is the only other hardware event that clears NMI blocking on APs), NMI blocking stays latched forever while the BSP executes `hlt` in the park stub. After `R6`, when `node_start` writes `start_request` and sends an NMI (`:1120`), **the hardware drops/blocks the start NMI**, `START_NS` expires, and the BSP can never run again for the rest of the boot. (On top of that, while parked inside an NMI context, a machine check or fault returning via `IRET` or nested NMI behavior differs unexpectedly.)
2. **`sealed` BSP becomes `unfenced` (`:1186` + `:1200` + `:1202`):** Suppose the BSP sealed cleanly (entering the park stub from `:1301` without an NMI). Later, `SEAL_NS` expires or `node_stop(kill)` accuses the `sealed` node (`:1186`). The fence driver raises `park_request`, skips `INIT` on the BSP (`:1200`), and sends an NMI (`:1199`). The park stub wakes from `hlt` (`:1202`), **reads ONLY `start_request`**, sees none, and executes `hlt` again **without writing `park_request` into `parked`** (and if the NMI handler vector is the park stub's trivial handler, `:1202` never mentions checking `park_request` or member state `fencing`!). `parked` never advances to `park_request`, `FENCE_NS` expires, and the `sealed` node is declared **`unfenced`**—permanently freezing all memory it held until machine restart (`:1144`).

**Mechanical Check (`explore_cores_failure_sealing.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cores_failure_sealing.py`
```
=== J1: x86-64 BSP NMI latch/stub (contract): VIOLATION (7 states) ===
  Error: Sealed x86-64 BSP accused by seal/kill becomes unfenced because :1202 park stub ignores park_request
  1. BSP seals cleanly -> writes parked=0 and halts in park stub (:1301/:1202) -> ('sealed_parked', False, 0, 0, 0, 'ok')
  2. SEAL_NS expires / kill -> driver raises park_req=1, skips INIT on BSP (:1200), sends NMI (:1199) -> ('sealed_nmi_sent', False, 1, 0, 0, 'ok')
  3. Park stub wakes on NMI, checks ONLY start_req==0 (:1202), halts again -> parked stays 0 < 1 -> FENCE_NS expires -> unfenced! -> ('bsp_unfenced', False, 1, 0, 0, 'sealed_bsp_unfenced')
=== J2: x86-64 BSP NMI latch/stub (fixed): HOLDS (8 states) ===
=== J3: x86-64 BSP NMI no-IRET (vacuity): VIOLATION (7 states) ===
  Error: x86-64 BSP permanently unreachable after NMI park due to SDM §7.7.1 NMI-blocking latch (no IRET, no INIT)
...
=== J4: x86-64 BSP stub ignore park (vacuity): VIOLATION (7 states) ===
```
**Non-vacuity:** `J3` removes `IRET` when entering the park stub from NMI (failing BSP restart); `J4` omits `parked = park_request` in the park stub wake path (failing `sealed` BSP fence). Both `J1` and `J3`/`J4` fail; `J2` holds.

**Smallest Fix:**
In `:1199` and `:1202`, replace `"enters the park stub's loop with interrupts masked"` and `:1202`'s wake rule with:
> `The NMI handler, after writing the crash record, leaving VMX root operation, and writing parked, returns by IRET into the park stub (with IF = 0, stack in the stub's per-core frame, clearing hardware NMI blocking per Intel SDM §7.7.1) before halting.` (`:1199`)
> `The park stub writes the park request it reads into parked on entry and after every wake from hlt (and checks member state fencing/start_request, returning from any NMI delivered inside the stub by IRET first so NMI blocking never stays latched); it enters the entry stub if start_request names a node, otherwise it halts again.` (`:1202`)

---

## Finding 10: ARM64 SDEI lifecycle omits `SDEI_EVENT_ENABLE`, ignores TF-A's `CPU_ON` wipe & `CPU_SUSPEND` mask, and calls `CPU_OFF` inside an uncompleted SDEI context

**Severity:** `blocks for ever` (plus EL3 wedge on some firmware)

**Quotes:**
- Line `:1205`:
  > `(1) Signal p with SDEI event 0 (SDEI_EVENT_SIGNAL), every core having registered the kernel's handler and unmasked itself when it entered its node (the entry stub unmasks before it reads its core word). (2) The handler calls PSCI CPU_OFF, which stops the calling core only.`
- Line `:1120`:
  > `The core enters the kept image's entry stub, which unmasks the fence's signal first (ARM64: SDEI_PE_UNMASK), then reads its core word and parks again`
- Line `:1306`:
  > `Methods: ... 2 PSCI CPU_SUSPEND, parameter the power state ... Flags: bit 0, the state loses the core's context`
- [kernel.md:149](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L149):
  > `SDEI registration, unmasking, and SDEI_EVENT_SIGNAL ... Refused ... SDEI_EVENT_DISABLE and SDEI_EVENT_UNREGISTER of event 0`

**Verification Against Trusted Firmware-A (`ARM-software/arm-trusted-firmware`, v2.12.0) and Linux (`arch/arm64/kernel/smp.c`):**
1. **Missing `SDEI_EVENT_ENABLE` (`kernel-interface.md:1205`, `kernel.md:149`):** In TF-A `services/std_svc/sdei/sdei_state.c:77-92`, `DO_REGISTER` transitions event 0 only from `[reg_]` to `reG_` (registered, **not enabled**); `DO_ENABLE` is required to reach `rEG_`. In `services/std_svc/sdei/sdei_main.c:919-938` (`sdei_signal`), TF-A checks **both** that the target PE is unmasked **and** that Event 0 is `REGISTERED` and `ENABLED`, otherwise failing with `SDEI_EINVAL`. Neither `:1205` nor `kernel.md:149` lists `SDEI_EVENT_ENABLE`!
2. **`PSCI CPU_ON` wipes private event registration/enable state (`:1120`):** In TF-A `services/std_svc/sdei/sdei_main.c:42-61` (`sdei_cpu_on_init`, subscribed at `:1123` to `psci_cpu_on_finish`), every `PSCI CPU_ON` resets private event state (`se->state = 0`) and calls `sdei_pe_mask()`. When `node_start` boots a core via `CPU_ON` (`:1120`), calling `SDEI_PE_UNMASK` alone in the entry stub leaves Event 0 **unregistered and disabled** on that core for the new node.
3. **`PSCI CPU_SUSPEND` power-down re-masks the PE (`:1306` + `:1205`):** In TF-A `services/std_svc/sdei/sdei_main.c:64-72` (`sdei_cpu_wakeup_init`, subscribed at `:1126` to `psci_suspend_pwrdown_finish`), waking from any power-down `CPU_SUSPEND` (`node_idle` flag bit 0, `:1306`) calls **`sdei_pe_mask()`**. Unless the kernel calls `SDEI_PE_UNMASK` immediately upon waking from a power-down idle state, `SDEI_EVENT_SIGNAL` returns `SDEI_EINVAL` while the core runs!
4. **Calling `PSCI CPU_OFF` directly inside the SDEI handler (`:1205(2)`):** In TF-A `services/std_svc/sdei/sdei_intr_mgmt.c:539`, `plat_ic_end_of_interrupt(intr_raw)` runs only when the SDEI handler completes via `SDEI_EVENT_COMPLETE*`. Calling `psci_do_cpu_off` (`lib/psci/psci_off.c:130-165`) directly inside the handler powers the core down with an **uncompleted SDEI context** in EL3. As **Linux `arch/arm64/kernel/smp.c:840-844` (`arm64_nmi_cpu_stop`)** explicitly documents: *"CPU_OFF from that not-yet-completed context wedges EL3 on some firmware"* (Linux avoids this by completing the SDEI handler with `COMPLETE_AND_RESUME` into a stub that then calls `CPU_OFF`).

**Mechanical Check (`explore_cores_failure_sealing.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cores_failure_sealing.py`
```
=== K1: ARM64 SDEI lifecycle (contract): VIOLATION (4 states) ===
  Error: TF-A SDEI_EVENT_SIGNAL failed with EINVAL (cp=running, sdei_state=reg_disabled, pe_masked=False)
  1. Kernel registers SDEI event 0 & unmasks PE (:1205), omits SDEI_EVENT_ENABLE -> state=reG_ -> ('running', 'reg_disabled', False, False, 'ok')
  2. Fence calls SDEI_EVENT_SIGNAL -> TF-A sdei_main.c:931 returns EINVAL (not ENABLED) -> class-1 core unfenced! -> ('running', 'reg_disabled', False, True, 'sdei_signal_einval')
=== K2: ARM64 SDEI lifecycle (fixed): HOLDS (6 states) ===
=== K3: ARM64 SDEI no-enable (vacuity): VIOLATION (4 states) ===
...
=== K4: ARM64 SDEI no-reunmask (vacuity): VIOLATION (4 states) ===
  Error: TF-A SDEI_EVENT_SIGNAL failed with EINVAL (cp=woke_susp, sdei_state=enabled, pe_masked=True)
```
**Non-vacuity:** `K3` drops `SDEI_EVENT_ENABLE` and `K4` drops post-`CPU_SUSPEND` `SDEI_PE_UNMASK`; both fail `sdei_signal` with `EINVAL`.

**Smallest Fix:**
In `:1120`, `:1205`, and [kernel.md:149](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L149):
1. Add `SDEI_EVENT_ENABLE` to the ARM64 allow-list (`kernel.md:149`) and specify that after every `CPU_ON` (in the entry stub before unmasking) the core calls `SDEI_EVENT_REGISTER`, `SDEI_EVENT_ENABLE`, and `SDEI_PE_UNMASK`, and after every power-down `CPU_SUSPEND` wakeup it calls `SDEI_PE_UNMASK` before resuming user or kernel work.
2. In `:1205(2)`, specify that the SDEI event 0 handler writes `parked` / crash record and completes via `SDEI_EVENT_COMPLETE_AND_RESUME` (Arm DEN 0054C §5.1.10) to a park routine that calls `PSCI CPU_OFF` outside active SDEI handler context (only falling back to parking with interrupts masked if `CPU_OFF` returns `DENIED`).

---

## Finding 11: `idle_until` `u64` overflow (`:1171`, `:1182`) and missing non-idle tick bound (`:483`, `:557`, `:564`) cause false `stale` and self-accusations (`:651`)

**Severity:** `wrong result` (falsely kills healthy nodes; or suppresses hangs up to 68 s / indefinitely)

**Quotes:**
- Line `:1171`:
  > `idle_until, the instant of its next armed timer when it goes idle (the largest value if none), so a core does not have to beat while idle`
- Line `:1182`:
  > `| stale | The gate recorded an observation (a core whose word names X's generation, its heartbeat value h, instant t), and now the heartbeat still reads h, now − t ≥ STALE_NS, and now > idle_until + STALE_NS |`
- Lines `:483`, `:557`, `:564`, `:651`:
  > `period T | Nanoseconds. B ≤ T ≤ 2^36 ns (about 68 s, provisional).` (`:483`)
  > `Slack ... Time that no context with budget wants goes to throttled contexts whose holder is runnable` (`:557`)
  > `After the choice, the hardware timer is set to the earliest of: the instant the running context's budget ends (now + r, when it runs from the ready queue), the first replenishment instant of the four throttled queues, and the first firing instant of the timer queue. With nothing armed, it is not set.` (`:564`)
  > `If one core of a node ... its heartbeat goes stale while it is not idle, the node accuses itself (evidence self)` (`:651`)

**Scenarios:**
1. **`u64` overflow (`:1171` + `:1182`):** When a core goes idle with no armed timer, `:1171` sets `idle_until = u64::MAX` (`18_446_744_073_709_551_615`). In `u64` arithmetic, `idle_until + STALE_NS` (`100_000_000`) wraps to `99_999_999`. Once `now ≥ 100 ms` after boot, **every idle core with no armed timer satisfies `now > idle_until + STALE_NS`** and is immediately accused `stale` by the sweep (`:1189`)!
2. **Wake-from-idle dilemma (`:483`, `:557`, `:564`, `:651`, `:1182`):**
   - If waking from idle **does not** reset `idle_until`, then a core that hangs immediately after waking suppresses `stale` until its previous `idle_until + STALE_NS`—up to 2^63 ns (292 years, or 68 s for a replenishment!).
   - If waking from idle **clears** `idle_until = 0`, consider a core running a compute-bound thread on **slack** (`:557`) with no replenishment/timer armed (`:564`: `"With nothing armed, it is not set"`), or with a budget `B > STALE_NS` (`:483` permits `B` up to 68 s!). While that thread runs for ≥ 100 ms without making a syscall, **no kernel event executes (`heartbeat` does not advance, `:1171`), and `idle_until == 0`**. Both an external sweep/waiter (`:1182`) and the node's own other cores (`:651`, `"its heartbeat goes stale while it is not idle"`) **falsely accuse and kill the healthy running node**!

**Mechanical Check (`explore_cores_failure_sealing.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cores_failure_sealing.py`
```
=== L1: idle_until u64 wrap (contract): VIOLATION (2 states) ===
  Error: Healthy core falsely accused as STALE (false_stale_wrap) at state ('idle_no_timer', 18446744073709551615, 200000000, 50000000, 'false_stale_wrap')
  1. Sweep observes idle core (idle_until=U64_MAX): U64_MAX+STALE_NS wraps to 99999999 < now=200000000 -> falsely accused STALE! -> ('idle_no_timer', 18446744073709551615, 200000000, 50000000, 'false_stale_wrap')
=== L2: slack false stale (contract): VIOLATION (3 states) ===
  Error: Healthy core falsely accused as STALE (false_stale_slack) at state ('running_slack', 0, 400000000, 250000000, 'false_stale_slack')
  1. Core wakes from idle (clears idle_until=0), runs thread on slack (:557, no timer) for 150ms without syscalls -> ('running_slack', 0, 400000000, 250000000, False)
  2. Sweep/waiter checks heartbeat unchanged for 150000000ns while core ran slack -> falsely accuses healthy core STALE! -> ('running_slack', 0, 400000000, 250000000, 'false_stale_slack')
=== L3: idle_until + timer cap (fixed): HOLDS (2 states) ===
=== L4: missing timer cap (vacuity): VIOLATION (3 states) ===
```
**Non-vacuity:** `L4` clears the idle flag on wake without bounding the non-idle timer interval `≤ STALE_NS`, triggering the false accusation in 2 steps.

**Smallest Fix:**
1. In `:1171` and `:1182`: store `idle_until = 2^63` (or `u64::MAX` with **saturating addition** `idle_until.saturating_add(STALE_NS)` and `now - idle_until >= STALE_NS` only when `now >= idle_until`), and reset `idle_until = 0` at every exit from idle (alongside updating `heartbeat`).
2. In `:564` and `:1171`: whenever a core is **not idle** (running user code from ready or slack), arm the hardware timer no later than `now + STALE_NS / 2` (a kernel heartbeat event that takes no thread change, updates `heartbeat`, and re-arms if still non-idle).

---

## Finding 12: Attack on "Faults found in the decided shape (D-128)" Points 4, 5, and 10 (`:2091`, `:2092`, `:2097`)

**Severity:** `blocks for ever` (`node_watch` contradiction, TOCTOU, 4-slot cap, node-wide `SENDS_PER_PEER` starvation, silent mailbox deadlocks)

**Quotes:**
- Point 4 (`:2091`, `:939`, `:1281`, `:1308`, `:1357`):
  > `4. A wait on another node no longer ends at the peer's death. With rule 7 withdrawn, a client whose service is on another node waits on its own notify; only a node_watch that the library binds tells it the peer died. And no call lends a scheduling context across nodes: a service that serves other nodes pays for their requests with its own contexts.` (`:2091`)
  > `A wait that must end if the peer dies binds node_watch for the peer's node to the same notify with another badge bit, so a change of the peer's member word wakes the wait. This is the one guarantee of the old text that the library must rebuild` (`:939`)
  > `| node_watch | node, index, notify | | read on the node, which must name the caller's node. Notify 0 unbinds |` (`:1281`, `:1308`)
  > `| NODE_WATCH_SLOTS | 4 | The node agent and up to three supervisor replicas |` (`:1357`)
- Point 5 (`:2092`):
  > `5. Only frames cross, and only from their owner. ... The remote signal of D-128 is written here as the doorbell of a frame grant (D-129), the only reading consistent with "no transfer of capabilities other than grants of frames": the owners should confirm that reading.` (`:2092`)
- Point 10 (`:2097`, `:907`, `:921-922`, `:1085`):
  > `10. Every node needs a mailbox agent. node_send reaches a node only through the thread that waits on its mailbox; that agent, which forwards remote frames and requests to the node's processes, becomes part of what every other node relies on, and a node whose agent has died is unreachable from other nodes until a supervisor restarts it` (`:2097`)
  > `Send: a node has at most SENDS_PER_PEER (8) sends in flight to each peer` (`:907`)

### Verdict: True D-128 Prices vs. Fixable Contract Faults

1. **Point 4 (`:2091`):**
   - **What is a true price of D-128:** The kernel no longer ends cross-node waits (`wait` on a local `notify` tied to a shared ring) automatically on peer death, and no cross-node scheduling context lending exists (`:2091` last sentence). Those follow directly from D-128 ("only one-shot operations cross", "no call, wait or receive on an object of another node").
   - **What are fixable contract faults that break `:939` itself:**
     1. *Direct contradiction (`invalid` on every call):* `:939` tells clients to bind `node_watch` **"for the peer's node"**, whereas `:1281` and `:1308` require `node` to **"name the caller's node"** (`invalid` for any peer node!). As written, the library's prescribed workaround cannot even be called.
     2. *4-slot exhaustion:* `:1357` allows only `NODE_WATCH_SLOTS = 4` per node (`"The node agent and up to three supervisor replicas"`), so individual clients/libraries (`:939`) cannot bind per-wait watches without starving the node agent and supervisors (and even a single multiplexer per node cannot cover `:939` as written).
     3. *TOCTOU missed-death deadlock:* Even if a multiplexer agent binds `node_watch`, `:1308` only signals *"after each change"*. If peer `Y` dies *after* the client sends a ring request (or checks `slot 13`) and *before* `node_watch` binds (or before the local node finishes R0), the edge signal is missed and the client hangs in `wait` forever!
2. **Point 5 (`:2092`):**
   - **What is a true price of D-128:** Owner-only frame grants, inability to pass endpoints/notifies across nodes (names travel inside rings instead), three-party sharing requiring owner grants to each party, and tying `grant_signal` to a grant's doorbell (`:930`) are genuine consequences of D-128 requiring owner confirmation.
   - **What are fixable contract faults around it:** The missing `use_index` in `grant_entry`, the `Release`/`Revoke` crossing deadlock (Finding 3), and the destroyed-waiter grant leak (Finding 4) are not prices of D-128—they are bugs in the ring/table state machine that the text can close directly.
3. **Point 10 (`:2097`):**
   - **What is a true price of D-128:** Because `node_send` targets one per-node mailbox endpoint (`:1085`), every node must run a trusted mailbox agent that other nodes rely on for connection setup/forwarding while the node is live (`:2097`).
   - **What are fixable contract faults in the surrounding rules:**
     1. *Indistinguishable dead mailbox vs. transiently busy mailbox:* Under `:922`, if a node's mailbox agent dies (or is temporarily killed without killing the node), every `node_send` returns **`would_wait`**—the exact same code returned when the agent is simply servicing the previous message (`would_wait` retry loop)! Callers cannot tell a transiently busy mailbox from a permanently unreachable node whose mailbox agent died (and cannot distinguish "no receiver waiting" from "mailbox capability deleted/dead").
     2. *Node-wide `SENDS_PER_PEER = 8` (`:907`) starvation / DoS:* Because `SENDS_PER_PEER = 8` is tracked **per node pair** rather than per task/process, 8 malicious or sluggish tasks (or threads destroyed in flight per Finding 4) holding 8 concurrent `node_send` calls to node `Y` make every `node_send` to `Y` from **every other service on node `X`** (including supervisor and memory service!) fail immediately with `busy` (`:921`).

**Mechanical Check (`explore_cores_failure_sealing.py`):**
Command: `timeout 30s python3 -B -I /tmp/review8_hydrogen/explore_cores_failure_sealing.py`
```
=== M1: node_watch peer invalid (:939 vs :1281): VIOLATION (2 states) ===
  Error: Point 4 / node_watch failure: invalid_peer_watch
  1. Client calls node_watch(peer_Y) as :939 directs -> :1281 refuses (Invalid: must name callers own node) -> ('live', False, 'none', 'invalid_peer_watch')
=== M2: node_watch TOCTOU (:1308): VIOLATION (5 states) ===
  Error: Point 4 / node_watch failure: toctou_missed_death
  1. Client sends ring request -> prepares to call node_watch(Y) -> ('live', False, 'binding', None)
  2. Peer Y dies BEFORE client executes node_watch(Y) -> ('dead', False, 'binding', None)
  3. Client calls node_watch(Y) after Y died, then waits on notify -> missed transition, hung forever! -> ('dead', True, 'hung', 'toctou_missed_death')
=== M3: node_watch fixed: HOLDS (5 states) ===
=== M4: node_watch edge-only (vacuity): VIOLATION (5 states) ===
```
**Non-vacuity:** `M4` omits the level-check signal on `node_watch` bind, failing the TOCTOU check in 3 steps.

**Smallest Fix:**
1. **Point 4 (`:939`, `:1281`, `:1308`):** First, clarify `:939` that the per-node **node agent** (using one of the 4 `node_watch` slots on the **caller's own node**, since `:1308` delivers every member/role change the caller's node processes—or `read`-only watch of slot 13 checked against the node's own `node_watch` notification) multiplexes peer-death wake-ups to local clients; AND fix `:1308` so `node_watch` is level-safe (if `node` changes have already occurred or the client checks slot 13 *after* registering/arming with the node agent, no death edge is lost). If direct per-client `node_watch` on peer nodes is intended instead, `:1281` and `:1357` need an owner decision to change the slot cap and allow peer `node` arguments.
2. **Point 10 (`:907`, `:922`):** Reserve at least 1–2 slots of `SENDS_PER_PEER` (or grant a separate credit for `NODE_WATCH` / mark-aware / supervisor tasks, or enforce a per-caller/per-task quota) so unprivileged processes cannot starve the supervisor's or memory service's `node_send` to `Y`; and document that `slot 15` (mailbox endpoint) death returns `gone` (not `would_wait`) in `SendAnswer` if the mailbox endpoint itself has been destroyed/unbound.
