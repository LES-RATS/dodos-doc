# Verification of contract review 11 (Mistral) and independent attack on pass 18

Independent verification of [Mistral's eleventh contract review](2026-11-17-contract-review-11-mistral.md) against pass 18 of [architecture/kernel-interface.md](../architecture/kernel-interface.md) (commit `74011e1`, 2,284 lines), [architecture/kernel.md](../architecture/kernel.md) (227 lines), and [decisions/README.md](../decisions/README.md) (D-128 to D-136), followed by an independent attack on the new and rewritten designs of pass 18. Written 17 November 2026. Nothing else in any repository was modified.

Line-count note: [Mistral's review](2026-11-17-contract-review-11-mistral.md#L4) states that `kernel-interface.md` has `"2,285 lines"`; the file at `74011e1` has **2,284** lines.

---

## Part A: Verification of Mistral's review

Mistral raised four findings (one medium, three low) and explicitly cleared six areas under *"What I checked and found correct"*. All four of Mistral's findings point to real defects (one `confirmed in part`, three `confirmed`), though Mistral missed a critical mathematical bug in Finding 2 that it copied into its own correction, distorted a quote and gave an ambiguous correction in Finding 3, and missed timestamp expiration after debugger release in Finding 4. In addition, Mistral's clearance of the quiet word (Attack 1), *"writes nothing before its last try"* (Attack 2), and G9 (Attack 5) is false: Part B breaks all three, including two **critical** IOMMU containment bypasses under G9.

### Finding 1 — Arm DDI 0487 citation at `kernel-interface.md:328`

**Verdict: `confirmed in part`.**

#### Quote and line-number check

[kernel-interface.md:328](../architecture/kernel-interface.md#L328) states verbatim:

> "(`TLBI VAE1IS` for a range, `TLBI ASIDE1IS` for a tag; when the kernel runs at EL2 with `HCR_EL2.{E2H, TGE}` = {1, 1} the same instructions act on the EL2&0 translation regime: Arm DDI 0487, C5.5.60), completed by `DSB ISH`. \"The invalidation applies to all PEs in the same Inner Shareable shareability domain as the PE that executes this System instruction\" ([Arm's description of `TLBI ASIDE1IS`](https://df.lth.se/~getz/ARM/SysReg/AArch64-tlbi-aside1is.html), the mirror [kernel.md](kernel.md#the-write-gate-mechanisms) cites), and a TLBI effect is complete once a DSB follows it (Arm DDI 0487, B2.3, \"TLBI Effects, Completed TLBI Effects and Invalidation Scopes\")."

Mistral's quote at lines 18–19 matches `kernel-interface.md:328`.

#### What is confirmed vs. refuted

- **Confirmed:**
  1. `C5.5.60` in Arm DDI 0487 M.d documents only `TLBI VAE1IS`; `TLBI ASIDE1IS` is in **`C5.5.11`**. Putting `(Arm DDI 0487, C5.5.60)` at the end of the parenthetical covering both instructions leaves `TLBI ASIDE1IS` mis-cited.
  2. Pointing to `B2.3` omits the `.1` subsection number (`B2.3` is the chapter-level heading *"Ordering requirements defined by the formal concurrency model"*), and the normative architectural rules for completion by `DSB` and Inner Shareable broadcast scope belong to **`D8.17.8`** (*"Ordering and completion of TLB maintenance instructions"*) and **`D8.17.7`** (*"Broadcast TLB maintenance"*).
- **Refuted in Mistral:**
  1. Mistral claims ([lines 24–26](2026-11-17-contract-review-11-mistral.md#L24-L26)): *"No section titled 'TLBI Effects, Completed TLBI Effects and Invalidation Scopes' exists anywhere in M.d's table of contents (the full TOC of the M.d issue was searched: zero matches for 'TLBI Effects', 'Completed TLBI', 'Invalidation scope')."* That inference from a TOC grep is wrong: **"TLBI Effects, Completed TLBI Effects and Invalidation Scopes"** is a verbatim inline subheading inside **`B2.3.1`** (*"Basic definitions"*, under `B2.3`), which defines `TLBI Effect` and `Completed TLBI Effect` (*"appears in program order before a DSB FULL Effect"*). Inline unnumbered subheadings do not appear in the PDF table of contents. The contract author copied the subheading verbatim and dropped `.1` from `B2.3.1`, rather than fabricating a title.
  2. Mistral claims ([lines 29–31](2026-11-17-contract-review-11-mistral.md#L29-L31)) that `B2.3` *"contradicts the decision it cites"* because [decisions/README.md:145](../decisions/README.md#L145) (D-135 item 11) names `D8.17 and D8.17.1`. D-135 item 11 refers to the two lines directly below (`333`, rule IWZCBG in `D8.17`, and `334`, break-before-make in `D8.17.1`), not to line `328`.

#### Judgement on Mistral's correction

Acceptable (with optional retention of `B2.3.1`). Replace `(Arm DDI 0487, C5.5.60)` with `(Arm DDI 0487, C5.5.60 for TLBI VAE1IS, C5.5.11 for TLBI ASIDE1IS)` and replace `(Arm DDI 0487, B2.3, "TLBI Effects, Completed TLBI Effects and Invalidation Scopes")` with `(Arm DDI 0487, D8.17.8; broadcast scope in D8.17.7; formal definition in B2.3.1)`.

---

### Finding 2 — `CORE_ANSWER_NS` start-up check at `kernel-interface.md:671` and `1489`

**Verdict: `confirmed` (and both `kernel-interface.md:658` and Mistral's correction contain an unsolvable recursive bound).**

#### Quote and line-number check

All quotes in Mistral lines 51–69 and 77–78 match [kernel-interface.md:671](../architecture/kernel-interface.md#L671), [`664`](../architecture/kernel-interface.md#L664), [`667`](../architecture/kernel-interface.md#L667), [`668`](../architecture/kernel-interface.md#L668), [`658`](../architecture/kernel-interface.md#L658), and [`1489`](../architecture/kernel-interface.md#L1489) verbatim.

#### Step-by-step scenario replay

Suppose `N = 64` (`CORES_PER_KERNEL_MAX`, [`1480`](../architecture/kernel-interface.md#L1480)), variant L2 is compiled, and the boot image configures `CORE_ANSWER_NS = 10 ms` with L1 worst-case hold `H = 100 µs` (`(N - 1) * H = 6.3 ms < 10 ms`, so the start-up check at lines `671` and `1489` passes).

1. Under L2, a step of `task_revoke` takes up to `k = 136` locks (`4 * 32 + 8`, [`662`](../architecture/kernel-interface.md#L662)), and a step of removal takes up to `k = 392` locks (`4 * (32 + 64) + 8`, [`662`](../architecture/kernel-interface.md#L662)). Even with a tiny object-lock hold `h = 1 µs`, the L2 lock-wait bound at [`667`](../architecture/kernel-interface.md#L667) (`2 * k * (N - 1) * h`) reaches `2 * 136 * 63 * 1 µs = 17.136 ms` for `task_revoke` and `49.392 ms` for a removal step—already above `CORE_ANSWER_NS = 10 ms`.
2. Even under L1, [`670`](../architecture/kernel-interface.md#L670) bounds a core invalidation request by `N * H` (plus interrupt delivery), which exceeds `(N - 1) * H` at line `671`.
3. Under L2, `k` concurrent escalations serialize in the `quiet_word` ticket queue while a core waiting at kernel entry spins on `quiet_word` with `entry_word = 0`. If `N - 1 = 63` escalated calls precede it (each say `300 µs` plus an initial drain `E`), the core waits ~`20 ms > 10 ms` on `quiet_word`.
4. By [`658`](../architecture/kernel-interface.md#L658) and [`671`](../architecture/kernel-interface.md#L671), the waiting healthy core writes `panic` (evidence `self`, reason 9 at [`1589`](../architecture/kernel-interface.md#L1589)), and the entire healthy node is fenced and reclaimed.

#### Critical flaw in both `kernel-interface.md:658` and Mistral's correction

Mistral missed that the contract's own formula for the bound of an escalated call at [`kernel-interface.md:658`](../architecture/kernel-interface.md#L658) is mathematically undefined, and copied that exact divergence into its own replacement formula:

- [`kernel-interface.md:658`](../architecture/kernel-interface.md#L658) writes: *"Bound of an escalated call: its one-core bound, plus E, the longest kernel event of another core of the node (the others end theirs in parallel), plus the escalated calls ahead of it in the queue of the word, at most N − 1, each of the same bound."* Let $B_{\text{esc}}$ denote that bound and $B_1$ the one-core bound. The sentence states:
  $$B_{\text{esc}} = B_1 + E + (N - 1) B_{\text{esc}}$$
  For any $N \ge 2$, $(2 - N) B_{\text{esc}} = B_1 + E$, which has **no finite positive solution** (at $N = 2$, $0 = B_1 + E$; at $N > 2$, $B_{\text{esc}} < 0$).
- Mistral reproduces this divergence verbatim at [line 72](2026-11-17-contract-review-11-mistral.md#L72) and embeds it in its proposed start-up check at [lines 103–104](2026-11-17-contract-review-11-mistral.md#L103-L104): `(N − 1) × (one-core bound + E + (N − 1) × the escalated bound)`, which no boot image can compute or pass. Mistral's alternative (`"scope the sentence at line 671 to L1"`) silently abandons the no-false-self-accusation guarantee for every L2 image.

Why the true bound is finite: an escalated call takes locks only once no other core is inside a kernel event (*"runs the call alone"*, [`658`](../architecture/kernel-interface.md#L658)), so once a core reaches the head of the `quiet_word` queue it executes in its **one-core bound** $B_1$ (with zero lock contention and zero nested `again`). Furthermore, only the **first** escalator in a back-to-back busy period waits `+ E` to drain non-escalating cores already in kernel events; every core arriving afterward blocks at kernel entry with `entry_word = 0`, and any other core that was already spinning on the ticket lock already has `entry_word = 0` (`"and while it waits for the quiet word"`, [`658`](../architecture/kernel-interface.md#L658)). Therefore, an escalated call (and any core entering the kernel behind at most $N - 1$ escalations) waits at most:
$$E + (N - 1) \times B_{1,\max}$$
(Waiters behind $m \le N - 1$ queued escalations observe at most one initial drain $E$ plus at most $m$ single-core executions $B_{1,\max}$ ahead of them, plus one $B_1$ of their own if escalated; even conservatively counting $E$ once per queued escalator yields at most $(N - 1) \times (B_{1,\max} + E)$, never $(N - 1) \times B_{\text{esc}}$.)

#### Exact replacement text

1. At [`658`](../architecture/kernel-interface.md#L658), replace `"Bound of an escalated call: its one-core bound, plus E, the longest kernel event of another core of the node (the others end theirs in parallel), plus the escalated calls ahead of it in the queue of the word, at most N − 1, each of the same bound."` with:
   `"Bound of an escalated call: once it holds the quiet word and waits for the node's other cores to leave their current events (at most E, the longest kernel event of another core, once at the start of an unbroken run of escalations, since waiting cores keep their entry word 0), it runs in its one-core bound with no contention; behind at most N − 1 escalated calls ahead of it in the queue, its bound is its one-core bound + E + (N − 1) × B_1_max, where B_1_max is the longest one-core bound of any call."`
2. At [`671`](../architecture/kernel-interface.md#L671) and [`1489`](../architecture/kernel-interface.md#L1489), require `CORE_ANSWER_NS` at machine start-up to exceed:
   - under L1: `N × H + IPI_DELIVERY_MAX` (covering `N * H` + IPI for invalidation requests in [`670`](../architecture/kernel-interface.md#L670), not `(N - 1) * H`);
   - under L2: `max(2 × k_max × (N − 1) × h, E + (N − 1) × B_1_max, E + k_max × (N − 1) × h + IPI_DELIVERY_MAX + quiet_wait)`, where `k_max = 4 × (32 + 64) + 8 = 392` (or `k_max` for the image's calls, with `IPI_DELIVERY_MAX` and `B_1_max` measured alongside `H`, `h`, and `E`).

---

### Finding 3 — Sealed state: sweep vs. `seal` evidence at `kernel-interface.md:1275, 1278`

**Verdict: `confirmed` (with quote distortion and an ambiguous correction in Mistral).**

#### Quote and line-number check

- [`kernel-interface.md:1275`](../architecture/kernel-interface.md#L1275) matches Mistral lines 111–112 verbatim.
- [`kernel-interface.md:1278`](../architecture/kernel-interface.md#L1278) actually reads:
  > "every live or sealing node also observes its two successors **among the nodes that are starting, live or sealing**, in cyclic index order, every `SWEEP_NS`, at a due event of its first core's timer queue, which it arms every `SWEEP_NS` while it is live or sealing (D-135); the sweep observes the first core of each successor. A sealed node is never observed for stale evidence, by the sweep or by a waiting thread, since it does not beat; only the evidence kill, retire and seal can accuse it."
  Mistral ([lines 117–119](2026-11-17-contract-review-11-mistral.md#L117-L119)) writes: `"A sealed node is **never observed … by the sweep** … only the evidence kill, retire and seal can accuse it."` Eliding `"for stale evidence"` makes the text look more self-contradictory on its face than it is; the real bug is in the preceding sentence, which defines the sweep's target set as `"among the nodes that are starting, live or sealing"`.
- A secondary inconsistency Mistral missed: [`1243`](../architecture/kernel-interface.md#L1243) and [`1252`](../architecture/kernel-interface.md#L1252) allow **any live or sealing node** to accuse with valid evidence (which includes `seal`), whereas [`1275`](../architecture/kernel-interface.md#L1275) restricts `Who looks` to `"Any live node; the sweep"`.

#### Step-by-step scenario replay

1. Node *X* holds no unit roles, receives no messages, has no waiters, and holds no remote mappings or granted frames anyone currently revokes—it still occupies its cores and ordinary chunks (`1253`).
2. *X* calls `node_stop` mode 1 (`1240–1241, 1408`), writes its `seal` instant into its node beacon (`1261`), and enters `sealed`.
3. Every `SWEEP_NS`, each live or sealing node scans only *"among the nodes that are starting, live or sealing"* (`1278`), skipping *X*. No thread waits for *X* (`1277`).
4. Even after `now - seal_instant > SEAL_NS`, nobody checks *X*'s `seal` instant. `SEAL_NS` (`1488`: *"Time a node may stay sealed before evidence seal accuses it"*) fails to hold; *X*'s cores and memory stay held indefinitely until reboot or an unrelated `node_stop` kill.

#### Flaw in Mistral's correction

Mistral's proposed addition ([lines 147–149](2026-11-17-contract-review-11-mistral.md#L147-L149)) — `"the sweep also reads the seal instant of a successor that is sealed, and accuses it with evidence seal once it is older than SEAL_NS"` — leaves *"a successor that is sealed"* ambiguous:
- If `sealed` nodes count toward *"its two successors"*, two consecutive `sealed` nodes in cyclic index order consume both slots, leaving every `starting`/`live`/`sealing` node behind them unobserved by that sweeper (breaking the 2-successor failure-tolerance bound for `stale`).
- If `sealed` nodes do not count toward the two `stale` successors, *"every sealed successor encountered on the way"* can force one sweep tick on a 1,024-node machine with 1,020 sealed nodes to scan $O(n)$ beacons inside one event, violating constant-work bounds.

#### Exact replacement text

1. At [`1278`](../architecture/kernel-interface.md#L1278), replace `"every live or sealing node also observes its two successors among the nodes that are starting, live or sealing, in cyclic index order, every SWEEP_NS ..."` with:
   `"every live or sealing node also observes, every SWEEP_NS at a due event of its first core's timer queue (armed while it is live or sealing), the first core of its two successors among the nodes that are starting, live or sealing (for stale), and reads the seal instant of its two successors among the nodes that are sealed (for seal), both in cyclic index order."`
   This keeps `O(1)` work per sweep (at most 4 successors checked) and guarantees every `sealed` node is accused within `SWEEP_NS + SEAL_NS` while keeping `stale` coverage across 2 live/sealing/starting successors.
2. At [`1275`](../architecture/kernel-interface.md#L1275), align `Who looks` with [`1243`](../architecture/kernel-interface.md#L1243) and [`1252`](../architecture/kernel-interface.md#L1252): `"Any live or sealing node; the sweep"`.

---

### Finding 4 — Debugger stop & `release word` at `kernel-interface.md:1639`

**Verdict: `confirmed` (and Mistral missed a separate timestamp-aging bug on `seal`, `FenceRecord`, and `invalidation_request` instants after gdb releases).**

#### Quote and line-number check

Mistral's quotes at lines 156–162 and 170–173 match [`kernel-interface.md:1639`](../architecture/kernel-interface.md#L1639) and [`1272`](../architecture/kernel-interface.md#L1272) verbatim; [`1279`](../architecture/kernel-interface.md#L1279) and [`1338`](../architecture/kernel-interface.md#L1338) match as cited.

#### Step-by-step scenario replay (extending Mistral)

1. A development image breaks into the stub on node *X*, raising the `release word` (`1639`). Suppose one core *p* of another node *Y* fails to stop within 10 ms (`"shown to gdb as running"`).
2. **Stuck observation & non-suspended paths (Mistral's case):** Because [`1639`](../architecture/kernel-interface.md#L1639) suspends only *"a wait, a due event or a step of a fence"*, *p*'s syscalls (`node_send` to *X*), interrupt arrivals (user-ring / console / IPI handlers), and non-fence recovery-reserve steps (`R0–R6`, unit rebuilds, kernel-ring drains, [`1338`](../architecture/kernel-interface.md#L1338)) keep executing. `node_send` calls the gate, which records a `stuck` observation against *X* (`1272`, `1279` has no `release word` guard). `STUCK_NS` and `STALE_NS` are omitted from `CORE_ANSWER_NS, FENCE_NS and SEAL_NS` (`1639`). If *p* enters a non-suspended path that checks `stuck` while the stop lasts > `STUCK_NS`, or if *p* enters `stuck` check right before the stub clears observations, *Y* accuses *X*.
3. **Missed post-release bug (stored timestamps outside `observations[8]`):**
   Even if all cores stop cleanly for gdb, clearing `"every open observation of every node beacon"` (`1639`) only resets `observations[8]` (`1261`). It does **not** adjust timestamps stored elsewhere in beacons or the living/node tables:
   - **Sealed node killed immediately on gdb release:** Suppose node *X* is `sealed` with `seal_instant = T0` in its node beacon (`1261`, `1275`), and `SEAL_NS` is configured to `10 ms`–`1 s` (`1488`). A developer stops at gdb for 30 s (`now` at release is `T0 + 30 s`; the monotonic `clock` continues running—only `CORE_ANSWER_NS, FENCE_NS and SEAL_NS` were said not to be measured while stopped). Before release, the stub clears `observations[8]`, leaving `X.seal_instant = T0`. On the very first sweep after release, a peer reads `now - T0 = 30 s > SEAL_NS` and immediately accuses *X* with evidence `seal` before `node_start` resume can run!
   - **Active `FenceRecord` / `invalidation_request` instants:** [`1285`](../architecture/kernel-interface.md#L1285) stores raw gate instants in `FenceRecord` (word 1 `first fence action`, word 2 `confirmed`, words 4–67 `last stop`), and [`329`](../architecture/kernel-interface.md#L329) stores `start` in `invalidation_request`. Neither is shifted on release, so *"its time counted from then"* (`1639`) only works if the paused interval is accounted for (either by shifting the `clock` / recording cumulative stub-paused nanoseconds subtracted from membership/clock reads, or by shifting all open instants on release). Notice `474` already solves the exact same problem for whole-machine suspend by freezing the monotonic clock (`ns_base` adjusted under the sequence word); pausing `ns_base` (or maintaining `paused_ns` in development builds) freezes **all** five membership timeouts (`STALE_NS`, `STUCK_NS`, `CORE_ANSWER_NS`, `FENCE_NS`, `SEAL_NS`) and `IOMMU_WAIT_NS` at once with zero residual timestamp drift!

#### Flaw in Mistral's Option 1 and exact replacement text

Mistral's Option 1 ([lines 190–191](2026-11-17-contract-review-11-mistral.md#L190-L191)) adds *"a step of the recovery reserve and an arrival"* to the suspend list, which still allows `node_send` (a syscall on a non-stopped core) to append a `stuck` observation and allows a `node_stop` / syscall path to inspect `seal` or observations. Neither Option 1 nor Option 2 fixes the `seal_instant` / `FenceRecord` / `invalidation_request` timestamp gap across release.

**Exact replacement at [`1639`](../architecture/kernel-interface.md#L1639)** (and [`1279`](../architecture/kernel-interface.md#L1279)):
- In [`1639`](../architecture/kernel-interface.md#L1639): *"While the release word is raised, no core records an observation and no core makes an accusation (`CORE_ANSWER_NS`, `FENCE_NS`, `SEAL_NS`, `STALE_NS` and `STUCK_NS` do not advance); in a development image, the stub measures the duration of the stop and, before clearing the release word, clears every open observation and advances `ns_base` back (or advances every node's `seal` instant, open `FenceRecord` instants, active `invalidation_request` start instants and `idle_until` values by the stop duration, so the monotonic `clock` either excludes stub stops like whole-machine suspend or every stored membership/wait deadline shifts by the stop duration). Any call (gate accusation included), due event, interrupt handler or recovery-reserve step that reads the release word raised refuses accusations/observations and waits for release before timing out any wait, fence, or seal."*
- In [`1279`](../architecture/kernel-interface.md#L1279): append `"; in a development image, the gate writes no observation while the release word is raised."`

---

## Part B: Independent attacks on pass 18

### B.1. The quiet word (`657–660, 664–671, 524, 552, 759–764, 778, 1481–1489`)

Mistral cleared the quiet word in Attack 1 ([lines 196–224](2026-11-17-contract-review-11-mistral.md#L196-L224)), concluding *"no deadlock or livelock found ... nothing is lost or delivered twice ... no shared-line write"*. Every one of the four attacks below breaks that clearance.

#### B.1.1. [High] Missing `StoreLoad` barrier on `entry_word` / `quiet_word` and `entry_word` / `untyped_retype` breaks mutual exclusion (`657, 658`)

[`kernel-interface.md:658`](../architecture/kernel-interface.md#L658) specifies:

> "Every core reads the quiet word when it enters the kernel for a call or an event, after it has written its entry word: if another core holds it, the core writes its entry word 0, waits until the word is clear and enters again, and it takes no lock before. ... **The entry word** of each core, in its part of the node block, holds the kernel epoch the core read when it entered its current kernel event, and 0 outside one and while it waits for the quiet word: one write to the core's own line at each entry and at each exit and one read of the epoch, a word written only at an escalation and at the last destruction of an untyped, so nothing on a memory access."

Mistral praised this ([lines 221–224](2026-11-17-contract-review-11-mistral.md#L221-L224)) without noticing the textbook Dekker / store-buffer reordering on x86-TSO, ARMv8, and RISC-V RVWMO:

**Step-by-step trace:**
1. Initial state: `kernel_epoch = E`, `quiet_word` free, Core 1 is in user space (`entry_word[1] = 0`).
2. **Core 0** escalates: it acquires `quiet_word`, writes `kernel_epoch = E + 1` (store), and then reads `entry_word[1]` (load). Without a `StoreLoad` barrier (`MFENCE` / locked RMW on x86-64, `DMB ISH` on ARM64, `fence rw, rw` on RISC-V) between writing `kernel_epoch` and reading `entry_word[1]`, Core 0 can observe `entry_word[1] == 0` while its store to `kernel_epoch` is still buffered (or before Core 1's store buffer drains).
3. Simultaneously, **Core 1** enters the kernel: it reads `kernel_epoch` (`E`, or even `E + 1` if reordered), writes `entry_word[1] = E` (store sitting in Core 1's store buffer), and reads `quiet_word` (load) **before** `entry_word[1]` becomes visible to Core 0! On x86-TSO, `MOV [entry_word], rax; MOV rbx, [quiet_word]` legally reorders the load ahead of the buffered store; Core 1 reads `quiet_word == 0` (old value).
4. **Result:** Core 0 concludes every other core is outside the kernel and *"runs the call alone, taking its locks in the order (no try can fail and no link can change, since no other core is in a kernel event)"* (`658`), while Core 1 simultaneously enters a kernel event and acquires the very same L2 object locks or mutates links Core 0 assumes are frozen.
5. **Symmetric race for [`657`](../architecture/kernel-interface.md#L657) (`untyped_retype` watermark return):** Destroying core writes `kernel_epoch = E + 1` and stores it in word 6; Core 0 runs `untyped_retype`, reads `entry_word[1] == 0`, and reuses the slab memory while Core 1 has just entered (with `entry_word[1] = E` still in its store buffer) and reads a stale pointer to that object before its lock acquisition!
6. **Consequence:** Every single kernel entry (even in an L2 node that never escalates!) **must execute a full `StoreLoad` memory barrier** (`MFENCE` or locked RMW on x86-64, `DMB ISH` on ARM64, `fence rw, rw` on RISC-V) between writing `entry_word` and reading `quiet_word` (and symmetrically on the escalator/`untyped_retype` side between writing `kernel_epoch` and reading `entry_word[*]`), directly contradicting the claim that entry costs only `"one write to the core's own line ... and one read"` and adding an unmeasured barrier to every fast-path syscall and interrupt.

#### B.1.2. [High] Arrival steps 1–2 while waiting on `quiet_word` without `core_lock` lose IRQs, break `irq_ack`, storm level lines, and cannot run IOAPIC `op 5` (`658, 759–764, 778, 1769`)

[`kernel-interface.md:658`](../architecture/kernel-interface.md#L658) specifies:

> "An interrupt that arrives on such a core is acknowledged at the controller, a level source masked first (steps 1 and 2 of [an arrival](#interrupts), which take no lock), and the rest of the arrival, its signal included, is done once the word is clear: that signal sets its bits under the core's lock, which a core that waits for the quiet word must not take."

Mistral asserted ([lines 210–213](2026-11-17-contract-review-11-mistral.md#L210-L213)): *"nothing is lost or delivered twice, since the irq states' pending bit and masking rules are unchanged."* This fails in four concrete ways:

1. **No storage defined for deferred arrivals (and loss of multiple edge vectors):** Neither [`658`](../architecture/kernel-interface.md#L658), [`1502`](../architecture/kernel-interface.md#L1502) (*"What each node keeps"*), nor [`1769`](../architecture/kernel-interface.md#L1769) (*"Since D-135"*) adds a per-core deferred-vector bitmap (`[u64; 4]` for 256 vectors). Worse, step 2 issues hardware End-Of-Interrupt (clearing the local APIC ISR / GIC active bit / IMSIC pending bit), destroying hardware latching of which vector(s) fired; if the core does not record each deferred vector in a per-core bitmap during the up-to-`CORE_ANSWER_NS` spin, edge interrupts from different devices arriving during the spin overwrite or lose each other completely.
2. **Broken `irq_ack` while a level IRQ is deferred:** Under [`648`](../architecture/kernel-interface.md#L648), `irq_ack`, `irq_bind`, and `irq` removal run from **any** core under `core_lock[A]`. Suppose Core *A* is spinning on `quiet_word`, receives level vector *V* (bound to `irq` *I*, state `armed`), masks *V* in step 1, and EOIs in step 2. *I*'s software state is **still `armed`** because step 3 was deferred! While Core *A* still waits (or after `quiet_word` clears before Core *A* acquires `core_lock[A]`), a driver on Core *B* calls `irq_ack(I)`. By [`757`](../architecture/kernel-interface.md#L757), `"On an armed irq it succeeds and does nothing"`—it does **not** unmask the controller, leaving a missed edge or masked level line stuck masked even after the driver ACKed.
3. **Cross-core `irq_bind` / destroy race violates `751` and causes an interrupt storm:**
   - **Step 1:** Vector *V* (level `irq` *I*, `armed`, bound to `notify` *N1*) arrives on Core *A* while Core *A* spins on `quiet_word`. Core *A* masks *V* (step 1), sends EOI (step 2), remembers *"run step 3 for vector V"*, and returns to spinning on `quiet_word` with `core_lock[A]` **not held**.
   - **Step 2:** `quiet_word` clears. Before Core *A* wins `core_lock[A]` to run deferred step 3 for *V*, Core *C* wins `core_lock[A]` and either:
     - *(Case a)* calls `irq_bind(I, 0)` then `irq_bind(I, N2)` (`756`): Core *C* sets *I* back to `armed` (bound to *N2*) and **unmasks** *V* at the controller! Or
     - *(Case b)* destroys *I* (`774`) and calls `irq_claim(..., V)` + `irq_bind(I2, N2)`, creating a **brand-new** `irq` *I2* on vector *V*, state `armed`, and **unmasked** at the controller!
   - **Step 3:** Core *A* now acquires `core_lock[A]` and runs deferred step 3 (`763`): *"If the irq is armed, it becomes fired and the notify is signalled"*. Core *A* reads `armed`, sends a phantom signal to *N2* (for the new driver/binding that arrived *after* the interrupt!), and sets *I*/*I2* to `fired` **while the level source remains UNMASKED at the controller**—directly violating [`751`](../architecture/kernel-interface.md#L751) (*"A level source is masked at the controller while the irq is idle or fired"*). Worse, if Core *A* never masks it again in step 3, an asserted level line fires continuously onto Core *A* with `irq` in state `fired`, causing an infinite interrupt storm!
4. **Step 1 on x86-64 without an IOAPIC EOI register cannot be lock-free (`778`):** [`778`](../architecture/kernel-interface.md#L778) states that when the IOAPIC has no EOI register (or broadcast EOI suppression is unavailable), *"the masking and unmasking of a level line are requests to the role holder"*. Issuing `UnitRequest` op 5 (`1010, 1024`) writes the shared unit request table, writes the kernel ring, and updates credits / sends an IPI through the gate lock—none of which can run in step 1 *"which take no lock"* (`658`) while `quiet_word` is held!

#### B.1.3. [High] Divergent escalated bound (`658`), omitted quiet-word terms in invalidation latency (`670`), and admission/budget break (`524, 552`)

1. **Divergent recursion in `658`:** As proved under Part A Finding 2, [`658`](../architecture/kernel-interface.md#L658) writes $B_{\text{esc}} = B_1 + E + (N - 1) B_{\text{esc}}$, which diverges for every $N \ge 2$. The actual closed bound is $B_1 + E + (N - 1) B_{1,\max}$.
2. **Omitted quiet-word wait in [`670`](../architecture/kernel-interface.md#L670):** Line `670` states that a core invalidation request lasts *"at most N × H (L1) or one event plus k × (N − 1) × h (L2), plus the delivery of one interrupt"*. Under L2 (`668`), both the asked core entering the interrupt handler and the completing core (if it exits and re-enters or triggers a second event) can block at kernel entry on `quiet_word` for up to $(N - 1) B_{1,\max} + E$.
3. **Admission and budget inversion (`524, 552, 658`):** [`658`](../architecture/kernel-interface.md#L658) claims the quiet-word wait is *"a term of ... the time admission leaves free on each core"*, yet [`524`](../architecture/kernel-interface.md#L524) admits contexts up to $2^{32}$ (**100%** of a core, leaving 0 free slack!). Moreover, [`552`](../architecture/kernel-interface.md#L552) charges all kernel time of an event—including spinning on `quiet_word` for *another* core's escalation—to whichever thread happened to be running on the waiting core at entry, draining an innocent frame-class context's budget (`r`) via contention initiated by another core.

#### B.1.4. [Medium] Ticket-lock state bug (`658`) and parameter inversion (`CORE_ANSWER_NS > STALE_NS`, `1481, 1489`)

1. **Ticket lock corruption on `"clears the word"`:** [`658`](../architecture/kernel-interface.md#L658) calls `quiet_word` *"a ticket lock taken by compare-and-swap, so that the cores that wait for it are served in the order they came"* and then states that the holder *"clears the word"*. Zeroing a ticket lock `(next_ticket, now_serving)` while Core 2 already took ticket $t+1$ and Core 3 later takes ticket $0$ corrupts the queue and admits two escalators at once. The lock must use `next_ticket` + `now_serving` (held iff `next_ticket != now_serving`, released by incrementing `now_serving`), with `quiet_word` cleared to *"free"* only conceptually (waiting until `next_ticket == now_serving` or observing `now_serving == my_ticket`).
2. **Parameter range inversion (`1481, 1489`):** [`1489`](../architecture/kernel-interface.md#L1489) allows `CORE_ANSWER_NS` up to **100 ms**, while [`1481`](../architecture/kernel-interface.md#L1481) allows `STALE_NS` down to **10 ms**. If `CORE_ANSWER_NS = 50 ms` and `STALE_NS = 10 ms`, a healthy 30 ms quiet-word wait on Core 0 (never mind an escalated wait) stalls Core 0's `heartbeat` past `STALE_NS = 10 ms` and causes a healthy peer to accuse and fence the entire node as `stale` (`1278`).

---

### B.2. `"A call writes nothing before its last try has succeeded"` (`652–656, 662, 128–129, 203, 402–406, 585–591, 1110–1113, 1121–1130`)

Mistral cleared this invariant in Attack 2 ([lines 226–237](2026-11-17-contract-review-11-mistral.md#L226-L237)): *"I walked the list and found no call that must write before a try."* That walk missed five violations and contradictions.

#### B.2.1. [High] Missing `task (2)` and `thread (3)` locks for IPC mark propagation (`656` vs. `1110–1113`) and missing `reply`/`thread` locks for lend-chain release (`203, 585–591`)

Under [`650`](../architecture/kernel-interface.md#L650), the L2 lock order is:
`cspace segments (1)` < `task (2)` < `thread (3)` < `endpoint (4)` < `reply (5)` < `notify (6)` < `timer (7)` < `sched (8)` < `aspace (9)` < `iospace (10)` < `cores (11)` < `gate (12)`.

By [`653`](../architecture/kernel-interface.md#L653), an `endpoint` or `reply` lock guards **only** a waiting thread's wait state, queue links, result, and message words—NOT `task.marks`, `task_attach`, `task_mark`, or `thread.own_marks`! Yet [`1110–1113`](../architecture/kernel-interface.md#L1110-L1113) require every IPC delivery (`call`, `send`, `reply_recv`, answer `send`, and fault delivery) to read `sender`'s effective marks at delivery (`1110`), OR them into `receiver.task` (or `receiver.thread` if detached) (`1112`), and—if $\ge 1$ capability transfers without `caps_dropped`—OR `receiver`'s pre-delivery marks into **`sender`'s `task` or `thread`** (`1113`).

- **Missing tries in [`656`](../architecture/kernel-interface.md#L656):**
  - `call` / `send` on `endpoint (4)` discovers the waiting `receiver` from the queue and must **try** `receiver.task (2)` (or `receiver.thread (3)` if detached) AND, if sending capabilities, must lock or **try** `sender.task (2)` / `sender.thread (3)` (and `receiver`'s `task`/`thread` may be the same or different object!).
  - `send` / `reply_recv` answering on `reply (5)` discovers the waiting `caller` inside the `reply` object (`653`) and must **try** `caller.task (2)` / `caller.thread (3)` (and `sender.task`/`thread` if sending caps).
  - `recv` / `reply_recv` on `endpoint (4)` discovers the queued `caller` and must **try** `caller.task (2)` / `caller.thread (3)` before writing either `caller`'s or `receiver`'s marks!
  - None of `task (2)` or `thread (3)` for mark propagation is listed in [`656`](../architecture/kernel-interface.md#L656).
- **Write before try in `recv` / `reply_recv` lend-chain release (`203, 585–591`):**
  [`203`](../architecture/kernel-interface.md#L203) says `recv` (and `reply_recv` after answering) first releases *"the lends of the thread and of the reply object"*, and only then checks *"the first caller in the queue"*. Under [`585–591`](../architecture/kernel-interface.md#L585-L591), releasing a lend from a `sched` chain mutates the doubly-linked `reply` neighbours (`kind 5`, which may have a lower address than the held `reply`, requiring a try omitted from [`656`](../architecture/kernel-interface.md#L656)), updates `sched (8)`, and if `reply_old` held a lend to another thread `T1`, sets `has_lost_context` on `T1` (`kind 3`, omitted from [`656`](../architecture/kernel-interface.md#L656)). Then `recv`/`reply_recv` inspects the `endpoint` queue (`kind 4`), finds a queued caller, and tries the caller's sent `cspace` segments (`kind 1`) and `caller.task` (`kind 2`)! If that try fails on both rounds and returns `again`, the call **already unlinked the lends and marked `T1`**, directly violating [`652`](../architecture/kernel-interface.md#L652) (*"the call returns `again` and has changed nothing. ... A call writes nothing before its last try has succeeded"*).

#### B.2.2. [High] Lock bound `k` overflow on `reply_recv`, `call`, `send`, and `thread_configure` (`662` vs. `656`)

[`kernel-interface.md:662`](../architecture/kernel-interface.md#L662) caps locks held simultaneously at **`k = 16`** for `call`, `reply_recv`, `send`, `node_send`, and **`k = 12`** for *"every other call"*.

Counting the locks required in Round 2 (when all tries are retaken in order and held simultaneously before the first write per [`652`](../architecture/kernel-interface.md#L652)):
- **`reply_recv` with answer + queued caller + 4 caps each way + lend chain:**
  1. Up to 4 caller `cspace` segments for answer receive range + 4 own `cspace` segments for answer capabilities (`8`).
  2. Up to 4 caller `cspace` segments for receive capabilities + 4 own `cspace` segments for receive range (`+8` = `16`, already at the limit!).
  3. Plus: own `thread` (`1`), answer caller `thread` + `task` (`2`), receive caller `thread` + `task` (`2`), own `task` (`1`), `endpoint` (`1`), `reply` + up to 2 `reply` lend-chain neighbours (`3`), up to 2 `sched` objects (`2`), core lock(s) (`2`), `gate` (`1`). Total = **28–32 locks** held at once (nearly double `k = 16`), even with deduplication of segments.
- **`call` with 4 sent caps + 4 recv slots:** up to 8 `cspace` segments + `thread`s + `task`s + `endpoint` + `reply` + `sched` + `core` + `gate` = **17–18 locks** > `k = 16`.
- **`thread_configure`** (replacing 4 bindings at once, [`389, 443`](../architecture/kernel-interface.md#L389)): `thread` (`1`) + caller `cspace` segments for arg lookup & msg page (`1–2`) + old & new `cspace` (`2`) + old & new `fault_ep` (`2`) + old & new `aspace` (`2`) + old & new list-neighbour `thread` locks in 3 lists (`3`–`6`) = **12–15 locks** > `k = 12`.

#### B.2.3. [Medium] `"the delivery of a fault"` in [`656`](../architecture/kernel-interface.md#L656) contradicts [`402`](../architecture/kernel-interface.md#L402), [`404`](../architecture/kernel-interface.md#L404), and [`654`](../architecture/kernel-interface.md#L654)

[`656`](../architecture/kernel-interface.md#L656) writes:

> "`call`, `recv`, `reply_recv`, `send` and the delivery of a fault, the segments of the receive range of the thread found (the receiver of a delivery, the caller an answer goes to) ... Each of these calls but `signal` may therefore return `again` with nothing changed under L2"

Three errors in one clause:
1. [`402`](../architecture/kernel-interface.md#L402) states `"A fault is not a call"`, and [`654`](../architecture/kernel-interface.md#L654) states `"An event that is not a call ... cannot return again"`. A fault cannot return `again` to user space!
2. [`404`](../architecture/kernel-interface.md#L404) states that a fault carries *"an empty receive range"* and [`407`](../architecture/kernel-interface.md#L407) states *"no capability, no flag"*, so a fault delivery **never** touches any receiver `cspace` segment.
3. What a fault *does* need out of order when holding `endpoint (4)` is `receiver.task (2)` / `receiver.thread (3)` for mark propagation (`1110–1112, 1116`). If that try fails, the fault cannot return `again`; it must release the endpoint, lock `task/thread -> endpoint -> sched/core` in order, and re-verify the waiter/binding like an arrival (`654`).

#### B.2.4. [High] `task_revoke` (`1121–1130`) writes before unit 1's try, takes `core`/`gate` out of order, and violates `k = 136` (`662`)

[`kernel-interface.md:1121`](../architecture/kernel-interface.md#L1121) states:

> "**The first call on a live task sets the flag revoked.** ... the first call also marks each such thread *leaving its core* and sends its core the leave interrupt ... **Each call, the first included, then detaches up to 32 attached threads**"

**Step-by-step breakage under L2:**
1. Suppose a task *T* has 500 threads, 100 of which are running on cores `1..63` when `task_revoke` is called.
2. *"marks each such thread leaving its core and sends its core the leave interrupt"*: doing this in one call scans and locks up to 500 `thread`s, up to 63 `core` locks (`kind 11`), and the `gate` (`kind 12`, G10 sends the leave IPI), far exceeding `k = 4 * 32 + 8 = 136` at [`662`](../architecture/kernel-interface.md#L662).
3. Furthermore, after setting `revoked = 1`, marking threads `leaving`, and sending leave IPIs via `gate (12)`, the call proceeds in the **same first call** (`"the first included"`, [`1125`](../architecture/kernel-interface.md#L1125)) to unit 1 of detaching up to 32 threads. Detaching a thread cancels its wait (trying `endpoint (4)` or `reply (5)` if held after `thread (3)`, or retaking in order). Since `gate (12)` and `core (11)` were taken to send leave IPIs, either `gate` is still held (violating *"the gate lock is the last lock of every order"*, [`648`](../architecture/kernel-interface.md#L648)) or, if `unit 1`'s try fails in Round 2, `task_revoke` returns `again` **after having set `revoked = 1`, marked threads `leaving`, and sent leave IPIs**—violating [`652`](../architecture/kernel-interface.md#L652) (*"a try that fails in its first unit takes the second round as any call does"*, returning `again` with nothing changed)!

#### B.2.5. [Medium] `cap_delete` / `cap_revoke` (`128–129`) mutate `dying` / `cspace.sweep` before unit 1's try succeeds

[`kernel-interface.md:128–129`](../architecture/kernel-interface.md#L128-L129) allow a step of `cap_delete` to mark a capability (and a `cspace`) `dying` on step 1, and advance `cspace.sweep` across up to 127 empty slots before reaching a capability in slot 128 whose derivation-list neighbour (`656`) lies in another segment and must be tried. If that try fails in Round 1 and Round 2, unit 1 has done 0 removals, so by [`652`](../architecture/kernel-interface.md#L652) the call must return `again` *"having changed nothing"*—yet it already mutated `dying` and `cspace.sweep`.

---
### B.3. G9 as rewritten (`1063, 1056–1059, 1016, 949, 366, 372`, D-135(12))

Mistral cleared G9 in Attack 5 ([lines 274–280](2026-11-17-contract-review-11-mistral.md#L274-L280)), echoing D-135(12) and [`kernel-interface.md:1063`](../architecture/kernel-interface.md#L1063): *"no, it does not let a node point a device at a lower-level table and reach memory it does not hold — the contract says so itself in the same sentence ('a lower table named as root still leads only to memory that G3 checked for that node, so containment holds, and only that node's device translates wrongly'), because every page of that class held by the node was G3-checked when the node took it."*

**This claim is false.** Passing a lower `iospace` table as root—together with the fact that rings are mapped plain-writable to node *X* (`949`)—produces **two independent critical IOMMU containment breaks** that let a faulty kernel on node *X* DMA-read and DMA-write **any physical address on the machine** (other nodes' memory, kernel memory, and gate pages).

Under the threat model ([`1049`](../architecture/kernel-interface.md#L1049), [`1074`](../architecture/kernel-interface.md#L1074)), containment (`1042`) must hold against *"misuse of the gate's legal interface by a corrupted kernel"*, and a ring *X* → *H* (`949`) *"is mapped writable only in X's kernel ... its writes are plain stores, not gate calls"*.

#### B.3.1. [Critical] Lower-level `*iospace table*` named as root in `UnitRequest` `op 1` lets the IOMMU walk a user-writable `*data*` page as a page table (`1063, 1056, 1016, 949`)

By [`1056`](../architecture/kernel-interface.md#L1056) (G2), all `iospace` tables—root and lower levels alike—share a single `PageClass` value `4` (`*iospace table*`). By [`1063`](../architecture/kernel-interface.md#L1063) (G9), the unit holder *H*'s gate accepts `UnitRequest` `op 1` (`1016`) whenever *"the root it names is a page of class *iospace table* held by the node that owns the device"*.

Hardware page-table formats cannot distinguish a leaf page-table entry (PTE) from a directory/root pointer (PML4E / Table descriptor):
- **Intel VT-d (revision 5.20, §9.8):** A valid 4-KB leaf second-stage PTE (`SS-PTE`) pointing to a normal writable `*data*` page *P* has `R=1` (bit 0), `W=1` (bit 1), `EMT/IPAT` (bits 6:3 — **ignored** in `SS-PML4E` / `SS-PDPTE` / `SS-PDE` when bit 7 = 0), **bit 7 = 0** (ignored in 4-KB `SS-PTE`, must be 0 in non-leaf entries), `A=1`/`D` (bits 8–9), **bit 11 = 0** (`SNP`, Reserved 0 in non-leaf entries), and bits `[HAW-1:12] = phys(P) >> 12`. Thus a valid 4-KB leaf `SS-PTE` written by G3 is **bit-for-bit valid as an `SS-PML4E`**!
- **Arm DDI 0487 M.d (§D8.3):** A VMSAv8-64 level-3 4-KB Page descriptor has `bits[1:0] = 0b11`—the exact same descriptor type encoding as a level-0, level-1, or level-2 Table descriptor!

**Step-by-step exploit:**
1. Faulty kernel *X* runs on a node owning at least one PCI device *D* (identifier word *taken* by *X*, [`354`](../architecture/kernel-interface.md#L354)) and one ordinary `*data*` page *P* (class `0`, owned by *X*). *H* (a healthy node) holds *D*'s IOMMU unit role.
2. *X* creates an `iospace` *I* and maps page *P* at 4-KB granularity via `iospace_map` (`348`) with `read` | `write`. G3 (`1057`) checks *P* (class `0` *data*, owned by *X*) and writes a valid 4-KB leaf entry pointing to `phys(P)` in *I*'s level-1 table `T1` (whose `PageClass` is `4`, `*iospace table*`).
3. *X* also maps *P* read-write in a normal `aspace` (G3 accepts *P* because it is `*data*`), and writes forged IOMMU intermediate/leaf page-table entries into *P* targeting physical address `0x...` of another node's memory, the kernel image, or the living part of the machine table (`1044–1047`).
4. *X* writes a `UnitRequest` `op 1` (`1016`: attach *D*, domain `d_X` in *X*'s domain range, `root = phys(T1)`) directly by plain stores into ring *X* → *H* (`949`). *X*'s own gate is never called!
5. *H*'s gate checks `op 1` against [`1016`](../architecture/kernel-interface.md#L1016) and [`1063`](../architecture/kernel-interface.md#L1063): *D*'s identifier word names *X*, `d_X` is in *X*'s range, and `phys(T1)` has `PageClass == 4` (`*iospace table*`) in a chunk owned by *X*. **G9 passes.** *H* writes *D*'s context entry with `SSPTPTR = phys(T1)`.
6. *D* issues DMA to virtual address `0`. The IOMMU reads `T1[0]` as a top-level `SS-PML4E`, follows `phys(P)` into ***X*-writable `*data*` page *P***, walks *X*'s forged entries inside *P* with **zero gate checks**, and DMAs arbitrarily across the entire physical address space of the machine. (Because `T1` is a valid `iospace` table page owned by *X*, even G14/R4 pass.)

#### B.3.2. [Critical] Spoofing an unattached `iospace`'s root in `op 1` + destroying that `iospace` turns a live `SSPTPTR` into writable `*data*` (`1063, 1056, 366, 949`)

Even if lower tables were rejected, G9 still breaks whenever `UnitRequest` `op 1` is written directly by *X*'s kernel (`949`) without *X*'s gate pinning the named root page:

**Step-by-step exploit:**
1. Faulty kernel *X* holds device *D* (already attached to `iospace` *I1*, so *D*'s identifier word is *taken* by *X*) and creates a second, empty `iospace` *I2* (`I2.root` has `PageClass == 4`). *I2*'s kernel header lists **0 attached devices** (`344, 367`).
2. *X* writes `UnitRequest` `op 1 (device = D, domain = d_X, root = phys(I2.root))` into ring *X* → *H* (`949`). *H* checks [`1016, 1063`](../architecture/kernel-interface.md#L1016): *D*'s identifier word names *X*, `d_X` is in *X*'s range, and `I2.root` is an `*iospace table*` owned by *X*. *H* programs `D`'s context entry `SSPTPTR = phys(I2.root)`.
3. Now *X* deletes *I2*'s root capability (`cap_delete`). *I2* has 0 attached devices in its kernel header, so [`366`](../architecture/kernel-interface.md#L366) runs no detach `UnitRequest` and [`1056`](../architecture/kernel-interface.md#L1056) (G2: *"turns back into \*data\* when the space is destroyed"*) resets `I2.root`'s `PageClass` from `4` back to `0` (`*data*`)!
4. *X* legally maps `I2.root` writable (`aspace_map`, G3 sees `*data*`), fills `I2.root` directly with forged IOMMU page-table entries pointing anywhere in physical memory, and triggers DMA from *D*. Containment (`1042`) is completely broken.

#### Required fix for B.3.1 + B.3.2

1. **Separate root/level classes for `iospace` tables (`1056, 1063`):** Encode `iospace` levels in `PageClass` exactly like CPU page tables (for instance `32 + k` for level `k = 1..L_io`, or at minimum a distinct `*iospace root*` class `5` in `PageClass::stored`), and require G9 `op 1` (`1063`) to check `PageClass == *iospace root*` (never a lower table).
2. **Prevent reverting an `iospace` root while attached in `H` (`949, 1016, 1056, 366`):** A faulty kernel *X* must not be able to tell *H* to install `phys(I2.root)` while *X* believes `I2` is unattached (or destroy `I2` while *H* points a context entry at it). Either:
   - Have *X*'s **gate** construct/validate `UnitRequest` `op 1` (e.g., maintain a per-`iospace`-root attachment/pin count or require `PageClass` transition from `*iospace root*` back to `*data*` to check that no device uses that root via gate-tracked `(unit, device, root)` state, or have *X*'s gate write a flag/pin into a living-part per-root/per-device slot checked by `op 1` and cleared only by `UnitAnswer` done for `op 2` detach or R6), **OR**
   - Keep `root` addresses out of `op 1` unless registered with *H* through *X*'s gate: e.g., when *X*'s gate sends `op 1` it transitions `PageClass(root)` to `*iospace active root*` (incrementing a gate-maintained pin count stored in `GateWord` or per-page metadata) that only `UnitAnswer(done)` on `op 2` detach (after invalidation) decrements, preventing G2 from ever reverting `root` to `*data*` while *D* may still use it.

---

### B.4. Owner word of a line (`749, 755, 774, 778, 795, 941, 1020, 1022, 1063, 1305, 1454–1455, 1769, 2067, 2071`)

#### B.4.1. [High] `irq` removal (`774, 749`) frees the line word immediately without sending IOAPIC/IOMMU `UnitRequest`s, causing a stale-claim/unmasked-line race (`1022, 1020`)

[`kernel-interface.md:774`](../architecture/kernel-interface.md#L774) states:

> "*The irq.* When its root capability is removed, it is unbound from its notify, its source is masked at the controller (on x86-64 the input of the IOAPIC is masked and the remapping entry is cleared), its pending bit is dropped and its vector can be claimed again. This is one unit of a removal step."

And [`749`](../architecture/kernel-interface.md#L749) states:

> "the removal of the `irq` writes it *free*, unclaimed"

Wait: [`778`](../architecture/kernel-interface.md#L778) and [`1063`](../architecture/kernel-interface.md#L1063) forbid node *X* from mapping the IOAPIC MMIO unless *X* holds the IOAPIC role, and [`1010, 1020`](../architecture/kernel-interface.md#L1010) require a unit request (`op 5`, plus `op 4` for IEC invalidation if remapped) to mask an IOAPIC input—which is asynchronous across the kernel ring and recovery reserve (`952, 1024`), NOT *"one unit of a removal step"*! Worse, there is no *unmapping* / *freeing* wait on an `irq` (`1024` lists `UNIT_REQUESTS` completions for `iospace_unmap`, `iospace_attach`/detach, `irq_claim` of a line, remapping writes, and `Unmapping` records—not `irq` removal!).

**Step-by-step race:**
1. On node *X* (which does not hold the IOAPIC role *H*), thread `T1` calls `irq_claim(line L, vec V1)` (`755`). *X*'s gate writes `L`'s line word `taken (*X*, g)`, writes remapping handle `H1`, and queues the sequential `UnitRequest` chain (`op 4 -> op 5 (claimed, H1)`) in `X`'s `unit request table` (`1022`).
2. Before `op 5 (claimed, H1)` reaches *H*, *X* destroys `T1` and deletes the `irq`'s root capability.
   - By [`1022`](../architecture/kernel-interface.md#L1022): *"If the waiting thread is destroyed, the later units are still asked and the redirection entry is still sent"*. So `op 4 -> op 5 (claimed, H1)` stays in flight toward *H*!
   - Meanwhile, by [`774`](../architecture/kernel-interface.md#L774) + [`749`](../architecture/kernel-interface.md#L749), removing the `irq` sets `L`'s line word to `*free*, unclaimed` in one unit, sends no `op 5 (masked)` (or sends one concurrently after), and clears `H1`'s remapping entry.
3. Immediately after step 2, another thread `T2` on *X* calls `irq_claim(line L, vec V2)` (`755`, handle `H2`). Because `L`'s line word is already `*free*, unclaimed`, `irq_claim` succeeds (`755`) and queues `op 4 -> op 5 (claimed, H2)` toward *H* (possibly even on a different `unit request table` slot, or `T2` deletes it after).
4. Both `T1`'s stale `op 5 (claimed, H1)` and `T2`'s `op 5 (claimed, H2)` pass *H*'s gate check in [`1020`](../architecture/kernel-interface.md#L1020) (*"the handle ... names a core whose word names the requester, and the line's word names the requester with its generation"*). Because the two `UnitRequest`s were sent on separate entries/epochs or raced with `irq_claim`'s `op 4 -> op 5`, *H* can process `T2`'s `op 5 (claimed, H2)` first and **`T1`'s stale `op 5 (claimed, H1)` second**, overwriting the IOAPIC RTE to point to the **deleted** handle `H1` / wrong vector while `L`'s line word belongs to `H2` (or while *X* already destroyed `H2` and expects `L` to be masked and `*free*`)!
5. The exact same stale-`op 5` corruption occurs on ARM64 (GIC distributor SPI route/enable) and RISC-V (APLIC target/enable), neither of which has an `op` number or completion path documented under `irq` removal (`1010`).

#### B.4.2. [High] `Report` (`941`) sends `two words 0` for every line, breaking IOAPIC and GIC distributor rebuilds (`1454–1455`)

[`kernel-interface.md:1454`](../architecture/kernel-interface.md#L1454) requires a unit role's successor *S* on take-over to rebuild shared interrupt controllers from node reports alone:

> "for an IOAPIC, it compares each redirection entry with the lines the live nodes report and masks the inputs nobody claims; for the GIC distributor, it rewrites the configuration of every interrupt a live node reports"

Yet [`kernel-interface.md:941`](../architecture/kernel-interface.md#L941) specifies the wire format of `Report` as:

> "then three words per item: its key, then for a device its root table and its domain number, **for a remapping handle or a line two words 0**. At most 28 items"

With `two words 0` for every line item:
1. On **x86-64 (IOAPIC)**, *S* receives **no** `(handle, vector, trigger, polarity, masked/armed)` (or `(APIC ID, vector, ...)` if unremapped) for any reported line! It cannot *"compare each redirection entry with the lines the live nodes report"*: if the dead holder left a line's RTE masked, corrupted, or pointing to an old vector/handle from before an uncompleted `op 5`, *S* has zero data to rewrite or verify it, and cannot distinguish a masked-`idle`/`fired` line from an `armed` unmasked line (`751`).
2. On **ARM64 (GIC distributor)**, *S* receives **no** `(target core/MPIDR, trigger_config, priority, enabled)` for any reported SPI/ESPI, so *S* literally cannot execute *"it rewrites the configuration of every interrupt a live node reports"* (`1454`).
3. Furthermore, [`1455`](../architecture/kernel-interface.md#L1455) justifies rebuild consistency by saying *"A node's context entries do not change during the rebuild, since attaching and detaching are requests to the holder, which keeps them until the rebuild ends"*, overlooking that `irq` removal (`774`) does **not** wait for the holder (`B.4.1`): a live node *Z* can report owning line *L* to *S*, then immediately delete its `irq` (`774`, marking `L` `*free*` locally) before *S* finishes pulling reports and programming the IOAPIC/GIC, leaving `L` unmasked in hardware while `L`'s line word reads `*free*, unclaimed`!

#### B.4.3. [Medium] `op 5 (masked)` omits generation check (`1020, 1063`) and vector requirement for edge lines (`1020`)

1. In [`1020`](../architecture/kernel-interface.md#L1020) and [`1063`](../architecture/kernel-interface.md#L1063):
   - Claimed check: *"the line's word names the requester **with its generation**"*
   - Masked check: *"the line's word is free or names the requester"* — **`with its generation` is missing** in both [`1020`](../architecture/kernel-interface.md#L1020) and G9 [`1063`](../architecture/kernel-interface.md#L1063). While a stale message from a dead generation is stopped at the ring receive check (`947`), [`1063`](../architecture/kernel-interface.md#L1063) states the gate's own invariant for every write, and leaving out the generation allows a holder gate that checks G9 directly on `UnitRequest` arguments to treat a previous dead generation's `taken` word as *"names the requester"*.
2. [`1020`](../architecture/kernel-interface.md#L1020) writes: *"and for a level line the vector of the remapping entry ('must match the Vector field programmed in the referenced IRTE', VT-d, §5.1.5.1, 'I/OxAPIC Programming')"*. VT-d §5.1.5.1 imposes this Vector-match requirement on **all** remapped I/OxAPIC redirection entries (edge and level alike), not only level lines (which additionally need the vector to match `IOAPIC_EOI` writes).

#### B.4.4. [Medium] Missing GSI/SPI/APLIC-to-line-word index map (`749, 2067, 2071`) and non-remapped / multi-arch mismatches (`749, 795`)

1. **Contiguous-index assumption vs. sparse firmware IDs (`749, 2067, 2071`):** [`749`](../architecture/kernel-interface.md#L749) states the `line words` are laid out *"in that order (on x86-64 by GSI)"*, and `StartMachine` (`2071`) publishes only `"the offset of the line words and their number"` (ignoring non-contiguous IOAPIC GSI bases/holes in `Interrupts` at `2067`, sparse ARM64 SPIs `32..1019` + ESPIs `4096..5119` = 1,984 lines vs. 5,119, and multiple RISC-V APLIC domains whose source numbers start at `1` per domain). `Interrupts` (`2067`) lists only `number of IOAPICs; then, per IOAPIC, its first GSI and its number of inputs`—it has no fields for ARM64 SPI/ESPI/LPI ranges or RISC-V APLIC domain ranges, nor any deterministic formula mapping `(domain, source)` / `(SPI/ESPI)` to a line-word index within `[0, num_line_words)`.
2. **`"in the same gate call as the remapping entry"` (`749`):** Line `749` says `irq_claim` takes the line word *"through its gate and in the same gate call as the remapping entry"*. On x86-64 without interrupt remapping (`795`), on ARM64 (GIC SPI/ESPI), and on RISC-V (APLIC), **there is no remapping entry**, leaving unclear which gate call takes the line word on those paths.
3. **Missing `APIC ID > 255` check for non-remapped IOAPIC lines (`795` vs `1020`):** [`795`](../architecture/kernel-interface.md#L795) checks `APIC ID > 255 -> unsupported` for MSIs without interrupt remapping, and [`1020`](../architecture/kernel-interface.md#L1020) passes a 32-bit `APIC ID` in `op 5` for a non-remapped line (`32-63`) even though a non-remapped IOAPIC RTE (`bits 63:56`) holds only an 8-bit physical APIC ID (`0..255`). [`795`](../architecture/kernel-interface.md#L795) omits stating that `irq_claim` of a line without interrupt remapping to a core whose APIC ID exceeds `255` returns `unsupported` (consistent with `755`).

---

## Corrections to apply, in order of severity

Every confirmed issue from Part A (with corrected replacements where Mistral's draft was flawed or incomplete) and every independent finding from Part B, merged into a single list ordered strictly by severity (`critical` → `high` → `medium` → `low`).

1. **[critical] `kernel-interface.md:1056, 1063` (plus `366, 949, 1016`) — Separate `iospace` root/level `PageClass` values and prevent reverting an attached `iospace` root (`B.3.1`, `B.3.2`)**
   - At `1056` (G2): replace `"and an iospace's tables, root included, are of class *iospace table*"` with distinct level classes in `PageClass::stored` (e.g., `32 + k` for `iospace` level `k` from `1` to `L_io`, or `4` `*iospace lower table*` and `5` `*iospace root*`).
   - At `1063` (G9): replace `"the root it names is a page of class *iospace table* held by the node that owns the device"` with `"the root it names is a page of class *iospace root* (top-level iospace table) held by the node that owns the device"`.
   - At `949, 1016, 1056, 366`: require `UnitRequest` `op 1` (attach) to be stamped/pinned by the requester's gate (or record per-root active-device pin state in the gate/living part) so that `iospace` destruction (`366`, G2) cannot revert an `iospace` root page back to `0` (`*data*`) until every `op 2` (detach) answer or R6 has confirmed no IOMMU context entry still points at that root.

2. **[high] `kernel-interface.md:658, 657` — Add `StoreLoad` barriers around `entry_word`, `quiet_word`, and `kernel_epoch` (`B.1.1`)**
   - At `658`: replace `"after it has written its entry word"` with `"separated by a full StoreLoad memory barrier (`MFENCE`/locked RMW on x86-64, `DMB ISH` on ARM64, `fence rw, rw` on RISC-V) after writing its entry word, and the escalator executes a StoreLoad barrier after raising the kernel epoch before reading the other cores' entry words"`.
   - At `657`: specify the symmetric `StoreLoad` barrier after raising `kernel_epoch` / before reading the other cores' `entry_word`s in `untyped_retype`, and revise the cost summary at `658` so it does not claim entry costs only a write and a read with no barrier.

3. **[high] `kernel-interface.md:658, 759–764, 778, 1502, 1769` — Fix IRQ deferral during `quiet_word` wait (`B.1.2`)**
   - Add a per-core `deferred_vectors` bitmap (256 bits) in `1502` and `1769` (or instead forbid EOI-and-defer when a level line requires an IOAPIC request or cross-core `core_lock`, leaving the interrupt un-EOIed at the local controller with interrupts masked until `quiet_word` clears; or mask+EOI only for local-EOI / edge sources while recording each vector in `deferred_vectors` and validating generation/state + re-checking `irq` state under `core_lock` once `quiet_word` clears, never calling `irq_ack` no-op on a deferred pending level arrival).
   - At `778` and `658`: settle the x86-64 IOAPIC-without-EOI-register path explicitly so step 1 (`658`, *"which take no lock"*) never attempts to queue a lock-requiring `UnitRequest` `op 5` inside the `quiet_word` spin (e.g., hold off local APIC EOI on that core with IF=0 until `quiet_word` clears, bounded by `B_1_max` / escalation, or wait on `quiet_word` with interrupts masked while polling).

4. **[high] `kernel-interface.md:658, 670, 671, 1489, 524, 552` — Replace the divergent escalation bound and fix `CORE_ANSWER_NS` start-up checks and admission/budget rules (`Part A #2`, `B.1.3`)**
   - At `658`: replace `"Bound of an escalated call: its one-core bound, plus E, ... plus the escalated calls ahead of it in the queue of the word, at most N − 1, each of the same bound"` with `"Bound of an escalated call: its one-core bound plus E (once for the initial drain of non-escalating cores) plus (N − 1) × B_1_max (at most N − 1 one-core escalated executions ahead of it in the queue)"`.
   - At `670`: include the `quiet_word` wait term under L2 (`E + (N − 1) × B_1_max`) in the core invalidation request latency bound.
   - At `671` and `1489`: fix the start-up check so it refuses `CORE_ANSWER_NS` not above `N × H + IPI_DELIVERY_MAX` under L1, and not above `max(2 × k_max × (N − 1) × h, E + (N − 1) × B_1_max, E + k_max × (N − 1) × h + IPI_DELIVERY_MAX + quiet_wait)` under L2.
   - At `524` and `552`: cap admission below `2^32` by the worst-case escalation / interrupt reserve (or isolate escalated spin accounting from unrelated frame-class budgets).

5. **[high] `kernel-interface.md:652–656, 662, 203, 585–591, 1110–1113, 1121–1130` — Fix missing L2 locks, lend-release write-before-try, `task_revoke` order/bound, and `k` overflow (`B.2.1`, `B.2.2`, `B.2.4`)**
   - At `656`: add `task (2)` and `thread (3)` tries for IPC mark propagation (`1110–1113`) on `call`, `send`, `recv`, and `reply_recv`, and add `reply (5)` neighbour / `sched (8)` / `T1 (3)` tries for lend release (`203, 585–591`); specify that `recv`/`reply_recv` takes/tries the caller's segments and marks **before** mutating/releasing the old lends (`203`) so `again` leaves nothing changed (`652`).
   - At `662`: recompute `k` accurately for Round 2 of `reply_recv` (up to ~32 locks if answer + receive are combined in one lock hold, or split `reply_recv`'s answer locks from its receive locks into two sequential non-`again` or rollback-safe phases—note that splitting after answer commits violates `"nothing changed"` if receive returns `again`, so either raise `k` to cover both + mark/lend locks or cap capabilities/segments per call). Raise `k` for `call`, `send`, and `thread_configure` similarly.
   - At `1121–1130` and `662`: split `task_revoke`'s initial `revoked` + `leaving`-IPI pass across bounded batches of at most 32 threads (or mark `revoked` + send IPIs only after unit 1's lock tries succeed, never calling `gate` / `core` before lower-order tries).

6. **[high] `kernel-interface.md:749, 774, 1020, 1022, 1024` — Make `irq` removal asynchronous across units (`op 5 masked` / `op 4`) before freeing the line word (`B.4.1`)**
   - At `749, 774, 1024`: when removing an `irq` on a line (or remapped vector), first mark the `irq` `dying` / unbind it, queue the required `UnitRequest` (`op 5 masked`, and `op 4` IEC invalidation where remapped, or GIC/APLIC disable), keep the line's owner word *taken* by the node (just like a `frame`'s *unmapping* record keeps counts until `UnitAnswer` done/*failed*, [`349, 1024`](../architecture/kernel-interface.md#L349)), return `again` from the removal step until any in-flight claim requests finish and the mask/clear request is confirmed, and clear the line word to `*free*, unclaimed` only upon confirmation.

7. **[high] `kernel-interface.md:941, 1454–1455` — Carry full line configuration in `Report` and close the rebuild-vs-removal race (`B.4.2`)**
   - At `941`: replace `"for a remapping handle or a line two words 0"` with the line's programmed state needed for rebuild (`two words 0` for a remapping handle stays; for a line, include `(handle/APIC_ID, vector, trigger, polarity, masked/armed)` on x86-64, `(target_core, trigger_config, enabled)` on ARM64 GIC distributor, `(target_hart, priority, enabled)` on RISC-V APLIC).
   - At `1455`: ensure a live node that already answered a `ReportAsk` (or is between `Report` and rebuild end) keeps the line word until the holder finishes rebuilding (automatic once `B.4.1` makes `irq` removal wait on a `UnitRequest` queued behind the rebuild!).

8. **[medium] `kernel-interface.md:658, 1481, 1489` — Fix ticket-lock release (`now_serving`) and forbid `CORE_ANSWER_NS >= STALE_NS` (`B.1.4`)**
   - At `658`: replace `"clears the word"` with `"advances the serving ticket of the quiet word (free when serving equals next)"`.
   - At `1481, 1489` (and start-up checks): require `CORE_ANSWER_NS < STALE_NS` (or enforce that `STALE_NS` exceeds `SWEEP_NS`/`CORE_ANSWER_NS` plus firmware stall margin) so a healthy quiet-word wait cannot exceed `STALE_NS`.

9. **[medium] `kernel-interface.md:656, 128–129` — Remove `"the delivery of a fault"` from the `again` call list and defer `dying`/`sweep` writes in `cap_delete`/`cap_revoke` (`B.2.3`, `B.2.5`)**
   - At `656`: remove `"and the delivery of a fault"` from the list of calls that try receiver segments and may return `again`; state separately under [`654`](../architecture/kernel-interface.md#L654) that a fault delivery holding `endpoint (4)` tries `receiver.task (2)` / `receiver.thread (3)` for marks (`1112`) and falls back in lock order (`task/thread -> endpoint -> sched/core`) without returning `again`.
   - At `128–129, 652`: either perform unit 1's derivation-list neighbour try *before* mutating `dying` or `cspace.sweep` (returning `again` cleanly with zero state changed), or explicitly bound/define `dying` and `sweep` updates.

10. **[medium] `kernel-interface.md:1020, 1063` — Add generation check on `op 5 (masked)` and require matching vector for all remapped IOAPIC lines (`B.4.3`)**
    - At `1020` and `1063`: change `"masked: the line's word is free or names the requester"` to `"masked: the line's word is free or names the requester with its generation"`.
    - At `1020`: remove `"for a level line"` before `"the vector of the remapping entry"` so every remapped IOAPIC entry (edge and level) matches the IRTE Vector field per VT-d §5.1.5.1.

11. **[medium] `kernel-interface.md:749, 795, 2067, 2071` — Define the sparse line-word index map, multi-arch claim gate call, and non-remapped IOAPIC `APIC ID > 255` rule (`B.4.4`)**
    - At `749, 2067, 2071`: define a deterministic mapping from x86-64 GSI, ARM64 SPI/ESPI, and RISC-V `(APLIC domain, source)` to line-word indices `[0, num_line_words)` (including ARM64/RISC-V fields in `Interrupts` at `2067` or a sparse line map).
    - At `749`: clarify that `irq_claim` takes the line word *"through its gate (in the same gate call as the remapping entry where interrupt remapping is used)"*.
    - At `795`: state explicitly that without interrupt remapping, `irq_claim` of a line as well as an MSI on a core whose APIC ID exceeds `255` returns `unsupported`.

12. **[low] `kernel-interface.md:1639, 1279` — Guard `observations[8]` and accusations on the `release word`, and freeze/shift membership & `seal` instants across debugger stops (`Part A #4`)**
    - At `1639`: suspend `STALE_NS` and `STUCK_NS` alongside `CORE_ANSWER_NS`, `FENCE_NS`, and `SEAL_NS`; prevent calls (accusations/`node_send` observations), arrivals, and recovery-reserve steps from recording observations or accusing while `release word` is raised; and adjust `ns_base` (or shift all `seal` instants, open `FenceRecord` instants, `invalidation_request` starts, and `idle_until` values) by the stop duration before clearing `release word`.
    - At `1279`: state that in development builds, the gate records no observation while `release word` is raised.

13. **[low] `kernel-interface.md:1275, 1278` — Have the sweep check two `sealed` successors for `seal`, and align `Who looks` (`Part A #3`)**
    - At `1278`: keep observing the first core of two successors among `{starting, live, sealing}` (for `stale`), and add observing the `seal` instant of two successors among `{sealed}` (for `seal`), both in cyclic index order.
    - At `1275`: update `Who looks` from `"Any live node; the sweep"` to `"Any live or sealing node; the sweep"`.

14. **[low] `kernel-interface.md:328` — Fix Arm DDI 0487 section citations (`Part A #1`)**
    - At `328`: change `(Arm DDI 0487, C5.5.60)` to `(Arm DDI 0487, C5.5.60 for TLBI VAE1IS, C5.5.11 for TLBI ASIDE1IS)`, and change `(Arm DDI 0487, B2.3, "TLBI Effects, Completed TLBI Effects and Invalidation Scopes")` to `(Arm DDI 0487, D8.17.8; broadcast scope in D8.17.7; formal definition in B2.3.1)`.
