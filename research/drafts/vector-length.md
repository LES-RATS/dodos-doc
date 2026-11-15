# Vector length on heterogeneous cores: RISC-V V, Arm SVE/SME, x86 AVX-512/AVX10

Research date: 2026-11-15. Linux sources were read from `torvalds/linux` master on that date. RISC-V quotes come from the `v1.0` tag of `riscvarchive/riscv-v-spec`, which is the ratified 1.0 text. Every claim below has a source in the last section. "Experiment" marks something I checked myself by compiling code. "Not verified" marks something I could not confirm from a primary source.

## Short answer for the design rule

On RISC-V, "refuse to place the thread on a core that lacks its length" is not enough if it means "a core with at least that length". The rule has to be **exact same VLEN**:

- Fixed-VLEN code (`-mrvv-vector-bits=128` or `=zvl`) silently corrupts memory on a core with a larger VLEN. Nothing traps.
- RISC-V has no way for M-mode or S-mode to cap the VLEN a thread sees. `vlenb` is a read-only design-time constant.
- Even vector-length-agnostic (VLA) code cannot move between cores of different VLEN once it has started. The vector registers can't be carried over, and the compiler also keeps VLEN-derived values in scalar state, such as stack frame sizes computed from `vlenb`.

So on RISC-V, a thread is pinned to the set of cores whose VLEN equals the one it started with, or equals the one it was compiled for when that is fixed. A VLA binary may *start* on any VLEN, but it then stays on that VLEN class for the rest of its life.

On Arm, a "≥" rule does work, because the kernel writes `ZCR_EL1.LEN` (and `SMCR_EL1.LEN`) on every context switch. A thread sees the same VL on every core that implements that length, and the architecture requires every core to implement all power-of-two lengths up to its maximum.

## 1. RISC-V: can a larger-VLEN core run code made for a smaller VLEN?

### What the spec promises

The RVV 1.0 spec promises portability across VLEN only "under certain constraints". It also warns that code can depend on VLEN:

> "The vector extension supports writing binary code that under certain constraints will execute portably on harts with different values for the VLEN parameter, provided the harts support the required element types and instructions."
>
> "NOTE: Code can be written that will expose differences in implementation parameters." (v-spec.adoc v1.0, lines 74–80)

VLMAX is derived from VLEN: "The derived value VLMAX = LMUL*VLEN/SEW represents the maximum number of elements that can be operated on with a single vector instruction" (line 344). `vsetvli` follows these rules: "`vl = AVL` if `AVL ≤ VLMAX`", "`ceil(AVL / 2) ≤ vl ≤ VLMAX` if `AVL < (2 * VLMAX)`", and "`vl = VLMAX` if `AVL ≥ (2 * VLMAX)`" (lines 1273–1277).

Whole-register loads and stores ignore `vl` and always move whole registers: "The instructions operate with an effective vector length, `evl`=NFIELDS*VLEN/EEW, regardless of current settings in `vtype` and `vl`." (line 2038–2040). The spec names these instructions as the tool for "compiler register spills, vector function calls where values are passed in vector registers, interrupt handlers, and OS context switches" (lines 2005–2011).

### (a) Vector-length-agnostic code

Code that takes `vl` from `vsetvli` on every strip-mining step, and sizes buffers and spill slots from `vlenb` at run time, works on any VLEN. On a larger core it simply gets a larger `vl`. This is the "under certain constraints" case. It holds only if the code never assumes a VLMAX value at compile time, and only as long as the thread stays on the same VLEN (see question 2).

### (b) Fixed-VLEN code: it breaks, and nothing traps

- GCC documents `-mrvv-vector-bits=zvl` as using the `-march` Zvl value as the exact VLEN: "The default is 'scalable', which tells GCC to interpret the number as a minimum, while 'zvl' tells GCC to use exactly the number of bits specified." (GCC RISC-V options.)
- In Clang, `-mrvv-vector-bits=<N>` or `=zvl` passes `-mvscale-max=N/64` and `-mvscale-min=N/64` to cc1 (`clang/lib/Driver/ToolChains/Clang.cpp`, lines 2117–2150). LLVM's `vscale_range(<val>)` "can be used to set both min and max to the same value" (LLVM LangRef). The optimizer therefore treats VLEN as a known constant.
- Clang's `riscv_rvv_vector_bits(N)` attribute "will be rejected unless `N==(__riscv_v_fixed_vlen*LMUL)`" (Clang AttrDocs.td).

**Experiment** (Apple clang 21.0.0, `--target=riscv64-unknown-elf -march=rv64gcv -O2`), comparing `-mrvv-vector-bits=scalable` with `-mrvv-vector-bits=128`:

1. **Auto-vectorized loop** `a[i] += b[i]`. With `=128` the loop body is `vsetivli zero, 8, e32, m2` / `vl2re32.v` / `vl2re32.v` / `vadd.vv` / `vs2r.v`, and the pointers advance by a constant 32 bytes. `vs2r.v` stores 2×VLEN bits whatever `vl` is. On a VLEN=512 core each iteration writes 128 bytes but advances only 32. The loop therefore rewrites elements it has not reached yet with wrong values, and it stores past the end of `a` on the last iterations. The scalable build reads `csrr vlenb` and scales the stride, so it is correct on any VLEN.
2. **Vector spill across a call.** With `=128` the prologue reserves a fixed `addi sp, sp, -512` and spills with `vs8r.v v16, (a2)` at `sp+400`. On VLEN=512 a `vs8r.v` writes 512 bytes, from `sp+400` to `sp+912`. That overwrites the saved `ra`/`s0` at `sp+512+16..31`, which corrupts the return address. The scalable build computes the frame as `sp -= 32*vlenb`.

These failures are the consequence of the spec rules quoted above. The specific wrong outputs are my own analysis of the generated code. I did not run it on 512-bit hardware, so execution is **not verified**. GCC's fixed-VLEN code generation was **not checked**.

A smaller core running code fixed for a larger VLEN is also wrong. `vsetivli` with AVL > VLMAX returns a smaller `vl`, and fixed-VLEN code does not read it back.

### Can M-mode or S-mode cap the VLEN a thread sees?

No, not in the ratified spec. "NOTE: The value in `vlenb` is a design-time constant in any implementation." (v-spec.adoc v1.0, line 536.) `vlenb` is listed as "URO" (user read-only) in the CSR table. The only privileged vector control I found is `mstatus.VS` (and `vsstatus.VS`), which sets Off/Initial/Clean/Dirty and does not change the length (spec section "Vector Context Status in `mstatus`").

I found no ratified or in-progress RISC-V extension that limits VLEN the way `ZCR_ELx.LEN` does on Arm. My searches were not exhaustive, so read this as "none found", not as a proof that none exists. The SpacemiT LPC 2026 talk lists "Configurable VLEN on A-series cores: Hardware switch: VLEN 1024 ↔ 256" only as a "design extrapolation for future silicon" that is "Not implemented on K3".

### What Linux does today

Linux supports one VLEN per system. A hart with a different VLEN does not come online.

- `arch/riscv/kernel/vector.c`, `riscv_v_setup_vsize()`: the first hart sets `riscv_v_vsize = vlenb*32`. Any later hart with a different value hits `WARN(1, "RISCV_ISA_V only supports one vlenb on SMP systems"); return -EOPNOTSUPP;`.
- `arch/riscv/kernel/cpufeature.c` calls it on the boot hart with the comment "This cannot fail when called on the boot hart".
- `arch/riscv/kernel/smpboot.c`, `smp_callin()`: "Return as early as possible so the hart with a mismatching vlen won't boot." followed by `if (riscv_v_setup_vsize()) return;`. The mismatching secondary hart is refused. Vector support stays on for the harts that match the boot hart.
- For the pre-ratification T-Head vector extension, VLEN comes from the device-tree property `thead,vlenb`. On a mismatch the kernel turns vectors off instead: `pr_warn("Unsupported heterogeneous vlenb detected, vector extension disabled.\n"); disable_xtheadvector();` (`cpufeature.c`).
- In practice (SpacemiT, LPC 2026), the K3 has "VLEN mismatch 256 vs 1024". The slides say: "Upstream kernel: Use 8 X100 cores only". The vendor kernel's `CONFIG_SPACEMIT_HMP` hard-codes "riscv_v_vsize = 4096 (hard-coded max across both core classes)" and binds threads to a core class through `/proc/set_ai_thread`. The slides call it "Vendor SDK only — not suitable for upstream".

## 2. Migrating a thread mid-computation between harts of different VLEN

The spec says it cannot be done in general:

> "NOTE: In general, thread contexts with active vector state cannot be migrated during execution between harts that have any difference in VLEN or ELEN parameters." (v-spec.adoc v1.0, lines 82–84)

What happens to each piece of state:

- **v0–v31.** Each register holds VLEN bits. A 512-bit register's contents do not fit in a 128-bit register. Going the other way, the upper bits would have to be invented. No defined mapping exists, so the state is not representable on the other hart.
- **vl.** It may exceed the new VLMAX, which `vsetvli` can never produce there.
- **vtype.** It is portable as an encoding. The `vta`/`vma` bits "must still be provided in `vtype` for compatibility and to support thread migration" (line 430). That note is about migration between different microarchitectures; it does not lift the VLEN restriction quoted above.
- **vstart.** Even with equal VLEN, "the `vstart` value might not be supported by the new hart microarchitecture. The runtime on the receiving hart might then have to emulate instruction execution up to the next supported `vstart` element position" (lines 602–608).

Migration is also unsafe when the vector registers are dead, which goes beyond what the spec says. **Experiment:** in VLA code, Clang's prologue does `csrr a3, vlenb; slli a3, a3, 5; sub sp, sp, a3`. The epilogue re-reads `vlenb` to undo it (`csrr a0, vlenb; slli a0, a0, 5; add sp, sp, a0`). A thread moved between these two points returns with a wrong `sp`. Loop strides and pointer increments derived from `vlenb` are also kept in scalar registers. So VLEN is baked into the scalar state of every live frame, not only into `v0–v31`. The SpacemiT slides say the same: "After the first vector instruction: All rvv register contents are semantically bound to VLEN. Migration to a different-VLEN core: save/restore undefined, data layout breaks", and "ARM big.LITTLE worst case: slow / RISC-V VLEN worst case: wrong".

A thread could safely change VLEN class only at a point where no live frame holds a VLEN-derived value, for example before `main` runs (at exec). The SpacemiT slides float a "VINIT" instruction as a user-declared migration window, but call it "Only helps software you compile / control — not a general solution". It is **not** in any RISC-V spec I found.

## 3. Arm64 comparison: SVE and SME

### A higher exception level constrains the length

From the Arm A-profile register description of `ZCR_EL1` (release 2026.09):

- LEN "Requests an Effective Non-streaming SVE vector length at EL1 of (LEN+1)*128 bits".
- "If EL2 is implemented and enabled in the current Security state, and the requested length is greater than the Effective length at EL2, then the Effective length at EL2 is used. If EL3 is implemented and the requested length is greater than the Effective length at EL3, then the Effective length at EL3 is used. Otherwise, the Effective length is the highest supported Non-streaming SVE vector length that is less than or equal to the requested length."

So EL1 sets the length for EL0, EL2 caps EL1, and EL3 caps EL2.

### What lengths a core must support

- "The Non-streaming SVE vector length can be any power of two from 128 bits to 2048 bits inclusive."
- "An implementation can support a subset of the architecturally permitted lengths."
- "An implementation is required to support all lengths that are powers of two, from 128 bits up to its maximum implemented Non-streaming SVE vector length."

A 512-bit core therefore also runs at 256 and 128 bits. Older SVE supplements also allowed non-power-of-two multiples of 128 bits. That is mentioned in a secondary search result only and is **not verified**. Linux comments that "The SVE architecture mandates support for 128-bit vectors" (`fpsimd.c`, `sve_setup()`).

### SME streaming length (SMCR_EL1)

The same scheme applies to SME through `SMCR_EL1.LEN`, with one difference: SME has no required set of lengths.

- LEN "Requests an Effective Streaming SVE vector length (SVL) at EL1 of (LEN+1)*128 bits", capped by EL2 and EL3 in the same way.
- "An implementation can support any subset of the architecturally permitted lengths."
- "If the requested length is less than the minimum implemented Streaming SVE vector length, then the Effective length is the minimum implemented Streaming SVE vector length."

Linux says the same: "SME doesn't require any particular vector length be supported but it does require at least one" (`fpsimd.c`, `sme_setup()`).

### What Linux does on systems whose CPUs differ (`arch/arm64/kernel/fpsimd.c`, `cpufeature.c`)

- At boot, `vec_probe_vqs()` writes every LEN value and reads back the effective VL to build the set of supported lengths per CPU.
- For the boot CPU and early secondary CPUs, `vec_update_vq_map()` does `bitmap_and(info->vq_map, ...)` (the intersection of all CPUs' lengths) and `bitmap_or(info->vq_partial_map, ...)`. User threads may only use lengths in `vq_map`, the set common to all CPUs. `sve_setup()` takes the maximum of that set.
- For late (hotplugged) CPUs, `vec_verify_vq_map()` prints "Required vector length(s) missing" if the CPU lacks any length in the committed set. `verify_sve_features()` / `verify_sme_features()` then print "vector length support mismatch" and call `cpu_die_early()`, so the CPU is refused.
- When KVM is present, a late CPU that supports *extra* lengths at or below the maximum virtualisable VL is also refused ("Unsupported vector length(s) present"). The reason is that a guest that probed lengths through `ZCR_EL1` would see a different set on that CPU. The kernel warns "unvirtualisable vector lengths present" when partial lengths exist.
- On every switch back to a task, the kernel writes `sysreg_clear_set_s(SYS_ZCR_EL1, ZCR_ELx_LEN, vq - 1)` and, for SME, `SYS_SMCR_EL1, SMCR_ELx_LEN`. Each thread therefore keeps its own VL on every CPU.

The thread VL is chosen with `prctl(PR_SVE_SET_VL)`. At boot the default "is initially set to 64 or the maximum supported vector length, whichever is smaller" (Documentation/arch/arm64/sve.rst). For SME the default is "the maximum supported value <= 32 (256 bits) if there is one" (`sme_setup()`).

## 4. x86-64, briefly

- **Alder Lake.** The P-cores physically have AVX-512 and the E-cores do not. Intel shipped with AVX-512 off so that both core types expose the same ISA, and then fused it off. Intel's support article says: "AVX-512 will be fused off on Alder Lake mobile products and most desktop products." and "Although AVX-512 was not fuse-disabled on certain early Alder Lake desktop products, Intel plans to fuse off AVX-512 on Alder Lake products going forward."
- **The BIOS workaround.** On some boards AVX-512 could be turned on only with the E-cores disabled. Only secondary sources (AnandTech, Tom's Hardware) report this, and I did not read Intel's developer-guide wording myself, so it is **not verified** from a primary source.
- **Linux.** No support for an asymmetric ISA was added. In November 2021 Andy Lutomirski proposed on LKML that AVX-512 be turned off per task through XCR0 with a prctl opt-in, "if Intel ever wants to expose the full Alder Lake physical capabilities and support efficiency cores and AVX-512 on the same boot". Arjan van de Ven (Intel) replied "Alderlake is not heterogenous." Thomas Gleixner answered that "context switching XCR0 sucks" and suggested XFD instead. I found no merged code for asymmetric CPUID features. I did not find a single authoritative statement of Linux policy on asymmetric x86 ISA, so that remains **not verified**.
- **AVX10.** Intel's answer is one ISA on all cores. The AVX10 technical paper (356368-003, Revision 3.0, March 2025) says: "The converged version of the Intel AVX10 vector ISA will include Intel AVX-512 vector instructions with an AVX512VL feature flag and eight 64-bit mask registers. This converged version will be supported on both P-cores and E-cores." Its revision history reads: "3.0 Removed references to 256-bit maximum vector register size, enumeration of vector-length support, and 256-bit instructions supporting embedded rounding. March 2025." Intel first allowed a 256-bit-only AVX10 for E-cores, then removed that option. Every core must now offer the same 512-bit ISA. Intel's answer is uniform hardware, not kernel scheduling.

## What this means for the DodOS rule

| | Can a core with a larger vector length run the thread? | Who holds the length | Rule the kernel needs |
|---|---|---|---|
| RISC-V V | Fixed-VLEN code: no, silent corruption. VLA code: yes at start, never after migration. | Hardware constant (`vlenb`); no cap | Exact VLEN equality, for the thread's whole life |
| Arm SVE | Yes. The kernel sets the thread's VL with `ZCR_EL1.LEN`, and all smaller powers of two must exist. | Kernel, per thread | Core must implement the thread's VL. A "≥ max" rule works for SVE. |
| Arm SME | Only if the core implements that exact SVL (lengths are an arbitrary subset) | Kernel, per thread | Core's set of SVLs contains the thread's SVL |
| x86 | Not applicable: vendors make the ISA uniform | Hardware | Same features on all cores |

For RISC-V the contract should state the following:

1. Each core class has one VLEN.
2. A thread's vector length is either fixed by its binary or recorded at its first vector use (or at exec) from the core it started on.
3. The scheduler places the thread only on cores whose VLEN is **equal**, never on a larger one.
4. Changing class happens only at exec, or at an explicit point where the thread promises no live VLEN-derived state. That would be a new contract feature with no ISA support today.

## Sources

RISC-V
- RISC-V "V" Vector Extension, Version 1.0 (ratified text, tag v1.0): https://github.com/riscvarchive/riscv-v-spec/blob/v1.0/v-spec.adoc (raw: https://raw.githubusercontent.com/riscvarchive/riscv-v-spec/v1.0/v-spec.adoc). Lines cited: 74–84, 105, 118, 344, 430, 536, 600–608, 1273–1277, 2005–2011, 2038–2040.
- GCC RISC-V options, `-mrvv-vector-bits`: https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html
- Clang driver handling of `-mrvv-vector-bits`: https://github.com/llvm/llvm-project/blob/main/clang/lib/Driver/ToolChains/Clang.cpp
- Clang `riscv_rvv_vector_bits` documentation: https://github.com/llvm/llvm-project/blob/main/clang/include/clang/Basic/AttrDocs.td
- LLVM LangRef, `vscale_range`: https://llvm.org/docs/LangRef.html
- RISC-V C API (`__riscv_v_min_vlen`): https://github.com/riscv-non-isa/riscv-c-api-doc/blob/main/src/c-api.adoc
- Linux `arch/riscv/kernel/vector.c`: https://github.com/torvalds/linux/blob/master/arch/riscv/kernel/vector.c
- Linux `arch/riscv/kernel/smpboot.c`: https://github.com/torvalds/linux/blob/master/arch/riscv/kernel/smpboot.c
- Linux `arch/riscv/kernel/cpufeature.c`: https://github.com/torvalds/linux/blob/master/arch/riscv/kernel/cpufeature.c
- Earlier patch discussion on heterogeneous vlenb from DT (Conor Dooley, 2024-05-16, "Re: [PATCH v6 03/17] riscv: vector: Use vlenb from DT"): https://www.mail-archive.com/linux-kselftest@vger.kernel.org/msg12690.html
- Mark Zhuang and Dong Xu (SpacemiT), "Heterogeneous RISC-V Cores in Linux", LPC 2026 RISC-V MC: https://lpc.events/event/20/contributions/2479/attachments/2178/4814/LPC2026-Heterogeneous-RISC-V-Cores-in-Linux-SpacemiT-202610.pdf

Arm
- Arm A-profile Architecture Registers, ZCR_EL1 (official page renders with JavaScript; text read from a rendering of the same release 2026.09): https://developer.arm.com/documentation/ddi0601/latest/AArch64-Registers/ZCR-EL1--SVE-Control-Register--EL1- and https://arm.jonpalmisc.com/latest_sysreg/AArch64-zcr_el1
- SMCR_EL1, same release, read from the rendering: https://arm.jonpalmisc.com/latest_sysreg/AArch64-smcr_el1 (official equivalent in DDI0601, URL not checked)
- Arm Learn, SVE insights: https://learn.arm.com/insights/sve/
- Linux `arch/arm64/kernel/fpsimd.c`: https://github.com/torvalds/linux/blob/master/arch/arm64/kernel/fpsimd.c
- Linux `arch/arm64/kernel/cpufeature.c` (`verify_sve_features`, `verify_sme_features`): https://github.com/torvalds/linux/blob/master/arch/arm64/kernel/cpufeature.c
- Linux Documentation/arch/arm64/sve.rst: https://docs.kernel.org/arch/arm64/sve.html (source https://github.com/torvalds/linux/blob/master/Documentation/arch/arm64/sve.rst)

x86
- Intel, "Is AVX-512 Fused Off on Alder Lake Client Products?" (last reviewed 2022-03-25): https://www.intel.com/content/www/us/en/support/articles/000089918/processors.html
- Intel AVX10 technical paper, 356368-003, Rev. 3.0, March 2025: https://cdrdv2-public.intel.com/849709/356368-003-intel-avx10-technical-paper.pdf
- LKML thread "Revisiting XFD-based AMX and heterogenous systems" (Nov 2021): https://lore.kernel.org/lkml/0f03a9e2-4611-4b5c-962f-93a7e1d2bde8@www.fastmail.com/ , https://lore.kernel.org/lkml/8425e818-f6cc-ae52-ac6b-9cc80515c238@linux.intel.com/ , https://lore.kernel.org/lkml/8735nx6s2z.ffs@tglx/
- Secondary, for the BIOS workaround only: AnandTech, "Intel Disabled AVX-512, but Not Really": https://www.anandtech.com/show/17047/the-intel-12th-gen-core-i912900k-review-hybrid-performance-brings-hybrid-complexity/2
