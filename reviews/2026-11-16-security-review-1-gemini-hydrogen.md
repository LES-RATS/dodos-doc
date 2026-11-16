# Independent Security & Completeness Review: `Docs/architecture/security.md`

- **Reviewer:** `gemini-4-hydrogen`
- **Date:** 2026-11-16
- **Object reviewed:** [`architecture/security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md) (377 lines, D-130, `Docs` `main` at `c93a623`), cross-checked against [`kernel.md`](/Users/btw/Documents/repos/Docs/architecture/kernel.md), [`kernel-interface.md`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md), [`ui.md`](/Users/btw/Documents/repos/Docs/architecture/ui.md), [`agent.md`](/Users/btw/Documents/repos/Docs/architecture/agent.md), [`drivers.md`](/Users/btw/Documents/repos/Docs/architecture/drivers.md), [`devices.md`](/Users/btw/Documents/repos/Docs/architecture/devices.md), [`network.md`](/Users/btw/Documents/repos/Docs/architecture/network.md), [`storage.md`](/Users/btw/Documents/repos/Docs/architecture/storage.md), [`web.md`](/Users/btw/Documents/repos/Docs/architecture/web.md), [`platform.md`](/Users/btw/Documents/repos/Docs/architecture/platform.md), [`wasm-abi.md`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md), [`memory.md`](/Users/btw/Documents/repos/Docs/architecture/memory.md), [`gpu.md`](/Users/btw/Documents/repos/Docs/architecture/gpu.md), [`scheduling.md`](/Users/btw/Documents/repos/Docs/architecture/scheduling.md), [`decisions/README.md`](/Users/btw/Documents/repos/Docs/decisions/README.md), [`plan/verification.md`](/Users/btw/Documents/repos/Docs/plan/verification.md), [`plan/gates.md`](/Users/btw/Documents/repos/Docs/plan/gates.md), [`plan/pending-decisions.md`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md), `dodos` contracts at commit `8bc6509`, and external primary sources.

---

## Executive Summary

[`architecture/security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md) sharply captures the agent's task/effect-class/provenance model and honestly surfaces 14 open points for the two owners. However, cross-checking the guarantees it asserts against the rest of the architecture, omitted adversaries/assets, primary external sources, and the 14 owner points uncovers **15 concrete defects**:

- **Cross-file mechanism breaks & contradictions:** The shared `home` collection handed to every fresh `actions.invoke` instance creates both a silent exfiltration path (`none, external` + read-only `home`) and a persistent taint/laundering bridge with long-lived `app` instances; compositor **direct scanout** (`0 frame added`) defeats compositor-drawn confirmations, wake-word/mic/capture indicators, and the secure attention view; the boot image omits both the **TPM driver** and **key service** needed to decrypt the `Device` and `User` zones at boot; cached machine code in `Cache` and `simple extent files` lack post-reboot integrity verification; **cross-publisher physical page sharing** of common compiled libraries in the page cache conflicts with the no-shared-address-space Spectre boundary; **TPM sealing** of the pre-session `Device` zone cannot use dictionary-attack PIN protection and has no anti-rollback binding; **hot kernel replacement** (`kernel image 1`) and **shared kept crash areas / unencrypted raw crash storage** break boot integrity and node/user confidentiality; and the **syscall code page** is misclassified as a chain-of-trust security boundary.
- **Omitted adversaries & assets:** Malicious non-keyboard HID peripherals (mice/touchscreens defeating 500 ms click confirmations; lock-screen BadUSB pre-acceptance); shared browser engine processes (`Hub`, `RequestServer`, `AudioServer`, `LibWasm`), `LibJS` web apps holding `os:core`, and browser secrets (cookies, origin storage, passkeys); local model weights, `llama.cpp`'s shared **Vulkan / NVK / GSP firmware** attack surface, global agent memory taint accumulation, and a trivial self-speech filter bypass; the build/CI/dependency supply chain (49 `vcpkg` ports, proprietary GSP firmware, unreviewed Maintenance-lane auto-merges, and inactive branch protection/`CODEOWNERS`); and unencrypted `Packages`, pre-boot DMA, and shutdown device state.
- **External fact error & unverified dependencies:** A **false section citation** to CaMeL (`section 9.2` instead of `section 8.2`), plus unverified assumptions around **Microsoft UEFI signing** under AGPLv3 and **Wasmtime**'s default Spectre/Winch configuration (`csdb` disabled by default on `aarch64`, guard-page omission of linear-memory bounds checks).
- **14 Owner Points audit:** Point 2 reopens settled `D-036`, and 9 of the 14 points miss load-bearing failure modes or concrete alternatives.

---

## Findings

### Finding 1: Shared `home` collection across long-lived `app` and fresh `actions.invoke` leaks secrets on `none, external` and breaks fresh-instance isolation

- **Category:** `breaks a guarantee` / `contradiction`
- **Severity:** Critical
- **Verbatim quotes:**
  - [`security.md:176-177`](/Users/btw/Documents/repos/Docs/architecture/security.md#L176-L177):
    > "Each action runs in a fresh instance, on which the system calls only `actions.invoke`. The instance shares no memory with the running application and is destroyed afterwards. It holds only what the request carries (input, bound objects, the `home` collection), attenuated to the class."
    > "storage is read-only when `change` is `none`, and every network import answers `denied` when `reach` is `local`."
  - [`kernel-interface.md:1072`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1072):
    > "The defence is the fresh instance of each agent action (`agent.md`): such an instance shares nothing that was set up before it was marked."
  - [`kernel-interface.md:1097-1099`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1097-L1099):
    > "**Sticky by default.** A process that receives a marked message takes the marks, and keeps them until it is restarted." ... "**Applications** are not concerned: an agent action runs in a fresh instance (see [agent.md](agent.md))."
  - [`wasm-abi.md:52, 57`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md#L52):
    > "`start(home)`: first launch, or launch with no saved state. `home` is the component's own collection." ... "The same component is instantiated in two ways: long-lived (`start` or `resume`, later `suspend`), and once per action, as a fresh instance on which the system calls only `actions.invoke`"
  - [`storage.md:24, 51`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L24):
    > "Version 1 has one mutable type for heavily rewritten data: simple extent files, allocated in large chunks, used by application databases." ... "Application | The `home` collection received at launch | One user and one application"

- **Concrete scenarios:**
  1. **Exfiltration on `none, external` without triggering `private`:** An application stores user credentials or sensitive user data inside its `home` collection (`Application` zone). An unmarked task invokes a `change: none, reach: external` action of that application (or is steered there by an untrusted description if Point 5 is not adopted, or by a hostile remote model per Point 3). Because [`security.md:176`](/Users/btw/Documents/repos/Docs/architecture/security.md#L176) unconditionally hands `home` (read-only) to the fresh `actions.invoke` instance alongside `wasi:http` `GET`/`HEAD` (`178`), the action reads `home` and exfiltrates its contents in the query string of an outgoing `GET` to its declared host. Reading `home` inside the action does **not** trigger a confirmation because the matrix decision was made at `invoke` entry before the task was marked `private` (and `GET` already ran).
  2. **Cross-instance taint & laundering between fresh actions and the long-lived app:** A `change: reversible, reach: local` action runs **automatically without confirmation** in a task marked both `private` and `untrusted` ([`security.md:203`](/Users/btw/Documents/repos/Docs/architecture/security.md#L203)), with write access to `home` (`177`). First, if the action writes untrusted payloads into an application SQLite database stored as a `simple extent file` ([`storage.md:24, 78`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L24)), no per-record provenance mark is specified for extent writes (unlike `store` objects in [`kernel-interface.md:1098`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1098)), laundering untrusted data back into the long-lived `app` (which then reads it unmarked into future outputs/clipboard). Second, even for marked `store` objects in `home`, [`kernel-interface.md:1099`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1099) exempts applications from being mark-aware, so the long-lived UI instance reading its own `home` becomes **sticky-marked `untrusted`/`private` until restart** ([`1097`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1097)) across completely unrelated tasks and user interactions.

- **Smallest concrete fix:**
  1. Do **not** pass the writable or private `home` collection automatically to `actions.invoke` when `reach` is `external` and `change` is `none` (or when `untrusted` is set without `private`), or treat opening any object from `home` as reading a `private` store object that aborts/confirms `external` egress before any network call can execute.
  2. Restrict `reversible, local` action writes to `home` inside a `private`/`untrusted` task either to provenance-tracked `store` objects (marking the whole extent file on write) or require explicit binding of target objects rather than silent ambient access to `home`.

---

### Finding 2: Direct scanout contradicts compositor-drawn confirmations, indicators, card frames, and the secure attention overlay

- **Category:** `contradiction` / `breaks a guarantee`
- **Severity:** High
- **Verbatim quotes:**
  - [`security.md:13`](/Users/btw/Documents/repos/Docs/architecture/security.md#L13):
    > "Indicators (microphone, camera, capture) and confirmations are drawn by the compositor, out of reach of applications."
  - [`security.md:228-236`](/Users/btw/Documents/repos/Docs/architecture/security.md#L228-L236):
    > "The system alone draws, in system material and out of reach of applications and of the model:
    > - confirmations, and the secure attention view;
    > - the indicators of microphone, camera and capture ([Baseline](#baseline));
    > - the agent's entity (below);
    > - the frame of each card..."
  - [`security.md:266`](/Users/btw/Documents/repos/Docs/architecture/security.md#L266):
    > "Proposed: a discreet permanent mark while only the detector listens (the entity's idle state), the full indicator once the agent listens"
  - [`ui.md:12-13`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L12-L13):
    > "From the first version: shared buffers without copy; direct scanout of a full-screen surface (the surface's buffer is sent to the screen as it is, with no composition and no added frame)" ... "Direct scanout stays decided subject to the GPU trial (**Decided**, 14 November 2026"
  - [`plan/gates.md:18`](/Users/btw/Documents/repos/Docs/plan/gates.md#L18):
    > "| Full-screen WebGPU | 0 frame added |"

- **Concrete scenario:** A user launches a full-screen WebGPU application or full-screen browser video, which triggers direct scanout (`ui.md:12`: the surface's buffer is sent to the display engine `"as it is, with no composition and no added frame"`). Meanwhile, (1) the always-on wake-word detector ([`agent.md:11`](/Users/btw/Documents/repos/Docs/architecture/agent.md#L11)) is active and must display its `"discreet permanent mark"` ([`security.md:266`](/Users/btw/Documents/repos/Docs/architecture/security.md#L266)); (2) a background service holds microphone or screen-capture permission and begins recording; or (3) the user presses the secure attention key ([`security.md:216`](/Users/btw/Documents/repos/Docs/architecture/security.md#L216)) or a confirmation dialog triggers while the full-screen surface owns scanout. Neither `ui.md` nor `security.md` defines hardware overlay plane reservation for system indicators or a rule forcing direct scanout to disengage when any system indicator, confirmation, or secure-attention overlay is active. Either direct scanout suppresses trusted-path UI (hiding active mic/capture indicators and confirmations behind a full-screen app), or forcing composition breaks the decided `"0 frame added"` latency gate (`plan/gates.md:18`).

- **Smallest concrete fix:** State explicitly in both [`ui.md`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L12) and [`security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md#L228) that direct scanout is **disabled whenever any confirmation, secure attention view, agent overlay, or active camera/microphone/capture/wake-word indicator must appear on screen**, unless the compositor places those system pixels on a dedicated hardware overlay plane above the scanout plane (verified in the GPU trial of [`gpu.md:30`](/Users/btw/Documents/repos/Docs/architecture/gpu.md#L30)).

---

### Finding 3: Boot-image circular dependency for TPM unsealing, unverified compiled code in `Cache`, and cross-publisher physical page sharing

- **Category:** `blocks building` / `contradiction` / `breaks a guarantee`
- **Severity:** High
- **Verbatim quotes:**
  - [`memory.md:67`](/Users/btw/Documents/repos/Docs/architecture/memory.md#L67) (and copied in [`security.md:123`](/Users/btw/Documents/repos/Docs/architecture/security.md#L123)):
    > "**Decided.** The services of the boot image are pinned in memory. The list is: kernel, storage service, disk driver, service manager, memory service, placement service."
  - [`kernel.md:199`](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L199):
    > "the user-space driver of the TPM feeds it, with `entropy_read`"
  - [`storage.md:47-49`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L47-L49):
    > "| Packages | Blobs and manifests of applications, models | Machine, shared between users | No | ... |"
    > "| Cache | Compiled code, thumbnails, indexes | Machine or user | Depends on the origin | No | Can be erased at any time |"
    > "| Device | Pairing keys, networks, hardware settings | Machine, available before the session | Yes, TPM key | No | Until factory reset |"
  - [`storage.md:24, 78`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L24):
    > "Version 1 has one mutable type for heavily rewritten data: simple extent files, allocated in large chunks, used by application databases. Copy-on-write extents, per-block checksums and snapshot-based versions for that type are deferred until after the alpha."
  - [`security.md:27-28`](/Users/btw/Documents/repos/Docs/architecture/security.md#L27-L28):
    > "- Firmware, then the signed boot image, then the system, which is a hash. Every blob is verified on read by its Merkle tree: at reboot, the machine is exactly that hash."
    > "- All executable code descends from a signed blob. Only the compile service produces machine code, cached by component hash, compiler version and instruction set (see [wasm-abi.md](wasm-abi.md#compile-service))."
  - [`security.md:22`](/Users/btw/Documents/repos/Docs/architecture/security.md#L22):
    > "One process per publisher (or per web site), never two publishers in the same address space, because of Spectre-type side channels"
  - [`memory.md:21-22`](/Users/btw/Documents/repos/Docs/architecture/memory.md#L21-L22):
    > "the page cache is the set of blobs, shared by hash between all processes. ... The shared cache serves compiled code and native programs (**Decided**)."
  - [`storage.md:68`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L68):
    > "Blobs are deduplicated by content between all packages: a library common to ten applications is stored once, and compiled once."

- **Concrete scenarios:**
  1. **Boot deadlock (`blocks building`):** `memory.md:67` (**Decided**) restricts the signed boot image to six items (`kernel, storage service, disk driver, service manager, memory service, placement service`), excluding both the **user-space TPM driver** (`kernel.md:199`) and the **key service** (`security.md:11, 89, 129`). Yet `storage service` needs the TPM-sealed disk key to decrypt the `Device` zone (`"available before the session"`, `storage.md:49`) and `User` zone (`"User and device zones encrypted, disk key sealed in the TPM"`, `security.md:105`). Either `storage` cannot unlock encrypted zones until services outside the boot image are somehow loaded from unencrypted `System`, or the `TPM driver` and `key service` must be pinned inside the boot image (`memory.md:67` / `security.md:123`)—currently unmentioned in both files.
  2. **Offline code injection in unencrypted `Cache` (`breaks a guarantee`):** Compiled Wasm machine code lives in the `Cache` zone (`"Machine or user | Encrypted: Depends on the origin"`, `storage.md:48`), while `System` only holds the OS image hash and `Packages` is unencrypted (`46-47`). No mechanism stores an authenticated HMAC/signature or Merkle root in a TPM-protected or encrypted zone for cached native machine code across reboots. A `Thief` (or an offline dual-boot OS) alters cached machine-code bytes for a public `Packages` component (or shared library component) in `Cache`. On reboot, `security.md:27`'s system-hash check passes (only `System` is in the boot hash) and the runtime maps the tampered native code (`memory.md:22`), bypassing both Wasm component boundaries (`security.md:28`) and `"at reboot, the machine is exactly that hash"`. Similarly, `simple extent files` (`storage.md:24, 78`) explicitly have **no Merkle tree** and **no per-block checksums**, contradicting `"Every blob is verified on read by its Merkle tree"` (`security.md:27`) if left unencrypted or corrupted offline.
  3. **Cross-publisher physical page sharing (`contradiction`):** `storage.md:68` compiles a shared library once across ten applications, and `memory.md:21-22` (**Decided**) shares compiled code blobs `"by hash between all processes"`. Mapping the exact same physical read-execute pages simultaneously into processes of two mutually untrusted publishers opens classic **Flush+Reload** / I-cache / branch-target-buffer side channels across process boundaries, undercutting the Spectre rationale of [`security.md:22`](/Users/btw/Documents/repos/Docs/architecture/security.md#L22) and [`339-342`](/Users/btw/Documents/repos/Docs/architecture/security.md#L339-L342).

- **Smallest concrete fix:**
  1. Add the TPM driver and key service to the boot-image list in `memory.md:67` and `security.md:123` (or document that the TPM driver + key service reside as plain blobs verified inside the `System` zone hash before `Device`/`User` mount).
  2. Authenticate every compiled-code entry in `Cache` with an HMAC/AEAD key sealed to the TPM / `Device` zone (or bind its Merkle root into the `Device`/`User` encrypted SQLite database), and scope the `security.md:27` Merkle guarantee explicitly to blobs (`User`/`Application` zones are encrypted AEAD; extent files carry zone encryption only until post-alpha CoW checksums).
  3. Clarify whether shared compiled-code physical pages are permitted across publishers (`memory.md:22`, accepting Flush+Reload on code fetch) or must be duplicated per publisher to honor [`security.md:22`](/Users/btw/Documents/repos/Docs/architecture/security.md#L22).

---

### Finding 4: Pre-session TPM sealing of `Device` zone has no anti-brute-force PIN and no anti-rollback against older signed images

- **Category:** `contradiction` / `breaks a guarantee`
- **Severity:** High
- **Verbatim quotes:**
  - [`security.md:54`](/Users/btw/Documents/repos/Docs/architecture/security.md#L54):
    > "The disk key is sealed in the TPM (Intel fTPM of the desktop) against the signing key of the system and not against its hash, so that an update does not break unlocking. The user's code is protected by the TPM's anti-brute-force mechanism."
  - [`security.md:105`](/Users/btw/Documents/repos/Docs/architecture/security.md#L105):
    > "| Thief with the machine, off or locked | Read the disk, boot other media, try codes, speak to the machine | User and device zones encrypted, disk key sealed in the TPM with its anti-brute-force mechanism"
  - [`storage.md:49`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L49):
    > "| Device | Pairing keys, networks, hardware settings | Machine, available before the session | Yes, TPM key | No | Until factory reset |"
  - [`platform.md:113-119`](/Users/btw/Documents/repos/Docs/architecture/platform.md#L113-L119):
    > "Headless server image ... Administration: no remote root shell."

- **Concrete scenarios:**
  1. **No user-code / DA protection on `Device` zone (or unattended servers):** In TPM 2.0, dictionary-attack (`DA`) lockout protects `TPM2_PolicyAuthValue` / `authValue` verification (the user's login code), **not** unattended keys unsealed before login. Because the `Device` zone (`pairing keys, networks, hardware settings`, `storage.md:49`) is `"available before the session"` (and headless servers boot without a user session), its TPM key cannot bind the user's code—only Secure Boot PCRs (`PCR 7` / `TPM2_PolicyAuthorize`). Neither [`security.md:54`](/Users/btw/Documents/repos/Docs/architecture/security.md#L54) nor `46` specifies how the `Device` key is bound (which PCRs—e.g. `PCR 0, 2, 4, 7`—or `TPM2_PolicyAuthorize`) vs the `User` key, nor requires TPM parameter-encrypted sessions (`TPM2_StartAuthSession` AES/XOR) so the unsealed disk key or user code is not sent in cleartext over LPC/SPI to a discrete TPM (or vulnerable fTPM interface).
  2. **Rollback to an older project-signed image (`security.md:54, 108`):** Sealing against `"the signing key of the system and not against its hash"` (`54`) omits **TPM NV monotonic counter / security version number (`TPM2_PolicyNV`)** and UEFI `dbx` revocation. Even if `security.md:108` relies on `A/B/R rollback` at update time, a `Thief` with brief disk/EFI-partition write access (or booting an older recovery/installer USB signed by the same project key before its key rotates) boots any historical project-signed image with a known vulnerability (e.g., an image with a console or debugger stub enabled, or a historical kernel bug) and the TPM happily unseals the `Device` disk key—extracting Wi-Fi PSKs and circle device pairing keys ([`devices.md:15-18`](/Users/btw/Documents/repos/Docs/architecture/devices.md#L15-L18)).

- **Smallest concrete fix:** Split the TPM model explicitly in [`security.md:54`](/Users/btw/Documents/repos/Docs/architecture/security.md#L54): (a) bind the `User` key with `PolicyAuthorize` (project signing key + minimum security version `PolicyNV`) **AND** `PolicyAuthValue` (user PIN under TPM DA lockout) using encrypted TPM sessions; (b) bind the pre-session `Device` key with `PCR 7` + `PolicyAuthorize` + a monotonic NV version counter bumped on security updates (and document that unattended `Device` secrets are protected against offline disk reading only insofar as Secure Boot + firmware stay uncompromised).

---

### Finding 5: Unspecified verification of hot kernel replacement (`kernel image 1`), unencrypted crash partition / cross-node crash-area leakage, and misclassified syscall code page

- **Category:** `breaks a guarantee` / `unsettled case` / `contradiction`
- **Severity:** High
- **Verbatim quotes:**
  - [`security.md:27, 29, 91`](/Users/btw/Documents/repos/Docs/architecture/security.md#L27):
    > "Firmware, then the signed boot image, then the system, which is a hash. Every blob is verified on read by its Merkle tree: at reboot, the machine is exactly that hash." ... "System calls are accepted only from the kernel-supplied code page (see [kernel.md](kernel.md#base-decisions))."
  - [`kernel.md:195`](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L195):
    > "a kernel update without a reboot, by `node_stop` mode seal and `node_start` mode resume with the replacement image, on the same cores"
  - [`kernel-interface.md:1330, 1344-1346, 1941`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1330):
    > "Kernel image 0 is the boot kernel, 1 the replacement slot." ... "**Replacement of a kernel** is `node_stop` mode seal followed by `node_start` mode resume with kernel image 1." ... "The kernel keeps: its image and the slot for a replacement image (the code page included)"
  - [`kernel-interface.md:1464-1465, 1477-1479, 1487, 1497-1504`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1464):
    > "It is kept memory, in no untyped, never cleared during the boot. The first stage keeps two crash areas, A and B: one is the area of this boot; the other holds what the previous boot wrote and is kept untouched for the whole boot" ... "`task identifier`, `effective marks`, `text of debug_write (24 bytes)`" ... "**How user space reads them:** through the kept frame of the current crash area, in every start-up space (`read` and `derive` only). Whoever holds it reads every core's rings and records, without a call, whether the writer is alive or not."
  - [`storage.md:38`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L38):
    > "2. The store, which carries everything else, plus a small raw region for the crash trace."
  - [`kernel-interface.md:423`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L423):
    > "| bad call | 6 | a system call instruction outside the kernel-supplied code page |"

- **Concrete scenarios:**
  1. **Unverified hot kernel replacement (`breaks a guarantee` / `unsettled case`):** [`security.md:27`](/Users/btw/Documents/repos/Docs/architecture/security.md#L27) restricts verification to `"Firmware, then the signed boot image, then the system ... at reboot"`. Meanwhile, [`kernel-interface.md:1330, 1346`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1330) keeps `kernel image 1` (`the replacement slot`) for live kernel updates without reboot. Neither `security.md` nor `kernel-interface.md` defines which user-space service may populate `kernel image 1`, how its signature against the project signing key (or user-enrolled key) is checked before `node_start` mode `resume`, or whether `TPM` PCRs/attestation reflect the hot-replaced kernel.
  2. **Crash-record confidentiality leak across boots, nodes, and raw disk (`breaks a guarantee`):** First, [`storage.md:38`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L38) puts crash traces in `"a small raw region"` outside encrypted `User` and `Device` zones (`storage.md:49-50`), while [`platform.md:64`](/Users/btw/Documents/repos/Docs/architecture/platform.md#L64) says crashes skip user cleanup—exposing unencrypted fault addresses, task IDs, marks, and up to 512 bytes per `debug_write` entry (`kernel-interface.md:1477-1518`) to a `Thief`. Second, [`kernel-interface.md:1487`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1487) places a `read`+`derive` capability to the **entire crash area (all cores, all nodes)** in **every** node's start-up space (`Slot` table), and [`1465`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1465) leaves the previous boot's crash area readable in kept memory for the entire boot. If a node's first service delegates or belongs to a non-system publisher, it can read another node's `task identifier`, `effective marks`, fault addresses, and `debug_write` strings—bypassing inter-node isolation and `marks` secrecy.
  3. **Syscall code page treated as Chain of Trust (`contradiction`):** Listing `"System calls are accepted only from the kernel-supplied code page"` under **Chain of trust** ([`security.md:29`](/Users/btw/Documents/repos/Docs/architecture/security.md#L29)) implies security enforcement, whereas [`kernel-interface.md:423`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L423) checks only whether RIP/PC lies inside that read-execute page (which any process can jump/ROP into, including a JITed Web process or compromised native driver). It is an ABI stability indirection (`D-005`), not a chain-of-trust gate.

- **Smallest concrete fix:**
  1. Specify the hot-replacement authority and signature verification path for `kernel image 1` (e.g., an update service or supervisor passes a TUF-verified kernel image; the kernel or supervisor checks the signature against the enrolled keys before writing `kernel image 1`).
  2. Move persisted crash traces inside an encrypted zone (`Device` or `User`) rather than an unencrypted raw disk region, clear or wipe sensitive previous-boot crash RAM once ingested by the log service, and restrict the kept crash-area frame capability (`kernel-interface.md:1487`) to the privileged log/supervisor service rather than every node's unprivileged first service.
  3. Move [`security.md:29`](/Users/btw/Documents/repos/Docs/architecture/security.md#L29) out of `Chain of trust` (cross-reference `wasm-abi.md#abi-stability` as an ABI measure, not a security guarantee).

---

### Finding 6: Omitted peripheral attack — malicious USB/Bluetooth mouse, touchscreen, or composite HID bypasses confirmations and lock-screen BadUSB defense

- **Category:** `breaks a guarantee` / `unsettled case`
- **Severity:** High
- **Verbatim quotes:**
  - [`security.md:106`](/Users/btw/Documents/repos/Docs/architecture/security.md#L106):
    > "| Hostile peripheral (USB, PCIe, Thunderbolt; Bluetooth after the alpha) | DMA, interrupts, malformed descriptors aimed at a driver, act as a keyboard, present hostile storage | ... **Not stopped**: a device that types as a keyboard ([point 12](#points-for-the-two-owners)) |"
  - [`security.md:214-215`](/Users/btw/Documents/repos/Docs/architecture/security.md#L214-L215):
    > "- **Answered only by a gesture on it**: a click or a touch on the confirmation, or a key while it holds the focus, which the compositor owns."
    > "- **Not answerable by accident**: its buttons ignore input for a short time after it appears (starting value 500 ms, to calibrate), and it never appears under the pointer."
  - [`security.md:327`](/Users/btw/Documents/repos/Docs/architecture/security.md#L327):
    > "12. **A device that types as a keyboard is the user.** Recommended: a newly connected keyboard is accepted after a key press on a keyboard already accepted, or at the lock screen. Alternative: accept every keyboard, as other systems do."
  - [`ui.md:108`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L108):
    > "**Chain.** Linux drivers (USB HID, I2C HID) that produce evdev events; libinput, ported, for the touchpad and gestures ... xkbcommon for keyboard layouts."

- **Concrete scenarios:**
  1. **Malicious mouse / touchscreen / composite HID defeats Point 12 and confirms actions:** Both [`security.md:106`](/Users/btw/Documents/repos/Docs/architecture/security.md#L106) and Point 12 (`327`) guard only `"a device that types as a keyboard"`. A malicious USB device (e.g., BadUSB charger or poisoned flash drive) that enumerates as a **USB HID mouse, absolute-coordinate digitizer/touchscreen, or composite storage+pointer** is accepted unconditionally. Under [`security.md:214-215`](/Users/btw/Documents/repos/Docs/architecture/security.md#L214-L215), it opens the agent bar via click/touch, uses an on-screen virtual keyboard (`ui.md:110`: `"The virtual keyboard ... go[es] through the same protocol"`) or pointer clicks to issue or confirm requests, waits 500 ms when any confirmation dialog appears, and sends an absolute touch or relative sweep + left click onto the `Confirm` button.
  2. **Lock-screen BadUSB pre-enrollment:** Point 12's own recommended rule accepts a newly connected keyboard `"at the lock screen"` (`327`). A `Thief` or passerby with 2 seconds of physical access to an unattended **locked** machine plugs in a BadUSB dongle while the lock screen is showing; the OS pre-accepts it on connection, so the instant the legitimate user unlocks the desktop (or wakes the screen), the rogue device already holds full trusted `user`-origin keyboard authority! (And while on the lock screen, it can brute-force PINs up to TPM DA lockout or trigger `wake word` / lock-screen actions.)

- **Smallest concrete fix:** Extend Point 12 ([`security.md:106, 327`](/Users/btw/Documents/repos/Docs/architecture/security.md#L327)) to **all new HID input devices** (mice, touchpads, touchscreens, gamepads, and composite USB interfaces containing HID), and remove `"or at the lock screen"`—requiring confirmation on an already-accepted input device (or explicit on-screen unlock-time approval tied to a physical port/device descriptor **after** authentication, never auto-accepting hot-plugged HID devices while locked).

---

### Finding 7: Omitted browser-engine shared processes, `LibJS` web-app capabilities, and conflation of "site" vs "origin"

- **Category:** `contradiction` / `unsettled case`
- **Severity:** High
- **Verbatim quotes:**
  - [`security.md:22, 101`](/Users/btw/Documents/repos/Docs/architecture/security.md#L101):
    > "| Process | Publishers. One process per publisher (or per web site), never two publishers in the same address space, because of Spectre-type side channels | One IPC |" ... "| Hostile web page | ... One process per site ([Three boundaries](#three-boundaries)); a site exports no actions and gets no WIT interface ([web.md](web.md#web-content-and-capabilities), Aligned); what the agent reads from it carries the origin `web:<origin>` and marks the task `untrusted` (D-035). The JIT of the content process is Open ([web.md](web.md#jit-in-the-web-content-process)) |"
  - [`web.md:22-25, 36-41`](/Users/btw/Documents/repos/Docs/architecture/web.md#L22-L25):
    > "49 vcpkg dependencies on mlibc ... the Rust crates: Ladybird has about thirty (LibJS, its JIT, the CSS engine, the core of the Compositor, LibWasm); an AudioServer back end, the sandbox, fonts without Fontconfig, and RequestServer (curl) on the project's network stack. The Hub process, without Qt since PR 14109, is the control junction."
    > "## Web applications
    > - The WIT interfaces granted by the manifest appear as ES modules (`import { open } from "os:core/store"`) ...
    > - This is reserved for signed packages, never for ordinary sites.
    > - JS and TS of web applications run on LibJS."
  - [`security.md:28`](/Users/btw/Documents/repos/Docs/architecture/security.md#L28):
    > "Only the compile service produces machine code ... The only exception under discussion is the JIT of the web process (**Open**; see [web.md](web.md#jit-in-the-web-content-process))."

- **Concrete scenario & gaps:**
  1. **Unmodeled shared browser processes (`breaks a guarantee` / `unsettled case`):** [`security.md:101`](/Users/btw/Documents/repos/Docs/architecture/security.md#L101) portrays the browser as purely `"One process per site"`, omitting Ladybird's multi-site shared processes explicitly required by [`web.md:23, 25`](/Users/btw/Documents/repos/Docs/architecture/web.md#L23): **`RequestServer (curl)`** (which parses HTTP/TLS/headers/redirects and holds cookies/connection pools across sites unless partitioned per process), **`Hub`** (`"the control junction"`), **`AudioServer`**, and the shared **`ImageDecoder`/media codecs** (`49 vcpkg dependencies` in native C/C++). A hostile web page exploiting `RequestServer`, `AudioServer`, or `Hub` crosses the `"One process per site"` boundary and accesses other sites' cookies, network sessions, or UI tabs—yet none of these shared native C++ processes appear in `What is trusted` (`117-134`) or `Adversaries` (`101`).
  2. **Omitted browser-held assets & `site` vs `origin` mismatch (`contradiction` / `unsettled case`):** [`security.md:84-95`](/Users/btw/Documents/repos/Docs/architecture/security.md#L84-L95) does not list browser-specific user assets (`cookies`, `localStorage`/`IndexedDB`, `saved passwords`, and `passkeys` named in [`devices.md:41`](/Users/btw/Documents/repos/Docs/architecture/devices.md#L41)). Moreover, `security.md:22, 101` isolates **per site** (`eTLD+1`, e.g., `github.io`), whereas provenance (`101, 186`) and web security boundaries (SOP, cookies, storage) operate **per origin** (`scheme + host + port`, `web:<origin>`). Putting mutually untrusted subdomains of a hosting platform (`alice.example.io` and `attacker.example.io`) into the same process exposes them to the very Spectre/memory attacks [`security.md:22`](/Users/btw/Documents/repos/Docs/architecture/security.md#L22) promises process separation prevents.
  3. **Signed Web Applications on `LibJS` (`contradiction` / `unsettled case`):** [`web.md:36-40`](/Users/btw/Documents/repos/Docs/architecture/web.md#L36-L40) runs **signed Web applications** with granted WIT capabilities (`os:core/store`, etc.) directly on **`LibJS`**, whereas [`security.md:28`](/Users/btw/Documents/repos/Docs/architecture/security.md#L28) discusses JIT only for `"the web process"` (ordinary sites). If `LibJS` JIT (`web.md:45`) stays enabled inside signed capability-bearing Web applications, a `LibJS` JIT or DOM/HTML parser bug in an app rendering untrusted remote content (e.g., an email viewer or Markdown reader) bypasses the `"no executable page"` guarantee of signed apps.

- **Smallest concrete fix:** (1) List `Hub`, `RequestServer`, and `AudioServer` in `security.md` (either partitioned per site/origin or added to `What is trusted` with strict process sandboxing and explicit cookie/storage isolation); (2) align `security.md:22, 101` on **origin isolation** (`web:<origin>`, respecting `Origin-Agent-Cluster`/public suffix lists) rather than coarse eTLD+1 site isolation; (3) state whether signed Web applications on `LibJS` run with JIT disabled regardless of `P-052`, and add browser site data / passkeys to [`What is protected`](/Users/btw/Documents/repos/Docs/architecture/security.md#L84-L95).

---

### Finding 8: Local model weights omitted as an asset; `llama.cpp` Vulkan path breaches Point 13; agent memory taint sink & trivial self-speech filter bypass

- **Category:** `breaks a guarantee` / `unsettled case`
- **Severity:** High
- **Verbatim quotes:**
  - [`agent.md:11`](/Users/btw/Documents/repos/Docs/architecture/agent.md#L11):
    > "Local inference by llama.cpp (1.0 stable since 13 November 2026), Vulkan back end"
  - [`gpu.md:25, 47, 53`](/Users/btw/Documents/repos/Docs/architecture/gpu.md#L25):
    > "The proprietary GSP firmware is required." ... "The GPU service alone arbitrates GPU time and memory" ... "The weights of a model are mapped blobs, shared between processes."
  - [`security.md:328`](/Users/btw/Documents/repos/Docs/architecture/security.md#L328):
    > "13. **Where inference runs.** llama.cpp is native code that parses third-party model files and reads private data and untrusted content together. Recommended: its own process, with no network and no write to the store"
  - [`storage.md:47`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L47):
    > "| Packages | Blobs and manifests of applications, models | Machine, shared between users | No |"
  - [`security.md:196, 279`](/Users/btw/Documents/repos/Docs/architecture/security.md#L196):
    > "What the agent writes into its memory carries the task's marks, as every store write does; a later task that reads it takes them back." ... "marks die with the task, and each request is a new task"
  - [`agent.md:41`](/Users/btw/Documents/repos/Docs/architecture/agent.md#L41):
    > "Across devices it is an append-only log merged by union"
  - [`security.md:268`](/Users/btw/Documents/repos/Docs/architecture/security.md#L268):
    > "Proposed: the recogniser also drops a request whose text matches what the machine spoke in the last seconds."

- **Concrete scenarios:**
  1. **`llama.cpp` Vulkan / NVK / GSP surface defeats Point 13 isolation (`breaks a guarantee`):** Point 13 (`328`) strips network and store-write from `llama.cpp` to contain native C++ vulnerabilities in GGUF model parsing (`"native code that parses third-party model files"`). However, `agent.md:11` selects the **Vulkan back end**, which compels `llama.cpp` to submit shaders, command buffers, and large mapped memory objects (`gpu.md:53`) through **`GPU service` -> `Mesa NVK` -> `NVIDIA open core` -> proprietary `GSP firmware`** (`gpu.md:22-25`). A malformed GGUF exploiting `llama.cpp` obtains arbitrary Vulkan compute/shader execution against a shared GPU service and closed-source GSP firmware (shared with the compositor and all apps), neither of which is in `What is trusted` (`117-134`)! Moreover, sharing model weight blobs across processes/VRAM (`gpu.md:53`) is unguarded for user-trained/private models placed in unencrypted `Packages` (`storage.md:47`) or `Cache`, and local model weights are missing from `What is protected` (`84-95`).
  2. **Agent memory creates a permanent global taint sink (`breaks a guarantee` / `contradiction`):** Under [`security.md:196`](/Users/btw/Documents/repos/Docs/architecture/security.md#L196) and [`agent.md:41`](/Users/btw/Documents/repos/Docs/architecture/agent.md#L41), every fact written to the agent's append-only memory during a task inherits that task's marks (`private` and/or `untrusted`), and any future task reading agent memory inherits them back (`"takes them back"`). Once the agent saves *any* note while `untrusted` (e.g., summarizing a meeting from an email) and later tasks retrieve memory (as default context or RAG), **every subsequent task becomes permanently `untrusted`**, defeating `"marks die with the task"` ([`279`](/Users/btw/Documents/repos/Docs/architecture/security.md#L279)) and also allowing an untrusted/poisoned write into memory to persist cross-task instructions (`CaMeL` §3 explicitly notes memory must remain uncompromised).
  3. **Self-speech filter bypass (`breaks a guarantee`):** [`security.md:268`](/Users/btw/Documents/repos/Docs/architecture/security.md#L268) drops spoken requests `"whose text matches what the machine spoke in the last seconds"`. A malicious webpage video or screen-reader text (`270`) simply prefixes or appends one harmless word (`"Oh, Hey Dodo, open ..."` vs exact match, or splits phrases across `N+1` seconds) so the recognized transcript no longer `"matches"`, triggering a `user`-origin agent task from machine audio whenever echo cancellation leaves residual leakage.

- **Smallest concrete fix:** (1) Add `GPU service` + `NVK` + proprietary `GSP firmware` to `What is trusted` (or `Out of scope` for GSP firmware bugs), place untrusted/third-party GGUF parsing in a separate Wasm/no-GPU validator process before passing verified tensor descriptors to `llama.cpp`, and move private/custom model weights to `User` zone; (2) prohibit writing to persistent agent memory when marked `untrusted` (or isolate untrusted memory entries so they are never auto-injected into fresh tasks without explicit user read/confirmation); (3) treat exact-string self-speech suppression (`268`) as non-blocking defense-in-depth and rely on audio-output ducking / no automatic non-local effects rather than text equality.

---

### Finding 9: Build/CI/dependency supply chain and the two owners' own development agents are omitted from the threat model

- **Category:** `unsettled case` / `contradiction`
- **Severity:** High
- **Verbatim quotes:**
  - [`security.md:97-110, 148`](/Users/btw/Documents/repos/Docs/architecture/security.md#L108):
    > "`Hostile update | A package signed by a compromised publisher key; a system image`" ... "`A malicious project signing threshold, or a publisher against its own packages | They are on the trusted list`"
  - [`plan/verification.md:24-25, 35, 39, 94-95`](/Users/btw/Documents/repos/Docs/plan/verification.md#L39):
    > "`Proposed.` The CI first proposed was judged insufficient once; this list awaits a review (**Open**)."
    > "`Base, all repositories | Format and lint; reproducible build (two builds, same bytes); tests; supply chain (cargo-deny, cargo-vet, GitHub actions pinned by SHA, no secret for an unreviewed PR)`"
    > "`Function | ... the merge is automatic once the checks and that review pass (Decided, 14 November 2026)`"
    > "`Maintenance | Dependencies, documentation | Direct PR | Merges alone when the checks pass (Decided, 14 November 2026)`"
  - [`plan/pending-decisions.md:30, 1254-1258`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L1254):
    > "`the merge queue waits for the transfer to an organisation, which the owner will create`" ... "`none of the three repositories has [branch protection, CODEOWNERS, and a merge queue] on 16 November 2026 (the inventory checked the GitHub settings). ... Options. A. Now. B. When outside contributors arrive. Costs: until then an agent can merge into the contract lane.`"
  - [`web.md:21`](/Users/btw/Documents/repos/Docs/architecture/web.md#L21):
    > "49 vcpkg dependencies on mlibc ... Rust crates: Ladybird has about thirty"

- **Concrete scenarios:**
  1. **Supply chain & CI bypasses via Maintenance / Function lanes:** [`security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md) treats shipped system images, trust roots (`network.md:25`), `llama.cpp`, Ladybird (`49 vcpkg ports`), Linux LTS drivers, and the NVIDIA GSP binary as uncompromised once signed by the project threshold (`108, 121-132`). Yet in [`plan/verification.md:94-95`](/Users/btw/Documents/repos/Docs/plan/verification.md#L95), **Maintenance-lane PRs (`Dependencies, documentation`) merge automatically with zero human or cross-family review**, and **Function-lane PRs auto-merge** on an AI review + human sample—while the `Base` supply-chain checks (`cargo-vet`, `cargo-deny`, SHA-pinned actions) are still **`Proposed`/`Open`** (`verification.md:35`) and there is no `vcpkg`/C++ upstream attestation or proprietary-firmware hash pinning mentioned anywhere.
  2. **The two owners' own development/review agents as an adversary:** Under [`verification.md:104-131`](/Users/btw/Documents/repos/Docs/plan/verification.md#L128), development agents work inside worktrees, read untrusted external web research/repos/kernel sources (`D-023`, `verification.md:135`), and can commit/push code (and as of 16 Nov 2026, `pending-decisions.md:1256` confirms branch protection/`CODEOWNERS`/merge queue are not enabled yet on GitHub). A prompt injection in an upstream issue, PR, vcpkg port, or external kernel file read by a coding/review agent (`verification.md:135`)—or a colluding/buggy model updating a dependency (`Maintenance`) or relaxing a check—can land malicious code on `main` that gets signed into the next release image if `reproducible build` + signed provenance + `cargo-vet` are not treated as load-bearing boundaries in `security.md`.

- **Smallest concrete fix:** Add **Compromised build/dependency/agent pipeline** to `Adversaries` and **Signed build provenance / SBOM / reproducible build inputs** to `What is protected` in [`security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md), explicitly requiring that: (1) `D-032`/`D-084` auto-merge cannot trigger before `P-086` (`CODEOWNERS`, branch protection, merge queue) and `verification.md:39` supply-chain checks (`cargo-vet`, SHA-pinned actions, reproducible builds, pinned upstream digests for `vcpkg`, Linux LTS, Ladybird, and NVIDIA GSP) are active; and (2) `Maintenance` PRs altering `Cargo.lock`, `vcpkg`, Nix pins, or build scripts require human or cross-family review rather than merging alone.

---

### Finding 10: Omitted physical-access exposures (unencrypted `Packages`, pre-boot DMA, devices not reset at shutdown, installer/debug port)

- **Category:** `unsettled case` / `breaks a guarantee`
- **Severity:** Medium
- **Verbatim quotes:**
  - [`security.md:105`](/Users/btw/Documents/repos/Docs/architecture/security.md#L105):
    > "| Thief with the machine, off or locked | Read the disk, boot other media, try codes, speak to the machine | User and device zones encrypted, disk key sealed in the TPM ... Advanced physical attacks are out of scope |"
  - [`storage.md:47, 54`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L47):
    > "| Packages | Blobs and manifests of applications, models | Machine, shared between users | No |" ... "| Foreign | USB sticks, disks of other systems, network shares | Seen as a collection, through a reader component | Depends on the medium |"
  - [`kernel-interface.md:1932`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1932):
    > "2. turns every IOMMU unit on in blocking mode, programs the remapping table"
  - [`platform.md:21, 64, 70, 83`](/Users/btw/Documents/repos/Docs/architecture/platform.md#L21):
    > "Devices are reset at boot, not at shutdown." ... "kernel debugger through the USB debug port. The kernel debugger is a stub of development images" ... "Installer: the USB image is the system in an ephemeral session"

- **Concrete scenarios:**
  1. **Pre-boot DMA before kernel step 2:** [`security.md:106`](/Users/btw/Documents/repos/Docs/architecture/security.md#L106) relies on `"IOMMU active before the first driver"`, which the kernel enables at startup step 2 ([`kernel-interface.md:1932`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1932)). Between power-on / sleep wake (`s2idle` / S3 on laptops, `platform.md:75`) and step 2, UEFI Option ROMs or Thunderbolt/PCIe hot-plug devices can DMA unless firmware Pre-Boot DMA Protection (Kernel DMA Protection / VT-d `DMAR` pre-boot flags) is required and verified.
  2. **Unencrypted `Packages` metadata & shutdown residue:** Unencrypted `Packages` (`storage.md:47`) leaks the full inventory of installed applications and local models (contrary to `"Read the disk"` protection in `105`), and `"Devices are reset at boot, not at shutdown"` (`platform.md:21`) leaves GPU VRAM, audio/USB/network device buffers, or NIC wake-on-LAN state uncleared when powered down or suspended if an attacker extracts peripherals/drives or boots other media (`security.md:105`). Meanwhile, `platform.md:83` runs an unauthenticated USB installer ephemeral session with full hardware access (where USB installer persistence or unencrypted `Foreign` media parsing is left out of `security.md`).

- **Smallest concrete fix:** Document in [`security.md:105`](/Users/btw/Documents/repos/Docs/architecture/security.md#L105) that: (a) installed application names and models in `Packages` are **not** confidential against physical disk inspection (unless installed privately in `User`, `P-060`); (b) firmware Pre-Boot DMA Protection must be enabled and verified before handing over to the kernel (and Thunderbolt external ports disabled/untrusted pre-session); and (c) shutdown/sleep must scrub or reset sensitive device memory (especially GPU VRAM holding inference context/display frames) rather than deferring all device resets to boot (`platform.md:21`).

---

### Finding 11: False external citation — CaMeL has no Section 9.2 (de-classification and user fatigue is Section 8.2)

- **Category:** `wrong fact`
- **Severity:** Medium
- **Verbatim quote:**
  - [`security.md:276`](/Users/btw/Documents/repos/Docs/architecture/security.md#L276):
    > "**1. Everything quickly becomes "untrusted" and the user confirms everything.** RTBAS names it "label creep" and notes that confirming every tool call leads to fatigue, to "mindlessly approving problematic requests or abandoning the system entirely" (section 1); CaMeL calls it user fatigue and does not solve it (section 9.2); FIDES names "confirmation fatigue and social engineering" (section 1)."
- **Primary-source verification (`arXiv:2503.18813v1`):**
  - Section 9 of Debenedetti et al., *Defeating Prompt Injections by Design* (CaMeL, [`arXiv:2503.18813v1`](https://arxiv.org/html/2503.18813v1)) is `## 9 Future work` and has **no subsections** (its three unnumbered paragraphs cover "Using a different programming language", "Towards Formal Verification", and "Contextual Integrity").
  - The discussion of de-classification and user fatigue is **`### 8.2 De-classification and user fatigue`**: *"This can lead to user fatigue, where users become desensitized to security prompts and may inadvertently approve malicious actions..."*.
  - *(Note: The RTBAS §1 quote and FIDES §1 phrase match their respective sources verbatim.)*

- **Smallest concrete fix:** Change `(section 9.2)` in [`security.md:276`](/Users/btw/Documents/repos/Docs/architecture/security.md#L276) to `(section 8.2)`.

---

### Finding 12: External technical assumptions unverified or misstated (Wasmtime Spectre defaults & Winch, Microsoft UEFI signing under AGPLv3, VT-d DMAR `RMRR`/`SATC`)

- **Category:** `wrong fact` / `unsettled case` / `blocks building`
- **Severity:** Medium
- **Verbatim quotes:**
  - [`security.md:340`](/Users/btw/Documents/repos/Docs/architecture/security.md#L340):
    > "- The Spectre protections of Wasmtime are active."
  - [`wasm-abi.md:95`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md#L95) & [`memory.md:33`](/Users/btw/Documents/repos/Docs/architecture/memory.md#L33):
    > "Launch without installing: the baseline compiler Winch, almost instant." ... "A Wasm memory reserves its virtual space with guard pages, which removes bounds checks. This holds for 32-bit memories only (**Decided**)."
  - [`security.md:58-60`](/Users/btw/Documents/repos/Docs/architecture/security.md#L58-L60):
    > "For machines where this is not possible, an intermediate loader signed by Microsoft, later." ... "A Microsoft-signed loader for a non-Linux OS is not verified."
  - [`kernel-interface.md:1931, 2113`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1931):
    > "reads the MADT and the DMAR (x86-64" ... "and no other (D-110, validated by D-112 as an exception to D-054)"

- **Primary-source verification & concrete defects:**
  1. **Wasmtime Spectre protections (`security.md:340`):** Official Wasmtime security documentation ([`docs.wasmtime.dev/security.html#spectre`](https://docs.wasmtime.dev/security.html#spectre)) explicitly states: (i) on **`aarch64`, `csdb` is disabled by default** (`use_csdb` off due to performance penalty), so ARM64 Spectre table/branch mitigations are **not** active out of the box unless explicitly configured; (ii) in Wasmtime's default virtual-memory guard-page mode (`memory.md:33`), **bounds checks are omitted on 32-bit memories**, so Cranelift inserts `enable_heap_access_spectre_mitigation` *only* when dynamic bounds checks are enabled (`"memory64"` or guard-less configurations); and (iii) [`wasm-abi.md:95`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md#L95) uses **Winch** for launch-without-installing, whereas Wasmtime's published Spectre docs document **Cranelift** mitigations (Winch's completeness across `call_indirect`/`br_table` speculative barriers is not established in `security.md`).
  2. **Microsoft UEFI signing vs AGPLv3 (`security.md:58-60`, `D-014`, `D-125`):** Microsoft's UEFI Signing Requirements (updated October 2025; CA 2011 expired June 2026) enforce strict license exclusions prohibiting **GPLv3 / AGPLv3** code (`D-014` licenses DodOS kernel+system under dual **AGPLv3** and commercial!) from Microsoft UEFI signing, and `rhboot/shim-review` requires a permissive BSD-licensed `shim` whose next-stage loader verifies Linux/PE images. Shipping a single combined AGPLv3 EFI binary (`D-125`) cannot obtain a Microsoft signature, and keeping `P-056` Option B open without isolating a small permissive BSD/Apache-2.0 first-stage verifier risks designing a non-signable boot layout.
  3. **Intel VT-d DMAR `RMRR` & `SATC` (`kernel-interface.md:1931`, `drivers.md:57`):** Relying on the DMAR table alone (`1931`) must handle **`RMRR`** (Reserved Memory Region Reporting, Type 1 structures required by legacy USB/BMC/firmware DMA even when IOMMU blocking is enabled) and **`SATC`** (SoC Integrated Address Translation Cache, Type 5, marking devices whose ATS `ATC_REQUIRED` bit prevents blocking/disabling ATS on newer Intel silicon)—ignoring `RMRR` breaks USB/platform boot or ignoring `SATC` leaves integrated ATS devices misconfigured.

- **Smallest concrete fix:** (1) Require `use_csdb` explicitly for ARM64 in Wasmtime config and verify whether Winch emits equivalent `call_indirect`/`br_table` Spectre fences before trusting Winch on untrusted Wasm (`wasm-abi.md:95`), clarifying in `security.md:340` which Spectre mitigations apply in guard-page vs bounds-checked modes; (2) note the AGPLv3 (`D-014`) Microsoft UEFI exclusion under [`security.md:58-60`](/Users/btw/Documents/repos/Docs/architecture/security.md#L58-L60) so any future `shim` uses a permissive license separate from the AGPLv3 kernel; (3) specify explicit parsing/rejection or identity-mapping policy for DMAR `RMRR` and `SATC` entries in [`kernel-interface.md:1931`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1931).

---

### Finding 13: Owner Point 2 directly contradicts and reopens settled decision `D-036`

- **Category:** `contradiction`
- **Severity:** Medium
- **Verbatim quotes:**
  - [`decisions/README.md:46`](/Users/btw/Documents/repos/Docs/decisions/README.md#L46):
    > "| D-036 | 14 November 2026 | The rule "no component combines private data, untrusted content and external communication" targets agent tasks | review | [security.md](../architecture/security.md#security-model-of-the-agent) |"
  - [`security.md:222-224, 317`](/Users/btw/Documents/repos/Docs/architecture/security.md#L222):
    > "**Decided, 14 November 2026** (D-036): no agent task combines private data, untrusted content and external communication." ... "The wording is a [point for the two owners](#points-for-the-two-owners) (point 2)."
    > "2. **The wording of the rule against the three risks.** D-036 says no task combines them; the matrix lets a task combine them with a confirmation of each external or irreversible effect, as Meta's text allows. Recommended wording: "no agent task combines private data, untrusted content and external communication without a confirmation, drawn by the system, of each external or irreversible effect". Alternative: forbid the combination outright, which forbids "summarise this page and mail it to my accountant" in one task."

- **Analysis:** Point 2 (`P-041`) correctly exposes that the decided confirmation matrix of `D-035` (`security.md:200-206`) **already permits** a single task to touch all three corners (reading untrusted content + private data + invoking `mail.send`, gated by confirmation, and even executing `reversible, local` modifications automatically without confirmation—contrary to Meta's Agents Rule of Two, which counts state changes under `[C]`). Keeping `D-036` unchanged contradicts `D-035`'s matrix; therefore Point 2 must be flagged explicitly in `decisions/README.md` as an active **reopen of `D-036`** (just as `D-128` reopened `D-026`). Furthermore, Point 2's recommended wording still differs from Meta's `[C]` on `reversible, local` state changes (which run unconfirmed in `private`+`untrusted` tasks).

- **Smallest concrete fix:** Note explicitly in Point 2 (`security.md:317`) and `P-041` that adopting the recommended wording **amends `D-036`** and explicitly accepts the documented deviation from Meta's Agents Rule of Two for reversible local modifications (`security.md:224`).

---

### Finding 14: Points 1, 3, 4, 6, 7, 13, and 14 omit critical edge cases or real architectural alternatives

- **Category:** `breaks a guarantee` / `unsettled case`
- **Severity:** High
- **Verbatim anchors (`security.md:316-329`):**
  - **Point 1 (`316`, `none, external`):** Recommended `GET` and `HEAD` with no body to declared manifest hosts **still fails** unless paired with two missing constraints: (a) **block or re-mark on HTTP redirects** (`301`/`302`/`307`/`308`)—otherwise `https://declared.example/redir?leak=secret` redirects to `https://evil.example/?leak=secret`, bypassing the declared-host allow-list in `network service`; (b) **deny ambient `home` access** on `none, external` (Finding 1)—otherwise `home` secrets leak into the `GET` URL of an unmarked task without tripping `private`.
  - **Point 3 (`318`, remote vs local model trust):** Point 3 marks only **remote** models `untrusted`, leaving an unmarked task served by a **compromised or backdoored local open-weights model** (`security.md:104`: *"Hostile model or model provider | Everything injected content can do, on every task, from the first token, with no mark set"*) still able to execute automatic matrix cells (`reversible, local` modifications and `none, external` reads carrying `home` data). Option B (trusting a chosen remote provider) also lacks a concrete policy for whether local untrusted model weights downloaded from third parties count as `untrusted`.
  - **Point 4 (`319`, faulty kernel across nodes):** Point 4 says a faulty kernel can drop marks, but [`kernel-interface.md:1127`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1127) shows the receiving kernel trusts **both** `task identifier` and `marks` on cross-node IPC/signals (`node_send`). A faulty kernel can therefore **forge another node's `task identifier`** to impersonate an unmarked task or forge a supervisor/system stamp! Moreover, Option B (ORing every mark of every task on the sending node) still fails to authenticate `task identifier`, and misses the cleaner **Option C**: **forbid cross-node IPC for agent tasks** (every process of an agent task runs inside one multi-core node—already the natural consequence of `D-128` placing each multi-core process in a single node—or reject cross-node messages with `untrusted`+`private` unless sent by a system node).
  - **Point 6 (`321`, always-open wake-word mic):** Presents only permanent discreet indicator vs disabling wake word in settings, omitting **hardware/OS push-to-talk key by default (mic closed at hardware/driver level until the agent key is pressed)** as the primary privacy-preserving default.
  - **Point 7 (`322`, spoken requests while locked):** Allows `"the wake word only opens the lock screen"` (`267`), which wakes the display/machine to ambient noise (`platform.md:77`) and conflicts with `agent.md:11` (`always active`), without evaluating **"wake word disabled while locked"** as an explicit option.
  - **Point 13 (`328`, where inference runs):** Isolating `llama.cpp` from network and store-write omits `agent.md:11`'s **Vulkan back end**, which shares `GPU service`, `NVK`, `VRAM`, and proprietary `GSP firmware` (`gpu.md:25, 53`). Missing option: run untrusted GGUF parsing in a sandboxed Wasm/CPU component before handing validated tensors to Vulkan, or separate/reset GPU contexts between untrusted inference and trusted compositor workloads.
  - **Point 14 (`329`, task scope):** Contrasts only `"every installed app minus exclusions"` (which exposes every app's `home` and actions to a steered model for automatic cells) against `"an LLM router"` (trusted LLM). Missing middle-ground option: **active-context + explicit `@mention` / pinned-app scope** (only active/open surfaces and user-pinned tools enter scope by default).

- **Smallest concrete fix:** Update Points 1, 3, 4, 6, 7, 13, and 14 in [`security.md:316-329`](/Users/btw/Documents/repos/Docs/architecture/security.md#L316-L329) (and their corresponding entries `P-036..P-049` in [`plan/pending-decisions.md`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md)) to include redirect blocking + `home` gating (Point 1), local model weight provenance (Point 3), `task identifier` spoofing + single-node placement requirement (Point 4), push-to-talk default (Point 6), locked wake-word suppression (Point 7), Vulkan/GSP split (Point 13), and active-context default scope (Point 14).

---

### Finding 15: Stale status and missing agent/cross-doc links on `agent.md`, `ui.md`, and `pending-decisions.md`

- **Category:** `contradiction` / `unsettled case`
- **Severity:** Low
- **Verbatim quotes:**
  - [`security.md:128, 228`](/Users/btw/Documents/repos/Docs/architecture/security.md#L128):
    > "8. The system side of tasks: the code that keeps the marks, applies the matrix, stamps provenance, validates the interface tree and builds each confirmation from the action's schema. The documents name no service and no process for it (point 10)."
  - [`ui.md:47`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L47):
    > "The interface tree is validated by the system at each update: kind known and allowed on the surface, props matching the kind, existing parent, actions within the scope of the task, size caps. A rejected update changes nothing."
  - [`security.md:356`](/Users/btw/Documents/repos/Docs/architecture/security.md#L356):
    > "against the files at commit `8bc6509` of the system repository. The files are not edited here: another revision is in progress, and this list is its input."
  - [`plan/pending-decisions.md:9`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L9):
    > "Two sources are not yet on the `main` branch of this repository: the new [security.md](../architecture/security.md) ... (commit `af51cc5` on `origin/main`...) and the Step 0 revision of the WIT contracts in the system repository (pull request 1 of `Vehicoule/DodOS`, branch `step0-contracts`, commit `aab7417`)"

- **Concrete issue:** [`security.md:356`](/Users/btw/Documents/repos/Docs/architecture/security.md#L356) benchmarks the WIT gaps against the pre-revision commit `8bc6509` in `dodos` (while `aab7417` already implemented or tracked `OPEN (owners)` items per `pending-decisions.md:9, 662, 736`), and [`ui.md:47`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L47) still tracks UI tree validation separately (`P-023`) from Point 10 (`P-039`, whether the `task service` owns A2UI/tree validation as well as marks/matrix).

- **Smallest concrete fix:** Cross-link `P-023` (UI tree validation placement) with Point 10 (`P-039`) so owners decide once whether both live in the proposed `task service`, and update `security.md:356`'s commit baseline once the Step 0 PR (`aab7417`) lands.

---

## Angle 1: Guarantee-to-Mechanism Cross-Check

| Guarantee in [`security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md) | Carrying Mechanism in Other Docs | Status / Discrepancy |
|---|---|---|
| No global name / no ambient authority (`5`, `37`) | Capability handles + relative paths ([`wasm-abi.md:21-22`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md#L21), [`kernel.md:5`](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L5)) | **Partial:** `actions.invoke` still gets ambient `home` ([**Finding 1**](#finding-1-shared-home-collection-across-long-lived-app-and-fresh-actionsinvoke-leaks-secrets-on-none-external-and-breaks-fresh-instance-isolation)). |
| Key service, isolated, narrow interface (`11`, `89`, `129`) | Named only in `security.md`; missing from boot-image services ([`memory.md:67`](/Users/btw/Documents/repos/Docs/architecture/memory.md#L67)) | **Unwired:** No service spec or boot-image slot to unlock `Device`/`User` ([**Finding 3**](#finding-3-boot-image-circular-dependency-for-tpm-unsealing-unverified-compiled-code-in-cache-and-cross-publisher-physical-page-sharing)). |
| Compositor draws indicators & confirmations out of app reach (`13`, `228-236`) | Compositor owns focus/cursor/UI ([`ui.md:17-18, 58, 68`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L17)) | **Broken under direct scanout:** [`ui.md:12`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L12) + [`gates.md:18`](/Users/btw/Documents/repos/Docs/plan/gates.md#L18) (`0 frame added`) omit disabling scanout ([**Finding 2**](#finding-2-direct-scanout-contradicts-compositor-drawn-confirmations-indicators-card-frames-and-the-secure-attention-overlay)). |
| Wasm component stops third-party libraries (`21`, `115`) | Component Model & WIT ([`wasm-abi.md:5-9, 92`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md#L5)) | **OK** for Wasm apps; N/A to native C++ `RequestServer`, `llama.cpp`, drivers. |
| One process per publisher / web site, never two in same address space (`22`, `101`, `339`) | Process isolation; SMT idle ([`scheduling.md:71`](/Users/btw/Documents/repos/Docs/architecture/scheduling.md#L71), [`web.md:33`](/Users/btw/Documents/repos/Docs/architecture/web.md#L33)) | **Contradiction:** Shared page cache maps compiled code by hash across processes ([`memory.md:21-22`](/Users/btw/Documents/repos/Docs/architecture/memory.md#L21), [`storage.md:68`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L68)); shared browser processes ([`web.md:23, 25`](/Users/btw/Documents/repos/Docs/architecture/web.md#L23)) ([**Findings 3, 7**](#finding-3-boot-image-circular-dependency-for-tpm-unsealing-unverified-compiled-code-in-cache-and-cross-publisher-physical-page-sharing)). |
| IOMMU domain per driver before first driver; interrupt remapping (`23`, `106`) | `iospace` capability + `iommu_*` gate calls ([`drivers.md:50-58`](/Users/btw/Documents/repos/Docs/architecture/drivers.md#L50), [`kernel-interface.md:1932`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1932)) | **Gap:** Pre-boot DMA before step 2 unaddressed; DMAR `RMRR`/`SATC` missing ([**Findings 10, 12**](#finding-10-omitted-physical-access-exposures-unencrypted-packages-pre-boot-dma-devices-not-reset-at-shutdown-installerdebug-port)). |
| Every blob verified by Merkle tree; machine = hash at reboot (`27`, `91`) | Blob Merkle trees ([`storage.md:13`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L13)); kept image SHA-256 ([`kernel-interface.md:1926`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1926)) | **Broken:** `Cache` compiled code & `simple extent files` unverified; hot `kernel image 1` unverified ([**Findings 3, 5**](#finding-3-boot-image-circular-dependency-for-tpm-unsealing-unverified-compiled-code-in-cache-and-cross-publisher-physical-page-sharing)). |
| Only compile service makes machine code; no executable pages (`28`) | Compile service ([`wasm-abi.md:92-101`](/Users/btw/Documents/repos/Docs/architecture/wasm-abi.md#L92)); W^X (`memory.md:62`); web JIT **Open** ([`web.md:45`](/Users/btw/Documents/repos/Docs/architecture/web.md#L45)) | **Gap:** Signed Web apps on `LibJS` ([`web.md:36-40`](/Users/btw/Documents/repos/Docs/architecture/web.md#L36)) unclarified wrt JIT ([**Finding 7**](#finding-7-omitted-browser-engine-shared-processes-libjs-web-app-capabilities-and-conflation-of-site-vs-origin)). |
| Syscalls only from kernel code page (`29`) | Entry RIP check -> fault kind 6 ([`kernel.md:15`](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L15), [`kernel-interface.md:423`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L423)) | **Misclassified:** Enforces ABI indirection (`D-005`), not security isolation ([**Finding 5**](#finding-5-unspecified-verification-of-hot-kernel-replacement-kernel-image-1-unencrypted-crash-partition--cross-node-crash-area-leakage-and-misclassified-syscall-code-page)). |
| Write gate bounds faulty kernel (`30`, `107`, `115`) | Rules G1-G14, XED/AARCHMRS scan ([`kernel.md:90, 122-164`](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L90)) | **Gap:** Faulty kernel can spoof `task identifier` & `marks` on `node_send` ([**Finding 14**](#finding-14-points-1-3-4-6-7-13-and-14-omit-critical-edge-cases-or-real-architectural-alternatives)); `PKS` on i5-14600KF & `WRSSQ` page walks unmeasured. |
| Console only if declared, no addresses/contents (`30`, D-118) | Console flag & fixed messages ([`kernel-interface.md:1561, 1910`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1561)) | **Gap:** Crash area & raw crash partition expose task/fault data ([**Finding 5**](#finding-5-unspecified-verification-of-hot-kernel-replacement-kernel-image-1-unencrypted-crash-partition--cross-node-crash-area-leakage-and-misclassified-syscall-code-page)). |
| Debugging = capability per component; dev key for stub (`40`) | `debug` capability & `thread_read/write_regs` ([`kernel-interface.md:1588-1600`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1588)) | **OK** for thread caps; kept crash frame in every start-up space leaks traces ([**Finding 5**](#finding-5-unspecified-verification-of-hot-kernel-replacement-kernel-image-1-unencrypted-crash-partition--cross-node-crash-area-leakage-and-misclassified-syscall-code-page)). |
| User/device zones encrypted; TPM key w/ anti-brute-force (`54`, `105`) | Zones ([`storage.md:49-51`](/Users/btw/Documents/repos/Docs/architecture/storage.md#L49)); TPM driver ([`kernel.md:199`](/Users/btw/Documents/repos/Docs/architecture/kernel.md#L199)) | **Broken:** `Device` zone lacks PIN/DA protection & anti-rollback; boot-image cycle ([**Findings 3, 4**](#finding-4-pre-session-tpm-sealing-of-device-zone-has-no-anti-brute-force-pin-and-no-anti-rollback-against-older-signed-images)). |
| Task marks + one-write `task_revoke` (`161`, `186`) | `task` kernel object, sticky/two-way marks ([`kernel-interface.md:1055-1098`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1055)) | **OK** in kernel for single node; breaks on shared `home` & agent memory ([**Findings 1, 8**](#finding-1-shared-home-collection-across-long-lived-app-and-fresh-actionsinvoke-leaks-secrets-on-none-external-and-breaks-fresh-instance-isolation)). |
| Network service replaces firewall; TLS + trust roots (`109`, `130`) | `wasi:http`/`sockets` caps, encrypted DNS ([`network.md:9, 21-25`](/Users/btw/Documents/repos/Docs/architecture/network.md#L9)) | **Gap:** HTTP redirects & `RequestServer` cookie sharing unaddressed ([**Findings 7, 14**](#finding-7-omitted-browser-engine-shared-processes-libjs-web-app-capabilities-and-conflation-of-site-vs-origin)). |
| Only focused surface receives keys; no synthetic input (`102`, `214`) | Input chain + cap model ([`ui.md:108-110`](/Users/btw/Documents/repos/Docs/architecture/ui.md#L108)) | **Gap:** Rogue USB/BT mice & touchscreens bypass keyboard check ([**Finding 6**](#finding-6-omitted-peripheral-attack--malicious-usbbluetooth-mouse-touchscreen-or-composite-hid-bypasses-confirmations-and-lock-screen-badusb-defense)). |

---

## Angle 4: Audit of the 14 Points for the Two Owners (`security.md:316-329`)

| Point (`security.md`) | `pending-decisions.md` | Status | Really Open? / Missing Alternative or Defect |
|---|---|---|---|
| **1.** External `none` class (`316`) | [`P-036`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L658) | Open (`agent.md:31` updated; `actions.wit` `OPEN`) | **Broken recommendation:** Must also block/re-evaluate HTTP redirects off declared hosts and revoke ambient `home` access so unmarked `none, external` cannot exfiltrate `home` via `GET` URLs (**Findings 1, 14**). |
| **2.** Wording of three-risk rule (`317`) | [`P-041`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L720) | **Reopens `D-036`** | **Contradiction:** Directly reopens settled `D-036` (`decisions/README.md:46`) and deviates from Meta's `[C]` by running `reversible, local` changes unconfirmed (**Finding 13**). |
| **3.** Remote model untrusted (`318`) | [`P-037`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L672) | Open (`inference` stub `OPEN`) | **Incomplete:** Leaves poisoned/backdoored *local* weights (`104`) unmarked on automatic cells (`none, external` + `home`), and mixes confidentiality policy with integrity policy (**Finding 14**). |
| **4.** Faulty kernel drops marks (`319`) | [`P-044`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L756) | Open (linked to `P-001`) | **Understated & missing Option C:** A faulty kernel also spoofs **`task identifier`** (`kernel-interface.md:1127`). Missing alternative: forbid agent-task cross-node IPC altogether (**Finding 14**). |
| **5.** Action descriptions untrusted (`320`) | [`P-042`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L732) | Open (`actions.wit` `OPEN`) | **Really open**, well-framed. |
| **6.** Always-on wake-word indicator (`321`) | [`P-047`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L792) | Open | **Missing alternative:** **Off by default / hardware push-to-talk key only** (avoiding permanent dot + `always active` conflict with `agent.md:11`) (**Finding 14**). |
| **7.** Spoken origin `user` (`322`) | [`P-048`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L804) | Open | **Flawed detail:** Allowing wake word to `"open the lock screen"` (`267`) still wakes a locked machine to ambient audio (`platform.md:77`); missing `"disable wake word while locked"` (**Finding 14**). |
| **8.** Confirmations driven by class (`323`) | [`P-045`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L768) | Open | **Really open**, well-framed (paired with `P-050` hold). |
| **9.** Sub-task quarantine deferral (`324`) | [`P-046`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L780) | Open (keeps `D-035` deferral) | **Really open**, aligns with `D-035` post-v1 deferral of per-value labels. |
| **10.** Named task service (`325`) | [`P-039`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L696) | Open (overlaps `P-023`) | **Really open**, should explicitly merge/resolve with `P-023` (where A2UI validation lives, `ui.md:47`) (**Finding 15**). |
| **11.** Capture & camera provenance (`326`) | [`P-043`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L744) | Open | **Really open**, well-framed (requires compositor surface-mark tracking for screenshots/recordings). |
| **12.** Hostile HID / keyboard (`327`) | [`P-049`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L816) | Open | **Broken:** Omits rogue mice, touchscreens, and composite HID (which click `Confirm` after 500 ms), and accepting new keyboards `"at the lock screen"` allows physical BadUSB pre-enrollment while locked (**Finding 6**). |
| **13.** Inference process isolation (`328`) | [`P-038`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L684) | Open (`agent.md:11` Vulkan) | **Incomplete:** `agent.md:11` uses the **Vulkan back end**, which forces `llama.cpp` to speak to shared `GPU service` / `NVK` / proprietary `GSP firmware` (`gpu.md:25, 53`). Missing sandboxed GGUF pre-parser or GPU context isolation (**Findings 8, 14**). |
| **14.** Scope of a new task (`329`) | [`P-040`](/Users/btw/Documents/repos/Docs/plan/pending-decisions.md#L708) | Open | **Missing alternative:** Active/open-surface + explicit user-pinned scope (between `"all installed apps minus exclusions"` and `"trusted LLM router"`) (**Finding 14**). |

---

## Checked and Found Correct

- **WIT contract citations vs `dodos` commit `8bc6509` (`security.md:358-374`):** Checked directly via `git show 8bc6509:contracts/{core,actions,catalog,store}.wit`:
  - `core.wit:50-56` (`principal`), `123-126` (`provenance`), `136-142` (`world service` + `OPEN`), and `194-198` (`handle` + `OPEN`) match.
  - `actions.wit:76-83` (`action-info`), `97-106` (`journal-entry`), `118-135` (`invoke` matrix), `108-152` (`task`/`subtask`), `155-168` (`inference`/`memory`/`audio` stubs) match.
  - `catalog.wit:25`, `32-45` (`icon-name`, with `system` at line `34` and `untrusted` at line `44`), `81-85` (`field` + `secret`) match.
  - `store.wit:202-212` (`exchange` `copy`/`paste` + `OPEN`) matches.
- **External agent security literature (except CaMeL §9.2 in Finding 11):**
  - Simon Willison, *The lethal trifecta for AI agents* (16 Jun 2025) and Meta, *Agents Rule of Two* (31 Oct 2025, `[A]`/`[B]`/`[C]` definitions and exception requiring human-in-the-loop supervision) match [`security.md:222-224`](/Users/btw/Documents/repos/Docs/architecture/security.md#L222).
  - CaMeL (`arXiv:2503.18813v1`): §3 trust assumptions (user prompt & memory), §3.1 text-to-text non-goal and UI provenance highlighting, and §5.4 control-flow/data-flow escalation match [`security.md:144, 193, 283`](/Users/btw/Documents/repos/Docs/architecture/security.md#L144).
  - FIDES (`arXiv:2505.23643v1`): §1 `"confirmation fatigue and social engineering"`, §5.1 variable hiding (`Hide`), and §5.2 quarantined `query_llm` typed extraction (`output="bool"`) match [`security.md:189, 276, 279, 281`](/Users/btw/Documents/repos/Docs/architecture/security.md#L189).
  - RTBAS (`arXiv:2502.08966v1`): §1 `"label creep"` and verbatim `"mindlessly approving problematic requests or abandoning the system entirely"`, plus §7 (`7.1` LM-Judge, `7.2` Attention-Based) match [`security.md:276, 280`](/Users/btw/Documents/repos/Docs/architecture/security.md#L276).
  - IsolateGPT (`arXiv:2403.04960v1`): Appendix `A.2` (`Session permission`) aligns with [`security.md:217, 279`](/Users/btw/Documents/repos/Docs/architecture/security.md#L217).
- **Single-node `task` kernel revocation & mark rules:** Verified in [`kernel-interface.md:1055-1091`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1055-L1091) that `task_revoke` stops threads in one atomic flag write (plus inter-core leave/interrupt bounded by `CORE_ANSWER_NS`) and detaches in bounded steps of 32, and that sticky/two-way capability mark propagation closes shared-writable-frame leaks within one node.
- **`pending-decisions.md` mapping:** Verified `P-035` (`Threat model` sign-off) and `P-036..P-057` map faithfully to [`security.md`](/Users/btw/Documents/repos/Docs/architecture/security.md) (none settled in `D-132`).

---

## Not Checked

- **Winch compiler backend source code for Spectre mitigations:** Only Wasmtime's published [`security.html`](https://docs.wasmtime.dev/security.html) and stability-tiers documentation were verified; Winch's Rust codegen paths for `visit_call_indirect` and `visit_br_table` were not audited line-by-line against Cranelift.
- **Physical CPUID / hardware silicon behavior on the reference Intel Core i5-14600KF:** Bare-metal `CPUID` flags (`PKS`, `CET_SS`, `CET_IBT`) and whether `WRSSQ`-typed page-table pages work cleanly with hardware page-table walks (`Accessed`/`Dirty` bit updates) across P-cores and E-cores remain unverified on hardware (`P-002`, `P-003`).
- **`dodos` branch `step0-contracts` (`aab7417`) diff:** Only `dodos` commit `8bc6509` (matching `security.md:356`) was inspected line-by-line; the newer `aab7417` revision cited in `pending-decisions.md:9` was not audited.
- **Third-party C/C++ port internals (`49 vcpkg` Ladybird dependencies, Mesa `NVK`, `NVIDIA/open-gpu-kernel-modules`, `llama.cpp` GGUF parser):** Specific CVEs or exact memory-safety boundaries inside those upstream codebases were not audited.
