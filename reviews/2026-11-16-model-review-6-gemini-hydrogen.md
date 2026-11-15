# Model Review 6 — Protocols Between Nodes (Adversarial)

- **Date:** 2026-11-16
- **Reviewer:** gemini-4-hydrogen (adversarial review — protocols between nodes)
- **Contract:** [`Docs/architecture/kernel-interface.md`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) (`Memory and devices between nodes`, `Cores`, `thread_move`)
- **Model & ABI:** [`dodos-kernel`](/Users/btw/Documents/repos/dodos-kernel) (`model` branch, commit `d4e883b`), tested in a temporary clone `/tmp/review6-gemini-hydrogen` so the source workspace stays untouched

---

## 1. What was read and run

### Read
- Contract: [`Docs/architecture/kernel-interface.md`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) lines 663–674 (`thread_move`), 738–898 (`Memory and devices between nodes`, `The gate over page tables`), and 983–1213 (`Cores`, `The states of a node`, `Detection`, `The fence`, `Reclaim`, `The reclaim barrier`, `Concurrency`, `The calls`, `Roles`).
- ABI & Model source: [`abi/src/machine.rs`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs), [`model/src/system.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs), [`model/src/remote.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs), [`model/src/recovery.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs), [`model/src/roles.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs), [`model/src/moves.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs), [`model/src/ipc.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs), [`model/src/sched.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs), [`model/src/table.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/table.rs), [`model/src/boot.rs`](/Users/btw/Documents/repos/dodos-kernel/model/src/boot.rs).
- Existing tests: [`model/tests/nodes.rs`](/Users/btw/Documents/repos/dodos-kernel/model/tests/nodes.rs), [`model/tests/recovery.rs`](/Users/btw/Documents/repos/dodos-kernel/model/tests/recovery.rs), [`model/tests/cores.rs`](/Users/btw/Documents/repos/dodos-kernel/model/tests/cores.rs), [`model/tests/liveness.rs`](/Users/btw/Documents/repos/dodos-kernel/model/tests/liveness.rs).

### Run
1. Existing baseline test suites (in `/tmp/review6-gemini-hydrogen`):
   ```sh
   timeout 240 nix develop /tmp/review6-gemini-hydrogen -c cargo test --manifest-path /tmp/review6-gemini-hydrogen/Cargo.toml -p dodos-model --test nodes --test recovery --test cores --test liveness
   ```
   Result: `cores` 22 passed, `liveness` 1 passed, `nodes` 37 passed, `recovery` 44 passed (0 failed).
2. Adversarial test suite (`adversarial_nodes.rs`, 18 tests added in `/tmp/review6-gemini-hydrogen/model/tests/adversarial_nodes.rs`):
   ```sh
   timeout 180 nix develop /tmp/review6-gemini-hydrogen -c cargo test --manifest-path /tmp/review6-gemini-hydrogen/Cargo.toml -p dodos-model --test adversarial_nodes -- --nocapture
   ```
   Result: **18 passed, 0 failed** (each test reproduces one of the failures below).

---

## 2. Verdict

The happy-path cross-node protocols and single-crash recovery in `dodos-kernel` are carefully structured around epochs, compare-and-swap gates, and per-dependency reclaim barriers, but adversarial interleavings break **cross-node memory isolation**, **liveness**, and **membership state invariants**. Most critically, stale grant serials after a fresh node restart combined with unchecked `Release`/`Refused` senders allow a stale `Sealed` node to revoke and reclaim physical memory that is still mapped into a third live node, while the recovery sweep falsely kills any `Sealed` node after `SWEEP_NS + STALE_NS`. In addition, multiple two-fault and mid-flight edge cases permanently brick reserve roles, hang `thread_move`/`Transfer` callers, freeze co-hosted physical cores, or strand `Unfenced` nodes and pinned grants forever.

---

## 3. Findings (Most Serious First)

### F1 (Critical) — Stale grant serial reuse + `Sealed` unmapped remote cap + unchecked `Release`/`Refused` breaks Invariant 71 and lets a stale node destroy a third node's live mapped `Frame` grant

- **What is wrong:**
  1. `drop_dead` clears `t.grants[node]` on death (`system.rs:473`), and `table.serials[node]` is never seeded from previous generations across `CoreStart(CORE_START_FRESH)`. When node 0 restarts fresh (`Live(2)`), grant index `0` starts again at `(grant = 0, serial = 0)`.
  2. If node 2 holds an **unmapped** remote capability from node 0 (generation 1, `grant = 0, serial = 0`) and is `Sealed`, node 2's `maps_of[0]` is `false`. By the `sealed` row of the reclaim barrier (`kernel-interface.md:1109`), node 0 transitions `Fenced -> Dead(1)` and restarts `Live(2)` while node 2 still holds `(granter=0, grant=0, serial=0)` in its `UseEntry` and `remotes`.
  3. Node 0 (`Live(2)`) then grants `(grant = 0, serial = 0)` for a `Frame` to node 1, which maps it. Invariant **71** (`system.rs:558-566`: *"only its grantee holds a remote object of a live grant with its serial"*) immediately breaks even before node 2 resumes.
  4. Worse, `released()` (`remote.rs:1077-1089`) and `refused()` (`remote.rs:1093-1118`) only check `e.serial == serial` and **ignore `from` (the sender node) and `entry.generation`**. When node 2 resumes and deletes its stale capability (`CapDelete`), node 2 sends `Body::Release { grant: 0, serial: 0 }` to node 0. Node 0 accepts the stale `Release` from node 2, **frees node 1's live `GrantEntry(0, grantee=1)`**, deletes its anchor, allows node 0 to delete the `Frame`/`Untyped` and `MemoryGive` the physical chunk to node 2, while node 1 still translates the physical frame in hardware (`check()` fails with `node 1: 58: translation under no grant`).
  5. Note also that `System::check` (`system.rs:570-588`) omits the check for documented invariant **72** (`"72: a use entry names a grant of another node"`), so the stale `UseEntry` whose granter died and restarted is not flagged until `(0, 0)` collides.
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:830,839-840,1109`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model: [`model/src/system.rs:473,558-588`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs), [`model/src/remote.rs:1077-1118`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs)
- **How you know (`run`):**
  - `f1a_sealed_unmapped_remote_and_restarted_granter_breaks_invariant_71`: `Err("71: remote object held by another node")`
  - `f1b_stale_release_from_wrong_grantee_destroys_live_mapped_frame_grant`: `Err("node 1: 58: translation under no grant")`
- **What a kernel author would do wrong:** Following the contract ("`Release` names the grant and its serial" at line 839 and ignoring `maps_of == false` sealed holders at line 1109), a kernel would reset or zero-initialize grant tables on fresh boot and omit sender/generation validation on `Release`/`Refused`, allowing a resumed node to unpin and corrupt another node's active DMA/CPU memory grant.
- **Smallest correction proposed:**
  1. Never reset grant serials on `drop_dead` / fresh start (or record `granter_generation` in `GrantEntry`, `UseEntry`, `Body::Release`, and `Body::Refused`), and make `released()`/`refused()` verify `e.grantee == from && e.generation == from_gen && e.serial == serial`.
  2. When a `Sealed` node resumes (before returning to `Live`), or whenever `Release` would be sent, check `UseEntry.generation == table.generation(granter) && granter_is_live`, dropping stale remote caps locally without sending `Release`.
  3. Enforce full Invariant 72 (`UseEntry` must match a live/revoking/pinned grant of the same `granter`, `serial`, and `granter_generation`) inside `System::check`.
- **Fault:** **Both contract and model.** The contract omits `grantee`/generation checks on `Release` and omits clearing stale unmapped `UseEntry` records across `Dead -> Starting` of the granter while letting `Sealed` nodes skip R2 (`kernel-interface.md:839,1109`); the model also fails to preserve `serials` across restarts and forgets Invariant 72 in `System::check`.
- **Missed by existing tests & `liveness.rs`:** `nodes.rs` tests grant reuse only within the same granter generation without sealing a holder or restarting the granter; `liveness.rs` never creates grants or restarts nodes (`core_start`).

---

### F2 (Critical) — Recovery sweep falsely accuses and kills any `Sealed` node as `Evidence::Stale`

- **What is wrong:** The contract guarantees that a `Sealed` node has parked cleanly and does not beat heartbeats: *"A sealed node does not beat, so only the evidence kill, retire and host can accuse it."* (`kernel-interface.md:1036`). However:
  1. `observe_needed` (`recovery.rs:467`) explicitly overrides `!self.table.writes(node)` for `MemberState::Sealed`, opening `Watched::Heartbeat` observations against parked `Sealed` nodes.
  2. `recovery_unit` (`recovery.rs:552-558`) includes `MemberState::Sealed` in `accusable`.
  3. Because a `Sealed` core never runs and never updates `heartbeat` (and if any runnable thread existed on it before sealing, `idle_until == 0`), `evidence()` (`recovery.rs:406-416`) returns `Some(Evidence::Stale)` once `SWEEP_NS + STALE_NS` elapse, killing the `Sealed` node and destroying its saved state (and breaking `core_start` mode resume / kernel upgrade).
- **Where:**
  - Contract (correct rule): [`Docs/architecture/kernel-interface.md:1036`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model (bug): [`model/src/recovery.rs:406-416,467,552-569`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)
- **How you know (`run`):**
  - `f11_sweep_falsely_accuses_and_kills_sealed_node_with_evidence_stale`: after sealing node 1 (`CORE_STOP_SEAL`) and advancing `SWEEP_NS + STALE_NS + 20 * MS`, `node 1` transitions `Sealed -> Fencing -> Fenced -> Dead (Evidence::Stale)`.
- **What a kernel author would do wrong:** Replicating `recovery.rs` would make `core_stop(SEAL)` + `core_start(RESUME)` (e.g., live kernel replacement or power parking) non-deterministic or impossible whenever a node stays sealed across one sweep interval.
- **Smallest correction proposed:** Remove the `MemberState::Sealed` exception in `observe_needed` (`recovery.rs:467`) and reject `Evidence::Stale` / `Evidence::Stuck` / `Evidence::SelfReported` accusations against `MemberState::Sealed` in both `evidence()`/`recovery_unit()` and the write-gate check (`abi::member_transition` / gate).
- **Fault:** **Model bug** directly contradicting [`Docs/architecture/kernel-interface.md:1036`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **Missed by existing tests & `liveness.rs`:** `recovery.rs` only runs `MS` after sealing a node, never `SWEEP_NS + STALE_NS`; `liveness.rs` manually kills `Sealed` nodes via `CoreStop(KILL)` (`liveness.rs:192-201`).

---

### F3 (High) — Destroying a thread waiting on `Transfer` or `Revoke` leaks proxy slots, hangs remote senders forever, and strands grants

- **What is wrong:**
  1. When receiver `R` waiting in `Wait::Node(id)` for `Body::TransferGrant` is destroyed (`CapDelete`), `unlink()` (`ipc.rs:703-706`) calls `cancel_remote(id)` (which ignores `Request::Transfer`) and deletes `Request::Transfer` from `self.requests`. When `Body::TransferGrant` arrives at `place_transfer()` (`remote.rs:858-868`), `self.requests.remove(&id)` returns `None` and **returns early without answering the peer's proxy (`answer`) or sending `Body::Refused`**. The peer's proxy slot (1 of `PROXIES_PER_PEER = 16`) stays allocated forever, the remote sender hangs in `Wait::Node` forever, and any moved capability on the sender stays marooned in `moved_from` / `GrantEntry`. After 16 such deletions, IPC from that peer is permanently wedged.
  2. Similarly, when a thread waiting on `Request::Revoke` is destroyed (`unlink()` at `ipc.rs:703-706`), `revoked_step()` (`remote.rs:1232-1235`) sees `self.requests.remove(&id) == None` and skips `self.free_grant(grant)`, leaving the grant stuck in `GrantState::Revoking`.
- **Where:**
  - Model: [`model/src/ipc.rs:693-707`](/Users/btw/Documents/repos/dodos-kernel/model/src/ipc.rs), [`model/src/remote.rs:858-868,1232-1238`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs)
- **How you know (`run`):**
  - `f2a_destroying_waiting_transfer_receiver_leaks_proxies_and_hangs_sender`: destroying 16 waiting receivers mid-transfer leaks all 16 proxies; a 17th `Send` to a live receiver hangs forever (`sender17 woken=None, recver17 woken=None`).
  - `f2b_destroying_caller_waiting_on_revoke_strands_grant_in_revoking`: passes, showing the grant remains in `Revoking` until another deletion re-triggers `revoke_anchor`.
- **What a kernel author would do wrong:** Following the model's `Wait::Node` cleanup pattern (dropping the request record when the local thread disappears) leaks remote proxies and hangs remote senders whenever a client/server crashes during a capability-carrying IPC.
- **Smallest correction proposed:** Never delete `Request::Transfer` in `unlink()` (set `receiver = None` or handle `Wait::None` in `place_transfer` just like `Request::Move`, so `place_transfer` still sends `Body::Refused`, wakes/answers `answer` proxy, and updates `reply`). Likewise, in `revoked_step`, complete `free_grant(grant)` whenever `done == true` (or keep `Request::Revoke` with `thread: Option<ObjId>`).
- **Fault:** **Model bug** violating [`Docs/architecture/kernel-interface.md:837,848`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **Missed by existing tests & `liveness.rs`:** `nodes.rs` tests `a_transfer_with_no_room_on_the_receiver` on a live receiver, never deleting the receiver mid-transfer; `liveness.rs` uses no transfers or revocations.

---

### F4 (High) — `isolate()` omits `Request::Move` and `Request::Transfer`, permanently hanging threads when the peer dies

- **What is wrong:** `isolate(node)` (`recovery.rs:823-848`) only wakes `Request::Call`, `Request::Carry`, and `Request::Revoke` threads with `Error::Gone`.
  1. `Request::Move` doesn't even store the destination node index (`remote.rs:218-222`), so when the destination node is accused while `Body::Move` is in flight, neither the caller nor the moved source thread is woken (`woken=None`, source stays non-runnable in `Wait::Node` forever), directly violating `kernel-interface.md:671` (*"If the destination node is accused before it answers, both waits end (the caller's with `gone`, Reclaim, R0)"*).
  2. `Request::Transfer` is also skipped by `isolate(sender)`, so if the sender node is accused while `Body::TransferAsk` is in flight, `isolate` wipes the sender's proxy on the receiver (`recovery.rs:851-865`) while leaving the receiving thread stuck in `Wait::Node` forever instead of delivering the message with `FLAG_CAPS_DROPPED` (or `gone`).
- **Where:**
  - Contract (clear for `Move`, silent on `TransferAsk` mid-crash): [`Docs/architecture/kernel-interface.md:671,1088`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model: [`model/src/remote.rs:218-222`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs), [`model/src/recovery.rs:823-848`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)
- **How you know (`run`):**
  - `f3a_dying_destination_during_thread_move_hangs_caller_and_source_forever`: `caller t[0] woken=None`, source thread `s(100)` permanently unrunnable after destination dies and settles.
  - `f3b_dying_sender_during_transfer_ask_hangs_receiver_forever`: `receiver t[1] woken=None` after sender dies during `TransferAsk`.
- **What a kernel author would do wrong:** Treating `Request::Move` and `Request::Transfer` separately from ordinary `Call` requests during R0 leaves processes deadlocked in *waiting for another node* whenever a peer crashes mid-migration or mid-transfer.
- **Smallest correction proposed:** Add `peer: u16` to `Request::Move` and `Request::Transfer`. In `isolate(node)`, end both `caller` (`Err(Error::Gone)`) and `source` (`Wait::None`) of `Request::Move { peer == node }`; for `Request::Transfer { peer == node }`, complete the delivery locally with `FLAG_CAPS_DROPPED` (no grants) and answer/clear any local `reply`.
- **Fault:** **Model bug** for `Move` (violates `kernel-interface.md:671`); **Contract omission + Model bug** for `TransferAsk` (contract R0 at line 1088 should specify delivering with `caps_dropped` when the sender node is accused during `TransferAsk`).
- **Missed by existing tests & `liveness.rs`:** `cores.rs` tests `thread_move` only between live nodes; `nodes.rs` and `liveness.rs` never crash a peer while `Body::Move` or `Body::TransferAsk` is in flight.

---

### F5 (High) — Reserve role and its taken chunks are permanently unclaimable (`Err(Busy)`) after the holder dies

- **What is wrong:** Rule 4 of taking (`kernel-interface.md:770`) keeps `owner = Reserve(j)` (`0xFFF0 + j`) in the chunk's ownership word and writes only the taker's `generation` into bits 32–63 (with **no node index**). When the reserve role holder dies (`Fenced -> Dead`), `barrier_unit` (`recovery.rs:942-944`) vacates the reserve role word (`RoleWord::vacant`), erasing which node held reserve `j`! Because the chunk's ownership word still says `(OwnState::Taken, Owner::Reserve(j), generation = old_g)`:
  1. `reserve_taken()` (`roles.rs:44-47`) conservatively treats `(Taken, Reserve(_))` as **always taken (`true`)**;
  2. Even in the contract, `R6` (`kernel-interface.md:1100`: *"a reserve's code with X's generation in bits 32-63"*) is ambiguous because multiple nodes can have the same generation `g`!
  Consequently, once any reserve holder takes a chunk of reserve `j` and dies, **no live node (not even the restarted node) can ever `RoleClaim` reserve role `j` again**, and no node can ever `MemoryTake` that chunk again — permanently bricking the replica's supervisor/memory-service reserve.
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:770,1100,1206,1211`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model: [`model/src/roles.rs:38-51`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs), [`model/src/recovery.rs:937-946`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)
- **How you know (`run`):**
  - `f4_reserve_role_and_chunk_permanently_bricked_after_holder_dies_with_taken_chunk`: node 1 claims reserve 0, takes a chunk of reserve 0, is killed to `Dead` (reserve 0 becomes `Vacant`), restarts fresh, and both `node 0` and restarted `node 1` receive `Err(Error::Busy)` on `RoleClaim`.
- **What a kernel author would do wrong:** Following rule 4 (`kernel-interface.md:770`) literally (writing only `Reserve(j)` + `generation`) leaves R6 and `role_claim` unable to distinguish a dead holder's reserve chunk from a live holder's, or worse, allows a careless R6 implementation to clear a live node's reserve chunk if its generation happens to match the dead node's generation!
- **Smallest correction proposed:** Record the taking node `X` in the reserve chunk word or in the fixed/living reserve metadata (`(holder, holder_gen)` of the last taker of reserve `j`), or clear reserve `j`'s taken chunks to `Free(Reserve(j), 0)` during step R6 while `role_word.holder() == X` (before `barrier_unit` vacates the role), so once `X` is `Dead` the reserve chunks are `Free` and `role_claim` succeeds.
- **Fault:** **Both contract and model.** The contract's bit layout (`kernel-interface.md:761-770`) omits the taking node from reserve chunks and relies on an ambiguous generation-only match in R6 (`kernel-interface.md:1100`); the model doesn't clear reserve chunks in R6 and hardcodes `(Taken, Reserve(_)) => true` in `roles.rs:46`.
- **Missed by existing tests & `liveness.rs`:** `recovery.rs` (`a_plain_role_of_a_fenced_holder_can_be_claimed_a_reserve_role_only_once_it_is_dead`) tests `RoleClaim` on a reserve role **without ever calling `MemoryTake` on a chunk of that reserve**.

---

### F6 (High) — Planned unit role hand-over skips `R1` (causing barrier deadlock vs `abi::barrier`), and `CORE_STOP_SEAL` on a hand-over target deadlocks `Sealing` forever

- **What is wrong:**
  1. **F6a — Missing R1 in step 5 of planned hand-over:** Contract section `R1 at every change of holder` (`kernel-interface.md:1205`) mandates that a node taking a unit role at step 5 of a planned hand-over runs `R1` for every `Fencing | Fenced | Unfenced | Dead` node and resets `acked[Z] = 0` before writing `Held`. In `model/src/roles.rs:332-337`, step 5 only calls `map_unit` and writes `RoleWord::held(me, epoch)` **without running `block_devices` or clearing `acked`**. If node 0 attached an IOMMU device via node 1, node 1 hands unit role 0 to node 2 (`Handing(1 -> 2)`), and node 0 is killed + node 1 is sealed before node 1 runs R1 for node 0, node 2 takes role 0 via step 5 leaving node 0's context entry `(0, 1)` intact on unit 0. Node 0 then **deadlocks permanently in `MemberState::Fenced`** because `recovery.rs:927-931` checks `!unit.entries.contains(0)`, even while `dodos_abi::barrier(...)` already returns `true` (which in real hardware/ABI would mark node 0 `Dead` while its DMA context entry is still live, breaking **Invariant 81**).
  2. **F6b — `Handing(X -> Y)` + `CORE_STOP_SEAL(Y)` deadlock:** If unit role `u` is `Handing(X -> Y)` and target `Y` enters `Sealing` (`CORE_STOP_SEAL`), `Y`'s `roles_unit()` stops running (`state != Live`, `roles.rs:321`), `Y`'s `sealing_unit()` refuses to finish because `w.target() == Y` (`roles.rs:478`, matching `kernel-interface.md:1027`), and every other node's `roles_unit()` skips `Sealing` (`roles.rs:348`). Thus `Y` stays `Sealing` and role `u` stays `Handing` forever (until a sweep falsifies `Y` or someone kills `Y`).
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:1027,1203,1205`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model: [`model/src/roles.rs:321,332-337,348,476-479`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs), [`model/src/recovery.rs:927-931`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)
- **How you know (`run`):**
  - `f5a_unit_handover_skips_r1_causing_barrier_deadlock_while_abi_allows_dead`: `node0=Fenced, node1=Sealed, node2=Live` at `2ms`, then `node0=Fenced` (permanently wedged) at `252ms` (with node 1 eventually falsely killed by F2).
  - `f5b_sealing_target_of_unit_handover_deadlocks_forever`: after `300ms`, `node2=Sealing, role0=RoleWord(Handing(1 -> 2))` with no further progress.
- **What a kernel author would do wrong:** Implementing step 5 without R1 lets a dead node's active DMA context survive `Fenced -> Dead`, violating Invariant 81; following the `Sealing` guard in `kernel-interface.md:1027` without letting `Sealing` either complete step 5 to its own successor or refuse `CORE_STOP_SEAL` while targeted deadlocks the cluster's IOMMU/IOAPIC role.
- **Smallest correction proposed:**
  - For F6a: In step 5 (`roles.rs:332-337`), before writing `Held`, reset `acked[Z] = 0` for non-live nodes and run `block_devices(Z)` / `rebuild(role)` for all `Fencing | Fenced | Unfenced | Dead` nodes.
  - For F6b: Either let `Sealing` target `Y` in step 5 take the role and immediately re-hand it to its `successor`, or have `core_stop(SEAL)` reject `Busy` while `Y` is `target` of a `Handing` role (and let the `Sealing` holder or successor take over if `Y` is already `Sealing`).
- **Fault:** F6a is a **Model bug** (violates `kernel-interface.md:1205`); F6b is **Both contract and model** (`kernel-interface.md:1027` explicitly creates the cyclic wait between `Y.Sealing` and `u.Handing(_ -> Y)`).
- **Missed by existing tests & `liveness.rs`:** `liveness.rs` only runs `hand` on an idle unit with no `IoSpaceAttach` device from a concurrently killed node, and never calls `CORE_STOP_SEAL` on the target of `Handing`.

---

### F7 (High) — `core_stop` last-live-node check ignores co-hosted live nodes, and `ParkSelf` halts shared physical cores

- **What is wrong:**
  1. `core_stop` (`kernel-interface.md:1171`, `recovery.rs:196-198`) checks only `!self.live_nodes().any(|n| n != node)` before allowing `KILL`, `RETIRE`, or `SEAL`. It ignores `placed[n]`, i.e., whether the remaining live node(s) share the **same physical core** as `node`.
  2. When 2 nodes share physical core 0 (placed via `core_place`), stopping node 1 with `KILL` leaves node 0 (`Live`) on core 0, so the check passes — and the subsequent NMI/INIT or `ParkSelf` stops core 0 (`runs = [false, false]`), **halting every running node on the machine** (and with 3 nodes where node 2 is `Sealed`, `runs = [false, false, false]`, zero running nodes while `node 0` stays `Live`, violating the spirit of **Invariant 86**).
  3. Similarly, `HwAction::ParkSelf { node }` (`system.rs:404-407`) unconditionally sets `self.cores[core] = CoreState::Parked`. If node 1 is co-hosted with live node 0 on core 0 and node 2 calls `CoreStop(1, SEAL)`, node 1 seals itself and emits `ParkSelf { node: 1 }`, which **parks core 0 while `Live` node 0 is placed there**, freezing node 0 (`runs(0) == false`).
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:1171,1173`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model: [`model/src/recovery.rs:196-198`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs), [`model/src/system.rs:404-407`](/Users/btw/Documents/repos/dodos-kernel/model/src/system.rs)
- **How you know (`run`):**
  - `f6a_core_stop_kill_cohosted_node_freezes_or_kills_all_live_nodes`: Part 1 (`core0=Parked, runs(0)=false, runs(1)=false`); Part 2 with sealed node 2 (`runs=[false, false, false]`).
  - `f6b_core_stop_seal_cohosted_node_parks_shared_core_halting_live_peer`: `core0=Parked, node0=Live, runs(0)=false, node1=Sealed`.
- **What a kernel author would do wrong:** Following the contract check `!live_nodes().any(|n| n != node)` and parking the current physical core on `SEAL`, a kernel will shoot itself or a co-hosted live peer in the head when two nodes have been consolidated onto one physical core (`core_place`).
- **Smallest correction proposed:**
  1. For `KILL`/`RETIRE` in `core_stop`, require at least one live node placed on a **different** physical core (`placed[n] != placed[node]`), or make `KILL`/`RETIRE` target only the node/virtual slot without stopping a physical core that still hosts a `Live` node.
  2. For `ParkSelf` on a shared core (`SEAL` or self-stop), switch the core to another `Live`/`Starting` node hosted on that core instead of parking the physical core (or reject co-hosting `SEAL` unless handled by core-scheduler handoff).
- **Fault:** **Both contract and model.** The contract checks only node liveness (`kernel-interface.md:1171`) and specifies `"parks its core"` (`line 1173`) without accounting for multiple nodes placed on one physical core via `core_place`.
- **Missed by existing tests & `liveness.rs`:** `liveness.rs` and `recovery.rs` never call `core_place` to place two `Live` nodes on one physical core before calling `core_stop`.

---

### F8 (Medium-High) — `fenced()` on co-hosted nodes violates Invariant 85 & unit-role rules; `abi::member_transition` omits `(Starting | Live, Sealed)`

- **What is wrong:**
  1. `fenced()` (`recovery.rs:719-742`, matching `kernel-interface.md:1080`) iterates over co-hosted nodes `z != node` on the stopped core, skipping only `Dead | Fenced` (and `Sealed` with `save_seal == true`). If a co-hosted node `z` is already `Fencing` (e.g., `Evidence::Retire`, or with its own driver) or `Unfenced`, `fenced()` executes two writes: `MemberState::Fencing(Evidence::Host)` followed by `MemberState::Fenced(Evidence::Host)`. Both `Fencing -> Fencing(different evidence)` and `Unfenced -> Fencing` are **illegal transitions** off the table (`abi/src/machine.rs:530-540`), breaking **Invariant 85** (`"85: a member word written off the table of transitions"`). Notice `System::run` never catches this because `member_writes` is `Ephemeral` and cleared between sub-steps inside `run()`.
  2. In [`model/src/recovery.rs:729-731`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs), when `z` is `Starting | Live` and `save_seal == true`, `fenced()` transitions `z -> Sealed` **without checking whether `z` holds or is target of a unit role** (`kernel-interface.md:1080` requires accusing `z` with `Host` instead, otherwise breaking Invariant 83).
  3. In [`abi/src/machine.rs:514-544`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs), `member_transition()` **completely omits** the `(Starting | Live, Sealed)` row from `kernel-interface.md:1028`, so a gate built on `dodos_abi::member_transition` will reject valid host-core sealing!
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:1028,1080`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - ABI & Model: [`abi/src/machine.rs:514-544`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs), [`model/src/recovery.rs:719-742`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs), [`model/src/table.rs:212`](/Users/btw/Documents/repos/dodos-kernel/model/src/table.rs)
- **How you know (`run` & `read`):**
  - `f7_fenced_on_core_with_cohosted_fencing_node_breaks_invariant_85` (`run`): `sys.recover(1); sys.check()` returns `Some("85: a member word written off the table of transitions")`.
  - `abi/src/machine.rs:514-544` (`read`): no `(Starting | Live, Sealed)` match arm exists in `member_transition`.
  - `recovery.rs:729-731` (`read`): no unit-role check precedes `MemberState::Sealed`.
- **What a kernel author would do wrong:** Copying `fenced()` would overwrite active `Retire` / `Unfenced` evidence with `Host` (or seal a unit role holder), while using `dodos_abi::member_transition` in the gate would break sealing co-hosted parked nodes.
- **Smallest correction proposed:**
  1. In `fenced()` and `kernel-interface.md:1080`, transition `Fencing | Unfenced -> Fenced` keeping `z`'s existing `evidence` and `driver` (`Transition::Fence` / `LateFence`), never overwriting with `Host`.
  2. Check that no unit role names `z` as holder or target before sealing `z` in `recovery.rs:729`.
  3. Add `(Starting | Live, Sealed) if same && cleared` to `abi::member_transition`.
- **Fault:** **Both contract, ABI, and model.**
- **Missed by existing tests & `liveness.rs`:** No test calls `fenced()` with a co-hosted `Fencing`/`Unfenced` peer or tests `abi::member_transition` against the `(Starting | Live, Sealed)` rule.

---

### F9 (Medium) — An `Unfenced` node whose driver dies is stranded forever

- **What is wrong:** `recovery.rs:580` only lets another live node become driver (`Redrive`) when `member.state() == MemberState::Fencing`: if node `X` timed out into `MemberState::Unfenced` (e.g., because `X`'s core was in VMX root operation) and then `X`'s driver `D` dies (`Dead`), no live node ever takes over `self.fences[X]`. Worse, `abi/src/machine.rs:530` and `kernel-interface.md:1030` only define `Redrive` for `(Fencing, Fencing)`, not `(Unfenced, Unfenced)` or `(Unfenced, Fencing)`. Even after `X` leaves VMX root operation (`set_vmx(false)`), `X` can never be re-fenced or reclaimed to `Fenced -> Dead`, leaking its floor, memory, and pinned grants until machine reboot even when the core *could* now be stopped cleanly.
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:1030,1033,1081`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - ABI & Model: [`abi/src/machine.rs:530-540`](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs), [`model/src/recovery.rs:580-593,694-698`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)
- **How you know (`run`):**
  - `f8_unfenced_node_whose_driver_dies_is_stranded_forever`: node 2 (`vmx=true`) goes `Fencing -> Unfenced` (driver 0); node 1 kills driver 0 to `Dead`; VMX clears on node 2; after `500 * MS`, `node2` remains `Unfenced` (`Member(4294967367)`) forever.
- **What a kernel author would do wrong:** Following the state table row `Unfenced -> Fenced` ("any live node", line 1033) without a `Redrive` row for `Unfenced` leaves every other live node forbidden by `G10` (`kernel-interface.md:886`: *"INIT, SIPI and NMI go only to a core whose node the caller drives the fence of"*) from ever probing `X` again once `D` dies!
- **Smallest correction proposed:** Allow `(Unfenced, Unfenced)` `Redrive` in `kernel-interface.md:1030` and `abi::member_transition` when `D` is no longer `Starting | Live | Sealing`, and extend `recovery.rs:580` to `matches!(member.state(), MemberState::Fencing | MemberState::Unfenced)`.
- **Fault:** **Both contract, ABI, and model** (contract `G10` requires driving the fence to send NMI/INIT/SIPI, yet omits driver takeover for `Unfenced`).
- **Missed by existing tests & `liveness.rs`:** `liveness.rs` never enables `vmx` (so never enters `Unfenced`); `recovery.rs` (`a_fence_whose_driver_dies_is_driven_again_by_another_node`) kills the driver while `X` is `Fencing`, never `Unfenced`.

---

### F10 (Medium) — Pinned grants (`R3`) are stranded forever if the dead grantee restarts fresh before `unpin()` runs

- **What is wrong:** When node 1 maps a `Frame` granted by node 0 and node 1 dies, node 0's `R3` sets the `GrantEntry` to `GrantState::Pinned`. `recovery_unit` (`recovery.rs:888-890`) only calls `self.unpin(node)` when `member(node).state() == MemberState::Dead`. If node 0 (or any supervisor on node 2) calls `CoreStart(1, CORE_START_FRESH)` right after node 1 reaches `Dead(1)` — before node 0's `unpin(1)` step runs — node 1 becomes `Live(2)` (`generation == 2`). From then on, `recovery.rs:888-890` never calls `unpin(1)`, leaving the `GrantEntry(grantee=1, generation=1, state=Pinned)` permanently `Pinned` and causing `CapRevoke` on node 0 to return `Err(Error::Again)` forever, leaking the underlying physical frame/untyped.
- **Where:**
  - Contract: [`Docs/architecture/kernel-interface.md:838,1094`](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
  - Model: [`model/src/recovery.rs:888-890,952-969`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)
- **How you know (`run`):**
  - `f9_pinned_grant_stranded_forever_if_grantee_restarts_fresh_before_unpin`: after `Dead(1)` -> `CoreStart(1, FRESH)` -> `Live(2)` and advancing `50 * MS`, `CapRevoke` on node 0 still returns `Err(Error::Again)` forever.
- **What a kernel author would do wrong:** Triggering unpin only while observing `member(X).state() == Dead` races with `core_start(FRESH)`, stranding physical memory across fast supervisor restarts.
- **Smallest correction proposed:** In `unpin` / `recovery_unit` (and `revoke_anchor` at `remote.rs:1185`), unpin any `Pinned` grant whose `entry.generation != self.table.generation(entry.grantee)` **or** `self.table.member(entry.grantee).state() == MemberState::Dead` (because `entry.generation` only turns `Dead` once R1 and the reclaim barrier have permanently cleared its devices and translations).
- **Fault:** **Both contract and model** (`kernel-interface.md:838,1094` says *"until X is dead"*, overlooking that `X` only stays `Dead` briefly before `core_start(FRESH)` moves `X` to `Starting(g + 1)`).
- **Missed by existing tests & `liveness.rs`:** `recovery.rs` (`the_frames_granted_to_a_fenced_node_stay_pinned_until_it_is_dead`) checks unpinning while node 1 stays `Dead` and never restarts it immediately.

---

### F11 (Medium) — `thread_move` breaks Invariant 42 (`admitted` sum) and steals an unrelated thread's context when `sched` is deleted or rebound mid-move

- **What is wrong:** Three concurrency bugs in `thread_move` when local syscalls mutate source or destination `sched` while `Body::Move` / `Body::Moved` is in flight:
  1. **F11a — Double-subtract of `admitted` on source `sched`:** Deleting a source `sched` with >32 children returns `Err(Again)` after `sched_dying()` has already subtracted its bandwidth from `self.admitted` (leaving `sched` present in `self.scheds` while dying). When `Body::Moved(Ok)` arrives (`moves.rs:231-233`), `moved()` sees `self.scheds.contains_key(&context)` and subtracts `self.scheds[&context].bandwidth()` **a second time**, corrupting `self.admitted` and breaking Invariant **42** (`Err("node 0: 42: admitted sum")`).
  2. **F11b — Destination `sched` re-admitted while dying:** `place_move` (`moves.rs:169-178`) checks `held.configured || held.home.is_some()` on the destination `sched` without checking `!self.dying(context)`. If the destination `sched` is mid-`CapDelete` (returning `Again` across steps), `place_move` re-configures it and adds its bandwidth to `self.admitted`. Finishing `CapDelete` then deletes the `sched` without subtracting the newly added bandwidth (`sched_dying` already ran on the first deletion step), breaking Invariant **42** (`Err("node 1: 42: admitted sum")`).
  3. **F11c — `SchedUnbind` + `SchedBind` steals in-flight `sched`:** `sched_unbind`, `sched_bind`, and `sched_configure` (`sched.rs:549-630`) do not reject a `sched` whose bound `home` thread is waiting in `Wait::Node(Move)`. While `Body::Move` is in flight, the caller can `SchedUnbind` source `sched`, `SchedBind` it to another thread `T2`, and `ThreadResume(T2)`. When `Body::Moved(Ok)` arrives (`moves.rs:235-241`), `moved()` clears `configured = false, budget = 0, period = 0` on that `sched` **while `T2` is actively bound to and runnable on it**!
- **Where:**
  - Model: [`model/src/moves.rs:169-178,231-242`](/Users/btw/Documents/repos/dodos-kernel/model/src/moves.rs), [`model/src/sched.rs:549-630`](/Users/btw/Documents/repos/dodos-kernel/model/src/sched.rs)
- **How you know (`run`):**
  - `f10a_destroying_source_sched_during_move_breaks_invariant_42_admitted`: `Err("node 0: 42: admitted sum")`
  - `f10b_dying_destination_sched_readmitted_by_move_breaks_invariant_42`: `Err("node 1: 42: admitted sum")`
  - `f10c_sched_unbind_and_rebind_during_in_flight_move_steals_unrelated_threads_context`: `sched 102` becomes unconfigured (`state: 4`, `budget=0`) underneath running thread `105`.
- **What a kernel author would do wrong:** Implementing `thread_move`'s *"nothing changes on the source from sending its state to the answer"* (`kernel-interface.md:671`) without blocking `sched_unbind` / `sched_configure` / `cap_delete` on the source `sched` (and checking `dying` on destination `sched`) corrupts CPU admission accounting and silently stalls unrelated threads.
- **Smallest correction proposed:** Reject `sched_configure`, `sched_bind`, `sched_unbind` (`Busy`) while `sched.home` is waiting in `Wait::Node(Move)` (and skip subtracting bandwidth in `moved()` if `!self.dying(context)` is false); in `place_move`, reject `Gone` (or `Busy`) if `self.dying(context)`.
- **Fault:** **Model bug** (violates `kernel-interface.md:671` and Invariant 42).
- **Missed by existing tests & `liveness.rs`:** `cores.rs` tests `thread_cancel` and `CapDelete` of the *thread* during `thread_move`, never `CapDelete`/`SchedUnbind`/`SchedBind` on the source or destination `sched`.

---

## 4. Scenarios existing tests and `liveness.rs` never reach

Specifically, [`model/tests/liveness.rs`](/Users/btw/Documents/repos/dodos-kernel/model/tests/liveness.rs) (`SCENARIOS` at lines 105–130, `machine()` at lines 29–38, `step()` at lines 42–48, `every_crash_at_every_step_of_a_recovery_is_recovered_from` at lines 179–218) and the existing unit tests in `nodes.rs`, `recovery.rs`, and `cores.rs` never reach:

1. **Co-hosted live nodes (`core_place`)** — `liveness.rs` and `recovery.rs` always map 1 node per distinct physical core, never exercising `core_stop` (`F7`) or `fenced()` (`F8`) with shared cores.
2. **Long-duration `Sealed` nodes across `SWEEP_NS + STALE_NS`** — `liveness.rs` manually calls `CoreStop(KILL)` on `Sealed` nodes (`liveness.rs:192-201`); `recovery.rs` only runs `MS` after sealing, missing `F2`.
3. **Reserves with taken chunks across holder death** — `recovery.rs` claims a reserve after death without `MemoryTake` (`F5`), and `liveness.rs` never uses reserve roles.
4. **Simultaneous node death + planned unit hand-over (`F6a`), or `CORE_STOP_SEAL` on a `Handing` target (`F6b`)** — `liveness.rs` only stops a single node in `begin()` and crashes a second node via `hang(_, true)` without an attached IOMMU device on a third node or `Seal` targeting the recipient of `Handing`.
5. **Unfenced nodes (`vmx == true` / `hang(_, false)`) whose driver dies** — `liveness.rs:191` only injects `hang(crashed, true)` (`NMI` handler succeeds), never leaving a node `Unfenced` while its driver dies (`F9`).
6. **Fresh restarts (`core_start(FRESH)`) racing with `unpin()` (`F10`) or with a `Sealed` unmapped remote cap (`F1a`/`F1b`)** — `liveness.rs` never grants memory/capabilities across nodes and never calls `core_start`.
7. **Out-of-order / mid-flight deletion against `Transfer`, `Revoke`, and `Move`** — `nodes.rs` and `cores.rs` never destroy a `Transfer` receiver (`F3`), never kill a `Move` destination (`F4`) or `TransferAsk` sender (`F4`), and never mutate/delete `sched` objects while `Body::Move` is in flight (`F11`).

---

## 5. What was checked and found right

- **`Body::Returned` ABA guard** ([`model/src/remote.rs:1123-1137`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs)): checks `(from, grant, serial)` against `remotes`, so a delayed `Returned` packet cannot destroy a newly granted remote capability at the same grant slot.
- **Atomic `GrantState::Revoking` before `Body::Revoke`** ([`model/src/remote.rs:1188`](/Users/btw/Documents/repos/dodos-kernel/model/src/remote.rs)): invalidates remote capabilities at the moment revocation begins, before the holder's step completes (`a_revoked_grant_is_refused_before_the_holder_knows` holds).
- **Unit role request epoch retry** ([`model/src/roles.rs:253-261,281-297,381-398`](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs)): stale-epoch `UnitRequest`s are cleanly refused (`done: false`) and re-dispatched to whichever node currently holds the role, even across multiple hand-overs and deaths.
- **`Body::Cancel` wait-number check**: proxy wait numbers prevent a delayed `Cancel` from cancelling a newer request that later reused the same proxy slot.
- **R3 frame pinning against `Unfenced` IOMMU writes** ([`model/src/recovery.rs:791-801`](/Users/btw/Documents/repos/dodos-kernel/model/src/recovery.rs)): keeping `GrantState::Pinned` blocks premature reclamation of granted frames while an unfenced grantee's DMA could still be active (until the F10 fast-restart gap above).

---

## 6. What was not checked due to time

- Non-x86 fence hardware mechanisms (ARM64 SDEI/`CPU_OFF` and RISC-V `sbi_hart_stop`/`fence_hart`) beyond the abstract `HwAction::Signal` state machine in `system.rs`.
- Multi-core-per-node `G12` gate locking (`model` models 1 virtual core per node; `core_place` only tests core placement, not parallel SMP execution within one node).
- 64+ node `SchedSetCores` multi-window interactions during node restarts and `thread_move`.
- `abi/` Kani proof harnesses (not run separately).
- `core_idle` / `core_perf` `Request::Carry` interactions with simultaneous `core_place` or `core_stop(SEAL)`.
