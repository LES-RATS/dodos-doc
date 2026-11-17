# Verification of two reviews of lot B

DodOS is a new operating system in design. Its kernel contract is
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
(branch `main`), with its decisions in `decisions/README.md` (D-128 to
D-140 are the recent ones). The executable model of the contract is pull
request 3 of `dodos-kernel`, head `6312868`, cloned read-only at
`/private/tmp/dodos-pr3-final`. Two reviewers who were given **no
context** (not the contract, not the decisions) each read the same lot
of that pull request:

- `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v1-B-opus.md`
- `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v1-B-deepseek.md`

You have the context they lacked, and you owe them nothing. Make your
own copy to run code:
`cp -R /private/tmp/dodos-pr3-final /private/tmp/dodos-pr3-ver-B`.
Read `AGENTS.md` and the skills `.claude/skills/dodos-rust` and
`.claude/skills/rust-1-100` there first. `nix` is at
`/nix/var/nix/profiles/default/bin`; `nix develop -c ./verify` runs
everything; use absolute paths; wait for long commands inside one tool
call; `git checkout -- .` between experiments.

For every finding of both reports:

1. Open the lines it cites. If the two reports have the same finding,
   judge it once and say so.
2. Reproduce it: write the test or the mutation and run it. A finding
   that was only read, not run, by its author is run by you. "Not run"
   is a verdict you may give only with the reason.
3. Verdict: **real** (the model is wrong against the contract, or a test
   or a check does less than it says); **the contract's fault** (the
   model does what the contract says and the contract is wrong or
   silent: quote the contract); **intended** (a decision or a sentence
   of the contract or of the README makes it deliberate: quote it);
   **refuted** (show what refutes it); and the severity you give.
4. For each real finding, the correction: the function, the change, and
   the test that fails without it.

Then one paragraph on what both reviewers missed in the lot, if your
reproductions showed you something.

## Output

One file, written as you go:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/ver-B.md`.
End it with one table: finding, verdict, severity, correction in one
line. You change nothing in any repository except your copy, and commit
nothing. English, plain sentences. Work alone, start no subagents. Do
not end your turn while a command of yours still runs; your last message
is the summary of the report. A result you did not obtain costs the
report its credit.
