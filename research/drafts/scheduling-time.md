# Draft: scheduling and time, call reference for one core

Group: scheduling contexts (`sched`) and their calls, lending a context across `call` and the answer, what runs next on one core, budget exhaustion and replenishment, `yield`, the `timer` object, the monotonic clock, and the idle state of a core.

Part 1 is written to be pasted into `kernel-interface.md`, at the end of "Call reference, one core" (after "Registers"). Parts 2 to 6 are for the people who merge it.

---

## Part 1. Text to paste

### Time

**Proposed, 14 November 2026**: drafted by the assistant for the time and scheduling groups. The points marked **(design choice)** are the ones where another answer was reasonable.

- **The clock.** The kernel has one clock: a count of nanoseconds in 64 bits, monotonic, the same on every core. It is read without a system call, by the function `clock_now` of the kernel-supplied code page, from a read-only **clock page** that the kernel writes and that is mapped with the code page. The layout of the clock page is in `abi/` (`ClockPage`): a version, a sequence word, and the parameters that turn the processor's counter into nanoseconds. A reader reads the sequence word, the parameters, the counter, then the sequence word again, and starts over if the word was odd or has changed; the value is `ns_base + ((counter - counter_base) * mult >> shift)`, the product taken in 128 bits.
- **The kernel uses the same value.** Every event of a kernel (a call, an interrupt) has one instant, `now`: the clock read at its entry, with the same parameters. So a deadline that user space computes from `clock_now` is compared by the kernel with the same clock, on every core.
- **Every instant and every duration given to a call is in nanoseconds and must be below 2^63** (`invalid` otherwise, judged with the plain arguments). An instant is a value of the clock; a duration is a difference of two values. 2^63 nanoseconds is 292 years, so no sum that the kernel makes from valid values overflows 64 bits.
- **Time spent with the machine suspended is not counted (design choice).** After a whole-machine resume the clock continues from the value it had at the suspend; the kernel changes `ns_base` under the sequence word. Why: if suspended time counted, every deadline, budget and timer would fall due at once at resume. The alternative is a clock that counts suspended time (Linux keeps both, `CLOCK_MONOTONIC` and `CLOCK_BOOTTIME`, from memory); the time of day, which must count it, is a service ([platform.md](platform.md#time)).
- **The architecture layer must give a counter that is invariant and synchronised between cores** (on x86-64, the invariant TSC). A value read on one core, then sent by any means to another core, is never greater than a value read afterwards on that core. A core whose counter does not meet this is not started.

### Scheduling contexts

A `sched` is a **scheduling context**: the right to use a share of one core's time. A thread runs only on a context.

Words used below:

- A context **bound** to a thread by `sched_bind` is that thread's **own context**; the thread is the context's **home**. A context has at most one home, a thread at most one own context.
- A context can be **lent**: a passive server that receives a call runs on the caller's context (see [The budget follows the call](#the-budget-follows-the-call)). A thread with a context lent to it has no own context.
- A thread's **context** is its own context, or the one lent to it, or none. Never both.
- A thread is **runnable** when it is not suspended and does not wait.
- The **holder** of a context is the one thread that may run on it (rule below). A context is **eligible** when it is configured, not dying, and its holder is runnable.

A context has these parameters, set by `sched_configure`:

| Parameter | Meaning |
|---|---|
| budget *B* | Nanoseconds of the core the context may use in each period. At least 10 µs (provisional) |
| period *T* | Nanoseconds. *B* ≤ *T* ≤ 2^36 ns (about 68 s, provisional). The deadline of each period is its end: the relative deadline is the period |
| class | 0 frame, 1 interactive, 2 background. Used only to share the time that no context with budget wants (see [What runs next](#what-runs-next)) |
| cores | The cores where the context may be placed: a window of 64 cores and a mask (`sched_set_cores`) |

and this state:

| State | Meaning |
|---|---|
| configured | A new context is not configured; it runs nothing |
| remaining *r* | Signed nanoseconds left in the current period. The context **has budget** when *r* > 0; otherwise it is **throttled** until its replenishment instant |
| deadline *d* | An instant: the end of the current period. The kernel orders contexts with budget by it |
| replenishment instant | While throttled: the instant at which budget comes back |
| consumed | Nanoseconds the context has run since it was created, all kinds of time included |
| home, chain | Its home thread, if any; its lends, in the order they were made (see below) |

A context made by `untyped_retype` (size argument 0) is not configured, has no home, class 2, and the cores set {the core of the kernel that holds it}.

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `sched_configure` | sched, core, budget, period, class | | `manage` on the sched, `write` on the core. Budget and period are both 0 (the context becomes not configured) or 10 µs ≤ budget ≤ period ≤ 2^36 ns; class is 0, 1 or 2; the core must be the core of the kernel that holds the sched; any of these failing is `invalid`. `budget` when admission fails (rule below) |
| `sched_bind` | sched, thread | | `manage` on the sched, `manage` on the thread. `busy` if the sched has a home, if the thread has an own context, or if a context is lent to it. The thread may be suspended, waiting, or bound to no capability space |
| `sched_unbind` | sched | | `manage`. Succeeds when the sched has no home |
| `sched_set_cores` | sched, core, window, mask | | `manage` on the sched, `write` on the core. The set is the cores numbered 64 × window + *i*, for each bit *i* set in the mask. `invalid` if the window is 1024 or more, if the mask is 0, or if the set does not contain the core of the kernel that holds the sched |
| `sched_read` | sched | consumed, remaining, deadline, state | `read`. Remaining is a signed word. The state word has bit 0 configured, bit 1 throttled, bit 2 has a home, bit 3 lent (its chain is not empty). A context that is not configured reads 0, 0, 0 and its state bits |
| `yield` | | | No capability. See [What runs next](#what-runs-next) |

Rules of the calls:

- **Configuration needs a `core` capability with `write` (design choice).** Every configured context takes a share of a core, and that share is refused to others; so who may configure is decided by holding the core, as with the `SchedControl` capability of seL4 MCS (verified, see sources). The placement service holds the core capabilities, configures every context, and hands out capabilities to the contexts, with `manage` or without. This is how "the frame class is a capability" holds: only the placement service makes a context of class 0, and the shell hands it to the foreground surface and takes it back. A `core` capability without `manage` gives this right without the right to stop the core.
- **Admission (design choice).** Each context has a bandwidth, *u* = ⌈*B* × 2^32 / *T*⌉ (128-bit arithmetic), and 0 when it is not configured. The kernel of each core keeps the sum of the bandwidths of the contexts it holds that are configured and not dying. `sched_configure` computes the sum with the new bandwidth in place of the old one; if it is greater than 2^32 (one whole core) the call returns `budget` and changes nothing. Removing a configuration never fails. Why every class, not only the frame class as [scheduling.md](scheduling.md#mechanism-in-each-cores-kernel) proposed: the order by deadline guarantees every budget only while the sum is at most one core; a context outside admission could take the time of a frame-class context. Unused time is not lost: it goes to throttled contexts (see below). How much of a core the frame class may take (half, per scheduling.md) is the placement service's rule, not the kernel's.
- **The effects of `sched_configure`.** On a context that was not configured, with a budget that is not 0: *r* = *B*, *d* = now + *T*. On a context that was configured, with a budget that is not 0: the class changes at once; *r* becomes the smaller of *r* and the new *B*; *d* and a replenishment instant do not change; the new *B* and *T* are used from the next replenishment. With budget 0: the context is not configured, *r* = 0, *d* = 0, and its holder does not run. The new bandwidth counts in the sum from this call.
- `sched_bind`: the thread becomes the home; a thread that was marked as having lost its context (see below) is no longer marked. `sched_unbind`: the home becomes none; the thread has no context. Neither changes the chain: lends go on.
- **Unbinding is how a server becomes passive.** A server thread is bound to a context so that it can run its start-up code and reach `recv`; while it waits, its context is unbound; it then runs only on the contexts lent to it.
- No thread ever waits on a `sched`. A call on a dying `sched` returns `gone`, as on any dying object.
- **Destroying a context** is a removal in bounded steps (see [The derivation tree](#the-derivation-tree)). The first step marks it dying, takes it out of every queue of the scheduler, takes its bandwidth out of the sum, and makes its home have no context. Each later step clears up to 32 of its lends, from the top of the chain down; each cleared lend counts as one of the 32 of the step. A thread that loses its context this way is marked as having lost it.
- `sched_set_cores` records the set. The core a context is on changes only by a move between kernels, which belongs to the multi-core part (see [One kernel per core](#one-kernel-per-core)).

### What runs next

The kernel of a core keeps its contexts in sorted queues linked through the `sched` objects themselves (no kernel memory):

- the **ready queue**: eligible contexts with budget, ordered by deadline;
- three **slack queues**, one per class: eligible throttled contexts, ordered by replenishment instant;
- the **sleeping queue**: throttled contexts that are not eligible, ordered by replenishment instant.

A context is in at most one of them. Equal keys are kept in the order in which the contexts entered the queue: a context that enters a queue goes after every context that has the same key. A context that changes queue, or whose key changes, enters again.

**The choice.** At the end of every event, the kernel runs:

1. the holder of the first context of the ready queue (the nearest deadline; between equal deadlines, the context that entered first);
2. otherwise, the holder of the first context of the slack queue of the smallest class number (the nearest replenishment instant; between equals, the context that entered first);
3. otherwise nothing: the core is idle.

A running context stays in its queue. A context that becomes eligible with a nearer deadline than the running one takes the core at the end of that event (preemption); with an equal deadline it does not.

**Order inside an event.** For every event:

1. `now` is read. The time since the previous event is charged to the context that was running, if any (added to consumed; and taken from *r* if it was running from the ready queue, not from a slack queue). The kernel's own time in an event is charged to the context that was running at its entry; a kernel measures it at the exit, and the reference model takes it as zero.
2. A timer interrupt processes the due events (below).
3. The call, if the event is a call.
4. If the context that was running at the entry was running from the ready queue and now has *r* ≤ 0, it is exhausted (below).
5. The faults `no_context` are raised (see [The budget follows the call](#the-budget-follows-the-call)).
6. Every context whose eligibility or budget changed in the event is put in its queue; a context that became eligible with budget gets the wake-up rule first.
7. The choice, then the hardware timer is set (below).

**Exhaustion and replenishment (design choice: a constant bandwidth server, as Linux `SCHED_DEADLINE`; verified, see sources).**

- A context is exhausted when *r* ≤ 0. Let *n* = 1 + ⌊−*r* / *B*⌋, the number of budgets needed to make *r* positive. Its replenishment instant is *d* + (*n* − 1) × *T*. If that instant is not after now, it is replenished at once; otherwise it goes to a slack queue or to the sleeping queue.
- At its replenishment instant: *r* += *n* × *B*, *d* += *n* × *T*, and if *d* is not after now, *d* = now + *T*. An overrun is therefore paid back over the following periods, as [D-039](../decisions/README.md) asks for emulated drivers; in practice an overrun is only the kernel's own latency, because a context is stopped when its budget ends.
- **The wake-up rule.** A context with budget that becomes eligible after being not eligible (its holder woke, was resumed, was bound; the context was configured) keeps *r* and *d* if *r* × *T* ≤ (*d* − now) × *B* and *d* is after now (128-bit products); otherwise *r* = *B* and *d* = now + *T*. This keeps a context that sleeps and wakes from using more than its bandwidth. A context that passes from one holder to another inside one event (a `call` to a passive server, an answer) is not woken: it was eligible before and after.
- A throttled context gets nothing from waking: it waits for its replenishment instant.
- **Exhaustion is not a fault (design choice).** A context that uses its whole budget waits for its next period; the thread is not told. Why: a periodic thread that uses all its budget is normal, and seL4 MCS also raises its timeout fault only when a handler was set (verified, see sources). The alternative, a notification at each exhaustion, is listed for the two humans.

**Slack (design choice).** Time that no context with budget wants goes to throttled contexts whose holder is runnable, frame class first, then interactive, then background, and in a class to the nearest replenishment instant. A context running on slack is charged in consumed, not in *r*. Why: admission makes every budget a guarantee, and without slack a core with little reserved bandwidth would stay idle while threads wait; an interactive thread with a small budget gets the whole core when nothing else wants it. The alternatives were classes with strict priority and no admission below the frame class (a thread that wakes is starved behind contexts whose deadlines lag, when the sum of bandwidths passes one core), or fixed priorities as in seL4 MCS, which the documents do not want.

**`yield`.** The context the caller runs on gives up its remaining budget: if it has budget, *r* = 0 and it is exhausted at once, by the rule above (*n* = 1, replenishment instant *d*). If it was already throttled (running on slack), it enters its slack queue again, behind the contexts that have the same replenishment instant. The call returns `ok` and the choice is made again; on an otherwise idle core the caller runs again at once, on slack. `yield` takes no argument; a thread whose capability space is dying gets `gone`, as from every call. Why: on one core a thread that waits for another thread by repeating a call must let it run; this is the rule of Linux `SCHED_DEADLINE` and of seL4 MCS for a context whose budget is smaller than its period (both verified).

**Due events and the hardware timer.**

- A **due event** is a replenishment whose instant is not after now, or a timer whose firing instant is not after now. A timer interrupt processes at most 16 due events (provisional), in this order: the earliest instant first; at equal instants, replenishments before timers, the slack queues by class, then the sleeping queue, then the timers; inside one queue, the order of the queue. If due events remain, the hardware timer is set to now, so the next interrupt comes at once and processes the next 16 before anything else runs.
- After the choice, the hardware timer is set to the earliest of: the instant the running context's budget ends (now + *r*, when it runs from the ready queue), the first replenishment instant of the four throttled queues, and the first firing instant of the timer queue. With nothing armed, it is not set.
- Determinism: the reference model processes every due event at its instant before any call at that instant. A kernel processes them at its interrupt, later by at most its interrupt latency; the differential test compares states at event boundaries. One call reads its own timer state exactly: see `timer_cancel`.

**Bounds.** Each sorted queue is a balanced tree linked through the objects, whose height is at most 2 × ⌈log2(*N* + 1)⌉ for *N* objects in it; *N* is bounded by the memory of the core's kernel (for 2^40 bytes, at most 2^33 contexts of 128 bytes, so at most 68 objects visited). The result never depends on the shape of the tree, only on the keys and the order of entry. A call puts at most 4 contexts in a new queue position, and at most one timer; a timer interrupt processes at most 16 due events, each one queue removal and at most one insertion, and a firing timer wakes at most one thread. **(design choice: the alternative, a calendar of time buckets with a bitmap, is constant time but rounds deadlines; the sorted queue of seL4's release queue is a list, linear in its length, from memory)**

### The budget follows the call

**A `call` lends the caller's context to a passive receiver (design choice: seL4 MCS, with the differences below).** This is the mechanism of [the budget follows the call](scheduling.md#the-budget-follows-the-call) (D-039).

- **A lend is made when a call is delivered** to a receiver that has no own context (a **passive** receiver), if the caller's context exists and is not dying. The lend is recorded in the receiver's reply object, the one that the delivery arms: the context, and the receiver. A receiver with an own context gets no lend and runs on its own context.
- **The chain.** The lends of one context are linked through the reply objects, in both directions, in the order they were made; the last one is the **top**. A passive server that, running on a lent context, calls another passive server lends the same context again, on top.
- **The holder.** The holder of a context is: its home, if the home is runnable; otherwise the receiver of the top lend, if the chain is not empty; otherwise none. So the home runs on its own context as soon as it is runnable, whatever servers still work on it; a server runs on a client's context only while the client waits.
- **A lend is released** only when: its receiver begins to receive (`recv` or `reply_recv`, after the answer of `reply_recv` and before anything is received); its reply object is given to `recv` or `reply_recv` by another thread; or its reply object, its receiver or its context is destroyed. Releasing takes the lend out of the chain in one step, wherever it is. **An answer does not release a lend, nor does the end of the caller's wait by `thread_cancel` (design choice).** So a reply object can be idle and still carry a lend, until its receiver receives again; an idle reply object is accepted by `recv` as before.
  - Why: a client whose call is ended by a time limit ([D-109](../decisions/README.md)) is runnable, and by the holder rule it runs at once on its own context. The server is not cut off in the middle of its work: it goes on with the abandoned request on the client's context whenever the client waits, until it receives again, and that time is charged to the client who asked for it. With seL4's rule (from memory) the context comes back only through the chain of answers, so a time limit could not free the client while the server worked; with the other obvious rule (the context comes back to the client and the server loses it) every time limit would leave a server thread without a context.
  - The cost: a server that answers with `send` and goes on working runs on its client's context until its next receive. A passive intermediate server whose own call is ended by `thread_cancel` is not freed at once: it runs again when the servers above it in the chain receive again. A time limit frees the home of the context at once, and only the home; a server that needs its own time limits has an own context.
- **What a passive thread does not get.** A passive thread has no time of its own, so nothing that is not a call reaches it: `recv` by a thread without a context does not take a pending notification of the bound `notify` (it stays pending); `signal` on a bound `notify` wakes the first thread that waits to receive only if it has an own context; `send` on an endpoint delivers only if the first thread that waits to receive has an own context, `would_wait` otherwise. Only the first waiting thread is looked at, so each of these is one step.
- **A thread that loses its context.** A thread is **marked as having lost its context** when a lend to it is released by anything other than its own receive (its reply object given to another receiver, its reply object or its context destroyed), when the context of which it is the home is destroyed, and when, passive, it receives a call that brings no lend (the caller had no context, or a dying one). The mark is removed when a context is bound to it or lent to it. At the end of the event in which a marked thread is runnable, it raises the fault **`no_context`**, unless its capability space is dying or destroyed, or it has no fault endpoint, or its fault endpoint is dying or destroyed; in those cases it simply does not run.
  - The fault is delivered as a `call` made by the thread on its fault endpoint: label `FAULT_NO_CONTEXT`, no word, no capability, the badge of the capability given to `thread_configure`, an empty receive range, wait number 0. It lends nothing (the thread has no context): a fault endpoint must be served by threads with an own context, and a passive thread that receives the fault is itself marked. The answer ends the fault; its words are ignored. The thread then runs if it has a context, and otherwise raises the fault again at the end of that event. `thread_cancel` with wait number 0 ends the fault wait in the same way.
  - Why a fault: when a client is killed, the passive server thread that worked for it has no time left; without a fault its supervisor would never learn it. The supervisor binds a context to the thread, or restarts it. The fault group will deliver its other faults the same way; only the label and this case are fixed here.
- A thread that has no context and is not marked (a new thread resumed before a context is bound, a thread whose own context was unbound or is not configured) does not run, and raises nothing.
- Destroying a reply object or a thread takes its lend out of the chain in one step; destroying a context takes its lends out in bounded steps (see [Scheduling contexts](#scheduling-contexts)). Destroying the home of a context leaves the context without a home; its lends go on.
- **Cost of the fast path.** A `call` to a passive receiver and its answer move no context between queues: the context stays eligible and only its holder changes, so the direct switch of [Synchronous or asynchronous](#synchronous-or-asynchronous) keeps its cost.
- **What is not provided (design choice, see "For the humans").** The kernel does not lend the context of a caller that waits in the queue of an endpoint to the thread that is serving another caller (the "lending" of [scheduling.md](scheduling.md#priority-inversion-on-a-shared-service)), and it does not refuse a call whose remaining budget is below a threshold. A slow request on a passive server holds the other callers for at most the replenishment of the served client's context; a service on the frame path has one thread per core (D-028) or an own context of the frame class.

### Timers

A `timer` is one deadline that, when it falls due, signals a `notify`. It is **idle** or **armed**. A new timer (size argument 0) is idle.

| Call | Arguments | Result | Rights and rules |
|---|---|---|---|
| `timer_set` | timer, notify, deadline, tolerance | was armed (0 or 1) | `write` on the timer, `send` on the notify. The deadline is an instant, below 2^63 (`invalid`). The tolerance is a duration, any word |
| `timer_cancel` | timer | was armed (0 or 1) | `write` |

- **Firing.** An armed timer fires at the first event at or after its **firing instant** at which the kernel processes it (a timer interrupt, within the 16 due events). Firing does what `signal` does with the capability given to `timer_set`: it sets in the word of the notify the bits of that capability's badge, or bit 0 if it has none; if a thread waits on the notify, the first one is woken with the whole word and the word is cleared; a bound endpoint is served as for `signal`. The timer becomes idle. A timer is one-shot; a period is built by setting it again, from the deadline it had, which does not drift because the deadline is an instant.
- **The firing instant (design choice).** With *x* the smaller of deadline + tolerance and 2^63 − 1, the firing instant *f* is the number between the deadline and *x* that has the most trailing zero bits: let *m* be the index of the highest bit in which deadline − 1 and *x* differ; *f* is *x* with its *m* lowest bits cleared (and *f* = 0 when the deadline is 0). A timer never fires before its deadline and never after its deadline plus its tolerance, plus the interrupt latency. Timers whose windows overlap tend to choose the same instant without the kernel comparing them, so they fire in one interrupt and the core sleeps longer. With tolerance 0, *f* is the deadline. Why: the grouping costs nothing and does not depend on the other timers, so it is deterministic. The alternatives: a window on both sides of the deadline, as the default of Zircon (verified), would fire a time limit early; choosing the instant from the timers already armed needs a second ordering of the queue.
- **`timer_set`**, in order: if the timer is armed and its firing instant is not after now, it fires first (this is how one call sees its own timer exactly); then the result is 1 if the timer is still armed, and that arming is cancelled; 0 otherwise; then *f* is computed with the new arguments; if *f* is not after now the timer fires in this call, before it returns, and stays idle; otherwise it is armed with *f*, the notify and the bits. Setting a timer again therefore replaces its arming, and never takes back a bit that an earlier firing set.
- **`timer_cancel`**, in order: if the timer is armed and its firing instant is not after now, it fires first; then the result is 1 if the timer was armed, and it becomes idle, 0 otherwise. **A result of 1 means that this arming has not fired and never will. A result of 0 means that the timer was not armed: it never was, it was cancelled, or it has fired, and then its bits are in the notify word or were already taken by a waiter. `timer_cancel` never clears a bit of the notify.** This settles the open point of the fifth review.
- The notify is judged when the call is made (rights at call time): revoking the capability afterwards does not disarm the timer. An armed timer is linked into a list of the notify it signals, through the timer objects. **Destroying a notify** disarms its armed timers in the steps of the removal, each one counted as one of the 32 of a step; a timer whose notify is dying is disarmed, without a signal, when it falls due.
- **Destroying an armed timer** takes it out of the queue and of the list of its notify, in one step. No thread ever waits on a timer. A call on a dying timer returns `gone`.
- Armed timers are kept in one sorted queue per core, ordered by firing instant, then by the order in which they were armed; it is linked through the timer objects and has the bounds of the scheduler's queues. At most 16 due events, timers and replenishments together, are processed per timer interrupt; this is also the most timers that fire in one interrupt.

**How a time limit is built, exactly (D-109).** A thread C gives each wait that has a limit a number greater than every number it used before, and writes it in a word that a helper thread H reads. It sets a timer T that signals a notify N on which H waits, then makes its call with that wait number.

- When its call returns, C calls `timer_cancel(T)`. Result 1: T did not fire and will not for this arming; nothing reaches H; C may write its next number and set T again at once. This is the common path, and it needs no exchange with H.
- Result 0: T fired; H has been woken or will be, and calls `thread_cancel(C, n)` with the number it reads. A cancel of a number whose wait is over is harmless, now and later. The one care is the word: C must not write its next number before H has read this one (H can clear the word, and C, on this path only, waits for that), otherwise H would cancel C's next wait. A thread that keeps two timers and two words, used in turn, never waits on this path.
- If H's cancel comes before C's wait begins, the wait returns `cancelled` at once (D-109).

### Idle

- **A core is idle when no context is eligible.** Its kernel sets the hardware timer to the next instant it must act (the earliest replenishment instant or firing instant, which it knows exactly because there is no periodic tick) and puts the core in the deepest idle state whose exit latency plus minimum residency is shorter than the time until that instant. An interrupt wakes it. With no armed instant, it takes the deepest state.
- The idle states of a processor are described by firmware (ACPI), which the kernel does not read; the table of states (exit latency, minimum residency, how to enter) is given to the kernel of each core by user space through a call of the Cores group. Until a table is given, the kernel uses the architecture's plain halt instruction.
- Idle time is charged to no context; each kernel counts its idle time, its slack time and its kernel time, published by `core_status`.

### One kernel per core

**What is per core.** Each kernel holds, in its node (D-108): the ready, slack and sleeping queues, the timer queue, the sum of admitted bandwidths, the running context, the instant of the previous event, the hardware timer, and the idle table. A `sched`, a `timer`, and the objects a lend links (the reply objects of the chain, the home, the receivers) all belong to that kernel. The clock is the only thing common to all cores, and it is computed, not shared: every kernel uses the same parameters.

**Rules that already hold for several kernels:**

- `sched_configure` and `sched_set_cores` need the core capability of the kernel that holds the sched; admission is per kernel.
- `sched_bind` needs the sched and the thread to belong to the same kernel; `timer_set` needs the timer and the notify to belong to the same kernel (`invalid` otherwise, judged with the kind of the second capability). Why: an interrupt never sends a message between kernels, and no lend crosses kernels.
- **A lend exists only inside one kernel.** A call delivered by another kernel brings no lend. The multi-core part must say what a passive receiver does with such a call; the recommendation is that the placement service avoids it (a service has a thread per core, D-028), and that the call is then delivered and the receiver marked, by the same rule as a caller without a context.

**What a move of a thread between kernels needs from this group** (the protocol itself is the multi-core part's):

- The context must be movable: its chain empty and its holder its home (no lend crosses kernels). Its state is plain values: *B*, *T*, class, cores, *r*, *d* or its replenishment instant, consumed. The instants are values of the common clock, so they keep their meaning on the other core.
- The source kernel takes the context out of its queues (one step) and its bandwidth out of its sum; the destination admits it, and may refuse with `budget` as `sched_configure` does. The destination must be in the context's cores set.
- Timers do not move with a thread: they are not bound to threads. A thread that moves keeps the timers it set on the old kernel, which signal notifies on that kernel.
- **Parked nodes (D-108).** A node parked on another core keeps its own queues and its own sum; the guarantees of admission hold for parked nodes only if the core that runs them gives each node its share. The parking protocol must therefore park only nodes whose sums add up to at most one core, and run them by the same order of deadlines; this is the multi-core part's.

---

## Part 2. Changes needed elsewhere in the contract

In `kernel-interface.md`:

1. **Objects table**, row `sched`: "budget, period, deadline, core class, allowed cores" becomes "budget, period, class, allowed cores; its current deadline and remaining budget". Row `reply`: "It returns the caller's budget" becomes "It carries the lend of the caller's context to a passive server". Row `timer`: "A deadline with a tolerance, which signals a `notify`" stays.
2. **System calls**: "About 46 calls" becomes 47. Scheduling row: add `sched_read`; replace "Admission control is in `sched_configure`. `sched_set_cores` is reserved to the placement service" by "Admission and `sched_set_cores` need a `core` capability with `write`". Time row: "read from a shared page, without a call" becomes "read by `clock_now` in the code page, from the clock page, without a call".
3. **Faults paragraph** ("A page fault, an illegal instruction or a budget overrun becomes a message on the thread's fault endpoint"): remove "a budget overrun" (exhaustion is not a fault) and add "a thread that lost its context (`no_context`)".
4. **Call reference, introduction**: "It covers ... capabilities, object creation, threads, IPC and notifications" adds scheduling and time.
5. **Order of checks, step 3**: "the kinds of the groups not yet specified: time, tasks, ..." loses "time"; `timer` is now made with size argument 0 (`sched` already was). **Step 4**: add `budget` to the state errors (only `sched_configure` returns it, and it has no other state error).
6. **Threads table**, row of `thread_read_regs`/`thread_write_regs`: "these two calls, and `yield`, are not part of the one-core reference" becomes "these two calls are not part of the one-core reference"; `yield` now has its rule. The same correction in D-109's summary is a matter for the log, not this file.
7. **Threads**, `thread_resume`: add "a resumed thread that has no context does not run (see [The budget follows the call])".
8. **IPC table**: `call`: add "the delivery lends the caller's context to a passive receiver". `recv`: "In order: a pending notification of the bound notify; ..." becomes "In order: the release of the thread's lend and of the reply object's lend; a pending notification of the bound notify, if the thread has an own context; the first caller ...". `send` on an endpoint: "delivered only if a thread waits to receive" becomes "... and the first one has an own context".
9. **IPC bullets**: "When a caller disappears while its request is being served, or its wait is ended by `thread_cancel`, the reply object becomes idle" gains "; a lend it carries stays until its receiver receives again".
10. **Notifications**: "A `signal` on a bound notify wakes the first thread that waits to receive on the endpoint, if no thread waits on the notify itself" gains "and if that thread has an own context". The same for `notify_bind` delivering a pending word at once.
11. **The derivation tree, removal steps**: "at most 32 capabilities are removed or threads woken" becomes "at most 32 capabilities are removed, threads woken, lends cleared or timers disarmed". "Destroying an object wakes every thread that waits on it" gains the cases of the `sched` (its lends) and of the `notify` (its armed timers).
12. **Errors table**, `budget`: "Admission refused: the scheduling budgets exceed the period" becomes "Admission refused: the bandwidths admitted on the core would exceed one whole core".
13. **Open points**: remove "whether `timer_cancel` says that the timer had already fired" (settled). The point "what becomes of a thread whose ... fault endpoint is destroyed" is partly settled for `no_context` (it raises nothing).
14. **Start-up information**: the `sched` of slot 4 is configured with budget = period = 10 ms, class 1, and bound to the first thread; its bandwidth is the whole core, so the first process lowers it before it configures another context (design choice: the first process must run, and only it knows the policy). The `core` capability of the boot core needs a fixed slot or an entry in the start-up page; the reference model gives it none today and needs one to call `sched_configure`. The clock page is mapped with the code page; **the contract does not say yet how the code page enters an address space**, and the clock page follows whatever is decided.
15. **Object sizes**: no change. A `sched` uses 96 of its 128 bytes; a `timer` uses its 64 (firing instant, notify, bits, three tree words, two list words); a `reply` uses its 64 (state and flags, caller or attached thread, receive range, and the lend: context, receiver, two chain words); a `notify` adds one word (its list of armed timers). If an implementation needs a word more for the dying mark of a timer, the timer goes to 128 bytes.
16. **Synchronous or asynchronous**, row "IPC on the same core": "runs on the caller's budget" holds for a passive server; add "a server with an own context runs on its own".
17. **Power states**: the clock does not count suspended time.

In `scheduling.md`:

18. "Admission. Creating a context of the frame class is refused if the sum of the budgets exceeds the period" becomes admission of every context per core, at most one whole core; the cap of the frame class is a rule of the placement service.
19. "The kernel picks the nearest deadline among the contexts that still have budget" gains "and gives the remaining time to throttled contexts, by class".
20. "Core load, Measurement ... publishes it in a read-only page": per context, `sched_read`; per core, `core_status`. A page per kernel listing every context cannot have a fixed size.
21. "Priority inversion on a shared service": point 2 (lending to the client being served) and point 3 (threshold on entry) are not in the kernel; point 4 ("A timeout fault goes to the supervisor of the service") becomes the fault `no_context` when a context is lost, and nothing on exhaustion.
22. "Time spent in interrupts": the driver's context being throttled is what keeps its line masked until the refill; the interrupt group says how `irq_ack` and the throttled state meet, and whether the kernel time of a device interrupt is charged to the driver's context instead of the interrupted one (this file charges the kernel's time of a timer interrupt to the interrupted context).
23. "Frequency ... energy or performance preference according to the class": the preference is set per core by the Cores group, not at each switch of context.

In `abi/src/lib.rs`: see Part 5.

---

## Part 3. For the humans

Each point has a recommended rule, already written in Part 1.

1. **Admission of every context, with slack, instead of admission of the frame class only.** Recommended: every configured context is admitted against one whole core, and unused time goes to throttled contexts by class. Cost: the placement service must keep the sum under one core and give every thread a small reservation; with hundreds of contexts each guarantee is small, though slack gives an idle machine to whoever wants it. Alternative A, admission for the frame class only and strict classes below: simpler for the placement service, but the order by deadline loses its guarantees when the unadmitted contexts pass one core, and a thread that wakes can be starved behind contexts whose deadlines lag. Alternative B, fixed priorities as in seL4 MCS: well known and proven, but the documents chose deadlines and the screen-free period per context.
2. **No help to a busy shared server, and no entry threshold.** Recommended: neither. Cost: a frame-class client queued behind a background client on a single-threaded passive server waits up to that client's replenishment, so the background period of clients of shared services must be short (the placement service's rule), and frame-path services need a thread per core or a frame-class context. Alternative A, lending the waiting client's context to the server: needs the kernel to know which thread serves an endpoint, and a second chain per context; seL4 has no such rule (from memory). Alternative B, a threshold per endpoint (the RFC-14 idea of scheduling.md): one word in the endpoint and a call to set it, and a call that does not enter must be retried by the kernel; the merge state of RFC-14 is not verified.
3. **No signal at budget exhaustion.** Recommended: none; the load is read with `sched_read`. Alternative: an optional notify and badge in each context, signalled at each exhaustion (16 bytes of the 32 spare, one signal per exhaustion, one more argument to `sched_configure` or one more call). It would give scheduling.md's "timeout fault to the supervisor" without a fault protocol.
4. **A lend survives the end of the caller's wait, and the home always runs first.** Recommended (Part 1, "The budget follows the call"). Cost: abandoned work goes on, charged to the client; an intermediate server is not freed early by its own time limit. Alternative: the context comes back to the client at once and the server loses it, which makes every time limit leave a server thread without context and needs the fault `no_context` on every limit.
5. **The clock does not count suspended time.** Alternative: counting it, with every deadline due at resume; or two clocks, which doubles the clock page and the deadline argument.
6. **The fault `no_context` is fixed before the fault group exists.** Recommended: deliver it as a call on the fault endpoint, as described. Alternative: a lost context only stops the thread, and supervisors detect stuck threads by their own time limits; simpler now, but a passive server whose client was killed is never noticed.
7. **Numbers** (provisional, to set by measurement): minimum budget 10 µs (makes an overrun from kernel latency smaller than one budget), maximum period 2^36 ns, 16 due events per timer interrupt, start-up context at the whole core with a period of 10 ms, 1024 windows of 64 cores.
8. **Sorted trees in the kernel.** Recommended: balanced trees linked through the objects, logarithmic per operation, exact deadlines. Alternative: a calendar of buckets, constant time with rounded deadlines; the verification of a balanced tree in the Rust part is a known cost.

---

## Part 4. What a reference model of this group must cover

**Inputs.** The clock is an input: an event `advance(t)` with *t* ≥ now, which delivers the timer interrupts at each due instant in order (repeated at the same instant while more than 16 events are due), then `apply(call)` made by the running thread, which the model computes (`running()`), no longer chosen by the caller. The model takes the kernel's own time as zero.

**State to add.** Per context: configured, *B*, *T*, class, cores, *r*, *d*, replenishment instant, consumed, home, chain (as a list), queue and entry number. Per thread: own context, the reply object of its lend, the lost-context mark. Per reply object: the lend (context, receiver). Per notify: its armed timers. Per timer: armed, firing instant, notify, bits, entry number. Per core: the queues (ordered maps keyed by (key, entry number)), the sum of bandwidths, the running context, the instant of the previous event, idle and slack time, the start-up `core` capability.

**Invariants worth checking at every step:**

1. A thread has an own context, or a lend, or neither; never both. `home(s) = t` exactly when `own(t) = s`.
2. Every lend in a chain is in a reply object that is idle or armed, never attached; its receiver's lend points back to that reply object; the chain is linked both ways and its top is the last lend made that is still there.
3. The holder of every context follows the rule (home if runnable, else the receiver of the top lend, else none).
4. A context is in the ready queue exactly when it is eligible and *r* > 0; in the slack queue of its class exactly when eligible and *r* ≤ 0; in the sleeping queue exactly when configured, not dying, *r* ≤ 0 and not eligible; in no queue otherwise.
5. The running thread is the holder of the context the choice gives; nothing runs only when the ready and slack queues are empty.
6. The sum of bandwidths equals the sum over configured, non-dying contexts, and is at most 2^32.
7. A throttled context's replenishment instant is after now (none overdue after the interrupt events of an instant); after a replenishment, *d* > now and *r* > 0.
8. *r* ≤ *B* for every context, except during the period after a configuration that lowered *B*, where *r* ≤ the old *B*.
9. A timer is armed exactly when it is in the timer queue and in the list of its notify; its firing instant is between its deadline and its deadline plus tolerance (saturated), and has the most trailing zeros there. No armed timer has a firing instant not after now once the interrupt events of now are done.
10. No more than 16 due events in one interrupt event.
11. A thread raises `no_context` only when marked, runnable, with a live fault endpoint and a live capability space; a passive thread is never the receiver of a notification or of a `send`.
12. Determinism: the same events at the same instants give the same state.

**Scenarios that must be tested:**

- Time limit, both orders: the timer fires before the reply (C gets `cancelled`, `timer_cancel` gives 0); the reply comes before (gives 1, no bit in N). The cancel comes before the wait (wait returns `cancelled` at once). `timer_cancel` at exactly the firing instant gives 0.
- Re-arming an armed timer gives 1 and moves the instant; re-arming after a firing gives 0 and leaves the bit in the word; a deadline in the past fires inside `timer_set`.
- 17 timers with the same firing instant: 16 fire in the first interrupt, the 17th in the next, before any call; the order is the order of arming.
- Grouping: two timers with overlapping windows get the same firing instant; tolerance 0 gives the deadline.
- Admission at the boundary: a sum of exactly 2^32 is accepted, one more is `budget` and changes nothing; removing a configuration never fails; lowering a budget frees bandwidth at once.
- Exhaustion with an overrun of more than one budget (needs a kernel latency in the model, or a direct state setup): *n* = 2, replenishment one period later.
- The wake-up rule: a context that slept past its deadline gets *r* = *B*, *d* = now + *T*; one that slept briefly keeps its values; one whose ratio is too high is reset.
- Slack: two throttled contexts of classes 1 and 2, the class 1 runs; a context with budget preempts slack at once.
- `yield` with budget (throttled until *d*), on slack (behind equal instants), alone on the core (runs again).
- Lending: client to passive server and back with no queue change; nested passive servers; client cancelled while the server works (the client runs, the server runs when the client waits again, the lend is released at the server's next receive); a worker answers a request while the receiving thread still runs (the client runs; the receiver keeps the lend until it receives).
- Loss: destroying a context with a chain longer than 32 lends takes several steps; each receiver is marked; a runnable marked receiver queues the fault on its fault endpoint; a handler with an own context answers and binds a context; a passive handler is itself marked.
- A passive receiver and a pending notification (stays pending), a `signal` on its bound notify (not woken), a `send` to it (`would_wait`).
- Destroying a notify with more than 32 armed timers takes several steps; a timer due before it is disarmed fires nothing.
- `sched_bind` and `sched_unbind` while the thread waits; unbinding a passive server while it waits; binding to a thread that holds a lend is `busy`.

---

## Part 5. Values that `abi/` must gain

- `Call::SchedRead = 46` (after `ThreadCancel = 45`; the other calls of the group already exist: `Yield`, `SchedConfigure`, `SchedBind`, `SchedUnbind`, `SchedSetCores`, `TimerSet`, `TimerCancel`).
- No new error code (`Budget = 8` exists) and no new object kind (`Sched = 5`, `Timer = 9`, `Core = 14` exist).
- Constants (provisional):
  - `TIME_LIMIT: u64 = 1 << 63` (every instant and duration argument is below it);
  - `SCHED_MIN_BUDGET_NS: u64 = 10_000`;
  - `SCHED_MAX_PERIOD_NS: u64 = 1 << 36`;
  - `SCHED_CLASS_FRAME: u8 = 0`, `SCHED_CLASS_INTERACTIVE: u8 = 1`, `SCHED_CLASS_BACKGROUND: u8 = 2`;
  - `ADMISSION_WHOLE_CORE: u64 = 1 << 32` (bandwidth of one core; a context's bandwidth is ⌈*B* × 2^32 / *T*⌉);
  - `CORE_WINDOWS: u32 = 1024`, `CORE_WINDOW_BITS: u32 = 64`;
  - `TIME_EVENT_STEP: usize = 16` (due events per timer interrupt);
  - `START_SCHED_PERIOD_NS: u64 = 10_000_000` (budget equal to the period, class 1);
  - `SCHED_STATE_CONFIGURED = 1 << 0`, `SCHED_STATE_THROTTLED = 1 << 1`, `SCHED_STATE_HOME = 1 << 2`, `SCHED_STATE_LENT = 1 << 3`;
  - `FAULT_NO_CONTEXT: u32 = 1` (label of the fault; the fault group numbers the others).
- A pure function with its Kani proof: `firing_instant(deadline, tolerance) -> u64`, proved to satisfy deadline ≤ *f* ≤ min(deadline + tolerance, 2^63 − 1) and to have the most trailing zeros in that range; and `bandwidth(budget, period) -> u64`, proved to be at most 2^32 when budget ≤ period.
- The clock page:

```rust
/// The clock page, written by the kernel, read by `clock_now` (Time).
#[repr(C)]
pub struct ClockPage {
    pub version: u32,      // 1
    pub seq: u32,          // odd while the kernel writes
    pub shift: u32,
    pub flags: u32,        // 0, reserved
    pub mult: u64,
    pub counter_base: u64,
    pub ns_base: u64,
}
// size_of::<ClockPage>() == 40
```

- Sizes: unchanged (`SCHED_BYTES = 128`, `TIMER_BYTES = 64`, `REPLY_BYTES = 64`, `NOTIFY_BYTES = 64`), see Part 2, point 15.

---

## Part 6. Sources

- seL4 MCS tutorial (scheduling contexts, `SchedControl` per core, passive servers and donation over `Call` and `ReplyRecv`, timeout faults only with a handler, `Yield` giving up the budget of a context whose budget is below its period, priority on the thread): https://docs.sel4.systems/Tutorials/mcs.html (read on 14 November 2026).
- Lyons, McLeod, Almatary, Heiser, "Scheduling-context capabilities", EuroSys 2018: https://sel4.systems/Research/pdfs/scheduling-context-capabilities.pdf (located, not read; the details of seL4 used here come from the tutorial or are marked from memory).
- Linux `SCHED_DEADLINE` (constant bandwidth server: the wake-up test, throttling, replenishment at the deadline with the deadline moved by one period, admission by the sum of bandwidths, `sched_yield` giving up the remaining runtime): https://docs.kernel.org/scheduler/sched-deadline.html (read on 14 November 2026).
- Zircon `zx_timer_set` (a new set cancels the pending timer; slack early, late or centred, chosen at creation, centred by default; the signal is cleared by cancel or by a new set, unlike the notify bits here): https://fuchsia.dev/reference/syscalls/timer_set (read on 14 November 2026); timer slack: https://fuchsia.googlesource.com/zircon/+/2d0ddc4468af26b568a1fa8ee9865b5fcc8d86ba/docs/timer_slack.md (search summary only).
- From memory, not checked: the constant bandwidth server of Abeni and Buttazzo (1998); the proportional sharing of CBS servers under overload and the lag of their deadlines (reasoned here, not read); seL4's release queue as a sorted list and the splicing of reply objects in its call stack; the height bound 2 log2(n + 1) of a red-black tree; Linux `CLOCK_MONOTONIC` and `CLOCK_BOOTTIME`; the invariant TSC and the TSC-deadline mode of x86 timers.
- Project documents: `kernel-interface.md`, `kernel.md` (nodes, D-108), `scheduling.md`, `memory.md`, `platform.md`, the decision log (D-028, D-039, D-040, D-106, D-107, D-109), the fifth reviews (Gemini Hydrogen finding 5, Mistral's client protocol), `abi/src/lib.rs`, and the reference model `model/src/lib.rs`.
