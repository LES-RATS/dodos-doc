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

## Your angle: can it be built on real hardware, and are its outside facts true?

- Every claim about a processor, a controller, a firmware interface or
  another system (x86-64, ARM64, RISC-V; APIC, IOAPIC, GIC, APLIC, IMSIC;
  VT-d and other IOMMUs; ACPI, UEFI, PSCI, SBI, SDEI; Linux or seL4 where
  cited): check it at its source today, in the edition the text names.
  Give the URL and the sentence you read. Say "not opened" where you
  could not open the source; do not answer from memory without saying
  so.
- A rule that the hardware cannot do as written: an atomicity or an
  ordering no instruction gives, a register that does not exist or
  behaves otherwise, an interrupt that cannot be masked or cannot be
  sent, a table format with no room for what the text puts in it.
- Concurrency between cores: every word written by one core and read by
  another without a lock. Is the order of the write and the read enough
  under each architecture's memory model?
- Timing: every time limit against what real machines do (firmware
  stalls, idle exit latencies, interrupt delivery).

## Output

One file, written as you go:
`/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/final/reports/v3-opus.md`.
For each finding: a number, a severity (breaks a guarantee / cannot be
built as written / contradiction / unsettled case / wrong external
fact), the lines quoted with their numbers, the scenario step by step,
and the smallest correction you would write. End with what you checked
and found sound, and what you did not check. An invented quote or a
scenario that does not follow from the text costs the report its
credit: another model will check every line of it. You change nothing
anywhere else. English, plain sentences. Work alone, start no
subagents. Your last message is the summary of the report.
