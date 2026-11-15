# Draft: the memory and devices group of the call reference

Group: MEMORY and DEVICES. Written for the current rule on clearing (the kernel does not clear frames). Author: the assistant, 14 November 2026, for re-reading.

Contents: (1) the text to paste into `kernel-interface.md`; (2) changes needed elsewhere in the contract; (3) for the humans; (4) what a reference model of this group must cover; (5) sources.

---

## 1. Text for kernel-interface.md

To insert in "Call reference, one core", after "Notifications" and before "Registers".

### Memory and devices

**Proposed, 14 November 2026**, to re-read by the two humans. It covers frames, address spaces, page faults, the IOMMU and the calls `aspace_map`, `aspace_unmap`, `aspace_protect`, `iospace_map`, `iospace_unmap` and `iospace_attach`. The rules of the sections above apply unchanged: order of checks, dying objects, removal in bounded steps. The points marked **(design choice)** are the ones where another answer was reasonable.

#### Frames

- A frame has a **page size** (4 KB, 2 MB or 1 GB), a **number of pages** from 1 to 512, a **memory type** and a kind of memory (ordinary or device). All four are fixed by `untyped_retype` and never change. Its pages are physically contiguous and aligned on the page size.
- **At most 512 pages per frame (design choice).** One frame then fills at most one table of 512 entries, so mapping, unmapping or changing the rights of a whole frame writes at most 512 entries, and every one of these calls is bounded without a resumption point. A larger block is several frames. The alternative, frames of any size, needs a mapping that progresses over several calls and a record of how far it got.
- The **memory type** is write-back for ordinary memory (the only value accepted there). For device memory it is uncached or write-combining. It belongs to the frame and not to a mapping, so every mapping of the same physical pages has the same type. Processors do not support one physical page mapped with two types (from memory: Intel SDM, volume 3, on page attribute aliasing).
- A frame on device memory never has `exec` (rules of `untyped_retype`).
- **What a new frame holds.** The kernel does not clear frames (rules of `untyped_retype`). A new frame holds what its memory last held. That includes the memory of kernel objects destroyed earlier in the same untyped: saved registers, message words, capability slots with kernel addresses. Whoever hands an untyped to a less trusted party clears it first, through a frame that it maps. This is the current rule; see "For the humans".

#### Mapping records

- **A frame capability holds one mapping record, empty or full.** A full record holds: the space (an `aspace` or an `iospace`), the address of the first mapped page, the first page of the frame that is mapped, the number of pages mapped, and the rights of the mapping. The page size and the memory type come from the frame. The mapped pages are pages *first* to *first + count − 1* of the frame, at consecutive addresses.
- **Every translation in a space belongs to exactly one record**, and every full record names exactly the translations it made. The space keeps a list of the capabilities whose records name it, most recently mapped first. The links of that list live in the capability slots, so they cost no memory beyond the slot (see Object sizes).
- **What happens to the record when the capability changes:**
  - `cap_derive` from a frame capability: the new capability has an empty record. The source keeps its own. This is how the same pages are mapped twice: each mapping needs its own capability (as in seL4, from memory).
  - `cap_move`, also by IPC: the record moves with the capability, and the mapping does not change. The kernel updates the two neighbours in the space's list and the space's head if needed. The cost does not depend on the size of the mapping.
  - Removal of a frame capability (by `cap_delete`, as a descendant in `cap_revoke` or `cap_delete`, or in the sweep of a dying capability space): if its record is full, the mapping is undone in the same step, before the slot is freed, exactly as `aspace_unmap` or `iospace_unmap` would undo it. This counts as the removal of one capability among the 32 of a step, whatever the number of pages.
  - `cap_revoke` on a frame capability: every descendant is removed, so each mapping made through a descendant is undone. The capability's own mapping stays.
  - The frame itself is destroyed only once its root capability is removed, which comes after all its descendants. Its memory therefore never returns to the untyped while a translation to it exists. The same holds for an untyped revoked with frames made from it.
- `cap_inspect` on a frame capability returns badge 0 and says nothing of the record (**design choice**: whoever mapped the capability knows where; a capability received by IPC can be unmapped at once, and `aspace_unmap` succeeds whether or not it was mapped).

#### Address spaces and their tables

- An `aspace` is made by `untyped_retype` from ordinary memory. It is 8 KB: its root table (4 KB) and a header. The kernel clears it and writes into the root table the entries it shares with every address space: its own half, and the **reserved slot** described below. A new `aspace` translates nothing in the user range.
- **The user range and the reserved slot.** On x86-64 with four levels of tables, the user range runs from 0 to 255 × 512 GB (0x7F80_0000_0000). The next 512 GB, the last root entry of the lower half, form the reserved slot. It holds the pages that the kernel shares with every address space: the kernel-supplied code page and the clock page. Their tables belong to the kernel and are shared by every address space. The start-up page publishes the user range, the addresses of the shared pages and the page sizes the processor supports. Any range that goes beyond the user range is `invalid`, so it can never overlap the reserved slot.
- **Lower tables come from the untyped the aspace was created from (design choice).** `aspace_map` takes a capability for that untyped. Any capability for the same untyped object is accepted, as for `cspace_grow`. A table is 4 KB, taken at the watermark (aligned on 4 KB) and cleared. It counts as a live piece of the untyped, as a segment of a capability space does, until the aspace is destroyed. No object depends on two untypeds, and the tables of a process are paid for by the memory it was given. The alternative, as in seL4, makes page tables objects that user space creates and maps itself. That puts the levels of the architecture into the interface, which [Architectures](#architectures) rejects.
- **A table that becomes empty goes to the free list of its aspace (design choice).** The kernel knows, for every table, the number of its entries that are present (where it keeps that count is up to the architecture layer). When an unmap leaves a table with no present entry, the table is unhooked from its parent and placed at the head of the aspace's free list, and its parent may become empty in turn. An aspace takes tables from its free list first (most recently freed first), then from its untyped. A table never goes back to the untyped before the aspace is destroyed: the watermark rule forbids it. Because of this rule a hooked table always has at least one present entry, so an address range in which nothing is translated holds no table either, and a large page can be mapped wherever nothing is translated. The alternative, never unhooking a table, would forbid a large page for ever in any slot that once held small pages.
- **The start-up aspace** was created from no untyped. The kernel builds it with the tables that the boot image's mappings need, plus the reserve of free tables that the boot image states. It never takes a table from an untyped: for it, an untyped argument other than 0 is `invalid`. This mirrors the start-up `cspace`.

#### Calls on address spaces

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `aspace_map` | aspace, frame, untyped, address, first page, page count, rights | | `write` on the aspace. On the frame, the rights asked for (judged with the plain arguments, `denied`). `write` on the untyped, which may be 0. Otherwise it must be a capability for the untyped the aspace was created from (`invalid`, judged right after its three checks). Maps pages *first page* to *first page + page count − 1* of the frame from *address*, with the frame's page size and memory type |
| `aspace_unmap` | frame | | No right on the capability itself, as for `cap_delete`: it can only take access away. Succeeds without effect if the record is empty. `busy` if the record names an `iospace` |
| `aspace_protect` | aspace, frame, rights | | `write` on the aspace. On the frame, the rights asked for (`denied`, with the plain argument). Replaces the rights of the whole mapping. `busy` if the record does not name this aspace |

The checks of `aspace_map`, in the order of [Order of checks](#order-of-checks):

1. The aspace: slot, kind, `write`. A dying aspace is `gone`.
2. The frame: slot, kind. No right is judged here, since the rights needed depend on the rights argument. Then the untyped, unless it is 0: slot, kind, `write`, then that it is the aspace's own untyped (`invalid`; any untyped is `invalid` for the start-up aspace). A dying frame or untyped is `gone`.
3. The plain arguments, in this order, each `invalid` if it fails:
   - the address is a multiple of the frame's page size;
   - the first page is less than the frame's number of pages;
   - the page count is at least 1, and first page + page count does not exceed the number of pages;
   - the range, from the address to the address plus page count times page size, lies inside the user range (computed without overflow);
   - the rights word: a bit other than `read`, `write` and `exec` is `invalid`; a word without `read`, or with both `write` and `exec`, is `invalid` (write or execute, never both, per mapping: **design choice**, see below); a word that is not a subset of the frame capability's rights is `denied`.
4. The state, in this order:
   - the frame capability's record is full (`busy`, even if it names this aspace);
   - some address of the range is already translated, by a page of any size (`busy`);
   - the tables the mapping needs are more than the aspace's free list and its untyped can supply (`no_memory`). An untyped of 0 supplies none. The untyped can supply as many 4 KB tables as fit between its watermark, aligned up to 4 KB, and its end. Nothing is taken when this fails.

Effect of `aspace_map`. The missing tables on the paths to the target entries are taken (free list first, then the untyped) and hooked in. The entries are written: present, user-accessible, with the frame's memory type, the rights asked for, and the page size of the frame. The record is filled and the capability is placed at the head of the aspace's list. No thread is woken. In particular a thread that waits for the answer to its fault stays waiting: only the answer resumes it (**design choice**: resuming it here would mean searching the threads that faulted in the range).

Effect of `aspace_unmap` on a full record that names an aspace (dying or not). Its entries are cleared. The tables left empty are unhooked and placed on the free list. The translations of the range are invalidated (see [TLB](#tlb-one-core-and-several)). The record is emptied and the capability leaves the aspace's list. Checks: the frame (slot, kind; a dying capability or frame is `gone`), then the state (`busy` if the record names an `iospace`).

Effect of `aspace_protect`. The entries of the mapping are rewritten with the new rights, the record's rights are replaced, and the translations of the range are invalidated. Asking for the rights the mapping already has succeeds and changes nothing. Checks: the aspace (`write`; dying is `gone`); the frame (slot, kind); the rights word, as for `aspace_map`; the state (`busy` if the record is empty or names another space). Unlike `aspace_unmap`, this call needs the aspace capability, because it can also *add* rights (copy on write gives write back to the last sharer).

- **Write or execute, never both, per mapping (design choice).** The kernel refuses a mapping that is both writable and executable. The same frame can still be writable through one capability and executable through another, in the same space or in two spaces. This is how the compile service hands over code, and a JIT can work the same way. The alternative, no rule in the kernel, leaves the rule of [memory.md](memory.md#other-rules) to every caller. A mapping is always readable, because the processors of version 1 cannot express write-only or execute-only in an ordinary page table.
- **Unmapping and protecting act on a whole record, never on part of one (design choice).** The kernel therefore never splits a large page or a mapping. To change the rights of part of a frame, the memory service maps that part through its own capability, which is derived for the purpose. Unmapping by address range would need a way back from a translation to its record.
- **Bounds.** `aspace_map` writes at most 512 entries. It takes and clears at most 6 tables: with four levels, a run of at most 512 pages crosses at most 2 tables at each of the three lower levels. `aspace_unmap` clears at most 512 entries and unhooks at most 6 tables. `aspace_protect` rewrites at most 512 entries. Each call then does one invalidation of at most 512 translations, or of the whole tag (see below).

#### Large pages

- The page size of a mapping is the page size of the frame. The kernel never maps a 2 MB frame with 4 KB entries, or the reverse (**design choice**: one frame, one size, which keeps the record small and removes splitting). Whoever needs 4 KB granularity makes 4 KB frames.
- A page size that the processor does not support is `unsupported` in `untyped_retype` (judged right after the page size value), so no frame of that size exists. The start-up page lists the supported sizes. The memory service decides when to use 1 GB pages ([memory.md](memory.md#page-sizes) places that after the alpha). The kernel supports them from the first version.
- A large page is placed in a slot of its level only if nothing in that slot is translated. A slot that once held small pages has lost its table, by the free-list rule, once the last of them is unmapped.

#### Device memory

- A frame on device memory can be mapped into an `aspace` (a driver's registers) and into an `iospace` (reserved regions that a device needs at fixed addresses, peer-to-peer transfers). The kernel never reads or writes device memory.
- The memory type of a device frame is uncached or write-combining, chosen in `untyped_retype`. `exec` never exists on device memory.
- The registers of the IOMMU units, and of any other device the kernel drives itself, are in no device untyped given at start-up. No capability can therefore map them.

#### Faults

A fault is not a call. The kernel turns it into a message on the thread's fault endpoint, sent on behalf of the faulting thread.

- **Kinds**, in the label of the message:
  1. page fault: an access to an address that is not translated, or with a right the translation does not give;
  2. no address space: the thread would return to user mode, but it is bound to no `aspace`, or to one that is dying or destroyed;
  3. exception: any other processor exception caused by the thread (illegal instruction, protection, divide, breakpoint);
  4. budget overrun: reserved; its content is defined with the scheduling group.
- **Words** (4, so the message fits in registers): the address of the access (0 for kinds 2 and 3), the access (bit 0 read, bit 1 write, bit 2 execute, bit 3 *present*: the address was translated but without the right needed; 0 for kinds 2 and 3), the instruction pointer, and an architecture code (for kind 1 the error code of the processor; for kind 3 the vector in the high 32 bits and the error code in the low 32 bits; 0 for kind 2). No capability. The badge is the badge of the fault endpoint capability given to `thread_configure`, which the thread keeps with the binding. Marks and task identifier are those of the faulting thread, as for any message it sends.
- **Delivery is a `call`.** The kernel makes it with wait number 0 and an empty receive range, with the rules of `call`. If a thread waits to receive on the endpoint, the message is delivered, that thread's reply object is armed with the faulting thread, and the faulting thread waits for the reply. Otherwise it joins the endpoint's queue, first in, first out. The kernel keeps the four words in the thread object, not in the thread's message page, and changes none of the thread's registers.
- **No handler.** If the thread has no fault endpoint, or the endpoint is dying, the thread becomes suspended at once and the fault is dropped. Its registers are unchanged, so resuming it executes the same instruction again.
- **The answer.** An answer with label 0 resumes the thread at the instruction that faulted, which runs again. For kind 2 raised at the end of a call, the thread resumes just after that call, with the call's result in its registers. Any other label leaves the thread suspended, as `thread_suspend` would, and drops the fault. The words of the answer are ignored. Since the receive range is empty, no capability moves: `send` reports `caps_dropped`, as for any delivery without slots. A thread that was suspended while it waited stays suspended, and runs from the faulting instruction when it is resumed.
- **A fault wait that ends without an answer** leaves the thread suspended and drops the fault. This happens when the endpoint or the reply object is destroyed (`gone`) or when `thread_cancel` is called with wait number 0 (`cancelled`). `thread_cancel` with any other number never ends a fault wait, because its number is 0.
- A thread that waits on a fault waits in the sense of `thread_configure` (`busy`).
- The state of the faulting thread's capability space plays no part: a fault moves no capability.

#### A thread and its address space

- `thread_configure` binds the thread to the aspace object, not to the capability. The thread is placed at the head of the aspace's list of bound threads, after leaving the list of its previous aspace. Revoking the capability used does not unbind it, as for the capability space ([Rights are checked when a call is made](#the-derivation-tree)).
- **A thread bound to no aspace, or to a dying or destroyed one, never runs user code (design choice).** Each time it would return to user mode, it raises a fault of kind 2 instead. A supervisor learns of it on the fault endpoint and decides. The alternatives were to suspend the thread silently, which a supervisor cannot see, or to destroy it, which the kernel never does to an object whose root capability lives.
- The fault endpoint is bound in the same way, to the endpoint object with the badge of the capability given. Destroying the endpoint unbinds every thread whose fault endpoint it is.

#### Destruction of an address space

- An aspace is dying from the first step of a removal that reaches its root capability (rule of [Removal ends](#the-derivation-tree)). In that step the kernel invalidates every translation tagged for it. It never makes it the current space of a core again, since its threads no longer run user code.
- When the root capability is the next to remove, the kernel first empties the record of each capability in the aspace's list, most recently mapped first. Then it unbinds each thread of its list, most recently bound first: the thread is bound to no aspace. Emptying a record does not touch the tables, which die with the aspace. Each record emptied and each thread unbound counts as one of the 32 of a step. Then the root capability is removed. The aspace is destroyed and its own memory and all its tables, hooked or free, stop counting as live pieces of the untyped, in the same step.
- Between two steps, a record still full names a dying aspace. `aspace_unmap` on it works as usual.
- Destroying an endpoint unbinds, in the same way and with the same count, each thread whose fault endpoint it is, after waking the threads that wait on it.

#### TLB, one core and several

- **Guarantee.** When a call returns (or a removal step returns `again`), no thread on any core can use a translation that the call removed or reduced. Translations that were added may cause no fault.
- **One core.** The kernel invalidates the translations of the range on its own core before it returns: page by page, or the whole tag of the space when that is cheaper. The tags (PCID on x86-64) are given by the architecture layer from a fixed table of the node and recycled with a full invalidation. They are invisible to user space.
- **Several cores (the hook, decided now).** An aspace holds a copy per node of its core group ([kernel.md](kernel.md#multi-core-structure)). Its header holds the set of those nodes and the number of acknowledgements outstanding. On one core the set is the own node and the number is 0. A change (map, unmap, protect, removal of a record) is applied to the home copy, then sent to every other node of the group. Each of them applies it to its copy and invalidates its own translations before it acknowledges. The call returns only when every acknowledgement is in. Meanwhile the calling thread waits in a state reserved for this, *waiting for the core group*, which the one-core reference never uses. A record names its space by node and address, so a record can name the copy of another node. This is the memory ownership invariant: every remote mapping is recorded on both sides. Which untyped pays for the tables of a remote copy is settled by the multi-core part.

#### IOMMU

The kernel programs the IOMMU (rule of [drivers.md](drivers.md#iommu)).

- **IOMMU units.** At start the architecture layer reads the list of IOMMU units from the firmware: on x86-64, only the DRHD entries of the ACPI DMAR table (register address, PCI segment). It turns every unit on before the first process starts. By default every device is blocked: no DMA reaches memory. The memory for the units' own tables (root and context tables, 1 MB and 4 KB per unit on x86-64) is taken at start from the boot node's share, once, and never grows.
- **`iommu` objects.** The kernel makes one `iommu` object per unit at start, with its root capability in the start-up space (the start-up page gives the slots). `untyped_retype` never makes one (`invalid`). It names the unit, and with `manage` it gives the right to attach any device identifier of that unit to an `iospace`. The kernel does not check that a device belongs to the unit's scope: discovering the devices is the platform service's job. A device attached through the wrong unit stays blocked, since its own unit still blocks it.
- **Devices the kernel uses itself** (the USB debug port, if the kernel drives it) are attached by the kernel to a domain of its own. Their identifiers are `busy` for `iospace_attach`.
- **`iospace` objects.** An `iospace` is made by `untyped_retype` from ordinary memory, 8 KB (root table and header). Its tables come from its untyped, with the same rules as for an aspace (free list, `no_memory`). Its address width and page sizes are the ones every unit supports, published in the start-up page (on x86-64, 48 bits if every unit supports four levels, otherwise 39). An iospace serves devices of one unit at a time, at most 16 of them. Its header lists them.

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `iospace_map` | iospace, frame, untyped, device address, first page, page count, rights | | As `aspace_map`, with these differences. `write` on the iospace. The frame's page size must be one that every unit supports (`unsupported`, the first plain check). The range must lie inside the iospace's address width. The rights word is a non-empty subset of `read` and `write` (`invalid` otherwise, `exec` included), and a subset of the frame capability's rights (`denied`). Device memory is accepted |
| `iospace_unmap` | frame | | As `aspace_unmap`. `busy` if the record names an `aspace`. If the iospace serves devices, the unit's translation cache is invalidated before the call returns |
| `iospace_attach` | iommu, iospace, device | | `manage` on the iommu, `manage` on the iospace, which may be 0 to detach. The device is a plain identifier whose form the architecture layer fixes (x86-64: bus, device and function in 16 bits, within the unit's segment; higher bits set are `invalid`) |

Rules of `iospace_attach`:

- With an iospace, the state is judged in this order:
  - the device is one the kernel uses (`busy`);
  - the device is attached to another iospace (`busy`; detach it first);
  - the device is already attached to this iospace (success, nothing changes);
  - the iospace serves devices of another unit (`busy`);
  - the iospace already serves 16 devices (`busy`);
  - the unit has no free domain number (`busy`).
  Then the unit's context entry for the device points at the iospace's tables, under the iospace's domain number for that unit, given at its first device and freed with its last. The device is added to the iospace's header. The unit's caches are invalidated.
- With iospace 0: if the device is attached, its context entry is cleared (the device is blocked again), it leaves the iospace's header, and the caches are invalidated. Otherwise the call succeeds without effect. Detaching a device of a dying iospace works.
- A dying iospace is `gone` for `iospace_map` and `iospace_attach`. Its destruction, when its root capability is the next to remove, first detaches each of its devices (most recently attached first), then empties each record of its list (most recently mapped first). Each counts as one of the 32 of a step. When the first device is detached, the unit's caches for its domain are invalidated, so no device reaches its tables.
- Destroying an `iommu` object detaches the devices attached through it, in increasing order of identifier. A step detaches at most 32 and examines at most 128 identifiers (the budgets of a sweep). The unit stays on and blocks every device of its scope until the next start.
- **Invalidations of the IOMMU wait for the hardware (design choice).** An unmap is not over until the unit has confirmed that no device can still use the translation. Otherwise the memory could return to its untyped while a device still writes into it. The kernel waits for the confirmation. A unit that does not confirm within 1 ms (provisional) is a hardware fault of the node that owns it, handled by [recovery](kernel.md#recovery-of-one-cores-kernel). The invalidations of one call, or of one removal step, are grouped into one wait before the call returns.
- **No device-side translation caches, no device page faults, no shared process address spaces (design choice).** The kernel enables neither ATS nor PRI nor PASID. A device that caches translations itself could keep using them, and invalidating them can take up to a minute under the PCIe rules (from memory). A device sees only its iospace. The cost: no shared virtual memory between a process and a device.
- **DMA faults are blocked and not reported (design choice).** The unit blocks the access. The kernel clears the fault record and writes it to the trace buffer. User space learns that a device is broken through the class interface (requests that do not finish), and the driver manager restarts it ([drivers.md](drivers.md#restart-of-a-driver)). Reporting to user space would need a `notify` binding and a record queue in the kernel.
- **The caller chooses device addresses (design choice, as seL4; Zircon's `zx_bti_pin` returns addresses chosen by the kernel).** The driver, or its emulation layer for `dma_map`, places its buffers. The kernel keeps no allocator of device addresses.
- **Bounds.** As for the calls on an aspace, plus one wait on the unit per call. `iospace_attach` writes one context entry.
- Interrupt remapping belongs to the interrupt group.

---

## 2. Changes needed elsewhere in the contract

Each item quotes the present text and gives the change.

1. **Objects, row `frame`.** "A run of physical pages of one size (4 KB, 2 MB, 1 GB)" becomes "A run of 1 to 512 physical pages of one size (4 KB, 2 MB, 1 GB), with a memory type".
2. **Objects, new row** `iommu`: "One IOMMU unit, made by the kernel at start. With `manage`, attaches devices of that unit to an `iospace` | Project". Kind number 16 (see the abi list below).
3. **Objects, sentence on device memory.** Add: "The registers of the IOMMU units, and of any device the kernel drives itself, are in no device untyped."
4. **System calls, row Memory.** "`aspace_map` accepts a run of frames and a page size, so one call maps a large block" becomes "`aspace_map` maps up to 512 pages of one frame, so one call maps up to 2 MB, 1 GB or 512 GB depending on the page size of the frame".
5. **System calls, row Interrupts and devices.** Add in the notes: "`iospace_attach` takes an `iommu` capability and a device identifier".
6. **"Faults are not calls..."** (end of System calls). Add: "The message, its delivery and the answer are specified in [Faults](#faults)."
7. **`untyped_retype` row.** "the page size and the number of pages for a frame" becomes "the page size, the memory type and the number of pages (1 to 512) for a frame". Add: "An `iommu` is never made by this call (`invalid`)."
8. **Order of checks, step 3.** "the kinds of the groups not yet specified: time, tasks, interrupts, devices, debugging, cores" becomes "...: time, tasks, interrupts, `ioports`, debugging, cores". Add: "for a frame, the page size value is judged first (`invalid`), then whether the processor supports it (`unsupported`), then the memory type (`invalid` if it does not suit the kind of memory), then the number of pages (`invalid`)".
9. **Rules of `untyped_retype`, the clearing sentence.** Keep the rule. Add the consequence, which is not written today: "A new frame therefore holds what its memory last held, including the memory of kernel objects destroyed earlier in the same untyped." (Or replace the rule, if the humans choose otherwise: see 3.1.)
10. **Rules of `untyped_retype`, rights.** Add: "an `aspace` and an `iospace` are cleared, and the kernel writes into the root table of an `aspace` the entries it shares with every address space."
11. **The derivation tree, the removal-step bullet.** After "at most 32 capabilities are removed or threads woken", add: "or mapping records emptied, threads unbound from a dying `aspace` or endpoint, or devices detached. Removing a frame capability with a full record undoes its mapping in the same step and counts as one."
12. **The derivation tree, "Destroying an object wakes every thread that waits on it".** Add: "Destroying an endpoint then unbinds the threads whose fault endpoint it is; destroying an `aspace` empties the records that name it and unbinds its threads; destroying an `iospace` detaches its devices and empties its records (see [Memory and devices](#memory-and-devices))."
13. **Threads, `thread_configure` row.** Add: "The thread is bound to the objects, not to the capabilities, and keeps the badge of the fault endpoint capability, which its fault messages carry. Binding to an aspace places the thread in that aspace's list of bound threads."
14. **Threads, gap outside this group.** The message page ("Each thread has one page shared with the kernel", Messages) is not placed anywhere: no call names it, and a 1 KB thread object cannot hold it. To settle with the threads group. My recommendation, from the seL4 model (from memory): a frame capability given to `thread_configure`, mapped by the caller in the thread's aspace, its address recorded in the thread. The kernel then reads it only through that mapping, and a fault of the kernel on it is impossible because the frame stays mapped while it is bound.
15. **Object sizes.**
    - "Capability slot | 32 bytes (object, rights, badge, links of the derivation tree)" becomes "64 bytes (object, rights, badge or mapping record, links of the derivation tree, links of the list of records of a space)". Reason: a full record (space, address, first page, count, rights) and its two list links do not fit beside the object and the tree links in 32 bytes. See 3.3.
    - `aspace`, `iospace`: "One root table (4 KB); lower tables are taken from supplied memory as mappings need them" becomes "8 KB (root table and header); lower tables of 4 KB each are taken from the untyped the space was created from".
    - `frame`: add "at most 512 pages".
    - New row `iommu`: "Memory of the kernel, taken at start; none from an untyped".
    - `cspace`: "32 bytes per slot" becomes "64 bytes per slot".
16. **Slots and addresses.** "`cspace_grow` adds one segment of 128 slots (4 KB)" becomes "(8 KB)". The maximum, the directory and the 32,768 calls to kill a full space do not change.
17. **Start-up information.** "the control capabilities for interrupts, I/O ports and IOMMU domains" becomes "the control capabilities for interrupts and I/O ports, and one `iommu` capability per IOMMU unit". Start-up page: add an entry *memory layout* (user range, reserved slot, addresses of the code page and the clock page, page sizes of the processor, address width and page sizes of the iospaces) and an entry *IOMMU units* (for each unit: slot of its capability, PCI segment, number of domains). Add: "The start-up aspace is built by the kernel with the tables of the boot image's mappings and the reserve of free tables the boot image states; it never takes tables from an untyped."
18. **Architectures.** "The kernel needs only a timer, an interrupt controller and a serial port from the platform" becomes "...a serial port and the list of IOMMU units (on x86-64 the DRHD entries of the ACPI DMAR table, read at start; nothing else of ACPI)". See 3.2.
19. **Pager.** "maps it in one `aspace_map`" stays true if the run is one frame. "A blob that is mapped whole ... is supplied in one call" becomes "in one call per frame of up to 512 pages".
20. **Open points.** Remove "Who clears frames" once 3.1 is decided. Remove "what becomes of a thread whose address space or fault endpoint is destroyed" (settled in [A thread and its address space](#a-thread-and-its-address-space) and [Faults](#faults)).
21. **memory.md, Address space.** "Page tables are the only source of truth, with no second structure to keep coherent" becomes "Page tables are the only structure that translates. The mapping record in a frame capability names a mapping and is kept coherent with it by the kernel; it is not a second translation map." (The contract already puts the record in the slot.)
22. **memory.md, Other rules, Drivers.** "Pinned memory through a separate capability" is satisfied by a derived frame capability mapped in the driver's `iospace`: the frame cannot be freed while that mapping exists, and revoking it unmaps it from the device first.
23. **devices.md** is about device-to-device communication and needs no change.
24. **Model, `lib.rs` header comment.** "Not modelled: what address spaces, frames ... do once created" stops being true once this group's model is written. The `thread_configure` CONTRACT-GAP is settled.

**Values `abi/` must gain:**

- Call numbers: none. `aspace_map`, `aspace_unmap`, `aspace_protect`, `iospace_map`, `iospace_unmap` and `iospace_attach` already exist (in the order of `Call`: 7, 8, 9, 32, 33, 34). The next new call stays at 46.
- Error codes: none.
- `ObjectKind::Iommu = 16`.
- `SLOT_BYTES = 64`, `ASPACE_BYTES = 8192`, `IOSPACE_BYTES = 8192`, `TABLE_BYTES = 4096`, `TABLE_ENTRIES = 512`, `FRAME_MAX_PAGES = 512`, `IOSPACE_MAX_DEVICES = 16`, `IOMMU_WAIT_NS = 1_000_000` (provisional).
- `MemoryType { WriteBack = 0, Uncached = 1, WriteCombining = 2 }`.
- Mapping rights: `MAP_RIGHTS = READ | WRITE | EXEC` (the bits of `Rights`; no new bits).
- Fault message: `FAULT_PAGE = 1`, `FAULT_NO_ASPACE = 2`, `FAULT_EXCEPTION = 3`, `FAULT_BUDGET = 4` (reserved), `FAULT_WORDS = 4`. Access bits: `ACCESS_READ = 1 << 0`, `ACCESS_WRITE = 1 << 1`, `ACCESS_EXEC = 1 << 2`, `ACCESS_PRESENT = 1 << 3`. Answer: `FAULT_RESUME = 0` (any other label suspends).
- `StartKind::Memory = 9`, `StartKind::Iommu = 10`.
- Kani proofs to add: a pure function that checks the plain arguments of a mapping (alignment, range without overflow, rights word), with the property that an accepted range lies inside the user range and holds at most 512 pages.

---

## 3. For the humans

### 3.1 Who clears frames (not decided; the group above follows the current rule)

**What the current rule leaves open.** The kernel clears its objects when it creates them, not frames. Memory returns to an untyped only as a whole, when its last object is destroyed. So a frame made from a reused untyped shows what was there before: user data of the previous holder, and also the kernel objects destroyed in that untyped. Those hold the registers and message words of threads, slots with kernel addresses (which defeats address randomisation of the kernel), and the derivation links. The argument of the contract ("the holder of an untyped already has authority over that memory") is true for user data. It is not true for kernel data: no holder ever had a right to read the registers of another process's thread or the kernel's addresses.

**What the other kernels do.**

- **seL4** clears an untyped when it is *reset*: when it is retyped again with no remaining child, before the new objects are made. Device untypeds are never written. A large untyped is cleared in chunks with a preemption point after each one. Objects are then created in memory that is already clear. Verified in the source (`resetUntypedCap` in `src/object/untyped.c`; `invokeUntyped_Retype` calls it first when `reset` is true) and confirmed on the seL4 list (2023): "if the untyped isn't device untyped, it should be zeroed before it is typed into an object". From memory, not verified: at boot seL4 marks the initial untypeds as used to the end, so that the first retype clears them.
- **Zircon** gives zero-filled memory: `zx_vmo_create` "creates a new, zero-filled, virtual memory object" (documentation). The kernel zeroes the pages. The exact mechanism (at allocation, or pages zeroed in advance) was not settled by the sources read. Zircon keeps a single shared zero page and a scanner that folds zero pages back into it.
- So both reference kernels guarantee that a new object, frames included, holds no previous data. Under the current rule DodOS would be the exception.

**The options.**

| Option | What the kernel does | Security | Cost |
|---|---|---|---|
| A. Current rule | Clears kernel objects at creation, never frames | Kernel data (registers of other threads, kernel addresses) and user data are visible through a frame made from a reused untyped. Every holder that hands an untyped on must clear it through a mapping, and one omission is a leak the kernel cannot see | Nothing in the kernel. The memory service clears pages before it hands them out, in idle time, which [memory.md](memory.md#other-rules) already requires |
| B. Clear kernel objects at destruction too | Clears the memory of each object when it is destroyed. Frames are not cleared | No kernel data ever leaks. User data of a previous holder still can | Destroying an aspace must clear all its tables: a few MB for a large process, so the removal needs a clearing budget per step. A second budget in a part that was reviewed five times |
| C. Clear at creation, frames included, in steps (recommended) | `untyped_retype` clears the memory of every object it makes from ordinary memory. Each untyped keeps a *clean* mark: the memory between its watermark and that mark is known to be clear. A creation that must clear more than 64 KB clears 64 KB per call and returns `again`, moving the mark. The progress does not depend on the arguments, so a caller may change them between two calls. When the watermark returns to the start, the clean mark returns too | No previous data, kernel or user, is ever visible in a new object. The property is local to the kernel and checked by its model | A 2 MB frame from dirty memory costs 32 calls, a 1 GB frame 16,384 calls (at about 10 GB/s of clearing, from memory, roughly 0.1 s in all). The memory service creates its pools in advance on idle efficiency cores, so the cost stays off the fault path. A page that moves from one process to another *without* passing through an untyped (the common case, by unmap and map) must still be cleared by the memory service, as today |
| D. Clear at the reset of the untyped, in steps (seL4) | Clears the whole untyped when it is reused, before the first new object | As C | Clears the whole untyped even when one small object is needed. In this contract the reset happens inside a removal step, so the clearing would have to move to the next `untyped_retype`, which is C with a coarser grain |

**Recommendation: C.** The kernel-data leak is a real hole in A, not a matter of policy, and both kernels the project takes as models close it. C costs one mark per untyped and one budget (64 KB, the same as the creation of a capability space). It removes a duty that every holder of an untyped would otherwise carry. It keeps the hot path unchanged, since the memory service reuses frames without the kernel. B closes only the kernel half, at a similar cost. D is C done in a coarser way.

**What changes in this group if C is chosen.** The paragraph "What a new frame holds" becomes "A new frame on ordinary memory is all zero". `untyped_retype` gains `again` for frames and the clean mark. Nothing else in the calls above changes. Device memory is never cleared under any option.

### 3.2 The kernel reads the IOMMU units from the firmware

The contract says the kernel needs only a timer, an interrupt controller and a serial port, and that ACPI is read in user space (D-054). The IOMMU is the exception chosen above. The kernel must own the IOMMU registers before any device untyped is handed out, and must turn the units on before the first process. Otherwise a device untyped could hold the IOMMU's own registers.

- **Recommended:** the architecture layer reads only the DRHD entries of DMAR (address and segment of each unit) and removes those ranges from the device untypeds. seL4 does the same on x86, reading DMAR at boot (from memory). Cost: a small ACPI table parser in the kernel.
- **Alternative:** the platform service finds the units and hands their register ranges to the kernel by a new call, with a device untyped as authority. Until that call, every device can reach all memory by DMA, including during the start of the platform service, and the kernel must check that no frame was made over the registers. It needs a new call and a new rule on device memory.

### 3.3 Capability slots of 64 bytes

A frame capability must hold its record and the links of its space's list. Without them, destroying a space cannot find the records that name it, and a record would then name freed memory. That makes the slot 64 bytes. A capability space costs twice as much: 64 MB for a full space of 2^20 slots, 8 KB per segment. A process with a thousand capabilities pays 64 KB instead of 32 KB.

The alternatives were looked at and set aside:

- *Shadow tables*: a parallel table per page table, holding a pointer back to the slot for each entry. It keeps 32-byte slots, but doubles the memory of the page tables and makes `cap_move` of a mapped frame cost up to 512 writes.
- *Address-space identifiers from a pool* (seL4: frame capabilities hold a 16-bit ASID and the mapped address; ASID pools are objects of 512 identifiers made from untyped; verified in `structures.bf`). It keeps 32-byte slots, but adds two object kinds and a table of pools per node, and stale records must be checked on every use.

It is a number of the reviewed section, so it is listed here for re-reading. The decision itself is technical.

---

## 4. What a reference model of this group must cover

**State to add.**

- For each frame: page size, number of pages, memory type, device or not.
- For each frame capability: its record, empty or (space, address, first page, count, rights).
- For each aspace and iospace: the translations, as a map from address to (frame, page of the frame, rights), with the page size; the set of hooked tables, with their level and slot; the free list, as an ordered list; the list of records; the list of bound threads (aspace); the attached devices and the unit (iospace); the untyped it came from (none for the start-up aspace); dying.
- For each thread: its aspace (or none), its fault endpoint and badge (or none), the pending fault (kind and four words) while it waits on one.
- For each `iommu`: the device-to-iospace map, the domain numbers in use, the identifiers the kernel uses.
- An abstract TLB per core: a set of (space, address, frame page, rights) that may only lose elements by an invalidation, and may hold an element only if it was translated at some point after the last invalidation of that address.

**Invariants worth checking after every call and every step.**

1. Every translation belongs to exactly one full record, and every full record's range is translated exactly: same frame pages, consecutive addresses, the record's rights, the frame's page size.
2. No two records of one space overlap. No record lies outside the user range (aspace) or the width (iospace). No translation lies in the reserved slot.
3. The rights of a record are a subset of its capability's rights. An aspace record has `read` and never `write` with `exec`. An iospace record never has `exec`.
4. Every hooked table holds at least one present entry. The tables hooked plus the tables free equal the tables taken. The untyped's count of live pieces includes them. Every table was taken from the space's own untyped. The start-up aspace never takes one.
5. Every record names a live space (dying allowed). No record names a destroyed space. The list of a space holds exactly the capabilities whose records name it.
6. No translation reaches the memory of a destroyed frame. No untyped's watermark has returned to the start while one of its frames is translated.
7. Every thread bound to an aspace is in that aspace's list, and that aspace is live. The same holds for fault endpoints.
8. A thread whose aspace is none, dying or destroyed never runs user code. The model's `runnable` must make it raise kind 2 instead.
9. A device identifier is attached to at most one iospace. An iospace has at most 16 devices, all of one unit, and appears with them in the unit's map. A domain number is in use only while its iospace has a device of that unit.
10. Frames on device memory have no `exec` and are never write-back. Frames on ordinary memory are write-back.
11. The abstract TLB of every core holds only translations that exist (with rights no greater) whenever a call returns or a step returns `again`.
12. A thread that waits on a fault has its four words in its thread state and unchanged registers.

**Sequences worth testing.**

- Each check of `aspace_map` and `iospace_map` alone and in pairs, to pin the order: alignment against range, rights `invalid` against `denied`, `busy` on the record against `busy` on the range against `no_memory`.
- The exact `no_memory` limit: an untyped with room for exactly the tables needed, and one table short. Untyped 0 with a sufficient free list.
- Map small pages in a 2 MB slot, unmap them, then map a 2 MB page there (the table must have gone to the free list). Map again and check that the table is reused before the untyped.
- A mapped frame capability: moved by `cap_move` and by IPC, then unmapped from its new slot. Derived, the child mapped elsewhere, then the parent revoked: the step count with 32, 33 and 64 mapped children.
- The aspace destroyed with N records and M bound threads, for N + M around 32 and 64: steps, `again`, order, and the threads then raising kind 2.
- Faults: no receiver (queue order with two faulting threads and a `call`), a receiver waiting, answer with label 0 and with label 1, answer by `reply_recv` listing capabilities, endpoint destroyed during the wait, reply object destroyed, `thread_cancel` with 0 and with a number, suspension during the wait and resumption afterwards, no fault endpoint at all.
- A thread that deletes the root capability of its own aspace: it gets the result of its call, then raises kind 2 at return.
- `iospace_attach` through every `busy` case. Detach of a device of a dying iospace. Destruction of an `iommu` with devices on both sides of 128 identifiers.

---

## 5. Sources

Read on the web, 14 November 2026:

- seL4, `src/object/untyped.c` (reset of an untyped clears it in chunks, with a preemption point, never device memory): https://raw.githubusercontent.com/seL4/seL4/master/src/object/untyped.c
- seL4, `src/object/objecttype.c` (object creation does not clear; it relies on cleared untyped memory): https://raw.githubusercontent.com/seL4/seL4/master/src/object/objecttype.c
- seL4 devel list, 2023, on whether retyped objects are zeroed ("if the untyped isn't device untyped, it should be zeroed before it is typed into an object"): https://lists.sel4.systems/hyperkitty/list/devel@sel4.systems/thread/Z66U7PSPNESYS4S5HAE3UKNPNTAGQMX6
- seL4, x86-64 `structures.bf` (frame capability with `capFMappedASID` 16 bits and `capFMappedAddress` 48 bits; ASID pools of 2^9; "the ASID doubles as the PCI bus/dev/fun when used in an IOMMU context"): https://raw.githubusercontent.com/seL4/seL4/master/include/arch/x86/arch/64/mode/object/structures.bf
- seL4 API reference (IOSpace and `seL4_X86_IOPageTable_Map`): https://docs.sel4.systems/projects/sel4/api-doc.html
- Zircon, `zx_vmo_create` ("creates a new, zero-filled, virtual memory object"): https://fuchsia.dev/reference/syscalls/vmo_create
- Zircon, `zx_bti_pin` (pinning, rights, device addresses returned to the caller): https://fuchsia.dev/reference/syscalls/bti_pin
- Zircon, `vm_cow_pages.cc` (zero-page helpers, de-duplication into the zero page): https://fuchsia.googlesource.com/fuchsia/+/main/zircon/kernel/vm/vm_cow_pages.cc

From memory, not verified today:

- seL4 allows one mapping per frame capability; mapping twice needs a copy. seL4 x86 reads ACPI DMAR at boot. At boot seL4 marks the initial untypeds as used, so that their first retype clears them.
- Intel SDM, volume 3: mapping one physical page with two memory types is not supported.
- PCIe: the completion of an ATS invalidation may take up to one minute.
- VT-d: second-level read and write permissions are independent; domain numbers per unit, their count given by the ND field.
- Clearing speed of about 10 GB/s per core.
