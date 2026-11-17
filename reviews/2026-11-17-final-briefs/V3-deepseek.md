# Review of a specification, on its own

You review one specification document. You know nothing else about the
project and you are given nothing else: that is intended. The document
is `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
(about 2,300 lines): the contract of an operating system kernel, its
objects, its system calls and the rules they keep. Read it whole, from
the first line to the last, before you write anything. Do not read any
other file of that repository (not its decisions, not its reviews, not
its other documents, even where the contract links to them) and do not
look for the project on the web: you judge what this text says by
itself.

## Your angle: does the text agree with itself, and is it complete?

- Two sentences that contradict each other (a number, a size, a state,
  an order of checks, a result code, who writes a word).
- A term used before or without its definition; a state, a field or a
  constant named in one place and nowhere defined.
- For every system call: can each result it lists be reached, and is
  every failure the rules imply listed? Is the order of its checks
  total?
- For every state machine (a capability slot, a thread, a node, a core
  word, an ownership word, an attach word, a role, a fence, a request):
  draw the states against the events and find the cell with no rule, or
  with two.
- Every bound and every size the text computes: recompute it.
- A rule that names something the text says no longer exists.

## Output

One file, written as you go:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v3-deepseek.md`.
For each finding: a number, a severity (breaks a guarantee / cannot be
built as written / contradiction / unsettled case / wrong external
fact), the lines quoted with their numbers, the scenario step by step,
and the smallest correction you would write. End with what you checked
and found sound, and what you did not check. An invented quote or a
scenario that does not follow from the text costs the report its
credit: another model will check every line of it. You change nothing
anywhere else. English, plain sentences. Work alone, start no
subagents. Your last message is the summary of the report.
