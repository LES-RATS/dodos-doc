# Progress

The map of the work and where it stands. An arrow means "is needed by". This file is updated in the same change as the work it describes: moving a box is part of "done" (see [verification.md](verification.md#development-workflow)).

Last update: 16 November 2026.

Colours: green is done, orange is in progress or next, grey is later. Double-bordered boxes are public milestones.

```mermaid
flowchart TD
    classDef done fill:#2e7d32,stroke:#1b5e20,color:#ffffff
    classDef next fill:#ef6c00,stroke:#e65100,color:#ffffff
    classDef later fill:#eceff1,stroke:#90a4ae,color:#263238

    subgraph Foundations
        design["Design documents and decision log"]:::done
        kif["Kernel interface, validated"]:::done
        abi["Interface in code: abi crate"]:::done
        wit["WIT contracts 0.1"]:::done
        repos["Kernel and system repositories, CI green"]:::done
        manifest["Package manifest contract"]:::next
    end

    subgraph Kernel["Kernel track"]
        model["Reference model, one core"]:::next
        trials["Trials: Zig and Rust boundary, kernel without per-thread stack, seL4 oracle harness"]:::next
        debug["Debugging base: console, debugger stub, traces, crash record"]:::next
        k1["One-core kernel: capabilities, IPC, frames"]:::later
        tools["Native shell and tools"]:::later
        models3["Formal models: revocation, group size, recovery"]:::later
        kn["Multi-core by messages, distributed revocation, kernel recovery"]:::later
        sched["Scheduling, memory service, mlibc, Rust std, virtio"]:::later
        hw["Reference desktop: ACPI, PCI, IOMMU, NVMe, network card"]:::later
        gputrial["Trial: NVIDIA core outside Linux"]:::next
        gpu["NVIDIA core, NVK back end, GPU service, USB, audio"]:::later
    end

    subgraph Hosted["Hosted track, on Linux and macOS"]
        runtime["Hosted runtime and dodo tool"]:::next
        gpuitrial["Trial: shell drawn by gpui"]:::next
        surface["Surface: compositor and catalogue"]:::later
        agent["Actions, agent, confirmations, injection attack suite"]:::later
        shell["Shell"]:::later
        store["Blob store and signed packages"]:::later
        ported["Services ported to the kernel"]:::later
    end

    subgraph Milestones
        demo[["First public demonstration, IPC measured"]]:::later
        http[["A wasi:http component served under QEMU"]]:::later
        server[["Server image on the desktop"]]:::later
        triangle[["Vulkan triangle, real compositor"]]:::later
        alpha[["Alpha, end of 2027"]]:::later
        beta[["Beta, 2028"]]:::later
    end

    design --> kif --> abi --> model
    design --> wit --> runtime
    repos --> model
    repos --> runtime
    wit --> manifest --> store
    abi --> trials
    model --> k1
    trials --> k1
    debug --> k1
    k1 --> tools
    k1 --> demo
    k1 --> kn
    models3 --> kn
    kn --> sched --> http
    sched --> hw --> server
    gputrial --> gpu
    hw --> gpu --> triangle

    runtime --> surface --> agent --> shell
    gpuitrial --> surface
    runtime --> store
    agent --> demo
    shell --> ported
    store --> ported
    sched --> ported --> server
    server --> triangle --> alpha --> beta
    ported --> alpha
```

## Now

| Item | Who | State |
|---|---|---|
| Reference model, one core | Claude Fable 5.2 (passes 1 to 9), Claude Opus 5.5 (passes 10 to 13) | Written from the settled contract; [pull request 3](https://github.com/Vehicoule/dodos-kernel/pull/3), head `2afc901`. Pass 13 (16 November 2026) answers the sixth review (four reports, 38 findings: protocols between nodes, other architectures, the gate, tests and time): all confirmed at least in part and corrected in the contract (D-124) and the model; two parts not confirmed (a revocation's grant is freed by the holder's release anyway; the MADT GICC does carry an efficiency class). 985 tests, CI green; the suite runs on three page geometries (4, 16 and 32 KB); `./verify` on CI from 11 min 21 s to 3 min 40 s, no assertion of a test removed (cut: repeated invariant checks in two setup loops, the second run of page-independent files). Mutation: the review's 44 surviving mutants all killed; of the 35 mutants of the pass's own fixes, 33 killed and 2 equivalent (redundant guards). Now modelled: several nodes sharing one core, the device identifiers' owners, mappings made in steps. Before pass 13: Pass 12 (16 November 2026) models every group of the contract on several nodes with two page sizes: 921 tests, CI green; mutants killed per group: nodes and grants 27 of 27, unlike cores 37 of 37, cores and roles 40 of 41 (one equivalent), debugging 17 of 17. Not modelled: the time recovery takes, several nodes sharing one core in turn, console output, DMA faults, the debugger stub, the contents of vector state and of a crash record, `cap_derive`/`cap_move`/`untyped_retype` with a destination on another node, capabilities carried back in a reply across nodes, requests to an IOAPIC's role holder. Eight contract problems reported and settled by D-123. Before pass 12: pass 11 (15 November 2026, head `40c6863`) modelled every group of the contract except cores, debugging and `ioports`: 690 tests, CI green, 23 contract problems reported and settled by D-122. Before pass 11: Follows D-109 (wait number for `thread_cancel`); 453 tests, CI green; mutation: 176 of 177 killed on the whole model at pass 8 (the last is equivalent), 54 of 54 on what pass 10 changed; the whole-model mutation was not rerun after pass 9. Reviewed five times (seventeen reports in `reviews/`); the fifth review found no wrong behaviour and one design error in D-106, corrected by D-109. Pass 10 is not yet reviewed from outside. To do: re-reading by the two humans, then merge |
| Kernel interface: every group (capabilities to start-up, memory and devices between nodes, the gate over page tables, unlike cores, cores and roles, debugging, `ioports`, entropy) | Claude Opus 5.5 | Integrated on 16 November 2026, branch `contract-integration`: the 23 problems of pass 11 settled by the rulings of 16 November, D-112 to D-121 and the seven drafts of `research/drafts/` written in; 64 calls. The values `abi/` must gain, and what pass 12 of the reference model must cover, are in [abi-changes.md](../research/drafts/abi-changes.md). No reference model of the new groups yet, not reviewed; the D-110 groups still need their review |
| Package manifest contract | | Not started |
| Trials of weeks 1-2 | | Not started |

## Decisions that block a step

A box below cannot turn orange before its decision is taken and written in the [decision log](../decisions/README.md). The agent that starts the step checks this table first.

| Decision to take | Blocks | Notes |
|---|---|---|
| Who clears frames (D-110, proposed) | Reference model of the memory group; one-core kernel | Rule written for validation: the kernel clears every object it creates, frames included, 64 KB per call with `again`. It replaces the earlier choice (the kernel did not clear frames). The memory service still clears pages it moves between processes without the kernel |
| Scheduling points of D-110 (proposed) | Reference model of the scheduling group; one-core kernel | Rules written for validation: admission of every context against one core, with slack by class; no lending to a busy shared server and no entry threshold; no signal at exhaustion; a lend outlives the caller's wait; the clock does not count suspended time; the fault *no context*; the numbers. See [Points for the two owners](../architecture/kernel-interface.md#points-for-the-two-owners) |
| Task and marks points of D-110 (proposed) | Reference model of the tasks group; research axis 4 as written in [prior-art.md](../research/prior-art.md#kernel-research-axes) | Rules written for validation: `task_revoke` stops threads in one write and capabilities are removed by the supervisor; the kernel task has no time budget and no log; a task lives on one node; marks flow both ways with capabilities |
| Start-up and hardware points of D-110 (proposed) | One-core kernel, for the start-up state and the layout of kernel memory | Rules written for validation: equal shares of memory per node; device memory and line interrupts owned by the boot node; the interrupt table as fixed kernel memory (exception to rule 3); the kernel reads the ACPI MADT and DMAR (exception to D-054); 64-byte capability slots; no vector state in the register calls |
| How the root of authority survives the loss of one core's kernel | One-core kernel, for what it fixes in `abi/` and in the layout of objects (generation number in a reference, share of memory per core in the start-up information); multi-core by messages for the rest | Direction decided (D-107): the root is rebuilt from a fixed share, nothing is adopted. To design before the one-core kernel is written |
| Whether a node may run on several cores at once (D-108 is validated otherwise, D-113) | One-core kernel, for the lock and the layout of kernel state | Decided by a measured trial of the three candidates of [kernel.md](../architecture/kernel.md#nodes-cores-and-load): first on the Mac (ARM64, native) as an indication, then on the reference desktop Third series on the Mac (15 November 2026, branch `trial-multicore`, commit `af018b5`): fixed groups are out; groups sized to the process lead on lookups with changes (2 to 32 % at 4 cores) and on change latency; one node per core leads on signals from many threads to one (8 % to 1.7 times) and by 1 to 2 % on IPC, at the edge of the noise. Still to measure: the real cost of an interrupt between cores (reference desktop), a notify updated by one atomic operation, finer locks for unmaps, and whether the fine locks are legal for the removal of a subtree. Fourth series (16 November 2026, `f9933bd`), k = 4: a signal by one atomic operation brings candidate 3 level with candidate 1 when the receiver is busy, and leaves candidate 1 ahead by 6 to 8 % when the receiver usually waits; unmap with range locks puts candidate 3 ahead when every thread unmaps (28 to 45 % with a free interrupt, 1.55 to 2.0 times at 1 µs); on a busy shared server the candidate makes no difference, the policy does (foreground p99: 170 µs in queue order, 59 with lending, 58 with refusal, 10 to 15 with two server threads). A flaw found in the earlier series (an interrupt charged twice) touches candidate 2 only. Still not measured: the real cost of an interrupt, removal of a derivation subtree under range locks. |
| Memory between nodes, and the node that owns each device (D-112, D-113) | One-core kernel, for the start-up page and `abi/` | Directions accepted: chunks that change owner, devices that follow their driver. Design being drafted |
| Who owns the hardware watchdog: the platform service or the kernel | Integration of the debugging draft into the contract | Held until the report on stopping a core without its cooperation (D-116): a watchdog is one way to stop a core. Asked for by the owner on 15 November 2026, not to be forgotten. Also open with it: the debug transport on the reference PC (a serial port, the owner's desktop has none on its case) |
| Measures that need the reference desktop | Choice between one node per core and groups sized to the process (real cost of an interrupt between cores); forced stop of the bootstrap core (D-117); debug transport | The desktop is out of reach until about 29 November 2026 (said by the owner on 15 November). Until then the work runs in virtual machines and on the Mac; what the Mac can measure is to be explored |
| Cancelling a wait | One-core kernel | D-106 corrected by D-109 after the fifth review (a wait number, so that a cancel is neither lost nor hits a later call). Contract, `abi/` and model done (pass 10 of pull request 3); to review by the two humans |
| Does the contract hold on ARM64 and RISC-V, and leave room for later architectures | One-core kernel | Asked by the user on 15 November 2026. One reviewer of the sixth review reads the whole contract with this angle only: every rule that depends on x86-64 without saying so |
| Weaknesses of the design for memory and devices between nodes (trust in the hardware node, changes that wait during its reload, line interrupts stopped, a table every kernel can write, free memory of a node that is down) | Integration of that design into the contract | Treated in the contract of 16 November 2026: the hardware node became one role per unit and its context entries are checked by the gate (G9); only changes on one unit wait during a take-over; lines are acknowledged from any node where the IOAPIC has an EOI register (to test); the table is read-only in every kernel and written only through gates; free memory starts unclaimed and a dead node's memory goes to any live node. To re-read by the owners |

Weeks and dates are in the [calendar](roadmap.md#calendar).
