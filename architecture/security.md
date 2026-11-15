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

## Threat model outline

**Proposed, 14 November 2026, to validate.** The threat model is one page, written at step 0 of the [build order](../plan/roadmap.md#build-order).

- Attackers: malicious application, web content, prompt injection, plugged-in peripheral, thief of the machine, network.
- Out of scope: compromised firmware, advanced physical attack.

The security model of the agent is a page to write before `core.wit` is frozen (**Decided**, 14 November 2026; see [agent.md](agent.md#security-model)).

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
