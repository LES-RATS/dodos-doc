# Security review of a pull request: lot D

You attack part of one pull request of a Rust repository. You know
nothing else about the project and you are given nothing else: that is
intended. Do not look for documentation outside the repository, do not
read any other directory of this machine, do not search the web for the
project.

The repository is cloned at `/private/tmp/dodos-pr3-final` (branch
`model`, head `6312868`). The pull request is everything between
`origin/main` and `HEAD`: two crates, `abi/` (the binary interface of
an operating system kernel: layouts, encodings, constants) and `model/`
(an executable reference model of that kernel: what every system call
and every event between kernels must do, with a checker of invariants).
The real kernel will be written against this code, so a hole here is a
hole there. Start with `AGENTS.md`, `model/README.md` and the
`.claude/skills/dodos-rust` and `.claude/skills/rust-1-100` folders.

**Your lot: every line of these files, in this order:**

- `model/src/check.rs`
- `model/src/scenarios/checker.rs`
- `model/src/check/cores.rs`
- `model/src/check/debug.rs`
- `model/src/scenarios/explore.rs`
- `model/src/check/machine.rs`
- `model/src/check/memory.rs`
- `model/src/scenarios/mod.rs`
- `model/src/check/node.rs`
- `model/src/check/sched.rs`
- `model/src/check/table.rs`
- `model/src/check/tasks.rs`
- `model/src/check/tests.rs`

Read other files as far as you need. The clone is shared: change nothing
in it. To run or change code, copy it first
(`cp -R /private/tmp/dodos-pr3-final /private/tmp/dodos-pr3-v2-D-deepseek`)
and work there; `nix` is at `/nix/var/nix/profiles/default/bin`;
`nix develop -c cargo test -p dodos-model <filter>` runs tests.

## What to do

Go through your files function by function. For each one that takes
something an attacker controls, ask what the attacker gains. The
attackers: a user program making system calls with any arguments, in any
order, from several threads and cores; a whole hostile kernel of one
group of cores, which can send any message to the others and write
anything into its own memory; a device; a boot image with any values.

Look for, and prove by a test you write and run wherever you can:

- a check that is missing, in the wrong order, or made on a value the
  attacker can change after the check;
- an authority that leaks: a right, a capability, a mapping, an identity
  or a count that survives its revocation, its owner's death or a move;
  something done in the name of another party because its name was taken
  from the message and not from where the message came;
- arithmetic: overflow, underflow, truncation, a shift or an index out
  of range, a size computed two ways, a wrapped counter or generation;
- a panic, an infinite loop or unbounded work reachable from an input;
- a state the checker of invariants accepts and should not, or that no
  invariant covers at all;
- a decoding that accepts what no encoding produces (reserved bits,
  unknown states) and what the code then does with it;
- a resource one party can exhaust for another.

## Output

One file, written as you go (after each file you finish):
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v2-D-deepseek.md`.
For each finding: a number, a severity (exploitable / likely
exploitable / hardening), the attacker, the file and line with the code
quoted, the attack as numbered steps, and the proof (the test you wrote,
the command, the output), or "not run" and why. End with the list of
functions you examined and found sound, and what you did not examine.
An invented line or a result you did not obtain costs the report its
credit: another reviewer attacks the same lot and a third will rerun
your tests. English, plain sentences. Work alone, start no subagents.
Do not end your turn while a command of yours still runs; your last
message is the summary of the report.
