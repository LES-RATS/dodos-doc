# Thesis, principles and scope

Statuses (Decided, Aligned, Proposed, Open) are defined in the [README](README.md#status-legend).

## Thesis

An operating system where an agent can act safely for the user, and which never gets in the way.

Three reasons to exist:

1. Monolithic kernels erode under the number of vulnerabilities. A capability microkernel is the structural answer. A capability is an explicit, revocable token that grants one right; a microkernel keeps only the minimum in the kernel and runs the rest as isolated programs.
2. Leave the Unix / POSIX / glibc / systemd ecosystem without locking users in again: the application ABI (application binary interface) is a standard (Wasm, WASI, the web) that also runs elsewhere.
3. A new experience: an agent that is always present, discreet and safe (the inspiration is Jarvis), in a shell designed for it, where the web is one surface among others.

## Principles

- Do not reinvent the wheel: port, borrow, and write only what differentiates.
- Tests are the specification. This is what makes code written together with AI agents reliable.
- Latency is a contract, checked by gates. Fast gates run at every merge and hardware gates run at night (see [plan/gates.md](plan/gates.md)).
- No ambient authority: a program has only what it is handed.
- The user owns the machine and the data.
- **Repositories** (**Decided**, 14 November 2026; replaces "one repository per component"). Two code repositories, split later if needed. The **kernel repository** holds the kernel, its executable model, the oracle harness, the formal models, the proofs and the [kernel interface](architecture/kernel-interface.md) with its generated bindings; nothing in it knows Wasm or WIT. The **system repository** holds everything in user space: runtime, services, drivers, shell, applications, the WIT contracts (including `os:core`), the SDK and the image build. It pins the kernel by commit, and moving the pin runs the system's checks. This documentation repository keeps the cross-cutting design and the decision log.
- The kernel is the centrepiece, the part that sells. The project starts from existing work to move fast, but the goal is to bring something new to the kernel (see the [kernel research axes](research/prior-art.md#kernel-research-axes)), then to the OS itself.
- **Portable and built to last** (**Decided**, 14 November 2026): the whole system, from the last application down to the kernel, is designed to be ported and to survive over time. Support for several architectures is part of this: nothing assumes x86-64 outside the architecture layer.
- **English for development** (**Decided**, 14 November 2026): code, comments, commits, `AGENTS.md`, decision records, repository documentation.
- **Documentation** (**Decided**, 14 November 2026): the original direction document is archived ([archive/DIRECTION.fr.md](archive/DIRECTION.fr.md)). The documentation is a set of English files, one per domain, with a [decision log](decisions/README.md).

## Scope

| Topic | Position | Status |
|---|---|---|
| Games | Wasm and cloud only | Decided |
| Native applications | Set aside for now: Wasm and WIT remain the only application ABI. See [architecture/wasm-abi.md](architecture/wasm-abi.md#native-applications) | Aligned |
| Virtual machines | Out of scope as a way to run anything on the OS. Linux drivers in micro-VMs are plan B, opened only if the emulation layer stalls on a driver (see [architecture/drivers.md](architecture/drivers.md#drivers-in-micro-vms-fallback)) | Decided |

## Out of scope

- Virtual machines, compatibility with Linux or Windows applications, POSIX as an ABI.
- CUDA and DLSS.
- A native ABI for applications, for now.
- 32-bit.
- Self-hosting of development (developing DodOS on DodOS).

What is deferred until after the alpha, rather than out of scope, is listed in [plan/roadmap.md](plan/roadmap.md#deferred-after-the-alpha).

## Licence

**Decided.** Dual licence: AGPLv3 and commercial. The SDK and the libraries linked into applications are under a permissive licence. Linux drivers are under GPLv2, in separate processes. The licence of the Linux emulation library is detailed in [architecture/drivers.md](architecture/drivers.md#licence). The points to put to legal counsel are listed in [research/open-questions.md](research/open-questions.md#project-level-questions).
