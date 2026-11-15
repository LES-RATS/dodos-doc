# Drafts

Working drafts written by agents, kept here so that they are not lost. They are **not** the contract: the contract is [kernel-interface.md](../../architecture/kernel-interface.md), and a rule exists only once it is written there and recorded in the [decision log](../../decisions/README.md).

| Draft | Status |
|---|---|
| `memory.md`, `scheduling-time.md`, `irq-tasks-startup.md` | Integrated into the contract on 14 November 2026 (D-110) |
| `nodes-memory-devices.md` | Not integrated. Memory that changes owner between nodes, devices that follow their driver (D-112, D-113) |
| `ownership-alternatives.md` | Not integrated. Survey and the write gate (D-115) |
| `heterogeneous-cores.md` | Not integrated. Cores described by numbers, kinds, feature masks (D-115) |
| `symmetric-nodes-recovery.md` | Not integrated. Roles instead of privileged nodes, the cores group, recovery order (D-115). Its "unfenced core" weakness is rejected by the owner (D-116) |
| `debug-ioports-gaps.md` | Not integrated. Debugging (trace rings, crash record, console, debugger stub), `ioports`, and the gaps found in the contract (15 November 2026) |

They are integrated together, after pass 11 of the reference model.
