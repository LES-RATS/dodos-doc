# Security

Statuses are defined in the [README](../README.md#status-legend). The sections "Three boundaries" and "Chain of trust" are **Proposed**. Other statuses are given per section.

There is no container, because there is nothing to contain: no global name and no ambient authority. Every program is, from the start, what a container tries to obtain after the fact.

## Baseline

**Aligned.**

- A key service, isolated, with a narrow interface.
- Data protection classes.
- Indicators (microphone, camera, capture) and confirmations are drawn by the compositor, out of reach of applications.

## Three boundaries

From the cheapest to the strongest.

| Boundary | Separates | Cost |
|---|---|---|
| Wasm component | The parts of one application, including its dependencies. A third-party library receives only the imports it is handed | A function call and the copy of the arguments |
| Process | Publishers. One process per publisher (or per web site), never two publishers in the same address space, because of Spectre-type side channels | One IPC |
| IOMMU domain | A driver, its device and the rest of memory (see [drivers.md](drivers.md#iommu)) | |

## Chain of trust

- Firmware, then the signed boot image, then the system, which is a hash. Every blob is verified on read by its Merkle tree: at reboot, the machine is exactly that hash.
- All executable code descends from a signed blob. Only the compile service produces machine code, cached by component hash, compiler version and instruction set (see [wasm-abi.md](wasm-abi.md#compile-service)). Applications cannot create an executable page. The only exception under discussion is the JIT of the web process (**Open**; see [web.md](web.md#jit-in-the-web-content-process)).
- System calls are accepted only from the kernel-supplied code page (see [kernel.md](kernel.md#base-decisions)).
- Inside the kernel, a write gate is the only writer of the page tables, the IOMMU tables and the machine table, so a faulty kernel on one core is bounded to its own memory (D-117, D-120; [The gate over page tables](kernel-interface.md#the-gate-over-page-tables)). The console exists only if the signed image declares one, and never shows an address or memory contents (D-118).
- The user can enrol their own keys: the machine stays theirs.

## Permissions

| Topic | Position | Status |
|---|---|---|
| Permissions | Centralised: one right = one capability = one revocable line | Decided |
| Persistence of rights | Static rights are re-derived from the manifest; dynamic rights live in a handle table kept by the system | Aligned |
| Rights screen | A query on the capability tree (see [ui.md](ui.md#settings-notifications-and-rights)) | Proposed |
| Debugging | Debugging a component is a capability, one per component. There is no global developer mode: the user enrols a developer key. The kernel has no object for it: the supervisor hands the debugger the component's thread capabilities (registers and hardware breakpoints) and forwards its faults. The kernel debugger stub exists only in development images, which only a developer key signs ([Debugging](kernel-interface.md#debugging-call-reference)) | Proposed |

## Accounts and user keys

**Proposed, 14 November 2026, to validate.**

- A user is a key. The session is opened by a code verified by the TPM (the machine's security chip); biometrics later.
- No online account is mandatory.
- There is no superuser: to administer is to hold the administration capabilities of the device, which are handed to the first user.
- Several users are planned in the design (zones per user; see [storage.md](storage.md#zones)); version 1 exposes only one user and the guest session.
- Lost key: a recovery key is handed over at installation; another device of the circle can give the key back; sharing between relatives later. There is no escrow at the project.

## Disk key

**Proposed.** The disk key is sealed in the TPM (Intel fTPM of the desktop) against the signing key of the system and not against its hash, so that an update does not break unlocking. The user's code is protected by the TPM's anti-brute-force mechanism. There is a recovery key.

## Secure boot

**Proposed.** A single signed EFI image (loader, kernel, boot image). On the project's machines, the user enrols the project's key or their own in the firmware. For machines where this is not possible, an intermediate loader signed by Microsoft, later.

TPM and secure boot: the mechanisms are known but were not re-read. A Microsoft-signed loader for a non-Linux OS is not verified.

## Signing keys

**Proposed, 14 November 2026, to validate.** TUF roles, an offline root on hardware keys, a threshold of two keys out of three (one per person, one in a safe).

## Publisher keys

**Decided, 14 November 2026.**

- A publisher has a root key that delegates signing keys.
- Revocation is distributed with the TUF metadata.
- A new right at update time requires the user's agreement.

The identity of a component is its publisher key plus its name (see [storage.md](storage.md#packages-and-distribution)).

<a id="threat-model-outline"></a>

## Threat model

**Proposed, 16 November 2026, to validate by the two owners.** It replaces the outline of 14 November 2026 and is the one page that step 0 of the [build order](../plan/roadmap.md#build-order) asks for. Each line names the decision or the file it comes from, with that line's own status. A line that no document backs is marked Proposed and gives the alternative. Where the design does not hold, the line says so and points to [Points for the two owners](#points-for-the-two-owners).

### What is protected

| Asset | Where it lives | Source |
|---|---|---|
| The user's data: collections, their versions, the `home` collection of each application | User and application zones, encrypted with the user key | [storage.md](storage.md#zones) (Proposed) |
| The agent's memory | User zone, store objects with provenance | [agent.md](agent.md#memory) (Aligned) |
| Secrets typed into a secret field (passwords, codes) | Never in the memory of the model or of the surface owner: the system reads the value when the button is activated and hands it to the action | [Provenance marks](#provenance-marks) (Decided, D-035) |
| Keys: user key, disk key, recovery key, device key, a developer's publisher keys, the project's signing keys | TPM, key service, offline hardware keys | [Accounts](#accounts-and-user-keys), [Disk key](#disk-key), [Signing keys](#signing-keys) (Proposed); [Publisher keys](#publisher-keys) (Decided) |
| The rights the user granted: manifest rights and the handle table | Held by the system | [Permissions](#permissions) (Decided, D-011) |
| The integrity of the running system: what runs is the signed system hash | System zone, every blob verified on read | [Chain of trust](#chain-of-trust) (Proposed) |
| The trusted path: confirmations, indicators, the focus, the agent's entity | Drawn by the compositor | [Baseline](#baseline) (Aligned); [The agent's entity](#the-agents-entity) (Proposed) |
| Microphone, camera, screen capture, sound capture | Distinct rights; indicator drawn by the compositor | [ui.md](ui.md#audio) |
| What can be done in the user's name outside the machine (mail, payments, accounts) through actions of reach `external` | Remote | [Effect class](#effect-class) (Decided, D-035) |
| The user's attention | | Proposed: named as an asset, because a confirmation protects only as far as it is read, and every rule that adds one is paid for here ([Known weaknesses](#known-weaknesses)) |

### Adversaries

| Adversary | What it can do | What stops it, and where it is not stopped |
|---|---|---|
| Hostile web page | Run script in its own content process; show any pixels in its surface; put any text in its accessibility tree, which the agent may read; attack the engine | One process per site ([Three boundaries](#three-boundaries)); a site exports no actions and gets no WIT interface ([web.md](web.md#web-content-and-capabilities), Aligned); what the agent reads from it carries the origin `web:<origin>` and marks the task `untrusted` (D-035). The JIT of the content process is Open ([web.md](web.md#jit-in-the-web-content-process)) |
| Hostile or compromised application, signed by its publisher | Use every capability it was granted; write any text into its outputs, its action descriptions, its notifications and its surface; declare the effect class of its actions | Component and process boundaries; no executable page (Chain of trust); only the focused surface gets keys ([ui.md](ui.md#input)); it cannot draw glass ([ui.md](ui.md#design-system)); its output is untrusted (D-035); a false class gains nothing for a local action (D-035). **Not stopped**: a false class on an action of reach `external` ([point 1](#points-for-the-two-owners)) |
| Hostile content read by the agent (prompt injection) | Any text or image in a mail, document, page, action output, transcript or capture. It can make the model pick any action of the task's scope with any input | The scope, the marks and the confirmation matrix, enforced by the system and not by the model (D-035, D-036) |
| Hostile model or model provider | Everything injected content can do, on every task, from the first token, with no mark set. A remote provider also reads everything sent to it | The scope and the confirmations of the matrix still hold. **Not stopped**: the cells the matrix leaves automatic in a task without the `untrusted` mark, and the confidentiality of what is sent to a remote model ([point 3](#points-for-the-two-owners)) |
| Thief with the machine, off or locked | Read the disk, boot other media, try codes, speak to the machine | User and device zones encrypted, disk key sealed in the TPM with its anti-brute-force mechanism ([Disk key](#disk-key), Proposed); a locked session runs no task on user data ([Speech](#speech), Proposed). Advanced physical attacks are out of scope |
| Hostile peripheral (USB, PCIe, Thunderbolt; Bluetooth after the alpha) | DMA, interrupts, malformed descriptors aimed at a driver, act as a keyboard, present hostile storage | IOMMU active before the first driver, interrupt remapping, one driver process per device ([drivers.md](drivers.md#iommu)); storage is the foreign zone, read through a reader component ([storage.md](storage.md#zones)). A machine without an IOMMU declares its drivers trusted and displays it. **Not stopped**: a device that types as a keyboard ([point 12](#points-for-the-two-owners)) |
| Faulty kernel on one core | Write wrong values anywhere its own node can reach | The write gate is the only writer of page tables, IOMMU tables and the machine table; the core is fenced, its memory reclaimed, its kernel reloaded (D-117, D-120). **Not bounded**: the task identifier and marks it stamps on the messages it sends to other nodes ([point 4](#points-for-the-two-owners)) |
| Hostile update | A package signed by a compromised publisher key; a system image | TUF metadata and revocation; no new right at update without the user's agreement (D-056); a system image needs the threshold of the project's keys ([Signing keys](#signing-keys), Proposed); the user can enrol their own keys. A/B/R rollback covers an image that fails to boot, not a hostile image that boots |
| Network attacker | Read, change, replay packets | TLS in the network service with shipped trust roots (D-055); no incoming packet without a listening capability, encrypted DNS ([network.md](network.md#the-network-service-replaces-a-firewall), Proposed) |

A hostile device of the user's circle is deferred with device-to-device communication (D-065); a lost device is revoked by the others (D-074).

### The three boundaries in this model

The [three boundaries](#three-boundaries) each stop one group of adversaries. The Wasm component stops a library inside an application, and makes each action a fresh instance. The process stops a site or a publisher from reaching another, including through Spectre-type channels. The IOMMU domain stops a peripheral and its driver. Two further lines carry the model without being called boundaries: the **task**, which bounds what the agent can do ([Delegation by task](#delegation-by-task)), and the **write gate**, which bounds a faulty kernel to its node (D-117, D-120).

### What is trusted

The documents give no size for any of these components except where stated.

1. The hardware and its firmware: processor, memory, TPM (the Intel fTPM of the desktop), IOMMU. Compromised firmware is out of scope.
2. The kernel of each core: a Rust core and a Zig hardware layer, with the write gate (D-126, proposed). Each node trusts the stamps that other nodes put on their messages.
3. The boot-image services, pinned in memory: storage service, disk driver, service manager, memory service, placement service ([memory.md](memory.md#boot-image-services), Decided).
4. The supervisor ([kernel.md](kernel.md)) and the platform service, which carries uACPI, PCI enumeration and interrupt routing (D-054).
5. The mark-aware services: storage, network, clipboard, compositor, memory service, supervisor. Each one has its own attack test ([Marks and services](kernel-interface.md#marks-and-services), D-110, proposed).
6. The Wasm runtime and the compile service (Wasmtime, with Winch and Cranelift): the component boundary and the linking of each action instance to its class rest on them. Only the compile service produces machine code (Chain of trust).
7. The compositor and the shell, with gpui, gpui-kit and wgpu: they draw the trusted path. A copy of gpui linked into an application weighs 8 to 15 MB, a figure quoted by a guide and still to measure ([ui.md](ui.md#design-system)).
8. The system side of tasks: the code that keeps the marks, applies the matrix, stamps provenance, validates the interface tree and builds each confirmation from the action's schema. The documents name no service and no process for it ([point 10](#points-for-the-two-owners)).
9. The key service.
10. The network service: TLS, the trust roots blob, the scopes of network capabilities.
11. The audio service and the input chain (the evdev drivers in the emulation layer, ported libinput and xkbcommon): they make the microphone indicator true and give keys the origin `user`.
12. Keys: the project's signing keys, each publisher's root key for its own packages, the keys the user enrols.
13. The user, for what they confirm.

Not trusted, and bounded instead: applications, web content processes, drivers and the Linux emulation layer (behind the IOMMU), the model and the inference engine, the agent component itself (it acts only through its task), the wake-word detector (microphone in, one signal out, no network, no storage: [agent.md](agent.md#voice)), input engines (no network: [ui.md](ui.md#input)).

### Out of scope

| What | Why | Status |
|---|---|---|
| Compromised firmware | It runs below the kernel and before it; nothing the system checks can vouch for it | Proposed, 14 November 2026 (outline) |
| Advanced physical attacks: cold boot, bus probing, fault injection, implants | They need the machine in a laboratory and defeat the TPM and the IOMMU, which the model relies on | Proposed, 14 November 2026 (outline) |
| Timing and other covert channels between a marked and an unmarked party | Known limit of every information-flow system; the bits of a notify carry no marks ([Tasks and marks](kernel-interface.md#tasks-and-marks)). Spectre-type channels between publishers are reduced, not excluded ([Side channels](#side-channels)) | Proposed (D-110) |
| Text-to-text manipulation: the model writes a false summary or a phishing sentence to the user, with no action | It changes no data flow; CaMeL excludes it too (non-goals, section 3.1). Cards of a marked task show the mark, so the user sees where the text comes from | Proposed |
| A user who confirms without reading, or under coercion | A confirmation cannot judge its reader; Meta's "Rule of Two" names the same limit. It is counted as the cost of each confirmation | Proposed |
| What a remote party does with data once an external action sent it | Outside the machine | Proposed |
| Denial of service by an application against the machine | Bounded by budgets ([scheduling.md](scheduling.md)), a goal of the latency contracts and not of this model | Proposed; alternative: count availability as an asset |
| A malicious project signing threshold, or a publisher against its own packages | They are on the trusted list; the user's own keys are the way out | Proposed |

## Vulnerabilities

**Proposed, 14 November 2026, to validate.** A `SECURITY.md` file, a disclosure delay of 90 days, and tracking of the fixes of the long-term-support Linux kernel and of Ladybird.

## Side channels

**Proposed, 14 November 2026, to validate.**

- The rule "one process per publisher" already bounds sharing.
- The Spectre protections of Wasmtime are active.
- Reduced-precision clock for untrusted content.
- Two hardware threads of one physical core never serve two publishers at once (see [scheduling.md](scheduling.md#core-load)).

## Related

- Lost device: [devices.md](devices.md#identity).
- Entropy: [kernel.md](kernel.md#entropy).
- Input security (focus, global shortcuts, input injection): [ui.md](ui.md#input).
- Audio rights and the microphone indicator: [ui.md](ui.md#audio).
- Attack tests per boundary: [plan/verification.md](../plan/verification.md#kernel-verification).
- Expected costs of isolation: [plan/gates.md](../plan/gates.md#expected-costs).
