# Verification of attack reports on the reference model

DodOS is a new operating system in design. Its kernel contract is
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
(branch `main`), with its decisions in `decisions/README.md` (D-100 to
D-140; D-117 and D-120 are the gate that confines a faulty kernel to its
own memory). The executable model of the contract is pull request 3 of
`dodos-kernel`, head `6312868`, cloned read-only at
`/private/tmp/dodos-pr3-final`. Reviewers who were given **no context**
(not the contract, not the decisions) attacked part of that code and
wrote:

- `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v2-D-opus.md`

Each report names a work copy of its author under `/private/tmp/` that
holds the tests it wrote: read them there, but run nothing in a copy
that is not yours. Make your own:
`cp -R /private/tmp/dodos-pr3-final /private/tmp/dodos-pr3-ver2-D-opus`.
Read `AGENTS.md` and the skills `.claude/skills/dodos-rust` and
`.claude/skills/rust-1-100` there first. `nix` is at
`/nix/var/nix/profiles/default/bin`; `nix develop -c cargo test -p dodos-model <filter>`
runs tests; use absolute paths; wait for long commands inside one tool
call.

You have the context the authors lacked, and you owe them nothing. For
every finding:

1. Open the lines it cites, and the author's test.
2. Reproduce it in your copy: write the test again yourself (do not copy
   it blindly: check that it reaches the state by calls or messages the
   attacker can really make, not by writing the model's fields by hand)
   and run it. "Not run" is a verdict you may give only with the reason.
3. Read what the contract says of that case and quote it. Verdict:
   **real, the model's fault** (the contract forbids it and the model
   allows it); **real, the contract's fault** (the model does what the
   contract says, and a guarantee of the contract breaks: name the
   guarantee); **intended** (a decision or a sentence makes it
   deliberate and no guarantee breaks: quote it); **refuted**. Give your
   own severity. One known disagreement to settle with care: a message
   whose header names another node than the ring it came on. The
   contract's check (the paragraph "One check on every message
   received") is stated on the sender the message carries, and the
   contract also says kernels trust each other's stamping of marks; say
   whether acting in another node's name stays inside what the gate
   promises (a faulty kernel reaches only its own memory and its own
   devices), with the scenario.
4. For each real finding, the correction: for the model, the function,
   the change and the test that fails without it; for the contract, the
   exact sentence and where, the smallest that closes it, what it costs
   and when, and whether it needs new state.

## Output

One file, written as you go:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/ver2-D-opus.md`.
End it with one table: finding, verdict, severity, correction in one
line. You change nothing in any repository except your copy, and commit
nothing. English, plain sentences. Work alone, start no subagents. Do
not end your turn while a command of yours still runs; your last message
is the summary of the report. A result you did not obtain costs the
report its credit.
