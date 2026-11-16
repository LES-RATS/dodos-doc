# Contract Review 9 (Hydrogen): Pass 16 Rules, Faulty Nodes, Builder Implementability, and SDM 325462-093 Citations

Target: [kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) (with cross-references to [kernel.md](/Users/btw/Documents/repos/Docs/architecture/kernel.md) and [model-15-contract-gaps.md](/Users/btw/Documents/repos/Docs/research/drafts/model-15-contract-gaps.md)) at commit `fd13764` (diff `a0a6947..fd13764`, pass 16 / D-133).

---

## Summary of Findings

| # | Severity | Lines | Summary |
|---|---|---|---|
| 1 | `breaks a guarantee` | [:93](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L93), [:1040](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1040), [:1183](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1183), [:1236](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1236), [:1264](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1264), [:1267](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1267), [:1366](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1366), [:1374-1376](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1374-L1376), [:1736](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1736), [:1954](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1954) | **Gap 8 (`started` + 1 ms NMI retry):** Latched retry NMI under SDM §7.7.2 fires at stub `IRET` or hits the live kernel; missing generation lets starter `C1`'s retry hit `C2`'s restarted generation; unset `u64` layout collides `0` ("none") with node slot `0`; and `:1183` imposes `started` retries on ARM64/RISC-V which have no park stub. |
| 2 | `breaks a guarantee` | [:92](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L92), [:794](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L794), [:1050](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1050), [:1154-1162](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1154-L1162), [:1172](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1172), [:1261](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1261), [:1294](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1294), [:1394](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1394) | **Gap 6 (`FenceRecord`):** `words 4..67` are indexed by ordinal core position, which shifts as multi-core R6 frees earlier cores, reading an older core's `last_stop` and freeing remaining cores before `SETTLE_NS`; `last_stop == 0` when no stop was sent and gate guards on `FenceRecord` are also unsettled. |
| 3 | `breaks a guarantee` | [:107](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L107), [:127](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L127), [:141](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L141), [:250](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L250), [:273](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L273), [:327](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L327), [:347](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L347), [:877](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L877), [:879](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L879), [:881](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L881), [:1000-1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1000-L1001), [:1899](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1899) | **Gap 15 (invalid remote capability with mapping):** Exempts only `mapping` (kind 1), omitting `unmapping` (kind 3) whose in-flight invalidation completion depends on the slot; and rejecting every non-exemption use with `gone` at slot check contradicts allowing `"a removal by its holder"`. |
| 4 | `blocks building` | [:134](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134), [:734](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L734), [:740](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L740), [:782](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L782), [:998](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L998), [:1000-1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1000-L1001), [:1889](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1889) | **Gap 12 (multi-unit MSI IEC sequence):** Neither the `unit request table` entry nor `irq` stores the MSI's PCI segment or unit cursor to find the next unit; failing at unit >= 2 leaks the written IRTE, claimed `irq`, and root slot; and thread destruction mid-sequence is unsettled. |
| 5 | `blocks building` | [:362](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L362), [:734](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L734), [:763](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L763), [:771-779](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L771-L779), [:910](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L910), [:923](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L923), [:996-997](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L996-L997), [:1039](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1039) | **Gap 3 (`UnitRequest` operands):** Op 1 (`attach`) omits `iospace` root table physical address and domain number; Op 5 (`redirection entry`) omits remapping handle `h` (or vector/APIC ID), trigger mode, and polarity. |
| 6 | `contradiction` | [:200-203](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L200-L203), [:215](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L215), [:229](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L229), [:254](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L254), [:318](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L318), [:527](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L527), [:585](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L585), [:644](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L644), [:646](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L646), [:648](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L648), [:744](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L744), [:757](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L757), [:1101](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1101), [:1903](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1903) | **Gap 5 (L2 lock order & bound *k*):** `aspace` and `sched` destruction, `send` on a `reply` object / `call` delivery, `irq` arrival / `notify_bind`, `task_revoke`, and `cap_move` / record-list updates invert the `:648` kind order and exceed the bound *k*. |
| 7 | `contradiction` | [:508](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L508), [:629](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L629), [:1364](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1364), [:1456](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1456), [:1933](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1933), [:1950](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1950) | **Gap 7 (single 64-core window):** `:1364` and `:1933` forbid naming cores across two 64-core windows, contradicting `:1950`'s fallback that runs one node `"on every usable core"` whenever `<= 64` usable cores cross a 64-core boundary (e.g., core 0 unusable or two sockets). |
| 8 | `contradiction` | [:573](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L573), [:633](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L633), [:662](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L662), [:1247](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1247), [:1254-1255](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1254-L1255), [:1469](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1469) | **Gap 16 (own-core heartbeat watch):** Requires every core at each timer event to watch sibling cores `"by the rule of stale evidence"`, which requires gate-written `observations[8]` (shared per node), impossible for up to 63 siblings; also idle siblings with no armed timer never fire `:662`. |

---

## Finding 1 (Gap 8): The `started` word and 1 ms NMI retry race with SDM §7.7.2 NMI blocking, live kernels, restarts, and slot 0

**Severity:** `breaks a guarantee` (also `blocks building` and `contradiction`)

**Lines:** [:93](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L93), [:1040](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1040), [:1183](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1183), [:1236](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1236), [:1264](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1264), [:1267](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1267), [:1366](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1366), [:1374-1376](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1374-L1376), [:1736](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1736), [:1954](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1954)

**Quotes:**
- Line [:1183](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1183):
  > `The stub writes the start request it takes into started of its core beacon (0 when it parks), and the node that starts a core sends the wake again every START_RETRY_NS (1 ms), in its recovery reserve, until started equals its request or the node is no longer starting (at most START_NS, after which the node is accused with stale). Why (gap 8): an NMI that reaches the stub between its read of the start request and its halt starts nothing, the lost wake-up the multicore trial found in its own park stub (pull request 8 of dodos-kernel); owned would confirm too late, since the core builds state before it writes it, and a wake repeated to a core that has left the stub would be taken by its node's kernel as a fence signal.`
- Line [:1267](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1267):
  > `An NMI wakes it: the stub's NMI handler writes the park request it reads into parked, reads the start request, and returns by IRET; if the start request names a node the stub writes it into started and goes to the entry stub, otherwise it halts again.`
- Line [:1264](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1264):
  > `If X's kernel can still run its NMI handler, the handler sees its member word in fencing, writes what it can of its core's crash record (The crash record), leaves VMX root operation if it is in it, writes the park request it reads into parked, and returns by IRET into the park stub, with interrupts masked, so that NMIs are delivered again: "Once NMI blocking is established, the processor blocks subsequent delivery of NMIs until the next execution of the IRET instruction" (Intel SDM §7.7.2, "NMI Blocking"...`
- Line [:1040](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1040):
  > `INIT, SIPI and NMI go only to a core whose core word names a node whose fence the caller drives and carries the fence mark, or to a core whose word names, as joining or owned, a node the caller is starting or resuming by node_start (Cores)...`
- Line [:1736](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1736) & [:1954](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1954) & [:93](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L93):
  > `The park request and the start request: one u64 each per physical core in the living part; parked (u64) in the core beacon.` (`:1736`)
  > `every core word (free, its park and start requests 0)` (`:1954`)
  > `node slot: The index of a node in the machine table, 0 to n − 1` (`:93`)

**Step-by-step defects:**

1. **An NMI arriving after the stub's NMI handler begins, or after the core leaves the stub (`breaks a guarantee` / `unsettled case`):**
   - *Case A (Latched behind SDM §7.7.2 NMI blocking while still in the stub):* Starter `C` sends NMI #1; core `p` enters the park stub's NMI handler, which establishes hardware NMI blocking (`§7.7.2`). Starter `C` sees `started == 0 != req` 1 ms later (or right after NMI #1 entered the handler) and sends NMI #2. Hardware latches NMI #2 in the local APIC until `IRET`. In `:1267`, the stub executes `IRET` **before** checking `if the start request names a node` and **before** writing `started`. On `IRET`, hardware immediately delivers latched NMI #2 to the park stub's NMI vector while `p` is mid-branch or already inside the kept entry stub (before `p` installs the node kernel's IDT at `:1366`). The stub's NMI handler reads the *same* unchanged `start request`, writes `started` again, and restarts the entry stub from the top (or loops on every retry NMI), corrupting entry-stub stack/register state and re-executing `CPU`/`TLB`/`SDEI` initialization mid-boot.
   - *Case B (Non-atomic read of `started` vs `G10` NMI delivery to the node's kernel):* Reading `started != req` (`:1183`) and sending an NMI through the gate (`:1040`) are separate steps. Suppose `C` reads `started != req` (or enters `C`'s gate just as `p` writes `started = req`), `C` stalls briefly (SMM or bus delay), and `C`'s retry NMI reaches `p` after `p` has already left the entry stub, installed node `N`'s kernel IDT, written `owned`, or even transitioned `N` to `live`. Line `:1183` itself states that *"a wake repeated to a core that has left the stub would be taken by its node's kernel as a fence signal"*. Yet `:1264` only specifies what `X`'s kernel NMI handler does when it *"sees its member word in fencing"*, leaving the behaviour when `member` is `starting` or `live` **unsettled**:
     - If the kernel NMI handler unconditionally parks on any NMI, a late start-retry NMI parks `p` and aborts a healthy boot/live node `N`.
     - If the kernel NMI handler ignores NMIs when `member != fencing`, `:1183`'s rationale (*"would be taken by its node's kernel as a fence signal"*) is false and contradicts the premise that motivated `started` in the first place (and requires specifying that a healthy kernel checks `member == fencing` and discards non-fencing NMIs without parking, which `:1264` omits).

2. **Two starters and a starter that dies while retrying (`breaks a guarantee` without generation in `start request`):**
   - *Two starters across a restart (`C1` and `C2`):* Suppose starter `C1` calls `node_start` for node `N` (`g`), sets `start request`, starts retrying every 1 ms, and stalls (e.g., SMM/interrupt delay) after `N`'s generation `g` fails (`START_NS` expires or `N` panics), is fenced, and is reclaimed by R6. Before `C1`'s next retry or stalled G10 write executes, supervisor `C2` calls `node_start` for `N` (`g + 2`) on the **same core `p`** (`N` is `starting (g + 2)`, `p` is `joining (N, g + 2)`). Under `:1183`, `C1`'s retry stop condition is *"until `started` equals its request or the node is no longer starting"*—which looks only at `N` being `starting`, not generation `g`! Likewise, `:1040` G10 permits NMI *"to a core whose word names, as joining or owned, a node the caller is starting or resuming by `node_start`"* without specifying that the gate records/checks the exact `(N, g)` generation that the caller started or that `start request` carries `g`. If `start request` carries no generation or sequence, `C1` can fire an NMI at `C2`'s start (or keep the old `start request` matching `N` when `C2` has not even written `start request` yet).
   - *Starter `C` dies while retrying:* Under `:1374-1375`, if `C` writes `start request = N` and sends NMI #1, that single NMI lands in the stub's read-to-`hlt` lost-wake window, and `C` immediately dies before sending NMI #2 at 1 ms, no other node ever picks up the retry loop. Core `p` stays halted in the stub forever until `START_NS` expires and kills `N` with `stale`. (While `:1375` anticipates `C` dying at step 2, a partial boot where core 0 of `N` booted and core 1 lost its sole NMI is still lost for `START_NS`.)

3. **`blocks building`: unspecified `u64` layout of `start request` and `started` collides with node slot 0:**
   - `:1736` defines `start request` and `started` only as `u64`.
   - `:1954` zeroes `start requests` at machine start-up (`0`), `:1236` writes `0` into `started` when a core parks, and `:1183` says *"A fence cancels the start requests of the cores whose words name the fenced node"* (presumably writing `0`).
   - Meanwhile, `:93` defines node slots `0 to n - 1`, and `:1267` checks `"if the start request names a node"`. With raw node slot index `0` encoded as `0`, node slot `0` is indistinguishable from "empty / cancelled / `0`"!

4. **`contradiction` across architectures (ARM64 and RISC-V have no park stub or `started` writer):**
   - `:1183` states unconditionally across all three architectures: *"The stub writes the start request it takes into `started` of its core beacon (0 when it parks), and the node that starts a core sends the wake again every `START_RETRY_NS` (1 ms), in its recovery reserve, until `started` equals its request or the node is no longer starting"*.
   - However, `:1270` (ARM64 PSCI `CPU_ON`) and `:1271` (RISC-V `sbi_hart_start`) have no x86-64 park stub (`:1267`) and start cores directly into `"the kept image's entry stub"` (`:1183`), and `:1236` defines `started` as `"the start request the park stub took when it left for the entry stub, 0 when it parks"`. Nothing in `:1183`, `:1270`, or `:1271` says who writes `started` on ARM64/RISC-V or forbids sending redundant `CPU_ON` / `sbi_hart_start` calls every 1 ms on ARM64/RISC-V (where `CPU_ON` returns `ALREADY_ON` once the core is running).

**Smallest Fix:**
1. Fix the `StartRequest` `u64` bit layout in `abi/` and `:1736`: e.g., bits `0..15` = `node_slot` (or `0xFFFF` for none), bit `16` = `valid` (so `0` is never a valid node request), bits `32..63` = `generation` (and optionally `seq`), written only by `C`'s gate when `C` starts `(N, g)` and cleared atomically to `0` by the fence or by `p`'s entry stub once taken.
2. In `:1267`, have the x86-64 park stub **read `start request`, write `started = req` (under an atomic/locked compare-and-clear or before `IRET`), mask NMIs via an `IRET` frame only after clearing/consuming the wake path**, and do **not** re-enter the entry stub if `started == req` is already set or `start request` no longer matches `CoreWord`'s `(N, g)`. Specify in `:1264` that a live/starting kernel's NMI handler checks `member.state == fencing` and ignores non-fencing NMIs (recording trace/return by `IRET` without parking).
3. Restrict `START_RETRY_NS` NMI retries explicitly to x86-64 (since ARM64 `CPU_ON` and RISC-V `sbi_hart_start` are synchronous firmware starts that either start the entry stub or fail), and tie G10 (`:1040`) and `:1183`'s retry condition to matching `(N, g)` in `CoreWord`, `Member`, and `start request`.

---

## Finding 2 (Gap 6): `FenceRecord.words[4..67]` ordinal position shifts during multi-core R6 and frees cores before `SETTLE_NS`

**Severity:** `breaks a guarantee` (also `unsettled case`)

**Lines:** [:92](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L92), [:794](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L794), [:1050](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1050), [:1154-1162](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1154-L1162), [:1172](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1172), [:1261](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1261), [:1294](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1294), [:1394](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1394)

**Quotes:**
- Line [:1261](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1261):
  > `The driver's gate records the instants of the fence in the living part, in the fence record of X's node slot, so that every node judges the delays of Roles and of R6 from the same instants, and the gate checks them when it allows a take-over or a write of R6: word 0, the generation the record concerns (bits 0-31, the other bits 0); word 1, the instant of the first fence action; word 2, the instant the fence was confirmed; word 3, reserved, 0; words 4 to 67, for each position of X's cores (0 to 63), the instant of the last stop sent to that core. An instant of 0 means none.`
- Line [:92](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L92):
  > `a node also numbers its own cores by their position in the node, 0 to N − 1 in the order of core numbers (A node of several cores), and every rule says which it uses...`
- Line [:1154-1162](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1154-L1162) & [:1172](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1172):
  > `The core word, one per physical core, in the living part (64 bits): 0-1 state ... 2 the fence mark ... 3 unusable ... 4-15 check ... 16-31 the node slot ... 32-63 the node's generation` (`:1153-1162`)
  > `any word naming (N, g) -> free, keeping the flag unusable ... the core is confirmed stopped, and SETTLE_NS have passed since the last stop sent to it, as its node's fence record gives it (Reclaim)` (`:1172`)
- Line [:1294](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1294):
  > `and every core word that names X's generation, which becomes free (keeping the flag unusable) once its core is confirmed stopped and SETTLE_NS have passed since the last stop sent to it, as X's fence record gives it (the second round showed R6 clearing a word while a stop was in flight landing on the core's next node: its variant r6_inflight).`

**Analysis of the three deep-dive questions:**

1. **Can R6 clear a core too early (`breaks a guarantee`: `r6_inflight`)?** Yes, deterministically on any multi-core node (`N >= 2`):
   - `CoreWord` (`:1154-1162`) stores only `(state, mark, unusable, check, node_slot, generation)` — it does **not** store the core's original position `j` (`0..N-1`) inside `X`. For nodes created dynamically by `node_start`, `BootNodes` does not list `X`'s cores either. Therefore, any reclaimer running R6 (another node `Y` that has only the living machine table, not `X`'s private node block) can determine a core's `"position"` in `X` only by scanning `CoreWord`s that still name `(X, g)` in core-number order (`:92`).
   - **Step-by-step trace:**
     1. Node `X` starts on physical cores `2` (position `0`) and `5` (position `1`).
     2. `X` is fenced. Core `2` stops at `t = 100 µs` (`words[4 + 0] = 100 µs`); core `5` is held in SMM and receives a repeated SIPI/INIT stop at `t = 15,000 µs` (`words[4 + 1] = 15,000 µs`), then confirms stopped at `t = 15,100 µs`.
     3. At `t = 15,200 µs`, reclaimer `Y` starts R6 (`:1294`, max 32 units per step). Suppose `Y` processes core `2` before core `5` (or processes core `5` in a later R6 step after `CORE` step 1 hit its 32-unit budget after freeing core `2`). For core `2` (`pos 0`), `15,200 - 100 >= SETTLE_NS (1,000 µs)` holds, so `Y`'s gate sets `CoreWord[2]` to **`free`**.
     4. On the next R6 unit/step at `t = 15,200 µs`, `CoreWord[2]` is already `free`! Only core `5` still has `CoreWord[5] == (X, g)`. Scanning cores of `(X, g)` in core-number order now gives core `5` **position `0`** (`0..0`).
     5. `Y`'s gate checks `words[4 + 0]` (`100 µs`) instead of `words[4 + 1]` (`15,000 µs`), concludes `15,200 - 100 >= 1,000 µs`, and frees `CoreWord[5]` **800 µs before `SETTLE_NS`**.
     6. Another node immediately calls `node_start` on core `5`, and the in-flight INIT/SIPI sent to core `5` at `15,000 µs` lands on the new node (`r6_inflight` broken).

2. **Who writes `FenceRecord`, and can a faulty driver write a false instant to force early take-over or R6 (`unsettled case` / missing gate guards)?**
   - Who writes it: `:794` and `:1261` assign write authority exclusively to the gate of the driver node (`member.driver == caller`), plus R6? (Actually R6 only *reads* `FenceRecord`; the next generation's first fence overwrites `word 0..67`.)
   - Can a faulty driver node *D* pass a forged timestamp through its gate? Under `:1050` (*"misuse of the gate's legal interface by a corrupted kernel"*), if the gate reads `clock` itself rather than accepting a caller timestamp, a corrupted kernel cannot supply an arbitrary backdated `word 1`, `word 2`, or `words 4..67`.
   - **However**, `:1261` never specifies the gate's own transition checks for writing `FenceRecord` (contrast `:1169-1173` and `:1294`, which explicitly list what the gate checks). For example, if *D*'s corrupted kernel calls its gate's "record first fence action" path again on an already-fencing `X` (where `word 0 == X.gen`), or calls "write confirmation" without verifying `parked`/confirmations, or takes over as driver and rewrites `word 1` instead of keeping it, nothing in G1–G14 states the gate invariants on `FenceRecord` fields. If the gate overwrites `word 1 = now` on re-entry, a faulty driver can continually delay an unfenced take-over (`FENCE_NS + SETTLE_NS`) forever.

3. **`unsettled case` when `words[4 + j] == 0`:**
   - `:1261` states: `"An instant of 0 means none."` When a `sealed` ARM64 node (or a self-parked node whose `AFFINITY_INFO` already returns `OFF` or `sbi_hart_get_status` returns `STOPPED`, `:1394`) is fenced and confirmed without sending a new stop, `words[4 + j]` stays `0`.
   - `:1294` checks `"once its core is confirmed stopped and SETTLE_NS have passed since the last stop sent to it, as X's fence record gives it"`, without settling whether `words[4 + j] == 0` satisfies the check immediately (0 -> no stop was ever in flight) or fails it (blocking R6 forever because no stop was sent).

4. **Is `FenceRecord` size counted everywhere?**
   - Yes, `544` bytes per node slot (`4 * 8 + 64 * 8 = 544`, `68 KB` for 128 slots) is counted consistently in `:1261`, `:1728`, `:1738`, `:1744`, `:1874`, and `:2039` (`StartMachine` layout v2 = 80 bytes). *(Side note on `:1874`: the Machine table row at `:1874` includes `a fence record of 544 bytes per node slot`, though it omits `start requests` and `identifier words` from that summary sentence.)*

**Smallest Fix:**
1. Instead of indexing `words 4..67` by mutable ordinal position during R6, index `words 4..67` by **`core_number - window_base`** (using the `64`-core single window guaranteed by Gap 7 — i.e., store `(window: u32, _pad: u32)` in `word 3` alongside `generation` in `word 0`, and store each core's `last_stop` at `words[4 + (core_number - 64 * window)]`), OR store the node's initial core bitmask in `FenceRecord` so each core's bit offset `0..63` stays invariant after R6 frees other cores!
2. State explicitly in `:1261` and `:1294` that `last_stop == 0` (no stop sent in this fence) satisfies the `SETTLE_NS` check immediately once the core is confirmed stopped, and list the gate's invariant checks for every `FenceRecord` write (only when `member.driver == caller`, `word 1` written once per `(X, gen)` atomically with accusing `X`, `word 2` written once atomically with `fenced` after all confirmations hold, `last_stop` written monotonically by `clock` on G10 stop).

---

## Finding 3 (Gap 15): Invalid remote capabilities omit `unmapping` (`kind 3`) and block holder cleanup (`gone`)

**Severity:** `breaks a guarantee` and `contradiction`

**Lines:** [:107](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L107), [:127](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L127), [:141](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L141), [:250](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L250), [:273](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L273), [:327](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L327), [:347](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L347), [:877](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L877), [:879](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L879), [:881](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L881), [:1000-1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1000-L1001), [:1899](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1899)

**Quotes:**
- Line [:877](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L877):
  > `A use of an invalid remote capability is gone, judged with the slot, and the slot becomes dead, unless its record holds a mapping: then the slot stays until a removal reaches it (the step of a Revoke, R2, or a removal by its holder), which undoes the mapping with its invalidations (gap 15: dropping the mapping in the use would skip the invalidation of the node's other cores and units, against the guarantee of TLB).`
- Line [:250](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L250) & [:1899](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1899):
  > `A full record is a mapping, a message page binding, or a mapping that is unmapping: its entries are cleared and their invalidation, on other cores of the node or by an IOMMU unit, is not yet complete...` (`:250`)
  > `Word 2 is the record: bits 0-1 its kind (0 empty, 1 mapping, 2 message page binding, 3 unmapping: a mapping whose entries are cleared and whose invalidation on other cores of the node, or by an IOMMU unit, is not complete...` (`:1899`)
- Line [:327](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L327) & [:1000-1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1000-L1001):
  > `what it completes (the record of one frame capability, unmapping meanwhile...) ... empties the record and takes it out of its space's list...` (`:327`)
  > `what it completes, which is either the thread that waits for it in waiting for a unit ... or the record left unmapping by a removal step, a step of a Revoke or a step of R2` (`:1000`)
- Line [:273](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L273) & [:879](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L879) & [:107](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L107) & [:127](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L127):
  > `cap_delete on a dead slot makes it empty.` (`:107`)
  > `cap_delete on a capability whose object is dying works as on any other: it acts on the slot, not on the object.` (`:127`)
  > `aspace_unmap | frame | No right on the capability itself, as for cap_delete: it can only take access away.` (`:273`)
  > `cap_delete, cap_revoke and cap_inspect act on Y's slots; aspace_map and iospace_map map it (below), and aspace_unmap, iospace_unmap and aspace_protect act on its record` (`:879`)

**Two distinct faults:**

1. **`unmapping` (`kind 3`) is not exempted (`breaks a guarantee`):**
   - `:250` and `:1899` distinguish record kind `1` (*mapping*) from kind `3` (*unmapping*), and `:877` exempts *"unless its record holds a mapping"*.
   - **Step-by-step scenario:**
     1. Node `Y` maps a granted frame of `X` in `slot S` (`kind = 1`) and later starts `aspace_unmap(S)` (on multi-core x86-64/RISC-V) or `iospace_unmap(S)` (while `X`'s grant is still `live`). `S`'s record transitions to `kind = 3 (unmapping)`, with an in-flight core invalidation request (`:327`) or `UnitRequest` (`:1000`) holding a pointer to `S` so completion can empty `S` and decrement `use_entry`'s leaf count (`G4, G6`).
     2. Meanwhile, `X` starts revocation (`use_entry` leaf count > 0) and writes `revoking` in `X`'s grant entry. `S` is now an invalid remote capability whose record is `unmapping` (`kind 3`), not `mapping` (`kind 1`).
     3. Before the core/unit invalidation finishes, a second thread on `Y` invokes any call on `S` (e.g., `cap_inspect(S)` or `aspace_protect(..., S, ...)`). Because `S`'s record is kind `3` (not `mapping`), the rule of `:877` drops `S` to `dead`, wiping `S` (`word 2` / `word 3` / list links) and removing the slot out from under the in-flight invalidation completion, which either dereferences a `dead` slot or leaks the `aspace`/`iospace` list linkage and `use_entry` leaf count forever!

2. **Blanket `gone` contradicts holder removal (`contradiction`):**
   - `:877` states `"A use of an invalid remote capability is gone, judged with the slot"` with **no list of exempt calls** (contrast `:1079` for a revoked task, which explicitly writes `"except task_read, task_revoke and the capability calls (cap_*)"`).
   - Thus, when holder `Y` calls `cap_delete(S)`, `cap_revoke(S)`, `aspace_unmap(S)`, or `iospace_unmap(S)` directly on a mapped invalid remote slot `S`, Step 1 of [Order of checks](#order-of-checks) (`:141`) returns `gone` and refuses the call!
   - This directly contradicts `:877` itself (*"then the slot stays until a removal reaches it (the step of a Revoke, R2, or a removal by its holder), which undoes the mapping with its invalidations"*), as well as `:273`, `:347`, `:879`, `:107`, and `:127`: the holder can never remove or unmap its own invalid remote capability except indirectly via an ancestor/cspace sweep or remote `Revoke`.

**Smallest Fix:**
Change `:877` to:
> `A use of an invalid remote capability (except cap_delete, cap_revoke, aspace_unmap, iospace_unmap, and the removal steps of a Revoke, R2 or cap_* on an ancestor or dying cspace) is gone, judged with the slot, and the slot becomes dead, unless its record holds a mapping or is unmapping: then the slot stays until a removal or unmap reaches it, which undoes the mapping with its invalidations; cap_delete or cap_revoke on an invalid remote capability whose record is empty (or whose unmap completes) turns it empty/dead as usual, and aspace_unmap/iospace_unmap undoes its mapping and invalidations.`

---

## Finding 4 (Gap 12): Multi-unit MSI invalidation cannot find the next unit, leaks on unit >= 2 failure, and does not settle destroyed waiters

**Severity:** `blocks building` (and `unsettled case`)

*(Note: this finding examines the sequential multi-unit request machinery of Gap 12 itself.)*

**Lines:** [:134](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134), [:734](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L734), [:740](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L740), [:782](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L782), [:998](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L998), [:1000-1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1000-L1001), [:1889](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1889)

**Quotes:**
- Line [:998](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L998):
  > `Several remapping units (gap 12). On a machine with several IOMMU units, the claim of an MSI sends one request for the invalidation of the interrupt entry cache to each unit that serves the source's PCI segment, one after another in the order of the units: it waits for the answer of one before it sends the next, so the thread holds one wait and one entry of the unit request table at a time (the entry is used again for the next unit, in the event that consumes the done of the one before). A unit found failed ends the call busy, and no later unit is asked; the units already asked keep their invalidation, which is harmless (an invalidation done twice changes nothing).`
- Line [:1000-1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1000-L1001):
  > `Each node has a unit request table in its node block, UNIT_REQUESTS (64, provisional) entries, each: the role, the operation, the epoch it was last sent with, its state (queued or sent), the credit it uses while sent, and what it completes, which is either the thread that waits for it in waiting for a unit (a call: iospace_unmap, iospace_attach and its detach, irq_claim of a line, a write of remapping entries) or the record left unmapping...` (`:1000`)
  > `done completes the entry (the counts of the record's leaves are lowered and the record is emptied, or the waiting call ends with its result)` (`:1001`)
- Line [:782](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L782):
  > `The interrupt remapping cache of the IOMMU is invalidated after a remapping entry is written.`
- Line [:134](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L134):
  > `a wait for an answer of another node, for a unit or for its node's cores ends, and the answer, the unit's confirmation or the completion of the request, when it comes, finds no thread to wake: its effect on grants, records, counts and credits is applied as if the thread still waited, D-131`

**Issues blocking implementation and leaving states unsettled:**

1. **Missing PCI segment and remaining-unit cursor (`blocks building`):**
   - `:998` says *"the entry is used again for the next unit, in the event that consumes the done of the one before"*, sending to *"each unit that serves the source's PCI segment, one after another in the order of the units"*.
   - Yet `:1000` fixes the fields of a `unit request table` entry as `(role, operation, epoch, state, credit, what it completes -> thread)`, `UnitRequest` for Op 4 passes operands `(0, 0)` (`:923`), `irq` entries (`:734`, `:1889`) store only `(core, table index)` in the capability slot (the PCI `source` word is not even stated to be stored in the `irq` entry for MSI, or at least `:734`/`:736` never records a unit cursor), and `thread` holds no PCI segment field.
   - When `UnitAnswer(done)` arrives for unit `i` in the recovery reserve (`:939, :1001`), the consumer event knows only `role_i`, `op = 4`, and `thread`. On a machine with IOMMU units `[0 (seg 0), 1 (seg 1), 2 (seg 0), 3 (seg 0)]`, the event has **no way to know the call's PCI segment (`seg 0`)** or, if `role_i` was matched only by unit index, whether later units of `seg 0` remain! Furthermore, if `role_0` is the local node (`:1000`: *"serves it with no message"*), `:998` does not clarify how/when the local unit completion transitions to `role_2`.

2. **Unit >= 2 failure leaves already-claimed IRTE, interrupt table entry, and capability slot behind (`unsettled case`):**
   - `:782` writes the remapping entry **before** sending the unit requests (`:998`). `:740` creates the `irq` entry and places the root `irq` capability in `destination` (otherwise what does `:740` state-check `no_slot` against?).
   - When unit 1 succeeds and unit 2 returns `failed`, `:998` states only: *"A unit found failed ends the call `busy`, and no later unit is asked; the units already asked keep their invalidation, which is harmless"*.
   - What happens to the **already-written remapping entry**, the **claimed `irq` entry in the core's interrupt table**, and the **`irq` capability in `destination`** is unsettled! If they are not rolled back before `irq_claim` returns `busy`, the failed `irq_claim` permanently leaks a claimed vector/IRQ table entry and leaves an active IRTE pointing at the vector (violating the general rule that a failed call changes no capability/vector state, or risking an orphaned IRTE); if they are rolled back, `:998` must specify clearing the IRTE, freeing the `irq` table entry, and leaving `destination` empty (and what happens if unit 1 cached a *now-cleared* IRTE!).

3. **Thread destroyed while in `waiting for a unit` mid-sequence (`unsettled case`):**
   - Suppose `irq_claim` wrote the IRTE and `irq` entry, sent the Op 4 request for unit 1, entered `waiting for a unit`, and then another thread on the same node destroys the claiming thread (`:134`) before unit 1 answers `done`.
   - `:134` ends the thread's wait (without cancelling the unit request) and says `"its effect on grants, records, counts and credits is applied as if the thread still waited"`. When unit 1's `done` arrives, `:998` would advance the entry and send unit 2's request even though the caller was already destroyed and may even have had its `irq` capability / `cspace` destroyed meanwhile!

**Smallest Fix:**
1. Add `segment: u16` (or `next_unit_index: u16` + `segment: u16`, or store the `(irq_core, irq_idx, segment)` on the `unit request table` entry) so the completion handler knows both the segment and the next IOMMU unit index, and clarify that a locally-held unit completing in the holder's recovery reserve invokes the same advancement step.
2. Specify rollback if any unit in the chain fails: `irq_claim` does not commit the `irq` capability to `destination` (reserving `destination` only as checked state, or cleaning up `destination`, the `irq` table entry, and the IRTE before returning `busy`).
3. If a waiting `irq_claim` thread is destroyed (`:134`) while unit `i` is in flight, specify whether the completion of unit `i` aborts the remaining units and rolls back the partial `irq` claim, or finishes all units before allowing the `irq` root's removal.

---

## Finding 5 (Gap 3): `UnitRequest` operands omit required arguments for Op 1 (`attach`) and Op 5 (`redirection entry`)

**Severity:** `blocks building`

**Lines:** [:362](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L362), [:734](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L734), [:763](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L763), [:771-779](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L771-L779), [:910](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L910), [:923](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L923), [:996-997](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L996-L997), [:1039](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1039)

**Quotes:**
- Line [:923](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L923):
  > `| 4 | UnitRequest | Three: the role (0-15), the epoch (16-44) and the operation (48-55, numbered in Devices and shared hardware); then two operands, whose meaning the operation fixes (attach and detach: the device identifier; a redirection entry: the global system interrupt, and 1 if claimed or 0 if masked; an invalidation: 0 and 0) | 3 |`
- Line [:996](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L996):
  > `What stays with the owner of a device (the node of its driver): its device blocks and their frames; its iospace and all the iospace's tables; its vectors, claimed through the owner's irq_control on the owner's cores; the record of the devices each of its iospaces serves and of its domain numbers...`
- Line [:362](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L362) & [:1039](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1039):
  > `Then the unit's context entry for the device points at the iospace's tables, under the iospace's domain number for that unit, given at its first device and freed with its last.` (`:362`)
  > `The gate of a unit's role holder writes a context entry only if the root it names is a top-level iospace table owned by the node that owns the device...` (`:1039`)
- Line [:779](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L779):
  > `With interrupt remapping ... handle h = core number × 192 + (vector − 48) ... A line is programmed in the IOAPIC in remappable format with the same handle.`

**Proof that a builder cannot implement Op 1 or Op 5 from `:923`:**
1. **Op 1 (`attach`):** `:923` sends *only* `the device identifier` (one operand, the other unused). By `:996`, the `iospace` root table and the owner's `domain number` stay private to the requester node (`X`)—note that `Report` at `:910` and `:927` explicitly carries `(key = device, root table, domain number)`. On the role holder (`H`), `H`'s gate requires the `iospace`'s root table physical address (`G9` at `:1039`) and `:362` requires its `domain number` to program the IOMMU context entry. Neither is sent in `UnitRequest(attach)`.
2. **Op 5 (`redirection entry`):** `:923` sends *only* `(global system interrupt, 1 if claimed or 0 if masked)`. By `:734` and `:996`, the requester's `irq` entry is in the requester's own core interrupt table, inaccessible to the IOAPIC role holder (`H`), and `:779` states that a claimed line is programmed in the IOAPIC in remappable format with remapping handle `h = core * 192 + (vector - 48)` (or `(APIC ID, vector)` without remapping, `:780`) plus trigger mode (`:772`) and polarity (`:773`). With only `(GSI, 1)`, `H` has no handle `h` (nor trigger mode, polarity, vector, or APIC ID) to write into the IOAPIC RTE!

**Smallest Fix:**
Pack all required operands into the two 64-bit operand words of `UnitRequest` (still 3 words total -> 1 ring entry, preserving all reserve arithmetic):
- **Op 1 (`attach`):** operand 1 = `(device_id << 0) | (domain << 32)`; operand 2 = `iospace_root_table_phys_addr`.
- **Op 2 (`detach`):** operand 1 = `device_id`, operand 2 = `0` (or `domain` if selective IOTLB/context cache invalidation needs it).
- **Op 3 (`invalidation of translations`):** `domain` (or `0` for global) instead of `(0, 0)` if domain-selective invalidation is used, or keep `(0, 0)` if unit-wide.
- **Op 5 (`redirection entry`):** operand 1 = `(gsi: u32) | (claimed_or_masked << 32) | (trigger << 33) | (polarity << 34) | (remapped_bit << 35)`; operand 2 = `handle h` (when remapped) or `(apic_id << 32) | vector` (when unremapped).

---

## Finding 6 (Gap 5): Variant L2 lock order and bound *k* are contradicted by six call/removal paths

**Severity:** `contradiction` (and `blocks building`)

**Lines:** [:200-203](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L200-L203), [:215](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L215), [:229](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L229), [:254](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L254), [:318](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L318), [:527](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L527), [:585](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L585), [:644](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L644), [:646](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L646), [:648](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L648), [:744](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L744), [:757](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L757), [:1101](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1101), [:1903](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1903)

**Quotes:**
- Line [:648](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L648):
  > `The order by kind is: the sequence words of cspace segments, by space then segment (the state of an untyped with them, under the lock of its root's segment); task; thread; endpoint; reply; notify; timer; sched; aspace; iospace; the lock words of cores, by position; the gate lock. Two locks of one kind are taken in the order of their objects' addresses. A call's k is the number of objects and slots its rules name, plus one per core whose queues or interrupt table it may change, plus one for the gate lock. Why this order: a call looks up its capabilities first (slots), then checks the objects in the order its rules name them, then changes the per-core state of its effect, then writes through the gate; no call needs a lock of an earlier kind after a later one.`
- Line [:318](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L318):
  > `When the root capability is the next to remove, the kernel first empties the record of each capability in the aspace's list, most recently mapped first. Then it unbinds each thread of its list, most recently bound first: the thread is bound to no aspace.`
- Line [:527](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L527):
  > `When its root capability is the next to remove, each step clears up to 32 of its lends, from the top of the chain down; each cleared lend counts as one of the 32 of the step. A thread that loses its context this way is marked as having lost it.`
- Line [:203](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L203) & [:209](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L209):
  > `On a reply object: answers the caller and makes the object idle; would_wait if it is not armed` (`:203`)

**Contradictions under `:648` (each breaks both the fixed kind order and/or the bound *k* formula):**

1. **`aspace` and `iospace` destruction (`:318`, `:364`):** Removal reaches the `aspace` root slot, acquires `aspace` (or `iospace`), and then walks the `aspace`'s internal lists to empty up to 32 frame-capability slot records (`cspace segment < aspace`) and unbind up to 32 threads (`thread < aspace`). Neither those slots nor those threads are named by the `cap_delete`/`cap_revoke` call (`k` violations: up to 32 extra `cspace` segments + 32 `thread`s vs 1 named slot!), and acquiring `cspace segment` or `thread` while holding `aspace` directly inverts `:648`'s `cspace segment -> thread -> aspace` order.
2. **`sched` destruction (`:527`):** While holding `sched` (to walk `chain`), the step clears up to 32 `reply` lends (`reply < sched`) and marks up to 32 receiver `thread`s (`thread < sched`), inverting `thread -> reply -> sched` and touching up to 64 unnamed objects beyond *k*.
3. **`send` on a `reply` object and `reply_recv` (`:202-203`):** The call names only the `reply` object and message page (`reply`), yet answering the armed caller writes the reply (plus up to 4 derived/moved capabilities into the caller's receive `cspace` segments!) and wakes the waiting `thread` (`cspace segment < thread < reply`), directly inverting the order and locking unnamed caller `thread` and `cspace` segments. (Similarly, `call` (`:200`) names `endpoint`, yet writes capabilities to/from a waiting receiver's `cspace` and arms its `reply` and wakes its `thread`, where `cspace < thread < endpoint < reply`.)
4. **Interrupt arrival (`:744`) and `notify` destruction (`:757`, `:1400`):** An arrival enters under the core lock to read the `irq` table entry (`core`), then signals `notify` (`notify < core`), wakes a `thread` on `notify` or bound `endpoint` (`thread < endpoint < notify < core`), and may wake another `core`. Likewise, `notify` destruction (`:757`) walks its linked `irq` entries (`core > notify`, ok in order, but touches unnamed `core` locks outside *k*) and its bound `endpoint` (`endpoint < notify`, order inversion).
5. **`task_revoke` (`:1101`) and `cap_move` / derivation-list / record-list updates (`:254`, `:1903`):** `task_revoke(task)` names only `task`, yet detaches up to 32 unnamed `thread`s (`k` exceeded) and pulls them out of unnamed `endpoint`/`notify` queues and disarms unnamed `reply` objects. And `cap_derive`/`cap_move`/`cap_delete` splice `prev`/`next` slot pointers in the node's single `derivation list` (`:1903`) and space's `record list` (`:254`), whose neighbour slots can sit in any earlier `(cspace, segment)` (inverting `cspace segment` address order unless all `cspace` segments share one lock).

**Smallest Fix:**
1. Replace the broken one-sentence *k* formula (`"the number of objects and slots its rules name..."`) with explicit per-operation lock sets (including the worst-case bound of 32 for bounded removal/revoke steps) and acknowledge that lock-order inversions in backwards-linked teardowns (`aspace -> thread/cspace`, `sched -> reply/thread`, `reply -> thread/cspace`, `notify -> endpoint`, `core -> notify`) cannot follow `:648`'s forward-only order: either use a try-lock-with-backoff / drop-and-relock-in-order protocol, move `cspace` segment locks under a single per-`cspace` (or per-node derivation) lock, or drop L2 in favour of L1 unless those paths are redesigned.

---

## Finding 7 (Gap 7): Single 64-core window in `node_start` and `BootNodes` contradicts `:1950` on machines with `<= 64` usable cores crossing a window boundary

**Severity:** `contradiction`

**Lines:** [:508](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L508), [:629](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L629), [:1364](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1364), [:1456](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1456), [:1933](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1933), [:1950](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1950)

**Quotes:**
- Line [:1364](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1364):
  > `The cores a node starts on lie in one window of 64 core numbers (gap 7): node_start and BootNodes name them by one window and one mask, so a set of cores of two windows cannot be named, and a node has at most 64 cores; a context's cores set, a window and a mask, can then hold every core of its node`
- Line [:1933](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1933):
  > `and BootNodes (the number of node slots n, and the nodes the machine start-up starts: for each, the cores it holds as a window and a mask; by default n is the number of usable cores and each usable core starts a node of its own)`
- Line [:1950](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1950):
  > `A core of fence class 0 does not stop the start-up: the machine then runs one node, on every usable core if the image supports that many and on the core firmware booted otherwise, unless the image declares the hardening monitor or accepts an unfenced core (The fence).`

**Contradiction:**
- By `:1364`, **no node can hold cores from two 64-core windows**, and `BootNodes` and `StartNode` / `sched_set_cores` (`:515`) represent a node's cores (or a context's `cores` set) solely as `(window: u32, mask: u64)`.
- Consider a machine with a fence-class-0 core and 64 (or fewer, e.g., 48) usable cores whose `StartCore` core numbers cross a 64-core boundary—for example:
  - 64 usable cores with core 0 absent/retired/disabled, leaving usable core numbers `1..64` (cores `1..63` in window 0, core `64` in window 1); or
  - a 2-socket machine (32 usable cores per socket) where socket 0 has core numbers `0..31` (window 0) and socket 1 has core numbers `64..95` (window 1), or a hypervisor with sparse APIC IDs (`0..31` and `64..95`, sorted by hardware ID per `:2024`—actually `:2024` makes `core number` contiguous `0..N_total-1`!).
  - Wait: check `:2024` carefully! Let's inspect `:92` and `:2024`: `:92` defines `core number` as *"The position of a physical core in the core list of the start-up page (entry `Cores`)"*, and `:2024` says `StartCore` has *"one per physical core, sorted by hardware identifier, so a core's position is its core number"*. How can usable cores still cross a 64-core window while numbering `<= 64` usable cores?
  - Whenever **1 or more physical cores in `StartCore` are unusable** (e.g., hyperthreaded SMT sibling cores disabled by policy, fused-off/unusable entries, or a single failed physical core in the `0..63` range on a 65-core-table machine where core `0..63` contains 1 unusable core and core `64` is usable): core numbers are dense over **all physical cores** (`0..64`), while **usable cores** are `<= 64` (`64` usable cores spanning `0..64` across window 0 and window 1)! Similarly, if the image supports 64 cores (`Node` supports 64) and a machine has 65 physical cores where core 17 is unusable (`64` usable cores spanning core numbers `0..64`), `:1950` requires starting **one node on every usable core** (`1..64` or `{0..64}\{17}`), which spans windows 0 and 1 and **cannot be represented by `(window, mask)`** under Gap 7 (`:1364`). (Equally, `node_start` cannot restart a multi-core node across any 64-core boundary when a core in `[0..63]` has been retired with `unusable` and a core in `[64..127]` is `free`.)

**Smallest Fix:**
In `:1950`, replace *"on every usable core if the image supports that many"* with:
> `on every usable core in the window of the core firmware booted (or on the largest subset of usable cores in one 64-core window containing the core firmware booted) if the image supports that many and all such cores share its state features and vector lengths, and on the core firmware booted otherwise`
(Notice also that `:1947` / `:1365` forbid differing state features or vector lengths within one node—another condition `:1950`'s *"on every usable core if the image supports that many"* silently omits on heterogeneous machines with a class-0 core!)

---

## Finding 8 (Gap 16): Own-core heartbeat watching `"by the rule of stale evidence"` cannot fit in `observations[8]` and misses idle siblings

**Severity:** `contradiction` (and `unsettled case`)

**Lines:** [:573](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L573), [:633](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L633), [:662](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L662), [:1247](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1247), [:1254-1255](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1254-L1255), [:1469](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1469)

**Quotes:**
- Line [:662](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L662):
  > `If one core of a node does not release a lock or does not acknowledge a request of its node within CORE_ANSWER_NS of the request's start (the core that started it sees this at the due event it armed, TLB), or its heartbeat goes stale while it is not idle (each core of the node compares, at each of its timer events, the heartbeats of the node's other cores with what it last saw, by the rule of stale evidence, gap 16), the node accuses itself (evidence self), and the whole node is fenced and reclaimed (Cores).`
- Line [:1247](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1247) & [:1255](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1255) & [:1469](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1469) & [:633](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L633):
  > `| stale | The gate recorded an observation (a core whose word names X's generation, its heartbeat value h, instant t), and now the heartbeat still reads h, now − t >= STALE_NS, and now − STALE_NS > idle_until ... |` (`:1247`)
  > `Observations are written by the gate only, at most 8 open per node, stamped with the clock, and expire after 4 × STALE_NS; a node cannot invent an old observation.` (`:1255`)
  > `What the cores of a node share: ... its recovery reserve, its observations and its watch slots.` (`:633`)
  > `| OBSERVATIONS_MAX | 8 | Open suspicions per node |` (`:1469`)
- Line [:573](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L573):
  > `while the core runs a thread, now + STALE_NS / 2, an event that only beats ... An idle core with nothing armed sets no timer.`

**Contradictions:**
1. **`observations[8]` vs 63 sibling cores (gate-checked `stale` evidence):**
   - `:662` states that each core checks its node's other cores *"by the rule of stale evidence"*.
   - Under `:1247`, `:1255`, and `:1469`, the rule of stale evidence requires a gate-recorded observation in the node's shared `observations[8]` array (`:633`, `OBSERVATIONS_MAX = 8`). On a node of `N = 64` cores (`CORES_PER_KERNEL_MAX`), there are up to **63 sibling cores** to watch simultaneously (plus external peer waits and the node's 2 sweep successors). An array of 8 observations cannot hold open observations for 9..63 sibling cores, and under L1/L2 every core taking a timer event would fight over `observations[8]` (or evict external/sibling suspicions before `STALE_NS` is ever reached). Moreover, `:1247` says `"now - STALE_NS > idle_until"`, which works per-core, whereas `:662` speaks of `"what it last saw"` (a private per-core last-seen heartbeat and instant, which is *not* what `"the rule of stale evidence"` in `:1247` uses and has no field listed in `:631`'s per-core node-block list).
2. **Idle siblings never detect a stalled core (`unsettled case`):**
   - By `:573`, `"An idle core with nothing armed sets no timer"`. If core 0 (which hosts the node's `recovery reserve`, `:1314`) hangs while running a thread, and cores `1..N-1` are idle with no timers armed, none of cores `1..N-1` ever takes a timer event to run `:662`, leaving the node's recovery reserve dead until another live node happens to sweep it at `SWEEP_NS` (`1 s`).

**Smallest Fix:**
Define own-core heartbeat watching explicitly in `:631` and `:662` using a per-core `last_seen_hb[63]` / `last_seen_at[63]` array in the core's own part of the node block (independent of the node's external `observations[8]`), checking `now - STALE_NS > sibling.idle_until` and `now - last_seen_at >= STALE_NS` directly without consuming `observations[8]`, and clarify that when all other cores are idle, external `SWEEP_NS` (1 s) is the accepted fallback bound (just as for an idle 1-core node).

---

## Checked and found correct

### 1. Remaining Pass 16 gaps (1, 2, 4, 9, 10, 11, 13, 14) and security/hardware edits
- **Gap 1 (`:1193`, `:1737`):** `Member` bits 7–8 reject fence class `3` in `from_raw` alongside states `8..15`, preventing a forged member word from claiming a non-existent class above `2` (forced).
- **Gap 2 (`:1503`, `:1738`):** Debug area header size is `4 + 2 + 2 + 4 + 4 + 8 + 8 + 8 = 40` bytes of listed fields + `24` reserved bytes = `64` bytes, matching `64` bytes + `4,032` bytes crash record = `4,096` bytes + `256 * 64` (16,384) + `768 * 64` (49,152) = `69,632` bytes (`17 * 4,096`).
- **Gap 4 (`:658`):** Taking pending interrupts at every kernel entry before dispatching a syscall prevents a thread marked *leaving its core* from executing a call before leaving its core and violating `thread_suspend`'s postcondition.
- **Gap 9 (`:970`):** Judging `grant` on the `node` capability upfront with `send` matches [Order of checks](#order-of-checks) (`:141–142`) and `send` (`:203`).
- **Gap 10 (`:877`, `:934`):** Remote capability validity spans `starting`, `live`, `sealing`, and `sealed` of the granting node's recorded generation, so kernel replacement (`seal` + `resume`) breaks no grants while keeping dead-generation grants invalid.
- **Gap 11 (`:354`):** Checking the unit's *failed* bit first among `iospace_attach` state errors matches [Order of checks](#order-of-checks) (`:144`).
- **Gap 13 (`:1447`):** Refusing `role_hand` of a unit role to a phantom node with `busy` prevents permanently wedging the role in `handing` (consistent with `:1382` and `:1418`).
- **Gap 14 (`:658`, `:134`):** Setting the thread's suspended flag when a removal step marks the thread *leaving its core* prevents the remote core from re-scheduling the thread after clearing the mark; `thread_resume` is already refused (`gone`) because the thread's root capability is dying (`:127`).
- **Security & hardware additions (`:326`, `:1090`, `:2244`):** Setting `TTBR*_ELx.CnP = 0` on ARM64 (`:326`), clearing `add_marks` in the delivered header (`:1090`), and keeping `FENCE_NS = 20 ms` / no time-only confirmation for INIT-in-SMM (`:1268, :2244`) are consistent with the contract.

### 2. Gap 3 arithmetic (message sizes, entry counts, and reserve of answers)
From `:916`, every message has a **16-byte header** and `w` 64-bit words after the header, occupying $\lceil (16 + 8w) / 64 \rceil$ 64-byte ring entries (`RING_KERNEL_ENTRIES = 64`, `RING_USER_ENTRIES = 64`):

| Message | Max words `w` (`:920-930`) | Byte length `16 + 8w` | Ring entries `ceil((16 + 8w)/64)` |
|---|---|---|---|
| `Ping` (9) | `0` | `16` | `1` |
| `Revoke` (1), `RevokeStep` (2), `Release` (3), `Signal` (12), `Handed` (6) | `1` | `24` | `1` |
| `UnitAnswer` (5), `ReportAsk` (7) | `2` | `32` | `1` |
| `UnitRequest` (4) | `3` | `40` | `1` |
| `SendAnswer` (10) | `1 + 4 = 5` | `56` | `1` |
| `Send` (11) | `3 + 4 + 64 = 71` | `584` | `ceil(584 / 64) = 10` (`<= 11`) |
| `Report` (8) | `1 + 28 * 3 = 85` | `696` | `ceil(696 / 64) = 11` (`<= 11`) |

**Reserve of answers (`:943`, `:1476`):**
- Each peer can have at most `REQUESTS_PER_PEER = 16` kernel requests and `SENDS_PER_PEER = 8` user sends in flight (`24` outstanding answerable requests total), with at most **one `ReportAsk`** in flight toward a given peer at a time (`:943`).
- In the worst case (15 non-`ReportAsk` kernel requests + 1 `ReportAsk` + 8 `Send`s), the owed answers consume `15 * 1 + 1 * 11 + 8 * 1 = 34` entries (`16 + 8 + 10 = 34`), leaving `64 - 34 = 30` non-reserved entries in the 64-entry kernel ring. The arithmetic matches `RING_ANSWER_RESERVE = 34` and `RING_MESSAGE_ENTRIES_MAX = 11` (`:936, :1476, :1728`).

*(Gap 6 layout sizes also check out arithmetically: `FenceRecord` = `4 * 8 + 64 * 8 = 544` bytes; `128 * 544 = 69,632` bytes = `68 KB`; `StartMachine` = `8 * 4 + 8 + 4 * 4 + 6 * 4 = 80` bytes at layout version 2, `:2039`.)*

### 3. Intel SDM `325462-093` (September 2026) renumbering and verbatim quotes
Checked against Intel 64 and IA-32 Architectures Software Developer's Manual Combined Volumes (order `325462-093`):

1. **Vol. 3A §7.7.2 "NMI Blocking"** (`kernel-interface.md:1264`): Section title and number match `325462-093` (shifted from §6.7.1 / §7.7.1 in earlier editions). Verbatim quote checked: *"Once NMI blocking is established, the processor blocks subsequent delivery of NMIs until the next execution of the IRET instruction."* — **Exact match.**
2. **Vol. 3A §11.4.2 "MP Initialization Protocol"** (`kernel-interface.md:1265`): Section number and INIT BSP-flag rule match `325462-093` (Multiple-Processor Management moved from Chapter 8/9/10 to Chapter 11). — **Exact match.**
3. **Vol. 3A §11.4.4.1 / Table 11-1** (`kernel-interface.md:1266`): Universal Start-up Algorithm delays (10 ms after INIT, 200 µs between SIPIs, shown as an example) match Chapter 11 renumbering in `325462-093`. — **Exact match.**
4. **Vol. 3C §26.8 "Restrictions on VMX Operation"** (`kernel-interface.md:1265`): Section number matches `325462-093` (VMX chapter moved to Chapter 26). Quote checked: *"The INIT signal is blocked whenever a logical processor is in VMX root operation. It is not blocked in VMX non-root operation. Instead, INITs cause VM exits"* — **Exact match.**
5. **Vol. 3C §34.5.1 "Initial SMM Execution Environment" and §34.14.2 "Default Treatment of RSM"** (`kernel-interface.md:1265`, `:2244`): Chapter 34 SMM section numbers and verbatim phrases (*"are inhibited when the processor enters SMM"*; *"blocked after RSM if and only if the logical processor will be in VMX root operation"*) match `325462-093`. — **Exact match.**
6. **Cross-checks in `kernel.md`** (`kernel.md:128, :130, :131`): `§2.5` (`CR0.WP` cannot be cleared while `CR4.CET` is set), Vol. 4 `Table 2-46` (`IA32_PKRS` listed in 12th/13th gen MSR table), and `CPUID.07H.01H:EDX.CET_SSS[bit 18]` + `WRSSD/WRSSQ` (`IA32_S_CET.SH_STK_EN` and `WR_SHSTK_EN`) match `325462-093`. — **Exact match.**

---

## Not checked
- The Rust reference model and `abi/` crate on `dodos-kernel` branch `model` were not executed or inspected.
- External ARM64 (`Arm DDI 0487 K.a`, `Arm IHI 0069`, `Arm DEN 0022E`, `Arm DEN 0054C`, TF-A `v2.12.0`) and RISC-V (`AIA`, `SBI HSM`, `Sdtrig`) citations beyond SDM `325462-093` were not re-fetched in this review.
- The known defect excluded by the brief was not investigated or reported.
