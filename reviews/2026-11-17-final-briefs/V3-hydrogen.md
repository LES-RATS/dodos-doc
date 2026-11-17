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

## Your angle: attack it

The text makes promises: a faulty or hostile kernel on one group of
cores is confined; a process reaches only what its capabilities name; a
device reaches only memory it was given; a dead part is fenced and its
memory reclaimed; every call ends in bounded time; nothing grows without
bound. Take the role of an attacker in turn as: a user process with a
few capabilities; a driver process with a device; a whole faulty kernel
of one node (it can write its own memory and send any message, but not
what the text says only the gate writes); a device doing DMA or raising
interrupts; someone at the debugger or the console.

For each, try to: read or write memory you were not given; keep
something after it was revoked or after you were killed; make another
party wait for ever, loop for ever, or accuse a healthy one; exhaust
something another party needs; forge a message, a request or a word;
win a race between two rules; survive a restart. Give each attack as
numbered steps naming the rule that lets each step pass. Say which
promises you could not break and how hard you tried.

## Output

One file, written as you go:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v3-hydrogen.md`.
For each finding: a number, a severity (breaks a guarantee / cannot be
built as written / contradiction / unsettled case / wrong external
fact), the lines quoted with their numbers, the scenario step by step,
and the smallest correction you would write. End with what you checked
and found sound, and what you did not check. An invented quote or a
scenario that does not follow from the text costs the report its
credit: another model will check every line of it. You change nothing
anywhere else. English, plain sentences. Work alone, start no
subagents. Your last message is the summary of the report.
