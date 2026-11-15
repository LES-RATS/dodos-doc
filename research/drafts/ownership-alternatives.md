# Protecting the chunk-ownership record from a kernel that goes wrong

Written 15 November 2026 for the two owners, as the survey D-114 asks for. Nothing under `/Users/btw/Documents/repos` was edited. **Verified** means checked on the web today; the source is given in the text and listed in part 6. **From memory** means I did not check it. Several papers were read in full text (extracted from the PDF); the rest are marked as known only through abstracts, course notes or search summaries.

**Threat model, as given:** a kernel bug (a stray write, or a logic error), not a malicious kernel. Two harms count: (1) node X damages the record of what *other* nodes own; (2) a reloaded node trusts a record that its dead predecessor could have damaged.

---

## 0. Verdict in one page

1. **The draft's check field does not stop the most likely bug.** A logic error (an off-by-one in a run, the wrong node index, a block range read from the wrong slot) writes a *well-formed* word at the wrong index, and a well-formed word passes the check. The check only catches garbage values. So the hole the owners spotted is real, and it is mostly not about stray writes.
2. **Per-owner write rights in hardware cannot sit on a per-chunk table.** Page permissions and protection keys work on whole pages. One 4 KB page of the table holds 512 words, which describe 1 GB of chunks whose owners change one by one. To give each owner its own write right you must group the words by owner, and that *is* candidate (a). So (b) with page permissions or keys becomes (a), and (b) with "a thin layer" becomes a hypervisor.
3. **Each DodOS node already has its own page tables, so "read-only for the others" costs nothing.** Every kernel maps the table read-only. What is left to decide is how the one legitimate writer writes.
4. **Recommended: keep the draft's per-chunk table and its protocol unchanged. Map the table read-only in every kernel, including the owner's. Make one small write gate per node the only code that writes a word.** The gate refuses any word whose current owner is not its own node. It is also the only code that maps or unmaps a chunk in the kernel's own address space. This is Nested Kernel *write-mediation* in a reduced form (Dautenhahn et al., ASPLOS 2015, verified), and the Rio file cache did the same to protect its cache (verified, qualitative). It stops stray writes (they fault: fail-stop) and wrong-index writes into other nodes' words (the gate refuses them). A reloaded node then trusts only words that name its own node. Only its predecessor or a giver could have written such words, and they cover memory that no live node uses.
5. **A new argument that settles "two nodes dead at once", for every candidate.** Once the reclaim step has confirmed that no live node or device reaches a dead node's memory, giving a chunk to the *wrong* dead node is harmless, because nothing alive refers to it. Safety needs only one rule: a chunk claimed by a live node is never handed to a reloading node. So "the memory of the dead nodes is everything that no live node claims" (the complement) is always safe, and splitting the complement among several reloading nodes is a matter of balance, not of safety. This also removes the draft's reason for rejecting the message-only variant.
6. **Ranking.** (1) Table + gate, adopted now. (2) The message-only variant with the complement rule, kept as the fallback if the owners want D-107 word for word, since the machine table then stays entirely read-only. (3) Claim pages (a): sound, but it needs the same gate to be safe and adds an offer protocol. Dropped: protection keys as a requirement, a hypervisor layer, NrOS-style replication, and MTE or CHERI for now. Details in part 4.

---

## 1. What exists

Each entry gives what it does, what it would give DodOS, and what it costs.

### Multikernels and partitioned kernels

**Barrelfish (capabilities across cores).** Every capability has an *owner node* that serialises the operations on it. Three invariants hold: each capability has an owner, copies share one owner, and the owner holds a local copy. Ownership moves through a distributed protocol. That protocol assumes "message channels between nodes are strictly FIFO and no messages get lost" and that "nodes are not adversarial" (Gerber, PhD 2018, ch. 4, read in full text, verified). RAM is handed out by a memory server (the same text; that there is one server *per core* is from memory). *Gives:* the principle that the owner is the single writer, which the draft already follows. *Costs / missing:* no handling of a failed node anywhere.

**Barrelfish/DC (OSDI 2014).** The kernel control block externalises each core's state so that a kernel can be replaced. The paper says: "we do not consider fault tolerance and isolation for now" (full text, verified). *Gives:* the node block (already cited in kernel.md). *Missing:* recovery from a dead kernel.

**seL4 clustered multikernel (von Tessin, 2012 workshop paper; PhD 2013).** Nodes are uniprocessor seL4 instances, each a cluster under a big lock. "No kernel data structures can be shared or moved between nodes." The proved Kernel Isolation Theorem says "any memory designated to create kernel data structures in is partitioned between nodes" and "kernel data structures are never created outside the designated memory region" (full text, verified). *Gives:* the shape of a theorem DodOS can state per generation: node X writes kernel memory only in its floor and in chunks whose word names X. The gate makes that a local, checkable property. *Costs / missing:* memory never moves, and there is no recovery.

**Quest-V.** Each sandbox kernel runs in its own VM, with one monitor per sandbox. "The EPT data structures are, themselves, restricted to access by the monitors, thereby preventing tampering by sandbox kernels." Memory is partitioned at launch. A shared region at the top of physical memory holds the communication channels and even "the global locks used to protect shared driver access". Local recovery may "re-initialize the entire local sandbox, as in the case of initial system launch" (arXiv 1112.5136, full text, verified). *Gives:* proof that a thin hardware layer can protect each kernel's view and support a restart. *Costs:* VMX/EPT in the trusted base, a monitor per core, a static partition, and a shared writable region with locks, which is what DodOS avoids.

**Popcorn Linux.** Several Linux kernels, each with "kernel-private memory and hardware devices". Physical memory is partitioned by boot parameters, and pages are shared between kernels with coherent mappings (Popcorn papers and guides, search summaries only, verified at that level). *Gives:* little for this question: no ownership that moves, no recovery found.

**NrOS / node replication (OSDI 2021).** Kernel state is replicated per NUMA node and kept consistent by a shared operation log. Physical memory is explicitly *not* replicated: "Physical memory allocation ... [does] not use NR"; memory is split at boot into per-NUMA caches (NCache) and per-core caches (TCache) (full text, verified). The verified NR (IronSync, OSDI 2023, Linear Dafny; later Verus) proves linearizability and does not verify liveness (search summaries, verified). *Gives:* nothing for ownership. Its own designers kept frame allocation outside the log. *Costs:* a shared log written by every replica, which is exactly the shared-write hazard kernel.md already rejected.

**SemperOS (ATC 2019).** Many microkernels on M3 manage distributed capabilities through a protocol between kernels (abstract only, verified). I found no fault-tolerance or memory-movement mechanism that applies here.

**Hive (SOSP 1995).** The closest precedent. Its "firewall" holds 64 bits per physical page, one per node, recording who may write the page, and it is "enforced by memory owner". On a cell failure, pages the failed cell could write are discarded (MIT 6.824 handout and search summaries; the paper PDF is a scan I could not read, so this is verified only at that level). The handout notes that it "really just" protects against application wild writes, and FLASH was simulated in SimOS, never built. *Gives:* the principles "per-page writer rights set by the owner" and "distrust whatever the dead node could write". *Costs:* hardware that does not exist on any CPU we target.

**Cellular Disco (SOSP 1999).** Cells borrow memory by RPC: "the loaner cell allocates memory from its freelist and returns a list of machine pages"; borrowing 4 MB takes 758 µs. Recovery begins with "a standard n-round agreement protocol" on the set of live cells. Cells share memory "because cells can trust each other" (the monitor is trusted, and only hardware faults are handled) (full text, verified). *Gives:* (1) a precedent for moving memory by message between cells; (2) agreement on the live set before any recovery action, which the complement rule needs when two nodes die together. *Costs:* it trusts every cell's software.

**Fault-tolerant multikernels in general.** An extended search found nothing beyond Quest-V that recovers a failed per-core kernel while the others run on (verified as an absence in that search; the search is not exhaustive). Kmorph and Barrelfish/DC are already in kernel.md. I found **no precedent** for recovering a node whose memory changes owner at run time.

### Partitioning hypervisors and memory hot-plug

**Jailhouse.** On cell creation, the hypervisor unmaps the cell's memory regions from the root cell and maps them into the new cell. On destruction, it maps them back, except communication regions; the root cell cannot be destroyed (Jailhouse source and docs, verified). *Gives:* the arbiter model: memory moves only through a trusted layer. *Costs:* the layer is a single shared point, and memory moves only at cell creation and destruction.

**virtio-mem (Hildenbrand and Schulz, VEE 2021).** The guest plugs and unplugs device blocks (block-size 2 MiB in the QEMU example). The hypervisor holds the authoritative plugged state, and the design "can reliably detect malicious VMs that use more memory than agreed" (paper page, QEMU and Linux commits, verified). *Gives:* authority sits with the arbiter, and the guest's view is advisory. *Costs:* a trusted arbiter above the kernels.

**pKVM (Android, arm64).** The EL2 hypervisor records the ownership state of each page in software bits of the stage-2 entries: owned, shared-owned, shared-borrowed. Host, hypervisor and guests move pages by explicit transitions (Linux source, verified). *Gives:* the best modern example of a thin layer with a per-page ownership state machine and donations. *Costs:* EL2 is required, it is Arm-only in mainline, and every transition is a hypercall.

**Windows Kernel Data Protection.** The hypervisor makes chosen kernel data read-only through second-level translation, with a secure pool managed by VTL1 (Microsoft blog 2020, verified). *Gives:* a production precedent for "protect kernel data from the kernel" with a thin layer. *Costs:* a hypervisor is required.

**Hardware ownership tables for confidential computing.** These are per-page ownership tables that hardware checks on every access and that only a small trusted agent writes:
- AMD SEV-SNP's RMP: one entry per 4 KB page; hypervisor writes are checked too.
- Arm CCA's Granule Protection Table: written only by the EL3 monitor; only four physical address spaces.
- RISC-V Smmtt / Smmpt: a memory-tracking table programmed by M-mode, per supervisor domain; still a draft, v0.49 per a July 2026 OpenSBI RFC.

(All verified through Linux docs, TF-A docs and mailing lists.) *Gives:* exactly the mechanism (b) asks for, but its owners are VMs or worlds, not nodes of one OS. *New avenue:* if Smmpt is ratified, each DodOS node could be one supervisor domain, with the M-mode root manager as arbiter. That would be per-node ownership enforced by hardware on RISC-V. It is not usable today.

### Write-protecting kernel data from the kernel itself

**Nested Kernel / PerspicuOS (ASPLOS 2015).** It runs in the same ring 0 as the kernel, toggling CR0.WP "on transitions between the outer kernel and nested kernel without swapping address spaces". It "de-privileges outer kernel code by replacing instances of writes to CR0", enables WP on every interrupt path, and keeps its own write-protected stack and IDT. It offers *write-mediation*: `nk_declare` marks pages read-only with a mediation function, and every write goes through `nk_write`. A nested-kernel call costs 0.139 µs, against 0.088 µs for a syscall and 0.513 µs for a VMCALL; overheads are under 1 % for Apache and 2.7 % for a kernel compile (full text, verified). *Gives:* the gate design almost directly. Its mediation function is our rule "write only a word whose owner is me". *Costs:* the full version mediates every page-table write and needs kernel code integrity. That is overkill against bugs; the reduced version (part 3) is enough.

**Rio file cache (ASPLOS 1996).** The file cache's pages are write-protected, and only file-cache procedures enable writes, for the time of each write. "Rio without protection is about as reliable as a write-through file system and even better with protection" (Rio project page and a Stanford quals summary, verified qualitatively; the figures are in a scanned PDF I did not read). *Gives:* the empirical precedent that page protection against the kernel's *own* bugs pays off.

**Otherworld (EuroSys 2010).** A crash kernel reads the dead kernel's structures and resurrects processes; it succeeds "in over 97% of the cases", with failures due to corrupted kernel memory. The authors propose cross-checking duplicated state after a failure, and checksums. Hiding user memory from the kernel with a second set of page tables costs a few percent (full text, verified). It also states that "most faults in the operating system kernel conform to the fail-stop model" (citing others). *Gives:* the audit idea in part 3, and evidence that adopting a dead kernel's state fails a measurable share of the time, which supports D-107.

**SKEE (NDSS 2016).** An isolated environment on ARMv7 and ARMv8 at the kernel's own privilege level: the kernel loses control of its translation tables, enters only through one gate, and uses a dedicated ASID (NDSS slides and abstract, verified). *Gives:* evidence that the gate is feasible on ARM, which has no CR0.WP.

**Read-only mappings really bind ring 0.** On x86, supervisor writes to read-only pages fault when CR0.WP = 1 (Intel SDM mirror, verified). On arm64 an EL1 write to a read-only mapping faults: Linux patches read-only kernel text through a temporary writable fixmap alias because the text "cannot be modified directly" (Linux commit, verified through its summary). On RISC-V, an S-mode store to a page with W = 0 raises a store page fault, with no override bit (from memory; the spec text was not retrieved).

### Protection keys

**Intel PKS.** A 4-bit key per supervisor page and the IA32_PKRS MSR per logical processor, with access-disable and write-disable bits for 16 keys. Sapphire Rapids and later server parts; "future non-server" parts were announced (LKML, LWN, verified). The patch series "PKS/PMEM: Add Stray Write Protection" (v8, January 2022) targets exactly our threat. I could not confirm that it reached mainline: the mainline protection-keys document covers only user PKU and arm64 POE (docs.kernel.org, verified). AMD support for PKS: none, from memory. *Gives:* a cheap switch for the gate, where it exists. *Costs:* not on AMD, not on RISC-V, and not certain on the reference machines. Page granularity, so it does not solve (b).

**Arm POE (FEAT_S1POE, Armv8.9).** User-space use was merged in Linux 6.12. Kernel use ("kpkeys", page-table hardening) is an RFC at v6 (February 2026). An earlier revision said no hardware implemented POE (LKML, LWN, verified). Same granularity limit.

**RISC-V.** No ratified supervisor protection keys found. PMP in M-mode has a small number of regions and cannot express an owner per 2 MB chunk (from memory). Smmpt (above) is the real future candidate.

### Isolation by language or capability hardware

**RedLeaf (OSDI 2020).** Shared-heap objects carry an owner domain ID. It is updated only by *trusted proxies* on cross-domain calls, and on a crash "we scan the entire RRef registry to clean up resources owned by a crashing domain" (full text, verified). *Gives:* (1) the owner field is written by trusted code, never by the domain, which is our gate; (2) the owner set is found by scanning a registry, which is our audit. *Costs:* it relies on Rust safety inside a single address space.

**Theseus (OSDI 2020).** Recovery proceeds in stages: unwind the task, respawn it, swap the corrupted "cells" for fresh copies. Its fault model is mostly hardware-induced faults below the language (full text, verified). *Gives:* little for ownership. The lesson that fits: in the kernel's Rust, make the chunk index unforgeable, so that the gate takes a typed block and never a raw index.

**CHERI.** CheriBSD has shipped a pure-capability kernel by default since 24.05, with "strong referential and spatial memory protection internally in the kernel" (release notes, verified). Each node's code could hold a capability bounded to its own words, which gives deterministic word-level protection. *Costs:* only on Morello and CHERI-RISC-V research hardware. A future option; it needs no hook.

**Arm MTE.** A 4-bit tag per 16-byte granule. A mismatch with random tags is caught with probability 15/16 (kernel docs and papers, verified). Words could be coloured by owner, but there are only 16 colours, it is Arm-only, and in the kernel it is best effort. Not portable: dropped.

---

## 2. The two candidates, attacked

### (a) Per-node claim pages, with ownership = everything no live node claims

**Layout.** Each node has a claim area in kept memory: a bitmap with one bit per chunk of the pool (64 KiB per node for 1 TB, 256 B per node for 4 GB), plus a fixed table of pending offers (say 64 entries: run base, log2 size, target node, target generation). Each node maps its own area writable and every other area read-only.

**Transfers in progress.** A bitmap alone cannot express a transfer without a window where nobody claims the chunk, or where both nodes do. A third state is needed:
1. Giver X writes "offer(run, Y, g_Y)" in its own area. X still claims the run.
2. Y's `memory_take` reads X's area, finds the offer, and sets its own bits.
3. X removes the offer once it sees Y's bits, on X's next call or by message.

Resolution rule: Y's bit beats X's offer to Y; an offer without Y's bit belongs to X. Steps 1-3 are what the draft avoided ("nothing is sent to the other node"). Here X must eventually read Y's area, and the offer table can fill (`busy`).

*Attack: X dies while an offer is pending, and Y is half-way through taking it.* A newly reloaded X′ computes its complement while Y is setting bits, so both own the run. **Closed only by the recovery order.** Before it answers the reclaim request, Y either finishes or abandons every offer from X's dead generation. After it answers, Y ignores offers whose generation is dead. X′ computes its complement only after every live node has answered. So (a) depends on the same "isolate, reset, reclaim, reload" order that the draft already depends on (draft weakness 10). It adds no new dependency, but it relies harder on the existing one.

**Two nodes dead at once.** The complement is the union of both dead nodes' memory, with no live record of which chunk was whose. By the argument of part 0, item 5, any split is safe once reclaim has confirmed that nothing live reaches that memory. The split must be computed from an agreed dead set, as Cellular Disco agrees on its live set; otherwise two reloading nodes could each take the whole complement. Rule: the recovery protocol fixes the set D of nodes being recovered in one round, and chunk c of the complement goes to the node of D at index c mod |D|. **Holds.**

**Free chunks.** A free chunk is a claimed chunk with no block. Nothing special. **Holds.**

**Cost of the complement.** A reloading node reads n − 1 bitmaps: about 8 MiB for 128 nodes and 1 TB, roughly a millisecond of memory bandwidth (estimate, from memory). Other costs:
- Kept memory grows as n × RAM, for example 8 MiB in that case against 4 MiB for the table. Negligible.
- "Who owns chunk c" becomes n probes. That is fine for the hardware node's sweep of a dead node, because it uses the complement too, and `memory_take` needs to read only the giver's area.

**Holds.**

**Do read-only mappings protect a kernel against its own bugs?**
- *Yes, against stray stores and against stores at a wrong index into another node's page.* The store faults before it lands (x86 with CR0.WP = 1, arm64 always, RISC-V always, see part 1), so the node fails stop.
- *No, against a bug in the node's own page-table code,* which can map a foreign page writable. That code is small and modelled, and the gate below protects it too.
- *No, against an instruction that clears CR0.WP on x86.* None needs to exist outside the gate, which can be checked by scanning the kernel binary at build time, as PerspicuOS de-privileges its outer kernel.
- *No, against DMA,* which bypasses CPU permissions. The claim areas must never be mapped writable in an iospace; the frame in slot 13 is read-only already.

**Attack that (a) alone does not survive: the lost claim.** A stray write, or a wrong-index logic error, by X *inside its own writable area* can clear the bit of a chunk X still uses. The page is X's own, so the MMU allows it. The next time any node is reloaded, the complement hands that chunk to the reloading node while X still has objects there. That is cross-node damage, through X's own record. (A spurious *set* bit only leaks a chunk; it is harmless.) So (a) does not confine X's bugs to X unless X's own area is *also* written only through a checked gate, or is audited against X's block records before every complement is computed. **Without a gate, (a) does not hold against the stated threat.**

**Is the write-monitor needed or overkill?** Needed, in its reduced form: one gate per node, the only code that writes ownership records and the only code that maps or unmaps chunks in the kernel's own space. The full Nested Kernel is overkill against bugs: mediating every page-table write, kernel code integrity, de-privileging scans of the binary, a protected IDT. Part 3 gives the reduced form.

**What (a) gives that the table + gate does not.** A bug *inside X's gate* can still damage only X's area, because the MMU in X maps the others read-only. With the table + gate, a gate bug could reach other nodes' words in the same page. That is (a)'s one real advantage, against a component of about a hundred lines with Kani proofs. Its price: the offer state, a cleanup step, a bounded offer table and n-probe lookups.

### (b) Hardware per-owner write rights on the per-chunk table

- **Page permissions.** Granularity breaks it: a 4 KB page holds the words of 512 chunks with independent owners. Two ways out, neither good. A layout of one word per page costs 512 Ki pages × 4 KB = 2 GiB of table for 1 TB, which is absurd. Grouping words by owner turns the design into (a). **Does not hold as stated.**
- **Protection keys (PKS, POE).** Same page granularity. Only 16 keys for up to 65,536 nodes. Not on AMD (from memory), not ratified on RISC-V, no shipped arm64 hardware and no merged kernel use for POE. **Drop as a mechanism.** PKS and POE remain possible *accelerators* for the gate (a WRMSR to PKRS is cheaper than editing a page-table entry), only where present.
- **A thin layer above the kernels** (VMX root / EL2 / M-mode, as in Quest-V, pKVM, Jailhouse, KDP). It gives word granularity, because the layer writes words on request, and it survives *any* kernel bug, including page-table bugs. Costs:
  - The layer is state shared by every node and in every node's trusted base, the thing D-026 avoided. If it fails, the machine stops.
  - Every TLB miss pays a second stage of translation (a few percent, from memory), and every transition pays a VM exit: 0.513 µs per VMCALL, against 0.139 µs for a gate (PerspicuOS, Table 3).
  - Three implementations (VMX/SVM, EL2, H-extension or M-mode), each with its own verification.
  - It collides with D-093. DodOS wants to *host* micro-VMs for Linux drivers. If DodOS itself sits under its own thin hypervisor, that layer becomes the VMM, or the micro-VMs need nested virtualisation.

  **Holds technically; rejected on cost.** Kept as a research comparison point.

---

## 3. The recommended design in detail: table + write gate

### The rule (contract text)

1. No kernel maps the ownership table or the device table writable, its own node's kernel included. Every kernel maps both read-only.
2. A node changes a word only through its **write gate**. The gate refuses to write a word whose current owner is not this node, so it reads and checks each word just before writing it.
3. The gate is also the only code that maps or unmaps a run in the kernel's own address space. This keeps one invariant: *X maps run r in its kernel space exactly when every word of r reads taken(X, X's current generation).*
4. The gate takes a block (a typed reference to the untyped slot) for release and give, and a run for take. It never takes a raw chunk index from the caller for a write. This is the RedLeaf and Theseus lesson: make the index unforgeable in Rust.
5. A reloaded node X′ accepts as free only the words that name X, of any generation. Under rule 2, such a word was written either by X (when it already owned that word) or by a giver handing the chunk to X. Either way the chunk is X's, and after reclaim no live node reaches it. **What dead X could damage is exactly the set X′ takes back, and nothing else.**
6. Single exception, for the cores group to settle: the successor named by the recovery protocol may write words that name a node removed for a hardware fault. The draft already has this hook ("successor writer").

### How the gate writes, per ISA (all three, no x86-only path)

- **Portable default: a temporary writable alias.** With interrupts masked, the gate maps the table page at a fixed private address with write permission, writes, unmaps, and invalidates *locally*. A node runs on one core at a time, so no shootdown is needed. This is how arm64 Linux patches read-only text (fixmap). It works the same on x86, arm64 and RISC-V. Residual risk: the one page-table page that controls the alias slot must stay writable (Linux has the same caveat for its fixmap tables).
- **x86 option: toggle CR0.WP** inside the gate, re-enabling it on every interrupt path (PerspicuOS invariants 8 and 11). There is then no extra mapping, but the gate is the only place where `mov cr0` may appear, which a build-time scan checks.
- **Accelerator where present:** a PKS or POE key on the table pages, with the gate flipping write-disable for its key. Optional; never required.

### Cost

A gate call is of the order of 0.14 µs (PerspicuOS, measured on x86 in 2015). Takes and gives touch at most 512 words and happen at 2 MB granularity, driven by the memory service, so the cost is negligible next to clearing even one chunk. To be measured on the three ISAs (part 4).

### Audit at every recovery round (the Otherworld idea, cheap)

When a live node Y answers a reclaim request, it first checks that every word covered by its live blocks still reads taken(Y, g_Y). That is at most the number of chunks Y holds: 512 Ki reads for 1 TB, about a millisecond (from memory). A mismatch means containment was violated somewhere, possibly by a gate bug in the dead node. kernel.md already says what follows: "a complete stop happens only if containment itself is violated", with a trace. The audit turns the gate's one residual risk into a detected full stop instead of silent cross-node damage.

### What it does not protect

- A bug inside a gate. It is small, has Kani proofs and is in the reference model; the audit detects the damage.
- A wild jump into the middle of a gate. Improbable for bugs; PerspicuOS defends against it only because it targets attackers.
- The judgement "this block has no live descendant" before a give, which belongs to the main kernel's derivation-tree logic.
- DMA written through a bad context entry: draft weakness 1, unchanged.
- Hardware bit flips. The check field stays useful for those, at no cost.

### Effect on the draft

The ownership word, the calls, the transfer protocol, the crash table and the "no message on give" rule are all unchanged. What changes: rule 1 (read-only everywhere), the gate as the only writer and mapper, the audit, and the reload rule written as "words naming this node". The draft's weakness 4 ("the ownership table is writable by every kernel") becomes "the ownership table is writable by no kernel, only through each node's gate".

### The fallback: message-only with the complement rule

The draft rejected "no shared table" because "neither list says which of the two owned a chunk". By part 0, item 5, that does not matter. So:
- Ownership lives only in each node's block capabilities, in its private memory.
- A give is an offer message, which the receiver stores in a fixed table.
- At recovery, every live node sends its claim list in its reclaim answer, which already exists. The reloading nodes split the complement, and the hardware node uses the same complement to find a dead node's memory.

D-107 then holds word for word: no writable part of the machine table at all, and D-114's amendment would not be needed. It costs:
- a message per give;
- a fixed offer table;
- claim lists carried in recovery messages (up to 64 KiB per node at 1 TB);
- the loss of the read-only table that the memory service and debugging can inspect;
- the same lost-claim hazard as (a), which needs the same audit against block records.

I rank it second: it is sound, but it adds more protocol than the gate does.

---

## 4. Ranked recommendation

### Adopt now (contract and one-core kernel)

1. **The table is read-only in every kernel; one write gate per node is the only writer and the only mapper of chunks in kernel space; the gate refuses words not owned by its node.** On one core it is the same function, and the reference model checks invariant 3 with phantom nodes.
2. **The gate's API takes typed blocks and runs, never raw indices**, in the Rust layer.
3. **The reload rule, written as:** "a reloaded node takes back only words that name its node", with the safety argument of rule 5.
4. **The complement principle written into the recovery section:** after reclaim, the memory of the nodes being recovered is everything no live node holds; a split among nodes recovered in the same round, agreed on a common dead set, is safe whatever it is. This settles "two nodes dead at once" and gives the hardware node its sweep set.
5. **The audit in the reclaim answer**, with a mismatch counting as a containment violation (full stop with trace).
6. **A build-time check** that no instruction able to disable write protection (`mov cr0` on x86, writes to SCTLR or TTBR on arm64, `satp` on RISC-V) appears outside the gate and the start-up code. Cheap; it borrows PerspicuOS's de-privileging.

### Keep as a hook (contract and `abi/`)

- In `StartOwnership`, name the existing `reserved: u32` **`layout`**, with 0 meaning "one word per chunk". If (a) or a hardware-backed layout (Smmpt) is ever chosen, the memory service reading slot 13 does not break. Cost: nothing.
- A field in the inter-kernel reclaim answer for the audit result, and room for a claim list (needed only by the message-only fallback). The inter-kernel protocol is versioned anyway.
- The gate exception for the successor of a removed node (cores group).
- In kernel.md's hardware features table: PKS and POE as **optional accelerators of the gate**, never requirements.

### Drop

- Protection keys as the protection mechanism: page granularity, 16 keys, missing on AMD, RISC-V and shipped arm64.
- A thin hypervisor layer for DodOS v1: shared trusted state, a cost on every TLB miss, three implementations, and a collision with D-093. Kept only as a measured comparison point.
- NrOS-style replication of ownership. NrOS itself keeps frame allocation out of the log.
- MTE colouring (Arm-only, probabilistic), and CHERI for now (no target hardware).
- The check field as the defence against logic errors. Keep it for bit flips only, and say so.

### Measure

| Question | How | What decides |
|---|---|---|
| Does the gate stop what the check field misses? | Fault injection in the reference model and on QEMU. (1) Random stray writes from the kernel under test; (2) mutation of `memory_take`, `memory_give` and destruction (off-by-one in runs, swapped node index, a stale block range). Count the corruptions of *another* node's record that survive to a reload, for the draft (check only), table + gate, and claim pages | If table + gate shows zero cross-node corruptions outside injected gate bugs, adopt it as final. If gate bugs dominate, reconsider (a) |
| Gate cost | Microbenchmark of take and give of a 1 GB run on x86 (alias, and CR0.WP), arm64 (alias, on the Mac) and RISC-V QEMU (alias) | Expected negligible; if not, use CR0.WP or PKS on x86 |
| Audit cost | Time to check all words of a node's blocks with 1 TB in QEMU | Must fit the recovery gate |
| Does the reference desktop or the Dell have PKS? | CPUID leaf 7, ECX bit 31 (bit position from memory) | Only whether the accelerator exists there |
| Complement cost (only if (a) or the message-only fallback is chosen) | 128 nodes, 1 TB, in QEMU | Expected about 1 ms |

### What is unproven

- **No precedent recovers a node of a multikernel whose memory changes owner at run time.** Hive comes closest and was never built in hardware; Quest-V partitions statically; Barrelfish and Cellular Disco assume nodes do not fail in software.
- The claim that kernel bugs are mostly fail-stop comes from studies of Linux cited by Otherworld, not from DodOS.
- Rio's benefit of protection is verified only qualitatively here.
- The gate's protection against wild jumps rests on improbability, not on a mechanism.
- Everything rests on the order "isolate, reset, reclaim, reload", which the cores group has yet to specify and model (draft weakness 10). The complement argument is only as safe as that order.
- RISC-V's store-fault behaviour for W = 0 pages and AMD's lack of PKS are from memory.
- Smmpt is a draft and may change or never ship.

---

## 5. How this answers D-114's question

D-114 listed three alternatives: a table written by each chunk's owner, claim pages only their node can write, and protection by hardware. The survey gives a fourth that dominates on cost: **the owner's table written only through a gate that every kernel, the owner included, must pass.** It turns the single-writer rule from a convention into a mechanism. Hive, Rio and Nested Kernel are its precedents; pKVM and the confidential-computing ownership tables are the hardware versions of the same idea, one layer up. Claim pages remain sound but need the same gate. Hardware protection at page or key granularity cannot express per-chunk owners, and a hypervisor layer can but costs too much for v1.

---

## 6. Sources (all retrieved 15 November 2026)

Read in full text (PDF extracted locally):
- von Tessin, "The Clustered Multikernel", SFMA 2012: https://www.trustworthy.systems/publications/nicta_full_text/5618.pdf ; abstract https://trustworthy.systems/publications/nictaabstracts/vonTessin_12.abstract
- Zellweger et al., "Decoupling Cores, Kernels, and Operating Systems", OSDI 2014: https://barrelfish.org/publications/zellweger-decoupling-cores.pdf
- Gerber, PhD dissertation (Barrelfish distributed capabilities): https://barrelfish.org/publications/gerbesim-phd.pdf
- Li, West et al., "Quest-V: A Virtualized Multikernel for High-Confidence Systems": https://arxiv.org/pdf/1112.5136
- Bhardwaj et al., "NrOS", OSDI 2021: https://rs3lab.github.io/assets/papers/2021/bhardwaj:nros.pdf
- Narayanan et al., "RedLeaf", OSDI 2020: https://files.usenix.org/s3fs-public/cdn/osdi20-narayanan_vikram.pdf
- Boos et al., "Theseus", OSDI 2020: https://files.usenix.org/s3fs-public/cdn/osdi20-boos.pdf
- Depoutovitch and Stumm, "Otherworld", EuroSys 2010: https://www.eecg.utoronto.ca/~stumm/Papers/Depoutovitch-EuroSys10.pdf
- Govil et al., "Cellular Disco", SOSP 1999: https://pages.cs.wisc.edu/~stjones/proj/vm_reading/cellular-disco.pdf
- Dautenhahn et al., "Nested Kernel", ASPLOS 2015: http://nathandautenhahn.com/downloads/publications/asplos200-dautenhahn.pdf (project page https://nestedkernel.github.io)

Through abstracts, docs, source or summaries:
- Hive: https://pdos.csail.mit.edu/6.824-2004/handouts/hive.txt ; paper (scan, not read) https://pdos.csail.mit.edu/archive/6.824-2004/papers/hive.pdf
- Rio: https://web.eecs.umich.edu/~pmchen/Rio/ ; https://carlstrom.com/stanford/quals/mirror/www.stanford.edu/~emrek/quals/summaries/The_Rio_File_Cache-Chen-1996.txt
- IronSync / verified NR: https://www.usenix.org/conference/osdi23/presentation/hance ; Verus artifact https://verus-lang.github.io/paper-sosp24-artifact/guide.html
- Popcorn Linux: https://popcornlinux.org/publications/SOSP_Popcorn.pdf ; https://popcornlinux.org/documents/InstallationGuide.pdf
- SemperOS: https://usenix.org/conference/atc19/presentation/hille
- Jailhouse hypervisor interface and control code: https://rtime.felk.cvut.cz/gitweb/jailhouse.git/blob/d93a78c545e009049ca2e67616cdda2891ca82a2:/Documentation/hypervisor-interfaces.txt
- virtio-mem: https://www.ce.cit.tum.de/caps/aktuelles/news-single-view/article/accepted-paper-at-vee21-virtio-mem-paravirtualized-memory-hotunplug-by-david-hildenbrand-and-martin-schulz/ ; https://kunit.googlesource.com/linux/+/refs/heads/memeq/drivers/virtio/virtio_mem.c
- pKVM ownership states: https://zerodayengineering.com/content/kvm-docs/v6.8.0-38-arm64/mem__protect_8h.html ; https://lkml.iu.edu/2502.3/07050.html
- Windows KDP: https://www.microsoft.com/security/blog/2020/07/08/introducing-kernel-data-protection-a-new-platform-security-technology-for-preventing-data-corruption
- SEV-SNP RMP: https://lkml.iu.edu/hypermail/linux/kernel/2412.1/09888.html ; Arm CCA GPT: https://trustedfirmware-a.readthedocs.io/en/latest/components/firme.html ; RISC-V Smmtt/Smmpt: https://lists.infradead.org/pipermail/opensbi/2026-July/010242.html
- Intel PKS: https://lwn.net/Articles/826091/ ; https://patchew.org/linux/20220127175505.851391-1-ira.weiny@intel.com/ ; https://www.lkml.org/lkml/2022/1/27/940 ; mainline pkeys doc https://docs.kernel.org/core-api/protection-keys.html
- Arm POE and kpkeys: https://lkml2.uits.iu.edu/hypermail/linux/kernel/2409.1/08571.html ; https://lkml.iu.edu/2602.3/07865.html ; https://lwn.net/Articles/1004438/
- CR0.WP: https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-77.html
- arm64 text patching via fixmap: https://git.evolution-x.org/anierin/msm-5.15/commit/2f896d586610
- SKEE: https://www.ndss-symposium.org/wp-content/uploads/2017/09/skee-lightweight-secure-kernel-level-execution-environment-for-arm.pdf
- CheriBSD pure-capability kernel: https://cheribsd.org/release-notes/24.05/index.html
- Arm MTE: https://docs.kernel.org/6.11/arch/arm64/memory-tagging-extension.html

From memory (not verified): the RISC-V store page fault for W = 0 with no override; AMD's lack of PKS; the CPUID bit for PKS; the bandwidth estimates (complement about 1 ms, audit about 1 ms); the cost of a second translation stage; per-core Barrelfish memory servers; PMP region counts.
