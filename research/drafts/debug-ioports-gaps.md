# Draft: debugging, `ioports`, and the other gaps of the kernel contract

Written 15 November 2026 for the two owners, following the brief `drafts/BRIEF.md`. Nothing under `/Users/btw/Documents/repos` was edited. It covers three things: the debugging group (`debug_write`, `trace_emit`, the trace rings, the crash record, the console, the debugger stub); the `ioports` object; and every other call or object of the contract whose behaviour no section fixes. It also goes through "Open points" line by line, and checks these groups against ARM64 and RISC-V. It was written after reading the cores draft (`research/drafts/symmetric-nodes-recovery.md`) and does not contradict it; where the two meet, the point is named.

**Verified** means checked on the web today, with the URL in part 6. **From memory** means not checked.

Part 1 is the text to paste into `kernel-interface.md`. Parts 2 to 6 are for the owners.

---

## Part 1. Text for kernel-interface.md

The two subsections below go after [Tasks and marks](#tasks-and-marks) (and after "Cores", if the cores draft is merged first). The subsection "Destruction: the links no group gathered" goes at the end of [The derivation tree](#the-derivation-tree).

> ### Debugging
>
> **Proposed, 15 November 2026: written, no reference model yet, not reviewed.** It covers the `debug` object, the calls `debug_write` and `trace_emit`, the trace rings, what the kernel traces, the crash record and how it reaches the next boot, the console, the two kinds of kernel build and the debugger stub. The rules of the sections above apply: order of checks, dying objects, bounded calls.
>
> #### What the kernel keeps for debugging
>
> - **The debug area of a node.** Each node has a debug area of 17 pages (69,632 bytes) in kept memory. Page 0 holds the area's header (64 bytes) and the node's crash record (4,032 bytes). Pages 1 to 4 hold the **kernel ring**: 256 entries of 64 bytes. Pages 5 to 16 hold the **user ring**: 768 entries of 64 bytes. Only the kernel that runs the node writes its area. Every kernel maps every debug area read-only, and its own node's area writable. This is a "trace buffer per core" of [Debugging](#debugging), per node because a node can be parked on another core.
> - **The crash area.** The debug areas of all nodes sit in one **crash area**: one header page, then the debug area of node *i* at offset 4,096 + *i* × 69,632. The crash area starts on a 2 MB boundary and its length is rounded up to 2 MB. It is kept memory: it is in no untyped and is never cleared during the boot. The loader keeps two crash areas, A and B. One is the area of this boot. The other holds what the previous boot wrote, and it is kept, untouched, for the whole boot (see [The crash record](#the-crash-record)).
> - **Why kept memory and not a frame supplied by user space (design choice).** The kernel must trace before any process exists, and the record must be readable after the node that wrote it is dead, and after the machine restarts. A frame from a node's share dies with the node; a frame given by user space does not exist at machine start. seL4's benchmark log takes a large frame from user space (verified), but it records only while a process asks for it. The cost: 136 KB of kept memory per node (two areas), 2.3 MB for 14 nodes, 136 MB at the maximum of 1,024 nodes.
>
> #### The trace rings
>
> An **entry** is 8 words of 64 bits:
>
> | Word | Content |
> |---|---|
> | 0 | sequence *s*, at least 1. The entry with sequence *s* sits at index (*s* − 1) mod *N* of its ring, where *N* is the ring's number of entries. Word 0 is 0 while the entry is being written |
> | 1 | the instant, a value of the [clock](#clock) |
> | 2 | bits 0-15 the code, bits 16-31 flags (bit 16 *continued*: the text goes on in the entry with the next sequence of the same ring; the other bits 0), bits 32-63 the generation of the node that wrote it |
> | 3 | the task identifier of the thread concerned, 0 if none |
> | 4 | the effective marks of the thread concerned ([Tasks and marks](#tasks-and-marks)), 0 if none |
> | 5-7 | the payload, by code (below) |
>
> The **header** of a debug area (64 bytes, at offset 0 of page 0): magic (u32), version (u16, 1), node index (u16), generation of the writing node (u32), reserved (u32, 0), next sequence of the kernel ring (u64), next sequence of the user ring (u64), number of kernel entries suppressed by the rate limit since machine start (u64), then 16 reserved bytes, 0.
>
> - **Writing.** The kernel writes word 0 to 0, then words 1 to 7, then word 0 to *s*, then the ring's next sequence to *s* + 1, each store ordered after the previous one (release order). One kernel writes each area, and its events are serial, so no lock is needed. When the ring is full the oldest entry is overwritten: writing never fails and never waits.
> - **Reading.** A reader reads the next sequence *n*. For each *s* from max(1, *n* − *N*) to *n* − 1, it reads word 0, copies the entry, then reads word 0 again. It keeps the entry only if both reads give *s*. A reader never stops a writer. Entries of all rings are ordered by their instant; the clock is the same on every core.
> - **Two rings (design choice).** The kernel ring receives only the kernel's own entries (codes below 16); the user ring receives only `debug_write` and `trace_emit` (codes 16 and 17). So a holder of a `debug` capability that floods its ring never evicts a DMA fault or a failure. The alternative, one ring, lets any holder erase the evidence the kernel recorded.
> - **Across generations.** A node started fresh (cores group) keeps its debug area. It checks the magic and version of the header. If they are right, it sets the generation and goes on from the next sequences found there. Otherwise it clears the area and starts at 1. It reads nothing else from the area: the ring is data for readers, and a damaged header can only produce wrong indexes, which are taken modulo *N*. It never writes the crash record of the area, except for its own failure. So the record of a dead generation stays readable until the next failure of the node.
> - **How user space reads them.** Through a **kept frame** (see [Frames](#frames)) of the crash area, in the start-up space. With `read`, it is mapped read-only. Whoever holds it reads every node's rings and records, without a call and whether the writer is alive or not.
>
> #### What the kernel traces
>
> | Code | Event | Words 5, 6, 7 |
> |---|---|---|
> | 1 | Text of the kernel (boot steps, warnings). Its wording is the implementation's | 24 bytes of UTF-8 text, zero-padded |
> | 2 | A fault recorded by an IOMMU unit: blocked DMA, or an interrupt refused by remapping. Written by the kernel that drives the unit | word 5: the device address, or the remapping handle; word 6: requester ID (bits 0-15), PCI segment (16-31), unit index (32-47), the architecture's reason code (48-55), bit 56 write, bit 57 interrupt remapping |
> | 3 | Entries suppressed | word 5: the code suppressed; word 6: the number suppressed, 0 when a unit lost records by overflow and does not say how many; word 7: the unit index for code 2, otherwise 0 |
> | 4 | An IOMMU unit did not confirm an invalidation within `IOMMU_WAIT_NS`. A failure of the node follows ([IOMMU](#iommu)) | word 5: unit index |
> | 5 | A fault with no handler: the thread became suspended and the fault was dropped ([Faults](#faults)) | word 5: the fault kind (low 32 bits) and the architecture's exception number (high 32); word 6: word 0 of the fault; word 7: word 4 of the fault. Words 3 and 4 are the thread's task and effective marks |
> | 6 | A failure of the node: the kernel found an error in itself | word 5: the reason of the crash record; word 6: the kernel's instruction pointer; word 7: the architecture's detail word 0 |
> | 7 | A hardware error that was corrected or contained | words 5-7: the architecture's record (x86-64: bank, IA32_MCi_STATUS, IA32_MCi_ADDR) |
> | 8 | An interrupt on a vector that no entry claims, or a spurious one | word 5: the vector; word 6: arrivals since the last entry for this vector |
> | 9 | A transition of a member word made by this node (cores group) | word 5: the node; word 6: the new member word |
> | 16 | Text of `debug_write` (user ring) | 24 bytes of text |
> | 17 | `trace_emit` (user ring) | the three words given |
>
> - **Rate limit of the kernel ring (design choice).** Each code except 6 may write at most 16 entries per window of 1 ms of its node. A window opens at the first entry of that code when the previous window is at least 1 ms old. An entry over the limit is not written: it adds one to the suppressed counter of the header and to a counter for the code. The first entry of that code allowed in a new window is preceded by one entry of code 3 with that counter, which is then zeroed; this entry of code 3 is not limited. Why: a device that keeps faulting, or a supervisor that resumes a faulting thread in a loop, must not erase the rest of the ring. The counters sit in the node block, fixed at start.
> - **DMA faults are read by the kernel that drives the unit**, in the unit's fault interrupt (a vector of the kernel). It reads at most 16 fault records per interrupt and clears them. If records remain, it masks that interrupt of the unit for 1 ms (a due event of its timer queue), then unmasks it and reads again. Faults stay blocked meanwhile, which is the unit's job, not the trace's. Records lost by overflow of the unit are reported by code 3 with number 0.
> - **The kernel never traces on the fast path.** `call`, `reply_recv`, `signal`, an interrupt that is signalled, and a fault that is delivered write no entry. What the kernel traces are rare events; a profiler of the fast path is outside the kernel ([Observability](platform.md#observability)).
>
> #### The `debug` object
>
> - Each node has one `debug` object. It is made at the node's start-up from no untyped (rule 3). Its root capability is in slot 5 of the node's start-up space, at depth 1, with every right. `untyped_retype` never makes one (`invalid`, with `irq`, `irq_control` and `iommu`). It holds no state: it is the authority to write into the user ring.
> - Its root can be deleted, like the root of any object made at start-up. The object is then destroyed and gives its memory back to no one. Nothing waits on it and nothing is linked to it, so the destruction undoes nothing. The kernel ring is not part of the object: it goes on.
>
> | Call | Arguments | Result | Rights and rules |
> |---|---|---|---|
> | `debug_write` | debug, length, text | | `write` on the debug. The text is the first ⌈length / 8⌉ message words of the call, byte *k* being byte *k* mod 8 (little-endian) of word *k* div 8. Length at most 512 (`invalid`). Then, if the text needs words of the message page and the thread has none, `invalid`. No state error |
> | `trace_emit` | debug, word 0, word 1, word 2 | | `write` on the debug. Any three words. No other check |
>
> - **Effect of `debug_write`.** With length 0, nothing is written and the call succeeds. Otherwise ⌈length / 24⌉ entries of code 16 are written into the user ring of the caller's node, with consecutive sequences, each holding the next 24 bytes; the last one is zero-padded. Every entry but the last has the flag *continued*. Word 3 is the caller's task identifier, word 4 its effective marks. The kernel does not check that the text is UTF-8.
> - **Effect of `trace_emit`.** One entry of code 17, with the three words, the caller's task identifier and effective marks.
> - **The ring of the caller's node, whatever node holds the `debug` object (design choice).** These calls change no state of the object, so they send no message between kernels: the capability is checked as for any call (slot, kind, rights, dying), and the caller's kernel writes its own area. The order of a node's entries is then the order of its events, and no kernel writes into another node's memory. The same rule holds for `ioport_in` and `ioport_out` ([I/O ports](#io-ports)). The alternative, rule 7 applied literally, costs a message for each trace entry, and makes one node write the trace of another.
> - **The marks are stamped on each entry.** A ring is a channel from any holder to every reader, like a message. A reader that keeps or forwards entries (the log service) treats them by their marks, as a mark-aware service treats a record. Writing an entry marks nobody, since nothing is received.
> - `debug_write` and `trace_emit` never wait, never return `would_wait` or `again`, and write at most 22 entries and one entry. A thread whose task is revoked, or whose space is dying, gets `gone` first, as from every call.
> - **Who holds it.** The first service gives copies to the services it trusts and to the components that a developer key authorizes ([security.md](security.md#permissions)). A holder can fill the user ring, never the kernel ring.
>
> #### The crash record
>
> **The node record** is at offset 64 of page 0 of the node's debug area (4,032 bytes):
>
> | Offset | Content |
> |---|---|
> | 64 | commit (u64): the boot identifier of the crash area when the record is complete, 0 while it is written |
> | 72 | generation (u32), reason (u32) |
> | 80 | instant (u64) |
> | 88 | the node's member word as last seen (u64; 0 without the cores group) |
> | 96 | 32 words of detail, whose layout the architecture layer fixes (x86-64: vector, error code, rip, rsp, rflags, cr2, cr3, rax, rbx, rcx, rdx, rsi, rdi, rbp, r8 to r15, IA32_MCG_STATUS, and the bank, IA32_MCi_STATUS, IA32_MCi_ADDR and IA32_MCi_MISC of the first bank with a valid error; the rest 0) |
> | 352 | 128 bytes of UTF-8 text, zero-padded |
> | 480 | a copy of the last 32 entries of the kernel ring at the time of the record |
> | 2,528 | a copy of the last 16 entries of the user ring |
> | 3,552 | reserved, 0, to the end of the page |
>
> Reasons: 1 assertion of the kernel, 2 unexpected exception in kernel mode, 3 double fault, 4 uncorrected hardware error, 5 stopped by a fence (cores group), 6 an IOMMU unit that does not confirm, 7 containment violated, 8 start-up refused.
>
> - **Who writes it.** The kernel of the node, when it finds a failure in itself, before it reports it (the `panic` word of its node beacon, cores group) and parks. And the node's handler of the fence signal (cores group, reason 5), within `NMI_GRACE_NS`, but only if the record does not already hold a committed record of the same generation. The writer sets commit to 0, writes the rest, then writes commit last. A reader accepts a record whose commit equals the boot identifier in the header of its crash area. A record from a kernel that went wrong may hold anything: it is data, never trusted.
> - **The machine record.** The header page of the crash area holds: magic (u64), version (u32, 1), number of nodes (u32), boot identifier (u64), sequence (u64), bytes per debug area (u32), build (u32: 0 production, 1 development), 8 reserved bytes, then the **stop record**: commit (u64), node (u32), reason (u32), instant (u64), 128 bytes of text. The kernel that stops the whole machine (a containment violation, or a start-up it refuses) writes the stop record before it restarts the machine. The rest of the page is reserved, 0.
> - **The boot identifier** is 64 bits drawn from the kernel's generator at machine start, after it has mixed in the loader's seed. It only tells the records of this boot from older ones.
> - **The restart after a complete stop** is a warm reset, so that memory keeps its contents: on x86-64, the value 0x06 written to port 0xCF9 (reset control of the chipset, from memory), then, if the machine still runs after 1 ms, a triple fault. The kernel reads no ACPI table that gives the reset register, by D-112.
>
> **How the record reaches the next boot.** The loader and the kernel are one signed image, so this is part of the contract.
>
> 1. The loader keeps the two crash areas at addresses recorded in one non-volatile UEFI variable (two pairs of base and length). It writes that variable only when it must place an area again: at the first boot, when the number of nodes needs a larger area, or when an address can no longer be allocated. It does not write it at every boot, to spare the firmware's flash.
> 2. At each boot it allocates both areas at their addresses (loader data). An area that cannot be allocated is lost and placed again.
> 3. The **previous** area is the one whose header has the right magic, version and the greater sequence; if neither header is valid, there is no previous area. The **current** area is the other. The loader hands over the bases and lengths of both, and the previous sequence (0 if none).
> 4. The boot kernel clears the current area, writes its header with sequence = previous sequence + 1 and a new boot identifier, and starts every debug area at sequence 1. It never writes the previous area. Both areas are kept memory for the whole boot, listed in the entry `Kept`.
> 5. The previous area is given to the first service as a kept frame (start-up slots), and described by the entry `CrashRecord` of the start-up page. A service (the storage service, by the first service's policy) copies the records it finds valid to the raw region of the store ([storage.md](storage.md#partitions)).
>
> - **Why memory and not the disk (design choice).** The kernel has no disk driver, and its failure path must not depend on one. Memory survives a warm reset on the machines of version 1 (from memory: this is what Linux's ramoops relies on, verified, which needs "persistent RAM"). The alternatives are a polled disk writer in the kernel, which puts a storage driver in the trusted base; a second crash kernel per node, as Linux kdump (from memory), which costs a reserved image per node; or the UEFI variable store at failure time, which needs the runtime services of the firmware on a failing core. Within a boot, the record of a node that died while the machine goes on is in memory anyway, and the supervisor copies it when the cores group signals the change.
> - **Where it is not kept.** A firmware that clears memory at reset (some servers initialise error-correcting memory at every reset, from memory), or a machine without a UEFI variable store, gives no previous area. The record of the current boot is then the only one, and a complete stop loses it.
>
> #### The console
>
> - **The console device** is named by the boot image: none; a 16550 UART on I/O ports (x86-64; base port); a 16550 UART in memory (physical address, register stride 1 or 4 bytes); a PL011 (ARM64; physical address); the SBI debug console (RISC-V, the DBCN extension, verified); or, in a development image only, the debug capability of an xHCI controller (its PCI segment, bus, device and function, and the address of its registers, which the loader reads before `ExitBootServices`). The kernel uses no firmware table to find it (D-112).
> - **The device is kept from user space.** The 8 ports of a UART on I/O ports are kernel ports ([I/O ports](#io-ports)). The page of a UART in memory, and the register range of the xHCI function, are kept: they are in no device untyped. The xHCI function used by the kernel is `busy` for `iospace_attach` ([IOMMU](#iommu)). The kernel never enables the device's interrupts: it polls.
> - **One node drives the device**, the **console node**: the boot node in this contract, and the holder of a unit role `console` if the cores group's roles are adopted. No other node touches it. A node's text reaches the console through its rings: the console node reads every debug area, which is kept memory mapped read-only in every kernel.
> - **What it prints.** The entries of every ring, ordered by instant (at equal instants: the smaller node index, then the kernel ring, then the smaller sequence). Codes 1 and 16 are printed as text, one run of *continued* entries without interruption; the other codes as one line with their words. Every line names its node and generation, and for codes 16 and 17 the task. Bytes below 0x20 other than line feed and tab, and 0x7F, are printed as `?`. The exact layout of a line is the implementation's: the console is for people, and no call returns it. When a ring has overwritten entries the console had not printed, it prints the number lost.
> - **Pacing (design choice).** While entries are not printed, the console node has a due event every 1 ms (in its timer queue, counted among the 16 due events of an interrupt) at which it writes at most 16 bytes, the depth of a 16550's transmit queue; that matches 115,200 baud. Its time is kernel time of an event, charged as an interrupt is ([What runs next](#what-runs-next)). It keeps one cursor per ring of each node, fixed at start. Choosing the next entry reads at most 2 × *n* ring heads. Why not write at every event: an access to a legacy UART takes about a microsecond (from memory), which the fast path cannot pay.
> - **Direct writes**, without the rings, happen only: during machine start-up, before a second core runs (the kernel that refuses to start writes its message there, then in the stop record); when the console node itself fails (it writes its record directly, then parks); and while the debugger stub holds the machine.
> - **The console is output only in a production image.** The kernel reads the device only in a development image, for the debugger stub.
>
> #### Two builds, and the debugger stub
>
> - **A kernel image is built either for production or for development.** Both give the same result for every call; the start-up page and the crash area header say which one runs.
> - **A production image has none of the following**, neither code nor data: the debugger stub; any reading of the console device; any use of the processor's hardware breakpoints (on x86-64, DR7 stays 0); the xHCI debug capability; the stop of every core for the stub. A production kernel refuses to start, with a stop record of reason 8, if its boot image asks for any of them.
> - **Present in every build:** `debug_write`, `trace_emit`, the kernel ring and its codes, the crash records, the crash areas and their handover, and console output when the boot image names a device. A server image may name a serial console; a desktop image names none.
> - **The debugger stub** (development images only) speaks the gdb remote protocol over the console device: packets `$data#checksum` acknowledged by `+` or `-`, and at least the commands `?`, `g`, `G`, `m`, `M`, `c` and `s` (verified). It is entered: when the console node reads the byte 0x03 (the console node polls the device's receive status at each console event); at a kernel breakpoint or watchpoint that gdb set with the hardware debug registers (kernel code is never patched, since it is read-only); and at a failure of any node, if the boot image's development option *stub on failure* is set (otherwise a failure follows the ordinary path of the cores group).
> - **Stopping the machine.** The core that enters the stub sends the architecture's strongest signal (x86-64 NMI; ARM64 SDEI event or pseudo-NMI; RISC-V interrupt, as in the fence of the cores group) to every core that runs a node. Each one saves its registers, vector state included, in a slot of its node kept for the stub, and waits on a release word in kept memory. A core that does not stop within 10 ms is shown to gdb as running. gdb sees one thread per node. It can read and write registers, the kernel memory that node maps, and physical memory (by a monitor command); set hardware breakpoints; step; continue. The clock goes on: after the release, events fall due late and are processed as at any late interrupt. Before the release, the stub clears every open observation of every node beacon (cores group), so that no node accuses another for the time stopped.
> - **The release word and the stop are shared state between nodes.** They exist only in development images, which may break the rule of [Multi-core structure](kernel.md#multi-core-structure) for this purpose: the production kernel has none of it.
> - **How the stub stays out of the trusted base of a production machine (design choice).** First, the production image has no stub code at all, so no bug of the stub exists there. Second, a development image is signed by a developer key, which the firmware trusts only if the user enrols it ([security.md](security.md#secure-boot)). Third, the disk key is sealed in the TPM against the system's signing key ([security.md](security.md#disk-key)), so a development image does not unseal the disk of a production installation. Fourth, the shell shows a permanent mark, drawn by the system, when the start-up page says development. The alternative, a stub present in every image and enabled by a capability, puts a parser of a device's input in the kernel of every machine.
> - **The transport (design choice).** The stub uses the console device. On QEMU, a 16550. On the reference desktop, a 16550: the board's serial header or a PCIe serial card, given as a UART in memory. The xHCI debug capability (the "USB debug port" of D-058) is supported as an option. It shares the PCI function of the xHCI controller, hence its requester ID and its IOMMU context (from memory). So the kernel must keep that whole function, and every USB port of that controller is lost to user space in that image. On a desktop with one xHCI controller, that is every USB port.
>
> #### Debugging a component
>
> - **The kernel has no object for it.** "Debugging a component is a capability" ([security.md](security.md#permissions)) is made of what exists: `read` and `write` on its threads (`thread_read_regs`, `thread_write_regs`, `thread_suspend`, `thread_resume`), frames to map its memory, and its faults. The supervisor is the fault handler of the component's threads. It forwards the faults of kind debug to the debugger it authorised, because changing the fault endpoint by `thread_configure` would need `manage` on the component's capability and address spaces.
> - **Hardware breakpoints are not given to user threads (design choice).** The register block has no debug register, and the kernel never enables them for a user thread. A user debugger writes a breakpoint instruction through a writable mapping of its own (a copy of the code frame, given by the compile service) and steps with the trap flag (x86-64: TF is in the user mask of rflags). A fault of kind debug therefore always comes from a breakpoint instruction or a single step; word 4 is DR6. The alternative, debug registers in the register block, adds per-thread state saved at every switch, and four addresses that every architecture expresses differently.
>
> #### Architectures
>
> The same on every architecture: the debug area, the rings and their entries, the codes, the rate limit, the records and their handover, the two builds, the calls. The architecture layer fixes: the detail words of the crash record; the console devices it supports; the signal that stops a core for the stub and for the fence; the hardware debug registers the stub uses (x86-64 DR0 to DR7; ARM64 breakpoint and watchpoint registers; RISC-V Sdtrig triggers, when the firmware lets S-mode use them, from memory); the warm reset (x86-64 port 0xCF9 then a triple fault; ARM64 PSCI `SYSTEM_RESET2` with a warm reset, from memory; RISC-V SBI `SRST` with a warm reboot, from memory); the hardware error records of code 7; and single stepping for user debuggers (x86-64 TF; ARM64: the step bit of SPSR is in the user mask of the flags word, and the kernel sets MDSCR_EL1.SS when it resumes such a thread; RISC-V has none, and a debugger places a breakpoint at the next instruction).

> ### I/O ports
>
> **Proposed, 15 November 2026: written, no reference model yet, not reviewed.** x86-64 only. It covers the `ioports` object and the calls `ioport_in`, `ioport_out` and `ioports_issue`.
>
> - **The object.** Each node has one `ioports` object on x86-64. It is made at the node's start-up from no untyped. Its root capability is in slot 7 of the node's start-up space, at depth 1, with every right. On other architectures slot 7 is empty and no `ioports` object exists. `untyped_retype` never makes one (`invalid`).
> - **A capability carries a range** [*first*, *last*] of ports, 0 ≤ *first* ≤ *last* ≤ 65,535, in the word that holds the badge of other kinds. The root's range is [0, 65,535]. `cap_inspect` returns it as the badge: *first* in bits 0-15, *last* in bits 16-31, the other bits 0. `cap_derive` and `cap_move` keep the range; a badge other than 0 asked of `cap_derive` is `invalid`, as on every kind but `endpoint` and `notify`. Only `ioports_issue` narrows a range.
> - **Kernel ports.** Some ports are the kernel's for the whole boot: 0x20-0x21 and 0xA0-0xA1 (the legacy PIC, which the kernel masks), and the 8 ports of the console when it is a UART on I/O ports. An access that touches one of them is `busy`, whatever the capability. A range may contain them. They are published in the start-up page (entry `Debug`, and the fixed PIC ports).
>
> | Call | Arguments | Result | Rights and rules |
> |---|---|---|---|
> | `ioport_in` | ioports, port, width | value | `read` |
> | `ioport_out` | ioports, port, width, value | | `write` |
> | `ioports_issue` | ioports, destination, first, last | | `derive` on the ioports |
>
> Checks of `ioport_in` and `ioport_out`, in the order of [Order of checks](#order-of-checks):
>
> 0. On an architecture without I/O ports: `unsupported`, before any argument is looked at (after the checks that come before every call: a thread bound to no space, of a revoked task, or in a dying space gets `gone`).
> 1. The ioports: slot, kind, `read` (in) or `write` (out). A dying object is `gone`.
> 3. The plain arguments, each `invalid`: the width is 1, 2 or 4; *first* ≤ port and port + width − 1 ≤ *last* (computed without overflow, so a port above 65,535 fails); for `ioport_out`, the value is below 2^(8 × width).
> 4. The state: an access that touches a kernel port is `busy`.
>
> Effect: the kernel executes one `in` or `out` of that width at that port. The value read is zero-extended to 64 bits. Constant work: one access.
>
> Checks of `ioports_issue`:
>
> 0. As above: `unsupported` on an architecture without I/O ports.
> 1. The ioports: slot, kind, `derive`. Dying is `gone`.
> 2. The destination: as any destination ([Order of checks](#order-of-checks)).
> 3. The plain arguments, each `invalid`: *first* ≤ *last* ≤ 65,535; [*first*, *last*] lies inside the range of the source; then the depth checks (a child deeper than 64 is `invalid`).
> 4. The state: the destination slot is not empty, `no_slot`.
>
> Effect: the new capability is a child of the source, with the source's rights and the range [*first*, *last*]. Constant work.
>
> - **The kernel executes each access (design choice).** The alternative is the processor's I/O permission bitmap: 65,536 bits, 8 KB, read by the processor at each `in` and `out` from a user mode whose privilege is above IOPL (verified). Kept per thread, as Linux does, it adds 8 KB to every thread that uses ports and a copy at each switch to such a thread (from memory, the LKML thread in part 6). Kept per address space, as Zircon does (verified: the bitmap belongs to the address space and is written into the core's TSS at each switch, by ranges), it adds 8 KB per space and a write of the TSS at each switch between spaces with different ports, and a message to every core of the group when a range changes. A call costs one system call per access, under a microsecond, against the access itself, about a microsecond on the legacy bus of a chipset (from memory). The users are rare and slow: the ACPI registers and `SystemIO` regions of uACPI in the platform service, the PS/2 controller, the CMOS clock, legacy serial ports, the I/O BARs of old PCI devices, and the `inb`/`outb` of the Linux emulation layer. seL4 does the same (verified: the kernel checks the range of the capability, then executes `in8`, `in16`, `in32` itself). The call keeps no state in the kernel and nothing on the path of a switch.
> - **User code cannot execute `in` or `out`.** User threads run with IOPL 0, which they cannot change (IOPL is not in the user mask of rflags, [Register calls](#register-calls)), and the TSS of every core has no bitmap (its I/O map base lies beyond the TSS limit). An `in` or `out` from user code is a fault of kind protection (#GP).
> - **No string I/O and no batch.** `ins` and `outs` are not offered: no device of version 1 needs them (no IDE disk). A batch of accesses in one call is not offered either; the cost per access is measured by a gate if a driver ever does many.
> - **No exclusive ranges (design choice).** The kernel does not check that two capabilities hold disjoint ranges. seL4 refuses to issue a port twice (verified, a bitmap of issued ports), which is kernel state shared by every core here. Who may touch which device is the platform service's decision, and revoking the parent capability takes the ranges back.
> - **Several nodes.** Every node's root covers the same ports; the platform service hands ranges out from one of them. Like the debug calls, the port calls are executed by the caller's kernel, whatever node holds the object: a port is a resource of the machine, and the call changes no object state.
> - **Destruction.** Deleting a capability removes its descendants first. Destroying the object undoes nothing, gives its memory back to no one, and does not touch the devices: a device keeps the state its ports were given. A node started fresh has a new root.
> - **ARM64 and RISC-V** have no I/O ports. The I/O space of PCI is a window of memory there (Linux maps it at `PCI_IOBASE` on both, verified), so the platform service gives a driver a device frame of that window. The three calls are `unsupported`, and `ioports` is the only object of the contract that exists on one architecture only ([Architectures](#architectures)).

> #### Destruction: the links no group gathered
>
> - **A bound endpoint and notify.** When an endpoint or a notify bound by `notify_bind` is destroyed, the binding is undone first among the links of [What else destruction undoes](#the-derivation-tree), after the waiting threads are woken: one unit of the 32 of a step. The other object becomes unbound. A pending word stays in the notify. The threads waiting to receive on a surviving endpoint are not woken: they wait for callers, as on any endpoint without a notify.
> - **A thread.** When the root capability of a thread is the next to remove, the kernel undoes, one unit each, in this order: its wait, if it waits (it leaves its queue; a reply object attached to it or armed with it becomes idle, as for `thread_cancel`); the lend whose receiver it is, if any ([The budget follows the call](#the-budget-follows-the-call)); then its bindings: message page (the frame capability's record is emptied), fault endpoint, address space, capability space, task, and home context (the context keeps its lends). At most 8 units. A step with fewer units left returns `again` and goes on at the next call. Then the root capability is removed.
> - **The rights of a kind.** "Every right" of a new object ([rules of `untyped_retype`](#capabilities-and-objects)) and "every right of its kind" (start-up) mean the eight rights of [Rights](#rights), for every kind, with three exceptions. A root made by `untyped_retype` has `exec` only by the rule of that call. A root made at start-up from no untyped has every right except `exec`; the start-up untypeds and the frames of the boot image keep the rights the [Start-up state](#start-up-state) gives them. A kept frame has `read` and `derive` only. So `cap_inspect` of a root returns 0xFF or 0xFB, and 0x41 for a kept frame.

> #### Kept frames
>
> (To add to [Frames](#frames).) A **kept frame** is a frame that the kernel makes at start-up over kept memory: the crash areas here, and, if the cores draft is merged, the living part of the machine table and the kept image. It is ordinary memory, write-back, with a page size of 2 MB for a crash area. Its root capability is at depth 1 in the start-up space and has `read` and `derive` only, so no mapping of it is writable or executable (`denied`, by the subset rule). It is never cleared. Removing its root destroys the frame object and gives the memory back to no one: the memory stays kept until the machine restarts.

> ### Values to add to `abi/` (debugging and I/O ports)
>
> - **Calls.** `IoportIn`, `IoportOut`, `IoportsIssue`, appended at the end of `Call`. If the cores and memory drafts are merged first (calls 48 to 55), they are 56, 57 and 58; otherwise 48, 49 and 50. `DebugWrite` and `TraceEmit` keep their place.
> - **Errors, object kinds.** None new. `IoPorts = 11` and `Debug = 15` become kinds that `untyped_retype` refuses with `Invalid`.
> - **Sizes.** `DEBUG_AREA_BYTES = 69_632`, `DEBUG_AREA_PAGES = 17`, `DEBUG_HEADER_BYTES = 64`, `NODE_CRASH_RECORD_BYTES = 4_032`, `CRASH_HEADER_BYTES = 4_096`, `CRASH_AREA_ALIGN = 2 << 20`, `TRACE_ENTRY_BYTES = 64`, `TRACE_KERNEL_ENTRIES = 256`, `TRACE_USER_ENTRIES = 768`, `TRACE_TEXT_BYTES = 24`, `DEBUG_WRITE_MAX = 512`, `TRACE_BURST = 16`, `TRACE_BURST_NS = 1_000_000`, `CONSOLE_STEP_BYTES = 16`, `CONSOLE_TICK_NS = 1_000_000`, `STUB_STOP_NS = 10_000_000`, `CRASH_RECORD_KERNEL_ENTRIES = 32`, `CRASH_RECORD_USER_ENTRIES = 16`.
> - **Types.** `TraceCode` (u16): `KernelText = 1`, `IommuFault = 2`, `Suppressed = 3`, `IommuTimeout = 4`, `FaultDropped = 5`, `NodeFailure = 6`, `HardwareError = 7`, `StrayInterrupt = 8`, `Membership = 9`, `UserText = 16`, `UserTrace = 17`; `TRACE_FLAG_CONTINUED = 1 << 0` (bit 16 of word 2). `TraceEntry` (`repr(C)`, 64 bytes: `seq`, `instant`, `word2`, `task`, `marks`, `payload: [u64; 3]`). `DebugAreaHeader` (64). `NodeCrashRecord` (4,032, the table above). `CrashAreaHeader` (200 used bytes of the 4,096). `CrashReason` (u32): `Assertion = 1`, `KernelException = 2`, `DoubleFault = 3`, `HardwareError = 4`, `Fenced = 5`, `IommuTimeout = 6`, `Containment = 7`, `StartRefused = 8`. `ConsoleKind` (u32): `None = 0`, `Uart16550Port = 1`, `Uart16550Mmio = 2`, `Pl011 = 3`, `SbiDbcn = 4`, `XhciDbc = 5`. `Build`: `Production = 0`, `Development = 1`. `IoPortRange(u64)` with `new(first, last)`, `first()`, `last()`, `contains(port, width)`.
> - **Start-up page.** Kind 8 `CrashRecord` now holds `StartCrash` (32 bytes): base, length, sequence (u64 each), slot of its kept frame, flags (bit 0 the stop record is valid, bit 1 at least one node record is valid) (u32 each). New kind `Debug` (the next free kind, 17 if the cores draft adds none): `StartDebug` (48 bytes): build (u32), console kind (u32), console address (u64: port, physical address, or segment, bus, device and function as in the source word of `irq_claim`), base and length of the current crash area (u64 each), slot of its kept frame (u32), bytes per debug area (u32), kernel entries, user entries, bytes per entry, reserved (u16 each).
> - **Module `x86_64`.** `KERNEL_PORTS: [(u16, u16); 2] = [(0x20, 0x21), (0xA0, 0xA1)]`; `UART_PORTS = 8`; `RESET_PORT = 0xCF9`, `RESET_WARM = 0x06`; `CRASH_DETAIL_WORDS = 32` with the index of each word.
> - **Pure functions with a Kani proof.** `IoPortRange::contains(port, width)` (true only if every port of the access lies in the range, for every input, with no overflow); `ioport_check(range, port, width, value)` (the order `invalid` of the plain arguments); `trace_index(seq, entries)` ((seq − 1) mod entries, never out of the ring); the issue check (an accepted range lies inside the source's).

---

## Part 2. Changes needed elsewhere in the contract

In `kernel-interface.md`:

1. **Rule 3.** Add to the exceptions fixed at start: "the two crash areas (the debug area of every node)". Add the `debug` and `ioports` objects to "the start-up objects, which are made from no untyped" (they already are, implicitly).
2. **Rule 7.** Add: "Calls that change no object state (`debug_write`, `trace_emit`, `ioport_in`, `ioport_out`) are executed by the caller's kernel, whichever kernel holds the object."
3. **Objects table.** `ioports`: "A range of x86-64 I/O ports, carried by the capability; the kernel executes each access. One per node, made at start (architecture layer only)". `debug`: "The authority to write into the user trace ring of one's node. One per node, made at start. The rings and the crash records are kept memory, read through kept frames".
4. **System calls.** "48 calls" becomes 51, or 59 with the cores and memory drafts. "except those of the groups not yet specified (cores, debugging)" loses "debugging". The Debug row keeps its note and gains: "the stub exists only in development images". A row "I/O ports (x86-64): `ioport_in`, `ioport_out`, `ioports_issue`".
5. **Call reference, status paragraph (line 71).** "Groups still not specified: cores, debugging, `ioports`" loses debugging and `ioports`.
6. **The derivation tree, first bullet.** "the frames of the start-up state are the exception, as descendants of the image untyped" becomes "...except the kept frames, which are roots at depth 1".
7. **Order of checks, step 3.** The kinds "that this version does not make (`ioports`, `core`, `debug` and the reserved `vcpu`)" become "(the reserved `vcpu`)"; the kinds "never made from an untyped" gain `ioports` and `debug` (and `core`, `role`, `memory_control` per the cores draft). Add before the numbered list: "On an architecture without I/O ports, `ioport_in`, `ioport_out` and `ioports_issue` return `unsupported` before any argument is looked at."
8. **`cap_derive` row.** Add: "On an `ioports` capability the new capability keeps the source's range." **`cap_inspect` row:** "the badge, or for an `ioports` capability its range".
9. **`untyped_retype` row.** "An `irq`, an `irq_control` or an `iommu` is never made by this call" gains `debug` and `ioports`.
10. **Frames.** Add the bullet on kept frames (Part 1).
11. **IOMMU.** "Devices the kernel uses itself (the USB debug port, if the kernel drives it)" becomes "(the xHCI function whose debug capability is the console of a development image)". "The kernel clears the fault record and writes it to the trace buffer" becomes "...writes it to the kernel ring of the node that drives the unit (code 2), with the rate limit of [Debugging](#debugging-call-reference)".
12. **Register calls.** "The kernel's debugger stub reads the vector state for kernel debugging" becomes "The debugger stub of a development image reads...".
13. **Faults.** After the table of kinds, add: "The kernel never enables hardware breakpoints for a user thread: a fault of kind debug comes from a breakpoint instruction or a single step." And under "No handler": "the kernel writes an entry of code 5 in its kernel ring".
14. **Rights table.** `read`, `write`: add "execute an `in` or an `out` (`ioports`); write into the trace (`debug`)". `derive`: add "narrow a range of ports (`ioports_issue`)".
15. **Object sizes.** Add rows: "`debug`, `ioports`: no memory (made at start, not from an untyped)"; "kept frame: kept memory, made at start".
16. **Start-up state.**
    - "What the loader hands over": "the crash record of the previous boot, if there is one" becomes "the base and length of the current and previous crash areas, and the previous sequence; the console record of the boot image".
    - "The kernel refuses to start, with a message on the serial console, if" becomes "...with a message on the console, if the boot image names one, and a stop record of reason 8, if". The list gains "the boot image asks a production kernel for a development option".
    - Memory rule 1 (Kept): add "the two crash areas".
    - Slots table: row 5 "`debug` of this node"; row 7 "`ioports` (x86-64; empty on other architectures), range [0, 65,535]; the kernel ports are refused at each access". Row "16 onwards" ends with: "...then one frame per module, in module order; then the kept frame of the current crash area; then the kept frame of the previous crash area, if there is one". The number of slots counts these one or two.
    - Depth and rights: "Every start-up capability except the frames is the root..." becomes "...except the frames of the boot image...; kept frames are roots at depth 1 with `read` and `derive`".
    - Start-up page: entry 8 "The bytes of the record; its format is the debugging group's" becomes "`StartCrash`"; new entry `Debug`.
17. **Debugging (Decided).** Item 2 becomes "a remote debugger stub in the kernel (gdb protocol), in development images only"; item 3 "a trace ring per node, readable after a panic and after a restart"; item 4 "a crash record written in memory, in the crash area, which the next boot hands over; the storage service copies it to the reserved area". Add a link to the call reference subsection.
18. **Points for the two owners.** Add the rows of Part 4.
19. **Open points.** As in Part 3.

In other files:

20. **kernel.md**, Recovery, further rules: "A trace is written to a reserved area (see storage.md), then the machine restarts" becomes "The stop record is written to the crash area in memory, the machine restarts by a warm reset, and the next boot hands the record over; the storage service writes it to the reserved area".
21. **platform.md**, Observability: "a kernel debugger through the USB debug port" becomes "a kernel debugger stub in development images, over a serial port or the USB debug port". Crash and shutdown, "Hang": "A hardware watchdog armed by the kernel" becomes "armed by the platform service and fed by the service manager" (see gap 12 in Part 3).
22. **security.md**, Permissions, Debugging: add "The kernel has no object for it: the supervisor hands the debugger the component's thread capabilities and forwards its faults. The kernel debugger stub exists only in development images, which only a developer key signs."
23. **storage.md**, Partitions: "a small raw region for the crash trace" gains "written by the storage service from the previous crash area that the start-up state hands over".
24. **D-058** keeps its meaning (the USB debug port is supported) but the transport of the reference desktop is a point for the owners (Part 4).
25. **Cores draft.** Add a unit role `console` (the node that drives the console device), with the hand-over rules of the other unit roles; add the kept frames of the crash areas to the list "16 onwards" of every node's start-up space; its NMI handler writes the node record with reason 5 and does not overwrite a committed record of the same generation (its "writes what it can of a crash record" becomes this rule). Nothing in it is contradicted.
26. **`abi/`**: `ObjectKind` comments for `IoPorts` and `Debug`; `start.rs` gains `StartCrash`, `StartDebug`, the new `StartKind`.

---

## Part 3. The other gaps, and the open points

### 3.1 Inventory: calls and objects whose behaviour no section fixes

Read with one question: is there a call named in "System calls" or an object named in "Objects" whose behaviour no section fixes?

| # | Call or object | What is missing | Size | Done here |
|---|---|---|---|---|
| 1 | `debug_write`, `trace_emit`, `debug` | Everything | Group | Specified (Part 1) |
| 2 | `ioports` | Everything | Group | Specified (Part 1) |
| 3 | `core_start`, `core_stop`, `core_status`, `core` | Everything | Group | The cores draft; not repeated |
| 4 | The call that gives a kernel its idle table ([Idle](#idle)) | It has no name in "System calls" | Small | The cores draft's `core_idle` |
| 5 | `notify_bind` and destruction | Neither the destruction of a bound endpoint nor of a bound notify says what happens to the binding | Small | Specified (Destruction, Part 1) |
| 6 | `thread` destruction | Its links are undone in pieces spread over five sections; no order and no count of units | Small | Specified (Destruction, Part 1) |
| 7 | Rights of a kind | "every right" and "every right of its kind" are not defined per kind, yet `cap_inspect` returns them | Small | Specified (Part 1): all eight, `exec` by rule |
| 8 | `cap_inspect` on a frame from no untyped, on `ioports` | Not covered | Small | Specified (kept frames; range) |
| 9 | `untyped_retype` with kinds `debug`, `ioports`, `core` | `unsupported` "in this version", which says nothing of a later one | Small | `invalid` for good (Part 2, item 7) |
| 10 | Start-up entry 8 `CrashRecord` | "its format is the debugging group's" | Small | `StartCrash` |
| 11 | The console of "refuses to start, with a message on the serial console" | No console is defined | Small | The console (Part 1) |
| 12 | `#DB` in the fault table | Word 4 holds DR6, but nothing says whether a user thread can have hardware breakpoints | Small | No (Part 1) |
| 13 | IOMMU interrupt-remapping faults | DMA faults go "to the trace buffer"; a refused interrupt is not mentioned | Small | Code 2, bit 57 |
| 14 | Calls on another node's `debug` or `ioports` | Rule 7 would make every trace entry a message | Small | Executed by the caller's kernel (rule 7 amended) |
| 15 | `vcpu` | Specified as reserved; nothing missing | — | — |
| 16 | `call`/`send` toward a `core` mailbox, `role` | The cores draft introduces them | — | Not mine |

Gaps outside that question, found on the way (each touches a decision, so the rule is recommended and listed for the owners):

| # | Where | What is missing | Recommended |
|---|---|---|---|
| 17 | Entropy (D-057; arrival step 4 of [Interrupts](#interrupts)) | The kernel pool is fed by interrupts, and D-057 says also by the TPM, but no call feeds it or reads it; its only consumers are the start-up seeds (`EntropySeed`) and the boot identifier. The TPM has a driver in user space, so its entropy cannot reach the kernel | Keep the pool for the seeds of nodes started fresh (each fresh start draws a new seed), and add one call `entropy_mix(word 0..word 3)` with no capability, like `yield`: mixing input into a hash can only add entropy (from memory: the construction of Linux's pool). Or amend D-057: the TPM feeds the user-space entropy service. For the owners |
| 18 | Hardware watchdog ([platform.md](platform.md#crash-and-shutdown): "armed by the kernel") | The kernel reads only MADT and DMAR (D-112); the watchdog (the chipset's TCO timer, the ACPI WDAT table) is described elsewhere. No call arms or feeds it | The platform service arms it and the service manager feeds it; node hangs are the cores group's (heartbeats). A whole-machine hang then resets the machine through the watchdog. Amend platform.md |
| 19 | Who reads the kernel-traced events in production | Nothing says that the log service reads the rings | The first service gives the kept frame of the current crash area to the log service; a rule for platform.md, not the contract |

### 3.2 Open points, line by line

| Open point | Can it be closed now? | How |
|---|---|---|
| The depth rule and a machine that does not die | Yes, with the cores draft | Its part 1.3.2 answers it: every node's start-up space is a root for that node's resources and holds roots of the machine objects; reserve roles carry the supervisor's memory. Close when that draft is merged. D-116 (1) (a core that cannot be stopped from outside) is a separate point and stays open in the cores draft |
| Numbers are defined in `abi/` | Yes | It is a standing rule, not an open point: move it to [Registers](#registers) ("values are in `abi/`, which this document names") and delete the line |
| The groups not yet specified | Yes | Closed by the cores draft and this draft once merged. Delete the line |
| Left to the multi-core part: untyped of a remote copy's tables | Rule now, protocol later | Recommended rule: each copy of an address space is paid by an untyped of the node that holds it, supplied by the call that adds a node to a core group; no object then depends on memory of two nodes (the rule "no object depends on two untypeds" applied per node). What stays missing is that call, part of the protocol of core groups |
| … what a passive receiver does with a call delivered by another kernel | Yes | Adopt the recommendation already written (delivered, receiver marked as having lost its context), and delete the line |
| … how parked nodes keep the guarantees of admission | Yes, with the cores draft | `core_place` refuses with `budget` when the sum of the nodes a core would run exceeds one core, and parked nodes run by deadlines (cores draft, 2.11) |
| … the protocols that move a context and a node | Half | A node: `core_place` (cores draft). A context and its thread between kernels: still missing. What it needs from the contract is written ([One kernel per core](#one-kernel-per-core)); missing are the messages, the state of the thread while it moves, and what a call made during the move returns |
| Message words in registers once APX is available | Yes | Make the number of register words a value of the code page, as call numbers are (rule 6), published in the start-up page; `Header::is_fast` uses the published value. The x86-64 code page keeps 6 until APX hardware exists to measure; nothing in the contract changes when it grows |
| The step bound (32), segment (128 slots), clearing step (64 KB) | No | They are measured on the kernel; they are values in `abi/`, not gaps. Merge with "the numbers of this draft" |
| The cost of a fault handled by the memory service | No | A gate ([gates](../plan/gates.md#overhead-gates)), already written there; move the line to the gates |
| Copy on write in version 1 or with snapshots | Yes, here | Not a kernel question: the kernel already offers what copy on write needs (`aspace_protect`, derived frame capabilities). Move the line to memory.md |
| The spread of sticky marks | No | Measured on the injection attack suite; it is a gate, move it there |
| The numbers of this draft | No | Measured after the one-core model; one line with the step bound |
| User interrupts as a second wake-up path | Decision needed | By the rule "no deferral in the kernel", either the hook is placed now or the feature is dropped. Intel's user interrupts appeared on server processors and are not offered by the client cores of the reference desktop (from memory), so nothing can be measured on it. Recommended: no user interrupts in version 1, and kernel.md's "retained, to be designed" becomes "not in version 1". The alternative hook: one word in `notify` (it has room in 64 bytes) naming a target thread and a vector, and the call number reserved. For the owners |

### 3.3 Checked against ARM64 and RISC-V

| Element | x86-64 | ARM64 | RISC-V | Same, or fixed by the architecture layer |
|---|---|---|---|---|
| Debug areas, rings, entries, codes, rate limit | — | — | — | Same |
| Crash record envelope | 32 detail words: registers, MCA bank | ESR, FAR, ELR, SPSR, registers, RAS error record | `scause`, `stval`, `sepc`, `sstatus`, registers | Envelope the same; detail words by the layer |
| Handover across a restart | UEFI variable, warm reset by port 0xCF9 | UEFI where present; PSCI `SYSTEM_RESET2` warm (from memory) | UEFI where present; SBI `SRST` warm reboot (from memory) | Rule the same; reset method by the layer. Without a UEFI variable store, no previous area |
| Console device | 16550 on ports or in memory; DbC in development | PL011 or 16550 in memory | SBI DBCN (verified) or 16550 in memory | Kinds listed in `ConsoleKind`; each layer accepts its own |
| IOMMU fault records | VT-d fault recording registers | SMMUv3 event queue | RISC-V IOMMU fault queue | Code 2 the same; the reason code is the layer's |
| Hardware errors (code 7) | Machine check banks | RAS extension, SError | No standard record (from memory) | Layer |
| Stub: stop signal | NMI | SDEI or pseudo-NMI | IPI (cooperative), or a firmware extension | Same handlers as the fence of the cores draft |
| Stub: hardware breakpoints | DR0-DR7 | Breakpoint and watchpoint registers | Sdtrig, if firmware gives it to S-mode | Layer |
| User single step | TF in rflags | Step bit in the flags word, kernel sets MDSCR_EL1.SS | None | Layer |
| `ioports` | Object and three calls | None, `unsupported`; PCI I/O is a memory window | Same as ARM64 | The only object of one architecture |

---

## Part 4. For the humans

| Point | Rule written (recommended) | Alternatives | What each costs |
|---|---|---|---|
| Where the crash record survives a restart | In memory, in two crash areas the loader keeps at addresses stored in one UEFI variable; warm reset | A: a polled disk writer in the kernel. B: a crash kernel per node (kdump). C: UEFI variables written at failure time | Rule: lost if the firmware clears memory at reset or has no variable store; to test on the reference desktop and the Dell. A: a storage driver in the trusted base and a disk path in the failure path. B: a reserved image per node and a second boot path to verify. C: firmware runtime services called from a failing core |
| The stub's transport on the reference desktop (D-058) | A 16550 (board header or PCIe card) by default; the xHCI debug capability as an option | The xHCI debug capability only, as D-058 says | Rule: a cable or a card of a few euros. Alternative: the development image loses every USB port of that controller, probably all of them on a desktop with one controller (from memory: the debug capability shares the controller's PCI function and IOMMU context) |
| Port I/O executed by the kernel | One system call per access; no bitmap | A: the I/O bitmap per thread (Linux). B: per address space (Zircon) | Rule: under a microsecond more per access, on devices that take a microsecond. A: 8 KB per thread that uses ports, a copy at switch. B: 8 KB per space, a TSS write at switch, a message to every core of a group on change |
| No exclusive port ranges | The platform service decides; the kernel does not check overlap | A bitmap of issued ports, as seL4 | Rule: two drivers given the same port by mistake can both use it. Alternative: an 8 KB table shared by every node, so a protocol between kernels for a debugging aid |
| Console in a production image | Allowed, output only, if the boot image names a device (servers) | Never in production | Rule: a server can be watched over a serial line. Alternative: a server's console is only the log service's |
| Size of the trace | 16 KB kernel ring and 48 KB user ring per node, two areas | Larger rings, or a size chosen by the boot image | Rule: 136 KB per node kept for the whole boot; about 256 kernel events and 768 user entries per node before overwrite. Larger: more kept memory, more history |
| The development stop of every core | A release word shared by every node, in development images only | No stop: the stub sees one node at a time | Rule: the development kernel differs from the production kernel in this path. Alternative: a multi-core bug cannot be examined in one consistent state |
| Hardware breakpoints for user debuggers | Not given; breakpoint instructions and single step | Debug registers in the register block | Rule: no watchpoints on data in user debuggers. Alternative: per-thread state at every switch and an architecture-dependent format in the contract |
| Entropy and the TPM (D-057) | Add `entropy_mix`, with no capability | Amend D-057: the TPM feeds the user-space entropy service only | Rule: one more call, with no right needed. Alternative: the kernel pool only seeds new nodes, from the processor and interrupts |
| User interrupts | Not in version 1 | Place a hook now (a word in `notify`, a call number) | Rule: kernel.md's "retained" is withdrawn. Hook: 8 bytes of each `notify` and a call that no hardware of the project runs yet |
| The watchdog | Armed by the platform service, fed by the service manager | Armed by the kernel (platform.md today) | Rule: a hang of the service manager resets the machine too. Alternative: the kernel reads the tables of the watchdog, a second exception to D-054 |

---

## Part 5. What a reference model of this group must cover

**States.** Per node: the two rings (entries, next sequences), the suppressed counters and rate windows per code, the node record (commit, content). Per machine: the crash area header with its boot identifier and stop record, the previous area read-only. Per capability of kind `ioports`: its range. The set of kernel ports. The architecture flag "has I/O ports". For the destruction rules: endpoint–notify bindings, a thread's links.

**Invariants worth checking.**

1. For every ring, the next sequence is one more than the greatest sequence written, and the entry with sequence *s* is at index (*s* − 1) mod *N*; word 0 of a visible entry is its sequence or 0.
2. The user ring holds only codes 16 and 17; the kernel ring never holds them. No sequence of calls on `debug` changes the kernel ring.
3. `debug_write` of length *L* > 0 writes exactly ⌈*L* / 24⌉ consecutive entries, all but the last *continued*, carrying the caller's task identifier and effective marks at the time of the call; length 0 writes nothing.
4. In any window of 1 ms, at most 16 kernel entries of one code other than 6 are written; every suppressed entry is counted once, and reported by exactly one code-3 entry before the next allowed entry of its code.
5. A node record is accepted only if its commit equals the boot identifier of its area; the fence handler never overwrites a committed record of the same generation.
6. The previous crash area is never written during the boot.
7. Every `ioports` capability's range lies inside its parent's; the root's range is [0, 65,535]; `cap_derive` never changes a range.
8. No `ioport_in` or `ioport_out` that touches a kernel port succeeds; every one that succeeds lies inside its capability's range.
9. On an architecture without I/O ports, the three port calls return `unsupported` whatever the arguments, after the checks that precede every call.
10. When a bound endpoint or notify is destroyed, the survivor is unbound and its waiters are untouched; a pending word stays.
11. Destroying a thread undoes at most 8 links, in the stated order, one unit each, across steps that return `again`; afterwards no object names it.
12. A start-up root has rights 0xFB; a kept frame 0x41; a root made by `untyped_retype` 0xFF or 0xFB.

**Orders of checks to test exhaustively.** `debug_write` (slot, kind, `write`, length, message page); `ioport_in`/`ioport_out` (architecture, slot, kind, right, width, range, value, kernel port); `ioports_issue` (architecture, source, destination, first ≤ last, inside, depth, `no_slot`).

**Outside the model** (hardware, tested on QEMU and the machines): console output and pacing, IOMMU fault reading, the warm reset and the handover of the previous area, the stub and the stop of every core.

---

## Part 6. Sources

Verified today:

- seL4 API reference: IO ports (`seL4_X86_IOPortControl_Issue`, `seL4_X86_IOPort_In8` …), debug calls in `DEBUG_BUILD`/`PRINTING` builds, benchmark log buffer as a user-supplied large frame: https://docs.sel4.systems/projects/sel4/api-doc.html
- seL4 kernel source, the kernel executes `in8` after `ensurePortOperationAllowed`, and refuses to issue a port twice (`isIOPortRangeFree`): https://raw.githubusercontent.com/seL4/seL4/master/src/arch/x86/object/ioport.c
- Zircon `zx_ioports_request` (resource of kind `ZX_RSRC_KIND_IOPORT`): https://fuchsia.dev/reference/syscalls/ioports_request
- Zircon I/O bitmap per address space, applied to the core's TSS by ranges at switch: https://fuchsia.googlesource.com/zircon/+/jj_test/kernel/arch/x86/ioport.cpp (and the search result https://fuchsia.googlesource.com/fuchsia/+/main/zircon/kernel/arch/x86/ioport.cc, not readable today)
- Zircon `zx_debuglog_create` (system resource, debuglog base): https://fuchsia.dev/reference/syscalls/debuglog_create ; `zx_ktrace_read` (tracing resource, debugging system calls enabled at boot): https://fuchsia.dev/reference/syscalls/ktrace_read
- x86 `IN`: the I/O permission bitmap is checked when CPL > IOPL, #GP if a bit is set, ports 0 to 65,535: https://www.felixcloutier.com/x86/in
- Linux, I/O bitmap per thread (from the LKML thread, not read in full): https://lkml.iu.edu/hypermail/linux/kernel/1911.0/06929.html
- Linux, xHCI debug capability (USB 3 debug port), xHCI spec section 7.6, early printk and `/dev/ttyDBC0`: https://docs.kernel.org/driver-api/usb/usb3-debug-port.html
- gdb remote protocol, packet framing and minimum commands: https://sourceware.org/gdb/current/onlinedocs/gdb.html/Overview.html
- Linux ramoops, records in persistent RAM across a restart: https://docs.kernel.org/admin-guide/ramoops.html
- Linux, `PCI_IOBASE` on arm64 and riscv (port I/O through a memory window): https://raw.githubusercontent.com/torvalds/linux/master/arch/arm64/include/asm/io.h ; https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/include/asm/io.h
- RISC-V SBI debug console extension (DBCN, SBI 2.0): https://docs.riscv.org/reference/sbi/ext-debug-console.html

From memory (not checked): port 0xCF9 and the value 0x06 for a warm reset of Intel chipsets; the cost of a legacy port access (about a microsecond); that the xHCI debug capability shares the controller's requester ID; that servers may clear memory at reset; Linux kdump; the hash-based mixing of Linux's entropy pool; PSCI `SYSTEM_RESET2` and SBI `SRST` warm reboot; Sdtrig availability to S-mode; Intel user interrupts absent from the client cores of the reference desktop; ChromeOS's use of ramoops on x86 across a warm reboot.
