# Progress

The map of the work and where it stands. An arrow means "is needed by". This file is updated in the same change as the work it describes: moving a box is part of "done" (see [verification.md](verification.md#development-workflow)).

Last update: 14 November 2026.

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
| Reference model, one core | Claude Fable 5.2 | Written from the settled contract; [pull request 3](https://github.com/Vehicoule/dodos-kernel/pull/3). Follows D-106 (`thread_cancel`); 405 tests, CI green; mutation: 176 of 177 killed on the whole model at pass 8 (the last is equivalent), 26 of 26 on `thread_cancel`. Reviewed four times (thirteen reports in `reviews/`); the last two reviews found no design error and no wrong behaviour. To do: re-reading by the two humans, then merge |
| Package manifest contract | | Not started |
| Trials of weeks 1-2 | | Not started |

## Decisions that block a step

A box below cannot turn orange before its decision is taken and written in the [decision log](../decisions/README.md). The agent that starts the step checks this table first.

| Decision to take | Blocks | Notes |
|---|---|---|
| Who clears frames: the kernel, or the memory service | The memory part of the kernel interface, which is itself needed before the one-core kernel is written | The kernel does not clear them today. The memory service gives pages from one process to another without the kernel, so it must clear in any case. To decide with a measure |
| How the root of authority survives the loss of one core's kernel | One-core kernel, for what it fixes in `abi/` and in the layout of objects (generation number in a reference, share of memory per core in the start-up information); multi-core by messages for the rest | Direction decided (D-107): the root is rebuilt from a fixed share, nothing is adopted. To design before the one-core kernel is written |
| Cancelling a wait | One-core kernel | Done (D-106): `thread_cancel` is in `abi/` and in the model, pull request 3 |

Weeks and dates are in the [calendar](roadmap.md#calendar).
