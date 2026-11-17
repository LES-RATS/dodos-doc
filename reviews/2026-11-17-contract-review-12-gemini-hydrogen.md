# Contract Review 12 (Pass 19)

**Reviewer:** Gemini 4 Hydrogen  
**Date:** 2026-11-17  
**Target:** `architecture/kernel-interface.md` at `main` (`05d4ed6`, including Pass 19 commits `e440458` and `e99e9b3`), cross-checked against `decisions/README.md` (`D-135`–`D-137`) and external specifications.

---

## Findings

### Finding 1 — CRITICAL: Ticket-lock deadlock in `quiet_word` escalation when two cores escalate concurrently

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:666`:
  > "A call that would return such an `again` while the count is already 2 does not return it: it **escalates**. It releases every lock it holds, takes the node's **quiet word** (one word of the node block: a ticket lock, its next ticket and its serving ticket, a ticket taken by an atomic add so that the cores that wait for it are served in the order they came; held while the two differ), raises the node's kernel epoch by one by an atomic add, orders both before its next load (an atomic read-modify-write is such an operation on x86-64; `DMB ISH` after it on ARM64; `fence rw,rw` on RISC-V), waits until the entry word of every other core of the node reads 0 or at least the new epoch, runs the call alone, taking its locks in the order (no try can fail and no link can change, since no other core is in a kernel event), and releases the word by advancing its serving ticket, a release store (D-137: the earlier text said it cleared the word, which a ticket lock with a waiter behind the holder cannot be)."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:666` (entry and `entry_word` definition):
  > "**Every core reads the quiet word when it enters the kernel** for a call or an event, after it has written its entry word by an operation that orders that store before its next load ... If another core holds the word, the core writes its entry word 0, waits until the word is released and enters again, and it takes no lock before."
  > "**The entry word** of each core, in its part of the node block, holds the kernel epoch the core read when it entered its current kernel event, and 0 outside one and while it waits for the quiet word: one ordered write to the core's own line at each entry, one release store of 0 at each exit..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:666` (bound counting queued escalations):
  > "...and each escalation ahead of it in the queue, at most *N* − 1, runs alone in its one-core bound."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:668`:
  > "**The quiet word adds no cycle (D-135):** a core waits for it only at the entry of an event, before it takes any lock, its entry word 0; the holder takes it only once it has released every lock, waits only for the other cores' current events, none of which waits for it, and then takes its locks in the order with no other core in an event..."

**Scenario / Contradiction:**
1. Suppose a node has cores *b* and *c* (with `kernel_epoch = e_old`). Core *b* enters a kernel event (so `b.entry_word = e_old`) and core *c* concurrently enters a kernel event (so `c.entry_word = e_old`).
2. Both cores execute calls that hit `again` from the rule of tries while their consecutive `again` count is 2, so both escalate inside their current kernel events.
3. Core *b* releases its locks, atomically adds to `quiet_word.next` to take ticket `t` (matching `serving == t`, so *b* acquires `quiet_word`), raises `kernel_epoch` to `e_old + 1`, and spins waiting for `c.entry_word` to read `0` or `>= e_old + 1`.
4. Core *c* releases its locks and atomically adds to `quiet_word.next` to take ticket `t + 1`. Because `serving == t != t + 1`, core *c* spins waiting for `serving` to advance to `t + 1`.
5. However, core *c* never exited its kernel event (`"one release store of 0 at each exit"`) and only kernel *entry* writes `entry_word = 0` when `quiet_word` is held (`"If another core holds the word, the core writes its entry word 0, waits until the word is released and enters again"`). Thus `c.entry_word` stays equal to `e_old` while *c* spins on its ticket!
6. Even worse: if `c` also raised `kernel_epoch` immediately after taking its ticket (`t + 1`) rather than after being served, `b` would raise its target to `e_old + 1` while `c` raised `kernel_epoch` to `e_old + 2` — and even if `c` waited before raising `kernel_epoch`, `c.entry_word` remains `e_old < e_old + 1`.
7. Result: *b* holds the ticket lock and waits forever for `c.entry_word` to become `0` or `>= e_old + 1`, while *c* spins forever waiting for *b* to advance `serving`! Both cores time out past `CORE_ANSWER_NS`, and a healthy node accuses itself (`evidence self`). Note also line `668`'s claim (*"a core waits for it only at the entry of an event, before it takes any lock, its entry word 0"*) directly contradicts line `666`'s ticket queue where up to *N* − 1 escalators wait for the ticket lock from inside their events.

**Smallest correction:**
1. After taking a ticket on `quiet_word` (and releasing all locks, with interrupts masked as already required), an escalating core that is not yet being served must write `entry_word = 0` (release store) before spinning on `quiet_word.serving == my_ticket`.
2. Only **after** `quiet_word.serving == my_ticket` holds (so it is the active holder) does it raise `kernel_epoch` by one (atomic add), write its own `entry_word = new_epoch` with store-load ordering (or keep `entry_word` out of its own check while preventing any third core from skipping wait), and then wait for every other core's `entry_word` to read `0` or `>= new_epoch` before executing its call alone. Waiters leaving ticket-spin upon acquiring `quiet_word` can either enter the holder's wait with `entry_word` still `0` until completion or restore `entry_word = new_epoch` on ticket acquisition before waiting on others' `entry_word`s (keeping `0` on release/exit).

---

### Finding 2 — CRITICAL: Sticky-mark monotonicity violated by `task_attach` under lock-free mark ORs

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1114`:
  > "Every thread also has its own marks word, 0 when the thread is created. The **effective marks** of a thread are the marks of its task if it is attached to one, and otherwise its own marks word. **The effective marks of a thread never lose a bit while the thread lives.** Every rule below keeps this invariant."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1116`:
  > "So every write of a marks word is an atomic OR, every read is a plain read, and a delivery needs no lock of a task or a thread and no try: it reads the marks and ORs them after its last try, where nothing can follow with `again` ([A node of several cores](#a-node-of-several-cores)). **Where a delivery ORs (D-137):** into the thread's own word always, and into its task's word too if the thread is attached to one, the task read after the own word is written; and `task_attach` writes the thread's new task first, then ORs into the new task the thread's own word and the marks of the task it leaves, each of these an operation ordered with the next (an atomic OR, a read after a store ordered as the entry word is). So when a delivery races an attach on another core, either the attach reads the own word with the new bits, or the delivery reads the new task and ORs into it: no bit a delivery stamps is lost by the thread or by the task it ends in."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1120`:
  > "Otherwise, with *m* the effective marks of the thread, the thread leaves its old task if it had one, joins the new one, and the new task's marks become marks \| *m*. This holds even when the new task is mark-aware. Detaching sets the thread's own marks word to the marks of the task it leaves."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1131, 1133, 1136`:
  > "- marks = the effective marks of the sender | the added marks of the message (below)."
  > "The values are taken at delivery, not when the call was made: a caller marked while it waited in a queue sends its new marks."
  > "If at a delivery at least one capability is moved or derived (the transfer was not dropped), and the sender is not attached to a mark-aware task, the sender's effective marks become themselves | the receiver's effective marks as they were before this delivery."

**Scenario / Contradiction:**
The ordering argument in line `1116` only considers bits newly stamped into `thread.own_word` during a delivery concurrent with `task_attach`; it breaks the invariant of line `1114` (*"The effective marks of a thread never lose a bit while the thread lives"*) in **two** ways:
1. **Re-attaching a thread (`Task1` → `Task2`) drops `Task1.marks`:**
   Suppose thread *T* is attached to `Task1`, where `Task1.marks = M ≠ 0` (e.g., set earlier via `task_mark` or via another thread of `Task1` receiving a marked message), while `T.own_word = 0` and `Task2.marks = 0`.
   - Core A executes `task_attach(T, Task2)`. By line `1116`, Core A writes `T.task = Task2` *first*, before ORing `Task1.marks` (`M`) into `Task2.marks`.
   - In the window between Core A writing `T.task = Task2` and Core A ORing `Task1.marks` into `Task2.marks`, Core B delivers a message from *T* (for example, *T* was waiting in an endpoint queue and wakes at delivery, line `1133`, or delivers a capability transfer to a receiver, line `1136`).
   - Core B reads `T.task == Task2` and `Task2.marks == 0` without taking `Task2`'s or `T`'s lock!
   - Thus *T*'s effective marks drop from `M` to `0`, and Core B stamps/delivers *T*'s message with marks `0` instead of `M`, violating line `1114` and leaking unmarked data from a marked task.
2. **Detaching (`Task1` → `0`) has no safe write order under lock-free delivery ORs:**
   Line `1116`'s store-first sequence does not even describe detach (`task == 0`, where there is no new task and `1120` sets `T.own_word |= Task1.marks`).
   - Clearing `T.task = 0` first drops *T*'s effective marks from `Task1.marks` (`M`) to `T.own_word` (`0`) in the same race window as (1).
   - Conversely, reading `Task1.marks` and ORing it into `T.own_word` *before* clearing `T.task = 0` still fails under lock-free delivery ORs: after `task_attach` reads `Task1.marks`, another core B delivers a marked message to sibling thread *T2* of `Task1` and executes `Task1.marks |= M'` lock-free (while `T.task` is still `Task1`). `T`'s effective marks are `Task1.marks` (`M'`), and when Core A clears `T.task = 0`, *T*'s effective marks revert to `T.own_word` (lacking `M'`), again losing bit `M'`.

**Smallest correction:**
Either:
- **(Option A — keep lock-free deliveries when not re-attaching, OR synchronize re-attach with deliveries):** Require `task_attach` (and detach) to OR `old_task.marks` into `new_task.marks` (or `T.own_word` for detach) **before** updating `T.task` when `old_task` cannot gain new bits during the transition — e.g., take `old_task`'s lock *and* forbid lock-free writes to `task.marks` (take the task lock at delivery, or at least when `task` is being detached/re-attached), OR only permit `task_attach` on a suspended, non-waiting thread whose old task has no other runnable/delivering thread (or wait out an epoch / take the quiet word after `T` stops taking deliveries and before `T.task` changes). Because `1116` explicitly wanted deliveries to avoid task/thread locks, taking `Task1`'s and `Task2`'s lock at delivery was what D-137 tried to omit; without locking the task on delivery (or quiescing concurrent deliveries to `old_task` across the attach/detach), a task's marks cannot be transferred atomically alongside a lock-free `T.task` pointer update.
- Specifically, if deliveries take the sender/receiver `task` lock only when reading/writing `task.marks` (counted in *k*, as before D-137) OR if `task_attach` transitions `T` via `task_attach` only when `T` is suspended and not waiting and uses a brief per-attach quiescent barrier / two-step attach while reading `old_task`, both races close. The cleanest fix to preserve `1114` and `1116`'s lock-free reads is: take `old_task`'s and `new_task`'s locks in `task_attach`, and make deliveries take `task` lock when ORing `task.marks` (re-introducing those at most 2 locks per message), **or** keep lock-free `task.marks` atomic ORs only if `task_attach` first marks `T` so deliveries pause/retry, OR writes `new_task.marks |= old_task.marks` (and for detach `T.own_word |= old_task.marks`), switches `T.task`, and re-reads/re-ORs after waiting out every other core's current kernel event (`kernel_epoch` / `entry_word`, as in `untyped_retype` `665`), which costs 0 on deliveries and adds an `entry_word` wait only on `task_attach` when leaving a non-null task.

---

### Finding 3 — HIGH: Infinite `again` loop in `iospace` destruction on a failed IOMMU unit, and stale `attach_word` on failed `op 1`

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:374`:
  > "Its destruction, when its root capability is the next to remove, first detaches each of its devices (most recently attached first), then empties each record of its list (most recently mapped first). Each counts as one of the 32 of a step. A detach is a unit request: the step that starts it returns `again`, and the device is detached at the answer, as for `iospace_attach` with iospace 0 (D-137). ... The root and the tables turn back into *data* only once the root's count of devices is 0 (G2); a detach answered *failed* leaves the attach word *attached* and the count above 0 (below)."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:373`:
  > "...at the answer done, the caller's gate writes the attach word 0 and the identifier word *free*, unclaimed, and lowers the root's count of devices, and the device leaves the iospace's header..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1046`:
  > "**At the answer**, in the event that consumes it, whether or not a thread still waits: *done* completes the entry ... *failed* empties the record with its counts kept, or ends the waiting call with `busy` ([IOMMU](#iommu))..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:380` & `368`:
  > "...and the table pages of an iospace that served a device of the unit keep their class (*iospace table of level k*, and its root *iospace root with n devices attached*, *n* > 0, since the attach word stays *attached*: D-137) when the iospace is destroyed, so they are never reused before the machine restarts;"
  > "`iospace_attach`: ... - the device is already attached to this iospace (success, nothing changes);"

**Scenario / Contradiction:**
There are two coupled defects here:
1. **Infinite `again` loop on destruction:** During `iospace` destruction (`374`), the step inspects the devices listed in the `iospace`'s header and sends a detach (`op 2`) for the most recently attached device, returning `again`. When the IOMMU unit has failed (`377`), the holder answers *failed*. By `373` and `1046`, only *done* removes the device from the `iospace`'s header (`"at the answer done ... the device leaves the iospace's header"`), while *failed* leaves the attach word `*attached*`, leaves `n > 0` (`374`, `380`), and says nothing about removing the device from the `iospace`'s header (`1046`). Consequently, on the next `cap_delete` / `cap_revoke` call, the `iospace`'s header still contains the exact same device! The destruction step issues another `op 2` detach request, which immediately gets *failed* again, returning `again` **forever**. Any `cap_delete` on a process `cspace` or `untyped` owning an `iospace` on a failed IOMMU unit hangs permanently in an infinite `again` loop.
2. **Broken `attach_word` state and false `ok` on failed `op 1` (`iospace_attach`):** At `372`, `iospace_attach` writes `attach_word = *pinned*(root)` and adds the device to `iso`'s header *before* waiting for `op 1`. If `op 1` fails on a unit failure (`*failed*`), `op 1`'s handler never runs `357` (`*pinned* -> *attached*`), so `attach_word` remains `*pinned*(root)` (contradicting `380`: *"since the attach word stays `*attached*`"*). Furthermore, if `iospace_attach` had timed out/failed earlier (or if a subsequent `iospace_attach` somehow ran before failure, or on a unit whose failure isn't checked before `368` if ever re-ordered), `dev` is in `iso`'s header despite never being attached at the unit.

**Smallest correction:**
1. On *failed* answer to a detach (`op 2`) started by `iospace` destruction (`374`), remove the device entry from the `iospace`'s header (and from the node's per-unit device list, `375`) at the answer (`1046`), **without** lowering the root's device count `n` or clearing `attach_word` / `identifier_word`. That lets destruction advance past the devices, empty the mapping records (`379`), and remove the root capability while keeping `n > 0` and the root/table page classes non-reusable until reboot (`380`).
2. Explicitly specify at `380`/`1046` that on *failed* `op 1`, `attach_word` stays `*pinned*(root)` (or note `"pinned or attached"`) and the device stays in the node's / iospace's failed-device state (or leaves the iospace's header on `iospace_attach` failure while keeping `attach_word = *pinned*(root)` and `n > 0`), and at `367`–`368` check `attach_word == *attached*(root)` rather than the header alone before returning success in `368`.

---

### Finding 4 — HIGH: `iospace_attach` / `iospace_detach` / destruction race on `attach_word` and `iospace` header

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:367-368`:
  > "- the device is attached to another iospace, or is being detached, its attach word not 0 (`busy`; detach it first, or wait for the detach's answer: D-137);
  > - the device is already attached to this iospace (success, nothing changes);"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:372-373`:
  > "Then, in one gate call, the identifier word becomes *taken* by the node and the attach word *pinned* (the iospace's root), the root's count of devices growing by one (D-137); the device is added to the iospace's header; and the attach is asked of the unit's role holder (operation 1), the caller waiting in *waiting for a unit*: the holder's gate writes the attach word *attached*..."
  > "With iospace 0: if the device is attached to an iospace of the caller's node, the detach is asked of the holder (operation 2), the caller waiting in *waiting for a unit*: the holder clears the context entry (the device is blocked again), invalidates the caches and, once the invalidation is complete, writes the attach word *detached*; at the answer done, the caller's gate writes the attach word 0 and the identifier word *free*, unclaimed, and lowers the root's count of devices, and the device leaves the iospace's header..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:359`:
  > "- *pinned* (root) or *detached* (root) → 0, by the gate of the owner, which lowers *n* in the same gate call and writes the identifier word *free*, unclaimed; never from *attached*;"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1037-1038, 1042`:
  > "| 1 attach | ... | G9: the attach word moves from *pinned* to *attached* with that root (or reads *attached* with it) ... |"
  > "| 2 detach | ... | ... once the invalidation is complete, the holder's gate writes the attach word *detached* if it reads *attached*; the identifier word stays the requester's until the requester's gate writes it *free* at the answer, with the attach word 0 (D-137) |"
  > "A request whose operands fail these checks is not written to the unit: the holder traces it (code 11, [What the kernel traces](#what-the-kernel-traces)) and answers it done, so the requester's entry ends;"

**Scenario / Contradiction:**
`372` adds `dev` to `iso`'s header *before* waiting for `op 1`, and `373` removes `dev` from `iso`'s header only at `UnitAnswer(done)`. This permits two destructive races on the same node:
1. **Premature `ok` during in-flight attach or detach:**
   - Thread `T1` calls `iospace_attach(iommu, iso, dev)`. `372` writes `attach_word = *pinned*(iso.root)` and inserts `dev` into `iso`'s header, then `T1` waits for `op 1`. While `op 1` is still in flight (no context entry written yet), Thread `T2` calls `iospace_attach(iommu, iso, dev)`: `367` passes (*"attached to another iospace"* is false because it is in `iso`'s header!), and `368` (*"already attached to this iospace"*) returns **success** to `T2` before DMA translation is enabled!
   - Symmetrically, while `T1` is waiting on `iospace_attach(iommu, 0, dev)` (`op 2` detach in flight), `dev` is still in `iso`'s header (`373`), so `T2` calling `iospace_attach(iommu, iso, dev)` gets **success** at `368` while `T1` is actively tearing down the device's context entry!
2. **Double detach (`op 2`) corrupts a later `iospace_attach` (`op 1`) and breaks G2 root pinning:**
   - Two threads on the same node (or `iospace_attach(iommu, 0, dev)` racing `iospace` destruction `374`) both observe `dev` attached to `iso1` and enqueue two `op 2` detach requests `D1` and `D2`.
   - `D1` finishes first (`UnitAnswer(done)`): `373` writes `attach_word = 0`, `identifier_word = free`, lowers `iso1.root` count, and removes `dev` from `iso1`'s header. `D2` is still queued or in flight.
   - Immediately, Thread `T3` calls `iospace_attach(iommu, iso2, dev)`. All checks pass (`attach_word == 0`). `372` sets `identifier_word = taken`, `attach_word = *pinned*(iso2.root)`, raises `iso2.root` class count to `48 + 1`, adds `dev` to `iso2`'s header, and queues `op 1` (`A1`).
   - Now `D2` arrives at holder *H*: `attach_word` reads `*pinned*(iso2.root)`, not `*attached*(iso1.root)`. By `1038` + `1042`, *H* skips modifying `attach_word`, traces code 11, and **answers `done`**.
   - When the requester node consumes `D2`'s `UnitAnswer(done)`, `373` runs its gate write (`359`), which explicitly allows `*pinned*(root) → 0`! The gate clears `attach_word` to `0`, clears `identifier_word` to `free`, lowers `iso2.root`'s device count back to `48 + 0`, and either drops `dev` from `iso2`'s header or leaves `iso2` inconsistent. Even worse: if `A1` has not yet run `1037` it fails `1037` (`0 != *pinned*`), traces code 11, and still answers `done` (`1042`), so `T3` returns `ok` with **no context entry**; or if `D2` completes *right after* `A1` moved `attach_word` to `*attached*`, `359` refuses `*attached* → 0`, or if `iso2` is destroyed while `iso2.root` was lowered to `48 + 0`, `iso2` tables can turn into `*data*`!

**Smallest correction:**
Track attach/detach transition state per device (e.g., an *attaching* / *detaching* flag on the iospace device entry and/or distinct `attach_word` handling):
- Refuse (`busy`, or `again`) any new `iospace_attach` (`367`/`368`) or `iospace_detach` (`373`/`374`) on a device that already has an `op 1` or `op 2` request in flight; in `368`, return success only if the device is currently `*attached*` with no detach/attach in flight.
- Restrict `359` / `373`–`374` so that a detach `UnitAnswer(done)` transitions `attach_word` to `0` and lowers `n` **only** if `attach_word == *detached*(iso.root)` (never clearing `*pinned*(iso2.root)`), and refuse `op 1` / `op 2` answers from an earlier transition by matching the `iospace` root / generation in the unit request completion.

---

### Finding 5 — HIGH: Unhooked table free-list chain written into word 0 violates G3(4) and G12(2)

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:267`:
  > "**An unhooked table joins the free list only at the completion of the invalidation that covers its unhooking (D-137)**: in the call on a node of one core and on ARM64 (the sequence of break-before-make below), at the completion of its core's request on x86-64 and RISC-V in a node of several cores ([TLB](#tlb-one-core-and-several)), and for an iospace at the unit's confirmation ([IOMMU](#iommu)); until then the tables a change unhooked are linked through their own first word, which an empty table does not use, in a chain whose head the request (or the entry of the unit request table) holds. Why: a core, or a unit, that still holds a cached entry of the old parent would walk the table at its old place, and a table hooked again meanwhile, at another level or for another range, would hand it translations no record names, to table pages or to memory already given back..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1078`:
  > "- **G3. Checks on writing an entry.** ... (4) checks the permissions: ... a non-present entry is written as all zeros; ..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1087`:
  > "It must show ... (2) that the invariant of G3 holds after **every store**, not only at the end of a call, because the walkers of the node's other cores read the tables while the gate writes them..."

**Scenario / Contradiction:**
1. The first word (byte offset 0) of an empty page-table page or IOMMU-table page **is entry 0** of that table.
2. Line `267` explicitly states that while the unhooked tables are in the chain (before invalidation completes), hardware walkers (other CPU cores or IOMMU units) *"still hold a cached entry of the old parent [and] would walk the table at its old place"*.
3. Linking those unhooked tables *"through their own first word"* stores a non-zero physical address (the next table's physical page address, e.g., `0x...000`, or an index/pointer) directly into entry 0 of a table that is actively reachable by concurrent hardware walkers!
4. That store directly violates:
   - **G3(4)** (`1078`): *"a non-present entry is written as all zeros"* — entry 0 is non-present yet non-zero! (And if a physical page address or pointer metadata happens to have bit 0 set — or on RISC-V/ARM64/VT-d depending on pointer encoding or bit 0/1 flags — the hardware walker interprets entry 0 as a **present** entry pointing to physical address `0` or bogus flags; even when bit 0 is 0, storing a non-zero pointer violates G3(4)'s explicit rule that non-present entries are all zeros, and breaks G12(2)'s requirement that G3 holds after every store.)
   - **G14** / gate verification (`1087`, `1089`): any table check or walker reading entry 0 sees a non-zero non-present entry in a table page of class `16 + k` or `32 + k` while the table is still not freed.

**Smallest correction:**
Do not write the chain link into word 0 of the unhooked table page. Each `aspace_unmap` (or `iospace_unmap`) unhooks at most `2 × (L − 1)` tables (`303`, e.g. at most 6 tables for 4 levels). Store the fixed array of up to `2 × (L − 1)` unhooked table physical addresses directly in the core's `invalidation request` entry (`329`) or the `unit request table` entry (`1045`), keeping every unhooked empty table's entries all zeros (`G3(4)`). (Alternatively, reconstruct empty unhooked tables or store the free-list/chain link in per-page metadata outside the hardware-walked table page.)

---

### Finding 6 — HIGH: x86-64 `Report` unmasks `idle`, `fired`, and dying level-triggered IOAPIC lines on role take-over

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:772`:
  > "A level source is masked at the controller while the `irq` is idle or fired, and unmasked while it is armed."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:795`:
  > "**Otherwise it is a request, as an unmapping is (D-137):** the step unbinds the irq, which stays dying with its vector and its line word, starts the requests in an entry of the unit request table and returns `again`: for a line, first the redirection entry masked (operation 5, or the architecture's route disabled) to the holder of its controller's role..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:962`:
  > "| 8 | `Report` | ... for a line the two operands of its operation 5 claimed (or of the architecture's route: on ARM64 the SPI's identifier, trigger and enable in the first and the affinity of `GICD_IROUTER` in the second; on RISC-V the source, its mode and enable in the first and the target hart, priority or identity in the second; D-137). At most 28 items |"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1041`:
  > "| 5 redirection entry | GSI (0-31), 1 claimed or 0 masked (32), trigger (33), polarity (34) | remapped: handle (0-15) and vector (16-23); not remapped: vector (16-23) and APIC ID (32-63); masked: 0 | claimed: ... masked: the line's word is free or names the requester with its generation ... |"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1477-1478`:
  > "...for an IOAPIC, it compares each redirection entry with the lines the live nodes report, rewrites each reported line's entry from the two words of its report (the operands of its operation 5 claimed, checked as at that request) and masks the inputs nobody claims..."
  > "...and a node reports every line whose word it holds, the dying ones included (D-137)..."

**Scenario / Contradiction:**
Notice the asymmetry introduced in Pass 19 (`D-137`): for ARM64 and RISC-V, `962` explicitly puts *"enable"* in the `Report` item, whereas for x86-64 IOAPIC lines, both `962` and `1477` specify that `Report` sends *"the two operands of its operation 5 claimed"*, and `1477` *"rewrites each reported line's entry from the two words of its report (the operands of its operation 5 claimed, checked as at that request)"*.
In `1041`, operation 5 `"claimed"` sets bit 32 to `1` (**unmasked**), whereas `"masked"` sets bit 32 to `0`. Therefore, whenever an IOAPIC role is taken over after a holder death (`1477`):
1. Every **idle** (unbound) level line held by a live or sealing node is rewritten unmasked (`bit 32 = 1`) instead of masked (`772`).
2. Every **fired** (un-acked) level line held by a live or sealing node is rewritten unmasked (`bit 32 = 1`) instead of staying masked (`772`), breaking *"An interrupt is signalled once until it is acknowledged. This is what bounds an interrupt storm"* (`791`) and triggering an immediate interrupt storm on any asserted device line whose driver's budget was exhausted or restarted (`797`).
3. Every **dying** level line whose `irq` is mid-removal (`1478` + `795`) — and even an `irq` whose `op 5 masked` already ran before the old holder died while `op 4` / removal step was still running — is also reported as `"claimed"` and **unmasked again** at the IOAPIC!

**Smallest correction:**
In `962`, `1041`, `1084` (G9), and `1477`:
- Have x86-64 `Report` set operand 1 bit 32 to `1` only when the reported line's `irq` is live and should be unmasked (`armed` level source, or edge source), and `0` (`masked`) when the `irq` is `idle`, `fired` (level), or `dying` (carrying its trigger/polarity/destination or masked form as appropriate, or setting mask bit 1 in the RTE when bit 32 is 0).
- Update `1477` so the IOAPIC rebuild writes the RTE masked (`mask = 1`) whenever bit 32 of the reported entry is `0` (already permitted by G9 `1084` and `1041` *"masked: the line's word is free or names the requester with its generation"*).

---

### Finding 7 — HIGH: Closed `CORE_ANSWER_NS` bound under L2 omits execution of the invalidation interrupt handler

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:691-692`:
  > "Each asked core answers at the interrupt sent to it, which it takes at the latest at the end of its current kernel event (an idle core is not asked: [TLB](#tlb-one-core-and-several)); so a wait for a request lasts at most *N* × *H* (L1), or *E* for the asked core's current event plus *E* + (*N* − 1) × *B*1max for a wait for the quiet word at its next entry (L2: 2 × *E* + (*N* − 1) × *B*1max, D-137: the earlier bound left the quiet word out), plus *D*, the delivery of one interrupt, every core answering in parallel."
  > "**The machine start-up refuses a `CORE_ANSWER_NS` not above the longest healthy wait it judges, for the largest *N* the kernel image supports (entry `Node`), from the values measured for that image (D-131, D-137):** under L1, *N* × *H* + *D* (a request is the longest of the three waits: a lock wait is at most (*N* − 1) × *H*); under L2, 2 × *E* + (*N* − 1) × *B*1max + *D*, with *E* = *E*1 + 2 × *k*max × (*N* − 1) × *h*, *E*1 the longest kernel event on one core and *k*max the largest *k* of the image's calls (above), which bounds a lock wait of two rounds, a wait for the quiet word and a request with one interrupt delivery."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1512`:
  > "...and above the longest healthy wait of a core for the largest *N* the image supports, *N* × *H* + *D* under L1 and 2 × *E* + (*N* − 1) × *B*1max + *D* under L2, which the machine start-up checks..."

**Scenario / Contradiction:**
Trace the worst-case time from when core *c1* starts an invalidation request (and sends the invalidation IPI to asked core *c2*) until *c2* acknowledges and completes that request under variant L2:
1. Core *c2* is currently inside a maximum-length kernel event (e.g., two rounds of locks + work): time up to **+ *E*** before *c2* exits to a state where interrupts are unmasked and takes the pending invalidation IPI.
2. Delivery of the invalidation IPI to *c2*: time up to **+ *D***.
3. At entry to the invalidation interrupt handler (`666`), *c2* sees `quiet_word` held by a chain of up to *N* − 1 escalating cores (whose wait begins with at most one remaining *E* for running cores plus `(*N* − 1) × B1max`): time up to **+ *E* + (*N* − 1) × *B*1max**.
4. **Missing term:** Once `quiet_word` is released and *c2* re-enters the kernel, *c2* has **not yet run** the invalidation interrupt handler! It must still flush up to *N* − 1 pending requests (each up to *E* translations or a whole tag) and, as the last acknowledging core, acquire the `gate` lock (`+ (*N* − 1) × h` or up to **+ *E*** — `"longest kernel event"`) to lower up to *E* map counts, return unhooked tables, wake waiting threads, and set `state = done` (`329`).
5. Total worst-case healthy wait for a request under L2 is therefore **`3 × E + (N − 1) × B1max + D`** (or `2 × E + (N − 1) × B1max + E_ipi + D`), **not** `2 × E + (N − 1) × B1max + D`. A kernel image whose `CORE_ANSWER_NS` passes start-up check `692`/`1512` just above `2 × E + (N − 1) × B1max + D` can still exceed `CORE_ANSWER_NS` during normal operation and accuse itself (`evidence self`, reason 9).

**Smallest correction:**
Change the L2 invalidation-request bound and the machine start-up check in `691`, `692`, and `1512` from `2 × E + (N − 1) × B1max + D` to **`3 × E + (N − 1) × B1max + D`** (or introduce `E_inv` if measured separately for the invalidation interrupt event, bounded above by `E`).

---

### Finding 8 — MEDIUM: L2 lock-count bounds (*k*, `676`–`681`) and `thread_configure` try list (`664`) omit locks taken in several calls

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:670, 676-681`:
  > "**The bound *k* (counted again by D-137).** A call's *k* is the most locks it holds at once in its second round, the locks it found included, counted from the list of tries above and from the locks each effect needs; it counts one lock per core whose queues or interrupt table the call may change and one for the gate lock..."
  > "| `recv` | 40 | the endpoint and the reply object; the two lends released, each its `sched`, the two reply objects next to it in its chain and the thread it leaves without a context (8); the bound notify; the 26 of the caller found; the caller's `sched`, lent, and the reply object on top of its chain; the thread's own core |"
  > "| `reply_recv` | 67 | the answer (the reply object, the 26, the caller's core and the gate: 29) and the receive (`recv` less its reply object, which is the same, and less the gate counted once: 38), taken and tried before either writes (above) |"
  > "| a step of a removal (`cap_delete`, `cap_revoke`, and the removals that other calls run) | 387 | ... the segments of the 128 slots of a dying space it examines, 2; the gate, 1 |"
  > "| a step of `task_revoke` | 194 | ... each later step, the task, 32 detached threads of 6 each (the thread, the object it waits on, its reply object, its two neighbours in the task's list, its core) and the gate, 194 |"
  > "| every other call | 12 | ... `node_send` takes 10 (the frames' slots and their old next in the derivation list for the anchors, 8; the caller's core; the gate, which guards the rings and the credits) |"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:664`:
  > "...`aspace_map`, `iospace_map`, `aspace_unmap`, `iospace_unmap`, `thread_configure` and the removal of a frame capability with a record, the segment or the thread of a neighbour in a space's list of records or of bound threads..."
- Also `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:920, 1005` (`node_send` doorbell list), `645, 647` (cross-core `sched` placement and reschedule IPI via gate), `656` (`cspace.dir[0]` seq word), `542, 1150` (`sched` queues on suspend).

**Contradictions across five entries:**
1. **`node_send` (`681` vs `920`, `1005`):** Line `920` states *"A notify keeps the list of the grant entries whose doorbell it is, linked through those entries"*, and `1005` takes a `doorbell` notify argument (`999`). Yet `681` counts only `10` locks for `node_send` (`8` frame/next segments + caller's core + gate) and omits the doorbell `notify` lock (`654`, `658`). Without locking `doorbell`, `node_send` races `cap_delete(notify)` (which unbinds that exact list in `920`, `1005` / `1012`), potentially inserting a grant entry into a freed/dying notify's list. With `doorbell` locked, `node_send` takes **11** locks, not `10`.
2. **`recv` (`676`) and `reply_recv` (`677`):** `676` gives `recv` only 1 core lock (`"the thread's own core"`) and **0** gate lock (`40`). Under `645` and `647`, both the caller whose `sched` is lent (`caller.sched.core`) and the idle reply object whose released lend returns to its holder (`old_reply_caller.sched.core`) may have their `sched` placed on **different** cores from the receiver's own core, requiring updates to those cores' scheduler queues and reschedule IPIs sent through the **`gate`**! Adding up to 2 more core locks + 1 gate lock raises `recv` to **43**; similarly `reply_recv` (`677`) omits the `sched` cores of the answered caller (`answer`) and incoming caller (`receive`), raising it from `67` to **69** (if caller/receiver/released-lend cores are distinct, gate counted once).
3. **`cap_delete` / removal step (`679`):** Line `656` assigns `cspace.dying` and `cspace.sweep` to **`dir[0]`'s sequence word** (`"guarded by the sequence word of the first entry of its directory"`). Line `679` only counts `2` segments for *"the segments of the 128 slots of a dying space it examines"*, omitting `dir[0]` whenever the 128-slot sweep lies in segments `i` and `i + 1` with `i > 0` (**3** segments, not `2`). Moreover, if a 32-unit step walks into nested dying `cspace`s (up to 64 levels, `122`–`123`), each dying `cspace` whose sweep/dying state is read/updated can contribute a `dir[0]` lock as well.
4. **`task_revoke` later steps (`680` vs `1148`–`1151`):** `680` counts 6 locks per detached thread (`thread, object it waits on, reply object, two neighbours in the task's list, core`). When `1150` sets a thread's `suspended` flag on a thread that is ready or lent (`sched` not null) and not waiting, removing its `sched` from its core's ready/slack/sleeping queues (`542`) requires locking that **`sched`** object too (`654`, `658`), which sits between `reply` and `core` in L2's order (7 locks per thread → `1 + 32 × 7 + 1 = 226`, not `194`). (Note also `core` in `680` for an *unwaiting* ready thread is the core where its `sched` is placed.)
5. **`thread_configure` try list (`664`):** `664` mentions *"the segment or the thread of a neighbour in a space's list of records or of bound threads"*, omitting `old_cspace` (`dir[0].seq`) and `old_msg_page`'s segment, both of which are only discovered after reading `thread` (`thread` > `cspace` segments in order `658`!) and must therefore also be **tried** (as `678` already counts them in `21`). Note `678` also counts both `old` and `new` head + 2 neighbours for all three lists (`2 + 4 = 6` each, total `21`), which is fine as an upper bound, though `new_cspace`/`new_aspace`/`new_ep`/`new_msg_page` are arguments known upfront.

**Smallest correction:**
- Add the `doorbell` `notify` lock to `node_send` (`681` → `11`).
- Account for the distinct core locks of the lent/released `sched` contexts and the `gate` lock in `recv` (`676` → `43`) and `reply_recv` (`677` → `69`).
- Include `dir[0]` for dying `cspace` sweeps in `679` (`2 → 3`, or bounded for nested spaces) and each detached thread's `sched` lock in `task_revoke` (`680` → `226`).
- Add `old_cspace`'s `dir[0]` and `old_msg_page`'s segment to `thread_configure`'s try list in `664`.

---

### Finding 9 — MEDIUM: `irq` removal frees remapping entry, handle, and vector when an IOMMU IEC invalidation returns `*failed*`

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:795`:
  > "**Otherwise it is a request, as an unmapping is (D-137):** the step unbinds the irq, which stays dying with its vector and its line word, starts the requests in an entry of the unit request table and returns `again`: for a line, first the redirection entry masked (operation 5, or the architecture's route disabled) to the holder of its controller's role; then, where a remapping entry is cleared, the invalidation of the interrupt entry cache (operation 4) to each unit that serves the source's segment, one after another as for a claim ([Devices and shared hardware](#devices-and-shared-hardware)). ... At the end of the last request, done or *failed*, the line word is written *free*, unclaimed, the remapping entry and the vector are free, and the next step removes the capability."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1043`:
  > "...a unit found failed may still hold a stale entry for the handle, one more cost of its failure..."
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:380`:
  > "every device of the unit stays as the unit has it: ... `iospace_attach` and every later request on the unit are `busy`..."

**Scenario / Contradiction:**
On x86-64, remapping handle `h = core * 192 + (vector - 48)` (`1030`) is shared across **all** IOMMU units on the machine. Suppose a driver on node *X* removes an `irq` on `(core, vector)` whose segment uses interrupt remapping behind IOMMU unit *U1*, and *U1* has failed (or fails during the `op 4` IEC invalidation request).
1. By `795`, *"At the end of the last request, done or \*failed\*, the line word is written \*free\*, unclaimed, the remapping entry and the vector are free, and the next step removes the capability."*
2. Immediately thereafter, node *X* (or another node reusing the line/vector if a device/IOAPIC wasn't behind *U1* or via another working unit *U2* / direct delivery) claims `(core, vector)` again, writing a **new** IRTE at handle `h` (e.g. targeting a new device or new vector/priority).
3. Meanwhile, failed unit *U1* never invalidated its interrupt entry cache for `h` (`1043`: *"a unit found failed may still hold a stale entry for the handle"*), and if a line's IOAPIC mask `op 5` itself also answered `*failed*` (held by a node whose unit/controller failed, or if a broken MSI device behind *U1* still triggers DMA writes with the old source ID/address for `h`), *U1* still delivers interrupts to `(core, vector)` using the stale cached IRTE! Freeing `(core, vector)` and `h` lets the new `irq` receive spurious/forged interrupts from the old source under the failed unit.

**Smallest correction:**
Match the `iommu` failure rule (`379`–`380`): if any `op 4` (IEC invalidation) or `op 5` (masking) request during `irq` removal ends with `*failed*`, still finish removing the capability so `cap_delete` terminates, **but** do not free the remapping entry/handle or the vector (keep that `(core, vector)` marked unclaimable/retired for the boot) and, if masking the IOAPIC line failed, do not write the `line_word` back to `*free*` (keep it pinned until restart). Only on all `done` are the line word, remapping entry, and vector freed.

---

### Finding 10 — MEDIUM: Development-image `stopped time` subtraction breaks `idle_until` in `stale` detection

**Locations and verbatim quotes:**
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1283`:
  > "`idle_until`, the instant of its next armed timer when it goes idle (the largest value if none), so a core does not have to beat while idle, and 0 again at its first event after idle"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1294`:
  > "| **stale** | The gate recorded an observation (a core whose word names *X*'s generation, its heartbeat value *h*, instant *t*), and now the heartbeat still reads *h*, now − *t* ≥ `STALE_NS`, and now − `STALE_NS` > `idle_until` ... |"
- `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1662`:
  > "In a development image, every instant that membership and the waits of a node compare is read from the monotonic clock less the stopped time: the instants the gate stamps and compares (an observation's instant, the instant of a seal, the instants of a fence record), the instant an invalidation request started, the start of a wait for a lock, for the quiet word or for a unit (`IOMMU_WAIT_NS` from a submission), the instant a start began (`START_NS`) and its retries, and a core's `idle_until` as it compares with now − `STALE_NS`; so `STALE_NS`, `STUCK_NS`, `CORE_ANSWER_NS`, `FENCE_NS`, `SEAL_NS`, `START_NS` and `IOMMU_WAIT_NS` all leave the stop out, and an instant stored before the stop is still right after it. The clock of user threads, their timers and the scheduling of contexts read the monotonic clock unchanged: a stop is time that passed for them."

**Scenario / Contradiction:**
`idle_until` bridges the two clocks that `1662` explicitly separates (`"monotonic clock less the stopped time"` for membership vs `"monotonic clock unchanged"` for timers), and fails under either possible reading:
1. **Literal reading of `1283` + `1662` (`idle_until` stores raw monotonic timer deadline, `now` is `monotonic - stopped_time`):**
   Suppose since boot the developer has stopped in `gdb` for a cumulative `stopped_time = 10 s`. Now core *p* arms a 5 ms timer at `monotonic = 20 s` (`idle_until = 20.005 s`) and goes idle. Core *p* then crashes/hangs and misses its timer. Other cores compare `now - STALE_NS > idle_until` where `now = monotonic - stopped_time = 20 s - 10 s = 10 s`. Even if `STALE_NS = 100 ms`, `now - STALE_NS` does not exceed `idle_until = 20.005 s` until `monotonic > 30.105 s` — **10 seconds late**! Every prior `gdb` pause cumulatively blinds `stale` detection of an idle core by the total `stopped_time` since boot.
2. **Alternative reading (`stopped_time` subtracted from `idle_until` at comparison, i.e., `idle_until_dev = idle_until - stopped_time` vs `now = monotonic - stopped_time`):**
   Even if `idle_until` had `stopped_time` subtracted in step `1662` (which makes `idle_until` incomparable to raw monotonic when a pause happens *after* `idle_until` was written): suppose `stopped_time = 0`, core *p* arms a timer for `monotonic = 10.010 s` (`idle_until = 10.010 s`), goes idle at `10.000 s`, and at `10.001 s` the developer hits `gdb` for `5 s` (so on resume `monotonic = 15.001 s`, `stopped_time = 5 s`, `now = 10.001 s`). Because the timer was on the **monotonic** clock, on resume its deadline `10.010 s` has already passed; if `stopped_time` (`5 s`) were subtracted from `idle_until`, `idle_until - stopped_time` would be `5.010 s`, so `now - STALE_NS = 9.901 s > 5.010 s` would hold **immediately** upon `gdb` resuming, allowing an observer to falsely accuse healthy core *p* with `stale` before *p* can execute its first interrupt after the debugger lowers `release`!

**Smallest correction:**
When core *p* goes idle (`1283`) in a development image, store `idle_until` as `max(timer_deadline - stopped_time_at_idle, now)` — wait, no, even simpler: membership (`now` in `stale`) compares against `idle_until`, and if `idle_until` is compared on the **membership clock** (`now = monotonic - stopped_time`), then:
- Since a timer fires at `monotonic == timer_deadline` (which could be *earlier* in `now` if a stop occurs while idle, or *no later* than `timer_deadline - stopped_time_at_idle` if no stop occurs), a clean rule is: when a core goes idle at `now` with a timer at monotonic `d`, write `idle_until = d - stopped_time_at_entry_to_idle` (so prior cumulative `stopped_time` does **not** shift `idle_until`!), **and** for the specific case where the debugger stub itself wakes/stops the machine across `d`, either:
  (a) record `idle_until` on the membership clock (`d - stopped_time_at_idle`) and have every core beat/wake or push `idle_until` forward by `delta_stopped` when resuming from the debugger stub if `idle_until != MAX` (or have the stub reset open `stale` windows / grace `STALE_NS` for idle cores whose timer expired during the stop before other nodes observe them), **or**
  (b) keep `idle_until` on the raw monotonic clock and compare `monotonic - STALE_NS - current_stop_elapsed > idle_until` (or track `unstopped_time_since(idle_until)`), which requires a raw monotonic comparison alongside `stopped_time`.
In either case, clarify the exact formula in `1662` so cumulative `stopped_time` from earlier `gdb` pauses never blinds `stale`, and a `gdb` pause spanning `idle_until` never produces an immediate false `stale` on resume.

---

### Finding 11 — LOW: Internal inconsistencies and edition/citation discrepancies

**Locations and verbatim quotes:**
1. **Intel SDM edition contradiction (`80`, `1312` vs `666`):**
   - `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:80`:
     > "**Editions cited (D-135).** Each specification is cited in one edition, the current one on 17 November 2026, named here once; a citation elsewhere gives only the document and the section: the Intel SDM, combined volumes, order 325462-093 (September 2026)..."
   - `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1312`:
     > "Every citation of the Intel SDM in this contract is of the edition named in [Call reference](#call-reference), read on 16 November 2026 (it renumbered the chapters of volume 3 cited before from order 325384-086)."
   - `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:666`:
     > "...(Intel SDM, section "Loads May Be Reordered with Earlier Stores to Different Locations", read in the older edition 253668-032, §8.2.3.4, not in the edition named above)..."
   - **Check against source:** In the combined Intel SDM (specifically `325462-093` / Volume 3A Chapter 11 Memory Ordering, renumbered from old Chapter 8), the section `"Loads May Be Reordered with Earlier Stores to Different Locations"` is **Volume 3A, §11.2.3.4** (`325462-093`). Citing `253668-032, §8.2.3.4` in `666` directly contradicts both `80` and `1312`.
2. **`untyped_retype` `Again` under L1 vs L2 (`665` vs `1746`, `1775`):**
   - `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:665`:
     > "**The rule holds under both variants (D-137):** under L1 the events of a node run one at a time under the node lock, but the two lock-free paths (the slot read, which finds an object before the lock, and the atomic OR of a `signal` on a notify's word, made before it) read and write object memory outside the lock, so the watermark rule reads the entry words there too..."
   - `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1746` & `1775`:
     > "| 6 | `UntypedRetype` | unchanged | Under variant L2, `Again` while the watermark is ready to return and another core of the node is still in the kernel event it was in at the last destruction (D-135); `Again` under variant L2 only, with nothing changed (D-134, D-135) |"
     > "`Again` is a new result of fourteen calls under variant L2, with nothing changed: those [A node of several cores](#a-node-of-several-cores) lists (D-134, D-135), in the rows above."
   - **Contradiction:** `665` (updated by D-137) explicitly extends the `entry_word` / `again` watermark check to **L1** as well as L2, whereas `1746` and `1775` still state `"Under variant L2, Again..."` and `"Again under variant L2 only"`.
3. **Intel VT-d revision / order number check (`80`):**
   - Line `80` cites *"the Intel Virtualization Technology for Directed I/O Architecture Specification (VT-d), revision 5.20, order D51397-019 (April 2026)"*. Publicly indexed Intel Developer Zone listings identify VT-d **Version 5.2** dated **14 May 2026** (Doc ID `671081` / `774206`), whereas order string `D51397-019` and date `April 2026` did not appear in indexed pages; the cited technical sections (`§5.1.5.1`, `§6.2.2.1`, `§6.5.2.8` / Figure 6-8, `§11.4.2`) match Version 5.2 accurately.

**Smallest correction:**
- Replace `(read in the older edition 253668-032, §8.2.3.4, not in the edition named above)` in `666` with `§11.2.3.4` (of `325462-093`).
- Update `1746` (and `1775`) so `UntypedRetype`'s watermark-wait `Again` applies under **both L1 and L2** (while L2 tries `Again` remains L2-only).
- Verify the VT-d PDF header for `D51397-019` / `April 2026` vs `Version 5.2` / `May 2026` in `80`.

---

## What I checked and found correct

- **Single-escalator vs single-enterer `quiet_word` four-order proof (`666`):** With `XCHG` (x86-64), store + `DMB ISH` (ARM64), and store + `fence rw,rw` (RISC-V) at kernel entry, paired with the escalator's atomic add + fence before reading `entry_word`, the four linearizability outcomes hold for one escalator against entering cores (only concurrent escalators deadlock as found in Finding 1).
- **Escalation frequency bound (`666`):** One escalation consumes two `again` calls plus the escalated call (`3 * c`), capping escalations per period of budget `b` at `b / (3 * c)`.
- **`cspace` sweep position on first-unit `again` (`660`, `128`):** Line `128` defines *"a slot counts as examined when the sweep moves past it, so a full slot is not counted while its capability is being removed."* Thus advancing `sweep` up to a full slot before its first-unit try (`660`) does not skip that slot if the first unit returns `again`.
- **`task_revoke` first call (`1144`, `680`):** Locks the task, at most *N* − 1 ≤ 63 running threads, their cores, and the gate (`128` locks) before writing `revoked` and marks; failing a try in both rounds leaves nothing written.
- **`STALE_NS` and `STUCK_NS` startup bounds (`1504`):** `STALE_NS > CORE_ANSWER_NS + E` covers waiting on `quiet_word` (`<= E + (N - 1)*B1max < CORE_ANSWER_NS`) plus one event (`<= E`) before the exit heartbeat, and `STUCK_NS > recovery_period + CORE_ANSWER_NS + E` covers waiting up to one recovery reserve period (`10 ms`) plus `CORE_ANSWER_NS + E` before draining a kernel ring. (Only L2 `CORE_ANSWER_NS` itself undercounts `E`, Finding 7.)
- **External citations verified against primary/indexed documentation:**
  - **Arm DDI 0487:** `B2.3.1` (*"TLBI Effects, Completed TLBI Effects and Invalidation Scopes"*), `C5.5.60` (`TLBI VAE1IS`), `C5.5.11` (`TLBI ASIDE1IS`), `D8.17.1` (break-before-make requirements), `D8.17.7` (broadcast scope), `D8.17.8` (completion with `DSB`), and `C5.2.1` (`ALLINT`). Note: the six-letter architecture rule identifier `IWZCBG` cited under `D8.17` in `333` could not be verified through public web indexing (`developer.arm.com` 6-letter rule IDs are not indexed in search snippets).
  - **Intel VT-d:** `§5.1.5.1` (*"I/OxAPIC Programming"* — `Interrupt_Index[14:0]` in bits `63:49`, `Interrupt_Index[15]` in bit `11`, bit `48` set, vector matching IRTE for level lines), `§6.2.2.1` (`DID = 0` forbidden when `CM=1`, matching `SSPTPTR` per `DID`), `§6.5.2.8` / Figure 6-8 (`IIDX` bits `47:32`, `IM` bits `31:27`, `G` bit `4`), `§11.4.2` (*"Capability Register"* `ND` bits `2:0`, `0 -> 16`, `6 -> 64K`).
  - **Arm PSCI (`DEN0022`):** Sections `5.1.7` (`MIGRATE_INFO_TYPE`), `5.1.8` (`MIGRATE_INFO_UP_CPU`), and `5.9` (`CPU_OFF` / `DENIED` / hot-unplug behavior) match indexed `DEN0022E`/`DEN0022F` text; exact `DEN0022F.b` sub-revision PDF was not directly retrieved.
- **Repository state:** `architecture/kernel-interface.md` and `decisions/README.md` are internally cross-linked cleanly on Pass 19 items not listed in Findings 1–11 (e.g., `656` unit request / service / ring lock assignment to `gate`, `355`–`362` `AttachWord` state transitions when non-concurrent, `770` `IRQ_LINES_MAX` indexing across sparse ARM64/RISC-V ranges).

---

## What I did not check

- **Recovery-reserve worst-case execution vs `STUCK_NS` (`1504`, `973`, `1361`):** Whether a full `156 µs / 10 ms` recovery reserve can service up to `64` kernel-ring `Revoke` (32-unit) or `ReportAsk` steps inside one `STUCK_NS` (`100 ms`) window when heavily loaded across multiple dying/reclaiming peers.
- **Unmodified sections from earlier passes:** Architecture-specific RISC-V AIA / ARM64 GICv3/ITS bitfields, register-block encodings, `plan/progress.md`, and Rust/Python implementation or explorer files outside `Docs/architecture/kernel-interface.md` and `Docs/decisions/README.md`.
- **Non-public PDF details:** Arm DDI 0487 `IWZCBG` rule code verbatim text, exact `DEN0022F.b` cover revision string, and Intel VT-d `D51397-019` cover order number.
