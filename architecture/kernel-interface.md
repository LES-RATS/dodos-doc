# Kernel interface

Statuses are defined in the [README](../README.md#status-legend).

**Proposed, 14 November 2026. First draft.** This file is the contract of the kernel: its objects, its system calls and the rules that bind them. It is written before any kernel code (**Decided**, 14 November 2026). The executable model, the oracle harness and the kernel are all written from it. Names and counts are provisional; the trials of weeks 1-2 and the one-core model will change them.

The kernel knows nothing about Wasm, WIT or components. The runtime and the services build those on top of this interface.

## Rules

1. **Everything is a capability.** A system call names its target by a slot in the caller's capability space. There is no global name and no ambient right.
2. **Any call can fail with `gone`.** A capability is revocable at any time (rule 1 of the [ABI](wasm-abi.md#abi-rules)).
3. **No kernel heap.** The memory of every object comes from an untyped capability supplied by the creator (see [memory.md](memory.md#kernel-memory)).
4. **Every call is bounded.** A long operation (revocation, deletion of a large object) runs in bounded steps and returns `again`; the caller repeats the call.
5. **A call never blocks the kernel.** The kernel has no per-thread stack. A thread that waits is a state of the thread, and the kernel returns to its scheduler.
6. **Calls enter through the kernel-supplied code page.** Call numbers are private to that page and can change between kernel versions.
7. **Objects belong to one core's kernel.** A call on an object held by another kernel becomes a message between kernels. The caller sees the same result, later.
8. **Data never crosses IPC.** IPC carries control. Data moves through shared memory objects (see [Data plane](#data-plane)).

## Objects

| Object | Role | Model |
|---|---|---|
| `untyped` | A range of physical memory, not yet typed. The only source of memory for other objects | seL4 |
| `cspace` | A table of capability slots. Flat, and grown by supplying memory. Deliberately simpler than the guarded tables of seL4 | To design |
| `aspace` | An address space: page tables, built from supplied memory. One copy per core in the core group | seL4, CortenMM |
| `memobj` | A set of pages that can be mapped, shared and copied on write. May be backed by a pager | Fuchsia VMO |
| `thread` | A register set, bound to a `cspace`, an `aspace` and a fault endpoint | seL4 |
| `sched` | A scheduling context: budget, period, deadline, core class, allowed cores | seL4 MCS |
| `endpoint` | A synchronous rendezvous point for call and reply. A derived capability carries a badge that identifies the caller | seL4 |
| `reply` | A one-shot right to answer one call. It returns the caller's budget | seL4 MCS |
| `notify` | A word of signal bits, asynchronous. Interrupts, timers and ring wake-ups arrive here | seL4 |
| `timer` | A deadline with a tolerance, which signals a `notify` | Project |
| `irq` | The right to receive one interrupt line or vector | seL4 |
| `ioports` | A range of x86 I/O ports (architecture layer only) | seL4 |
| `iospace` | An IOMMU domain: what a device can reach by DMA | seL4, Fuchsia BTI |
| `task` | An agent task: delegated rights, time budget, provenance marks, log. Revocable in one operation ([research axis 4](../research/prior-art.md#kernel-research-axes)) | Project |
| `core` | Control of one core's kernel: start, stop, replace, recover, status | Barrelfish/DC |
| `debug` | Console, trace buffer, crash record | Project |
| `vcpu` | Reserved name, not built. It exists only if the [micro-VM fallback](drivers.md#drivers-in-micro-vms-fallback) is opened | — |

Device memory (MMIO) is an `untyped` marked as device memory; it can only become a `memobj` that is mapped, never a kernel object.

## System calls

About 40 calls. All take capability slots and words in registers.

| Group | Calls | Notes |
|---|---|---|
| Capabilities | `cap_derive`, `cap_move`, `cap_delete`, `cap_revoke`, `cap_inspect` | `cap_derive` copies with fewer rights or with a badge. `cap_revoke` deletes everything derived from a capability; it is the distributed two-phase protocol between kernels, and it returns `again` |
| Memory | `untyped_retype`, `memobj_clone`, `memobj_supply`, `memobj_evict`, `aspace_map`, `aspace_unmap`, `aspace_protect` | `memobj_supply` and `memobj_evict` are the pager's calls. `aspace_map` accepts a range and a page size, so one call maps a large block |
| IPC | `call`, `reply_recv`, `recv`, `send`, `signal`, `wait`, `poll` | `call` and `reply_recv` are the fast path. `send` never blocks. `wait` waits on a `notify`, or on an endpoint with a bound `notify` |
| Threads | `thread_configure`, `thread_read_regs`, `thread_write_regs`, `thread_resume`, `thread_suspend`, `yield` | |
| Scheduling | `sched_configure`, `sched_bind`, `sched_unbind`, `sched_set_cores` | Admission control is in `sched_configure`. `sched_set_cores` is reserved to the placement service |
| Time | `timer_set`, `timer_cancel` | The monotonic clock is read from a shared page, without a call |
| Interrupts and devices | `irq_bind`, `irq_ack`, `iospace_map`, `iospace_unmap`, `iospace_attach` | |
| Tasks | `task_create`, `task_attach`, `task_mark`, `task_revoke`, `task_read` | See [Tasks and provenance](#tasks-and-provenance) |
| Cores | `core_start`, `core_stop`, `core_status` | Replacement and recovery are `core_stop` followed by `core_start` with a kernel image |
| Debug | `debug_write`, `trace_emit` | Present in every build; the capability decides who may call them |

Faults are not calls. A page fault, an illegal instruction or a budget overrun becomes a message on the thread's fault endpoint; the handler answers through the `reply` object.

## Synchronous or asynchronous

**Proposed; each line is to be measured** (request of the user, 14 November 2026).

| Path | Form | Reason | Cost to watch |
|---|---|---|---|
| IPC on the same core | Synchronous: `call` switches directly to the server thread, which runs on the caller's budget | No queue, no scheduler pass, no wake-up. This is the path of the gate "under 1.2 times seL4" | A slow server holds its caller |
| IPC to another core | Asynchronous inside the kernel: a message between kernels, and the caller thread waits | Kernels share no state | Two inter-kernel messages and an interrupt. The placement service avoids it: a service has a thread on the caller's core, or the caller moves |
| Notification | Asynchronous: bits are set, with no payload | Interrupts, timers and wake-ups must never wait for a receiver | Bits merge, so a notification says "look", not "how many" |
| Fault | Synchronous message to the handler | The faulting thread cannot continue anyway | One IPC round trip per fault; see [Pager](#pager) |
| Data plane | No kernel entry on the common path | Rings in shared memory | A `signal` only when a ring goes from empty to non-empty |
| Long operation (revocation, teardown) | Bounded steps with `again` | A bounded kernel cannot loop | The caller's latency. Other threads are not delayed |
| Call between components (WIT, WASI 0.3) | Asynchronous in its type, synchronous in its execution when the callee finishes without waiting | Short calls must cost a plain IPC | The measured overhead of the asynchronous form (3.5 times, see [gates](../plan/gates.md#overhead-gates)) must apply only to calls that really wait |

What is measured, in the trials of weeks 1-2 and then at each merge:

- round trip of `call` on one core, against seL4 MCS;
- round trip of a call between two cores;
- latency from `signal` to the wake-up of the waiting thread;
- a short WIT call in its synchronous execution against its asynchronous execution;
- throughput and tail latency of a ring, with and without wake-ups.

A blocking system call (wait in the kernel with a kernel stack) is rejected: it contradicts rule 5 and hot replacement.

## Data plane

**Decided, 14 November 2026.** Data never crosses IPC. Disk blocks, network packets, audio frames and display buffers move through single-producer single-consumer rings in shared `memobj` objects (model of sDDF; see [drivers.md](drivers.md#driver-framework)). IPC sets the rings up, and a `notify` wakes a side that sleeps.

A gate counts the kernel entries per unit of work: per displayed frame, per disk read, per network packet (see [gates](../plan/gates.md#overhead-gates)).

## Pager

**Decided, 14 November 2026.** Paging stays in user space (see [memory.md](memory.md#paging-in-user-space)), with two rules that keep its cost bounded:

- **Read-ahead.** A fault is answered with a run of pages, not with one page. The pager chooses the run; `memobj_supply` accepts a range.
- **Large mappings.** A blob that is mapped whole (compiled code, model weights) is supplied in one call, in 2 MB pages where its size allows.

A gate is added: faults per megabyte read on a cold sequential read.

## Tasks and provenance

**Proposed.** The task is the project's own kernel object.

- `task_create` makes a task from a time budget and a set of marks (private, untrusted; see [agent.md](agent.md)).
- `task_attach` places a capability or a thread under a task. Everything derived from it stays under the task.
- The kernel stamps every IPC message with the sender's task marks. The receiver reads them; it cannot forge them. This is [research axis 1](../research/prior-art.md#kernel-research-axes).
- `task_mark` only adds marks. A task that has read untrusted data stays marked.
- `task_revoke` removes every right of the task in one operation. It is `cap_revoke` on the root of the task, so it uses the same distributed protocol.

Open: where marks are stored for a thread that serves several tasks in turn (a service). The first answer: the marks follow the call, like the budget.

## Power states

**Decided, 14 November 2026.** Sleep is part of the interface from the first version, not an addition.

- The kernel offers per-core idle and stop (`core_stop`), and a whole-machine suspend entered by the power service once every driver has answered.
- Every driver class interface carries `suspend` and `resume`, and a driver declares the device states it supports. A driver that does not resume is restarted (see [drivers.md](drivers.md#restart-of-a-driver)).

## Debugging

**Decided, 14 November 2026.** Debugging comes before features. In order, at the very start of the kernel track:

1. serial console, on QEMU and on the reference desktop;
2. a remote debugger stub in the kernel (gdb protocol);
3. a trace buffer per core, readable after a panic;
4. a crash record written to the reserved area (see [storage.md](storage.md#partitions)).

A small native shell and a few tools (list capabilities, read memory, start and stop a thread, read traces) are ported as soon as the kernel starts a first process. They are native programs, outside the Wasm runtime, and they stay in the rescue image.

Agents drive the same tools: QEMU's console and monitor and the debugger stub are all text. A trial in weeks 1-2 checks that an agent can boot a kernel, read its console and set a breakpoint without help.

## Language split

**Estimate, to be replaced by a count after the trials.** For x86-64, about 30 % of the kernel's lines in Zig and 70 % in Rust.

| Zig | Rust |
|---|---|
| Boot and platform bring-up; entry and exit; context switch and vector state; page-table primitives and TLB; interrupt controller and timers; the IPC fast path; the rings between kernels; the low part of the debugger stub | Capabilities and the derivation tree; revocation; object life cycle; scheduling policy and admission; memory objects; the IPC slow path; the inter-kernel protocol; tasks and marks; recovery logic |

The Zig part is the architecture layer plus the fast path, so it is rewritten for each new architecture; the Rust part is not. The fast path is checked by the equivalence test against the Rust slow path (see [verification.md](../plan/verification.md#kernel-verification)).

## Open points

- The exact message format: number of register words, and how capabilities are transferred in a message.
- The `cspace` layout, and whether a slot number is stable across a suspend.
- Whether `memobj_clone` (copy on write) is in version 1 or follows the snapshot work.
- User interrupts as a second wake-up path (see [kernel.md](kernel.md#hardware-features)).
- Marks for a thread that serves several tasks.
