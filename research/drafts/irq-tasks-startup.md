# Draft: interrupts, tasks and marks, start-up state, threads (the rest)

Drafted on 14 November 2026 for `architecture/kernel-interface.md`. It follows the form of "Call reference, one core". Part 1 is the text to paste. Parts 2 to 5 are working notes for the owners.

---

## Part 1. Text ready to be pasted into kernel-interface.md

Where each piece goes:

- "Interrupts", "Tasks and marks" and "Threads: bindings, faults and registers" are new subsections of "Call reference, one core", after "Notifications". The status line of that section (the list of groups it covers) gains these three groups.
- "Start-up state" replaces the section "Start-up information".
- "Tasks and marks" replaces the rules of "Tasks and provenance" and of "Marks and services". The flowchart of "Marks and services" stays.

---

### Interrupts

An `irq` capability names one entry of the interrupt table of one node: one vector of that node's core, bound to one source. In the kernel an interrupt is a constant amount of work: mask the source or record the arrival, signal one notify, acknowledge the controller. Routing policy, the firmware tables and the driver are in user space (the platform service, D-054).

**Objects.**

- `irq_control` is one object per node. It is made at start-up and never from an untyped. It is the authority to claim the vectors of its node.
- An `irq` is one entry of the node's **interrupt table**. The table has one entry for each vector that can be claimed. On x86-64 those are vectors 48 to 239, so 192 entries of 64 bytes (12 KB) per node. The table is taken at start-up from the memory the kernel keeps for the node. `irq_claim` makes an `irq`. `untyped_retype` never makes one: the kinds `irq` and `irq_control` are `invalid` there. The root capability of an `irq` is a child of the `irq_control` capability used to claim it, so `cap_revoke` on a control capability releases every vector claimed through it. **(design choice:** a vector is a hardware resource that exists whether or not memory is supplied, as in seL4, where IRQ handler capabilities take no untyped. The alternative was an `irq` made from an untyped. That `irq` would be a child of the untyped, and revoking the control capability would not reach it.**)**

**States of an `irq`.** An `irq` is **idle** (bound to no notify), **armed** (bound, and the next arrival is signalled) or **fired** (bound and signalled, and no further signal until `irq_ack`). An entry for an edge source also has a **pending** bit, set by an arrival that was not signalled. A level source is masked at the controller while the `irq` is idle or fired, and unmasked while it is armed. An edge source is never masked at the controller once it is claimed: the kernel records the arrival instead.

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `irq_claim` | irq_control, source, vector, destination | MSI address, MSI data | `manage` on the irq_control. The source is one word whose format the architecture layer defines (x86-64 below). A source the format refuses is `invalid`, and so is a vector outside the claimable range. Both are judged in that order, after the destination. Then `unsupported` if this machine cannot deliver that source to that core (x86-64 below). The depth checks come last. State: `busy` if the vector is already claimed on this node, then `busy` if the source is a line whose input is already claimed (on any vector), then `no_slot`. The new `irq` is idle, with pending 0, and its root capability has every right. The result is the address and data the device must be given for an MSI, and 0 and 0 for a line |
| `irq_bind` | irq, notify | | `manage` on the irq. Notify 0 unbinds. Otherwise `send` on the notify, and the notify must belong to the node of the irq (`invalid` otherwise, judged after the capability checks). State: `busy` if the irq is bound and the notify is not 0. That includes a second bind to the same notify, as for `notify_bind`. Binding records the bits the interrupt will set: the badge of the notify capability, or bit 0 if it has no badge. If pending is set, it is cleared, the notify is signalled at once and the irq is fired. Otherwise the irq is armed and a level source is unmasked. Unbinding makes the irq idle, masks a level source and keeps pending. It succeeds on an idle irq |
| `irq_ack` | irq | | `write` on the irq. State: `busy` if the irq is idle. On an armed irq it succeeds and does nothing. On a fired irq: if pending is set, it is cleared, the notify is signalled again and the irq stays fired. Otherwise the irq is armed and a level source is unmasked |

**An arrival.** When the vector of a claimed entry arrives on its core, the kernel does the following, in this order:

1. If the source is a level source, it is masked at the controller.
2. The interrupt controller is acknowledged (end of interrupt).
3. If the irq is armed, it becomes fired and the notify is signalled with the recorded bits, exactly as `signal` with a capability whose badge is those bits. That wakes at most one thread. Otherwise an edge source sets pending.
4. The time stamp of the arrival is mixed into the entropy pool (D-057).

A vector that is claimed by no entry is acknowledged and ignored. An arrival on a notify that is dying is delivered as on a live one: it can only take a waiter out of its queue, so the notify still only shrinks.

- **The work of the interrupt path is constant (design choice).** One table lookup, at most one controller write to mask, one end of interrupt, at most one thread woken, one mix into the entropy pool. There is no loop and no queue. A burst of arrivals on an edge source costs one constant path per arrival and still one signal until the next `irq_ack`. How the time of this path is charged is fixed by the scheduling group ([scheduling.md](scheduling.md#time-spent-in-interrupts)); this group fixes only that it is constant.
- **Masking is unbinding (design choice).** No separate call masks a vector. `irq_bind` with notify 0 masks a level source at once, and makes an edge source record arrivals without signalling them. Binding again delivers what is pending. The alternative was a pair of calls, mask and unmask, on top of the acknowledgement. Each state they could reach is already one of the three states above.
- **An interrupt is signalled once until it is acknowledged.** This is what bounds an interrupt storm. A driver whose budget is exhausted cannot run, so it cannot call `irq_ack`, and its source stays masked until its budget is refilled ([scheduling.md](scheduling.md#time-spent-in-interrupts)). The kernel needs no other mechanism for this.
- **What is destroyed, and what follows.**
  - *The notify.* Each irq bound to it is unbound, as by `irq_bind` with notify 0 (idle, level source masked, pending kept). This is done in the steps of the removal that destroys the notify, one unit of the 32 of a step per irq ([The derivation tree](#the-derivation-tree)). The irqs bound to one notify are linked through the irq entries, so each unbinding is one step whatever their number. A later `irq_ack` on such an irq is `busy`.
  - *The thread that served the interrupt.* Nothing happens to the irq. It stays fired, with its source masked if it is a level source, until someone calls `irq_ack` or `irq_bind`, or the irq is destroyed. Bits already set in the word of the notify stay there.
  - *The irq.* When its root capability is removed, it is unbound from its notify, its source is masked at the controller (on x86-64 the input of the IOAPIC is masked and the remapping entry is cleared), its pending bit is dropped and its vector can be claimed again. This is one unit of a removal step. Bits already set in the notify are not taken back.
  - *The control capability.* `cap_revoke` or `cap_delete` on a control capability removes the irqs claimed through it, by the same steps.
- **Restart of a driver.** The platform service keeps the root capability of each irq and gives the driver a copy with `manage` and `write`. When the driver dies, its notify is destroyed with its untyped, so the irq becomes idle and a level source stays masked. The device is reset at bus level ([drivers.md](drivers.md#restart-of-a-driver)). The new driver then binds its own notify. A device that keeps its line asserted cannot cause a storm meanwhile.
- **Whole-machine suspend.** The interrupt table is the truth. On resume, the kernel programs the controller inputs and the remapping entries again from it before any thread runs. The states (idle, armed, fired, pending) do not change. An edge arrival during the suspend is lost unless the hardware latched it, and the driver's `resume` resynchronises its device.
- **Nodes.** The table, the vectors and `irq_control` belong to one node (rule 7). Each node's `irq_control` is given in the start-up space of that node (see [Start-up state](#start-up-state)). Line interrupts can be claimed only through the `irq_control` of the boot node (`invalid` elsewhere, judged with the source). The inputs of the IOAPICs are shared by the whole machine, and one owner avoids a protocol between kernels for a legacy path (the ACPI SCI, PS/2, legacy INTx). **(design choice:** the alternative was a protocol between kernels that hands each input to the node that asks for it.**)** When a node is moved to another core ([D-108](kernel.md#nodes-cores-and-load), proposed), the kernel rewrites the destination of its claimed entries: at most 192, a bounded step.

**x86-64.** The interrupt controller (the local APIC), the IOAPICs and the interrupt remapping of the IOMMU are driven by the kernel. Their register ranges are kept by the kernel and are in no untyped. The kernel finds them in the ACPI tables MADT and DMAR at start-up, and reads no other ACPI table. Vectors 0 to 47 and 240 to 255 are the kernel's: exceptions, the range of the legacy PIC (masked, its spurious vectors ignored), the timer, the interrupts between kernels and the spurious vector of the APIC. Vectors 48 to 239 can be claimed. The priority class of a vector is its high four bits, so the platform service orders interrupts by the vector it chooses.

The source word:

| Bits | MSI or MSI-X (kind 1) | Line (kind 2) |
|---|---|---|
| 0-7 | 1 | 2 |
| 8 | 0 | trigger: 0 edge, 1 level |
| 9 | 0 | polarity: 0 active high, 1 active low |
| 10-31 | 0 | 0 |
| 32-63 | requester ID: function in bits 32-34, device in 35-39, bus in 40-47, PCI segment in 48-63 | global system interrupt (GSI) |

- **`invalid`**: a kind other than 1 or 2, a reserved bit set, bits 8-9 set for an MSI, a GSI that no IOAPIC known to the kernel serves, or a line on a node other than the boot node.
- **MSI and MSI-X** are edge sources. One `irq` is one message. A device with several MSI-X vectors gets one claim per vector. Multi-message MSI (several vectors in one MSI capability) is refused by construction: the kernel hands out one message at a time, and a driver that needs several uses MSI-X **(design choice:** multi-message MSI needs aligned blocks of vectors, which a claim of one vector cannot express**)**. The per-vector mask bit of MSI-X sits in the device's table, in the driver's memory. The kernel never touches it.
- **With interrupt remapping** (the normal case; [drivers.md](drivers.md#iommu) requires it), each claimable entry of each node has a fixed remapping entry: handle *h* = node index × 192 + (vector − 48). Claiming writes that entry, with the vector, the APIC ID of the node's core, edge or level, and source validation. Source validation checks the requester ID of the source word for an MSI, and the IOAPIC's own source ID for a line. The result of `irq_claim` for an MSI is then address = 0xFEE0_0000 | ((*h* & 0x7FFF) << 5) | (1 << 4) | (((*h* >> 15) & 1) << 2), and data = 0 (remappable format, no subhandle; Intel VT-d, from memory). The device can then raise only that entry: a device cannot forge another interrupt. A line is programmed in the IOAPIC in remappable format with the same handle. The remapping table holds one entry per handle, rounded up to a power of two, at most 65,536. A node of index 341 or more cannot claim (`unsupported`).
- **Without interrupt remapping**, the result is address = 0xFEE0_0000 | (APIC ID << 12) and data = the vector (physical destination, fixed delivery, edge). A core whose APIC ID is greater than 255 cannot be reached this way (`unsupported`). The requester ID is then checked for its format only.
- **A level line** is masked in the IOAPIC before the end of interrupt, and unmasked by `irq_ack` or by binding. If the device still asserts the line, it arrives again at once. This is the mask-then-acknowledge flow of Linux for level interrupts, and the one-shot rule of its threaded handlers ([genericirq](https://docs.kernel.org/core-api/genericirq.html)).
- **The interrupt remapping cache** of the IOMMU is invalidated after a remapping entry is written. Which kernel drives an IOMMU unit is fixed by the devices group (`iospace`). A claim on another node is then a message between kernels (rule 7).

---

### Tasks and marks

A **task** is the unit of provenance and of stopping. It carries an identifier and marks, and it can be stopped as a whole. Each thread is attached to at most one task. The supervisor attaches the threads of each process to one task. An agent task spans the processes of one agent action, and all their threads are attached to it.

A task holds:

- an **identifier**: the node index in bits 48-63, and in bits 0-47 a counter of that node that starts at 1 (the start-up task is 1). An identifier is never reused within one generation of the node, and identifier 0 means "no task";
- **marks** (64 bits: bit 0 private, bit 1 untrusted, the others reserved);
- the flag **mark-aware**;
- the flag **revoked**;
- the list of the threads attached to it, with their number.

`untyped_retype` makes a task (size argument 0; 256 bytes). A new task has the next identifier, marks 0, is neither mark-aware nor revoked, and has no thread.

Every thread also has its own marks word, 0 when the thread is created. The **effective marks** of a thread are the marks of its task if it is attached to one, and otherwise its own marks word. **The effective marks of a thread never lose a bit while the thread lives.** Every rule below keeps this invariant. Restarting a process (new threads) is the only way to shed marks.

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `task_attach` | thread, task | | `manage` on the thread. Task 0 detaches. Otherwise `manage` on the task. The thread and the task must belong to the same node (`invalid` otherwise, judged after the capability checks). State: `busy` if the thread is attached to a revoked task. If the thread is already attached to this task, nothing changes. Otherwise, with *m* the effective marks of the thread, the thread leaves its old task if it had one, joins the new one, and the new task's marks become marks \| *m*. This holds even when the new task is mark-aware. Detaching sets the thread's own marks word to the marks of the task it leaves. It succeeds on a thread that is attached to nothing |
| `task_mark` | task, marks | | `write` on the task. A reserved bit is `invalid`. The marks of the task become marks \| the argument. Marks 0 succeeds |
| `task_exempt` | task, aware task | | `manage` on the task. `manage` on the aware task, which must be mark-aware: `denied` otherwise, judged as a right of that slot. The task becomes mark-aware, for the rest of its life. It succeeds on a task that is already mark-aware |
| `task_revoke` | task | | `manage`. Stops every thread attached to the task, then detaches them, in bounded steps. Returns `again` while attached threads remain (below) |
| `task_read` | task | identifier, marks, flags, number of attached threads | `read`. Flags: bit 0 mark-aware, bit 1 revoked |

**A revoked task** answers `gone` to every call that names it, at the check of its capability, except `task_read`, `task_revoke` and the capability calls (`cap_*`). That covers the task argument of `task_attach`, `task_mark`, and both arguments of `task_exempt`.

**What the kernel stamps on a message.** At delivery, the receiver gets:

- the identifier of the sender's task (0 if the sender is attached to none);
- marks = the effective marks of the sender | the added marks of the message (below).

Delivery means every delivery: of `call`, `send`, `reply_recv`, of an answer by `send` on a reply object, and of a fault message, whose sender is the faulting thread. The values are taken at delivery, not when the call was made: a caller marked while it waited in a queue sends its new marks. A notification returned by `recv` carries marks 0 and identifier 0, as already decided (D-109).

- **Sticky by default.** At the same delivery, if the receiver is not attached to a mark-aware task, its effective marks become themselves | the stamped marks. That is the marks of its task, or its own word if it has no task. A thread attached to no task therefore keeps marks too. Without a task, nothing is lost; there is only less to read back. **(design choice:** the alternative was to treat a thread without a task as mark-aware. That would make a forgotten `task_attach` a way to launder marks.**)**
- **Marks flow both ways with capabilities (design choice).** If at a delivery at least one capability is moved or derived (the transfer was not dropped), and the sender is not attached to a mark-aware task, the sender's effective marks become themselves | the receiver's effective marks as they were before this delivery. Why: a capability given to a marked party, typically a writable frame, is a channel back to the giver, and data never crosses IPC (rule 8). The alternative, marks in one direction only, leaves this channel open: an unmarked process that hands a frame to a marked one by `send` would read back what the marked one writes, and receive no marked message. The cost is that a sender of a read-only capability is marked as well.
- **Added marks.** A sender may set the header flag `add_marks`, the only flag a sender may set. The kernel then reads one word of the sender's message page, whose place the architecture layer fixes with the other fields of that page ([Registers](#registers)). A reserved bit in that word is `invalid`, judged with the header. The word is read when the call is made and kept in the thread with the message. It adds to the stamp of this message only, never to the sender's own marks. Adding a mark is always safe, so no right is needed. This is how a mark-aware service hands back a record with the marks it was stored with. A message with this flag does not take the fast path.
- **Mark-aware tasks.** A thread attached to a mark-aware task takes no marks when it receives. It sends its task's marks, plus the marks it adds. The first mark-aware task is the start-up task. Every other one is made by `task_exempt` from a capability for a mark-aware task, so the right to be mark-aware is delegated through capabilities, from the first process down. The list of services that hold one is in [Marks and services](#marks-and-services).
- **Fault messages carry marks.** A faulting thread chooses the address and the kind of its fault, so a fault is a channel like a message. A fault handler that must not be marked (the memory service, a supervisor) is attached to a mark-aware task.
- **What carries no marks** (known limits, besides timing): the bits of a notify (`signal`, interrupts, timers), and memory that was shared before one side was marked. A marked thread that holds several notify capabilities with different badges can pass a few bits per `signal`. The defence is the fresh instance of each agent action ([agent.md](agent.md#effect-class)): such an instance shares nothing that was set up before it was marked.

**`task_revoke`: stopped in one operation, removed in bounded steps.** This settles the contradiction between "in one operation" and rule 4.

- **The first call on a live task sets the flag revoked.** That is one write, and from that moment every thread attached to the task is stopped:
  - every call it makes returns `gone` before any argument is looked at, as for a thread whose capability space is dying;
  - it never runs again. When the scheduler would pick it, the kernel sets its suspended flag and picks again. Each such removal is constant work, and the kernel takes pending interrupts between two removals, so a revoked task with many ready threads cannot lengthen the latency of an interrupt;
  - it can still be a receiver or a caller in a queue until its step comes. A message delivered to it in the meantime is simply never acted on. Its callers wait, as for a killed server, until the reply objects are destroyed or the wait is cancelled.
- **Each call, the first included, then detaches up to 32 attached threads**, most recently attached first. For each one:
  - if it waits, its wait ends: it leaves its queue, a reply object attached to it or armed with it becomes idle, and its call returns `gone`;
  - its suspended flag is set;
  - it is detached, keeping the marks of the task in its own word.
  
  The call returns `again` while attached threads remain. The call that detaches the last one returns success, never `again`. A revoked task with no attached thread returns success.
- **What "every right of the task" means here.** Once the flag is set, no thread of the task can use any capability, map memory, write a shared frame or signal anyone. The capabilities themselves are removed by the supervisor afterwards, with `cap_delete` on the root capabilities of the task's spaces, by the steps of [The derivation tree](#the-derivation-tree). That removal also removes everything the task derived and handed to others, since a capability never outlives the capability it was derived from. A capability the task *moved* out survives. The supervisor therefore gives a task only derived capabilities. **(design choice:** the alternative was a task tag on every capability ("everything derived from it stays under the task"), checked on every use. It costs either 8 bytes more per slot, or one proxy object per attached capability and one more indirection on every call, the fast path included. Stopping the threads gives the property that matters at once, because data never crosses IPC: without its threads a task can do nothing, even through rings it already has mapped.**)**
- `task_revoke` needs no protocol between kernels, because a task and its threads are on one node. An agent task whose processes run on several nodes is one task object per node. The supervisor revokes each of them: one call per node, each stopping at once.

**Destruction.** When the root capability of a task is removed, its attached threads are detached in the steps of the removal, one unit of the 32 each. Each keeps the task's marks in its own word. If the task was revoked, each one is also treated as by a step of `task_revoke` (wait ended, suspended). When a thread is destroyed, it is unlinked from its task: one step.

**Bound.** `task_attach`, `task_mark`, `task_exempt` and `task_read` do constant work. A step of `task_revoke` detaches at most 32 threads. Stamping and the sticky rule add two loads and at most two writes to a delivery.

#### Marks and services

The rules stay as proposed, with the kernel terms above. "A process" is the set of threads attached to one task. "A capability that turns this off" is a capability for a mark-aware task, presented to `task_exempt`. Besides storage, network, clipboard and compositor, the services that handle faults (the memory service and the supervisor) are mark-aware, for the reason given under "Fault messages carry marks". The flowchart is unchanged.

---

### Threads: bindings, faults and registers

**Bindings.**

- A thread is bound to at most one of each of these: a capability space, an address space, a fault endpoint (with the badge of the capability given to `thread_configure`), a task and a scheduling context. Each binding is a link both ways, so undoing it is one step.
- When the object a thread is bound to is destroyed, the binding is undone in the steps of the removal, one unit of the 32 of a step per thread. The thread is then bound to nothing of that kind.

**A thread whose address space is destroyed**, or that was configured with none, still runs. On x86-64 the kernel uses an address space that maps only the kernel. When it is about to execute in user mode, it takes the fault **no address space** instead. That fault is sent as below. It is not sent as a page fault, so that the memory service does not try to serve it. **(design choice:** the alternative was to suspend such threads in the destruction step. The thread is then told nothing, and its supervisor learns nothing through the usual path for faults.**)**

**A thread whose fault endpoint is destroyed** (or that has none, or whose fault endpoint is dying at the moment of the fault) is suspended when it faults. Its registers stay as at the fault and nothing is sent, as in seL4 when no thread can receive a fault. A thread that was waiting in the queue of that endpoint with a fault message is woken with `gone`, which for a fault means the same thing: suspended, registers as at the fault.

**Faults.** A fault is sent as a `call` by the faulting thread on its fault endpoint, with an empty receive range and wait number 0. It follows every rule of `call` (queue, reply object armed, budget follows the call), and the task stamp and the marks apply. The `send` right was checked by `thread_configure` and is not checked again. A fault is sent even when the thread's capability space is dying, since it carries no capability.

- **Header:** label = the fault kind, 5 words, no capability, no flag. The receiver sees the badge of the fault endpoint capability, which tells it which thread faulted.
- **Words** (5, so a fault fits in the 6 register words and takes the fast path):

  | Word | Content |
  |---|---|
  | 0 | the instruction pointer as the processor reports it: the faulting instruction for a fault, the next one for a trap (breakpoint, single step) |
  | 1 | the stack pointer |
  | 2 | the architecture's exception number (x86-64: the vector) |
  | 3 | the architecture's error code, 0 if the exception has none |
  | 4 | an architecture address: CR2 for a page fault, DR6 for a debug exception, otherwise 0 |

- **Kinds** (the label):

  | Kind | Label | x86-64 |
  |---|---|---|
  | page fault | 1 | #PF. The memory group fixes the meaning of words 3 and 4 and may add words |
  | undefined instruction | 2 | #UD |
  | arithmetic | 3 | #DE, #MF, #XM |
  | protection | 4 | #GP, #SS, #AC, #CP |
  | debug | 5 | #BP, #DB |
  | bad call | 6 | a system call instruction outside the kernel-supplied code page; words 2 to 4 are 0 |
  | no address space | 7 | words 2 to 4 are 0 |
  | budget | 8 | reserved for the scheduling group, same layout |

  The other exceptions are not faults of the thread. #NM is the kernel's own (vector state), #DF is a bug of the kernel, and #MC is a hardware error handled by the recovery of the node.
- **The answer.** The handler answers through the reply object, as for any call.
  - **Label 0:** the thread resumes at word 0 of its fault, so a fault is executed again, and a trap continues after the instruction.
  - **Label 1, with at least 2 words:** the thread resumes with its instruction pointer and its stack pointer set to words 0 and 1. A handler can thus skip an instruction or redirect the thread without suspending it. A non-canonical address counts as another label.
  - **Any other label:** the thread is left suspended, with its registers as at the fault.
  
  Capabilities in the answer are dropped, since the receive range is empty: `send` returns the flag `caps_dropped`. A thread suspended while it waits for the answer gets the answer's effect and runs when it is resumed.
- **Ending a fault wait.** A fault wait has wait number 0, so only `thread_cancel` with number 0 ends it. The thread is then suspended, with its registers as at the fault. It is not left running: it would only fault again. This is the general rule for a fault wait that ends without an answer, whether by `thread_cancel` or by `gone`.

**Registers.** These two rows replace the row of `thread_read_regs` and `thread_write_regs` in [Threads](#threads).

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `thread_read_regs` | thread | the register block | `read`. State: `busy` if the thread is not suspended (so a thread never reads its own registers). A waiting thread can be read. The block holds the values the thread will see when it resumes, except the registers in which a call it waits in returns its result |
| `thread_write_regs` | thread, register block | | `write`. The block must have exactly the architecture's number of words, and the words the architecture requires to be canonical addresses must be canonical (`invalid`, judged word by word in order). State: `busy` if the thread is not suspended, then `busy` if it waits: the end of its wait would overwrite registers. Bits of the flags word that user code cannot change are forced to their fixed values without an error |

- **The contract fixes** that the block is a sequence of 64-bit words, at most 64, that travels as the message words of the call (result or argument). Word 0 is the instruction pointer, word 1 the stack pointer and word 2 the flags. The block of a new thread is all zeros, except the flags at their fixed value.
- **The architecture layer fixes** the number of words, the order of the others, which words must be canonical, and the mask of the flags. x86-64: 20 words. In order: rip, rsp, rflags, rax, rbx, rcx, rdx, rsi, rdi, rbp, r8 to r15, fs_base, gs_base. Words 0, 1, 18 and 19 must be canonical. rflags keeps CF, PF, AF, ZF, SF, TF, DF, OF, AC and ID as given; IF is always 1 and the other bits are 0, so a new thread has rflags 0x202. With APX the block grows by r16 to r31 (36 words, still a message).
- **The vector state is not in the block (design choice).** Its size and format depend on the processor and on the features the kernel enables, and the contract would have to version them. The alternative was a frame argument that receives the XSAVE image. The kernel's debugger stub reads the vector state for kernel debugging. A user-space debugger of native services gets the general registers only.
- Both calls do constant work (at most 64 words).

**The reserved kind `vcpu`** has the number 16. `untyped_retype` with kind 16 is `unsupported`.

**A slot number is stable across a whole-machine suspend (design choice).** Capability spaces are in memory, which suspend keeps (s2idle, and S3 if it is ever used). The kernel renumbers nothing and invalidates nothing. Before any thread runs on resume, it restores the state that the hardware lost: the cores, the interrupt controllers and the remapping entries (see [Interrupts](#interrupts)), and the timers. What the devices lost is the drivers' affair (`suspend` and `resume`, [Power states](#power-states)). The alternative was to make every capability that names hardware return `gone` after a resume. Then every driver must rebuild its capabilities, while the driver's own protocol already covers the device. Slots are not stable across the reload of a node: references to its objects return `gone` (rule 2, D-107). There is no hibernation.

---

### Start-up state

The kernel of the boot core starts one process, the first service of the boot image, and gives it everything. No other authority exists in the system. The start-up state is determined entirely by three things, and no other value is chosen anywhere:

- the machine: memory map, cores, interrupt controllers, IOMMU;
- the boot image;
- the memory the kernel keeps, which it publishes in the start-up page.

The reference model takes the same description as input.

**What the loader hands over.** The loader is the part of the single signed EFI image that runs before the kernel. It hands over:

- the UEFI memory map after `ExitBootServices`;
- the ACPI root pointer;
- the framebuffer;
- an entropy seed of 64 bytes;
- the boot time stamps;
- the crash record of the previous boot, if there is one;
- the boot image, already in memory, as a list of **modules**:
  - first, the segments of the first service, each with its virtual address, its rights and its length; the loader has already filled in the file contents and zeroed the tail;
  - then the files of the other services of the boot image;
  - and the entry point of the first service.

The loader lays out the modules in order, each on a 4 KB boundary, from a physical address aligned on 2^*k*. Here *k* is the smallest number such that 2^*k* is at least the size of the modules plus 256 KB, the reserve for the start-up page and the message page. The kernel refuses to start, with a message on the serial console, if:

- a segment of the first service lies below 2 MB;
- a segment is both writable and executable;
- the start-up page would need more than 63 pages;
- or the start-up space would exceed 2^20 slots.

**Memory, by rule.**

1. **Kept.** The kernel keeps: its image, the block of the boot node, the machine table (below), the start-up objects that are made from no untyped, the interrupt table of the node, the interrupt remapping table, its own stacks and page tables, and the register ranges of the local APIC, the IOAPICs and the IOMMU units. The kept ranges are listed in the entry `Kept`. Their size is the implementation's own, and publishing it is what lets the oracle rebuild the same state.
2. **Image region.** This is the 2^*k* bytes that hold the boot image.
3. **Ordinary memory.** This is the RAM that is usable after `ExitBootServices`: the UEFI types loader code and data, boot services code and data, and conventional memory. The kept ranges and the image region are taken out, and each range is shrunk inwards to 4 KB boundaries.
4. **Shares (D-107).** Let *n* be the number of usable cores and *O* the size of the ordinary memory. Each node gets *S* = floor(*O* / *n* / 2 MB) × 2 MB bytes, taken in order of ascending address: node 0 takes the first *S* bytes, node 1 the next *S*, and so on. The last node takes the rest. The image region is added to the share of the boot node, which is node 0. A share does not change after start-up. It is recorded, with the core list, in the **machine table**, which is read-only after start-up and is read by every kernel, a reloaded one included.
5. **Untypeds of the boot node.**
   - The **image untyped** comes first: one ordinary untyped of exactly the image region.
   - Then each range of the boot share, in ascending order, is cut into the fewest blocks that are each a naturally aligned power of two, of at least 4 KB. At address *a*, with *L* bytes left, the block is 2^min(trailing zeros of *a*, floor(log2 *L*)) bytes.
   - The other nodes' shares give no capability to the first process. They become the untypeds of the start-up space of their node when that node is started (`core_start`, cores group).
6. **Device untypeds.** Every physical address below 2^MAXPHYADDR that is not RAM of any share, not in the image region, not kept, and not of the UEFI type unusable memory, is cut into blocks by the same rule and given as device untypeds. That includes MMIO, the framebuffer, the ACPI tables and NVS, firmware-reserved memory and the runtime services of UEFI. They all belong to the boot node.
7. **Rights.** Ordinary untypeds have every right, `exec` included: the first process hands that right to the compile service. Device untypeds have every right except `exec`.

**Slots.** The start-up space has every segment present from the start, and it never grows.

| Slot | Capability |
|---|---|
| 0 | never used |
| 1 | its `cspace`, which holds itself |
| 2 | its `aspace` |
| 3 | its `thread` |
| 4 | its `sched` |
| 5 | `debug` |
| 6 | the `irq_control` of the boot node |
| 7 | `ioports` (x86-64; empty on other architectures). The devices group fixes its range; the kernel's serial port is outside it |
| 8 | the IOMMU control capability of the devices group (empty if that group gives none, or if the machine has no IOMMU) |
| 9 | the start-up task (mark-aware) |
| 10 | the frame of the start-up page |
| 11 | the frame of the message page of the first thread |
| 12-15 | empty |
| 16 onwards | contiguous, in this order: one `core` capability per core, in the order of the core list; then the untypeds: the image untyped, the ordinary ones by ascending address, the device ones by ascending address; then one frame per module, in module order |
| after these | empty slots, to the end |

- **Number of slots:** the multiple of 128 just at or above 16 + cores + untypeds + modules + 4,096. So the first process always has at least 4,096 empty slots.
- **Depth and rights.** Every start-up capability except the frames is the root of its object, at depth 1, with every right of its kind (device untypeds without `exec`). The frames are made from the image untyped, in the order modules, start-up page, message page. They are its children at depth 2, with every right. The watermark of the image untyped stands after the message page, so the rest of the image region can be retyped. When every frame of the boot image has been deleted, that memory is usable again, by the ordinary rule of the watermark.

**Address space.**

- Each segment of the first service is mapped at its virtual address with its rights: always read, plus write or execute.
- The kernel-supplied code page is mapped at 0x1000, read and execute, with no capability.
- The message page is mapped at 0x2000, read and write.
- The start-up page is mapped from 0x4000, read only, up to 63 pages.

Nothing else is mapped. Each frame capability records its mapping.

**The first thread.**

- **Bindings.** It is bound to the space in slot 1 and the address space in slot 2. It has no fault endpoint. It is attached to the start-up task (identifier 1 of node 0, marks 0, mark-aware), and the `sched` in slot 4 is bound to it.
- **State.** It is not suspended, its *cancelled up to* word is 0 and its own marks are 0.
- **Registers.** The instruction pointer is the entry point of the first service, and the first argument register holds the address of the start-up page (x86-64: rdi = 0x4000). Every other register is 0, the flags are at their fixed value (x86-64: 0x202) and the vector state is in its initial state (x86-64: as after FNINIT, with MXCSR 0x1F80). It has no stack: its first instructions set one, from one of its own segments, as the root task of seL4 does (from memory).
- **Scheduling.** The `sched` has a budget equal to its period, on the boot core only. The period is fixed by the scheduling group.

**The start-up page.** It starts with a header, then a table of entries, then their contents. All integers are little-endian. Offsets are in bytes from the start of the page, and every entry starts on an 8-byte boundary. Each kind appears at most once. Entries are sorted by kind, and a kind with nothing to say is left out (no framebuffer, no crash record). A reader skips a kind it does not know. The header is `StartHeader` as in `abi/`: magic `START_MAGIC`, version 1, number of entries. It is followed by `StartEntry` records (kind, reserved, offset, length).

| Kind | Name | Content |
|---|---|---|
| 0 | ObjectSizes | One u64 per object kind, indexed by its number (0 to 17): the bytes `untyped_retype` takes. That is the bytes per slot for a `cspace`, the minimum for an `untyped`, the vector state included for a `thread`, and 0 for a `frame` and for kinds never made from an untyped |
| 1 | Untyped | `StartUntyped` records (16 bytes): base, slot, log2 of the size, flags (bit 0 device, bit 1 image), node |
| 2 | Cores | `StartCore` records (24 bytes): APIC ID, node, class (0 performance, 1 efficiency, 0 for every core of a processor that has one type), flags (bit 0 boot core), slot of its `core` capability. The boot core comes first, then the others by ascending APIC ID; a core's position in the list is its node index. At start-up the boot kernel starts each other core long enough to read its type (x86-64: CPUID leaf 0x1A), then stops it |
| 3 | AcpiRoot | One u64: the physical address of the ACPI root pointer |
| 4 | UefiMemoryMap | Descriptor size (u32), descriptor version (u32), then the descriptors as UEFI gave them |
| 5 | Framebuffer | Base and size (u64 each); width, height, bytes per line, format (u32 each; 0 = 32-bit BGRx, 1 = 32-bit RGBx) |
| 6 | EntropySeed | 64 bytes, drawn from the kernel's generator after it has mixed in the loader's seed and the processor's source |
| 7 | BootTimes | Five u64: the frequency of the time stamp counter, then the counter at entry to the loader, at `ExitBootServices`, at entry to the kernel and at the first instruction of the first thread (0 if unknown) |
| 8 | CrashRecord | The bytes of the record; its format is the debugging group's |
| 9 | Process | `StartProcess` (48 bytes): entry point, address of the code page, of the message page, of the start-up page, length of the start-up page, number of slots of the space, first empty slot after the ranges |
| 10 | Modules | `StartModule` records (32 bytes): slot, flags (bit 0 mapped, bit 1 read, bit 2 write, bit 3 exec), virtual address (0 if not mapped), length, offset and length of its name (UTF-8, in the page) |
| 11 | Node | `StartNode` (16 bytes): this node's index, number of nodes, generation, index of the boot node |
| 12 | Shares | `StartShare` records (24 bytes): node, reserved, base, length; sorted by node, then base |
| 13 | Interrupts | First and last claimable vector, flags (bit 0 interrupt remapping on, bit 1 x2APIC), number of IOAPICs (u32 each); then, per IOAPIC, its first GSI and its number of inputs (u32 each) |
| 14 | Kept | `StartKept` records (16 bytes): base, length of each range the kernel keeps |

**Hooks for a reloaded kernel (D-107, D-108).** They are placed now, without designing the protocol between kernels.

- The share of each node and the core list are in the machine table, read-only from the end of start-up, and are copied into the entries `Shares` and `Cores`. A kernel that is reloaded on a node rebuilds the start-up state of that node from its share by the same rules: the same slots 1 to 11, its own share's untypeds, no `core` capability and no device untyped. What its first thread runs is fixed by `core_start`.
- Every node has a **generation**: 1 for every node at machine boot, incremented each time the node is reloaded. It is given in the entry `Node`.
- A reference held by one node to an object of another node carries the index and the generation of that node (`NodeGen` in `abi/`). A reference whose generation is not the node's current one names nothing, and its use returns `gone`.
- Task identifiers carry the node index. After a reload, a log that spans the reload records the generation alongside the identifier.

---

## Part 2. Changes needed elsewhere in the contract

In kernel-interface.md:

1. **Objects table.**
   - `irq` becomes "One vector of one core, bound to one interrupt source; an entry of the node's interrupt table".
   - A new row: `irq_control`, "The authority to claim the vectors of one node", model seL4.
   - `task` becomes "The unit of provenance and of stopping: identifier, marks, attached threads. Stopped in one operation". The words "delegated rights, time budget, ... log" and "Revocable in one operation" go (see For the humans, points 1 and 2).
   - `vcpu`: "Reserved name and number (16), not built".
2. **System calls table.**
   - "Interrupts and devices" gains `irq_claim`.
   - "Tasks" reads `task_attach`, `task_mark`, `task_exempt`, `task_revoke`, `task_read`. `task_create` goes: a task is made by `untyped_retype`, like every object (D-099).
   - "About 46 calls" becomes "About 47".
3. **The derivation tree, first bullet.** "except the capabilities given at start-up, each of which is the root capability of its object" becomes "except the capabilities given at start-up, each of which is the root capability of its object; the frames of the boot image are the exception, as children of the image untyped".
4. **The derivation tree, third bullet.** "An object lives exactly as long as the capability that `untyped_retype` returned for it" becomes "... that `untyped_retype`, or `irq_claim` for an `irq`, returned for it". The next sentence ("its memory goes back to the untyped it came from") gains "(an `irq` has no untyped: its entry becomes free)".
5. **Removal step budget.** "at most 32 capabilities are removed or threads woken" becomes "at most 32 capabilities are removed, threads woken, or bindings undone (a thread from its capability space, address space, fault endpoint or task; an `irq` from its notify)". The present text does not count the unbinding of threads from a destroyed capability space, which has the same unbounded form.
6. **Order of checks, step 3.** "a kind that this version does not make (the kinds of the groups not yet specified: time, tasks, interrupts, devices, debugging, cores) is `unsupported`" becomes "... (time, devices, debugging, cores, and `vcpu`) is `unsupported`; the kinds `irq` and `irq_control` are never made from an untyped and are `invalid`".
7. **Order of checks, step 2.** "a header ... with a flag bit set by the sender is `invalid`" becomes "with a flag bit other than `add_marks` set by the sender". The header check also judges the added-marks word when that flag is set.
8. **Messages.** "the marks of the sender's task (64 bits ...)" becomes "the effective marks of the sender (the marks of its task, or its own if it has none), plus the marks it adds; 64 bits ...". "the task identifier" gains "(0 if the sender is attached to no task)".
9. **IPC, the paragraph "The receiver gets the header..."** "the marks and the identifier of the sender's task" becomes "the stamp defined in [Tasks and marks](#tasks-and-marks)".
10. **Threads table, row `thread_read_regs`, `thread_write_regs`.** It is replaced by the two rows above. The sentence "these two calls, and `yield`, are not part of the one-core reference: in it they return `unsupported`..." becomes "`yield` is not part of the one-core reference: in it, it returns `unsupported` as soon as the capability space of the caller is found". D-109 stays true of the one-core reference that was written; the reference model of this group replaces it for the two register calls.
11. **Gap outside this group, found here: the message page of a thread is given nowhere.** `thread_configure` takes no frame. Proposal for the threads group: `thread_configure` gains a fifth argument, a frame of one 4 KB page with `read` and `write` (0 allowed). The kernel reads and writes the message words, the capability list and the added-marks word there. Destroying the frame undoes the binding, as for the other bindings. A call that needs the message page, from a thread that has none, is `invalid`.
12. **Faults are not calls (paragraph after the System calls table).** Add "The message, the kinds and the answer are in [Threads: bindings, faults and registers](#threads-bindings-faults-and-registers)".
13. **Object sizes.** `irq` leaves the row of 64-byte objects and gets its own row: "An entry of the node's interrupt table, 64 bytes per claimable vector (12 KB per node on x86-64), taken at start-up; not made from an untyped". `task` keeps 256 bytes.
14. **Rights.** `manage` gains "claim a vector (`irq_control`)".
15. **Architectures.** "The kernel needs only a timer, an interrupt controller and a serial port ... Everything else (ACPI or device tree, buses) is discovered in user space" gains "On x86-64 the kernel reads two ACPI tables at start-up, the MADT (cores, IOAPICs) and the DMAR (IOMMU units and the source IDs of the IOAPICs), and no other".
16. **Rule 3 ("No kernel heap ... every object comes from an untyped")** gains "except the fixed tables of a node, sized by the hardware at start-up (the interrupt table), and the start-up objects".
17. **Open points.** The following are settled and go:
    - the four points of the fourth review (thread with a destroyed address space or fault endpoint, slots of the start-up capabilities, `task_revoke` against bounded steps, number of `vcpu`);
    - "To settle with the start-up information: the start-up state that today exists only in the reference model";
    - "Whether a slot number is stable across a suspend".
    
    "The spread of sticky marks in practice" stays and gains "including the two-way rule for capabilities".
18. **"A call on one core" diagram.** The note "stamps badge and task marks" stays true.

Elsewhere:

19. **research/prior-art.md, axis 4.** "a single object gathers the delegated rights, the time budget, the provenance label and the log of an agent task, revocable in one operation" becomes "a kernel object gathers the provenance marks and the threads of an agent task, and stops them in one operation; its rights are removed with its capability spaces". This needs the humans (point 1).
20. **scheduling.md, "Time spent in interrupts".** "its interrupt line stays masked until the refill" is now a consequence of the acknowledgement rule, with no mechanism of its own. Say so in a parenthesis.
21. **memory.md, "Physical memory per core".** "the reserves are rebalanced by messages" predates D-107 (fixed shares). It should read "the shares are fixed at start-up (D-107); memory of another share is used through remote mappings recorded on both sides". This tension existed before this draft.
22. **agent.md, "The agent in the contract".** "The task is the unit of delegation ... revocable as a whole" stays at the WIT level. The kernel task is the mechanism that stops it, and the delegated rights are capabilities that the supervisor removes. A sentence pointing to the kernel task belongs there.
23. **The reference model (dodos-kernel/model).** `Model::boot()` and the constants `BOOT_UNTYPED_BYTES` and `BOOT_DEVICE_BYTES` give way to `Model::boot(&StartDescription)`. The description holds the RAM ranges, device ranges, kept ranges, module lengths and number of cores, and the state is derived by the rules above. Tests that fill the start-up space must account for at least 4,096 empty slots, not 128.

**Values `abi/` must gain.** Nothing is removed. One name changes, at the same number.

- `Call`: `TaskCreate` (35) is renamed `TaskExempt`, at the same place. `IrqClaim = 46`.
- `ObjectKind`: `Vcpu = 16`, `IrqControl = 17`.
- `Error`: no new code.
- `Header::FLAG_ADD_MARKS = 1 << 2`, the only flag a sender may set. `Header::is_fast` also requires `flags() == 0`.
- `FaultKind` (u32 labels): `Page = 1`, `Undefined = 2`, `Arithmetic = 3`, `Protection = 4`, `Debug = 5`, `BadCall = 6`, `NoAddressSpace = 7`, `Budget = 8`. Also `FAULT_WORDS = 5`, `FAULT_REPLY_RESUME = 0`, `FAULT_REPLY_REDIRECT = 1`.
- `IrqSource(u64)`, with `msi(segment, bus, device, function)` and `line(gsi, level, active_low)`, and `from_raw` returning `Invalid` per the table above. This is a pure function, so it gets a Kani proof that it reads back.
- `TaskFlags`: `AWARE = 1`, `REVOKED = 2`. `TaskId(u64)`, with `node()` and `counter()`. `NodeGen(u64)`: generation in bits 0-31, node in 32-47, 48-63 zero.
- Module `x86_64`:
  - `IRQ_VECTOR_FIRST = 48`, `IRQ_VECTOR_LAST = 239`, `IRQ_TABLE_ENTRIES = 192`, `IRQ_MAX_NODES_REMAPPED = 341`;
  - `REGS_WORDS = 20`, with the index of each register;
  - `RFLAGS_USER_MASK = 0x0024_0DD5` (CF, PF, AF, ZF, SF, TF, DF, OF, AC, ID) and `RFLAGS_FIXED = 0x202`.
- Start-up slots: `START_SLOT_IRQ_CONTROL = 6`, `START_SLOT_IOPORTS = 7`, `START_SLOT_IOMMU = 8`, `START_SLOT_TASK = 9`, `START_SLOT_START_PAGE = 10`, `START_SLOT_MESSAGE_PAGE = 11`. `START_SLOT_FIRST` stays 16. Also `START_FREE_SLOTS = 4096`.
- Start-up layout: `START_VERSION = 1`, `START_PAGE_MAX_PAGES = 63`, `START_RESERVE_BYTES = 256 * 1024`, `START_CODE_PAGE_ADDR = 0x1000`, `START_MESSAGE_PAGE_ADDR = 0x2000`, `START_PAGE_ADDR = 0x4000`, `FIRST_SERVICE_MIN_ADDR = 0x20_0000`, `SHARE_ALIGN = 2 * 1024 * 1024`.
- `StartKind`: 0 to 8 unchanged; `Process = 9`, `Modules = 10`, `Node = 11`, `Shares = 12`, `Interrupts = 13`, `Kept = 14`.
- New `repr(C)` records, with sizes asserted in `layouts_are_fixed`. Field types are in the order given in the table of the start-up page:
  - `StartUntyped` (16 bytes): u64, u32, u8, u8, u16;
  - `StartCore` (24): six u32;
  - `StartModule` (32): u32, u32, u64, u64, u32, u32;
  - `StartProcess` (48): five u64, two u32;
  - `StartNode` (16): four u32;
  - `StartShare` (24): u32, u32, u64, u64;
  - `StartKept` (16): two u64;
  - `StartIoApic` (8): two u32;
  - `StartInterrupts` (16): four u32;
  - `StartFramebuffer` (32): two u64, four u32;
  - `StartBootTimes` (40): five u64.
- `StartHeader` and `StartEntry` are unchanged.
- The doc comment of `IRQ_BYTES` changes to "bytes of one entry of the interrupt table".

---

## Part 3. For the humans

Each point gives my recommended rule (already written into Part 1), the alternatives and what each costs.

1. **What "revocable in one operation" means (research axis 4).**
   - *Recommended:* `task_revoke` *stops* every thread of the task in one write. The capabilities are then removed by the supervisor's `cap_delete` of the task's spaces, in bounded steps.
     - It costs nothing on the fast path.
     - It is honest with rule 4.
     - What a task moved out (rather than derived) survives it, so a supervisor gives tasks derived capabilities only.
   - *Alternative A:* a task tag on every capability, checked on every use. "Everything derived from it stays under the task" then holds literally, and it is stronger for the research claim. It costs 8 bytes per slot (32 to 40, likely 48 with alignment), or a proxy object per attached capability and one more load on every call, the IPC fast path included (the 1.2 × seL4 gate).
   - *Alternative B:* keep the old sentence. That leaves a contract that contradicts rule 4.
2. **The task without a time budget and without a log.**
   - *Recommended:* the kernel task holds marks, an identifier and threads only.
     - The time budget of an agent task is the `sched` objects its supervisor binds to its threads. Budget follows the call, so the cost is counted end to end there.
     - The log is the agent runtime's journal and the system log, keyed by the task identifier the kernel stamps.
   - *Alternative:* a CPU-time allowance in the task, debited at every charge of a `sched`. That is one more write per charge. It also needs a message between kernels for every thread on another node, unless each node has its own allowance. A kernel log ring per task (a frame the kernel appends to) costs a write per message on the hot path.
3. **A task lives on one node.**
   - *Recommended:* a thread can be attached only to a task of its own node. An agent task spread over *k* nodes is *k* task objects, revoked by *k* calls, each of which stops its part at once.
   - *Alternative:* a task that spans nodes, with the revoked flag replicated by the protocol between kernels. Stopping is then no longer one write. It needs a two-phase protocol like `cap_revoke` and a formal model, which is work for the multi-core part.
4. **Marks flow both ways when capabilities move.**
   - *Recommended* as written. It costs over-marking: whoever hands any capability to a marked party gets marked, even for a read-only frame. This feeds "the spread of sticky marks" open point.
   - *Alternative:* one way only, with no over-marking. That leaves an overt channel through writable frames that an unmarked party gives to a marked one. A finer rule (only capabilities with `write`) is possible, but the kind of every capability would have to be judged at delivery, and an endpoint capability is also a channel back.
5. **The share of memory per node (D-107).**
   - *Recommended:* an equal split by address, in 2 MB units, with the boot node first (it gets the low memory) and the image region added to it. The first process sees only the boot share.
   - *Alternative A:* weights by core class (more for performance cores).
   - *Alternative B:* a table in the boot image. Flexible, but it must be signed and kept in step with each machine.
   - *Alternative C:* the boot node takes most, the others a fixed reserve (for example 256 MB). Big processes stay on one node and avoid remote mappings, but losing the boot node loses most processes, against "no node is necessary to the machine".
   
   With an equal split on a 24-core desktop with 64 GB, each node has about 2.6 GB. A large process (model weights) depends on remote mappings from the first day.
6. **Device memory and line interrupts belong to the boot node.**
   - *Recommended* as written: the boot node owns every device untyped and every IOAPIC input. While the boot node is reloaded, every driver loses its MMIO mappings and the line interrupts stop. The drivers restart by their protocol once the node is back.
   - *Alternative:* partition the device ranges and the PCI segments between nodes at start-up. Drivers then survive the loss of a node other than their own, but the platform service must place each driver on the node that owns its device, and a device that spans ranges is hard to place.
7. **The interrupt table is fixed kernel memory, not memory from an untyped.** This is a second exception to rule 3, after the start-up objects. It costs 12 KB per node. The alternative (an `irq` from an untyped) loses the revocation of all vectors through the control capability, and a vector would exist only while someone pays for it, although the hardware has it regardless.
8. **No vector state in the register calls.** A user-space debugger of native services sees only the general registers. The alternative (a frame argument that receives the XSAVE image) puts a format into the contract that depends on the processor's features and changes with them (APX, AMX).

---

## Part 4. What a reference model of this group must cover

**Inputs** besides calls:

- the hardware event "vector *v* arrives on node *n*";
- for a level line, "line asserted" and "line released";
- the start-up description: RAM ranges, device ranges, kept ranges, module lengths and their segment flags, number of cores, MAXPHYADDR.

**States:**

- **irq:** idle, armed or fired; pending; bound notify and bits; level source masked or not.
- **task:** identifier, marks, mark-aware, revoked, the ordered list of attached threads.
- **thread:** its own marks; the bindings (cspace, aspace, fault endpoint with badge, task); a fault wait as a kind of wait; the register block as an opaque array of `REGS_WORDS` words, with the masking function of the architecture as a parameter.

**Invariants worth checking at every state:**

1. At most one irq per (node, vector), and at most one per GSI.
2. An irq is bound if and only if it is linked in the list of exactly one live notify of its node. An idle irq is in no list.
3. A level source is masked if and only if its irq is idle or fired.
4. Between two `irq_ack` calls on one irq, at most one signal comes from it. An arrival on an armed irq signals exactly once.
5. After the destruction of a notify completes, no irq refers to it. After the destruction of an irq, its vector is free and its source is masked.
6. The effective marks of each live thread never lose a bit, from state to state.
7. At every delivery, the stamped marks are equal to the sender's effective marks before the delivery | the added marks, and the stamped identifier is that of the sender's task, or 0.
8. A thread attached to a mark-aware task never changes its marks at a receive. A sender attached to a mark-aware task never takes marks from a capability transfer.
9. Every thread attached to a revoked task is never runnable, and every call it makes returns `gone`.
10. `task_revoke` returns `again` while attached threads remain, and success exactly on the call that detaches the last one. Repeated calls end. A step detaches at most 32 threads.
11. Task identifiers are unique among the tasks ever made on a node in one run, and never 0. The start-up task is 1.
12. Each binding of a thread names a live object, or nothing. Undoing bindings at a destruction counts in the 32 of a step.
13. A thread with no address space that is made to run takes fault kind 7, and a thread with no usable fault endpoint that faults is suspended with unchanged registers.
14. A fault wait ended by `thread_cancel` with number 0, or by `gone`, leaves the thread suspended with unchanged registers. Answer label 0 leaves the registers unchanged, label 1 sets exactly words 0 and 1, and any other label suspends.
15. `thread_write_regs` never stores a non-canonical word in the positions the architecture names, and never a flag bit outside the mask. It is `busy` on a waiting thread. `thread_read_regs` returns what the last write stored, masked.
16. **Start-up, derived from a description:**
    - every usable byte of ordinary memory is in exactly one share;
    - every byte of the boot share is in exactly one ordinary untyped;
    - every untyped is a naturally aligned power of two, at least 4 KB;
    - device untypeds and ordinary untypeds never overlap, and neither overlaps a kept range;
    - the slots follow the fixed table and the order of the ranges, and the number of slots is the formula;
    - each start-up capability is at depth 1, except the frames, which are at depth 2 under the image untyped, whose watermark is after the message page;
    - the start-up page parses back to the same state (an oracle check: the model writes the page, a parser reads it, and both agree).

**Abstract counters**, to check the bounds: per call and per arrival, the number of controller writes, threads woken and bindings undone, against the bounds above.

---

## Part 5. Sources

Checked on the web on 14 November 2026:

- seL4 API reference: `seL4_IRQControl_Get`, `GetIOAPIC` (ioapic, pin, level, polarity, vector), `GetMSI` (PCI bus, device, function, handle, vector), `seL4_IRQHandler_Ack`, `SetNotification` and `Clear`, and `seL4_TCB_ReadRegisters` / `WriteRegisters` (count, suspend source, resume target). https://docs.sel4.systems/projects/sel4/api-doc.html
- seL4 start-up capability slots (`seL4_CapInitThreadTCB = 1` ... 16 initial capabilities) and `seL4_BootInfo` (`untypedList` of physical address, log2 size and device flag; slot regions for untypeds, image frames and empty slots). https://raw.githubusercontent.com/seL4/seL4/master/libsel4/include/sel4/bootinfo_types.h
- seL4 fault handling: the label gives the fault type, a reply with label 0 restarts the thread, and with no receiver "the kernel will simply suspend the faulting thread". https://docs.sel4.systems/Tutorials/fault-handlers.html
- Zircon `zx_interrupt_bind`: one port only, a packet sent at once if already triggered when bound, unbinding drops queued packets. https://fuchsia.dev/reference/syscalls/interrupt_bind
- Zircon `zx_interrupt_ack`: back to untriggered, and triggers again at once if still asserted. https://fuchsia.dev/reference/syscalls/interrupt_ack
- Zircon `zx_interrupt_create`: edge or level modes, virtual interrupts, created from an IRQ resource. https://fuchsia.dev/reference/syscalls/interrupt_create
- Zircon `zx_msi_create`: one interrupt object per MSI of an allocation. https://fuchsia.dev/reference/syscalls/msi_create
- Linux generic IRQ: level flow masks and acknowledges, then unmasks after the handler; `IRQF_ONESHOT` runs the threaded handler with the line masked. https://docs.kernel.org/core-api/genericirq.html
- Barrelfish/DC, "Decoupling Cores, Kernels, and Operating Systems", OSDI 2014: the kernel control block as the handle on the state of an OS node. https://usenix.org/node/186143 and https://barrelfish.org/publications/zellweger-decoupling-cores.pdf

From memory, not checked:

- the remappable MSI address format of Intel VT-d (handle bits 19:5 and bit 2, format bit 4, subhandle valid bit 3), and the compatibility format (destination APIC ID in bits 19:12);
- IOAPIC level inputs (a masked input that is still asserted is delivered again when unmasked) and the 8-bit destination limit without remapping;
- the x86-64 exception vectors and which of them push an error code, CR2 and DR6;
- CPUID leaf 0x1A for the core type;
- the user-modifiable bits of rflags;
- the danger of returning to a non-canonical rip (the sysret problem on Intel);
- sel4runtime setting up a static stack for the root task;
- the UEFI memory types.
