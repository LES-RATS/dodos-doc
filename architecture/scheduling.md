# Scheduling

Statuses are defined in the [README](../README.md#status-legend). Unless a line says otherwise, this file is **Proposed**; the lines marked Decided come from the decisions of 14 November 2026.

The mechanism is in the kernel and the policy is in user space.

## Mechanism in each node's kernel

- Each physical core of a node has its own queues; a node of several cores shares its objects under locks (D-128, D-129, [A node of several cores](kernel-interface.md#a-node-of-several-cores)).
- A thread runs only if it holds a **scheduling context**: a kernel object designated by a capability, which carries a budget, a period, a deadline, a slack class and the set of cores where it may be placed (model of seL4 MCS). Which kind of core a context goes to is the placement service's choice, expressed by that set ([Unlike cores](kernel-interface.md#unlike-cores)).
- The kernel picks the nearest deadline among the contexts that still have budget, and gives the time that none of them wants to throttled contexts, by class (D-110, see [What runs next](kernel-interface.md#what-runs-next)).
- The kernel moves a thread only within the set of cores that the placement service has authorised for it (**Decided**, 14 November 2026).
- Budgets are counted in time (**Decided**, 14 November 2026).
- **Admission.** Every configured context is admitted on its core: the sum of the bandwidths (budget over period) of the contexts of a core stays at most one whole core (D-110, proposed, see [Scheduling contexts](kernel-interface.md#scheduling-contexts)). How much of a core the frame class may take is a rule of the placement service.
- **Idle.** A core with no context is put to rest by its kernel.

## Clock

There is no periodic tick, and the clock does not count time spent with the machine suspended (D-110, see [Clock](kernel-interface.md#clock)). The screen is not the kernel's clock: the period is an attribute of each context, and the compositor aligns its own period on the screen (**Decided**, 14 November 2026). Wake-ups are driven by a deadline timer.

- **Wake-ups.** Each timer declares a tolerance; the kernel groups wake-ups within that tolerance to let cores sleep.
- **Rest.** Without a tick, the next wake-up of each core is known exactly, so the deepest compatible idle state is chosen without guessing.

The kernel's only clock is monotonic; wall-clock time is a service (see [platform.md](platform.md#time)).

## The budget follows the call

**Decided, 14 November 2026.**

- By default, when a client calls a service, the service runs on the client's budget. A service then has no time of its own, so it can neither steal time nor be starved, and the cost of an agent task is counted end to end.
- An asynchronous call carries a slice of the client's budget.
- Audio, drivers and the background work of storage have their own scheduling context.
- An emulated Linux driver cannot be cancelled: an overrun is charged to the client over its following periods.

## Classes

| Class | Work | Cores |
|---|---|---|
| Frame | Input, compositor, audio | Fast cores, with a guaranteed reserve. In performance preference (Decided, 14 November 2026) |
| Interactive | Interactive work | |
| Background | Compilation, indexing, long inference | Efficiency cores, preempted at every period |

- **Who gets which class.** The frame class is a capability. The shell hands it to the foreground surface and to the services on its path (input, compositor, audio), and takes it back when the surface goes behind. An application cannot give it to itself.
- **Background work.** A fair share between tasks, weighted by the user or by the agent; a guaranteed minimum share prevents starvation.
- **Agent inference.** Interactive class while the agent answers the user, background class otherwise; its GPU batches can be preempted at every frame.
- **GPU.** The GPU service applies the same classes to submissions, in the same deadline graph (see [gpu.md](gpu.md#gpu-scheduling)).
- **Input and output queues** (**Decided**, 14 November 2026). The classes apply to the disk and network queues; budgets for them come later.
- **Core class in the contract** (**Aligned**: retained). The core class is part of the contract of a scheduling capability: the frame path on fast cores, background work on efficiency cores. The promise is made by the placement service, through the cores set of the contexts it configures; the kernel holds no core class, and describes each core by numbers, not a class (D-115).
- **Starting values, to calibrate.** Period of the frame class equal to that of the screen (8.3 ms at 120 Hz); reserve of the frame class capped at half of each fast core; background slice of 10 ms.

## Background execution

**Decided, 14 November 2026.** Running in the background is a capability declared in the manifest. Without a surface, a program is in the background class, with a budget. It is woken by a notification service. Audio playback keeps its class.

## Placement service

The placement service runs in user space.

- It decides which context goes on which core, and requests migrations by messages. It knows the core types, the load, the temperature and the energy. It can be replaced without touching the kernel (lesson of `sched_ext`).
- It groups the load to put cores to sleep.
- **Heat and battery.** It first reduces the budgets of the background class, then closes fast cores; the frame class is touched last.
- It is one of the boot-image services pinned in memory (see [memory.md](memory.md#boot-image-services)).

### Core load

- **Measurement.** Each kernel knows the exact load of each context, because it debits the budgets. It gives it per context by `sched_read` (with the instructions retired, on demand: D-118) and per core by `node_status` (D-110, D-129); a page listing every context could not have a fixed size. There is no statistical estimate as in Linux.
- **Two speeds.** Reflex in the kernel: a core with no work sleeps in place, and no node runs on another node's core (D-128); the kernel moves no thread by itself, and a thread never leaves its node (inside its node, the placement service moves its context with `sched_configure`: [A node of several cores](kernel-interface.md#a-node-of-several-cores)). Policy in user space: the placement service rebalances, groups, chooses core types and moves threads within the set of cores it authorised, on the scale of a few periods.
- **Frequency.** In version 1, only per-class preferences are set: on Intel, the hardware sets the frequency itself (HWP, from memory), and the system gives it, per core, the bounds and the energy or performance preference according to the class; the preference is set per core with `node_perf` ([Cores](kernel-interface.md#cores)), not at each switch of context (D-110). On-demand frequency is deferred until after the alpha (**Decided**, 14 November 2026). The deferred proposal: deadlines are known, so the frequency of a core is chosen to finish the budget just before the deadline, instead of reacting to load after the fact; a user input raises the frequency of the frame path before the load arrives.
- **Cores on demand.** Nodes that take and give cores at run time are deferred until after the alpha (**Decided**, 14 November 2026) and enter the contract only once the conditions of its open point hold (D-128). In version 1 the placement service sizes each node when it starts (see [kernel.md](kernel.md#dynamic-structure)).
- **Hardware hints** on the nature of each thread (Intel Thread Director, AMD's workload classification): one more input for the placement service, which the kernel records per context when the placement service counts it (`sched_count`, [Unlike cores](kernel-interface.md#unlike-cores)), with the instructions retired (D-118).
- **Hardware threads.** Two hardware threads of one physical core never serve two different publishers at the same time (side channels). In version 1 the second thread stays idle (see [kernel.md](kernel.md#multi-core-structure)).

## In a process

The Wasm runtime schedules its asynchronous tasks cooperatively; the kernel sees only threads.

## Priority inversion on a shared service

**Proposed, 14 November 2026**, with the changes decided the same day.

The case: a background client is inside the service when a frame-class client arrives.

1. **Threads.** A service chooses one thread or one thread per core (**Decided**). With one passive thread per core, a call stays on the caller's core and two cores do not wait for each other.
2. **Lending.** The waiting client lends its context (budget and deadline) to the client being served, until the service is free. Not in the kernel (D-110, proposed: see [What is not provided](kernel-interface.md#the-budget-follows-the-call)); a service on the frame path has one thread per core or a frame-class context.
3. **Threshold on entry.** Not in the kernel either (D-110). A call enters only if the remaining budget covers the declared worst case of the call (the latency contract of the capability); otherwise it waits outside for its budget to be refilled. seL4 MCS has this problem open, and the same remedy as a proposal (RFC-14, budget thresholds on endpoints, not merged to the project's knowledge; read through a search summary, merge state not verified).
4. **Exhaustion all the same.** Exhaustion raises nothing in the kernel: the context waits for its next period (D-110). A server thread that loses the context it ran on raises the fault *no context* to its supervisor ([The budget follows the call](kernel-interface.md#the-budget-follows-the-call)); the request is cancelled and the service returns to its previous state. Cancellable requests are required only of the project's own native services (**Decided**).

## A multithreaded process

**Revised, 16 November 2026 (D-128).** The core group of 14 November 2026, a process spread over several per-core kernels, is gone: a process lives in one node, and a process with threads on several cores lives in a node of several cores ([kernel.md](kernel.md#multi-core-structure)).

- The placement service starts a node of the size a process needs (from its manifest), on free cores, and the process's objects are made from that node's memory. The node's cores are fixed until it ends; growing or shrinking a node while it runs is deferred (above).
- Each context is placed on one core of the node, in its cores set, and admitted there; the placement service moves contexts between the node's cores with `sched_configure`. The budget is per context, in nanoseconds of the core it runs on; the kernel scales nothing across unlike cores. A node may hold cores of several kinds that share their state features and vector lengths.
- The kernel notifies the runtime of the number of cores its node has, so that the runtime sizes its threads instead of overloading (idea of scheduler activations, from memory).
- A thread preempted while it holds a lock: the waiter lends it its context, by the same lending mechanism as above (not in the kernel, D-110).

## Time spent in interrupts

**Proposed, 14 November 2026.**

- Drivers are in user space: in the kernel an interrupt is only an acknowledgement and a notification, of bounded duration.
- That time is constant, and is charged to the context that was running when the interrupt arrived (D-110, see [What runs next](kernel-interface.md#what-runs-next)).
- The driver does its processing on its own context. When its budget is exhausted, its interrupt line stays masked until the refill, which bounds an interrupt storm (a consequence of the acknowledgement rule, with no mechanism of its own: an interrupt is signalled once until `irq_ack`, which a throttled driver cannot call; see [Interrupts](kernel-interface.md#interrupts)).
- An input or output completion is charged to the client whose request completes: the request carries a slice of its budget.
- Interrupts of devices outside the frame class are directed to efficiency cores or grouped at the start of a period.

## Latency contracts

**Aligned** (retained with the user's agreement, to be designed; from the second delegated study of 14 November 2026, not cross-checked).

- Latency contracts are carried by capabilities, with admission at the time of the grant and a model that the agent can query. They use measured budgets, because a worst case computed on Wasm is unrealistic.
- GPU submissions enter the same deadline graph as the processor. The earlier claim that no kernel was found doing display-anchored scheduling is softened (**Decided**, 14 November 2026; see [prior art](../research/prior-art.md#novelty-claims-and-verdicts)).

## Real time

**Proposed.** Scheduling contexts with a budget and a deadline already suit embedded real-time needs (see [platform.md](platform.md#embedded)).

## Hardware to watch

Intel Software Defined Super Cores: patent EP4579444A1 (filed in 2023, published in July 2025; verified 14 November 2026 by web search), several cores merged for a single thread and seen as one core by the OS. It is a patent, not a product. If the merge becomes controllable by the OS, it is one more policy for user space.

## Checks and gates

- Deterministic simulation of the scheduler (same seeds as the messages between cores), and the latency gates.
- Gate added (**Decided**, 14 November 2026): an asynchronous WIT call between two processes, end to end. See [plan/gates.md](../plan/gates.md).
