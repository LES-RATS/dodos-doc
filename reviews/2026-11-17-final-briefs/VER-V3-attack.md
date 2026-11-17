# Verification of a review of the kernel contract

DodOS is a new operating system in design. Its kernel contract is
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
(branch `main`, head `6e7d8c0`); read it whole, then
`architecture/kernel.md` and the decisions D-100 to D-140 in
`decisions/README.md`. A reviewer who was given **only the contract**
(no decisions, no other document) wrote:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v3-hydrogen.md`

You have the context it lacked, and you owe it nothing. For every
finding:

1. Open every quote at its line and say whether it is exact.
2. Replay the scenario step by step against the full contract and look
   for the sentence that already prevents it. Write a race as a numbered
   trace of single reads and writes.
3. Where the finding rests on an outside fact (a processor, a
   controller, a firmware interface, another system), open the source
   today (17 November 2026) in the edition the contract names and quote
   the sentence with its URL: Intel SDM 325462-093
   (https://cdrdv2.intel.com/v1/dl/getContent/671200), VT-d revision
   5.20 (https://cdrdv2.intel.com/v1/dl/getContent/671081), Arm DDI 0487
   M.d (developer.arm.com), the RISC-V specifications (docs.riscv.org).
   "Not opened" where you could not.
4. Verdict: **real**; **intended** (a decision or another document
   settles it: quote it); **refuted** (quote what refutes it); and the
   severity you give, which may differ from the author's.
5. For each real finding, the correction as exact text and where, the
   smallest that closes it; say what it costs and when (the owners'
   principle: a guarantee is paid at a failure or a rare event, never on
   every memory access), and whether it needs new state.

## Output

One file, written as you go:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/ver-V3-attack.md`.
End it with one table: finding, verdict, severity, correction in one
line. You change nothing in any repository and commit nothing. English,
plain sentences. Work alone, start no subagents. Your last message is
the summary of the report. An invented quote or a scenario that does not
follow from the text costs the report its credit.
