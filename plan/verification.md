# Verification and development workflow

Statuses are defined in the [README](../README.md#status-legend). Sections with no status line had none in the source.

## Harness for development agents

The goal: a development agent can neither cheat on verification, nor widen its task, nor merge alone.

The method is drawn from experience reports of 2026: the rewrite of the Copilot runtime in Rust (GitHub, 16 September), Copilot Cowork (Microsoft, 2 November), Bun from Zig to Rust (8 July), Anthropic's C compiler (5 February), OpenAI's harness engineering (11 February). The harness sources were verified on 13 November 2026.

### In each repository

- A short `AGENTS.md`, 60 to 100 lines, written by hand: the verification command at the top, three zones (always, ask first, never), pointers to `docs/`. An automatically generated file degrades results (ETH Zurich study, arXiv 2602.11988).
- A `CLAUDE.md` of a few lines that points to `AGENTS.md`.
- Skills in `.agents/skills/`, with a link `.claude/skills` to that folder: conventions of the repository's language, QEMU debugging, rebase and review, triage of an oracle failure.
- A versioned `docs/`: architecture, conventions. `AGENTS.md` is the map, not the content. Decision records are not kept per repository (see [Development workflow](#development-workflow)).
- Hard rules never live in prose: they are enforced by CI, linters, `CODEOWNERS` and hooks.

### CI is authoritative

- A hermetic environment pinned by Nix: the same tools locally and in CI, so no "it works on my machine".
- A single command, `verify`, identical locally and in CI.
- Merge queue: every pull request (PR) is retested on the real tip of the branch before it enters.
- Every check proves that it checked: it prints what it inspected, and a test injects a fault into it to verify that it fails.
- Folders protected by `CODEOWNERS`: tests, oracles, workflows, `AGENTS.md`, budgets. There is no waiver label that an agent can set.
- Ratchet budgets, which can only go down without agreement: `unsafe`, size of the kernel and of the images, dependencies and licences (`cargo-deny`), and the escape hatches of Verus (see below).
- Tiers: hosted tests and QEMU with KVM at every PR; differential fuzzing and long matrices at night; real hardware and latency gates on the reference desktop, never triggered by an unreviewed PR. KVM on free runners is not the only gate (**Decided**, 14 November 2026).
- Gates: fast gates at every merge; hardware gates at night; a merge that breaks a night gate is reverted (**Decided**, 14 November 2026; see [gates.md](gates.md)).
- Free infrastructure: GitHub Actions for public repositories (Linux x86 with KVM), Cloudflare R2 for caches and blobs.
- The reference desktop is not a runner; the laptop drives it. A self-hosted runner is used on a private repository only (**Decided**, 14 November 2026).
- An integration repository pins the commit of each repository. A change of `os:core` triggers the tests of the repositories that depend on it.

### Checks per stage

**Proposed.** The CI first proposed was judged insufficient once; this list awaits a review (**Open**). Rule: a check enters CI at the same time as the code it guards, never afterwards.

| Stage | Checks |
|---|---|
| Base, all repositories | Format and lint; reproducible build (two builds, same bytes); tests; supply chain (`cargo-deny`, `cargo-vet`, GitHub actions pinned by SHA, no secret for an unreviewed PR); mutation test at night (a fault injected into the code must make a test fail) |
| `unsafe` code and the Zig/Rust boundary | Miri, sanitizers in hosted mode, Kani |
| Kernel | See [Kernel verification](#kernel-verification); boot under QEMU; fuzzing of system calls |
| ABI | Detection of a breaking change of WIT; corpus of old binaries; WASI suite |
| Performance | Deterministic instruction counts under QEMU at every PR; latency and overhead gates on the reference desktop at night, with a statistical threshold; automatic bisection of a regression |
| Hardware in the loop | Controlled power, captured serial console, image flashed automatically |
| Userland | WPT for the web; reference screenshots for the compositor and the catalogue; accessibility checks |
| Release | Signed and reproducible image, SBOM, update and rollback test |
| CI itself | Every check has its fault-injection test; a flaky test is quarantined with a ticket, never re-run until green |

## Kernel verification

**Decided, 14 November 2026**, unless marked.

The kernel is written from an executable model. The order for the kernel is never reversed: specification, model, oracle, implementation.

- **The executable model** is the artefact of the contract lane: re-read by the two humans, protected by `CODEOWNERS`, written by Claude Fable 5.2 from the settled contract, in a session separate from the implementation (decision of the user, 14 November 2026, against the assistant's advice to keep two families). Two first versions, by Gemini 4 Hydrogen and Mistral Large 4, serve only to find the gaps of the contract and are discarded. Because the model and the kernel now come from the same family, the independent checks are: a review of the model against the contract by another family, seL4 as second oracle, and the re-reading by the two humans. The agent that implements cannot modify the model.
- **At every PR**: a differential test of the implementation against the model, on random call sequences and on interleavings between cores.
- **seL4 as second oracle.** seL4 stays a second oracle, used as a black box by differential fuzzing, on the common subset. The list of accepted differences is a protected file, with a ratchet. Limit: this oracle covers only the semantics on one core and sees only the surface of the ABI. The protocols between nodes, a node of several cores, the IOMMU and the fast path need their own tests.
- **Fast path in Zig**: an equivalence test, the same corpus with and without the fast path, identical traces.
- **Verus** (a proof tool for Rust): the properties to prove are written in the contract of the kernel (invariants of the derivation tree, object life cycle, no dangling reference). The escape hatches (`assume`, `admit`, external bodies) enter the ratchet budgets. Humans re-read the specifications, not the proofs.
- **Three formal models** checked by state exploration: see [kernel.md](../architecture/kernel.md#multi-core-structure).
- **Deterministic simulation** of the messages between nodes (orders and failures replayed from a seed). It kills a node at random at every merge and verifies that the rest survives.
- **Under QEMU**, instructions are counted, not cycles.
- **Lock-free queues**: systematic exploration of interleavings; load tests on hardware.
- **Attack tests**: one attack test per boundary (IOMMU, capabilities, executable pages, compile service), which must fail.
- **Mutation test** on the kernel logic, with a ratchet.
- **Two repositories** (D-087, amending D-030): the kernel, its model, the oracle harness, the formal models and the [kernel interface](../architecture/kernel-interface.md) live in the kernel repository. `os:core` and the other WIT contracts live in the system repository with the runtime (see [thesis.md](../thesis.md#principles); **Decided**, 14 November 2026).
- **Software rendering and a virtio-gpu driver**, to test the compositor under QEMU (see [gpu.md](../architecture/gpu.md#fallback-and-test-paths)).

### Formal proof

**Open.** A formal proof of the whole kernel is out of reach (Zig has no proof tool). Partial lead: Verus on the Rust logic (capabilities, object life cycle). Precedent: Atmosphere, a Rust microkernel of 6,000 lines verified with Verus in less than 2.5 person-years (SOSP 2025), with a global lock. Kani (bounded verification, no annotations, able to handle `unsafe` code) as a complement, in CI: absence of panic, of overflow and of memory error.

Flux (refinement types for Rust) as a proof tool is **Aligned** (retained, to be designed; second delegated study of 14 November 2026, not cross-checked): TickTock (SOSP 2025) verified the isolation of Tock and found seven bugs.

## Authoritative test suites

| Area | Suite |
|---|---|
| Kernel | Differential oracle |
| Web | WPT |
| ABI | WASI suite |
| Compositor | Latency gates |

## Development workflow

**Proposed**, with the points marked Decided.

- A single trunk per repository, short branches, mandatory PR, merge queue, linear history, signed commits. A regression is handled by a revert first, the fix afterwards.
- Three lanes, according to what the change touches:

  | Lane | Touches | Process | Review and merge |
  |---|---|---|---|
  | Contract | Kernel, `os:core`, package format, security model (also: WIT, ABI, kernel interfaces, gates) | A decision record re-read by the two humans, then the executable model and the tests, then the code | Agreement of the two humans. Humans write or validate the tests and merge only in this lane (Decided, 14 November 2026) |
  | Function | Features | Brief, tests, agent, review, merge (the task cycle below) | Tests and code are reviewed by agents of a different model family, with read access to the repository; a human reviews a sample; the merge is automatic once the checks and that review pass (Decided, 14 November 2026) |
  | Maintenance | Dependencies, documentation | Direct PR | Merges alone when the checks pass (Decided, 14 November 2026) |

- Decision records live in the common documentation repository, in [decisions/](../decisions/README.md), not in each repository, because decisions cross repositories (**Decided**, 14 November 2026).
- Between repositories: a contract change is a PR in the repository of the contract, then a move of the pin in the integration repository, which re-runs the tests of the dependants.
- Definition of "done": `verify` green, gates held, documentation up to date, no ratchet budget loosened.
- Rhythm: a nightly image, a weekly image tested on hardware, a version when the gates are held.

### Task cycle

1. A human writes the brief (goal, repository, authorised files, forbidden zones, expected final state). Tests come before the code. In the contract lane a human writes or validates them; in the function lane they are reviewed with the code, in step 4. For the kernel and the ABI, part of the tests stays invisible to the agent.
2. The agent works in a worktree, with no secret, until `verify` passes. Beyond a fixed number of turns or three identical failures, it stops and escalates.
3. Anti-cheat gate: the new test must fail without the fix. No stub, no `todo!()`, no workaround justified by a paragraph.
4. Review by agents with a blank context, of another family of models: two reviewers for the kernel and for the ABI, one for userland. They receive the diff, the brief and the contracts, and read access to the repository (**Decided**, 14 November 2026).
5. Merge queue. In the contract lane a human merges. In the function lane the merge is automatic once the checks and the review pass (**Decided**, 14 November 2026).

### Documented pitfalls to avoid

- "If it compiles, it is right" is false: dozens of semantic regressions passed the compiler at GitHub.
- Agents have deleted a test to hide an omission, and set a waiver label themselves.
- Checks have fallen to zero files inspected without anyone seeing it.
- Too many compilations in parallel freeze the machine: a single build at a time per machine.
- A vague brief ("port X") produces work that avoids the hard parts.

### Cost of agents

**Proposed** (decision of the user; recommendation). Cost is not the constraint. The criterion is the ratio of quality to time. The work is spread over several model providers, with a cheaper model as fallback. The per-task ceiling of the harness stays, as a guard against loops, not as a spending limit.

**Roles** (**Decided**, 14 November 2026):

| Work | Model |
|---|---|
| First versions of the executable model, to find the gaps of the contract | Gemini 4 Hydrogen, thinking level high; a second one by another family (DeepSeek, thinking max) |
| Executable model of the kernel (the reference) | Claude Fable 5.2, effort medium |
| Review of the model against the contract | Four independent reviews, each time: Gemini 4 Hydrogen (high), Gemini 4 Argon (high, a separate quota), Mistral Large 4 (high, with the attacker's angle) and DeepSeek (high). Each reviewer gets its own angle. Claude checks every finding before the contract or the model changes: a reviewer can be wrong too (D-104) |
| Kernel implementation | Claude Fable 5.2, effort medium |
| Web research and minor codebase exploration | DeepSeek, thinking max |
| Everything else delegated | Gemini 4 Hydrogen, thinking level high |

## Reading the code of other kernels

**Decided.** The agents read the code of all open kernels, seL4 included. From seL4 the project takes only the minimalism, the tests and the benches, in other languages and another architecture. One rule: no file-by-file translation and no copy, and the origin of an idea that is taken is cited. Permissive sources verified: Barrelfish (MIT), NVIDIA core (MIT); Asterinas is under MPL-2.0, the seL4 kernel under GPLv2. There is no separation into two agents: the cost was judged disproportionate. A legal opinion is needed before a commercial version.
