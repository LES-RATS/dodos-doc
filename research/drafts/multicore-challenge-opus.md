# Challenge of the multi-core execution of DodOS (Opus)

Written 16 November 2026 by Claude Opus 5.5, for the brief `pass14/CHALLENGE.md`. A research draft, not the contract. Another model did the same work separately; I have not read its file.

**Scope.** I read: `architecture/kernel.md` (lines 24 to 181), `architecture/kernel-interface.md` (the rules, address spaces and the TLB, unlike cores, interrupts, memory and devices between nodes, the gate, tasks, cores and roles, the data plane, the open points), the decision log (D-026 to D-028, D-107 to D-124), the research drafts that the contract cites, the 31 files of `reviews/`, the model on branch `model` at `2afc901` (`remote.rs`, `system.rs`, `table.rs`, `roles.rs`, parts of `lib.rs` and `moves.rs`, `tests/nodes.rs`), and the trial results on branch `trial-multicore` at `f9933bd` (`trials/multicore/results-mac-m5.md`, cited below as "M5"). I wrote two tests in a copy of the kernel repository (`/tmp/opus-challenge/k/model/tests/challenge_opus.rs`, appendix A); both pass, which shows the behaviour they describe. I changed nothing else and committed nothing. Outside systems were read at their sources through `curl` and `pdftotext`; each claim names the URL. What I could not open is marked "not verified". A suspicion is marked as one.

---

## 0. The verdict, briefly

The idea holds. The memory layer holds too: ownership words, the write gate, the fence and the reclaim barrier are careful work, and they cost little at run time. The naive part is **how much crosses nodes inside the kernel**. Rule 7 (`kernel-interface.md:17`) and D-122 promise that any call on any object of another node works as if it were local, later. That promise requires a distributed capability system in the kernel: remote calls held by proxies, capability transfer by grants, distributed revocation, `thread_move`, carried calls, unit-role requests. The project then multiplied the lifecycles those protocols must survive: seal, resume, parked and co-hosted nodes (D-108), fencing, unfenced. Almost every severe fault of the sixth and seventh reviews lies in the product of the two: protocols that cross nodes × node lifecycle events.

Barrelfish paid about 8,000 lines and a blocking two-phase protocol for the same promise, in user space. The seL4 multikernel, the path its community agreed on, refuses it: in the kernel, nothing crosses but interrupts (sources in part 4). My recommendation: keep the fixed points and keep the memory layer, and cut the transparent remote call. More detail in part 6.

---

## 1. The protocols between nodes

Two kinds of protocol cross nodes. In the first, kernels exchange **messages**: 18 kinds in the model (`model/src/remote.rs:37-139`). In the second, kernels write **shared words** of the living part of the machine table, each by compare-and-swap through the writer's gate (`kernel-interface.md:748-752`). A third, the core group, is still a hook with no protocol written (`kernel-interface.md:320`, `:1877`).

For each protocol below: what it is for, the application need behind it, its size, and what happens when one party dies.

### 1.1 Message protocols

| # | Protocol (message kinds) | What it is for | The need it serves | States and messages | When a party dies |
|---|---|---|---|---|---|
| M1 | **Remote call**: `Request`, `Answer`, `Cancel` | Rule 7: a call on an object of another node (`:849-860`) | A client calls a service whose thread runs on another core; a wait or signal on a notify of another node | Caller side: held in the FIFO when no proxy is free, then in flight, then waiting on the proxy, then answered (`remote.rs:426-484`). Callee side: 16 proxies per peer, each free, serving or waiting (`:856`). 3 messages | Callee dies: R0 ends the caller's wait with `gone` (`:853`, `:1098`). Caller dies: R0 on the callee frees the proxies (`:1098`). Caller thread destroyed: the request is cancelled there, or completes without it (`:854`) |
| M2 | **Capability transfer**: `TransferAsk`, `TransferGrant` (`Crossing::Grant` or `Home`), `Refused`, `Returned` | A message delivered on Y lists capabilities of X (`:836-839`) | Handing a frame (a shared buffer) or an endpoint to a process on another core | Ask, then grants written by X, then use entries and slots written by Y, or a refusal. Moves go back home. Four kinds; the anchor is held in X's kernel space during the exchange | X dies after the ask: the receiver gets `gone`. Y dies after the grants: X pins them (R3). Receiver destroyed: refused, `caps_dropped` (`:854`) |
| M3 | **Grant revocation and release**: `Revoke`, `RevokeStep`, `Release` | Two-phase revocation of a grant X made to Y (`:842-844`) | Memory safety of shared frames: X's memory never returns to an untyped while Y translates to it | Grant entry: free, live, revoking, pinned (`:833`). Steps of at most 32 units, one answer per step. A release needs no waiter | Y dies: the grant is pinned until Y's generation is over (R3, `:1104`). X dies: Y removes its remote capabilities in R2, or at resume (`:845`) |
| M4 | **Thread move**: `Move`, `Moved` | `thread_move` (`:672-677`) | Placement on unlike cores; load balancing | The source thread and its context are frozen until the answer. Bandwidth stays reserved at the source. 2 messages | Destination dies: both waits end, nothing changes (`:675`). Source dies: the destination never sees the move |
| M5 | **Unit-role requests**: `UnitRequest`, `UnitAnswer` | Attach or detach, invalidate the IOMMU, program the IOAPIC (`:865`) | Shared hardware with one writer: IOMMU units, IOAPIC, GIC | Each request carries the role's epoch. The holder refuses another epoch; the requester re-reads the role word and sends again. Requests are idempotent (`:1212`) | Holder dies: requests are kept and re-sent to the successor (`:1098`) |
| M6 | **Planned hand-over**: `Handed` | Step 4 of a unit role's hand-over (`:1213`) | Sealing a node; moving a role | 5 steps; role word vacant, held or handing | Covered step by step in `:1213` |
| M7 | **Take-over rebuild** (reports) | The successor asks every live node for its report on the unit (`:1214`) | Rebuilding an IOMMU unit, IOAPIC or GIC after its holder dies | One report message per iospace, 192 handles per node | **The model does not send these messages.** The rebuild reads every node's report from a shared table, in one atomic event (`roles.rs:437-456`). Only IOMMU units are modelled (`roles.rs:8-10`) |
| M8 | **Carried call**: `Carry`, `CarryDone` | `core_idle` and `core_perf` on another node (`:1188`, `:1192`) | A central placement service tunes other cores | 2 messages | Ended by R0 |
| M9 | **Ping** | The sweep wakes an idle successor (`:1070`) | Finding nodes that died silently | 1 message, no answer | Unconsumed, it becomes *stuck* evidence |
| M10 | **Mailbox send**: `core` capability as an endpoint (`:1002`) | Services find each other across generations | Start-up and reload | Carried by M1 | As M1 |

### 1.2 Shared-word protocols

These protocols exchange no message.

| # | Protocol | Words and states | Need | When a party dies |
|---|---|---|---|---|
| S1 | **Taking and giving memory** (`memory_take`, `memory_give`, `memory_split`; `:770-813`) | Ownership word: none, free, taken; owner; generation (`:759-769`). Four rules of taking (`:770-776`) | Memory moves between nodes (the equal split was rejected by D-112) | "Each word is resolved alone" (`:813`) |
| S2 | **Membership** (`:1006-1048`) | Member word: 8 states and 13 transition rows | Recovery: a fixed point | Driver replaced; node dying while starting or while sealing (`:1136-1137`) |
| S3 | **Detection** (`:1058-1073`) | Beacons, 8 observations per node, 6 kinds of evidence | Recovery | — |
| S4 | **Fence** (`:1077-1092`) | x86-64: 5 steps; ARM64: SDEI then `CPU_OFF`; RISC-V: the DodOS SBI extension; fence classes 0 to 2 | Recovery | Driver replaced; *unfenced* state |
| S5 | **Reclaim and barrier** (R0 to R6, `:1096-1126`) | `acked[n]`, `maps_of`, R6 cursor | Recovery | Two failures (`:1135`) |
| S6 | **Roles: claim and hand** (`:1196-1222`) | Role word: vacant, held, handing; epoch; successor rule | Shared hardware; no privileged node (D-115) | Take-over after `SETTLE_NS` (`:1205`) |
| S7 | **Grant and use tables** (`:833-835`) | Entries written by each node's own gate; cleared by R6 | Supports M2 and M3 | R6 |
| S8 | **Device identifier words** (`:339`) | One word per PCI identifier | Ownership of a device on a unit | R6. A fault here was found in review 7 (section 2) |

### 1.3 The core group

**What it should be.** A copy of a process's address space on each node of its core group. A change is applied at home, sent to the other nodes, each acknowledges, and the call waits for every acknowledgement (`:320`).

**Need.** Native multithreaded code: Ladybird, inference. WebAssembly has no threads in WASI 0.3, and "the parallelism of a Wasm application goes through several instances, which suits one kernel per core" (`wasm-abi.md:128`).

**State.** **No message kind exists. No protocol is written** (`:1877`). The model never enters the waiting state of the group (`lib.rs:19`). The most demanding need of the design is the one protocol that is neither specified nor modelled.

**What the inventory says.** M1, M2, M4, M8 and M10 exist to make another node's objects look local. M3, M5 to M7, M9 and S1 to S8 exist because memory, hardware and failure are truly shared. This split matters for the proposals.

---

## 2. The evidence: where the confirmed faults lie

**Which rounds touch protocols between nodes.** Rounds 1 to 5 of the reviews (14 November) cover the one-core model only. Their file headers say "one-core model". The multi-node contract was integrated on 16 November (D-122, `decisions/README.md:132`). So the evidence on protocols between nodes is **two review rounds (6 and 7) and two model passes (12 and 13)**, not thirteen. Passes 1 to 9 and 10 to 11 were one-core work (`plan/progress.md:90-91`).

| Source | Findings | Between nodes | Share | Notes |
|---|---|---|---|---|
| Pass 12 of the model (the 8 problems settled by D-123, `decisions/README.md:133`) | 8 | 7 | 7/8 | All but the rate limit of the kernel ring: barrier and IOMMU, transitions, `thread_move`, pinned grants, own-node argument, R6, handing word and cancel |
| Review 6, four reports, 38 findings (D-124; all confirmed at least in part, `plan/progress.md:90`) | 38 | 17 | 45 % | Hydrogen: 11 of 11. DeepSeek: F3 (device identifier). Argon: F1 (`core_stop`). Mistral: F1, F2 (fence classes), F3 (interrupts between cores through the gate), F6 (RISC-V single writer, a role question) |
| Review 7, confirmed by at least one verifier (verification files) | about 24 | about 13 | about 54 % | Hydrogen: 9 confirmed by both verifiers (F1 to F8 in part, F11), F9 and F10 disputed. Mistral: F1 to F3 (fence and routing). DeepSeek: F12 (a wording on reclaim). DeepSeek's other 10 confirmed faults lie in the gate on one node. Argon 1.1 (device identifier word wedged across a fresh restart) is not verified by a second model |
| Pass 11 (23 problems in the contract text) | 23 | not classified | — | The problems are not listed one by one in the repository; I did not count them |

**Severity tells more than the share.** In review 7, every fault that a verifier rated "breaks isolation between nodes" or "blocks for ever" lies in a protocol between nodes. The verdict tables of `2026-11-16-model-review-7-verify-hydrogen-by-deepseek.md` and `...-by-opus.md` rate them so for F1, F2, F3, F4 and F8. The confirmed faults of the gate are "wrong result" or "wording" (`...-verify-deepseek-by-hydrogen.md`, summary table).

### The families that come back, pass after pass

| Family | Pass 12 | Review 6 | Review 7 | Root cause |
|---|---|---|---|---|
| **Names reused across in-flight messages (ABA)** | — | Hydrogen F1 (serial reuse, a stale node destroys a third node's mapped grant) | Hydrogen F1 (stale `RevokeStep`), F3 (`Move` and `Request` without serial), F6 (`Refused` names) | Grant entries are recycled at once on a local free, while messages that name them are still in flight. D-124(1) added serials to the contract, but the model's message bodies kept bare `u16` indices |
| **Teardown of state held for another node** (proxies, requests, held requests, transfers) | (8) cancel of a held request | F3 (proxies leak), F4 (R0 omits `Move` and `Transfer`) | F5 (`unlink`), F6 (stranded moved capability), F7 (unhandled remote arguments) | Every new terminating event must visit every kind of state held for a peer |
| **Parked, sealed and co-hosted nodes** (D-108) | (3) live to sealed transition | F2 (sweep accuses a sealed node), F7, F8 (co-hosted) | F2 (`core_place` then `core_stop`), F4 (resume skips R0 and R3) | One physical core hosts several node lifecycles |
| **Roles and units** | (1) barrier and IOMMU context entries, (8) handing word | F5 (reserve chunks), F6 (hand-over skips R1), F9 (unfenced driver dies) | F8 (unit request lost when the role comes back) | One writer for shared hardware that must survive its holder |
| **`thread_move`** | (4) | F11 | F9 (resume during a move) | Freezing a thread across two kernels |
| **Pinned grants and clearing** | (5), (7) R6 | F10 | — | Memory that the dead node's devices could still reach |
| **Device identifier words** | — | DeepSeek F3 | Argon 1.1 | A shared word whose owner can restart fresh |

**What the evidence says.** The families recur because the same root causes stay in place. Each review closed the instances it found. None closed the cause. With two rounds of data, I cannot tell convergence from a plateau: review 7 found as many inter-node faults as review 6 (11 against 11 in the Hydrogen reports). That is not what convergence looks like after a full correction pass.

Two families are the price of the fixed points: roles and units, pinned grants and clearing. Recovery cannot exist without them. Three come from choices that are open: names in flight, teardown of state held for another node, and `thread_move` come from rule 7's transparency; parked nodes come from D-108.

---

## 3. Where it breaks

### 3.1 Correctness

**C1. One process can stop every other process of its node from calling a peer node. Confirmed by a test.**

- *The rule.* Each node keeps 16 proxies per peer, and "a request that finds no free proxy waits on the caller's node, first in first out" (`:856`). The model counts every request against that pool, waits or not (`remote.rs:472-481`).
- *The test.* `challenge_sixteen_idle_waits_of_one_process_block_every_request_of_the_node_to_its_peer` (appendix A). Sixteen threads wait on a remote notify that nobody signals: an ordinary idle state, such as event loops waiting for work. Another thread then signals a different notify of the same peer. The signal never leaves its node. Eight simulated seconds later the peer's notify is still unsignalled, and no rule ends the wait.
- *The consequence.* Any process holding one remote capability and 16 threads can freeze, for every other process on its node, all calls to that peer: a client's `call` to a server, the supervisor's requests, the memory service's IPC. It needs no fault and no privilege. Detection cannot see it: the peer consumes its ring, so there is no *stuck* evidence. This is an isolation failure between processes, and the contract does not mention it.
- *Status.* Not reported in the seven rounds. The nearest finding is review 6 Hydrogen F3, about leaked proxies, which is a different bug.

**C2. The rings between kernels are not in the contract.**

- *What exists.* Their format, capacity, ordering and full-ring behaviour are not specified. The only definition is in a draft: "Each ordered pair of nodes has a ring ... with a producer index ... and a consumer index" (`research/drafts/symmetric-nodes-recovery.md:249`), and FIFO order per pair appears only at `:587` of the same draft. The contract cites "the rings between kernels" only as a component of the Zig layer (`:1832`) and in G6 (`:890`).
- *Why it matters.* The verifiers of review 7 had to decide which message orders were legal. They chose ring order (FIFO per pair) and found that three tests of the repository break it (`...-verify-hydrogen-by-opus.md:122`, N3).
- *The second test.* `challenge_releases_owed_to_one_node_are_bounded_only_by_its_grants` puts 64 releases in flight from one node to another. Releases are sent "with no thread waiting" (`:844`), so nothing bounds them but the grant table: up to 4,096 per peer. The model's outbox is an unbounded vector (`remote.rs:304-312`, `lib.rs:979`).
- *The open question.* A real kernel with fixed rings and no heap (rule 3) must say what happens when a ring is full: the removal step returns `again`, the message is dropped, or the ring is sized for the worst case. The contract says none of these. A bound on every call (rule 4) depends on the answer.

**C3. Concurrency at the level of words is neither specified nor modelled.** The model runs "every event of a node ... alone" (`system.rs:5-7`). Every node's copy of the machine table is "equal to the others after each event" (`table.rs:143-146`). A real kernel interleaves single words. The contract fixes no memory ordering for the living part; its only ordering rule is for the trace rings (`:1271`). The model cannot see the following orders, which the contract does not settle:

- **Contested `memory_take`, found by reading.**
  - *The rule.* A take writes up to *E* words "in ascending order" (`:803`), each by compare-and-swap. A lost compare-and-swap leaves the word as it was (`:752`).
  - *The case.* After a death, all of the dead node's chunks are free for every live node (rule 3, `:773`). Two memory services on two nodes take overlapping runs at the same time. Both pass the state check (`:801`), then race word by word. If X wins the low words and Y wins the high words, each holds half a run.
  - *The gap.* The contract does not say whether the call undoes its words and returns `busy`, or leaves a run cut in two. The paragraph on crashes covers only a crash (`:813`).
  - *The fix.* Undo the words already written and return `busy`. Ascending order makes this free of deadlock.
- **Torn reads in the barrier check, found by reading; a suspicion of a real fault.**
  - *The rule.* The barrier holds when every unit role is held by a live node that has `acked[X]` = *g* (`:1124`). A new unit holder writes `acked[X]` back to 0 before it writes held, and acknowledges again only after R1 (`:1215`). The gate re-checks "at most *n* beacons and the role table" (`:1124`), in no stated order and with no snapshot.
  - *The interleaving.* A checker reads the new holder's beacon first, while it still holds *g* from an earlier acknowledgement. The holder then writes 0 and held. The checker then reads the role table: a live holder. This mixes two instants, and the barrier holds while the unit may still have a context entry that names X.
  - *The fix.* Read the role words with their epochs, then the beacons, then the role words again, and retry if an epoch changed.
- **Memory ordering.** On ARM64 and RISC-V, a node must publish `maps_of` bit Y "before this node makes its first translation" (`:1053`). The contract does not say that a barrier instruction orders the two writes. The same holds for every "write A, then write B" in R5, R6 and the hand-over.

These are exactly the faults a model with atomic events cannot reach. D-027 promised the models checked by state exploration (`kernel.md:33`, `:1893`); none exists. I found no `.tla` file under `/Users/btw/Documents/repos`.

**C4. The hardest need is unspecified.** The core group (section 1.3) has no protocol, and the brief's most demanding scenario depends on it. Several facts make it worse than a gap:

- *Every change waits.* A map waits for every acknowledgement (`:320`), although the TLB guarantee lets additions be lazy (`:318`). M5 lists this as a point unfair to candidate 1 (M5:282).
- *Lazy additions are not free.* They would need a fault-driven fetch from home: a new protocol of the Popcorn kind (part 4).
- *The model skips the report protocol.* The take-over rebuild reads every node's report from a shared table (`roles.rs:437-456`) instead of exchanging messages. So the model has not checked the message protocol the contract describes (M7).

**C5. Hardware assumptions to keep in view.** The contract already flags most of them; the reviews confirmed them.

- **Fence classes.** Class 1 on ARM64 rests on SDEI and an EL2 kernel. The Trusted OS case cannot be known from standard interfaces as written: review 7, Mistral F1, judged "wrong, with the right fact" (`MIGRATE_INFO_TYPE` exists).
- **Writes posted by a stopped core.** That they reach their device within `SETTLE_NS` is "the one hardware assumption, to test" (`:1217`).
- **GIC routing.** It is MMIO, so the binary scan cannot see it (review 7, Mistral F3, confirmed).
- **ASIDs on Armv8.** The seL4 BoF of 2025 recorded "ASIDs have to be consistent across cores for same address spaces on armv8", attributed to Gerwin Klein, and disputed by David Cock as needed only "for shared TLBs that never got implemented" ([BoF notes](http://www.mail-archive.com/devel@sel4.systems/msg04563.html)). The contract allocates tags per node (G7, `:891`). **Not verified** in the Arm Architecture Reference Manual. If Klein is right, a multi-node address space needs one ASID across nodes: shared state that the contract does not have.

**C6. Two failures and recovery during another protocol.** The contract treats them (`:1134-1138`), and the reviews found many faults there (section 2). The liveness tests do not explore double faults, moves between nodes, or threads stuck on another node (review 7, Hydrogen F11, confirmed by both verifiers).

### 3.2 Performance and use

**P1. The grant table caps a process spread over several nodes. Shown by arithmetic from the contract.**

- *The rules.* A frame holds at most *E* pages (`:236-237`): 2 MiB with 4 KiB pages on the reference machine. Each copy of an address space maps the frames under grants (`:320`). Every grant is between the object's node and one holder (`:839`). A granting node has `GRANTS` = 4,096 entries for all its grantees and all its processes (`:833`). The rings between kernels are grants too (G6, `:890`). Mapping several pieces of one frame with different rights takes one derived capability per piece (`:295`); those derivations stay under the same grant on the holder (`:840`).
- *The count.* A 4 GiB heap in 4 KiB pages is 2,048 frames. Spread over the home node and *k* − 1 others, it needs 2,048 × (*k* − 1) grant entries on the home node. At *k* = 3 it takes the whole grant table of its home, for every other process of that node too. Each holder also spends 2,048 of its 4,096 use entries.
- *What avoids it, and the cost.* Large-page frames avoid the ceiling (a frame of 2 MiB pages covers 1 GiB), at the price of 2 MiB granularity for guard pages, copy on write and protection.
- *Status.* `GRANTS` is "provisional" and "to measure" (`:1890`). The structure is the problem, not the number: the cost of the per-node copies grows as frames × nodes.

**P2. A process on several nodes pays every change in messages.**

- *What M5 measured.* M5 measured this choice directly (with the interrupt modelled, not measured). At *k* = 4, groups sized to the process (candidate 3) lead on unmaps when every thread unmaps: by 28 to 45 % at `ipi` 0, and 1.55 to 2.0 times at 1 µs (M5:1060). They also lead on change latency, 2.3 to 9.6 times lower at 1 µs (M5:651). One node per core (candidate 1) leads on IPC by 1 to 2 %, at the edge of the noise (M5:652), and on many-to-one signals by 6 to 8 % (M5:1056).
- *What M5 did not measure.* Memory: "candidate 1 keeps a copy of the page tables ... per node" (M5:307). ARM's broadcast TLB invalidation, which "would favour groups further" (M5:274).
- *History.* Barrelfish needed NUMA-aware multicast trees before its message-based unmap beat Linux and Windows on 32 cores. Its naive broadcast did not scale as well ([multikernel paper, §5.1](https://www.read.seas.harvard.edu/~kohler/class/aosref/baumann09multikernel.pdf)). The contract sends from home to every node of the group, with no tree (`:320`).

**P3. IPC between cores is second class by design.**

- *Lends stay on one node.* "No lend crosses nodes": a passive server reached from another node is "marked as having lost its context" (`:607`, `:858`). So every service that serves several cores needs one thread per core (D-028), with its state replicated or shared in user space.
- *The busy-server measure.* M5's busy-server series shows that the policy dominates the candidate: p99 of 170 µs FIFO, 59 µs lending, 58 µs refusal, 10 to 15 µs with two server threads (`plan/progress.md:106`; M5:1023).
- *Consequence.* A remote call through the kernel brings little that a ring plus a remote signal would not. The data plane already chose rings and a notify (`:1782-1787`).

**P4. Every interrupt of a device lands on one core.**

- *The rules.* A device belongs to its driver's node, and "its interrupts are claimed through that node's `irq_control`" (`:784`). An `irq` is a vector "of that node's core" (`:687`). "An interrupt never sends a message between kernels" (`:606`).
- *The consequence.* A multi-queue NIC or NVMe controller cannot spread its MSI-X vectors over the cores that consume its queues; the driver forwards work by messages instead.
- *When it matters.* Little on a desktop with a 2.5 GbE NIC and one NVMe drive. A lot on 64 cores with 100 GbE. I found no measure of it in the repository.

**P5. `thread_move` and unlike cores.** The design is sound for placement "re-examined every few periods" (`kernel.md:72`). The move costs one exchange of the register block and the save area (`:676`), plus two frozen states and the faults of section 2. It could be done with local calls by an agent on each node, if the kernel could export and import the vector save area. D-112 says "no vector state in the register calls" (`decisions/README.md:122`). That is the one missing piece.

**P6. Two cores and 64 cores.**

- *Two cores.* Every service that must survive a node runs on both nodes (`kernel.md:49`). The process with threads on both dies with its home. The last-node rules hold (`:1138`).
- *64 cores.*
  - The n² beacons are small (8 × 64² bytes).
  - The 16 proxies per peer are about 1 MB per node.
  - The 4,096 grants are shared by 63 peers.
  - An unmap in a group of 64 waits for 63 acknowledgements sent one by one.
  - Every interrupt of a device lands on one core (P4).
  - The sweep scales (two successors per node).

**P7. The common case against a kernel with shared state.**

- *What is unmeasured.* The gate costs: a root load per switch of address space, a gate call per mapping change, and on ARM64 and RISC-V a gate call per interrupt to another core (`:902`). Its own text says "Not measured".
- *What M5 says.* With interrupts modelled, the per-core kernel matches a locked group on lookups and IPC and loses on changes (P2). The contest "is decided by three quantities the Mac cannot measure: the real cost of an interrupt, the real kernel work per call, and the rate of changes to shared structures in real programs" (M5:250-256).
- *Conclusion.* Nothing in the repository yet shows that the per-core kernel pays for itself in the common case. Nothing shows that it does not.

---

## 4. What others did, and what happened to it

| System | What crossed kernels | What they refused to make cross | What they regretted, or what happened | Source |
|---|---|---|---|---|
| **Barrelfish** (2009) | Capabilities, via a user-level monitor per core. A one-phase commit for unmaps; a two-phase commit for retype and revoke. Replicated or shared page tables | Shared kernel state: "CPU drivers cannot directly communicate with each other" | "By far the biggest distraction came from adopting the seL4 capability model for memory management" (Baumann, 2021). NrOS reports the capability system as "about 8,000 lines of code not including the two domain-specific languages", with "a blocking two-phase protocol so complex that it is explicitly encoded as a large state machine". barrelfish.org: "The Barrelfish project is no longer active"; no reason stated | [SOSP'09 §4.6-4.8, §5.1](https://www.read.seas.harvard.edu/~kohler/class/aosref/baumann09multikernel.pdf); [retrospective](https://www.sigops.org/2021/fish-in-a-barrel-an-insiders-retrospective-of-the-sosp09-multikernel-paper/); [Gerber and Roscoe 2016](https://simu.github.io/static/pubs/osdi16.pdf); [NrOS §2](https://rs3lab.github.io/assets/papers/2021/bhardwaj:nros.pdf); [barrelfish.org](https://barrelfish.org/) |
| **Barrelfish/DC** (OSDI 2014) | A kernel control block per core, moved and multiplexed; kernels replaced core by core | — | "we do not consider fault tolerance and isolation for now" (§4) | [paper](https://barrelfish.org/publications/zellweger-decoupling-cores.pdf) |
| **seL4 clustered multikernel** (von Tessin, 2012) | Nothing in the kernel: "IPC only works within a node, communication across nodes has to be implemented via shared userlevel memory"; a big lock inside a node | Kernel resources across nodes: "kernel resources being bound to nodes" | Proof of concept; two correspondence proofs missing | [paper](https://trustworthy.systems/publications/nicta_full_text/5618.pdf) |
| **seL4 static multikernel** (Proofcraft, 2023 to 2026) | "minimal cross-core communication". BoF 2025: "Cross-core communication only in userspace", "Once seL4 kernels boot, the system is static"; Heiser, asked whether more than IPIs is needed: "No" | Dynamic resources between kernels; memory is partitioned before boot | Still in progress (2026: "extending the seL4 proofs to support a static multikernel configuration") | [Proofcraft 2023](https://proofcraft.systems/news-2023/); [Summit 2024](https://sel4.systems/Summit/2024/abstracts2024.html); [Summit 2025](https://sel4.systems/Summit/2025/abstracts2025.html); [BoF notes](http://www.mail-archive.com/devel@sel4.systems/msg04563.html); [Proofcraft 2026](https://proofcraft.systems/news-2026/) |
| **NrOS** (OSDI 2021) | A shared operation log per replicated structure, one replica per NUMA node; TLB shootdown by IPI | Point-to-point messages between kernels (they criticise "n² messages") | NR later verified (IronSync, Linear Dafny). Liveness not verified | [paper](https://rs3lab.github.io/assets/papers/2021/bhardwaj:nros.pdf); [IronSync](https://www.andrew.cmu.edu/user/bparno/papers/ironsync.pdf) |
| **Popcorn Linux** | Thread groups, address-space consistency and thread migration between kernels, through a messaging layer and a page coherency protocol | — | Research prototypes; its IPI protocol was questioned when reused by the Linux multikernel RFC of 2025 | [ICDCS 2015](https://www.ssrg.ece.vt.edu/papers/icdcs2015_katz.pdf); [SYSTOR 2013](https://popcornlinux.org/publications/Systor2013_Popcorn_Final.pdf) |
| **Linux multikernel RFC** (September 2025) | Kernel instances on dedicated cores, an inter-kernel IPI framework | — | Reviewers asked for evidence and benchmarks against KVM; I found no later revision | [thread](https://lkml.iu.edu/2509.3/01073.html) |
| **Hive** (SOSP 1995) | RPC between cells, "sets timeouts whenever waiting for a reply"; direct remote reads under a "careful reference protocol"; spanning tasks with a consistent address-space map | Write-sharing of user pages across cells, judged hard to make safe | Needed firewall hardware; "consensus among the surviving cells is required to reboot a failed cell", and all cells suspend user processes during recovery. The policy process Wax "exits whenever any cell fails" and restarts from scratch | [paper](https://pdos.csail.mit.edu/archive/6.824-2004/papers/hive.pdf) |
| **Tornado** (OSDI 1999) | Shared memory, with clustered objects: per-processor representatives; "all locks are internal to the objects ... and no global locks are used" | Global locks | K42 not opened: **not verified** | [paper](https://www.eecg.utoronto.ca/~stumm/Papers/Gamsa-OSDI99.pdf) |
| **Corey** (OSDI 2008) | What the application declares shared: address ranges, shares, kernel cores | Implicit sharing: "the kernel should arrange each data structure so that only a single processor need update it, unless directed otherwise". Linux TLB shootdown measured at 18,742 cycles on 16 cores against 5,092 on 2 | Prototype | [paper](https://static.usenix.org/event/osdi08/tech/full_papers/boyd-wickizer/boyd-wickizer_html/index.html) |
| **fos** (2009 to 2011) | OS services as fleets of message-passing servers in user space | Kernel-level sharing | Abstracts only: **not verified** in full | [DSpace](https://dspace.mit.edu/handle/1721.1/61640) |
| **Tessellation** (HotPar 2009) | Space-time partitions (cells) with secure restricted channels between them | Fine-grained sharing between partitions | — | [paper](https://people.eecs.berkeley.edu/~krste/papers/tessellation-hotpar2009.pdf) |
| **Quest-V** | Shared-memory channels between sandbox kernels; a monitor per sandbox, through hardware virtualization | Kernel state across sandboxes; isolation by two-stage translation, which DodOS refuses (D-117) | Online recovery of drivers shown | [arXiv 1112.5136](https://arxiv.org/pdf/1112.5136) |
| **Theseus** | One address space, state spill avoided by design | — | Two of 13 recovery cases hung, which "can be solved via timeouts" | [paper](https://par.nsf.gov//servlets/purl/10250904) |
| **Hubris** | One core: "Behavior in multicore situations is not yet defined"; generations of tasks, a supervisor restarts them | Runtime creation of tasks | — | [reference](https://hubris.oxide.computer/reference/) |
| **LionsOS** | Components distributed across cores, single-producer single-consumer shared-memory queues, a static system description | Multithreaded components | Core management "work in progress" | [arXiv 2501.06234](https://arxiv.org/pdf/2501.06234) |
| **Mitosis** (ASPLOS 2020) | Page tables replicated per socket | — | Up to 1.34 times on multi-socket workloads (abstract) | [ASPLOS abstract](https://asplos.hosting2.acm.org/wp/wp-content/uploads/2020/abstracts/paper_3_2.html) |

### What the record says

1. **Only Barrelfish crossed capabilities between kernels, and it did so in user space.** Its own authors call the memory side of that model their biggest distraction; NrOS calls the result the reason multikernels "fail to exploit the simplicity ... of shared memory". DodOS does the same in the kernel, with no monitor, plus recovery. No system I found combines a distributed capability system in the kernel with recovery of one kernel.
2. **The seL4 path keeps the kernel out of everything between cores except interrupts**, and pushes communication, dynamic sharing and policy to user space. The same people pass verified multikernels through it.
3. **Recovery precedents use timeouts and hardware help.** Hive used both; it also used global agreement and suspension during recovery. DodOS's evidence-based accusation without a vote (`:1073`) is a real step beyond Hive, and I found no fault in its idea. It has the same price: a slow node may be fenced (`:1072`).
4. **Shared address spaces across kernels were done by shared tables or by coherency protocols**: Barrelfish with a single table per process (NrOS §6.3); Corey with explicitly shared ranges; Popcorn with a page coherency protocol; Hive with a consistent address-space map. DodOS's per-node copies plus per-frame grants combine the costs of replication with the bookkeeping of capabilities.

---

## 5. Proposals, one weak point at a time

The fixed points are kept in every proposal: one kernel per core, no mutable kernel state shared between kernels, recovery of one kernel, no heap, capabilities, a guarantee paid at a failure or a rare event. Ideas not tried elsewhere are marked **[new]**.

### W1. The transparent remote call: rule 7, M1, M2, M4, M8, M10. **Change: cut it.**

**Alternative A: the kernel crosses nodes only for memory, signals, stamped messages and failure.** Keep:

- ownership words (S1);
- grants of frames, with revocation and release (M3, S7);
- membership, fence, reclaim and roles (S2 to S6, M5 to M7, M9);
- **a remote signal**: OR bits into a notify of another node, fire-and-forget, idempotent, so it holds no state on the receiver;
- **a stamped send** into a bounded per-peer kernel queue of the receiving node's mailbox. It carries no capability except grants of frames, never waits on the remote side, and returns `busy` when the queue is full. It keeps what research axis 1 needs: the receiver reads an unforgeable task identifier and marks (`:935-947`).

Cut, and move to user space over rings in granted frames (the data plane's own model, `:1782-1787`):

- remote calls and waits held by proxies;
- transfer of capabilities other than frames;
- `thread_move` as a kernel exchange, which becomes local calls by an agent on each node, once a vector save area can be exported and imported;
- carried calls, which the agent on the target node makes locally.

| | |
|---|---|
| **Removes** | 11 of the 18 message kinds (`Request`, `Answer`, `Cancel`, `TransferAsk`, `TransferGrant` except a frame-only offer, `Refused`, `Returned`, `Move`, `Moved`, `Carry`, `CarryDone`). All waits held on another node for an object, so proxies, held requests and outstanding counters. Contract lines 847-860, most of 836-840, 670-677. In the model, an estimated 900 of the 1,424 lines of `remote.rs` (lines 316 to 1255 serve calls and transfers) and the 269 lines of `moves.rs`, with their tests. Faults of section 2 that could not have existed: review 6 Hydrogen F3, F4, F11; review 7 Hydrogen F3 (the `Move` and `Request` part), F5, F6, F7, F9; pass 12 (4) and (6); and C1 above |
| **Costs** | Nothing on an ordinary access. A cross-node service call costs a ring write plus a remote signal: about the same messages as now. One more copy if the payload does not already live in a shared frame (rule 8 already forbids data in IPC) |
| **Lost** | The illusion that placement is invisible to the caller (rule 7's "same result, later"). Capabilities to non-memory objects of another node: a process manipulates kernel objects of another node only through that node's agent. Synchronous call semantics across nodes, which lending already did not give (`:607`) |
| **To measure** | Round-trip latency of a ring plus remote signal against the current M1 on the reference desktop. How many calls of real services cross nodes |

### W2. The core group: per-node copies and grants per frame. **Change.**

**Alternative B: one page table per process, owned and written by its home node.** Cores of other nodes load the home's root under a grant of the whole address space. Barrelfish did this ("a single page table per process", NrOS §6.3). Corey shares hardware page tables for shared ranges.

The pieces:

- The gate of Y loads a root it holds a live aspace grant for. G7 changes from "owned by this node" to "owned or granted as a root".
- A change is made by home's gate, then one invalidation request per node that loads the root, then the acknowledgement. This is the same number of messages as today, without copies.
- When home dies, R2 becomes "stop loading its roots, flush their tags": the process dies with its home anyway (`kernel.md:48`).
- When home revokes a grant from Z, it invalidates on the nodes that load its roots before it acknowledges Z. **[new in this form]** The dependency set of the barrier is "the nodes where X's roots are loaded", which X records like `maps_of`.

| | |
|---|---|
| **Removes** | The per-node copies, their memory and their tables. The 2,048 × (*k* − 1) grants of P1, which become one aspace grant per node. The protocol for changing the size of a group, which becomes "load or stop loading the root". Most of the unwritten core-group protocol |
| **Costs** | Remote page walks reach home's memory: on one socket, through the shared L3. Mitosis reports up to 1.34 times on multi-socket machines (abstract), so it matters only there. The TLB shootdown by message stays |
| **Lost** | Address spaces between cores with different page-table formats (the multikernel paper names this as the reason for replication). The contract already forbids a node on a core whose kind lacks its features (`:645`) |
| **To measure** | Page-walk latency through another core's tables on the reference desktop |
| **Open** | The Armv8 ASID question of C5 |

**Alternative B′.** The open question of `kernel.md:51-59`, a node on several cores, is outside the fixed point "one kernel per core" as the brief states it, so I do not propose it. But M5 favours it on exactly the operations B targets, and it changes what containment costs less than it seems: a process with threads on several nodes is already lost with its home (`kernel.md:48`).

### W3. The shared proxy pool (C1), if rule 7 stays. **Change.**

Two possible fixes:

- Charge proxies per task or per process, with a quota. The waits of one task then never hold another task's requests.
- Or cut remote waits: `call`, `recv` and `wait` on another node's object become `invalid`, and only non-waiting requests cross.

The second leads to A.

### W4. Rings between kernels (C2). **Change: write them into the contract.**

The contract needs:

- the ring per ordered pair, FIFO;
- its capacity, a value of the machine;
- the rule when it is full: the sending step returns `again` and keeps its place;
- how many slots each kind may need at most. Under A: unit requests, stamped sends bounded per peer, releases bounded by grants.

Then the model needs a bounded ring that the tests cannot reorder.

### W5. Names of grants in flight (ABA). **Change.**

**[new as a discipline]** Make the full name (node, generation, index, serial) one type in `abi/`: the only way any message body can name a grant. Add a check, a unit test or a Kani harness, that every `Body` variant naming a grant uses it.

This removes the family of review 6 Hydrogen F1 and review 7 Hydrogen F1, F3 and F6. Its cost is 8 bytes more per name in a message.

### W6. Parked and co-hosted nodes (D-108). **Cut from version 1.**

Keep the node block, its format, and seal and resume on the same core: these are needed for core-by-core replacement (`kernel.md:181`). Cut parking a node on another core's kernel. An idle core sleeps in place: idle cores need no heartbeat (`idle_until`, `:1052`) and wake on an interrupt.

| | |
|---|---|
| **Removes** | The transition from live to sealed by host, the evidence *host*, the save-seal checks of the fence on a shared core, `core_place`, the sum of several nodes on one core (`:614`). The faults of review 6 Hydrogen F7, F8; review 7 Hydrogen F2, F4; pass 12 (3) |
| **Costs** | Energy, if a deep-idle core that takes rare interrupts uses more than a parked one. Not measured |
| **To measure** | Package power with *n* − 1 cores in their deepest state and an occasional IPI, against the same load with nodes parked on one core |

### W7. Concurrency at the level of words (C3). **Change, urgently.**

1. Write a memory-ordering rule for the living part: which writes are releases, which reads acquires, and the order of each multi-word step in R5, R6 and the hand-over.
2. Write the outcome of a lost compare-and-swap in the middle of `memory_take`.
3. Make the barrier check a consistent read with epochs.
4. Then build the model D-027 promised, at word granularity, with each word access a step: TLA+, or Rust with `loom` or `shuttle` over the gate's functions. The current `System` cannot reach these faults.

### W8. Device interrupts on one core (P4). **Change, after version 1 if the desktop does not need it.**

Allow a node that owns a device to give a **vector grant** on its queues to another node. The remapping entry of a vector then names the other node's core and lives in that node's handle range, written by its gate. The device's iospace stays with its owner. **[new]**

| | |
|---|---|
| **Costs** | A grant entry per vector; a role request to invalidate the interrupt entry cache, as today |
| **To measure** | NIC or NVMe throughput with one interrupt core against interrupts spread over cores |

### W9. Things to keep as they are

- **Ownership words and the write gate (S1).** Local compare-and-swap, no messages, few faults. The decisions are D-112 to D-115 and D-120, and I found no structural fault in them.
- **Membership by evidence without a vote (S2 to S5).** It is the price of the fixed point, and it is better than Hive's agreement round (part 4).
- **Unit roles with epochs (M5 to M7, S6).** Shared hardware needs one writer. Keep, and model the report messages.

### W10. The alternatives the brief names

- **Only rings and a fence in the kernel, everything else in a user-level service.** It cannot hold: blocking DMA, stopping a core and the barrier on translations must be in the kernel, or containment fails. Its sound part is A.
- **A static partition, as seL4 does.** This is A without ownership words. The user rejected the equal split (D-112), and ownership words make the partition dynamic for the price of local compare-and-swaps. Keep A.
- **One owner per object, other nodes holding names.** This is what grants already are, and B applies it to address spaces. Extending it to every object is rule 7, which I propose to cut.
- **A smaller set of operations between nodes.** This is A.
- **A replicated log (NrOS).** The log is mutable state written by every replica, which breaks a fixed point. The reason recorded at `kernel.md:63` stands.

---

## 6. Ranked list, experiments, verdict

### Keep, change, cut, most important first

1. **Cut** rule 7's transparent remote call for objects other than memory, and with it proxies, general capability transfer, kernel `thread_move` and carried calls (W1, alternative A). Keep a remote signal and a stamped, bounded send.
2. **Change** the core group to one table per process owned by its home, loaded by the other nodes under a grant (W2, alternative B). Write it before any more work on copies.
3. **Change** the contract and the model to specify concurrency at word level: ordering, a lost compare-and-swap in `memory_take`, a consistent barrier read. Build the state-exploration model D-027 promised (W7).
4. **Change** the contract to specify the rings between kernels: FIFO, capacity, the full-ring rule (W4).
5. **Cut** parking of nodes on another core from version 1 (W6).
6. **Change** the naming of grants to one full-name type in every message (W5).
7. **Change** the proxy accounting if rule 7 survives (W3).
8. **Keep** ownership words, the write gate, membership by evidence, the fence, the barrier and unit roles (W9).
9. **Change later** the single interrupt core per device (W8).

### The three experiments that would most quickly prove the present design wrong

1. **A census, in a few days, against the fixed tables.**
   - *Run.* Trace a real native multithreaded program on Linux, on 4 to 8 cores: Ladybird, and an inference engine. Record mappings, distinct frames of at most *E* pages, the rates of `mmap`, `munmap` and `mprotect`, the threads blocked on waits that would cross cores, and the shared objects.
   - *Compute.* Grants per node against 4,096, proxies per peer against 16, and acknowledgements per second for the core group at a measured message cost.
   - *Reading.* If the grant or proxy numbers come out above the tables by a factor, the per-node copies and rule 7 are wrong as designed.
2. **A model of the shared-word protocols at word granularity, in one to two weeks.**
   - *Scope.* Membership transitions, R5, R6 and the barrier, a role take-over and a hand-over, contested `memory_take`, with ordering under x86-TSO and ARMv8, and two failures.
   - *Tool.* TLA+, or `loom` or `shuttle` over the gate functions, where each word read or write is a step.
   - *Expect.* The torn barrier read and the half-taken run of C3 should appear at once. If many more appear, the shared-word layer needs a redesign, not a patch.
3. **A bare-metal measure of the message cost against a lock, on the reference desktop and on an ARM64 board.**
   - *Measure.* An IPI round trip through the gate, a message through a ring, a TLB shootdown by message to 1, 3, 7 and 13 cores, and the same operations under one lock with the hardware's own shootdown.
   - *Reading.* M5 says these numbers decide the contest (M5:250-256). If the message round trip costs well above 1 µs, candidate 1 loses the core group outright, and every protocol that crosses nodes costs more than it buys.

### Verdict in ten lines

1. The idea is right, and the memory and failure layer (ownership words, gate, fence, barrier) is careful and cheap.
2. The execution is naive in one place: it makes the kernel hide which node holds an object (rule 7).
3. That one choice brings a distributed capability system into the kernel, the thing Barrelfish regretted and seL4 refuses.
4. The faults of reviews 6 and 7 concentrate where that system meets node lifecycles, and they recur by family, not by accident.
5. The parked nodes of D-108 multiply those lifecycles for a gain in energy nobody has measured.
6. The hardest need, a multithreaded process over several nodes, has no protocol, and its planned shape hits a grant ceiling at three nodes.
7. The model cannot see interleavings of words, which is where a real machine will break the shared-word protocols.
8. The decisions to change: rule 7 and D-122's remote capabilities for every kind; D-108's parking; the per-node copies of the core-group hook.
9. Keep D-112 to D-117, D-120 and the evidence-based membership.
10. Cut to memory, signals, stamped messages and failure between nodes; then the remaining protocols are few enough to model completely.

---

## Appendix A. The tests

File: `/tmp/opus-challenge/k/model/tests/challenge_opus.rs`, in a clone of `dodos-kernel` at `2afc901`. It reuses the helpers of `model/tests/nodes.rs` (copied above the tests). Run:

```
cd /tmp/opus-challenge/k
nix develop -c cargo test -p dodos-model --test challenge_opus -- --nocapture
```

Output on 16 November 2026: both pass. The program prints "poll on node 0: Err(WouldWait)" (the notify was never signalled) and "releases in flight from node 1 to node 0: 64".

```rust
// Challenge (Opus, 16 November 2026): the proxies of a pair of nodes are
// one pool for every process of the calling node.
#[test]
fn challenge_sixteen_idle_waits_of_one_process_block_every_request_of_the_node_to_its_peer() {
    let mut m = S::new();
    m.granted(Notify); // node 1: GOT
    m.ok(0, retype(Notify, 0, OBJ + 1));
    assert_eq!(m.on(1, recv(range(GOT + 1, 4))), WAITS);
    let send = Syscall::Send {
        target: core(1),
        message: msg(7, vec![Transfer::Derive(s(OBJ + 1), Rights::ALL.without(Rights::EXEC).bits())]),
    };
    assert_eq!(m.on(0, send), WAITS);
    m.settle();
    let waiters: Vec<ObjId> = (0..PROXIES_PER_PEER as u32).map(|i| m.spawn(1, 200 + i)).collect();
    for &t in &waiters {
        assert_eq!(m.by(1, t, Syscall::Wait(s(GOT), 0)), WAITS);
    }
    m.settle();
    let b = m.spawn(1, 200 + PROXIES_PER_PEER as u32);
    assert_eq!(m.by(1, b, Syscall::Signal(s(GOT + 1))), WAITS);
    assert!(m.sys.pending().is_empty(), "{:?}", m.sys.pending());
    for _ in 0..8 {
        m.settle();
        m.sys.advance(m.sys.now() + 1_000_000_000);
        assert_eq!(m.sys.check(), Ok(()));
    }
    assert_eq!(m.sys.node(1).woken(b), None);
    let p = m.on(0, Syscall::Poll(s(OBJ + 1)));
    assert!(!matches!(p, Ok(Output::Word(1))), "{p:?}");
}

// Challenge (Opus): nothing bounds the messages one node owes another.
#[test]
fn challenge_releases_owed_to_one_node_are_bounded_only_by_its_grants() {
    let mut m = S::new();
    const N: u32 = 64;
    for i in 0..N {
        m.ok(0, retype(Notify, 0, 300 + i));
        assert_eq!(m.on(1, recv(range(500 + i, 1))), WAITS);
        let send = Syscall::Send {
            target: core(1),
            message: msg(7, vec![Transfer::Derive(s(300 + i), Rights::ALL.without(Rights::EXEC).bits())]),
        };
        assert_eq!(m.on(0, send), WAITS);
        m.settle();
    }
    for i in 0..N {
        m.ok(1, Syscall::CapDelete(s(500 + i)));
    }
    let releases = m.sys.pending().iter().filter(|p| matches!(p.body, Body::Release { .. })).count();
    assert_eq!(releases, N as usize);
}
```

## Appendix B. What I did not verify

- K42 beyond Tornado. fos beyond abstracts. Why Barrelfish stopped: the site gives no reason.
- The Armv8 ASID requirement: only the BoF notes, not the Arm Architecture Reference Manual.
- Mitosis beyond its abstract. Quest-V's later fault-tolerance papers: downloaded, not read.
- The 23 problems of pass 11: not classified.
- Review 7 Argon 1.1: not re-run by me, and not verified by a second model in the repository.
- The two shared-word orders of C3: found by reading the contract. The model cannot run them.
- The figure of about 900 lines of `remote.rs` cut by W1: an estimate from the function list (`remote.rs:316-1255`).
