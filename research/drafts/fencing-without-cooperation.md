# Fencing a failed node without its cooperation

Written 15 November 2026 for the two owners, in answer to D-116 (1). Nothing under `/Users/btw/Documents/repos` was edited. It builds on `symmetric-nodes-recovery.md`, `ownership-alternatives.md` and `nodes-memory-devices.md` (Docs/research/drafts), `kernel.md`, and D-093, D-107, D-108, D-114, D-115 and D-116.

**Verification marks.**
- **Verified** means read today in the primary source: the vendor manual, the specification, the paper's PDF or the source code. The source is in part 10.
- **(arithmetic)** means a figure I computed from verified inputs.
- **Not verified** means exactly that.
- **(inference)** marks a conclusion of mine that no single source states.

Four research passes gathered the sources; their texts and extracts are in the scratchpad folders `x86/`, `arm/`, `rv/` and `pdfs/`. I re-read the load-bearing quotes myself in those extracts: the Arm masking rule RXBYXL, the TLB-completion rules RQRNJC, ISTPSQ, ILXHLD and IYNJCP, the SDM rules on external-interrupt exiting, INIT and NMI in SMM, the RISC-V HS trap rule, AMD INVLPGB and R_INIT, Intel RAR, and the cycle tables of Dune, Hyperkernel, Gandhi and NOVA.

---

## 0. Verdict

1. **The requirement is not "stop the core". It is "revoke what the core can reach, and make the core fall into code we trust".** Every architecture we target has a level under the kernel that the kernel cannot mask: VMX root on x86-64, EL2 on ARM64, HS-mode (and M-mode) on RISC-V. If each node runs as a guest of a small monitor at that level, with second-stage translation that maps only the node's own chunks, then:
   - **x86-64.** An NMI forces the node into its monitor. With "NMI exiting" and "virtual NMIs" set, the guest cannot block it except for one instruction after STI or MOV SS. INIT is no longer needed, so the boot processor (BSP) is no longer special. Verified, SDM.
   - **ARM64.** Another core can cut the node's memory access with no code on the target. It clears the node's stage-2 root, then issues TLBI VMALLS12E1IS and DSB ISH. The Arm ARM guarantees that, once this completes, "no new memory accesses using the in-scope old translation information are architecturally performed by any observer". The target's next memory access then faults into its monitor. Verified, Arm ARM D8.17.
   - **AMD.** INVLPGB with the nested bit, followed by TLBSYNC, does the same, and TLBSYNC also waits until "writes using the translations have drained". Verified, APM vol. 3.
   - **RISC-V.** The standard SBI remote fence `sbi_remote_hfence_gvma_vmid` is executed by M-mode on the target hart. S-mode and HS-mode cannot mask that interrupt. Verified, OpenSBI source and the privileged spec.
2. **Cooperation does not disappear: it moves from the whole kernel to the monitor.** A hung or wild kernel can no longer prevent its own fence. A monitor that hangs with its interrupts masked still could, and so could a core whose hardware has failed.
   - The monitor can be a few thousand lines with no unbounded loop. Proofs of that size exist on ARMv8 multiprocessors: SeKVM's KCore, 3.8 K lines, about two person-years, and seL4 AArch64 in EL2.
   - The hardware residue is the same for every design, including the present one, and part 5 states it plainly.
3. **The cost on the common paths is small if the monitor stays out of them.**
   - **No exit** on system calls, IPC on one node, page faults or device interrupts. The monitor does not virtualise interrupts on x86-64 or on ARM64 (IMO = 0), and on RISC-V it uses AIA guest interrupt files.
   - **One extra exit** on memory takes, gives and shares between nodes (2 MB-granular, rare), and optionally on each IPI between nodes.
   - **TLB misses** pay a two-stage walk. With 2 MB or 1 GB stage-2 blocks, which DodOS chunks give for free, the measured costs are:
     - 0.6 % on a kernel compile (NOVA, Core i7);
     - under 1 % for Bao and Jailhouse on Cortex-A53;
     - for the worst TLB-bound workload measured, graph500 on Sandy Bridge, 13 % against 6 % natively with 2 MB pages at both levels.
   - **Exits themselves** cost 497 to 961 cycles on x86 (Hyperkernel, seven CPUs) and 752 to 6,500 cycles on ARM (Dall et al.).
4. **Recommendation, ranked.**
   1. **A thin per-core fence monitor with stage-2 confinement**, on every machine that gives the OS the hypervisor level. That is every x86-64 machine with VMX or SVM, ARM64 machines entered at EL2, and RISC-V harts with H. RVA23 makes H mandatory.
   2. **On RISC-V without H**, a DodOS M-mode fence: an SBI extension that sets the target hart's PMP to deny everything and parks it. It is non-cooperative but gives no confinement while the node runs.
   3. **Where neither exists** (for example ARM64 laptops that enter the OS at EL1 under a vendor hypervisor), the cooperative design of the recovery draft, and the machine is declared "degraded recovery".

   This revises the earlier rejection of "a hypervisor layer for v1" (`ownership-alternatives.md`, part 4), moves the write gate of D-115 (1) into the monitor, rewrites the fence and fence classes of the recovery draft, and amends D-093: the monitor becomes the only hypervisor and driver micro-VMs are its guests. Part 8 gives the exact list.
5. **Not proven yet:**
   - that a stage-2 abort reliably catches an ARM64 core spinning in a loop held in a micro-op cache (the architectural text says yes for new accesses; to test);
   - the real cost on the reference desktop and an ARM64 board;
   - the size of a monitor that also hosts micro-VMs;
   - that a monitor proof of termination and bounded masking is achievable in the project's means. SeKVM proved isolation, not termination.

---

## 1. What a failed kernel can do, and what each fence must take away

A node's kernel that is hung or wrong can:

| # | Harm | Reached through | Present design (gate + cooperative fence) |
|---|---|---|---|
| H1 | Write any memory its page tables map: its own chunks, remote frames it maps, the read-only machine table if a page-table bug made it writable | CPU stores | Gate keeps shared words; anything mapped stays writable until the core stops |
| H2 | Write device registers it maps, including the registers of an IOMMU unit or IOAPIC whose role it holds | CPU MMIO stores | Same as H1 |
| H3 | Make devices it drives write memory (DMA) | IOMMU context entries | Blocked by the unit role holders without the core's help (R1) |
| H4 | Send interrupts to other cores: IPIs, and on x86 INIT and NMI | Local interrupt controller | Not addressed |
| H5 | Keep its physical core | Not answering the stop | The core is lost; memory and roles frozen if unfenced |
| H6 | Leave firmware in a bad state (SMM, UEFI runtime, Trusted OS) | Firmware calls | Not repairable by any OS (recovery draft 1.5) |

D-116 asks to end the freezing that follows H5. The weakness exists because nothing removes H1 and H2 from a core that keeps running. So the real target is: **make H1 and H2 impossible without the node's help, bound H4, and recover the core when the hardware still works.** H3 is already covered. H6 is outside every design.

---

## 2. The evidence: what each architecture gives below the kernel

All items are verified unless marked; sources are in part 10.

### 2.1 x86-64

| Fact | Quote or figure | Source |
|---|---|---|
| External interrupts can be kept away from the guest | Table 27-5: "If this control is 1, external interrupts cause VM exits ... If this control is 1, the value of RFLAGS.IF does not affect interrupt blocking." With 0, they "are delivered normally" | SDM vol. 3, 325384-093 |
| NMIs reach the monitor whatever the guest does | NMI exiting: "non-maskable interrupts (NMIs) cause VM exits"; with virtual NMIs, "NMIs are not blocked in VMX non-root operation (except for ordinary blocking for other reasons, such as by the MOV SS instruction ...)" | SDM §28.3, §29.7.1 |
| INIT is a VM exit in non-root and blocked in root | "INIT signals cause VM exits"; "The INIT signal is blocked whenever a logical processor is in VMX root operation" | SDM §28.2, §24 |
| An NMI that arrives during SMM is taken before the next instruction after RSM | "If an NMI request is pending when the processor executes the RSM instruction, the NMI is serviced before the next instruction of the interrupted code sequence" (only one is latched; an SMI handler that executes IRET re-enables NMIs inside SMM) | SDM §34.8 |
| Per-core timer the guest cannot stop | The VMX-preemption timer "counts down in VMX non-root operation ... A VM exit occurs when the timer counts down to zero". It stops in C-states deeper than C2. AMD has none (the term does not occur in APM vol. 2 r3.46) | SDM Table 27-5, §28.5.1; APM vol. 2 |
| Guest ways to stall interrupts, which the monitor must close | Writes to CR8 reach the physical TPR unless "CR8-load exiting" or the TPR shadow is used. Exception storms (#AC, #DB: CVE-2015-5307, CVE-2015-8104), which Linux intercepts unconditionally. "Instruction timeout" exits exist for operations that keep the processor from an instruction boundary | SDM §32.3, §27.6.24; NVD CVE-2015-5307; Linux vmx.c and svm.c |
| AMD INIT | Intercepted in the guest. In the host, with GIF = 1 and no redirection, INIT is "Taken normally", so a stuck AMD monitor outside the GIF = 0 window can still be INITed. R_INIT turns it into #SX | APM vol. 2 Table 15-12, §15.30.1 |
| Remote invalidation, AMD | INVLPGB: "Invalidations are done both in the local TLB and broadcast to all processors"; rAX[5]: "all nested translations that could be used for guest translation ... are flushed"; TLBSYNC ensures "memory instructions using the translations invalidated ... have retired and writes using the translations have drained" | APM vol. 3 r3.39 |
| Remote invalidation, Intel | Remote Action Request: the target "performs the actions ... entirely by hardware", including an INVEPT payload; "In VMX non-root mode, the setting of ... RFLAGS.IF has no effect on the handling of RAR". Only on Sapphire Rapids (06_8FH); Linux support is an RFC (v5, November 2025) | Intel white paper 341431-001; LKML |
| IPI virtualisation | VMX "IPI virtualization" control: a guest's ICR write is turned into a posted interrupt with no exit. It needs virtual-interrupt delivery, hence external-interrupt exiting = 1. Which client parts implement it: **not verified** | SDM §32.1.6 |

### 2.2 ARM64

| Fact | Quote or figure | Source |
|---|---|---|
| Interrupts routed to EL2 cannot be masked by EL1 | Rule RXBYXL: "If the target Exception level is EL2 and any of the following are true, the interrupt cannot be masked by the PSTATE.{A, I, F} bits. — The Effective value of HCR_EL2.E2H is 0. — The Effective value of HCR_EL2.TGE is 0." | Arm ARM DDI 0487 M.d, D1 |
| The routing is all or nothing per type | HCR_EL2.IMO = 1: "Physical IRQ exceptions are taken to EL2". With IMO = 0 EL2 receives no IRQ while EL1 runs. FIQ (FMO) and SError (AMO) are routed separately. Under IMO = 1, EL1's priority mask (ICC_PMR_EL1) becomes the virtual one | Arm ARM HCR_EL2; GIC IHI 0069H §6.2 |
| FEAT_NMI cannot mask EL2's interrupts | "AllIntMask does not affect the masking or routing of interrupts to a higher Exception level." Optional from v8.7, mandatory from v8.8; Linux support not merged (series of July 2026) | Arm ARM; LKML |
| SDEI goes to the hypervisor, and EL1 cannot mask it | "For a firmware dispatcher (ELD = EL3), the client must be a hypervisor (ELC = EL2)"; events preempt "even when the client has its interrupts masked in its PSTATE" | SDEI DEN0054C §3.2.1, §4.3.1 |
| Broadcast TLB maintenance needs no code on the other PE | RQRNJC: a TLB maintenance instruction "causes a TLB maintenance operation to occur on each PE within the Shareability domain". ISTPSQ: the operation on a PE "is finished when all Memory Effects ... by that PE using in-scope old translation information are complete". ILXHLD: once complete, "no new memory accesses using the in-scope old translation information are architecturally performed by any observer". IYNJCP: completion is guaranteed for the other PEs "after the execution of DSB by the PEx" (the issuer). No rule asks anything of the other PEs | Arm ARM D8.17 |
| Caveats of that guarantee | Speculative accesses are allowed only where no observer can detect them (ICPZSM). TLBI IPAS2E1IS "is not required to apply to caching structures that combine stage 1 and stage 2", hence TLBI IPAS2E1IS, DSB, TLBI VMALLE1IS, or VMALLS12E1IS | Arm ARM D8.17 |
| Inter-processor interrupts under IMO = 1 | "A virtual write to ICC_SGI0R_EL1, ICC_SGI1R_EL1, or ICC_ASGI1R_EL1 traps to EL2." GICv4.1 removes the trap on the receiving side only | GIC IHI 0069H |
| Direct injection | GICv4 delivers virtual LPIs (MSIs through an ITS) to a running vPE "without involving the hypervisor". Timer PPIs and SPIs still go through EL2 | GIC IHI 0069H §1.1 |
| Who gets EL2 | Linux booting.rst: entry "either in EL2 (RECOMMENDED ...), or in EL1". Apple M1 with m1n1: "EL2 is available". Pixel 6 and later enter the kernel at EL2 (pKVM). Raspberry Pi armstub switches to EL2. Snapdragon Windows laptops: the Gunyah/QHEE hypervisor holds EL2 unless `slbounce` is used. AmpereOne runs KVM with NV2. Apple chips after M1, including the M5 of the trials: **not verified** | Linux docs; Asahi; AOSP; raspberrypi/tools; slbounce; Ampere |

### 2.3 RISC-V

| Fact | Quote or figure | Source |
|---|---|---|
| Higher modes are always interruptible from lower ones | "Interrupts for higher-privilege modes, y>x, are always globally enabled regardless of the setting of the global yIE bit for the higher-privilege mode" | Priv. spec, machine.adoc |
| HS-level interrupts while a guest runs | "An interrupt *i* will trap to HS-mode whenever ... (a) either the current operating mode is HS-mode and the SIE bit in the sstatus register is set, or the current operating mode has less privilege than HS-mode ...; and (c) bit *i* is not set in hideleg." So the guest's vsstatus.SIE has no effect | Priv. spec, hypervisor.adoc l. 526 (re-read) |
| Device MSIs straight to the guest | IMSIC guest interrupt files (GEILEN of them) deliver to VS-mode "without the hypervisor being invoked for each arriving interrupt". The APLIC (wired interrupts) has no virtualisation help | AIA spec |
| Remote stage-2 invalidation is done by M-mode on the target | `sbi_remote_hfence_gvma_vmid` (RFENCE, FIDs 3 to 6). In OpenSBI the target runs `__sbi_hfence_gvma_vmid` from `IRQ_M_SOFT`, an M-level interrupt that S- and HS-mode cannot mask. "eventually, but not necessarily immediately" for MSIP. No broadcast TLB invalidation is ratified (a 2019 RFC was dropped) | SBI spec; OpenSBI sbi_tlb.c, sbi_trap.c; LKML |
| PMP is per hart and M-mode only | "PMP CSRs are only accessible to M-mode"; per-hart registers | Priv. spec |
| Smrnmi | Resumable NMIs that "cannot be disabled by software", taken in M-mode; what drives the signal is platform-defined, and no hart can raise one on another | Smrnmi spec |
| H in silicon | RVA23 makes Sha (H and its companions) mandatory. H in silicon: SiFive P550 (ESWIN EIC7700, Linux dts) and SpacemiT K3 (dts). Vendor claims: P670, P870, Veyron V2, Ascalon. Absent: SG2042 (C920), JH7110 (U74), SpacemiT K1 (X60, dts). C908 and SG2044: **not verified** | riscv-profiles; Linux dts; vendor pages |

### 2.4 What the evidence changes

The recovery draft said: "No architecture lets one core cut another core's access to memory. Stopping its execution is the only fence" (part 2.1). **That is true at EL1, S-mode and ring 0, and false one level down.**
- On ARM64 and AMD, another core can revoke a guest's memory access in hardware.
- On Intel, an NMI forces the guest into the monitor, and the guest cannot refuse.
- On RISC-V, M-mode on the target does the revocation.

The whole option space is reshaped by this one fact.

---

## 3. The five families

### A. A small monitor under every node

#### A.1 The design I propose: a thin fence monitor

- **One monitor image, separate from the kernel, the same code on every core, with per-core state.** It is entered at boot before the node start-up and never left. The node runs in VMX non-root or SVM guest mode, at EL1 with E2H = 0 under EL2, or in VS-mode.
- **Stage-2 confinement.** Each node has a stage-2 table: EPT, NPT, VTTBR or hgatp. It maps exactly:
  - the node's floor and the chunks whose ownership word names it;
  - frames other nodes have shared with it;
  - the MMIO of devices it owns;
  - the registers of the units whose role it holds.

  The tables are filled when memory is taken, so they never fault in normal operation. Chunks are 2 MB aligned and runs go up to 1 GB, so stage-2 always uses 2 MB or 1 GB blocks. The 4 KB level appears only for frames shared between nodes.
- **The write gate moves into the monitor.** It is the only writer of the ownership words, member words and role words, and the only writer of the stage-2 tables. `memory_take`, `memory_give`, a share and a role move each become one hypercall that checks and writes the word (compare-and-swap, as today) and edits the stage-2 table in the same step. This turns the gate's single-writer rule into hardware confinement: a node can no longer write another node's memory through a page-table bug. The gate could not stop that, which the survey recorded as a residual risk.
- **No interrupt virtualisation by default.**
  - x86-64: external-interrupt exiting = 0, so device and timer interrupts go to the guest IDT. NMI exiting = 1 and virtual NMIs = 1 are set for the fence.
  - ARM64: IMO = 0, so interrupts go to EL1 directly.
  - RISC-V: VS interrupts are delegated by hideleg; device MSIs use IMSIC guest files where present. The HS-level software interrupt is the fence.
- **Inter-processor interrupts.**
  - On x86 the monitor intercepts writes to the x2APIC ICR. Otherwise a wild node could send INIT, NMI or interrupt storms to every core. Where IPI virtualisation exists it removes that exit.
  - On ARM64 with IMO = 0 a node can still generate SGIs physically. That is a denial-of-service window until it is fenced, not a write (inference). Closing it needs IMO = 1, whose costs are given below.
  - On RISC-V, IPIs go through the IMSIC or through SBI. A node can write only the MSI addresses its stage-2 maps (inference).
- **The fence, per architecture.** It is driven by any live node, through its own monitor:

| | Step 1: revoke | Step 2: the target falls into its monitor | Confirmation | Memory and roles reusable |
|---|---|---|---|---|
| ARM64 | Driver's monitor writes the kill word, clears the target node's stage-2 root (one page, or up to 16 with concatenated tables), TLBI VMALLS12E1IS for the target's VMID, DSB ISH | Its next memory access or instruction fetch takes a stage-2 abort to EL2, a synchronous exception that cannot be masked (inference from ILXHLD and the routing rules); the monitor reads the kill word and parks the guest | Not needed for memory: the DSB on the driver is the guarantee. The monitor's park record confirms that the core can be reloaded | At the DSB, after `SETTLE_NS` for posted device writes |
| AMD | Kill word, clear the target's NPT root, INVLPGB (ASID, nested bit) and TLBSYNC | NPT fault → #VMEXIT; also an NMI with the NMI intercept | TLBSYNC for memory; park record for the core | At TLBSYNC, after `SETTLE_NS` |
| Intel with RAR (Sapphire Rapids) | Kill word, clear EPT root, RAR with an INVEPT payload | EPT violation → VM exit | RAR completion; park record | At completion |
| Intel without RAR (the reference desktop, i5-14600KF, Raptor Lake: RAR not listed for it) | Kill word, clear EPT root, NMI to the target core | NMI → VM exit at the next instruction boundary (one-instruction window after STI or MOV SS); if the core is in SMM, before the next guest instruction after RSM (SDM §34.8) | The target's monitor runs INVEPT and writes the park record. That is the monitor's cooperation, not the kernel's | At the park record |
| RISC-V with H | Kill word, clear hgatp root, `sbi_remote_hfence_gvma_vmid` | Guest-page fault to HS-mode | The SBI call returns when the target's M-mode has fenced | At return |

- **Reload.** The monitor builds a fresh guest state (VMCS, EL1 registers, VS CSRs) and enters the node's kernel at its start-up entry. No INIT, SIPI, PSCI `CPU_OFF`/`CPU_ON` or SBI HSM is used after boot. So:
  - the BSP stops being special;
  - a core hosting a Trusted OS is not powered off, so the PSCI `MIGRATE` problem disappears;
  - the park stub below 1 MB and the INIT/SIPI window in which a broadcast machine check would kill the machine (attack table of the recovery draft) are no longer needed.

#### A.2 What it guarantees, and on which architecture

- **H1 and H2 end without the node's help.**
  - ARM64, AMD, Intel with RAR and RISC-V with H: from the moment the revocation completes.
  - Intel without RAR: from the moment the target's monitor exits, which the guest cannot prevent.

  This is what the owners asked for, except that on Intel without RAR the monitor must answer.
- **H1 and H2 are also bounded while the node runs:** a wrong kernel can damage only its own chunks, memory others shared with it, and its own devices. This is stronger than the present gate on every architecture.
- **H5 becomes recoverable** whenever the core's hardware still executes: it falls into the monitor and is reloaded. The recovery draft's **unfenced** state then means only a failed monitor or failed hardware (part 5).
- **The core's whole life is in the monitor's hands.** Reload is a monitor operation, which also gives the replacement path of kernel.md: seal, then reload with another image.

#### A.3 Cost, in figures

Common paths. "0" means no exit on that path by construction, and the source shows that a guest's path stays in the guest.

| Path | x86-64 | ARM64 | RISC-V |
|---|---|---|---|
| System call, IPC on one node | 0 exits. Quest-V: "hardware virtualization does not add any obvious overhead to Quest-V system calls". Dune: a system-call trap handled inside VMX non-root costs 180 cycles | 0 exits (EL0→EL1 traps do not involve EL2). Published comparison of seL4 with and without hypervisor mode: **not available** (sel4bench has the benchmark, no published result). To measure: the same kernel's IPC bench on one board, EL1 native and under the monitor | 0 exits (U→VS traps stay in VS with hedeleg). **No measurement found**; to measure on QEMU, then on a P550 board |
| IPC between nodes | Shared rings: TLB misses only. Notification IPI: +1 exit if the ICR is intercepted. A hypercall round trip costs 497–961 cycles across seven Intel parts and 697 on Zen 1, against 64–79 for a system call (Hyperkernel Fig. 11). 0 with IPI virtualisation (parts **not verified**) | IMO = 0: 0. IMO = 1: a trap on the sender. A virtual IPI costs 2,526 cycles in the optimised KVM of Dall et al. 2017 and 5,978 for Xen ARM, against 11,557 for KVM ARM in 2016 (X-Gene, Cortex-A57) | IPI to a guest through IMSIC: no exit where guest files exist. KVM virtual IPI 5,012 cycles on FireSim (DuVisor) where emulated |
| Device interrupt | 0 (external-interrupt exiting = 0; Quest-V: device interrupts reach the sandbox "without monitor intervention") | IMO = 0: 0. IMO = 1: average latency 140 ns native → 572 ns under Bao, 2,170 ns maximum (Cortex-A53); Jailhouse 0.45 → 1.26 µs (Cortex-A15); MSIs through GICv4 direct injection: no exit | Guest interrupt files: near native. Trap and emulate: about 80 ns → 740 ns (Rocket in FireSim) |
| Page fault in the node | 0 exits (stage-2 never faults in normal operation). The walk is longer: Dune measured a page fault at 2,687 cycles native against 5,093 inside VMX non-root (Ivy Bridge, 4 KB EPT) | 0 exits; added walk cost **not measured**. To measure: a fault microbenchmark native and under the monitor with 2 MB stage-2 blocks | 0 exits; **not measured** |
| TLB miss (two-stage walk) | Walk 35.8 → 86.4 cycles (Dune, 4 KB EPT). With large stage-2 pages: kernel compile −0.6 % (NOVA, Core i7). graph500 overhead 6 % native at 2 MB → 13 % at 2M+2M, 3 % at 1 GB → 11 % at 1G+1G; with 4 KB at both levels, 28 % → 113 % (Gandhi et al., Sandy Bridge). Simulation: 2D walks 3.9–4.6× slower (Bhargava et al.) | Bao, Jailhouse, Xen under 1 % (Cortex-A53, RTAS 2023). SeKVM under 10 % for applications, 35–50 % more without huge pages (Cortex-A57) | Rocket (FireSim) about 1 % on MiBench; CVA6 up to 13 % without a G-stage TLB, about 12.5 % recovered with one. No real silicon measured |
| Memory take, give or share (2 MB-granular) | +1 hypercall, 497–961 cycles, instead of the gate's 0.139 µs mediated write (Nested Kernel) | +1 hypercall: 752 cycles optimised, 6,500 for KVM ARM 2016, 376 for Xen ARM | +1 hypercall: 739 cycles (KVM null hypercall, FireSim) |
| Switching parked nodes (D-108) | A guest switch: 4,812 cycles (KVM x86) to 10,534 (Xen x86) | 8,799 (Xen ARM) to 10,387 (KVM ARM) | Not measured |

The ARM and x86 rows from Dall et al. come from 2016–2017 machines running full hypervisors. A thin monitor that saves little state should sit at the low end: Xen ARM's hypercall is 376 cycles against KVM ARM's 6,500 because KVM saves the whole context (inference from the paper's Table III).

**Memory.**
- Monitor code: Quest-V's fits in 4 KB, with about 400 lines needed after start-up. Bao's static memory is about 59 KiB plus 28 KiB per CPU.
- Stage-2 tables: Quest-V needs 12 KB per 1 GB sandbox. For DodOS with 2 MB blocks, the leaf tables cover all of memory once, 4 KB per GB (256 KB for 64 GB), plus two or three pages per node (arithmetic). The 4 KB entries for shared frames add one page per 2 MB of shared memory.

**Lines of trusted code.** These are the systems closest to what is proposed:

| System | Size | Note |
|---|---|---|
| Quest-V monitor | About 400 lines after start-up | x86 only; IA-32 |
| SeKVM KCore | 3.8 K lines (3.4 K C, 400 assembly) | Proven, Armv8 multiprocessor |
| Bao | 5.6 K SLoC (Armv8); RISC-V port 4.7 K beside a 5 K core in a later count | Static partitioning |
| Jailhouse | Core 3.5 K, plus 5.4–7.4 K per architecture | Static partitioning |
| pKVM EL2 | About 11 K | Hosts guests on behalf of an EL1 host |
| seL4 AArch64 with hypervisor support | 12.6 K SLOC | Verified in EL2 |

DodOS's monitor needs the gate's table rules, stage-2 editing, the fence, reload, and per architecture the VMCS/EL2/HS set-up. My estimate is 3 to 6 K lines per architecture before micro-VM hosting (inference from the table above).

#### A.4 One monitor per core, or one shared monitor

- **Quest-V** had a separate monitor per sandbox, so that no monitor switches EPT mappings, and it allowed the monitors to be implemented differently. Its sandboxes still shared a writable region "for all the sandboxes", which held driver locks.
- **The fence above needs two things to be shared:**
  - every node's kill word and stage-2 root must be writable by every monitor;
  - every monitor must read the ownership words.
- **Recommendation: one image, per-core state, and shared state limited to the machine table's living part** (written by compare-and-swap, as the gate already does), the kill words and the stage-2 roots.
  - It removes no single point of design: the same code runs everywhere.
  - Different monitors per core, as Quest-V allows, would cut common-mode risk at the price of two verified implementations. I do not recommend it for v1.

#### A.5 Hosting driver micro-VMs (D-093)

There are two ways:

| Way | Cost and complexity |
|---|---|
| Nested virtualisation: a node itself runs a hypervisor | ARM needs FEAT_NV2 (Armv8.4; Linux enabled NV in 6.16, still "experimental"). Intel has VMCS shadowing. RISC-V has only emulation (KVM patches of January 2026). A nested hypercall costs 92,385 cycles on ARM with NEVE and 36,345 on x86 with shadowing (NEVE, SOSP 2017). Turtles measured 6–8 % at the application level on x86 |
| **The monitor is the only hypervisor; a micro-VM is another guest of it, created and scheduled by a node through monitor calls, with stage-2 built from that node's chunks** | This is pKVM's structure: the deprivileged host at EL1 asks EL2 to create and run protected VMs (`__pkvm_init_vm`, `__pkvm_host_donate_guest`, teardown with reclaimed memory "zeroed by the hypervisor"). No nesting. It adds vCPU state handling and emulation hooks to the monitor, which is why pKVM is about 11 K lines |

**Recommendation: the second way.**
- The `vcpu` name reserved in kernel-interface.md becomes an object whose operations are monitor calls made by the owning node.
- The micro-VM's emulation of devices stays in user space on the node, as D-093 intends.
- This removes D-093's main objection ("a hypervisor to add to the kernel, so more trusted code"): the hypervisor exists anyway, and the micro-VM adds only vCPU support to it.
- The monitor's size target then needs two tiers: tier 1, fence and confinement (proof target); tier 2, vCPU hosting. Tier 2 is loaded only if the fallback is opened. Separating them so that tier 2 cannot break tier 1's invariants is a verification question to settle in the prototype.

#### A.6 What a monitor bug does

- **The monitor is on every core and holds every stage-2 table**, so a monitor bug is a common-mode failure of the whole machine. It is worse than a kernel bug, which costs one node.
- **This trades many independent kernels** (each a possible non-answering fence) for one small, proven monitor.
- **The trade pays only if the monitor is much smaller and much better checked than the kernel.** Its interface must be finite: no unbounded loop, no allocation, a bounded handler per exit, as Hyperkernel did: "we made the Hyperkernel interface finite, avoiding unbounded loops, recursion, or complex data structures".
- **The audit of the recovery draft (R4) stays.** Each node checks its ownership words at every recovery, now against the monitor's writes, so damage caused by a monitor bug to the table is detected and stops the machine with a trace.

#### A.7 Is formal verification realistic?

What exists (verified):

| Work | Property | Architecture, cores | Size, effort |
|---|---|---|---|
| SeKVM (S&P 2021; USENIX Security 2021) | KCore refines its specification; VM confidentiality and integrity; a model with shared page tables, tagged TLBs and caches | Armv8, multiprocessor ("first machine-checked security proof for a commodity multiprocessor hypervisor") | 3.8 K lines, two person-years; the link between the C and assembly proofs is not machine-checked |
| seL4 | C-level functional correctness, integrity and confidentiality; in EL2 on AArch64. Termination of every call: "all kernel API calls terminate" (SOSP 2009) | AArch64 hypervisor mode verified. RISC-V and x64 hypervisor modes not verified. Multicore not verified (static multikernel verification "scheduled to complete Q3/28") | About 20 person-years originally for 8.7 K lines |
| CertiKOS mC2 | Functional correctness of a concurrent kernel; system calls "terminate eventually", assuming a fair hardware scheduler and lock holders that release within *k* steps | x86 multicore | 6.5 K lines, under 2 person-years for concurrency |
| Hyperkernel | Push-button refinement | x86, uniprocessor | 7.4 K lines, "several researchers about a year" |
| uberXMHF | Memory integrity | x86; the analysers assume sequential execution | 7 K SLoC, 1 person-year |
| Komodo | Non-interference | ARMv7, one core | About 2 person-years |
| pKVM | An executable specification used as a test oracle, not a proof | arm64 | About 14 K lines of specification, one person-year |
| Hafnium | No complete proof; the model of `mm.c` was left incomplete | — | — |
| Atmosphere | Refinement and non-interference in Verus; no termination (Verus treats `decreases` on executable code as a lint) | x86, big lock | 6 K lines, 20.1 K lines of proof, under 2.5 person-years |

**Verdict.**
- **Isolation (the stage-2 tables contain only owned chunks; the kill word is honoured before every guest entry): realistic.** SeKVM is the precedent, at the same size, on a multiprocessor.
- **Termination and bounded masked time for every monitor handler:** seL4 proves termination, and its time bounds come from a separate static analysis. Its closed-system worst case was 387.4 µs on a Cortex-A8 at 800 MHz in 2011, and 193 k cycles on an ARM1136 in 2016. A monitor with no loops beyond fixed bounds makes this simpler (inference).
- **Not proven by anyone:** the fence protocol across cores, meaning revocation, completion and park in the relaxed memory models. Arm's relaxed TLB model has been formalised (ESOP 2022, cited by the pKVM work), which gives a starting point. This is the research contribution, and it belongs in the TLA+ model the recovery draft already asks for.

#### A.8 Machines where the level is not available

- **x86-64.** VMX or SVM is on every reference target. Firmware can disable it in setup (inference; I did not check the reference desktop's firmware).
- **ARM64.**
  - Machines entered at EL1 cannot run the monitor: Snapdragon Windows laptops without `slbounce`, and phones whose vendor hypervisor holds EL2.
  - Apple M1 is entered at EL2 through m1n1. The M5 of the trials: **not verified**.
  - These machines fall back to rank 3.
- **RISC-V.** Harts without H (JH7110, SG2042, SpacemiT K1) use rank 2. RVA23 boards have H.

#### A.9 What remains uncovered by A

- **H3:** DMA through a unit whose role holder is wrong (recovery draft weakness 9). Unchanged unless the IOMMU programming also moves into the monitor, which would add an IOMMU driver per architecture to the trusted base. Not recommended for v1.
- **H4:** IPI storms from a node not yet fenced, on ARM64 with IMO = 0. Bounded by detection time.
- **H6:** firmware.
- **A failed monitor** (part 5).

### B. Hardware that fences without software cooperation

| Mechanism | What it can do | Fit | Cost |
|---|---|---|---|
| Arm RME, granule protection | Tables written only at EL3 (GPTBR_EL3, GPCCR_EL3 are EL3-only). The GPT encodes physical address spaces, not PEs. Configuration must be consistent across PEs (RXLDKK: otherwise CONSTRAINED UNPREDICTABLE). The SMMU applies the same checks | **Cannot separate two Non-secure cores**: no per-node fence. Shipped silicon with RME enabled: not verified | No Arm figure for GPC cost |
| RISC-V PMP and Smepmp | Per hart, M-mode only | The basis of rank 2: M-mode on the target, reached by an M-level IPI the kernel cannot mask, sets deny-all and parks. Too few entries for dynamic chunk ownership while running (inference from the per-hart register count) | 0 on the common path; one M-mode IPI at fence time. Size scale: Keystone's security monitor adds 1.6 K lines to an M-mode of 10.7 K |
| RISC-V SPMP (ratified 24 August 2026) | PMP model for S-mode, with `satp.MODE` Bare | Not a fence: programmed by the kernel being fenced. "SPMP for Hypervisor" is at v0.6 | — |
| RISC-V Smmtt/Smmpt (now Smsd/Smmpt, v0.9.0) | Supervisor domains; the table pointer is in a per-hart M-mode CSR | A future per-node hardware ownership table on RISC-V, one domain per node; not ratified | — |
| RISC-V IOPMP (v0.8.4) and WorldGuard (proposal v0.3; "Fast Track" planned ratification not confirmed) | Checkers at the memory or bus check every transaction by initiator ID ("irrespective of their (hart or non-hart) origin"). WorldGuard IDs are per hart and set by M-mode, with 2 to 32 worlds. Checkers can be reprogrammed at run time ("first turn off the rule ... then perform any necessary updates"), though "Efficiently changing WG configurations dynamically ... is not a goal" | The only design found where **another agent can cut one hart's memory access at the memory side**. Limited by the number of worlds (fewer than nodes on large machines), no ratification and no general-purpose silicon found | No figures |
| AMD SEV-SNP RMP, Intel TDX | Ownership per guest (VM), not per core. RMP writes go through RMPUPDATE; hardware invalidates TLBs; hypervisor writes are checked | Only useful if nodes are VMs, which is A with a heavier table. No gain over stage-2 for this purpose | RMP table about 8.5 GB per 2 TB (0.4 %). PAMT up to 0.4 % of memory. Per-check cost: AMD published only RMPOPT cycle counts (139,790 cycles average per RMPOPT) |
| Per-core reset in SoCs | Allwinner, Rockchip (Linux warns other cores "might be stalled" if a powered-off core is not reset), i.MX8MQ per-core reset bits; TI K3 per-core TISCI device | SoC-specific platform drivers; they reset a core but revoke nothing. A last resort for a core whose monitor failed, on those SoCs only | 0 on the common path |
| Arm BSA watchdog | WS0: "Non-secure EL2 interrupt, directly targeting a single PE"; WS1 action "platform-specific" | A per-core watchdog interrupt to EL2, usable by the monitor as a self-check | 0 |
| Arm external debug and CTI | A CTI debug request halts a PE, if external invasive debug is enabled (authentication). Memory-mapped access is optional. EDPRCR.CWRR is RAZ/WI with RME. Linux's coresight-cpu-debug reads EDPCSR of locked-up CPUs, and notes some designs hang the bus | Not a production mechanism: authentication is platform policy (whether it is usually disabled: not verified) | — |
| Arm PPU WARM_RST | "accepted immediately ... UNPREDICTABLE ... a system deadlock might occur", "strictly for debug purposes" | No | — |
| PSCI, SCMI, SBI, RPMI | PSCI: only `CPU_ON`, `AFFINITY_INFO`, `MIGRATE` and `NODE_HW_STATE` take a target. SCMI: the OS "must not directly use SCMI to manage the power state of these processors". SBI v3 and RPMI v1: hart stop acts on the caller | No remote stop anywhere in the standard firmware interfaces | — |
| RISC-V Debug Module | haltreq, hartreset through the DMI, whose manager is the debug transport. No platform found that exposes it to harts (OpenTitan explicitly does not) | No | — |
| Lockstep (Cortex-A76AE, A78AE, R52) | Pairs compare; "If a fault is detected, both of the cores are permitted to continue execution but the results are UNPREDICTABLE"; the divergence is reported | Detection of hardware faults, not a fence; halves the cores in lock mode | No area or performance figure published |

**Verdict on B.** No portable hardware fence exists below the hypervisor level. RISC-V M-mode (rank 2) is the one usable lever. WorldGuard, IOPMP and Smmpt would make a RISC-V memory-side fence possible later, and the design should keep a place for them: the ownership table layout field (`layout` in `StartOwnership`, already proposed) and a fence back-end per platform.

### C. Making cooperation unnecessary by construction

- **What proofs give.**
  - seL4 proves that every kernel call terminates.
  - CertiKOS proves termination assuming fair hardware and lock holders that release within *k* steps. That assumption is exactly "the other core answers".
  - Theseus and RedLeaf recover from panics, not from hangs. Theseus leaves hangs to "complementary hardware mechanisms like watchdog timers": of 665 faults that manifested, 30 ended as hung tasks.
  - Atmosphere proves refinement, not termination. Verus does not prove termination of executable code.
- **What hardware does to the argument.** A proof covers the code on correct hardware.
  - Google ("Cores that don't count") reports "a few mercurial cores per several thousand machines", where "typically just one core fails, often consistently". Symptoms include broken lock semantics and kernel crashes.
  - Meta reports "hundreds of CPUs" across "hundreds of thousands of machines", "orders of magnitude higher than soft-error based FIT simulations".
  - A mercurial core can loop with interrupts masked in proven code. No proof excludes that.
- **Cost.**
  - Applied to the whole DodOS kernel: proof effort of the order of seL4 (about 20 person-years for 8.7 K lines originally) or Atmosphere (2.5 person-years for 6 K lines with refinement, without termination).
  - Run time: only the preemption points needed for bounded masked sections (seL4 1 KiB copy chunks of about 20 µs on an ARM1136).
  - The same on all three architectures; the proof is per architecture for the assembly parts.
- **Verdict.** C alone cannot remove the unfenced state, because of hardware faults, and it is the most expensive. **Applied to the monitor only**, it is what makes A sound: the kernel's cooperation is no longer needed, and the monitor's is proven.

### D. Tolerating an unstopped core without freezing anything

- **With A (or rank 2 on RISC-V), D comes for free.** Once revocation completes, a core that still runs reaches no memory, no device register and no unit (stage-2 is empty; ARM64, AMD, Intel with RAR, RISC-V with H).
  - Its memory is reclaimed at once.
  - Its unit roles move after `SETTLE_NS`.
  - Nothing is frozen. What is lost is the core itself, until it falls into the monitor, which happens at its next memory access, so in practice at once.
  - The barrier of the recovery draft keeps its per-dependency form. Its "fenced" condition becomes "revoked", which the driver can establish alone on ARM64 and AMD.
- **Without A, D gives nothing.** At EL1 or ring 0, the node's own page tables are its own, so no other core can revoke. Only rank 3's cooperative fence remains.
- **Cost.**
  - The lost core: 1/*n* of the machine, until reload. Nothing else.
  - Memory: none frozen.
  - Trusted code: that of A.

### E. Other structures

| Structure | What it gives | Cost | Verdict |
|---|---|---|---|
| Every node a VM of an existing verified separation kernel (seL4 as hypervisor) | Proven isolation (AArch64) | seL4's multicore kernel is not verified (static multikernel verification planned for Q3 2028). The CAmkES VMM is 40 K lines on top of a 14.8 K-line kernel. On Cortex-A53, overhead up to 7 % and interrupt latency 9.4 µs against a 200 ns baseline (Bao 840 ns) | Worse than a purpose-built monitor on every count; keep as a comparison |
| Partitioning hypervisors: Jailhouse, Bao, XtratuM, ARINC 653 | Jailhouse stops a cell's CPU with an NMI (x86) or an SGI to EL2 / SDEI (ARM), then parks it; it waits for the CPU with no timeout (`while (!cpu_suspended) cpu_relax();`). XtratuM and ARINC 653 take the CPU back at the next time window. Bao has no restart; a guest abort hangs that core in `while (true)` | Jailhouse core 3.5 K + 5.4–7.4 K lines per architecture; Bao 5.6 K | They confirm A's mechanism (stop by exit into the hypervisor, park) and show the trap: **a management CPU that waits for a confirmation with no timeout is lost with the failed one**. DodOS's driver must never wait unboundedly (its recovery reserve steps already forbid it) |
| Quest-V | Per-sandbox monitor, EPT, local and remote recovery of a NIC driver (VM exit 707–885 cycles; driver re-initialisation 1.45 × 10⁷ cycles; web server restored in under 0.5 s); detection by EPT violation only. A preemption timeout to force traps was proposed, not built | Monitor of about 400 lines | The closest precedent for A; it measured no full sandbox reload and had no IOMMU |
| NoHype | One VM per core, no hypervisor at run time. A VM is stopped by an NMI from the management core; "Any VM exit will trigger our kill VM routine"; about 1 % faster than Xen | — | Confirms that a guest cannot refuse an NMI exit, and that a hypervisor can stay off the hot path |
| Lockstep (A76AE, A78AE) | Detects divergence in hardware | Half the cores in lock mode; no figures | A hardware option for safety machines, orthogonal to A |
| Software redundancy (Romain, PLR) | Masks transient faults in user programs | Romain: up to 30 % for three replicas (single thread), 24–65 % with 2–4 threads. PLR: 16.9 % detection, 41.1 % with recovery | Not for a kernel |
| POWER and z hardware | POWER7: retry, then move the core's state to another core, then the hypervisor checkstops "the partition using the processor core". z16: spare cores | Proprietary | Shows the industry answer: hardware plus a hypervisor that owns the partitions, which is A |
| Microreboot | Crash-only components, state outside, leases including CPU leases ("if a computation hangs and does not renew its execution lease, it should be terminated"); a single EJB restarts in 411–601 ms against 19,083 ms for the JVM | — | DodOS's node reload already follows it. The CPU-lease idea is what a monitor timer would implement, if detection ever moved into the monitor |
| HP NonStop | "IamAlive" every 1.2 s, regroup after 2.4 s; the excluded processor gets a "poison packet ... causing it to halt itself" | — | Cooperative self-halt, the weakness D-116 refuses |

---

## 4. Comparison

| | A: monitor + stage-2 | B: hardware partitioning | C: proof of the kernel | D: abandon the core | E: seL4 as host |
|---|---|---|---|---|---|
| Ends H1 and H2 without the node's help | Yes (Intel without RAR: the monitor's help) | RISC-V M-mode at fence time only; nothing portable | No (hardware faults) | Only with A | Yes |
| Confinement while the node runs | Yes | No | Partly (proved code) | — | Yes |
| Recovers the core | Yes, if the hardware executes | M-mode parks it (RISC-V) | — | No | Yes |
| x86-64 | Yes | No | — | — | Not verified on x64 hypervisor mode |
| ARM64 | Yes where EL2 is given | No | — | — | Yes (AArch64 verified) |
| RISC-V | Yes with H | Yes, through M-mode | — | — | Hypervisor mode not verified |
| Common-path cost | 0 exits on system calls, IPC, interrupts, page faults; TLB miss +0.6 % to +7 points (large blocks) | 0 | 0 | 0 | Up to 7 %, interrupt latency 9.4 µs (A53) |
| Trusted code added | 3–6 K lines per architecture (estimate) | M-mode extension of about 1–2 K (Keystone scale) | 0, but the kernel proof | 0 | About 55 K (kernel + VMM) |
| Proof effort | SeKVM scale (two person-years) plus the fence protocol | Small | About 20 person-years (seL4 scale) | — | Done for one core; multicore after 2028 |

---

## 5. What remains uncovered whatever is chosen

1. **A core whose hardware stops executing.** It writes nothing, so it does no harm.
   - On ARM64 and AMD the revocation completes only if its TLB still answers broadcast maintenance. If it does not, the DSB or TLBSYNC on the driver may never complete, and the driver hangs too (inference). Such a fault already hangs every Linux machine that uses broadcast TLBI.
   - On Intel without RAR the core never confirms. Since it cannot execute, its memory could be reused, but nothing distinguishes "hung for good" from "in a very long SMI".
   - Rule proposed: reuse after the NMI is sent and an SMI bound has passed, relying on SDM §34.8 (the NMI is taken before the next guest instruction after RSM). The open point is an SMI handler that executes IRET, which re-enables NMIs inside SMM, and whether SMM entry drains stores (not verified).
2. **A core whose hardware executes wrongly** ("mercurial"): in its monitor, it can write whatever the monitor maps.
   - The monitor maps only its own state, the machine table and the stage-2 tables, so the damage reaches the table. The audit (R4) detects it and stops the machine with a trace.
   - The only full answer is lockstep hardware.
3. **A monitor bug:** common mode, on every core. It is the reason for the proof.
4. **Firmware** (SMM, EL3, M-mode, Trusted OS): trusted by every design.
5. **Machines without the hypervisor level** (rank 3).

---

## 6. Ranked recommendation

1. **Adopt A in its thin form** on x86-64, ARM64 (EL2 entry) and RISC-V with H. Specifically:
   - a per-core monitor of one image;
   - stage-2 confinement with 2 MB and 1 GB blocks;
   - the write gate inside the monitor;
   - the fence by revocation (ARM64, AMD, Intel with RAR, RISC-V) or by a forced NMI exit (Intel without RAR);
   - reload by the monitor;
   - no interrupt virtualisation by default; the x2APIC ICR intercepted on x86;
   - micro-VMs as the monitor's guests (tier 2).

   Why first: it is the only option that ends the freezing on all three architectures, it also turns containment rule 1 into a hardware guarantee, and its common-path cost is a TLB-walk cost the chunk sizes keep low.
2. **On RISC-V without H, rank 2:** a DodOS SBI extension in M-mode (`fence_hart`: PMP deny-all for S/U, park, report). It is non-cooperative. Confinement while running stays with the gate in the kernel, as decided by D-115. The extension needs DodOS to ship or upstream an OpenSBI patch.
3. **Rank 3 on machines without the level:** the cooperative fence of the recovery draft, with the unfenced state. The machine runs, and `core_status` and the start-up page say "degraded recovery". The owners decide whether DodOS supports such machines at all (part 9).
4. **Rejected as primary:**
   - B (not portable; RME cannot tell cores apart);
   - C for the whole kernel (hardware faults; cost);
   - E with seL4 (multicore not verified, 55 K lines, 9.4 µs interrupts on A53);
   - lockstep (hardware-specific, half the cores).

   Kept: C for the monitor; WorldGuard, IOPMP and Smmpt as future RISC-V back-ends.

---

## 7. What must be prototyped and measured first

| # | Question | How | What decides |
|---|---|---|---|
| 1 | Does a revoked ARM64 core really fall into EL2 at once, including a tight loop with interrupts masked and no data access (loop held in an instruction buffer)? | On an ARM64 board entered at EL2 (Raspberry Pi 5 with its armstub, or AmpereOne; the M5 if m1n1 supports it, not verified): core B spins at EL1 with PSTATE.I set; core A clears B's stage-2 root, TLBI VMALLS12E1IS, DSB ISH; measure the time to B's stage-2 abort over 10⁶ trials, with loops of 1 to 64 instructions | If any trial never faults, ARM64 also needs a forced entry (IMO = 1, SDEI or FIQ), whose costs are in A.3 |
| 2 | Fence latency per architecture | Kill to memory reusable: ARM64 (TLBI + DSB), AMD (INVLPGB + TLBSYNC), Intel reference desktop (NMI → exit → INVEPT → park), RISC-V QEMU then a P550 board (SBI remote hfence) | `FENCE_NS`; whether the unfenced state can be dropped on each |
| 3 | Common-path cost of the thin monitor | The same one-core kernel, native and under the monitor: system call, IPC on one node, IPC between nodes (ICR intercepted against IPI virtualisation where present), device interrupt latency, page fault, a TLB-miss microbenchmark (random walk over 2¹⁶ pages, as Dune), a kernel compile in a Linux micro-VM, with 2 MB and 1 GB stage-2 blocks | The gate the owners set; the ARM IMO choice |
| 4 | Gate as a hypercall | `memory_take`/`give` of 2 MB and 1 GB runs: hypercall against the in-kernel gate | Expected negligible at 2 MB granularity |
| 5 | NMI during SMM on the reference desktop | Send an NMI fence to a core inside a long SMI (provoked by firmware calls); record the guest RIP at exit, against the RIP at SMI entry | Whether SDM §34.8 holds on that firmware (no guest instruction between RSM and the exit) |
| 6 | Monitor size and proof feasibility | Write the tier-1 monitor for ARM64 first (the best-understood proof target: SeKVM, seL4 EL2); count lines; model the fence in TLA+ with the TLB as state | If tier 1 exceeds about 6 K lines, cut features before proceeding |
| 7 | `SETTLE_NS` | Already in the recovery draft (posted writes after a stop): now after a revocation | One hardware assumption of the role argument |

---

## 8. What changes in the DodOS structure, and which decisions are revised

| Item | Today | Becomes |
|---|---|---|
| `ownership-alternatives.md`, part 4 "Drop: a thin hypervisor layer for v1" | Dropped for four reasons | **Revised.** (1) "Shared trusted state": the monitor shares only the table the gate already shares, plus kill words and stage-2 roots. (2) "A cost on every TLB miss": measured at 0.6 % (NOVA), under 1 % (A53), 6 → 13 % in the worst TLB-bound case with 2 MB blocks. (3) "Three implementations": still true; it is the main cost. (4) "Collision with D-093": resolved by making the monitor the only hypervisor |
| **D-115 (1), the write gate** | In each kernel, which maps the table read-only and writes through a temporary alias | **Amended:** the gate is in the monitor, writes ownership, member and role words, and edits the stage-2 tables in the same step; kernels call it by hypercall. The table stays read-only to every kernel. Its rules (typed blocks, refusing foreign words, unclaimed and dead-owner words, reserve codes) are unchanged. Where rank 2 or 3 applies (no hypervisor level), the in-kernel gate of D-115 stays as specified |
| **D-093** | Micro-VM is plan B; "a hypervisor to add to the kernel" | **Amended:** if opened, micro-VMs are guests of the DodOS monitor, created and run by a node through monitor calls; the `vcpu` object is built on that. Emulation stays mandatory and first (D-093's position is unchanged) |
| D-107, D-114 | A reloaded kernel adopts nothing; the machine table has a read-only and a living part | **Unchanged.** The monitor also adopts nothing from a dead node: reload rebuilds the guest state from scratch |
| D-108 | Parked nodes switched by the kernel | Parked nodes are separate guests; a switch is a monitor guest switch (A.3 figures). "Containment is per node" becomes a hardware property |
| `symmetric-nodes-recovery.md` part 2.6, the fence | NMI/INIT/park stub; SDEI/NMI + `CPU_OFF`; IPI + `hart_stop` | Revoke + forced entry + park in the monitor, per the table of A.1. INIT, SIPI, the park stub below 1 MB, PSCI `CPU_OFF` and SBI HSM are no longer used after boot. The BSP and Trusted OS cores are no longer special |
| Same draft, fence classes (3.1) | 2 forced, 1 signalled, 0 cooperative | **Forced** for every core under a monitor (on Intel without RAR, forced through the monitor). Class 1 remains only for rank 2 (M-mode, which is forced too, so class 2) and rank 3. The successor rule keeps the classes for mixed machines |
| Same draft, states | `fencing`, `fenced`, `unfenced` | `fenced` means "revoked and completed", reached by the driver alone on ARM64, AMD and RISC-V. `unfenced` remains only for rank 3, a failed monitor, or the Intel case of part 5 item 1 |
| Same draft, 1.5 residue item 2 | Cores not fenceable by hardware | Reduced to machines of rank 3 |
| kernel.md, "Recovery of one core's kernel", item 1 "each kernel maps only its own memory" | A rule of the kernel | Enforced by the monitor's stage-2 |
| kernel.md, hardware features table | — | Add: VMX/SVM, EL2 entry and RISC-V H as **required** for full recovery; RAR, INVLPGB, IPI virtualisation, GICv4.1 and AIA guest files as optional accelerators |
| Start-up path | Machine start-up, then node start-up | Machine start-up, then **monitor start-up on every core** (VMXON / EL2 vectors / HS set-up, stage-2 of the node's floor and kept image), then node start-up as a guest |

---

## 9. For the humans

| # | Point | Recommended | Alternatives | Cost of each |
|---|---|---|---|---|
| 1 | Adopt the monitor | Yes, thin form, tier 1 proven | Stay with the cooperative fence; or seL4 as host | Rule: 3–6 K trusted lines per architecture, a proof of SeKVM scale plus the fence protocol, TLB-miss cost. Cooperative: the unfenced state D-116 refuses. seL4: multicore unverified until 2028, interrupt latency |
| 2 | ARM64 interrupts | IMO = 0 (no exit on interrupts), if prototype 1 shows a revoked core always faults | IMO = 1 (every IRQ and SGI through EL2, MSIs direct with GICv4) | IMO = 0: IPI storms possible until the fence. IMO = 1: interrupt latency 140 → 572 ns (Bao), a trap per SGI sent |
| 3 | x86 IPIs between nodes | Intercept ICR writes; use IPI virtualisation where present | Let the node write the ICR | Rule: +1 exit (about 500–1,000 cycles) per notification without IPI virtualisation. Alternative: a wild node can send INIT, NMI and storms to every core (INIT and NMI become exits into the targets' monitors, so a denial of service, not damage) |
| 4 | Machines without the hypervisor level | Run with "degraded recovery" (rank 3) | Do not support them | Rule: two recovery designs to keep. Alternative: no Snapdragon laptops (without `slbounce`) and no ARM phones with vendor hypervisors |
| 5 | RISC-V without H | Ship an M-mode `fence_hart` extension (rank 2) | Rank 3 on those harts | Rule: DodOS maintains an OpenSBI patch. Alternative: frozen memory on JH7110, SG2042 and K1 class boards |
| 6 | IOMMU in the monitor | No for v1: unit roles stay in nodes | Move IOMMU programming into the monitor (as pKVM plans) | Rule: a wrong unit holder stays trusted for DMA (weakness 9). Alternative: an IOMMU driver per architecture in the trusted base |
| 7 | Intel without RAR, core that never confirms | Reuse after the NMI and an SMI bound, on the argument of SDM §34.8 | Keep its memory quarantined (unfenced) | Rule: depends on the firmware's SMI handler not consuming the NMI (test 5). Alternative: the freezing D-116 refuses, in a rare hardware case |
| 8 | Different monitor implementations per core (Quest-V's idea) | No | Two monitors, half the cores each | Two verified implementations against a cut in common-mode risk |

---

## 10. What the one-core kernel must contain now to keep this open

D-107's rule applies: what the monitor needs in the contract, `abi/` and the layout of objects is settled before the one-core kernel is written. On one core the monitor still exists. It holds the gate and the stage-2 table of the single node, and has no fence work to do.

1. **The kernel runs as a guest from its first line:** VMX non-root or SVM guest, EL1 with E2H = 0 under an EL2 monitor, VS-mode.
   - It never executes VMX, SVM or EL2 instructions, never touches the H-extension CSRs, and never writes the physical x2APIC ICR or the ARM SGI registers except through one function, "send interrupt to node", which the monitor may intercept.
   - A build-time scan enforces this, as `ownership-alternatives.md` already proposes for CR0 and TTBR writes.
2. **The monitor is a separate binary** in the kept image, with its own SHA-256 in the read-only machine table, loaded by the machine start-up before any node start-up. Its first version can be the gate plus stage-2 for one node: a few hundred lines.
3. **The write gate's interface is a call** (the function "gate operation" of the drafts), already typed by blocks. On machines of rank 2 or 3 it runs in the kernel; under a monitor it is a hypercall. Same rules, same results.
4. **Every mapping of another node's memory, of device memory and of unit registers goes through a gate operation**, so that the monitor can mirror it in stage-2. The drafts already route chunk takes, `maps_of` and unit mappings through the gate; add device blocks (`memory_take` kind 1) and every remote mapping record.
5. **The kernel maps its memory by range**, never a direct map of all RAM. This is already item 1 of `nodes-memory-devices.md` part 3; stage-2 needs it too.
6. **Ownership words keep 2 MB chunks and runs up to 1 GB**, which give stage-2 its large blocks. Shared frames between nodes are the only 4 KB stage-2 entries; their records carry the page count.
7. **A VMID or ASID per node** in the node block (16 bits on ARM with FEAT_VMID16, otherwise 8; 14 bits for VMID on RISC-V Sv39x4 hgatp, not verified; the ASID on AMD; the VPID or EPTP on Intel). Parked nodes keep theirs.
8. **The member word gains no state.** `fenced` changes meaning to "revoked, completed". `abi/` adds the fence back-end as a field in the start-up page (`StartCore` flags bits 1-2 keep the fence class: 2 under a monitor or M-mode extension, 1 or 0 otherwise). The recovery draft's `vmx` beacon field and park stub page are removed.
9. **The `vcpu` object** (kind 16, reserved) is defined as a monitor-backed object owned by a node; nothing is built until D-093's fallback opens.
10. **Remove from the one-core plan** the x86 park stub below 1 MB, the INIT/SIPI sequence after boot, and the ARM `CPU_OFF` handler and RISC-V `hart_stop` fence paths. Keep PSCI `CPU_ON` and SBI `hart_start` for machine start-up only.

---

## 11. Sources

**x86-64**
- Intel SDM vol. 3, 325384-093US (September 2026): https://cdrdv2.intel.com/v1/dl/getContent/671447 — Table 27-5, §28.2, §28.3, §28.4.1, §28.5.1, §29.2.1.1, §29.7.1, §32.1.6, §32.3, §32.6, §34.8.
- AMD APM vol. 2 r3.46 and vol. 3 r3.39 (amd.com links return 404; read from the mirror) https://kib.kiev.ua/x86docs/AMD/AMD64/24593_APM_v2-r3.46.pdf , https://kib.kiev.ua/x86docs/AMD/AMD64/24594_APM_v3-r3.39.pdf — Tables 15-12, 15-13, §15.21, §15.30.1; INVLPGB, TLBSYNC.
- Intel VT-d rev 5.20: https://cdrdv2.intel.com/v1/dl/getContent/671081
- Intel Remote Action Request white paper 341431-001: https://intel.com/content/dam/develop/external/us/en/documents/341431-remote-action-request-white-paper.pdf ; Linux RAR RFC v5: https://lkml.iu.edu/2511.2/05079.html
- CVE-2015-5307: https://cveawg.mitre.org/api/cve/CVE-2015-5307 ; Linux `arch/x86/kvm/vmx/vmx.c`, `svm/svm.c`, `Documentation/virt/kvm/api.rst` (mainline).

**ARM64**
- Arm ARM DDI 0487 M.d: https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1 — RXBYXL (D1), HCR_EL2, D8.17 (RQRNJC, ISTPSQ, ILXHLD, ICPZSM, IYNJCP, IBLDZX), D9 (GPC: RYMRVT, RXLDKK), H2, H5, H6, H8, H9.
- SDEI DEN0054C: https://documentation-service.arm.com/static/63cfe298e4378a55c5e03d93
- GICv3/v4 IHI 0069H.b: https://documentation-service.arm.com/static/67eaa4d098aa3c3b6eea7351
- RME guide DEN0126: https://developer.arm.com/documentation/den0126/latest ; TF-A GPT design: https://trustedfirmware-a.readthedocs.io/en/latest/components/granule-protection-tables-design.html ; Neoverse V3 TRM: https://developer.arm.com/documentation/107734/latest
- BSA DEN0094: https://developer.arm.com/documentation/den0094/latest ; SCMI DEN0056: https://developer.arm.com/documentation/den0056/latest ; PSCI DEN0022 F.b (same site).
- Cortex-A78AE TRM: https://developer.arm.com/documentation/101779/latest
- FEAT_NMI Linux series: https://lkml.iu.edu/2607.0/09094.html ; HIP12 claim: https://lkml.iu.edu/2607.0/06225.html
- EL2 availability: Linux `Documentation/arch/arm64/booting.rst`; https://asahilinux.org/2021/03/progress-report-january-february-2021/ ; https://source.android.com/docs/core/virtualization/architecture ; https://github.com/TravMurav/slbounce ; raspberrypi/tools `armstubs/armstub8.S` ; https://amperecomputing.com/blogs/unlocking-layers
- Linux arm64 stop escalation: https://raw.githubusercontent.com/torvalds/linux/master/arch/arm64/kernel/smp.c ; kexec: `arch/arm64/kernel/machine_kexec.c`.

**RISC-V**
- Privileged spec: https://github.com/riscv/riscv-isa-manual (src/priv/machine.adoc, hypervisor.adoc, smepmp.adoc, smrnmi.adoc; debug_module.adoc).
- AIA: https://github.com/riscv/riscv-aia ; SBI: https://github.com/riscv-non-isa/riscv-sbi-doc ; profiles (RVA23): https://github.com/riscv/riscv-profiles
- OpenSBI `lib/sbi/sbi_tlb.c`, `lib/sbi/sbi_trap.c`, `lib/utils/ipi/aclint_mswi.c`: https://github.com/riscv-software-src/opensbi
- SPMP releases: https://github.com/riscv/riscv-spmp/releases ; Smmtt/Smmpt: https://github.com/riscv/riscv-smmtt ; IOPMP: https://github.com/riscv-non-isa/iopmp-spec ; WorldGuard proposal: https://github.com/riscvarchive/security/blob/main/papers/worldguard%20proposal.pdf ; WorldGuard task group page: https://riscv.atlassian.net/wiki/spaces/PSXX/pages/338919428/Worldguard ; OpenSBI wgchecker: https://lists.infradead.org/pipermail/opensbi/2026-May/009927.html
- Broadcast sfence RFC: https://lkml.iu.edu/hypermail/linux/kernel/1909.2/03537.html
- Device trees: Linux `arch/riscv/boot/dts` (eswin/eic7700.dtsi, sophgo/sg2042-cpus.dtsi, starfive/jh7110.dtsi, spacemit/k1.dtsi, k3.dtsi).

**Monitors, costs, verification**
- Quest-V: https://arxiv.org/pdf/1112.5136 ; https://arxiv.org/pdf/1310.6349 ; VEE 2014 https://www.cs.bu.edu/~richwest/papers/vee2014.pdf ; TOCS 2016 https://www.cs.bu.edu/~richwest/papers/west-tocs16.pdf
- Bhargava et al., ASPLOS 2008: https://courses.physics.illinois.edu/ece598ms/fa2019/papers/paper223.pdf
- Gandhi et al., MICRO 2014: https://scail.cs.wisc.edu/papers/micro14-virtualization.pdf ; agile paging, ISCA 2016: https://research.cs.wisc.edu/multifacet/papers/isca16_agile_paging.pdf
- NOVA, EuroSys 2010: https://hypervisor.org/eurosys2010.pdf
- Dune, OSDI 2012: https://www.usenix.org/system/files/conference/osdi12/osdi12-final-117.pdf
- Bao, NG-RES 2020: https://drops.dagstuhl.de/storage/01oasics/oasics-vol077-ng-res2020/OASIcs.NG-RES.2020.3/OASIcs.NG-RES.2020.3.pdf ; Martins and Pinto, RTAS 2023: https://arxiv.org/pdf/2303.11186
- Jailhouse: https://arxiv.org/pdf/1705.06932 ; source https://github.com/siemens/jailhouse (hypervisor/control.c, Documentation/hypervisor-interfaces.txt)
- Dall et al., ISCA 2016: https://www.cs.columbia.edu/~nieh/pubs/isca2016_armvirt.pdf ; ATC 2017: https://www.usenix.org/system/files/conference/atc17/atc17-dall.pdf ; NEVE, SOSP 2017: https://www.cs.columbia.edu/~nieh/pubs/sosp2017_neve.pdf ; Turtles, OSDI 2010: https://www.usenix.org/legacy/event/osdi10/tech/full_papers/Ben-Yehuda.pdf
- Hyperkernel, SOSP 2017: https://unsat.cs.washington.edu/papers/nelson-hyperkernel.pdf
- SeKVM, S&P 2021: https://www.cs.columbia.edu/~nieh/pubs/ieeesp2021_kvm.pdf
- RISC-V hypervisor measurements: https://arxiv.org/pdf/2103.14951 ; CVA6: https://arxiv.org/pdf/2302.02969 ; DuVisor: https://arxiv.org/pdf/2201.09652
- seL4: https://docs.sel4.systems/projects/sel4/verified-configurations.html ; https://sel4.systems/About/FAQ.html ; https://sel4.systems/roadmap.html ; https://sel4.systems/performance.html ; SOSP 2009: https://www.sigops.org/s/conferences/sosp/2009/papers/klein-sosp09.pdf ; WCET RTSS 2011: https://trustworthy.systems/publications/nicta_full_text/4863.pdf ; EuroSys 2012: https://trustworthy.systems/publications/nicta_full_text/5391.pdf ; RTAS 2016: https://www.sel4.systems/Research/pdfs/complete-high-assurance-determination.pdf ; Sewell et al. 2017: https://trustworthy.systems/publications/full_text/Sewell_KH_17.pdf
- pKVM: https://github.com/torvalds/linux/blob/master/Documentation/virt/kvm/arm/pkvm.rst ; https://source.android.com/docs/core/virtualization/security ; executable specification, SOSP 2025: https://www.cl.cam.ac.uk/~pes20/Stuff/exec-spec-paper.pdf
- CertiKOS, OSDI 2016: https://www.usenix.org/system/files/conference/osdi16/osdi16-gu.pdf ; Atmosphere, SOSP 2025: https://mars-research.github.io/doc/2025-sosp-atmo.pdf ; Verus termination: https://verus-lang.github.io/verus/guide/exec_termination.html
- Theseus: https://www.usenix.org/system/files/osdi20-boos.pdf ; RedLeaf: https://www.usenix.org/system/files/osdi20-narayanan_vikram.pdf
- NoHype: ISCA 2010 https://www.cs.purdue.edu/homes/bb/cs590/papers/mehdi.pdf ; CCS 2011 https://www.cs.princeton.edu/~jrex/papers/ccs11.pdf
- Nested KVM arm64 in 6.16: https://lists.infradead.org/pipermail/linux-arm-kernel/2025-May/1030501.html
- Windows HVCI gaming figures (press, not peer-reviewed): https://www.tomshardware.com/news/windows-11-gaming-benchmarks-performance-vbs-hvci-security

**Hardware faults, recovery, partitioning**
- Cores that don't count: https://sigops.org/s/conferences/hotos/2021/papers/hotos21-s01-hochschild.pdf ; Silent data corruptions at scale: https://arxiv.org/pdf/2102.11245
- Microreboot: https://arxiv.org/pdf/cs/0406005 ; Nooks: https://dada.cs.washington.edu/research/nooks/nooks-sosp.pdf ; MINIX 3 DSN 2007: https://minix3.org/docs/jorrit-herder/dsn-dccs07.pdf ; CuriOS: https://www.usenix.org/legacy/event/osdi08/tech/full_papers/david/david.pdf
- XtratuM manual: https://microelectronics.esa.int/gr740/xm-4-usermanual-047d.pdf ; ARINC 653 (university copy): https://mail.kia.prz.edu.pl/~ssamolej/vxworks/ARINC_653P1-2.pdf ; Bao source: https://github.com/bao-project/bao-hypervisor ; Xen: https://github.com/xen-project/xen ; Hafnium: https://git.trustedfirmware.org/hafnium/hafnium.git
- Romain, EMSOFT 2012: https://ls12-www.cs.tu-dortmund.de/daes/media/documents/publications/downloads/2012-emsoft-doebel.pdf ; RomainMT: https://os.inf.tu-dresden.de/papers_ps/emsoft14-doebel-romain.pdf
- POWER7 RAS: https://public.dhe.ibm.com/software/emea/de/stg/Power7-SystemRAS.pdf ; z16 Redbook: https://www.redbooks.ibm.com/redbooks/pdfs/sg248951.pdf ; NonStop: https://patents.google.com/patent/US5892895 , https://ftp.hp.com/pub/softlib/NonStopOpMsgsMnl/ch45.html
- kmorph: https://github.com/multikernel/kmorph ; Linux multikernel RFC: https://lists.infradead.org/pipermail/kexec/2025-September/033829.html
- SEV-SNP white paper: https://docs.amd.com/v/u/en-US/SEV-SNP-strengthening-vm-isolation-with-integrity-protection-and-more ; RMPOPT: https://lkml.iu.edu/2603.0/07797.html ; TDX: https://github.com/torvalds/linux/blob/master/Documentation/arch/x86/tdx.rst
- Keystone: the figure "only 1.6 KLoC added by Keystone", M-mode total 10.7 KLoC, was read in the paper's arXiv v2 by the research pass; the URL https://arxiv.org/abs/1907.10119 is given from memory (not verified).

**Not verified** (and not relied on for a conclusion):
- whether a revoked ARM64 core can keep executing out of a micro-op or loop buffer (test 1);
- which Intel client parts have IPI virtualisation;
- RAR after Sapphire Rapids;
- whether SMM entry drains stores, and how real SMI handlers treat NMIs;
- EL2 entry on Apple chips after M1 (including the M5), on AWS Graviton bare metal and on Ampere Altra;
- H on T-Head C908 and SOPHGO SG2044;
- WorldGuard's ratification;
- shipped silicon with RME enabled;
- debug authentication defaults in production;
- seL4 IPC with and without hypervisor mode on the same board;
- any H-extension measurement on real silicon;
- ARM64 and RISC-V page-fault cost under stage-2;
- pKVM host stage-2 overhead;
- lockstep area and performance;
- the 14-bit VMID width of RISC-V hgatp for Sv39x4;
- the line estimate of 3 to 6 K for the DodOS monitor (inference from published sizes).
