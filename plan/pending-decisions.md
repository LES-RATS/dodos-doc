# Pending decisions

A booklet for the two owners: every question the documents leave open, put so that it can be answered by choosing an option. Written on 16 November 2026 by the assistant, from the documents themselves; the inventory of what is not done (in `research/drafts/`) was used as a list of leads and checked item by item. Nothing here is decided: each entry says what the documents propose, what the assistant recommends, and who must answer.

**How to answer.** Read the table, then answer by a list such as "P-012: A; P-013: as recommended; P-040: B, with this change". An entry marked **measure** is not a decision yet: it says what to measure, on which machine, and which decision waits for the number. The groups are in the order in which the work needs them; inside a group, an entry comes before the entries that depend on it.

**Words used throughout.** A *capability* is an unforgeable, revocable token that grants one right; the kernel acts only on capabilities. A *node* is one running kernel and the cores it runs on. *WIT* is the language of the typed interfaces between components; `os:core` is the DodOS package of those interfaces. A *task* is the unit of delegation of the agent: the rights, the marks and the journal of one request. The two *marks* are `private` (the task has read the user's private data) and `untrusted` (the task has read content that may carry a third party's instructions). The *effect class* of an action has two fields: `change` (none, reversible, irreversible) and `reach` (local, external). The *confirmation matrix* is the table that decides, from the class and the marks, whether an action runs at once or waits for the user's confirmation. *Proposed*, *Aligned* and *Open* are the statuses of the [README](../README.md); only *Decided* is firm.

**Where the lines come from.** Line numbers are those of 16 November 2026. Two files move while this booklet is written: `architecture/kernel-interface.md` and `architecture/kernel.md` are being rewritten by pass 14B, so their lines can shift; search for the section named. Two sources are not yet on the `main` branch of this repository: the new [security.md](../architecture/security.md) with the threat model, the security model of the agent and its fourteen "Points for the two owners" (commit `af51cc5` on `origin/main`, lines cited from that version), and the Step 0 revision of the WIT contracts in the system repository (pull request 1 of `Vehicoule/DodOS`, branch `step0-contracts`, commit `aab7417`, cited as `DodOS: contracts/<file>:<line>`).

## Answers received

Answers given by one owner on 16 November 2026 (recorded in the decision log as D-132; the second owner has not yet confirmed those marked "Both" in the table below).

| No. | Answer | Note |
|---|---|---|
| P-004 | A: require CET | Given on the condition that CET is old and widely supported. On Intel it starts with the 11th generation (Tiger Lake, 2020); the reading of the reference desktop (P-002) confirms |
| P-005 | A: the split of D-126 | The owner asked for B only if it showed a real gain; the Zig study and its verification show none |
| P-006 | A | |
| P-007 | B: the USB debug capability | It needs an xHCI controller that offers the capability and a USB 3.0 A-to-A debug cable; if either is missing on the desktop, the serial port of option A is the fallback, decided at the machine |
| P-008 | A | |
| P-009 | A | |
| P-010 | A (no signal) | |
| P-011 | A | |
| P-012 | A | |
| P-013 | A, on the assistant's advice | Research axis 4 is to be reworded |
| P-019 | A: Verus and Kani, Flux not adopted | |
| P-020 | C: group by group, on the assistant's advice | A group is accepted once it has passed its review |
| P-021 | B: pull request 3 waits for the model pass of D-128 and D-129 | Pull request 5 (the licence of `abi/`) was not answered separately |
| P-085, P-086 | Done in practice | The owner authorised Step 0 on GitHub: the template repository and the rulesets exist; the merge queue waits for the transfer to an organisation, which the owner will create |

## Table of entries

| No. | Question, shortened | Who answers | Recommendation | Sureness | Blocks |
|---|---|---|---|---|---|
| P-001 | Multi-core structure and protocols between kernels | Both, in the pass 14B review | Not in this booklet | — | Multi-core kernel |
| **Kernel** | | | | | |
| P-002 | Confirm the reference processor and its CET, PKS, FRED | Measure | Read CPUID and enable each feature on every core | — | P-003, P-004 |
| P-003 | Which write-gate mechanism on x86-64 | Measure | Prototype shadow-stack page tables first (D-120) | — | Gate code on x86-64 |
| P-004 | Require CET on every x86-64 machine | Both | A: require it | Leaning | Supported hardware list |
| P-005 | Where Rust and Zig sit in the kernel (D-126) | One owner | A: as proposed | Firm | Kernel code layout, trials |
| P-006 | The kernel's own hand-over block and UEFI stub (D-125) | One owner | A: as proposed | Firm | Start-up page, signed image |
| P-007 | The debugging link on the reference desktop | One owner | A: a 16550 serial port | Leaning | Debugging base, first boot |
| P-008 | Who arms the hardware watchdog | One owner | A: platform service | Firm | Platform service contract |
| P-009 | Admission of scheduling contexts | Both | Rule as written | Leaning | Scheduling group of the model |
| P-010 | A signal when a budget runs out | One owner | Rule as written: none | Leaning | Scheduling group |
| P-011 | The fault *no context* | One owner | Rule as written: a fault | Firm | Scheduling group |
| P-012 | Sorted queues of deadlines | One owner | Rule as written: balanced trees | Leaning | Scheduling group |
| P-013 | The kernel task has no budget and no log | Both | Rule as written | Leaning | Research axis 4, tasks group |
| P-014 | The busy shared server | Measure (D-111) | Keep the written rule until measured | — | Frame-path services |
| P-015 | The kernel's numbers (budgets, step bounds) | Measure | Keep the written values until measured | — | Calibrated `abi/` |
| P-016 | Does memory survive a warm reset | Measure | Test on the desktop and the Dell | — | Crash record hand-over |
| P-017 | Cost of a page fault in the memory service | Measure | Measure against Linux | — | Overhead gate, D-095 |
| P-018 | Kernel trials of weeks 1-2 | Measure | Run them first | — | One-core kernel |
| P-019 | Which proof tools for the kernel | Both | Verus and Kani; Flux not now | Leaning | Kernel CI, gate proof |
| P-020 | Accept the one-core contract as the base | Both | A: accept now | Leaning | P-021, kernel code |
| P-021 | Merge the reference model and the `abi/` licence | Both | A: merge both now | Leaning | Kernel baseline on `main` |
| P-089 | May one process of a node use every send to a peer node | Both | B: two of eight sends kept for supervisors | Leaning | The model pass of D-131 |
| P-090 | Must the gate contain a faulty kernel that holds a granted frame | Both | B: free a grant only on the holder's gate-written words | Leaning | The grant protocol in the model |
| P-091 | What the audit of a recovery checks | Both | A: a walk of the tables after the acknowledgement | Leaning | G14 in the model |
| **Hosted userland and agent** | | | | | |
| P-022 | Accept the Step 0 contract revision as a draft | Both | A: merge as draft | Leaning | Hosted runtime, `dodo` |
| P-023 | Where the actions of system services run | Both | A: in the service's own process | Leaning | Shell, settings contracts |
| P-024 | The three other ways to draw (WebGPU, gpui, web view) | Both | A: wait for a released `wasi:webgpu` | Leaning | Canvas, games, gpui apps |
| P-025 | No native application ABI | Both | Confirm | Firm | Developer story |
| P-026 | Which model serves the agent by default | Both | A: local by default | Leaning | First start, P-037 |
| P-027 | The gpui trial | Measure | Run it in weeks 1-2 | — | D-083, hosted surface |
| P-028 | Native userland as a presence, not a window | Both | A: as proposed | Leaning | Shell, settings, files |
| P-029 | Message format for translations | One owner | Toss-up; verify library support first | Toss-up | Localisation SDK |
| P-030 | Which terminal shell to port | Measure (audit) | Audit candidates first | — | Alpha terminal |
| P-031 | Automatic snapshots of idle Wasm components | Measure | Run the one-week trial | — | D-025 point 2 |
| P-032 | Cost of asynchronous calls | Measure | Measure when the runtime exists | — | Overhead gate |
| P-033 | Pointer prediction | Measure | Measure the error before enabling | — | Compositor feature |
| P-034 | When to freeze `os:core` 0.1.0 | Both | B: after hosted step 3 | Leaning | Third-party developers |
| **Security** | | | | | |
| P-035 | What the threat model leaves out | Both | A: as written | Leaning | Threat model sign-off |
| P-036 | External actions declared harmless (point 1) | Both | A: GET and HEAD only, to listed hosts | Leaning | Manifest, P-034, P-067 |
| P-037 | A remote model counts as untrusted (point 3) | Both | A: as recommended | Firm | Inference contract |
| P-038 | Where inference runs (point 13) | Both | A: own process, no network | Firm | Agent services |
| P-039 | A named task service (point 10) | Both | A: as recommended | Firm | Shell, confirmations |
| P-040 | Who chooses the scope of a task (point 14) | Both | A: everything minus exclusions | Leaning | Agent `handle` |
| P-041 | Wording of the rule against the three risks (point 2) | Both | A: allow with confirmation | Firm | D-036 text |
| P-042 | Action descriptions as untrusted text (point 5) | Both | A: reading them marks `untrusted` | Leaning | `available` in contract |
| P-043 | Marks of captures and camera (point 11) | Both | A: as recommended | Firm | Capture service |
| P-044 | Marks a faulty kernel can drop (point 4) | Both | A: state the limit | Leaning | Kernel contract line |
| P-045 | The number of confirmations (point 8) | Both | A: accept and measure | Leaning | Injection suite |
| P-046 | No quarantine of untrusted reading in v1 (point 9) | Both | A: keep the deferral | Firm | — |
| P-047 | Showing the always-on wake-word microphone (point 6) | Both | A: as recommended | Firm | Compositor indicators |
| P-048 | Anyone audible is the user (point 7) | Both | A: as recommended | Firm | Voice path |
| P-049 | A device that types or clicks (point 12) | Both | A: accept every new input device by a gesture on an accepted one | Leaning | Input chain |
| P-050 | A hold before an external modification | Both | A: 10 s default, setting | Leaning | Journal, contract |
| P-051 | The agent's figure on screen | Both | A: closed states, drawn by the system | Leaning | Shell design |
| P-052 | JIT in the web content process | Both | B: no JIT in v1 | Leaning | Ladybird port, security rule |
| P-053 | The account model | Both | A: as proposed | Leaning | Installer, session |
| P-054 | A lost key with no escrow | Both | A: as proposed | Leaning | Installer |
| P-055 | What the disk key is sealed against (point 24) | Both | C: the signing key and a minimum version | Leaning | Installer, updates |
| P-056 | Secure boot route | Both | A: user enrols keys in v1 | Leaning | Signed image, installer |
| P-057 | The project's signing keys | Both | A: two of three, offline | Firm | First signed release |
| P-058 | Spread of sticky marks | Measure | Measure on the injection suite | — | D-111 two-way marks |
| P-092 | Where the mark `private` comes from (point 15) | Both | A: by zone, at read | Leaning | Storage service, matrix |
| P-093 | A local write of a package that holds the network (point 16) | Both | A: external in a marked task | Leaning | `invoke`, `world service` |
| P-094 | `keep` in an action instance (point 17) | Both | A: read only | Firm | `world service` |
| P-095 | Secret fields (point 18) | Both | A: `os-secret` only, always confirmed | Firm | Catalogue, `invoke` |
| P-096 | Answering a confirmation (point 19) | Both | A: own keys, focus moved by the user | Firm | Compositor, P-049 |
| P-097 | Captures and system material (point 20) | Both | A: blanked | Firm | Capture path |
| P-098 | Direct scanout and system elements (point 21) | Both | B: stops except for the discreet mark | Leaning | Compositor, latency gate |
| P-099 | A button that carries an action (point 22) | Both | A: overlay and own notifications only | Leaning | Catalogue, notifications |
| P-100 | Third-party words in a confirmation (point 23) | Both | A: outside system material, labelled | Firm | Confirmation drawing |
| P-101 | Dependency changes in the maintenance lane (point 25) | Both | B: another model family reviews | Leaning | D-032, CI |
| P-102 | A grant for the rest of a task and a later mark (point 27) | Both | A: ends with the mark | Firm | `invoke` |
| P-103 | `focus-surface` (point 28) | Both | A: as recommended | Leaning | Shell actions |
| **Storage, memory, platform, network, media, devices** | | | | | |
| P-059 | How long versions are kept | Both | A: as proposed | Leaning | Storage service |
| P-060 | Packages shared between users, unencrypted | Both | A: as proposed | Leaning | Zones, installer |
| P-061 | Backup in version 1 | Both | B: external disk and circle device only | Leaning | Storage, P-081 |
| P-062 | Copy on write in the memory service | One owner | B: with the snapshot work | Leaning | Memory service scope |
| P-063 | Who loads processor microcode | One owner | B: the first stage | Leaning | Start-up path |
| P-064 | Does the desktop sleep in version 1 | Both | A: no sleep at first | Leaning | Power service |
| P-065 | Dual boot in the installer | Both | A: as proposed, no resizing | Leaning | Installer |
| P-066 | Server administration without SSH | Both | A: as proposed | Leaning | Server image |
| P-067 | Network rights per host and port | Both | A: as proposed | Firm | Network service, manifest |
| P-068 | Who runs the relay | Both | Decide with P-081 | Toss-up | Key-addressed services |
| P-069 | The network stack | Measure (trial) | Run the extraction trial | — | Hosted network stack |
| P-070 | H.264 and AAC in version 1 | Both, after counsel | Wait for P-080 | Leaning | Media components |
| P-071 | Protected video (Widevine) | Both | A: accept the limit | Leaning | Browser |
| P-072 | The system font family | One owner | B: choose with the token file | Leaning | Design tokens |
| P-073 | The GPU trial | Measure | Run it at the head of the GPU track | — | D-050, GPU track |
| P-074 | Wake word during sleep | Measure | Test on the Dell | — | Voice promise |
| P-075 | Calibrate the gates | Measure | Calibrate before arming | — | Ratchets |
| **The project** | | | | | |
| P-076 | When to engage legal counsel | Both | A: now, one brief | Leaning | P-077 to P-080 |
| P-077 | The contributor agreement | Legal counsel | Licence with relicensing right | Leaning | First outside contribution |
| P-078 | Licence of the Linux emulation layer | Legal counsel | Confirm D-047 | — | Driver processes |
| P-079 | Reading other kernels' code | Legal counsel | Opinion before commercial version | — | Commercial licence |
| P-080 | Patents on H.264 and AAC | Legal counsel | Opinion | — | P-070 |
| P-081 | Who buys | Both | A and B first | Leaning | P-061, P-068 |
| P-082 | The name | Both | Decide before the demonstration | Leaning | P-088 |
| P-083 | Telemetry | Both | A: none by default | Firm | Crash reporting |
| P-084 | The integration repository | Both | B: the system repository's pin | Leaning | Step 0 |
| P-085 | The template repository | Both | B: not now | Leaning | Step 0 |
| P-086 | Branch protection and code owners | Both | A: now, on the three repositories | Firm | Contract lane |
| P-087 | The list of checks per stage | Both | A: accept as written | Leaning | CI growth |
| P-088 | The first public demonstration | Both | A: as proposed | Leaning | Publication, P-082 |

---

## P-001 — Out of this booklet: the multi-core structure and the protocols between kernels

**Question.** How a node of several cores locks its state, how nodes exchange messages, recover each other and move memory and devices: these are answered in the pass 14B review, not here.

**Where.** [decisions/README.md](../decisions/README.md) D-128 (decided by the owners) and D-129 (proposed by the assistant, lines 138-139); [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), "Points for the two owners" (rows from "Memory between nodes" to "The mailbox"), "Faults found in the decided shape (D-128)" (ten faults for the owners), and [Open points](../architecture/kernel-interface.md#open-points) (locking L1 or L2, elastic nodes, the times of membership, INIT during SMM, the RISC-V stop extension, the IOAPIC end of interrupt, the numbers of the multi-node part); [kernel.md](../architecture/kernel.md).

**Also left there.** The trial of the x86-64 bootstrap core (D-117), the reload policy, roles, the mailbox, the kept image, devices that follow their driver, stopping a core, the multi-core "Dynamic structure" of kernel.md, and two sentences made stale by D-128: memory.md line 27 ("each core has its own copy of the page table") and the multi-core gates of [gates.md](gates.md). The parts of D-122 to D-127 that concern only one node are in P-005, P-006 and P-020.

**Who answers.** Both owners, when pass 14B is finished. **Except** the three questions the eighth review left for the owners (pass 14C, D-131), which change what the system promises and are put here as P-089 to P-091.

---

## Group 1 — What blocks the kernel being written

## P-002 — Confirm the reference processor and its features (measure)

**Question.** Which exact processor is in the reference desktop, and do all its cores really have CET (shadow stacks and indirect-branch tracking), PKS and FRED?

**Where.** [decisions/README.md](../decisions/README.md) D-116 point 4 (line 126): "probably an Intel Core i5-14600KF … to confirm"; [kernel.md](../architecture/kernel.md) line 207 (FRED presence: Open), line 210 (CET: "present … per its CPUID, to confirm on the machine"), line 120 onward (PKS: `IA32_PKRS` is in the SDM's table of 12th and 13th-generation hybrid MSRs, volume 4 Table 2-46 of order 325462-093, while Intel support said 13th-generation parts lack PKS: to test on the machine).

**What to measure.** On the desktop, from a boot image that runs on every core in turn: the model name and stepping; the CPUID bits of CET shadow stacks, IBT, PKS and FRED on each performance core and each efficiency core; then enable shadow stacks, IBT and PKS on each core and check that they work, since a CPUID bit alone was already contradicted for PKS; supervisor shadow stacks only once `CPUID.07H.01H:EDX.CET_SSS[18]` is read, since `WRSSQ` at ring 0 needs them on (`IA32_S_CET.SH_STK_EN` and `WR_SHSTK_EN`). FRED is deferred after the alpha (D-065) and is recorded only.

**What waits for it.** P-003 and P-004; the list of supported hardware.

**Who answers.** A measure on the reference desktop, out of reach until about 29 November 2026 ([progress.md](progress.md) line 109). An agent prepares the image under QEMU before that date.

## P-003 — Which write-gate mechanism on x86-64 (measure)

**Question.** On x86-64, does the kernel protect its page tables by typing them as shadow-stack pages written only by `WRSSQ` (no window open while the gate writes), or by a page-table root that only the gate uses (a window opens while it writes)?

**Where.** [kernel.md](../architecture/kernel.md) "The write gate: mechanisms", line 120 onward; D-120 point 1 (line 130). Status Proposed. The *write gate* is the one small piece of kernel code allowed to write page tables, IOMMU tables and the machine table, so a faulty kernel stays inside its own memory (D-117).

**Options.** A. Shadow-stack page tables: an ordinary store to a page table faults, nothing to close on an interrupt; costs a mechanism nobody has built. B. A gate-only root with PCID: well understood; costs two root switches per gate call and a window that every interrupt arriving inside it must close first. C. PKS: only if P-002 shows it works; no figure found.

**Proposed today.** A first, B as the fallback (D-120). The figures kernel.md cites are measured by others: `WRSSQ` 9.3 cycles against 0.8 for a `MOV` on a Tiger Lake core (CETIS, CCS 2022); two root writes of about 200 cycles each (Ren et al., SOSP 2019).

**What to measure.** The list kernel.md gives (line 166): whether a page-table page typed as a shadow-stack page still serves the page walk and its accessed and dirty bits; the cost of a gate call and of a batch of 512 entries; CET's cost on a null call, an IPC and an address-space switch; the false positives of the instruction scanner.

**What waits for it.** The x86-64 part of the gate; P-004. **Depends on** P-002.

**Who answers.** A measure on the reference desktop. No opinion replaces it.

## P-004 — Require CET on every x86-64 machine

**Question.** Does DodOS refuse to run on an x86-64 processor without CET?

**Where.** [kernel.md](../architecture/kernel.md) line 210, "CET: To be required", Proposed (D-120).

**Options.**
- **A. Require CET.** Gives: one gate design on x86-64; CET keeps a wild jump out of the middle of the gate. Costs: older x86-64 processors without CET cannot run DodOS; that list is not in the documents.
- **B. CET optional, with the CR0.WP toggle on older processors** (the Nested Kernel method, about 473 cycles per call on a Core i7-3770, ASPLOS 2015, as kernel.md cites). Gives: older machines. Costs: a second gate path to write, test and prove, and no protection against a jump into the gate.

**Proposed today.** A. The project's two machines are recent; D-024 limits the machines to two.

**Recommendation.** A: the project has two target machines and the proof of the gate (D-117) is hard enough once. *Leaning*, until P-002 confirms CET on both kinds of core.

**Blocks.** The supported hardware list; the gate design. **Depends on** P-002, P-003.

**Who answers.** Both owners.

## P-005 — Where Rust and Zig sit in the kernel (D-126)

**Question.** Do you accept the split of D-126: Rust for the gate, the IPC fast path, firmware table parsing, the UEFI stub and all the logic; Zig for trap entry, the context switch, interrupt controllers, timers, IOMMU registers, starting cores and the generated register layer?

**Where.** [decisions/README.md](../decisions/README.md) D-126 (line 136), Proposed by the assistant; [kernel-interface.md](../architecture/kernel-interface.md) "Language split" (line 2028); [kernel.md](../architecture/kernel.md) lines 13-14.

**Options.**
- **A. As proposed.** Gives: everything the proof tools must see (the gate, the fast path) is in Rust, where Verus and Kani work; the boundary is crossed once per event, never per table entry. Costs: the earlier plan of a Zig fast path goes.
- **B. Zig also for the fast path** (the earlier plan, still written in [verification.md](verification.md) line 58, "Fast path in Zig"). Gives: Zig where speed matters. Costs: the fast path is outside the proof tools; an equivalence test is the only check.
- **C. Rust only.** Gives: one language. Costs: reopens D-004 and D-094, which the user confirmed against the assistant's advice.

**Proposed today.** A, from the draft `zig-in-the-hardware-layer.md` and its verification by Hydrogen. The draft measured that a packed struct stored through a volatile pointer compiles to one read-modify-write per field in Zig 0.17.1, and that `std.debug.simple_panic` does not build freestanding in 0.17.1 (as D-126 states).

**Recommendation.** A: it keeps Zig (D-094) and puts the proven parts in the language that has proof tools. *Firm.* If accepted, verification.md line 58 must say "fast path in Rust".

**Blocks.** The layout of the kernel's code; the trials of P-018. **Depends on** nothing.

**Who answers.** One owner re-reads; the assistant settled the details (D-098).

## P-006 — The kernel's own hand-over block and UEFI stub (D-125)

**Question.** Does the kernel receive only a DodOS hand-over block, built by a first stage per platform (on PCs the DodOS UEFI stub, in Rust, inside the single signed image), rather than a standard boot protocol?

**Where.** [decisions/README.md](../decisions/README.md) D-125 (line 135), Proposed by the assistant; [kernel-interface.md](../architecture/kernel-interface.md) line 1799, "What the first stage hands over".

**Options.**
- **A. As proposed.** Gives: the kernel names no firmware standard, so ARM64 boards and phones (U-Boot, device tree) need only a new first stage; the UEFI stub is the signed EFI image that secure boot wants (P-056). Costs: the project writes and maintains a first stage per platform; Limine stays a bring-up tool only.
- **B. The Limine protocol as the kernel's entry.** Gives: faster bring-up. Costs: the kernel depends on a loader the project does not control, and a second path is still needed for non-UEFI machines.
- **C. The kernel as a UEFI application.** Gives: one binary. Costs: UEFI types inside the kernel, against "portable and built to last" (D-015).

**Recommendation.** A: it is the only option that keeps the kernel free of one platform, as D-015 requires. *Firm.*

**Blocks.** The start-up page (version 3), the signed image, the crash areas kept across a reboot. **Depends on** nothing.

**Who answers.** One owner re-reads.

## P-007 — The debugging link on the reference desktop

**Question.** Which link carries the kernel's debugger stub and console on the reference desktop: a 16550 serial port, or the USB controller's debug capability?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#open-points), Open points, "The debugging means on the reference desktop" (line 2109), not decided; D-058 (line 68) says "kernel debugger through the USB debug port"; [progress.md](progress.md) line 108: the owner's desktop has no serial port on its case.

**Options.**
- **A. A 16550 serial port** (the board's header with a bracket, or a PCIe serial card), with the USB debug capability as an option. Gives: the simplest link, usable from the first instruction. Costs: a part to buy and fit; amends D-058.
- **B. The USB debug capability only.** Gives: no hardware to buy. Costs: it shares the PCI function of its USB controller, so a development image loses the USB ports of that controller; more code before the first message.

**Proposed today.** A.

**Recommendation.** A: debugging comes before features (D-091), and a serial line works before any USB code exists. *Leaning*: it depends on whether the board has a header.

**Blocks.** The debugging base of kernel step 0; booting on the desktop from the first week. **Depends on** nothing.

**Who answers.** The owner who holds the desktop (one owner).

## P-008 — Who arms the hardware watchdog

**Question.** Is the hardware watchdog (the timer that resets a hung machine) armed by the platform service and fed by the service manager, or by the kernel?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#open-points), Open points (line 2108), not decided; [platform.md](../architecture/platform.md) line 62; [progress.md](progress.md) line 108 held this "until the report on stopping a core without its cooperation (D-116)": that report exists and D-117 is decided, so nothing holds it now.

**Options.**
- **A. Platform service arms it, service manager feeds it.** Gives: the kernel reads only the MADT and the DMAR (D-112); a whole-machine hang resets through it. Costs: a hang of the platform service's node also stops the feeding, which is the intended effect.
- **B. The kernel arms it.** Gives: works with no user space. Costs: a second exception to D-054 (the kernel reading ACPI tables), since the watchdog is described in other tables (the ACPI WDAT table, the chipset's timer).

**Recommendation.** A: it keeps the kernel's ACPI reading to two tables. *Firm.*

**Blocks.** The platform service's contract; the crash path of platform.md. **Depends on** nothing.

**Who answers.** One owner.

## P-009 — Admission of scheduling contexts

**Question.** Does the kernel admit every scheduling context against one whole core (the sum of budget over period stays at most one core), giving unused time to throttled contexts by class?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "Admission" (line 2057), Proposed (D-110); [scheduling.md](../architecture/scheduling.md) line 14; [progress.md](progress.md) line 102.

**Options.**
- **A. As written.** Gives: every deadline is guaranteed on its core. Costs: the placement service must keep the sum under one core and give every thread a small reservation.
- **B. Admit only the frame class; strict classes below.** Gives: simpler. Costs: deadlines lose their guarantee beyond one core, and a waking thread can starve.
- **C. Fixed priorities, as seL4 MCS.** Gives: a proven model. Costs: the documents chose deadlines (D-040).

**Recommendation.** A: it is the only option that keeps the deadline promise the latency gates rest on. *Leaning*, until the placement service shows the reservations are manageable.

**Blocks.** The scheduling group of the reference model; the one-core kernel. **Depends on** nothing.

**Who answers.** Both owners.

## P-010 — A signal when a budget runs out

**Question.** When a scheduling context uses its whole budget, does the kernel signal anyone, or does a supervisor read the load with `sched_read`?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "Signal at exhaustion" (line 2059), Proposed (D-110).

**Options.** A. No signal; the supervisor polls `sched_read`. Gives: nothing in the kernel. Costs: polling. B. An optional notify per context, signalled at each exhaustion. Gives: an event. Costs: 16 bytes of the `sched` object, one signal per exhaustion, one more argument or call.

**Recommendation.** A: a periodic thread that uses all its budget is normal, and seL4 MCS raises its timeout fault only when a handler is set (as the contract states, line 553). *Leaning*; B can be added later as a new call without breaking the ABI.

**Blocks.** The scheduling group. **Depends on** nothing. **Who answers.** One owner.

## P-011 — The fault *no context*

**Question.** When a server thread loses the scheduling context it ran on (its client was killed), does the kernel raise a fault to its supervisor, or does the thread only stop?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "The fault *no context*" (line 2062), Proposed (D-110); [scheduling.md](../architecture/scheduling.md) line 86.

**Options.** A. A fault on the fault endpoint. Costs: one more fault kind. B. The thread only stops. Costs: a passive server whose client was killed is never noticed.

**Recommendation.** A: a stuck server that nobody sees is a silent hang. *Firm.*

**Blocks.** The scheduling group. **Depends on** nothing. **Who answers.** One owner.

## P-012 — Sorted queues of deadlines

**Question.** Does the kernel keep its deadlines in balanced trees linked through the objects (exact deadlines), or in a calendar of buckets (rounded deadlines)?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "Sorted queues" (line 2064), Proposed (D-110).

**Options.** A. Balanced trees. Gives: exact deadlines. Costs: logarithmic time and a balanced tree to verify in Rust. B. A calendar. Gives: constant time. Costs: deadlines rounded to a bucket.

**Recommendation.** A: exact deadlines are what the frame class needs, and the queues are short. *Leaning*; the measure of P-015 can reopen it.

**Blocks.** The scheduling group. **Depends on** nothing. **Who answers.** One owner.

## P-013 — The kernel task has no budget and no log

**Question.** Does the kernel's `task` object hold only marks, an identifier and threads, with its time counted by its threads' scheduling contexts and its log kept by the runtime's journal, rather than a time allowance and a log ring of its own?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "Task without budget and log" (line 2066), Proposed (D-110); [progress.md](progress.md) line 103; research axis 4 in [prior-art.md](../research/prior-art.md).

**Options.** A. As written. Gives: nothing on the hot path; consistent with "budgets are split, never copied" in the security model ([security.md](../architecture/security.md), line 164 on `origin/main`). Costs: research axis 4 ("the task as a kernel object gathering rights, budget, label and log") must be reworded. B. A time allowance and a log ring in the task. Gives: the research claim as first written. Costs: a write at every charge of a context and a write per message.

**Recommendation.** A: the claim gets weaker, the kernel stays fast and bounded. *Leaning*: it is a choice about what the project claims as new, which is the owners'.

**Blocks.** The tasks group of the model; the wording of research axis 4. **Depends on** nothing. **Who answers.** Both owners.

## P-014 — The busy shared server (measure)

**Question.** When a frame-class client waits behind a background client inside a shared service, which rule does the kernel apply: no lending and no threshold (written), lending of the waiting client's context, or a budget threshold per endpoint?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "Busy shared server" (line 2058); D-111 (line 121): "the written rule and its two alternatives are to be measured"; [scheduling.md](../architecture/scheduling.md) line 77 onward. The threshold idea comes from seL4's RFC-14, "read through a search summary; merge state not verified" ([verification-status.md](../research/verification-status.md) line 29).

**What to measure.** On the one-core kernel, the wait of a frame-class client behind a background client in one shared service, under the three rules, with the frame-path services of the hosted track ported (input, compositor, audio). The written rule stands meanwhile; frame-path services use one thread per core or a frame-class context.

**What waits for it.** The design of shared services on the frame path. **Who answers.** A measure; then both owners.

## P-015 — The kernel's numbers (measure)

**Question.** Which values replace the provisional numbers: minimum budget 10 µs, maximum period 2^36 ns, 16 due events per interrupt, a start-up context of 10 ms, the removal step bound of 32, the `cspace` segment of 128 slots and the clearing step of 64 KB?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#points-for-the-two-owners), row "Scheduling numbers" (line 2063); [Open points](../architecture/kernel-interface.md#open-points) (line 2102).

**What to measure.** On the reference desktop with the one-core kernel: the longest time of one call at each bound (each value bounds the latency of one call, D-042), and the interrupt latency at 16 due events. The written values stand until then; they are constants of `abi/`.

**What waits for it.** A calibrated `abi/`. **Depends on** the one-core kernel. **Who answers.** A measure.

## P-016 — Does memory survive a warm reset (measure)

**Question.** On the reference desktop and the Dell laptop, does RAM keep its contents across a warm reset, so that the crash record of a complete stop can be read by the next boot?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#open-points), Open points (line 2110); line 1454; D-125 point 1 (a first stage keeps the crash areas by its own means, or says it cannot).

**What to measure.** Write a known pattern in the crash area, trigger a warm reset, read it from the next boot, on both machines, several times. If it does not survive, the first stage must keep the record by another means (a UEFI variable or a file on the EFI partition, as D-125 lists).

**What waits for it.** The hand-over of the crash record. **Who answers.** A measure on both machines.

## P-017 — Cost of a page fault in the memory service (measure)

**Question.** How much does a page fault cost when the user-space memory service resolves it, compared with Linux, where the kernel resolves it?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#open-points), Open points (line 2103); "Memory outside the kernel" (line 1641), Decided (D-095); [gates.md](gates.md) lines 52 and 56 ("To set").

**What to measure.** A minor fault resolved from memory already present, and a mapping, on the one-core kernel against Linux on the same desktop. The documents argue the cost stays low because memory is mapped at reservation (no first-touch fault). The number sets the gate; D-095 is decided and is reopened only if the number is far off.

**Who answers.** A measure.

## P-018 — The kernel trials of weeks 1-2 (measure)

**Question.** Do the Zig and Rust boundary and a kernel with no per-thread stack work as the documents assume?

**Where.** [kernel.md](../architecture/kernel.md) lines 16 and 20 (the kernel shape is Aligned; its feasibility is "from memory"); [verification-status.md](../research/verification-status.md) line 47; [progress.md](progress.md) line 26; [roadmap.md](roadmap.md) line 54.

**What to measure.** Under QEMU: a Zig trap stub calling Rust and back, with the constants generated from `abi/` (P-005); a context switch and a blocking IPC with no kernel stack per thread; the seL4 oracle harness running a first differential test. The documents give no fallback if the stackless kernel fails; if it does, the owners decide then.

**What waits for it.** The one-core kernel. **Depends on** P-005. **Who answers.** A trial by an agent.

## P-019 — Which proof tools for the kernel

**Question.** Which tools prove the kernel's Rust logic and the gate: Verus with Kani, as decided in D-029, or Flux as well?

**Where.** [verification.md](verification.md) "Formal proof", lines 69-73: Open; Flux is Aligned; D-029 (line 39) puts Verus properties in the contract; D-117 says "the gate is to be proven"; D-128's third fault says a gate for several cores has no proof tool yet ([kernel-interface.md](../architecture/kernel-interface.md), "Faults found in the decided shape", point 2).

**Options.** A. Verus for the gate and the derivation tree, Kani in CI on every PR, Flux not adopted. B. Verus and Flux both. C. Kani only for version 1.

**Proposed today.** Verus (decided) and Kani. Flux's support is a study not cross-checked (TickTock, SOSP 2025). The precedent cited for Verus, Atmosphere ("6,000 lines … in less than 2.5 person-years … with a global lock"), is listed as not confirmed by the review ([verification-status.md](../research/verification-status.md) line 78).

**Recommendation.** A: one proof tool is already a large effort, and Kani runs today in the `abi/` crate. *Leaning.*

**Blocks.** The proof budget in CI; the structure of the gate's code. **Depends on** P-005. **Who answers.** Both owners.

## P-020 — Accept the one-node contract as the base of the model and the kernel

**Question.** Do you accept now, as the base of the next model pass and of the one-core kernel, the parts of the contract that concern one node: the five D-110 groups (memory and devices; threads; scheduling and time; interrupts; tasks and marks), the start-up state, and the one-node parts of D-122 to D-127?

**Where.** [decisions/README.md](../decisions/README.md) D-110 (line 120, "To review four times (D-104), then by the two humans"), D-122 to D-127 (lines 132-137, "Proposed by the assistant, to be read by the two owners"); [kernel-interface.md](../architecture/kernel-interface.md) line 76 onward; [progress.md](progress.md) lines 101-104 and line 91 ("the D-110 groups still need their review").

**Options.**
- **A. Accept now**, with P-005 to P-013 answered and the list below validated as written. Gives: the model pass and the kernel start this week. Costs: the D-110 groups have not had a review of their own; the sixth and seventh reviews (four reports each) read the whole contract.
- **B. Wait for four independent reviews of the D-110 groups** (D-104). Gives: the review the decision log asks for. Costs: about a day of agents and the owners' re-reading before the kernel starts.
- **C. Accept group by group** as each passes its reviews.

**No alternative worth a decision, validate as written:** the kernel clears every object it creates (D-111); 64-byte slots and the other rows of D-112; feature masks as the size argument of `untyped_retype`; a `sched` object of 256 bytes; `core_perf` (now `node_perf`); `entropy_read` taking words to mix in; the debugger stub on its own link; an undelivered *no context* fault recorded in the thread; padding before an object kept cleared; one page size per level, no page larger than 512 chunks, a 64 KB granule refused (D-124, D-127); little-endian required; a machine with neither a seed nor a hardware generator does not start; registers and scan lists generated from AARCHMRS, `riscv-unified-db` and Intel XED, the build failing on an unclassified encoding; Velosiraptor not used; the model behind a machine boundary; no kernel heap ([kernel.md](../architecture/kernel.md) line 18); the user-interrupt hook placed and not used; PKS and POE as optional accelerators; a kernel binary per core type only if measured.

**Recommendation.** A: the contract has been read by two rounds of four reviewers and three model passes, and each later finding is cheaper in the model than in kernel code. *Leaning*: B is what D-110 itself says.

**Blocks.** P-021; the one-core kernel. **Depends on** P-005 to P-013. **Who answers.** Both owners.

## P-021 — Merge the reference model and fix the `abi/` licence

**Question.** Do you merge now pull request 3 of the kernel repository (the reference model and the `abi/` crate, branch `model`) and pull request 5 (`abi/` under the Apache License 2.0, D-119)?

**Where.** [progress.md](progress.md) line 90 (stale: it gives head `2afc901` and 985 tests); pull requests 3 and 5 of `Vehicoule/dodos-kernel`, both open on 16 November 2026. Checked: `abi/Cargo.toml` on branch `model` still says `license.workspace = true`, so it inherits the AGPL of the workspace, against D-119; on branch `abi-apache` it says `Apache-2.0`.

**Options.**
- **A. Merge both now**, PR 5 first, then PR 3 with its `abi/Cargo.toml` set to Apache-2.0. Gives: `main` holds the model the kernel is written against; each later pass is a smaller pull request. Costs: the next pass (for D-128 and D-129) changes `abi/` a lot, on `main`.
- **B. Wait for the model pass of D-128 and D-129.** Gives: one merge. Costs: `main` keeps the 542-line `abi/` of before D-110 meanwhile, and the green box "Interface in code: abi crate" of progress.md stays untrue.

**Recommendation.** A: the contract lane asks humans to merge, and a merged base makes every later pass reviewable. *Leaning.*

**Blocks.** The kernel's baseline on `main`. **Depends on** P-020. **Who answers.** Both owners (contract lane, D-084).


## P-089 — May one process of a node use every send to a peer node

**Question.** `SENDS_PER_PEER` (8) counts the stamped sends in flight from one node to another, whatever process makes them. Should any process be able to hold all eight, so that the supervisor's `node_send` to that peer returns `busy`?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md), "Questions after the eighth review (D-131)", question 1; "Calls between nodes", the state checks of `node_send`; the eighth review by Hydrogen, finding 12, and both its verifications (`reviews/2026-11-16-contract-review-8-*`), which leave it to the owners.

**Options.**
- **A. Accept it.** Gives: nothing to add. Costs: a process can keep a supervisor from reaching another node until its sends are answered; the placement service and the supervisor must notice and act.
- **B. Keep two of the eight for a `node` capability with `manage`**, which only supervisors hold. Gives: a supervisor always has a send. Costs: one comparison in `node_send`; ordinary processes have six.
- **C. A quota per task.** Gives: fairness between processes. Costs: a count per task and per peer, which the 256-byte task object cannot hold for 1,024 peers.

**Proposed today.** B is written in the contract as the recommended rule.

**Recommendation.** B: the cost is one comparison, and it keeps recovery and supervision reachable. *Leaning.*

**Blocks.** The model pass of D-131 (the send credits). **Who answers.** Both owners.

## P-090 — Must the gate contain a faulty kernel that holds a granted frame

**Question.** A node frees a grant of one of its frames on the holder's word: its `Release`, its `RevokeStep` that reports the root removed, its `SendAnswer` that says a frame was not delivered, and the use index that answer gives. If the holder's kernel is faulty in those messages (its gate being correct), the granting node can free and reuse memory that the holder still translates. Should the gate's guarantee cover that case?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md), "Questions after the eighth review (D-131)", question 2, and "What it costs and what it does not cover" ("Not covered"); found by the assistant's own attack on pass 14C, raised by no reviewer.

**Options.**
- **A. No: say so.** A grant trusts the grantee's kernel for its release; G holds for the memory a node owns, not for frames it granted to a faulty node. Gives: no change. Costs: a kernel bug on a node that holds a frame can reach the granter's reused memory.
- **B. Yes: the granter frees only on words the holder's gate wrote.** The use entry at the recorded index must name the grant with count 0; the holder's gate keeps such an entry, *released*, until the grant is freed, and writes a use entry for every frame of a `Send` it consumes. Gives: G holds against a faulty holder. Costs: one read per freeing, use entries that live until their grant is freed, and one case still to settle (a `Send` that finds the holder's use table full), so B needs a model before it enters.
- **C. Yes: the granter searches the holder's use table (128 KB) before every freeing**, in steps. Gives: G holds with no protocol change. Costs: that search at every release.

**Proposed today.** A is written in the contract, because B is not settled; B is the recommendation.

**Recommendation.** B, after a model of its full-table case. *Leaning.*

**Blocks.** The grant protocol in the next model pass. **Who answers.** Both owners.

## P-091 — What the audit of a recovery checks

**Question.** At each recovery, every node audits its own gate. The contract asked for each map count to equal the leaves of the node's tables that target its chunk, but the walk that counts them runs in steps while the node maps and unmaps, so a healthy node stopped the machine. What should the audit check?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md), "Questions after the eighth review (D-131)", question 3, and G14; Opus's verification of the eighth review (DeepSeek's report), new finding N3.

**Options.**
- **A. A walk of each table page under the gate lock**, checking that every entry targets memory the node may map, after the node's acknowledgement so it delays no reclaim. Gives: an exact check per step, no cost to the node's processes. Costs: a count left too low by a gate bug shows only once the memory it let go is reused.
- **B. Keep the equality and freeze the node's map counts while its audit runs.** Gives: the stronger check. Costs: the node's processes cannot map or unmap during every recovery of any node, for as long as the walk of its tables.
- **C. Keep the equality with a tally of 4 bytes per chunk of the machine in each node**, corrected by the gate behind the walk. Gives: the stronger check, no freeze. Costs: kept memory of 2 MB per node on a machine of 1 TB (256 MB for 128 node slots).

**Proposed today.** A is written in the contract.

**Recommendation.** A: the audit detects, it does not prevent, and A costs nothing to the processes the recovery keeps running. *Leaning.*

**Blocks.** G14 in the next model pass. **Who answers.** Both owners.

---

## Group 2 — What blocks the hosted userland and the agent's experience on Linux and macOS

## P-022 — Accept the Step 0 revision of the contracts as a draft

**Question.** Do you merge pull request 1 of the system repository (the Step 0 revision of the WIT contracts) as the draft `os:core` 0.1.0, not yet frozen?

**Where.** Pull request 1 of `Vehicoule/DodOS`, commit `aab7417`, open since 16 November 2026. It settles most of the `OPEN` items that [open-questions.md](../research/open-questions.md) lines 49-57 still list, and adds `manifest.wit` (the package manifest contract, which progress.md line 92 says is "Not started"), `input.wit` (text input), `agent.wit` (inference, memory, audio, the agent's figure, reading another window's accessibility tree), `shell.wit`, `mcp.md`, and the WASI 0.3.2 packages vendored.

**No alternative worth a decision, validate as written:** schemas of actions in a subset of JSON Schema 2020-12 with two DodOS keywords (`os-item`, `os-secret`); a manifest signed as a TUF target of its publisher; the publisher written as the 64-hex-digit TUF key id; an object identifier of 128 random bits in 26 base32 characters; the size caps of `core.wit` lines 51-74; background wake-up by `background.schedule` and the `wake` export; no purge offered to components (purging is a confirmed system action); query with "or" and "!=", full-text and semantic search left to derived indexes; the accessibility tree as the system's own projection with WAI-ARIA 1.2 roles (which settles the Open point of [ui.md](../architecture/ui.md) line 122); MCP tools mapped to actions by an adapter component.

**Options.** A. Merge as a draft; the `OPEN` points (P-023, P-024, P-036, P-037, P-042) stay marked in the files. B. Answer those points first, then merge. C. Leave it open until the freeze (P-034).

**Recommendation.** A: the hosted runtime and `dodo` need a contract to build against now, and a draft can still change. *Leaning.*

**Blocks.** The hosted runtime and `dodo` (hosted step 1). **Depends on** nothing. **Who answers.** Both owners (contract lane).

## P-023 — Where the actions of system services run

**Question.** Do the actions of system services (the shell's windows, settings, network, installation, power) run in the service's own process, or in a fresh instance per action like third-party actions?

**Where.** `DodOS: contracts/shell.wit:11-18`, `OPEN (owners)`. D-035 decides a fresh instance per action, holding only what its request carries; but these actions act on the compositor's state, which no request carries.

**Options.**
- **A. In the service's own process, the service on the trusted list.** Gives: the actions can reach the state they change. Costs: these services must be trusted as the compositor is; the fresh instance stays for third-party publishers, whose class it makes binding.
- **B. A fresh instance whose request carries a capability to the service.** Gives: one rule for all actions. Costs: the capability gives the instance the whole service, so the fresh instance protects nothing more.

**Recommendation.** A: the fresh instance exists to make a third party's declared class binding, and a system service has no third party to bind. *Leaning.*

**Blocks.** `shell.wit`, the settings and other service contracts. **Depends on** P-039. **Who answers.** Both owners.

## P-024 — The three other ways to draw

**Question.** Does `os:core` 0.1 wait for a released `wasi:webgpu` before offering raw WebGPU, gpui compiled to Wasm and the `canvas` kind fed by the GPU, or does it vendor a pre-release now?

**Where.** `DodOS: contracts/core.wit:320-328` and `catalog.wit:199-201`, `OPEN`; [wasm-abi.md](../architecture/wasm-abi.md) line 157 lists four ways to draw; [gpu.md](../architecture/gpu.md) line 9: `wasi:webgpu` is "a WASI proposal in phase 2". The contract notes it has no release in WASI 0.3.2.

**Options.**
- **A. Wait.** Gives: a frozen ABI that rests only on released standards. Costs: until then, third-party applications draw only with the catalogue; games (Wasm only, D-013) and gpui applications wait.
- **B. Vendor the pre-release, marked unstable.** Gives: games and free drawing in the hosted track. Costs: a component built against it may break when the proposal changes, against the promise that a published component keeps running.

**Recommendation.** A for 0.1, with B allowed in a separate unstable package that no frozen world includes. *Leaning.*

**Blocks.** The `canvas` kind; games; gpui applications. **Depends on** nothing. **Who answers.** Both owners.

## P-025 — No native application ABI

**Question.** Do you confirm that Wasm components and WIT stay the only application ABI, with no native ABI for applications?

**Where.** [wasm-abi.md](../architecture/wasm-abi.md) line 179, Aligned; [thesis.md](../thesis.md) line 33, Aligned.

**Options.** A. Confirm. Costs: every application, game and IDE runs as Wasm; Electron is not planned (D-077). B. Plan a native ABI. Costs, as wasm-abi.md lists: one binary per architecture, a libc and an executable format to keep stable, the port of each runtime.

**Recommendation.** A: it is the second reason the project exists (thesis, point 2). *Firm.*

**Blocks.** The developer story. **Depends on** nothing. **Who answers.** Both owners.

## P-026 — Which model serves the agent by default

**Question.** At first start, does the agent use a local model by default, with a cloud provider as an opt-in, or does the user choose a provider at first start?

**Where.** [agent.md](../architecture/agent.md) line 11, Aligned: "Models are interchangeable, local or cloud. Local inference by llama.cpp". No document says which is the default.

**Options.**
- **A. Local by default; a remote provider is a setting.** Gives: no data leaves the machine by default; no online account needed (P-053). Costs: the quality and speed of the agent are those of a local model on the user's hardware.
- **B. The user picks at first start.** Gives: the best model for those who want it. Costs: a first-start screen; with P-037, a remote model marks every task `untrusted` for the matrix.

**Recommendation.** A: it matches "the user owns the machine and the data" (thesis) and the security points. *Leaning.*

**Blocks.** The first-start experience; the hosted agent (hosted step 3). **Depends on** P-037. **Who answers.** Both owners.

## P-027 — The gpui trial (measure)

**Question.** Does gpui hold as the shell's renderer (D-083), or does the project fall back to Rune?

**Where.** [ui.md](../architecture/ui.md) lines 26-29; D-083 (line 93); [progress.md](progress.md) line 40.

**What to measure.** In weeks 1-2: draw the catalogue with gpui and gpui-kit; write gpui's window back end for the project's compositor; compare LibWeb on the same catalogue; reference screenshots per kind and theme; and the size an application pays when it links gpui ([ui.md](../architecture/ui.md) line 72 quotes 8 to 15 MB "to measure").

**What waits for it.** The hosted surface (hosted step 2). **Who answers.** A trial by an agent; the owners read the report.

## P-028 — Native userland as a presence, not a window

**Question.** Is the project's own userland (settings, files and the rest) made of services that export actions and catalogue views shown by the shell, with no application frame?

**Where.** [ui.md](../architecture/ui.md) lines 61-72, "Design system", Proposed.

**Options.** A. As proposed. Gives: one look, everything drivable by the agent, rendering paid once in the shell. Costs: the catalogue must grow beyond the agent's fifteen kinds; no classic windowed applications from the project. B. Classic applications with frames. Gives: the familiar model. Costs: each pays for its own renderer (8 to 15 MB with gpui, to measure).

**Recommendation.** A: it is the experience the thesis promises (an agent always present, a shell designed for it). *Leaning.*

**Blocks.** The shell and the project's applications. **Depends on** P-027. **Who answers.** Both owners.

## P-029 — Message format for translations

**Question.** Are user-facing strings written in Fluent or in MessageFormat 2?

**Where.** [ui.md](../architecture/ui.md) line 118, Proposed: "message format to choose (Fluent or MessageFormat 2)"; ICU4X for locales.

**Options.** A. Fluent. B. MessageFormat 2. The documents give no ground for either.

**Recommendation.** Have an agent verify which of the two the Rust stack of the shell (gpui, ICU4X) supports in a released crate, and take that one. *Toss-up* until then.

**Blocks.** The localisation SDK. **Who answers.** One owner, after the check.

## P-030 — Which terminal shell to port (audit)

**Question.** Which existing shell with structured data, whose commands are actions, does the terminal port, now that Nushell is withdrawn?

**Where.** [wasm-abi.md](../architecture/wasm-abi.md) line 171, Proposed; D-079 (line 89); brush "compiles for `wasm32-wasip3` experimentally" (line 166).

**What to do first.** An agent audits the candidates that build for WASI 0.3 and reports. Then the owners choose. No new language (the proposal).

**What waits for it.** The terminal of the alpha (D-061). **Who answers.** An audit, then both owners.

## P-031 — Automatic snapshots of idle Wasm components (measure)

**Question.** Does Wasmtime allow an automatic snapshot of an idle Wasm component, as D-025 point 2 plans after a one-week trial?

**Where.** [platform.md](../architecture/platform.md) line 34; D-025 (line 35).

**What to measure.** In the hosted runtime: snapshot and restore an idle component, its size and time. If it fails, version 1 has only `suspend` and `resume` (already decided) and memory pressure step 3 of [memory.md](../architecture/memory.md) is removed.

**Who answers.** A trial by an agent.

## P-032 — Cost of asynchronous calls (measure)

**Question.** How much do asynchronous component calls cost on DodOS's own interfaces?

**Where.** [wasm-abi.md](../architecture/wasm-abi.md) line 124, Open ("about 3.5 times on synchronous calls in Wasmtime"); [gates.md](gates.md) line 43 ("To set").

**What to measure.** Once the hosted runtime exists: a call and an asynchronous call between two components and between two processes, end to end. The number sets the gate; rule 4 of the ABI (asynchronous by default) is decided.

**Who answers.** A measure.

## P-033 — Pointer prediction (measure)

**Question.** Does the compositor predict the pointer's path to prepare the target and hide display latency?

**Where.** [ui.md](../architecture/ui.md) line 114, Proposed (the user's idea): "To measure: the error on stops and sharp turns".

**What to measure.** The overshoot of the predicted cursor on stops and sharp turns, at 120 Hz. It is enabled only if an overshoot is not visible.

**Who answers.** A measure on the reference desktop.

## P-034 — When to freeze `os:core` 0.1.0

**Question.** When does `os:core` 0.1.0 become stable, so that a published component keeps running?

**Where.** D-051 (line 61); [roadmap.md](roadmap.md) line 20; [security.md](../architecture/security.md) line 83 on `main` (the agent's security page must exist first, now written on `origin/main`); [wasm-abi.md](../architecture/wasm-abi.md) line 17 (the promise).

**Options.**
- **A. Now**, once P-022 to P-024 and the security points that touch the contract (P-036, P-037, P-042, P-050) are answered. Gives: outside developers can start. Costs: what the hosted agent finds later becomes a new version, served alongside.
- **B. After hosted step 3** (actions, agent, confirmations, injection attacks: weeks 3-7). Gives: the contract is tested by a working agent before it is promised. Costs: no outside developer before then.
- **C. Stay at 0.x until the alpha.** Costs: no promise to anyone for a year.

**Recommendation.** B: there are no outside developers yet, and the agent is what will find the gaps. *Leaning.*

**Blocks.** Third-party developers. **Depends on** P-022, P-023, P-024, P-036, P-037, P-042, P-050. **Who answers.** Both owners.

---

## Group 3 — Security

The points of this group come from the new [security.md](../architecture/security.md) (on `origin/main`, commit `af51cc5`), whose "Points for the two owners" give fourteen points with a recommendation each; their sources were verified on 16 November 2026 (the "Sources" line of "Security model of the agent"). The three items of P-036, P-037 and P-042 are also marked `OPEN (owners)` in the contracts. Points 15 to 28 were added later on 16 November 2026, from the reviews of the WIT contracts and of the security page and their verifications: P-092 to P-103, and updates to P-049, P-052 and P-055; most are also marked `OPEN (owners)` in the contracts.

## P-035 — What the threat model leaves out

**Question.** Do you accept the list of what the threat model leaves out: compromised firmware, advanced physical attacks, covert timing channels, text-to-text manipulation with no action, a user who confirms without reading, what a remote party does with sent data, denial of service by an application, a malicious project signing threshold?

**Where.** [security.md](../architecture/security.md) lines 78-148 on `origin/main` ("Threat model", Proposed, to validate by the two owners); "Out of scope", lines 137-148.

**Options.** A. As written. B. Count availability as an asset, so denial of service by an application is in scope (the alternative the page gives, line 147). Costs: a gate on availability, beyond the budgets of scheduling.

**No alternative worth a decision, validate as written:** the assets, the adversaries, the trusted list of thirteen components, and the attack walk-through (lines 291-310) as the first list of the injection suite.

**Recommendation.** A: denial of service is already bounded by budgets and the latency contracts. *Leaning.*

**Blocks.** The sign-off of the threat model, which step 0 asks for. **Who answers.** Both owners.

## P-036 — External actions declared harmless (security point 1)

**Question.** How is an action of reach `external` declared `change: none` kept from changing remote state: only `GET` and `HEAD` with no body, to the hosts its manifest lists, or a confirmation for every external action?

**Where.** [security.md](../architecture/security.md) line 178 and point 1 (line 316) on `origin/main`; `DodOS: contracts/core.wit:276-282`, `OPEN (owners)`. The finding: a network capability cannot tell a read from a write, so an action declared `none`, `external` can send a mail or a payment, and the matrix runs it without confirmation in most tasks.

**Options.**
- **A. `GET` and `HEAD` only, no body, to the listed hosts.** Gives: no confirmation for ordinary fetches. Costs: a server that changes state on `GET`, data carried in the address, and a publisher that lists its own host stay possible.
- **B. Confirm every action of reach `external`.** Gives: nothing leaves unconfirmed. Costs: every web fetch asks the user, which feeds confirmation fatigue (P-045).

**Recommendation.** A: it closes the plain case (attack 4 of the walk-through) without confirming every fetch. *Leaning.*

**Blocks.** The manifest (hosts per action); P-034; P-067. **Who answers.** Both owners.

## P-037 — A remote model counts as untrusted (security point 3)

**Question.** Is a task served by a remote model treated as marked `untrusted` for the matrix, with private data sent to a remote model only for a provider the user enabled for it?

**Where.** [security.md](../architecture/security.md) point 3 (line 318) on `origin/main`; `DodOS: contracts/agent.wit:28-34`, `OPEN (owners)`.

**Options.** A. As recommended. Gives: a hostile provider cannot run the automatic cells unseen, such as an external read carrying private data in its address (attack 6). Costs: more confirmations with a remote model. B. Trust the chosen provider, put it on the trusted list, say so to the user. C. Every task counts as `untrusted` for the matrix from its first token, whatever the model. Costs: with P-092, almost every external read is confirmed. D. Local weights not signed by the project count as remote. Costs: a model the user installed is confirmed like a remote one. With A, a hostile local model stays a residual (security.md, row of the hostile model).

**Recommendation.** A: the principle of the page is that the model is not trusted to decide, and D-035 already makes third-party output untrusted. *Firm.*

**Blocks.** The `inference` interface; P-026. **Who answers.** Both owners.

## P-038 — Where inference runs (security point 13)

**Question.** Does llama.cpp run in its own process, with no network and no write to the store, and a remote model reached only through the network service, to the provider's host?

**Where.** [security.md](../architecture/security.md) point 13 (line 328) on `origin/main`. The reason given: llama.cpp is native code that parses third-party model files and reads private data and untrusted content together.

**Options.** A. As recommended. B. Inference inside the agent's process. Costs: a flaw in the model parser reaches the agent's rights.

**Recommendation.** A. *Firm.*

**Blocks.** The agent's services in the hosted track. **Who answers.** Both owners.

## P-039 — A named task service (security point 10)

**Question.** Is the system side of tasks (keeping the marks, applying the matrix, stamping provenance, building each confirmation) a task service of its own, separate from the shell, with its own attack test?

**Where.** [security.md](../architecture/security.md) point 10 (line 325) and the trusted list, item 8 (line 128), on `origin/main`: "The documents name no service and no process for it".

**Options.** A. A separate task service; the compositor draws a confirmation only from what that service hands it. B. Inside the shell. Costs: the shell's large code base becomes the holder of the matrix.

**Recommendation.** A. *Firm.*

**Blocks.** The confirmation path; P-023. **Who answers.** Both owners.

## P-040 — Who chooses the scope of a task (security point 14)

**Question.** When the user makes a request, which actions can its task use: every action of the system services and installed applications minus those the user excluded, or a scope chosen per request by a router?

**Where.** [security.md](../architecture/security.md) line 163 and point 14 (line 329) on `origin/main`, Open.

**Options.** A. Everything minus exclusions. Gives: no component guesses the scope; protection comes from the class, the marks, the journal and revocation. Costs: a steered model can name any installed action (it still meets the matrix). B. A router chooses per request. Costs: one more component to trust, which reads the request. C. The surfaces open and the applications the request names. Costs: "do X" with an application that is not open needs the user to name it.

**Recommendation.** A. *Leaning.*

**Blocks.** The agent's `handle`. **Who answers.** Both owners.

## P-041 — Wording of the rule against the three risks (security point 2)

**Question.** Does D-036 read "no agent task combines private data, untrusted content and external communication **without a confirmation, drawn by the system, of each external or irreversible effect**", or does it forbid the combination outright?

**Where.** [security.md](../architecture/security.md) line 224 and point 2 (line 317) on `origin/main`; D-036 (line 46), Decided as "no task combines them". Meta's "Agents Rule of Two" admits the three under human approval (as the page quotes it).

**Options.** A. The new wording. B. Forbid outright. Costs: "summarise this page and mail it to my accountant" is impossible in one task.

**Recommendation.** A: it is what the matrix already does. *Firm.*

**Blocks.** The text of D-036. **Who answers.** Both owners.

## P-042 — Action descriptions as untrusted text (security point 5)

**Question.** Does reading a third-party action's name, description and schemas mark the task `untrusted`?

**Where.** [security.md](../architecture/security.md) line 179 and point 5 (line 320) on `origin/main`; `DodOS: contracts/actions.wit:189-191`, `OPEN (owners)`.

**Options.** A. Yes. Costs: most tasks that use a third-party application are marked, which under the matrix changes only an external read in a private task and what a confirmation displays. B. Trust signed descriptions. Costs: an injection channel in every manifest (attack 9).

**Recommendation.** A. *Leaning.*

**Blocks.** `available` in `actions.wit`; P-034. **Who answers.** Both owners.

## P-043 — Marks of captures and of the camera (security point 11)

**Question.** Does a screenshot take the union of the marks of the surfaces it shows, and are camera and microphone recordings made outside a request untrusted?

**Where.** [security.md](../architecture/security.md) lines 194-195 and point 11 (line 326) on `origin/main`.

**Options.** A. As recommended. B. No rule. Costs: capturing a hostile page makes it trusted (attack 7).

**Recommendation.** A. *Firm.*

**Blocks.** The capture path of the compositor. **Who answers.** Both owners.

## P-044 — Marks a faulty kernel can drop (security point 4)

**Question.** Do you accept, as a stated limit of the kernel contract, that a faulty kernel on another node can drop the marks it stamps on its messages, and place the processes of one agent task on one node where possible?

**Where.** [security.md](../architecture/security.md) point 4 (line 319) and line 376 on `origin/main`. It touches pass 14B (P-001).

**Options.** A. State the limit and co-locate. B. The receiving node adds to each message the marks of every task it knows on the sending node. Costs: over-marking.

**Recommendation.** A. *Leaning.*

**Blocks.** One line of the kernel contract. **Depends on** P-001. **Who answers.** Both owners.

## P-045 — The number of confirmations (security point 8)

**Question.** Do you accept for version 1 that every external modification is confirmed, measuring confirmations per task on the injection suite, with the hold (P-050) and the grant for the rest of a task as the two levers?

**Where.** [security.md](../architecture/security.md) point 8 (line 323) on `origin/main`. CaMeL and Meta both state the problem is unsolved (as the page cites).

**Options.** A. Accept and measure. B. Fewer confirmations by trusting some publishers. Costs: the injection channels the page closes reopen.

**Recommendation.** A. *Leaning.*

**Blocks.** The injection suite's counters. **Who answers.** Both owners.

## P-046 — No quarantine of untrusted reading in version 1 (security point 9)

**Question.** Do you keep the deferral of labels per value (D-035), so that one untrusted read marks the rest of the task?

**Where.** [security.md](../architecture/security.md) point 9 (line 324) on `origin/main`; D-035.

**Options.** A. Keep the deferral; FIDES's quarantined reading is the design after version 1. B. Bring labels per value into version 1. Costs: a second provenance system before the first is built.

**Recommendation.** A. *Firm.*

**Who answers.** Both owners.

## P-047 — Showing the always-on wake-word microphone (security point 6)

**Question.** While only the wake-word detector listens, does the screen show a discreet permanent mark, the full microphone indicator once the agent listens, and a setting that turns the wake word off?

**Where.** [security.md](../architecture/security.md) line 266 and point 6 (line 321) on `origin/main`; `DodOS: contracts/agent.wit:192`.

**Options.** A. As recommended. B. No mark for the detector. Costs: the microphone indicator is no longer the whole truth. C. The wake word off by default, voice on request. Costs: it touches the Aligned line "Voice detection is always active" (agent.md). The mark does not stop direct scanout (P-098).

**Recommendation.** A. *Firm.*

**Blocks.** The compositor's indicators. **Who answers.** Both owners.

## P-048 — Anyone audible is the user (security point 7)

**Question.** For spoken requests: the transcript shown as heard, no confirmation by voice, and no task on user data while the session is locked?

**Where.** [security.md](../architecture/security.md) line 267 and point 7 (line 322) on `origin/main`.

**Options.** A. As recommended, with a spoken confirmation available as an accessibility setting. B. Allow spoken confirmations. Costs: anyone audible, a loudspeaker included, can confirm (attack 10).

**Recommendation.** A. *Firm.*

**Blocks.** The voice path. **Who answers.** Both owners.

## P-049 — A device that types as a keyboard (security point 12)

**Question.** Is a newly connected input device (keyboard, mouse, touch screen, tablet) accepted only after a key press or a click on a device already accepted, or once the user's code has been typed on it at the lock screen? A device plugged in while the session is locked is not accepted by being plugged in. Updated on 16 November 2026 from the security reviews: a device that clicks can answer a confirmation, so keyboards alone are not enough (P-096).

**Where.** [security.md](../architecture/security.md) point 12 (line 327) on `origin/main`; attack 13.

**Options.** A. As recommended. Costs: one key press or click when plugging a device; friction when a mouse is replaced; a first device is accepted at installation. B. Keyboards only. Costs: a device that reports as a pointer answers a confirmation. C. Accept every device, as other systems do. Costs: a USB stick that types can drive the agent with origin `user`.

**Recommendation.** A. *Leaning*: it adds friction every user sees.

**Blocks.** The input chain. **Who answers.** Both owners.

## P-050 — A hold before an external modification

**Question.** After the user confirms an external modification (a mail, a payment), does the system wait before running it, 10 seconds by default, a setting that allows 0, with the journal entry cancellable during the hold?

**Where.** [security.md](../architecture/security.md) line 218 on `origin/main`, Proposed.

**Options.** A. As proposed. Gives: a window to cancel what cannot be undone. Costs: every sent mail leaves 10 seconds late. B. No hold.

**Recommendation.** A. *Leaning*: the default value is a product choice.

**Blocks.** The journal states in `actions.wit`. **Who answers.** Both owners.

## P-051 — The agent's figure on screen

**Question.** Is the agent shown as a small figure drawn by the compositor, from a closed list of states (idle, listening, thinking, speaking, acting, waiting, stopped), each derived from a fact the system knows, never drawn or chosen by the model?

**Where.** [security.md](../architecture/security.md) lines 240-262 on `origin/main`, Proposed; `DodOS: contracts/agent.wit` (the entity).

**Options.** A. As proposed. B. Expression parameters chosen by the model within bounds (rejected by the page: the figure would no longer be true, and could press the user). C. No figure, only the bar. Costs: the state is no longer visible at a glance.

**Recommendation.** A. *Leaning*: it is also a design choice.

**Blocks.** The shell's design. **Who answers.** Both owners.

## P-052 — JIT in the web content process

**Question.** May the web content process create executable code for LibJS's JIT, the only exception to "only the compile service makes machine code"?

**Where.** [web.md](../architecture/web.md) lines 43-45, Open: "LibJS has had a JIT active by default since October 2026 (PR 12492 and 12613)"; [security.md](../architecture/security.md) line 28.

**Options.**
- **A. Allow it**, for the content process only. Gives: JavaScript speed. Costs: an executable page in a process that runs hostile code; the chain-of-trust rule gets an exception.
- **B. No JIT in version 1**; LibJS's interpreter only. Gives: the rule holds without exception. Costs: slower JavaScript on heavy sites.

**Recommendation.** B for version 1, revisited with measures on real sites. *Leaning.* Whatever the answer, a web application that holds WIT interfaces runs without the JIT (security.md point 26). Alternative for those: follow this answer. Costs: an executable page next to the user's capabilities.

**Blocks.** The Ladybird port; the final wording of the chain of trust. **Who answers.** Both owners.

## P-053 — The account model

**Question.** Is a user a key, the session opened by a code checked by the TPM (the machine's security chip), with no mandatory online account, no superuser, and only one user plus a guest session in version 1?

**Where.** [security.md](../architecture/security.md) lines 42-49, Proposed, to validate.

**Options.** A. As proposed. B. Several users in version 1. Costs: the user zones and their keys tested from the start. C. An online account. Costs: against "the user owns the machine".

**Recommendation.** A. *Leaning.*

**Blocks.** The installer and the session. **Who answers.** Both owners.

## P-054 — A lost key with no escrow

**Question.** If the user loses their code: a recovery key handed over at installation, another device of the circle can give the key back, and the project keeps no copy?

**Where.** [security.md](../architecture/security.md) line 50, Proposed.

**Options.** A. As proposed. Costs: a user who loses the code and the recovery key, with no other device, loses the data. B. An escrow at the project. Costs: the project holds keys to users' data.

**Recommendation.** A. *Leaning*: it is the owners' promise to users.

**Blocks.** The installer. **Who answers.** Both owners.

## P-055 — What the disk key is sealed against

**Question.** Is the disk key sealed in the TPM against the system's signing key rather than against the system's hash, so that an update does not break unlocking?

**Where.** [security.md](../architecture/security.md) line 54, Proposed. "TPM and secure boot: the mechanisms are known but were not re-read" (line 60; [verification-status.md](../research/verification-status.md) line 55); option C's write authority: `reviews/2026-11-16-security-review-2-verify-deepseek-by-mistral.md` finding 7.

**Options.** A. Against the signing key. Costs: any image signed by the project unlocks the disk, including an old one with a known flaw (TCG, TPM 2.0 Library Part 3: Commands, `TPM2_PolicyAuthorize`: every policy signed with the key satisfies it). B. Against the hash. Costs: every update needs the recovery key or a re-seal step. C. Against the signing key and a minimum version in a TPM NV index raised by security updates (`TPM2_PolicyAuthorizeNV`, or a counter). The index is written only under a policy that the signed system satisfies during an update, authorised by the same signing key that authorises the PCR policy: an old image that merely boots holds no such authorisation and cannot lower it. Gives: updates do not break unlocking, and an old signed image no longer unlocks. Costs: one NV index and one write per security update; to verify on the desktop's Intel fTPM (NV indexes or counters, `TPM2_PolicyAuthorizeNV`). If that write authority cannot be built, an old signed image can lower a plain index, C then equals A, and A is the fallback.

**Recommendation.** C (security.md point 24; the mechanism was read at the TCG source by the security review's verifier on 16 November 2026). *Leaning.*

**Blocks.** The installer; updates. **Who answers.** Both owners.

## P-056 — Secure boot route

**Question.** In version 1, does the user enrol the project's key (or their own) in the firmware, with a Microsoft-signed intermediate loader left for later?

**Where.** [security.md](../architecture/security.md) lines 56-60, Proposed. "A Microsoft-signed loader for a non-Linux OS is not verified" ([verification-status.md](../research/verification-status.md) line 55).

**Options.** A. Enrolment by the user in version 1. Costs: an installation step in the firmware's menus. B. Seek a Microsoft-signed loader now. Costs: unverified feasibility.

**Recommendation.** A. *Leaning.*

**Blocks.** The signed image; the installer. **Depends on** P-006. **Who answers.** Both owners.

## P-057 — The project's signing keys

**Question.** Are system images signed through TUF roles with an offline root on hardware keys, two keys out of three (one per owner, one in a safe)?

**Where.** [security.md](../architecture/security.md) line 64, Proposed, to validate.

**Options.** A. As proposed. Costs: three hardware keys and a safe; two owners present to change the root. B. One key per owner, any one signs. Costs: one stolen key signs a hostile image.

**Recommendation.** A. *Firm.*

**Blocks.** The first signed release. **Who answers.** Both owners.

## P-058 — Spread of sticky marks (measure)

**Question.** With marks flowing both ways when a capability is transferred (D-111), how many services and long-lived applications end up marked in normal use?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#open-points), Open points (line 2105); D-111 (line 121).

**What to measure.** On the hosted injection suite, then on the kernel: the services marked after typical sessions, and the confirmations per task. D-111 stands; the number tells whether the rule must be narrowed to capabilities with `write`.

**Who answers.** A measure.

## P-092 — Where the mark `private` comes from (security point 15)

**Question.** Which data carries `private`? Today no rule says so: a file an application saved outside any task carries no mark, so reading the user's files never marks a task `private`, and the one cell of the matrix that depends on it (an external read in a task marked `private` and `untrusted`) never fires.

**Where.** [security.md](../architecture/security.md), "Provenance marks" and point 15; `DodOS: contracts/core.wit` (`provenance`, `OPEN`), `contracts/store.wit` (`object-info`); found by three reviewers (`reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` N9, `security-review-1-verify-hydrogen-by-opus.md` N1, `security-review-1-verify-deepseek-by-mistral.md` finding 1); second round: `security-review-2-verify-deepseek-by-mistral.md` finding 2, `wit-review-2-verify-hydrogen-by-deepseek.md` finding 2.

**Options.**
- **A. By zone, at read.** The storage service adds `private` to every read from the user, application, snapshot and device zones; cache and ephemeral keep the writer's marks; system and packages no `private`; `untrusted` follows the writer and the origin; a collection bound to a call marks it by its zone; every route out of a surface (accessibility tree, a selection copied or cut, an item dragged out, a capture) adds `private` always and `untrusted` unless the owner is the system, and a store object leaving that way keeps its own marks too. Gives: the matrix's cell fires on the user's data, including data already stored and data copied off the screen. Costs: almost every task that touches the user's data or an application's `home` is `private`; once also `untrusted` (P-037, P-042 make that frequent), every external read is confirmed, and a remote model without leave for private data is refused; a task that began with a pasted public page pays one confirmation per external read.
- **B. By writer, as today.** Gives: no confirmation added. Costs: the confirmation D-036 relies on almost never appears.
- **C. The application zone only when its manifest asks.** Gives: fewer confirmations for feed readers, weather or maps. Costs: an application that forgets leaves its secrets unmarked, and the producer decides, against "never by the producer".
- **D. Downloads excluded.** Gives: fewer confirmations after reading public files. Costs: a downloaded bank statement is unmarked unless the user marks it.

**Proposed today.** A is written in the page and the contracts. Stamping `private` at write time was rejected: it misses data already stored.

**Recommendation.** A; the injection suite counts the confirmations it adds (P-045, P-058). *Leaning.*

**Blocks.** The storage service's marks; the matrix. **Who answers.** Both owners.

## P-093 — A local write of a package that holds the network (security point 16)

**Question.** An action of change `reversible`, reach `local`, writes into `home`, a kept item or a bound item with `write`; the long-lived instance of the same package holds the right "network" and runs outside any task, or another action of the package has hosts and reads `home`; either can send what was written. How is that kept from defeating the matrix?

**Where.** [security.md](../architecture/security.md), "Effect class" and point 16; `DodOS: contracts/core.wit` (`world service`, `OPEN`), `contracts/actions.wit` (`invoke`); `reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` N1 and C2, and the alternatives table of `wit-review-1-verify-opus-new-findings-by-hydrogen.md` ("Deep comparison"); second round: `security-review-2-verify-deepseek-by-mistral.md` findings 1 and 3, `wit-review-2-verify-hydrogen-by-deepseek.md` finding 1.

**Options.**
- **A. In a task marked `untrusted`, decided as an external modification** (confirmed, held, counted in the external budget, not undoable once done), for every package that can reach the network (the right "network", or hosts on any of its actions), on the class at `invoke` whatever the instance then writes to; automatic in an unmarked task. Gives: no silent path in a marked task, including the two-step path of a local write then an external action of the same package. Costs: confirmations for the writes of networked applications in marked tasks; the residual of a hostile application, or a hostile local model, in an unmarked task stays, stated in the threat model.
- **B. The same in every task.** Costs: every edit of a syncing application asks (a note saved, an event added; five items checked are five confirmations), even with no mark.
- **C. A read-only or separate `home` for action instances.** Gives: no confirmation. Costs: stateful actions of networked applications break (mail drafts, an application's own database, an MCP adapter's token).
- **D. The network service refuses a request from a sender marked `private` and `untrusted` unless the task service confirmed.** Gives: no confirmation at `invoke`. Costs: the confirmation would carry no typed input, only a raw request; an honest application loses background sync after any marked edit, since its long-lived instance takes the marks of what it reads.

**Proposed today.** A, with a known limit: an instance of change `none` and reach `external` can send its own `home` to the hosts of the action (it gets no `keep`, P-094); what entered `home` from a marked task was confirmed under A.

**Recommendation.** A. *Leaning*: it reopens a line of security.md that rests on D-035.

**Blocks.** `invoke` and `world service` in the contracts. **Who answers.** Both owners.

## P-094 — `keep` in an action instance (security point 17)

**Question.** The fresh instance of an action imports `keep`, the component's table of kept capabilities. What may it do with it?

**Where.** [security.md](../architecture/security.md) point 17; `DodOS: contracts/core.wit` (`world service`), `contracts/store.wit` (`keep`); `reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` finding 1 and C3, `wit-review-1-verify-hydrogen-by-deepseek.md` finding 1; second round: `wit-review-2-verify-hydrogen-by-deepseek.md` finding 1.

**Options.**
- **A. Read only**: `get` and `slots`, `get` attenuated to the class, `put` and `forget` refused; in an instance of change `none` and reach `external`, every call refused. Gives: nothing the request carried is kept as a capability (what the instance writes is P-093's subject); an action can use a capability the application kept, except one that only reads from outside, which was the one way a folder the user picked reached an instance that can send without marking the call. Costs: none in confirmations.
- **B. `keep` refused entirely.** Gives: the instance holds strictly what its request carries. Costs: an action cannot use a folder the user picked once; the request must carry it.

**Recommendation.** A. *Firm.*

**Blocks.** `world service`. **Who answers.** Both owners.

## P-095 — Secret fields (security point 18)

**Question.** A secret field can feed any property of an action, and a reversible local action that receives the password runs unconfirmed and writes it into the journal. What are the rules?

**Where.** [security.md](../architecture/security.md), "Confirmation matrix" and point 18; `DodOS: contracts/catalog.wit` (`field`), `contracts/manifest.wit` (`os-secret`); `reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` N2 and C1 with Hydrogen's amendment, `security-review-1-verify-deepseek-by-mistral.md` C2; `wit-review-2-verify-hydrogen-by-deepseek.md` finding 3.

**Options.**
- **A.** A secret field feeds only a property marked `os-secret`, judged on the tree an update leaves; an action that receives a secret is confirmed whatever its class, the secret shown masked and written as null in the journal; a secret field on the agent's overlay is refused while the task is marked `untrusted`, needs at least one button that reads it, and stops answering once the task is marked; a literal for an `os-secret` property in the call's input is refused (`invalid`); on an application's own surface the owner receives its own secret field's value in the event (the user typed it for that application), and the system never journals it, never gives it to the agent, and never exposes it through `accessibility`. Costs: one confirmation per secret handed over; the grant for the rest of a task covers repeats in an unmarked task.
- **B. The matrix alone, as before.** Costs: a password reaches a reversible local action unconfirmed.

**Recommendation.** A. *Firm.*

**Blocks.** The catalogue's checks; `invoke`. **Who answers.** Both owners.

## P-096 — Answering a confirmation (security point 19)

**Question.** Which input answers a confirmation, and when does it take the focus?

**Where.** [security.md](../architecture/security.md), "Proposed rules for the confirmation itself" and point 19; `reviews/2026-11-16-security-review-1-verify-deepseek-by-mistral.md` finding 6 and C7, `security-review-1-verify-hydrogen-by-opus.md` correction 6 and Q5.

**Options.**
- **A.** A click or a touch on it, or Return or Space while it holds the focus; it takes the focus only when the user moves it there; a keystroke begun before it appeared cannot reach it; and every new device that can give origin `user` is accepted first (P-049). Costs: no confirmation added; the friction of P-049.
- **B. Any key while it holds the focus, as before.** Costs: a keystroke meant for another window answers it.
- **C. A, with keyboards alone accepted.** Costs: a device that clicks answers it.

**Recommendation.** A. *Firm.*

**Blocks.** The compositor's confirmation; P-049. **Who answers.** Both owners.

## P-097 — Captures and system material (security point 20)

**Question.** Does a screenshot or recording made by an application include the confirmation, the secure attention view and the indicators?

**Where.** [security.md](../architecture/security.md), "Provenance marks" and point 20; `reviews/2026-11-16-security-review-1-verify-deepseek-by-mistral.md` finding 10 and C3.

**Options.**
- **A. Blanked** in every captured frame not made by the system. Costs: no confirmation added; a recording shows blank areas.
- **B. The capture's marks only, as today.** Costs: an application with the capture right sees a confirmation and sends it with its own network right.

**Recommendation.** A. *Firm.*

**Blocks.** The compositor's capture path. **Who answers.** Both owners.

## P-098 — Direct scanout and system elements (security point 21)

**Question.** When a full-screen surface is scanned out directly, what happens when a system element must be shown?

**Where.** [ui.md](../architecture/ui.md#compositor) and [security.md](../architecture/security.md) point 21; `reviews/2026-11-16-security-review-1-verify-hydrogen-by-opus.md` finding 2 and Q4.

**Options.**
- **A. Scanout stops for every system element**, the detector's discreet mark included. Costs: no direct scanout while the wake word is on.
- **B. It stops for a confirmation, the secure attention view and the full microphone, camera and capture indicators, not for the discreet mark.** Costs: the discreet mark is not shown over a full-screen surface.
- **C. System elements on a hardware plane** above the scanout plane, if the GPU trial shows planes (gpu.md, from memory).

None adds a confirmation; the latency gate is measured with no system element shown.

**Recommendation.** B now, C if the GPU trial shows planes. *Leaning.*

**Blocks.** The compositor; the latency gate's conditions. **Depends on** P-073. **Who answers.** Both owners.

## P-099 — A button that carries an action (security point 22)

**Question.** The catalogue's `button` can carry an action "through the task", but an application's surface has no task. Where may such a button appear, and in which task does it run?

**Where.** [security.md](../architecture/security.md), "Delegation by task" and point 22; `DodOS: contracts/catalog.wit` (`button`), `contracts/ui.wit` (`update`); `reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` N5, judged by Hydrogen (C9 wrong), `wit-review-1-verify-hydrogen-by-deepseek.md` N1, `security-review-1-verify-deepseek-by-mistral.md` N5.

**Options.**
- **A.** Refused on an application's own surface; on the agent's overlay, in the overlay's task; on a notification, only an action of the notifying package, with no bound item, in a task opened for that one call, marked `untrusted`, whose scope is that action; the click is not a confirmation. Costs: no confirmation added.
- **B. On an application surface, the owner's own actions in a one-call task** (Hydrogen's replacement). Costs: less strict, and it gives nothing the application cannot do by handling its own events.
- **C. Any action from any surface in a one-call task.** Costs: one click on a hostile application's button runs another application's local actions unconfirmed and hands their output to the hostile one. Rejected.

**Recommendation.** A. *Leaning*: notifications have no interface yet.

**Blocks.** The catalogue's checks; the notification interface. **Who answers.** Both owners.

## P-100 — Third-party words in a confirmation (security point 23)

**Question.** The confirmation is drawn from the action's schema, whose titles and descriptions the publisher wrote. May they appear in system material?

**Where.** [security.md](../architecture/security.md), "Confirmation matrix" and point 23; `reviews/2026-11-16-security-review-1-verify-deepseek-by-mistral.md` finding 5 and C6.

**Options.**
- **A. Schema titles shown outside system material, labelled with the publisher's name**; nothing a publisher or a model wrote in system material.
- **B. No schema titles or descriptions at all.** Costs: raw property names are unreadable.
- **C. As before, unstated.** Costs: glass vouches for the publisher's words.

None changes the number of confirmations.

**Recommendation.** A. *Firm.*

**Blocks.** The drawing of confirmations. **Who answers.** Both owners.

## P-101 — Dependency changes in the maintenance lane (security point 25)

**Question.** Does a dependency change that alters what ships in a signed image still merge alone in the maintenance lane when the checks pass (D-032)?

**Where.** [security.md](../architecture/security.md), row "Compromised dependency or build" and point 25; D-032; `reviews/2026-11-16-security-review-1-verify-hydrogen-by-opus.md` finding 9.1 and Q8.

**Options.**
- **A. As D-032.** Costs: a compromised dependency, port, pin or firmware blob reaches a signed image with no review.
- **B. A change to what ships in a signed image (lockfiles, vcpkg ports, Nix pins, firmware blobs, build scripts) needs the review of another model family**, as the function lane does. Costs: one more review on those changes; it reopens D-032 for that one case.
- **C. Such changes go to the contract lane**, reviewed by humans. Costs: slow for every pin.

**Recommendation.** B. *Leaning.*

**Blocks.** D-032; the CI of the three repositories. **Who answers.** Both owners.

## P-102 — A grant for the rest of a task and a later mark (security point 27)

**Question.** The user allows an action for the rest of an unmarked task; the task is marked `untrusted` afterwards. Does the grant survive, and what does it cover?

**Where.** [security.md](../architecture/security.md), "Proposed rules for the confirmation itself" and point 27; `DodOS: contracts/actions.wit` (`invoke`); `reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` finding 5 and C4, `security-review-1-verify-hydrogen-by-opus.md` N10, `security-review-1-verify-deepseek-by-mistral.md` C8; second round: `wit-review-2-verify-hydrogen-by-deepseek.md` finding 2.

**Options.**
- **A. The grant ends when the task takes the mark**; an object argument is pinned to its version; a call that binds a collection is never covered by the grant and asks when the matrix asks. Costs: one more confirmation in a task marked after the grant.
- **B. The grant survives the mark.** Costs: injected steps can repeat the call unconfirmed.

**Recommendation.** A. *Firm.*

**Blocks.** `invoke`. **Who answers.** Both owners.

## P-103 — `focus-surface` (security point 28)

**Question.** The shell's action `focus-surface` is class `none`, so it runs automatically, but it decides where the user's next keys go. What limits it?

**Where.** [security.md](../architecture/security.md) point 28; `DodOS: contracts/shell.wit`; `reviews/2026-11-16-wit-review-1-verify-deepseek-by-opus.md` finding 4 and C7, judged partly right by Hydrogen.

**Options.**
- **A.** `denied` for the agent's bar and for a confirmation; `busy` while the user types into another surface (keys typed into the bar do not count, so "focus the terminal" works at once); no window that drops keys; confirmed in a task marked `untrusted`. Costs: one confirmation per focus change in a marked task.
- **B. Automatic in every task, with `busy` and 500 ms of dropped keys** (the first proposal). Costs: it breaks a focus request typed in the bar, and lets a steered task move the focus after a pause.
- **C. Class `none`, as before.** Costs: a steered task sends the user's next keys to another application.

**Recommendation.** A. *Leaning.*

**Blocks.** The shell's actions. **Who answers.** Both owners.

---

## Group 4 — Storage, memory, platform, network, media, devices

## P-059 — How long versions are kept

**Question.** Does the store keep every version for 30 days, then one per day, then one per week, adjustable?

**Where.** [storage.md](../architecture/storage.md) line 81, open point 4 with a proposed answer; the contract defers to it (`DodOS: contracts/store.wit`, "the system's retention policy").

**Options.** A. As proposed. B. Keep everything until space is needed. Costs: unpredictable disk use. C. Shorter. Costs: fewer undos.

**Recommendation.** A. *Leaning.*

**Blocks.** The storage service. **Who answers.** Both owners.

## P-060 — Packages shared between users, unencrypted

**Question.** Are packages installed by one user visible to the others, in a machine zone that is not encrypted, with a private installation going into the user's zone?

**Where.** [storage.md](../architecture/storage.md) line 83 (open point 6) and line 47 (the Packages zone: not encrypted).

**Options.** A. As proposed. Gives: one copy of each application, compiled once. Costs: anyone with the disk sees which applications are installed. B. Packages in each user's encrypted zone. Costs: no deduplication across encrypted zones (D-045), so one copy per user.

**Recommendation.** A. *Leaning*: it is a privacy trade-off.

**Blocks.** The zones; the installer. **Who answers.** Both owners.

## P-061 — Backup in version 1

**Question.** Where can the user back up in version 1: a device of the circle, an external disk, S3-type object storage?

**Where.** [storage.md](../architecture/storage.md) lines 107-114, Proposed, to validate. Devices of the circle are deferred to 2028 (D-065).

**Options.** A. All three, as written. B. External disk in version 1; the circle with device communication in 2028; object storage with the commercial model. C. None in version 1.

**Recommendation.** B: the circle does not exist before 2028 and a paid backup belongs to P-081. *Leaning.*

**Blocks.** The storage service. **Depends on** P-081. **Who answers.** Both owners.

## P-062 — Copy on write in the memory service

**Question.** Does the memory service offer copy on write in version 1, or with the snapshot work?

**Where.** [kernel-interface.md](../architecture/kernel-interface.md#open-points), Open points (line 2104).

**Options.** A. In version 1. Costs: more code in the memory service now. B. With the snapshot work. Costs: no cheap copy of a memory object in version 1.

**Recommendation.** B: periodic snapshots are deferred after the alpha (D-025), and the kernel already allows copy on write in user space (D-095). *Leaning.*

**Blocks.** The memory service's scope. **Who answers.** One owner.

## P-063 — Who loads processor microcode

**Question.** Is processor microcode a system blob loaded by the kernel at boot, or applied by the first stage before the kernel starts?

**Where.** [platform.md](../architecture/platform.md) line 22, Proposed: "loaded by the kernel at boot".

**Options.** A. The kernel. Costs: a microcode loader in the kernel's hardware layer, per vendor. B. The first stage (P-006), which hands the kernel a machine already updated. Gives: the kernel stays smaller.

**Recommendation.** B, since D-125 gives each platform a first stage. *Leaning.*

**Blocks.** The start-up path. **Depends on** P-006. **Who answers.** One owner.

## P-064 — Does the desktop sleep in version 1

**Question.** Does the desktop have no sleep at first (screen off, idle states, frequency by the hardware), with sleep only on the laptop (modern standby)?

**Where.** [platform.md](../architecture/platform.md) lines 72-77 (no status line); the gate "wake from sleep ≤ 0.5 s" is Proposed ([gates.md](gates.md) line 26).

**Options.** A. As written. Costs: the desktop never sleeps. B. Sleep on the desktop in version 1. Costs: every emulated Linux driver must replay its suspend callbacks earlier.

**Recommendation.** A. *Leaning.*

**Blocks.** The power service. **Who answers.** Both owners.

## P-065 — Dual boot in the installer

**Question.** Does the installer allow DodOS beside another system, on a dedicated disk or free space, without resizing the other system's partitions in version 1?

**Where.** [platform.md](../architecture/platform.md) lines 79-86, Proposed, to validate.

**Options.** A. As proposed. B. Whole disk only. C. With resizing. Costs: the risk of damaging the other system.

**No alternative worth a decision, validate as written:** the USB image as an ephemeral session, the recovery slot's contents, firmware updates by UEFI capsules (the source LVFS is "from memory, to verify").

**Recommendation.** A. *Leaning.*

**Blocks.** The installer. **Who answers.** Both owners.

## P-066 — Server administration without SSH

**Question.** Is a DodOS server administered only through `dodo` and the agent, over the key-addressed transport with delegated capabilities, with no remote root shell?

**Where.** [platform.md](../architecture/platform.md) lines 113-119, Proposed, to validate.

**Options.** A. As proposed. Gives: nothing listening on the internet. Costs: administrators' usual tools do not work. B. Also an SSH service. Costs: a root-like shell against "no superuser".

**Recommendation.** A: the server image is sold on recovery and safety. *Leaning.*

**Blocks.** The server image. **Who answers.** Both owners.

## P-067 — Network rights per host and port

**Question.** Does an application's network capability carry its scope (hosts, ports, direction), with no separate firewall and every unmatched incoming packet dropped?

**Where.** [network.md](../architecture/network.md) lines 17-33, Proposed, to validate.

**Options.** A. As proposed. Costs: manifests list hosts; the user sees them at installation. B. One "network" right. Costs: P-036 loses its declared hosts.

**No alternative worth a decision, validate as written:** encrypted DNS by default, mDNS locally, WireGuard as a component, ports opened by a listening capability, rate limiting in the network service.

**Recommendation.** A. *Firm.*

**Blocks.** The network service; the manifest. **Depends on** P-036. **Who answers.** Both owners.

## P-068 — Who runs the relay

**Question.** Who runs the relay that key-addressed services connect to: the project, the user, or a third party?

**Where.** [network.md](../architecture/network.md) lines 35-39 and [devices.md](../architecture/devices.md) lines 20-25: a relay is needed and "sees who talks to whom"; no document says who runs it. A relay service is one of the commercial candidates ([open-questions.md](../research/open-questions.md) line 75).

**Options.** A. The project runs it. Costs: a service to pay for and operate. B. The user's own relay, configured. C. A third party's.

**Recommendation.** Decide with P-081. *Toss-up.*

**Blocks.** Key-addressed services; server administration (P-066). **Depends on** P-081. **Who answers.** Both owners.

## P-069 — The network stack (trial)

**Question.** Does the project extract Netstack3 from the Fuchsia tree itself, or fall back on the NetBSD stack (rump)?

**Where.** [network.md](../architecture/network.md) lines 5-13, Open, "trial with priority". The published crate `netstack3-core` 0.1.0 comes from an anonymous account with no source repository, verified 13 November 2026.

**What to do.** An agent extracts the Netstack3 core and reports the gap with upstream. Then the owners choose.

**Who answers.** A trial, then both owners.

## P-070 — H.264 and AAC in version 1

**Question.** Does version 1 decode H.264 and AAC, through FFmpeg and Vulkan Video?

**Where.** [media.md](../architecture/media.md) line 9, Proposed: "patents to put to legal counsel".

**Options.** A. Yes. Costs: patent exposure, P-080. B. Free codecs only (AV1, VP9, Opus, FLAC). Costs: much of the web's video and audio does not play.

**Recommendation.** Wait for P-080. *Leaning* towards A if counsel finds a path.

**Blocks.** The media components. **Depends on** P-080. **Who answers.** Both owners, after counsel.

## P-071 — Protected video (Widevine)

**Question.** Does the project accept, for now, that protected video does not play, with casting from another device as the way round?

**Where.** [media.md](../architecture/media.md) lines 11-15, Proposed. The user reported that the independent browser Zen received a Widevine licence on 14 November 2026; this was "not found again by search".

**Options.** A. Accept the limit, re-evaluate with volume. B. Seek a licence now. Costs: unknown conditions; a protected module inside a capability system.

**Recommendation.** A. *Leaning.*

**Blocks.** The browser. **Who answers.** Both owners.

## P-072 — The system font family

**Question.** Which font family under the OFL licence is the system's, with Noto for scripts and emoji?

**Where.** [media.md](../architecture/media.md) line 23, Proposed: "One system family under the OFL licence"; no family is named.

**Options.** A. Choose now. B. Choose with the single token file of the design system ([ui.md](../architecture/ui.md) line 80).

**Recommendation.** B: the family is part of the type scale. *Leaning.*

**Blocks.** The design tokens. **Who answers.** One owner.

## P-073 — The GPU trial (measure)

**Question.** Does NVIDIA's OS-independent core compile outside Linux, with display planes, channel priorities and llama.cpp on NVK, confirming direct scanout (D-050) and the GPU route (D-009)?

**Where.** [gpu.md](../architecture/gpu.md) lines 23 and 28-33; D-050 (line 60); [progress.md](progress.md) line 34. NVK's performance on the reference card is Open; the figure "less than half of the proprietary driver" on an RTX 5080 is confirmed in direction, not in value ([verification-status.md](../research/verification-status.md) line 77).

**What to measure.** The two weeks D-050 describes; NVK's performance on the reference card; whether the NVIDIA core exposes hardware planes and channel priority without its Linux layer (from memory, gpu.md line 33).

**Who answers.** A trial on the reference desktop.

## P-074 — Wake word during sleep (measure)

**Question.** Can the Dell's signal processor, with the manufacturer's signed SOF firmware, run a keyword detector that wakes the machine?

**Where.** [platform.md](../architecture/platform.md) line 77: "a goal, not yet achieved … To test on the Dell". On the desktop: light sleep with a detector on the processor, or a USB microphone with a microcontroller.

**What to measure.** On the Dell: whether the signed firmware carries the needed module and accepts a model. The answer says whether the agent can be called during sleep.

**Who answers.** A measure on the Dell.

## P-075 — Calibrate the gates (measure)

**Question.** Which targets do the latency gates and the overhead gates marked "To set" take, before their ratchets are armed?

**Where.** [gates.md](gates.md) lines 13-26 and 40-59; the boot baselines of Linux, Windows and macOS on the same machine (line 32); the shutdown delay of 500 ms (D-081, line 91).

**What to measure.** On the reference desktop, with a photodiode at 120 Hz for latency; each "To set" line against its reference. Calibration comes before the ratchet (D-064); no gate is armed before it.

**Who answers.** A measure; it also needs the hardware-in-the-loop rig ([verification.md](verification.md) line 44) set up by the owners.

**No alternative worth a decision, validate as written (group 4):** the two partitions; the zones other than packages; one disk in version 1 and mirroring later (open point 2); quotas carried by the collection's capability (point 3); compression in memory in version 1 and encrypted overflow later (point 5, and memory.md lines 53-56); blobs deduplicated across packages; the rules of [memory.md](../architecture/memory.md) (memory objects, pressure order, zeroing, pinned memory for drivers, protections); wall-clock time as an NTS service with time zones as a blob; shutdown and crash on one path; printing by driverless protocols after version 1; the order of deployment surfaces; the embedded rules; the scheduling rules of [scheduling.md](../architecture/scheduling.md) (time in interrupts charged to the running context, real time, latency contracts, starting values); GPU classes and the order under GPU memory pressure ([gpu.md](../architecture/gpu.md)); the driver framework and manifests deduced from traces ([drivers.md](../architecture/drivers.md)); declarative wiring in the system hash ([overview.md](../architecture/overview.md) line 83); free codecs first, AV2 later; hardware video decoding as upstream allows. [devices.md](../architecture/devices.md) is deferred to 2028 (D-065): nothing in it needs a decision before then.

---

## Group 5 — The project's own questions

## P-076 — When to engage legal counsel

**Question.** Do you brief legal counsel now with the four questions of P-077 to P-080, or wait for the first outside contribution or the first commercial contact?

**Where.** [open-questions.md](../research/open-questions.md) lines 84-91; D-047 (line 57), D-119 (line 129): "These choices go to legal counsel".

**Options.** A. Now, one brief. Costs: fees now. B. Later. Costs: a contributor who arrives first must wait (P-077), and the licence of the emulation layer stays unconfirmed while drivers are written under it.

**Recommendation.** A. *Leaning.*

**Blocks.** P-077 to P-080. **Who answers.** Both owners.

## P-077 — The contributor agreement

**Question.** Which form of contributor agreement: a contribution licence with the right to relicense, or an assignment of rights; and what is the status of code written by agents?

**Where.** [open-questions.md](../research/open-questions.md) line 89, Open; D-119 (line 129): needed before the first outside contribution, because the commercial licence requires that the project holds every right.

**Proposed today.** A licence with the right to relicense, rather than an assignment.

**Blocks.** The first outside contribution. **Depends on** P-076. **Who answers.** Legal counsel, then both owners.

## P-078 — Licence of the Linux emulation layer

**Question.** Is it right that the emulation library can be published under MIT while the whole driver process is under GPLv2, talking to the rest by IPC?

**Where.** D-047 (line 57) and [drivers.md](../architecture/drivers.md) line 41: "to be confirmed by legal counsel".

**Blocks.** The driver processes. **Depends on** P-076. **Who answers.** Legal counsel.

## P-079 — Reading other kernels' code

**Question.** Does the agents' reading of other kernels' code (seL4 under GPLv2, Asterinas under MPL-2.0), with no translation and no copy, allow a commercial licence of the kernel?

**Where.** [verification.md](verification.md) line 135: "A legal opinion is needed before a commercial version"; D-023.

**Blocks.** The commercial licence. **Depends on** P-076. **Who answers.** Legal counsel.

## P-080 — Patents on H.264 and AAC

**Question.** What exposure does decoding H.264 and AAC carry, and on what terms?

**Where.** [media.md](../architecture/media.md) line 9; [open-questions.md](../research/open-questions.md) line 91.

**Blocks.** P-070. **Depends on** P-076. **Who answers.** Legal counsel.

## P-081 — Who buys

**Question.** Which of the four candidates does the project pursue first: a commercial licence for device makers who do not want the AGPL, support and licence on the server side, optional services (relay, backup, store), a reference machine?

**Where.** [open-questions.md](../research/open-questions.md) lines 69-76, "Open; to settle".

**Options.** A. Commercial licence. Needs P-077 and P-079. B. Server support and licence. Needs the server image. C. Optional services. Needs operations (P-061, P-068). D. A reference machine. Needs hardware partners.

**Recommendation.** A and B first: the dual licence is already decided (D-014) and the server image is a decided milestone with its argument (recovery of one kernel). *Leaning.*

**Blocks.** P-061, P-068. **Who answers.** Both owners.

## P-082 — The name

**Question.** Does the project keep the name DodOS, with the domain `dod-os.org` and a trademark search, or choose another name before the first public demonstration?

**Where.** [open-questions.md](../research/open-questions.md) lines 78-82: `dodos` taken on GitHub, `dodos.org` and `dodos.io` taken, `dod-os.org` free (verified 14 November 2026); the trademark is not verified. Line 82 also says the repository `Vehicoule/dodOS` is "empty": it is not (it holds the contracts, `verify` and CI).

**Options.** A. Keep DodOS: register the domain, search the trademark. B. A new name before the demonstration.

**Recommendation.** Decide before the demonstration, after a trademark search. *Leaning.*

**Blocks.** P-088. **Who answers.** Both owners.

## P-083 — Telemetry

**Question.** No telemetry by default, a crash report leaving the machine only with the user's agreement, report by report?

**Where.** [open-questions.md](../research/open-questions.md) lines 93-95, Proposed; [platform.md](../architecture/platform.md) line 66.

**Options.** A. As proposed. B. Opt-in usage statistics as well.

**Recommendation.** A. *Firm.*

**Blocks.** Crash reporting. **Who answers.** Both owners.

## P-084 — The integration repository

**Question.** Is a separate integration repository that pins every repository still needed, or is the system repository's pin of the kernel the integration point?

**Where.** [roadmap.md](roadmap.md) line 18 and [verification.md](verification.md) line 31 plan an integration repository; [thesis.md](../thesis.md) line 22 (D-087) says the system repository "pins the kernel by commit, and moving the pin runs the system's checks". With two code repositories the two overlap.

**Options.** A. A separate integration repository. Costs: a third place to keep green. B. The system repository's pin. Gives: one less repository. Costs: an integration repository comes back when the repositories split further.

**Recommendation.** B. *Leaning.*

**Blocks.** Step 0. **Who answers.** Both owners.

## P-085 — The template repository

**Question.** Is the template repository of Step 0 made now, though the three repositories already exist with their CI?

**Where.** [roadmap.md](roadmap.md) line 18.

**Options.** A. Now. B. When the next repository is created.

**Recommendation.** B: no new repository is planned before the split. *Leaning.*

**Blocks.** Step 0. **Who answers.** Both owners.

## P-086 — Branch protection and code owners

**Question.** Do you turn on now, on the three repositories, branch protection, `CODEOWNERS` over the contract lane (tests, oracles, workflows, `AGENTS.md`, budgets, the contract and `abi/`) and a merge queue?

**Where.** [verification.md](verification.md) lines 23-25; none of the three repositories has them on 16 November 2026 (the inventory checked the GitHub settings). Only the owners can set them.

**Options.** A. Now. B. When outside contributors arrive. Costs: until then an agent can merge into the contract lane.

**Recommendation.** A: the harness's first rule is that an agent cannot merge alone. *Firm.*

**Blocks.** The protection of the contract lane. **Who answers.** Both owners.

## P-087 — The list of checks per stage

**Question.** Do you accept the list of checks per stage as written, or ask for a review first?

**Where.** [verification.md](verification.md) lines 33-47, Proposed, "awaits a review (Open)".

**Options.** A. Accept; each check enters CI with the code it guards. B. A review by agents of another family first.

**Recommendation.** A: the rule "a check enters with the code it guards" already makes it grow as needed. *Leaning.*

**Blocks.** The growth of CI. **Who answers.** Both owners.

## P-088 — The first public demonstration

**Question.** Is the first public demonstration the agent acting safely on applications in the hosted userland (hosted steps 1 to 3) and the kernel booting under QEMU and passing the oracle, in weeks 3-7?

**Where.** [roadmap.md](roadmap.md) lines 68-70, Proposed; the calendar, line 55.

**Options.** A. As proposed. B. The hosted agent only. Gives: earlier. Costs: the kernel, "the part that sells" (thesis), is not shown.

**No alternative worth a decision, validate as written (group 5):** the development workflow (one trunk, short branches, linear history, signed commits, three lanes), the cost of agents, the publications after the demonstration (D-076).

**Recommendation.** A. *Leaning.*

**Blocks.** The position paper (D-076). **Depends on** P-082. **Who answers.** Both owners.
