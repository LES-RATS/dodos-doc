# Review of a pull request: lot F2

You review part of one pull request of a Rust repository. You know
nothing else about the project and you are given nothing else: that is
intended. Do not look for documentation outside the repository, do not
read any other directory of this machine, do not search the web for the
project.

The repository is cloned at `/private/tmp/dodos-pr3-final` (branch
`model`, head `6312868`). The pull request is everything between
`origin/main` and `HEAD` (`git -C /private/tmp/dodos-pr3-final diff origin/main...HEAD --stat`):
79 files, about 56,000 lines, two crates, `abi/` and `model/`. Start
with `AGENTS.md`, `model/README.md` and the `.claude/skills/dodos-rust`
and `.claude/skills/rust-1-100` folders of the repository, which say how
its Rust is meant to be written.

**Your lot: read every line of these files, whole, in this order:**

- `model/tests/blocks.rs`
- `model/tests/boot.rs`
- `model/tests/cores.rs`
- `model/tests/debug.rs`
- `model/tests/faults.rs`
- `model/tests/gate_attack.rs`
- `model/tests/gate_classes.rs`
- `model/tests/gate_words.rs`
- `model/tests/generations.rs`
- `model/tests/irq.rs`
- `model/tests/memory.rs`
- `model/tests/sched.rs`
- `model/tests/tasks.rs`
- `model/tests/verify7_deepseek.rs`

Read other files of the repository as far as you need to understand
yours. The clone is shared with other reviewers: change nothing in it.
If you want to run or change code, copy it first
(`cp -R /private/tmp/dodos-pr3-final /private/tmp/dodos-pr3-F2-mistral`) and
work there; `nix` is at `/nix/var/nix/profiles/default/bin` and
`nix develop -c ./verify` runs everything.

## What to report

With a fresh eye, anything a careful reviewer would stop a merge for, or
would want answered first:

- code that does not do what its name, its comment or its neighbour says;
- a case that is not handled, a panic or an overflow reachable from an
  input, an index or an arithmetic step that can go out of range;
- two places that should agree and do not (a constant, a layout, a size,
  an encoding and its decoding, a check and the thing it checks);
- a test that cannot fail, or that tests less than its name says; a rule
  with no test;
- dead code, duplicated logic, a comment that is false;
- anything you could not understand after an honest effort: say what and
  why, since code a newcomer cannot follow is a finding too.

Not findings: formatting, naming taste, wishes for more features.

## Output

One file, written as you go (after each file you finish):
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v1-F2-mistral.md`.
For each finding: a number, a severity (stops the merge / should be
fixed / question), the file and line, the code quoted, what is wrong,
and how you know (if you ran something, the command and its result).
End with the list of the files you read whole, and anything you did not
read. An invented line or a result you did not obtain costs the report
its credit: another reviewer reads the same lot and a third will check
both. English, plain sentences. Work alone, start no subagents. Do not
end your turn while a command of yours still runs; your last message is
the summary of the report.
