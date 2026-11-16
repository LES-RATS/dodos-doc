# Zig in the hardware layer: where its strengths pay, and where the split should run

**Research draft, 16 November 2026. Not integrated: not the contract.** Written by an agent at the owner's request. The question: does DodOS use Zig where Zig is strong (comptime, packed structs, struct-of-arrays and the rest), and does the split proposed last put Zig in the wrong place? The presence of Zig in the kernel (D-004, D-094) is not reopened; only where it sits.

The split under review, not yet written down: the gate's checks and the generic page-table walk in Rust; in Zig, per architecture, the primitives (write a table entry, invalidate the TLB, load a root), trap entry and exit, the context switch, the IPC fast path; about 1,000 to 2,500 lines of Zig per architecture.

**Method.** Every snippet below was compiled with Zig 0.17.1 (`/Users/btw/.nix-profile/bin/zig`, LLVM 22.1.8 per `zig cc --version`) for `x86_64-freestanding`, `aarch64-freestanding` and `riscv64-freestanding`, and the Rust ones with rustc 1.100.0 (LLVM 23.1.5, `rustc -vV`) from the flake of `dodos-kernel` with two more targets added (`aarch64-unknown-none`, `riscv64gc-unknown-none-elf`) in a copy under `/tmp/dodos-zig`, its lock file unchanged. The experiments are in `/tmp/dodos-zig/{lto,feat,bench,link,compat,abi}` (temporary; the key code is quoted here). The abi constants come from `dodos-kernel` branch `model` at `2afc901`. The contract is cited at Docs commit `4b12baf`. Timings are from one machine, an Apple M5 (`sysctl machdep.cpu.brand_string`), and say nothing of x86-64 or RISC-V hardware. What could not be tested is marked **not verified**.

## Contents

1. [Summary](#1-summary)
2. [The boundary: can a Zig primitive be inlined into Rust?](#2-the-boundary-can-a-zig-primitive-be-inlined-into-rust)
3. [comptime](#3-comptime)
4. [Packed structs, bit fields and volatile](#4-packed-structs-bit-fields-and-volatile)
5. [Struct-of-arrays](#5-struct-of-arrays)
6. [Inline assembly, naked functions, sections, linker script](#6-inline-assembly-naked-functions-sections-linker-script)
7. [Safety modes and what crosses to Rust](#7-safety-modes-and-what-crosses-to-rust)
8. [How the two builds are driven](#8-how-the-two-builds-are-driven)
9. [The split I recommend, function by function](#9-the-split-i-recommend-function-by-function)
10. [What the contract must say](#10-what-the-contract-must-say)
11. [Not verified](#11-not-verified)

## 1. Summary

**The proposed split puts one thing in the wrong place: the page-table primitives.** A Rust walker that calls a Zig "write one entry" once per entry pays a real call per entry unless both languages go through one LTO step. That step works (section 2: inlined on all three targets, disassembly shown), but only under five conditions that couple the two toolchains tightly, and it fights the gate itself: the gate must be one unit in one section for the binary scan of G11, and a Zig primitive placed in the gate section was *not* inlined. The primitives are one to four instructions each; Rust's `asm!` writes them as well as Zig's. They belong with the walker and the checks, in Rust, inside the gate.

**The IPC fast path is better in Rust too.** It reads the same capability slots, endpoints and threads as the slow path. In Zig it needs a C-ABI mirror of every structure it touches and keeps Rust from using its own types there, for no Zig strength I could show. The stub calls the fast path once per event whichever language it is in.

**Zig pays in the device-facing hardware layer:** register files and descriptors as packed structs, system register accessors generated at compile time from the vendors' data with the gate classification enforced by the compiler, entry stubs generated from `abi/` constants, and no `.S` file at all. These are calls made once per event or per operation, never per table entry, so the boundary costs nothing worth measuring and needs no cross-language LTO.

| Feature | Where it pays in DodOS | Where it does not | Against Rust |
|---|---|---|---|
| `comptime` format descriptions | Would pay if the walker were Zig | The walker belongs in Rust with the checks | **Equal**: same machine code (18 against 18 instructions for a walk, 9 against 8 for a leaf) |
| `comptime` from data (ZON import, asm templates built from data) | Register accessors and scan lists; classification enforced at compile time | Parsing the 97 MB Arm JSON at compile time: no, a build step reduces it | **Zig better**: Rust needs a macro per register, and `asm!` cannot take a template from a const |
| Layout checks against `abi/` | Entry stubs: offsets from generated constants, checked at compile time | | **Equal** (`offset_of!` and `const` asm operands in Rust) |
| Architecture selection | `switch (builtin.cpu.arch)`, other branches never analysed | | **Equal** (`#[cfg(target_arch)]`) |
| `packed struct` | MMIO registers, IOMMU and interrupt-controller descriptors, command queue entries | Table entries handled by the Rust gate as raw words | **Zig better** (Rust has no bit fields; macros or crates) |
| `volatile` packed MMIO | Same | Field writes are read-modify-write; a struct literal stored through a volatile pointer is one RMW **per field** (measured) | Rust has the same hazards with any wrapper |
| `MultiArrayList` / hand-made SoA | Works with no allocator on a static buffer | No hot data in the hardware layer; the gate's words are already SoA by contract, and AoS against SoA differs by at most 1.75× (measured) | Equal by hand; the std type is a Zig convenience |
| Naked functions, inline and global asm, sections | Entry, vector tables, IDT stubs, AP trampoline: nothing needs a `.S` file | | **Equal** (`#[unsafe(naked)]`, `naked_asm!`, `global_asm!` produce the same bytes) |
| Safety modes | `ReleaseSafe` for the hardware layer, `@setRuntimeSafety(false)` for marked scopes, one panic path into Rust's stop | Error unions and slices do not cross `extern` | Rust: overflow checks per profile, `Option<&T>` crosses as a nullable pointer |

## 2. The boundary: can a Zig primitive be inlined into Rust?

### 2.1 The test

A Zig file of primitives (`/tmp/dodos-zig/lto/prim.zig`):

```zig
const builtin = @import("builtin");
export fn pt_write_entry(table: [*]volatile u64, index: usize, value: u64) callconv(.c) void {
    table[index] = value;
}
export fn pt_invalidate_page(tag: u64, va: u64) callconv(.c) void {
    switch (builtin.cpu.arch) {
        .x86_64 => asm volatile ("invlpg (%[va])" : : [va] "r" (va) : .{ .memory = true }),
        .aarch64 => asm volatile ("dsb ishst\ntlbi vae1is, %[arg]\ndsb ish\nisb"
            : : [arg] "r" ((va >> 12) | (tag << 48)) : .{ .memory = true }),
        .riscv64 => asm volatile ("sfence.vma %[va], %[asid]"
            : : [va] "r" (va), [asid] "r" (tag) : .{ .memory = true }),
        else => @compileError("unsupported architecture"),
    }
}
```

and a Rust walker that calls them per entry (`walk.rs`, `kmain.rs`):

```rust
unsafe extern "C" { fn pt_write_entry(table: *mut u64, index: usize, value: u64); fn pt_invalidate_page(tag: u64, va: u64); }
#[unsafe(no_mangle)]
pub extern "C" fn map_run(table: *mut u64, first: usize, count: usize, pa: u64, flags: u64) {
    for i in 0..count { unsafe { pt_write_entry(table, first + i, (pa + ((i as u64) << 12)) | flags) }; }
}
```

### 2.2 Versions

Zig 0.17.1 is built on LLVM 22.1.8; Rust 1.100.0 on LLVM 23.1.5. Not the same major version. LLVM promises that a newer release reads older bitcode ("The current LLVM version supports loading any bitcode since version 3.0", [LLVM Developer Policy, IR Backwards Compatibility](https://llvm.org/docs/DeveloperPolicy.html#ir-backwards-compatibility)), not the reverse. The rustc book says the same for linker-plugin LTO: "use an LLVM linker plugin whose version is at least as new as the newest compiler involved" ([rustc book, Linker-plugin-based LTO, Toolchain Compatibility](https://doc.rust-lang.org/rustc/linker-plugin-lto.html)).

Both directions tested:

- **LLVM 23 reading Zig's LLVM 22 bitcode** (`rust-lld --lto-O3`, `llvm-link`, `opt`): works on all three targets.
- **Zig's LLVM 22 reading Rust's LLVM 23 bitcode**: the small walker happened to load and even inline, but the embedded bitcode of Rust's own `core` (extracted from `libcore-*.rlib`, section `.llvmbc`) is refused: `error: Not an int attribute (Producer: 'LLVM23.1.5-rust-1.100.0-stable' Reader: 'LLVM 22.1.8')`. So **Zig cannot be the linker of an LTO build with Rust**; the LTO link must run on Rust's LLVM, and it keeps working only while Rust's LLVM is at least as new as Zig's.

### 2.3 What blocked inlining, in order

The first link (`rust-lld -flavor gnu -static -nostdlib --lto-O3`, Rust object from `-Clinker-plugin-lto`, Zig from `-femit-llvm-bc`) produced a call per entry on all three targets. Four causes, each found and removed:

1. **Two LTO partitions.** rustc's bitcode carries a ThinLTO summary (6 summary entries in `llvm-dis walk-aarch64.o`); Zig's carries none. lld then optimises Rust's module in the ThinLTO backend and Zig's in the regular LTO partition (`--save-temps`: `t.elf.0.*` holds only the Zig functions), and nothing crosses. `rustc --emit=llvm-bc` also writes the summary. Two fixes work: strip Rust's summary (`opt walk.bc -o walkA.bc`, 0 entries left) so both are regular LTO, or give Zig's module a summary with LLVM 23's `opt --thinlto-bc` so both are ThinLTO. The second fits a real build: rustc links as usual with `-Clinker-plugin-lto -Clink-arg=primB.bc`.
2. **Zig's exports are aliases.** Zig 0.17.1 emits `export fn pt_write_entry` as an internal function `@prim.pt_write_entry` and an external `@pt_write_entry = alias ...` (seen in `llvm-dis`). The inliner does not go through an alias that is still external; once the symbol is internalised (lld does it for a static link, where the resolution file shows `pt_write_entry,pl`; `opt -passes=internalize` in the manual test) it goes through.
3. **Conflicting target features (x86-64).** The inliner refused with `'prim.pt_write_entry' not inlined into 'map_run' because it should never be inlined (cost=never): conflicting target features` (remark from `opt -pass-remarks-missed=inline`). Zig's default x86-64 freestanding target enables `+sse,+sse2,+mmx`; Rust's `x86_64-unknown-none` disables them and sets `+soft-float`. Fix: `zig build-obj -mcpu=x86_64-mmx-sse-sse2+soft_float`. ARM64 (`generic-ete-trbe+strict_align`) and RISC-V (`baseline_rv64+zifencei`) were matched the same way; on those two the defaults already inlined once causes 1 and 2 were removed.
4. **Red zone.** Not a cause of the refusal, but found on the way: Zig's x86-64 freestanding functions carry no `noredzone` attribute (Rust's do). A kernel must pass `-mno-red-zone` (or `.red_zone = false` in `zig build`).

### 2.4 The result: inlined on all three targets

Through rustc's own link (`rustc ... -Clinker-plugin-lto -Clink-arg=primB-$a.bc -Clink-arg=--lto-O3 kmain.rs`), the Zig primitives disappear into Rust's `_start`. x86-64:

```
_start:
  movq  $0x200003, 0x1000      ; eight entries written, no call
  ...
  movq  $0x207003, 0x1038
  movq  $0x0, 0x1008           ; unmap_one: the store ...
  movl  $0x1000, %eax
  invlpg (%rax)                ; ... and Zig's invlpg, inline
```

ARM64 (`map_run` and `unmap_one` of the regular-LTO variant):

```
map_run:  cbz x2, 1f ; add x8, x0, x1, lsl #3
       0: orr x9, x3, x4 ; subs x2, x2, #1 ; add x3, x3, #1, lsl #12 ; str x9, [x8] ; add x8, x8, #8 ; b.ne 0b
       1: ret
unmap_one: lsr x8, x3, #12 ; str xzr, [x0, x1, lsl #3] ; orr x8, x8, x2, lsl #48
           dsb ishst ; tlbi vae1is, x8 ; dsb ish ; isb ; ret
```

RISC-V: `map_run` is a ten-instruction loop with `sd` inline, `unmap_one` is `sd zero, 0(a0); sfence.vma a3, a2; ret`. Before the fixes the same functions held `callq *%rbp`, `bl pt_write_entry` and `jalr pt_write_entry` in the loop.

So: **yes, cross-language LTO inlines a small Zig function into Rust on x86-64, ARM64 and RISC-V**, under five conditions: Rust's LLVM at least as new as Zig's; Rust's linker (not Zig's) performs the LTO link; both modules in one partition (an extra `opt --thinlto-bc` step from LLVM 23's tools); Zig's CPU features matched by hand to Rust's target, per target; the symbols internalised.

### 2.5 Two findings that argue against relying on it

- **An explicit section stops the inlining.** With `pt_invalidate_page` placed in `linksection(".gate.text")`, the same build kept it out of line (`callq 0x1330 <pt_invalidate_page>`, the function alone in section `.gate.text`), while `pt_write_entry`, with no section, was still inlined. The reason was not traced in LLVM's sources (**not verified**; likely ThinLTO's rule against importing a local symbol that has an explicit section, and Zig's exports are locals behind aliases). For DodOS this matters: G11 requires the forbidden instructions (`invlpg`, `msr ttbr0_el1`, `csrw satp`, `wrssq`) to sit only inside the gate, so the gate's code must be in its own section. A Zig primitive in the gate section is not inlined; a Zig primitive inlined into Rust leaves the gate section. Either the walker and its primitives are in the same language, or the per-entry call stays.
- **Per-call cost when not inlined.** On the M5, a Rust loop writing 512 entries through a Zig function in another object, no LTO, cost 2.18 ns per entry against 0.48 ns for an inline volatile store; with a G3-shaped check per entry (ownership word with its check field, gate word, class byte, all in cache) 1.57 ns against 0.95 to 0.99 ns (three runs each, `/tmp/dodos-zig/bench/bench.rs`). So up to about 1 µs added per call of 512 entries on this machine. Small next to a TLB invalidation, but it is pure loss for a one-instruction operation. x86-64 and RISC-V hardware: **not measured**.

Also: per the LLVM policy above, debug metadata of older bitcode "is currently dropped during upgrades", so Zig code merged by LLVM 23 may lose its debug information (**not verified** in the produced binaries).

**Consequence for the split:** put each primitive on the side of the code that calls it per entry. The walker and the checks are Rust (the draft's recommendation, beside the model and Kani), so the primitives are Rust `asm!` in the gate section. Everything Zig keeps is then called once per event or per operation, the link needs no cross-language LTO, and the two LLVM versions are free of each other.

## 3. comptime

### 3.1 Page-table formats from a description: equal to Rust

`/tmp/dodos-zig/feat/pt_format.zig` describes seven formats as comptime values and builds one specialised code per format. The description holds functions, so it exists only at compile time:

```zig
pub const Desc = struct {
    page_shift: u6, index_bits: u6, levels: u4,
    leaf_levels: u8,                // bit k: level k may hold a leaf
    valid: u64, table_bits: u64,
    leafBits: fn (level: u4) u64,   // x86-64 PS, ARM64 page against block
    addr_shift: u6, addr_mask: u64,
    encodePerm: fn (Perm) u64,
    preset: u64,                    // accessed and dirty, preset (G3 step 4)
};
pub fn Format(comptime d: Desc) type {
    comptime {
        if (@as(u32, d.page_shift) + @as(u32, d.index_bits) * d.levels > 64) @compileError("format covers more than 64 bits");
        if (d.leaf_levels & 1 << 1 == 0) @compileError("level 1 must hold leaves");
    }
    return struct {
        pub const entries: usize = @as(usize, 1) << d.index_bits;
        pub inline fn leaf(pa: u64, level: u4, perm: Perm) u64 {
            return d.valid | d.leafBits(level) | d.encodePerm(perm) | d.preset |
                (((pa >> d.page_shift) << d.addr_shift) & d.addr_mask);
        }
        pub fn entryFor(root_pa: u64, va: u64, stop: u4, direct_map: u64) ?*volatile u64 { ... }
    };
}
pub const X86_4 = Format(x86_64(4));   pub const X86_5 = Format(x86_64(5));
pub const Arm4K = Format(arm64(12, 4)); pub const Arm16K = Format(arm64(14, 3));
pub const Sv39 = Format(sv(3)); pub const Sv48 = Format(sv(4)); pub const Sv57 = Format(sv(5));
```

All seven compile on all three targets (the formats are not tied to the target, so they can be tested on the host), and a test checks encodings (`zig test pt_format.zig`: x86-64 4 KB leaf `0x8000_0000_4000_0067`, 2 MB leaf with PS `...00E7`, 2,048 entries per 16 KB table, Sv48 leaf, Sv57 index). The walk is fully unrolled per format with every shift and mask a constant.

The same in Rust (`pt_format.rs`): a trait `Format` with associated constants and two `#[inline(always)]` functions, a generic `Walker<F: Format>`, `Sv<const L: u32>` and `Arm<const G: u32, const L: u32>` with const generics, and the description's checks as an associated `const CHECK: () = { assert!(...) }` evaluated where it is used. Generated code, with frame pointers omitted on the Zig side (`-fomit-frame-pointer`; Zig keeps them by default in ReleaseFast for freestanding, `"frame-pointer"="all"` in its IR):

| Function | Zig instructions | Rust instructions |
|---|---|---|
| `sv48_leaf` (RISC-V) | 6 | 6 |
| `sv48_entry_for` (RISC-V, 4-level walk) | 44 | 43 |
| `arm16k_leaf` (ARM64) | 9 | 8 |
| `arm16k_entry_for` (ARM64, 3-level walk) | 18 | 18 |

**Equal.** Redox's `rmm` already does this in Rust (draft, part 2.1), Linux `generic_pt` in C. Zig's form is shorter to write (a description is an ordinary struct value, functions included; Rust needs a type per format and a trait), and Rust's form checks the interface at the definition (a trait) where Zig checks it only when a format is instantiated. Neither difference changes the code. Since the walker belongs with the checks in Rust (section 2.5 and the draft), this strength of Zig is not needed here.

### 3.2 Registers and scan lists from the vendors' data: Zig is better, through a build step

`/tmp/dodos-zig/feat/regs.zig` imports a ZON file (`@import("regs.zon")`, typed as `[]const Reg`) that stands for the output of a build step reducing Arm's `Registers.json` to the fields the kernel uses, with the classification of the draft (part 4.4: `gate`, `kernel`, `unreachable`, `unused`). From it, at compile time:

```zig
pub inline fn write(comptime name: []const u8, v: u64) void {
    const r = comptime find(name);
    if (r.class != .kernel) @compileError(name ++ " is classified ." ++ @tagName(r.class) ++ ": only the gate writes it");
    asm volatile ("msr " ++ spell(r) ++ ", %[v]" :: [v] "r" (v));   // spell(r) = "S3_0_C2_C0_0"
}
pub const forbidden_msr = blk: { ... every encoding not `kernel`, sorted ... };
export const dodos_scan_msr linksection(".dodos.scan") = forbidden_msr;
```

- Kernel code that writes a gate register does not compile: `regs.zig:29:29: error: TTBR0_EL1 is classified .gate: only the gate writes it`.
- The accessor uses the generic spelling `S<op0>_<op1>_C<n>_C<m>_<op2>`, so it does not depend on the assembler knowing the name or on target features. The named form does: `msr zcr_el1, x0` failed with `expected writable system register or pstate` on the default ARM64 target (SVE not enabled), while the generic form assembles anywhere.
- The encodings computed at compile time match the assembler: `msr ttbr0_el1, x0` assembles to `d5182000` and the computed value is `d5182000`; likewise `TCR_EL1` `d5182040`, `VBAR_EL1` `d518c000`, `ICC_SGI1R_EL1` `d518cba0`, `CNTV_CVAL_EL0` `d51be340`, `SCTLR_EL1` `d5181000` (`llvm-objdump` of the same object). This also checks the six register encodings of my test data, which I wrote from memory.
- The scan list is in the binary itself (596 entries in `.dodos.scan`), so the build-time scanner reads it from the image it scans.

Compile time, fresh cache: 0.24 to 0.25 s with 600 records on each target, 2.36 s with 6,000. The real list is the 598 writable encodings plus about 450 system instructions of the draft's count (part 4.1), so about 1,000 records: under a second. **Parsing `Registers.json` itself at compile time is not viable**: it is 97 MB (draft, part 4.1) against the 6,000 small records that already took 2.4 s, and comptime evaluation has no heap. So: **a build step** (a small host program, pinned with the specification's hash) reduces the JSON to a reviewable, diffable data file; the compiler consumes that. The same step writes the Rust side (below) and the scanner's input, so one reduced file feeds all three.

Rust can enforce the same classification, but only through generated code: a macro emits one type and one accessor per register, and the class is a trait (`regs.rs`; misuse fails with `error[E0599]: no associated function or constant named 'write' found for struct 'TTBR0_EL1'`). Rust cannot build an `asm!` template from data: `concat!("msr ", R::ENC, ", {}")` with an associated const fails with `error: expected a literal`. So in Rust the build step must emit Rust source, register by register; in Zig it emits plain data and the language does the rest. **Zig better**, modestly: both work, Zig's is less machinery.

### 3.3 Layout checks against `abi/`: equal

The build generates `abi_gen.zig` from the real `abi` crate (`gen_abi.rs` links `dodos_abi` and prints `pub const REG_RAX: usize = 3;` and the rest: `REGS_WORDS` 26, `REG_RIP` 0, `REG_RSP` 1, `REG_RFLAGS` 2, `REG_R8` 10, `REG_FS_BASE` 18, `REG_GS_BASE` 19, `RFLAGS_USER_MASK` `0x240DD5`, from `abi/src/x86_64.rs`). The Zig entry code builds its instructions from these with `std.fmt.comptimePrint` and checks them at compile time (every register word distinct and inside the block; `REG_R8 + 7 < REGS_WORDS`). Rust does the same with `const` operands of `asm!` and `core::mem::offset_of!`: the Rust `syscall_entry` of section 6 produced the same bytes as the Zig one (`movq %rsp, %gs:0x8; movq %gs:0x0, %rsp; movq %rcx, (%rsp); movq %r11, 0x10(%rsp); movq %rax, 0x18(%rsp)`). **Equal.**

Two facts on the route kernel.md describes ("a C header is generated and translated for Zig by the build", `architecture/kernel.md:14`): `@cImport` is indeed gone in 0.17.1 (`error: invalid builtin function: '@cImport'`), and `zig translate-c x.h` did not finish within 200 s (it appeared to wait on a package; stopped; **not verified** whether it works offline). For constants and offsets, a Zig file printed by a Rust build step, as above, needs no C at all; I recommend it over the header route. Also: `abi/` fixes the x86-64 register block but not the ARM64 and RISC-V ones (`abi/src/aarch64.rs` is 13 lines, `riscv64.rs` 11, features only); the stubs of section 6 had to invent them.

### 3.4 Choosing the architecture: equal

`switch (builtin.cpu.arch)` on a comptime value: the branches of other architectures are not analysed, so x86-64 assembly inside a `.x86_64` branch never reaches the ARM64 assembler (`entry.zig` compiles for all three with each architecture's asm in its own branch). Rust's `#[cfg(target_arch = "...")]` does the same. **Equal**; neither needs a preprocessor.

One pitfall: comptime has a branch quota. Generating the RISC-V register save loop with `comptimePrint` failed with `evaluation exceeded 17000 backwards branches` until `@setEvalBranchQuota(100_000)` was added in the generating function.

## 4. Packed structs, bit fields and volatile

`/tmp/dodos-zig/feat/packed.zig`, compiled in Debug, ReleaseSafe and ReleaseFast on the three targets.

```zig
pub const X86Pte = packed struct(u64) {
    present: bool, write: bool, user: bool, pwt: bool, pcd: bool, accessed: bool, dirty: bool,
    pat: bool, global: bool, _sw0: u3 = 0, frame: u40, _sw1: u7 = 0, pkey: u4 = 0, no_exec: bool,
};
comptime {
    std.debug.assert(@sizeOf(X86Pte) == 8 and @alignOf(X86Pte) == 8);
    std.debug.assert(@bitOffsetOf(X86Pte, "frame") == 12 and @bitOffsetOf(X86Pte, "no_exec") == 63);
}
pub const Svr = packed struct(u32) { vector: u8, enable: bool, focus_off: bool, _r0: u2 = 0, eoi_suppress: bool, _r1: u19 = 0 };
export fn apic_enable(svr: *volatile Svr) void { svr.enable = true; }
```

What was measured:

- **Bit order.** Fields go from the least significant bit up; the `@bitOffsetOf` assertions hold (also for Sv48: `ppn` at 10, `pbmt` at 61).
- **ABI.** A packed struct with an explicit backing integer crosses `extern` as that integer: `x86_leaf` returns the entry in `rax` (`orq %rcx, %rax; retq`), so Rust sees a `u64`. It may sit inside an `extern struct` (`QueueEntry { head: X86Pte, tail: u64 }` compiles).
- **A field write through a volatile pointer is a read-modify-write of the whole register**: `apic_enable` is `ldr w8,[x0]; orr w8,w8,#0x100; str w8,[x0]` on ARM64, `orl $0x100,(%rdi)` on x86-64. The explicit form (`var v: Svr = @bitCast(svr.*); v.enable = true; svr.* = @bitCast(v);`) compiled to the same code (the linker folded the two functions into one address).
- **The pitfall found: storing a struct literal through a volatile pointer writes field by field.** `st.* = .{ .fault = true, .overflow = false }` on a `*volatile packed struct(u32)` compiled to three loads and three stores on ARM64 and RISC-V (`ldr/orr/str`, `ldr/and/str`, `ldr/and/str`) and three RMW instructions on x86-64. On a write-1-to-clear status register (VT-d fault status, GIC, IOMMU queues) that is a bug: the first write-back can clear bits it only read. The fix is to build the value first: `const v: Status = .{ ... }; st.* = v;` gives one store (`movl $0x1,(%rdi)`; `mov w8,#1; str w8,[x0]`; `li a1,1; sw a1,0(a0)`). A rule for the hardware layer: MMIO registers are written with whole values from a local, never field by field and never by literal through the pointer.
- **A field is not addressable as a normal pointer**: `&e.write` has type `*align(8:1:8) bool` (`error: expected type '*bool', found '*align(8:1:8) bool'`).
- **No arrays in packed structs**: `packed struct(u128) { words: [2]u64 }` fails (`packed structs cannot contain fields of type '[2]u64'`). Wider descriptors (a 512-bit SMMUv3 stream table entry, 128-bit VT-d context entries) are an `extern struct` of packed 64-bit words.
- **Endianness.** The bit order is defined on the backing integer; its byte order in memory is the target's. All three DodOS targets are little-endian; Zig also knows `aarch64_be` and `riscv64be` (its architecture list). Not a concern unless a big-endian target is added.
- **Alignment.** `packed struct(u64)` has the alignment of `u64`; a descriptor at an odd offset in a device table needs `align(1)` pointers.

**Where it pays:** register files and descriptors of the devices the kernel drives (local APIC and x2APIC, IOAPIC redirection entries, VT-d root, context and remapping entries and its queues' descriptors, GICv3 and ITS commands, SMMUv3 stream table entries and commands, APLIC and IMSIC, the RISC-V IOMMU's queues). Rust has no bit fields; it uses shifts, macros or crates (`bitflags`, `tock-registers`), which work but are more text. **Zig better** here. **Where it does not:** CPU table entries inside the Rust gate are raw `u64` words with constant masks from the format description; a Zig packed type cannot be used by Rust code anyway.

## 5. Struct-of-arrays

### 5.1 It works with no allocator

`std.MultiArrayList` keeps three public fields, `bytes`, `len` and `capacity` (`lib/zig/std/multi_array_list.zig:26-28`), and only allocates in `setCapacity` and the functions that grow (`:543-569`). With a static buffer of `capacityInBytes(N)` bytes (`:656`) it runs with no allocator at all (`/tmp/dodos-zig/feat/soa.zig`, compiled on the three targets, `zig test` passes):

```zig
const L = std.MultiArrayList(Thread);
var buf: [L.capacityInBytes(N)]u8 align(@alignOf(u64)) = undefined;
var threads: L = .{ .bytes = &buf, .len = 0, .capacity = N };
// threads.addOneBounded(), set(), slice().items(.prio) need no allocator
```

The fields are public but this use is not documented as an API, so it can break with a Zig release. A hand-made struct of fixed arrays (`state: [N]u8, prio: [N]u8, ...`) does the same with nothing computed at run time, in either language.

### 5.2 Is any data hot enough?

Taking the candidates of the brief one by one, from the contract:

- **Saved contexts**: always saved and restored whole, one thread at a time. SoA would scatter one restore over 26 arrays. AoS is right; the layout is fixed by `abi/` anyway.
- **Capability slots**: 64 bytes, one cache line, fixed by the contract ([The capability slot](../../architecture/kernel-interface.md#the-capability-slot)); a lookup reads one slot. SoA would turn one line into several. AoS is right.
- **Interrupt table**: 192 entries of 64 bytes (`IRQ_TABLE_ENTRIES`, `abi/src/x86_64.rs`), touched one entry per interrupt. AoS.
- **Run queues**: the hot structure of a priority scheduler is a bitmap of non-empty priorities and a list head per priority, neither of which has fields to split. Nothing to gain.
- **The per-chunk words of the gate**: already struct-of-arrays by the contract, for reasons of writers and protection (ownership table, gate words of G4, page classes of G2, `kernel-interface.md:886-888`). This is the only place where the question is real, so I measured it.

Measurement (`/tmp/dodos-zig/bench/soa.rs`, Rust, M5, 16 Mi chunks so each array is 128 MB, well beyond the caches): ownership word plus gate word, as two arrays against interleaved 16-byte pairs, three rounds:

| Access | Two arrays (SoA) | Pairs (AoS) |
|---|---|---|
| Random chunk, dependent chain (latency) | 98 to 119 ns | 95 to 112 ns |
| Random chunk, independent (throughput) | 3.4 to 3.5 ns | 4.8 to 4.9 ns |
| Scan of every ownership word (reclaim, audit) | 0.171 ns per word | 0.300 to 0.304 ns per word |

The two misses of a SoA check overlap (both addresses are known at once), so AoS saves only 3 to 14 % on the dependent chain; SoA is faster on the scan (1.75×, half the bytes) and, unexpectedly, on independent random checks (not explained; perhaps the 16-byte copy). And a mapping call checks the same chunk for up to 512 consecutive entries of one run, so per-entry misses are amortised. **Verdict: the contract's layout is fine; nothing here justifies changing it, and it is Rust data.** `MultiArrayList` is a Zig convenience with no use in the hardware layer, where I found no data that is both large and scanned by field.

## 6. Inline assembly, naked functions, sections, linker script

`/tmp/dodos-zig/feat/entry.zig` holds the three entry paths in one file, chosen by the architecture switch; it compiles on the three targets.

- **x86-64 `syscall` entry**, a `callconv(.naked)` function whose whole body is one asm string built at compile time from `abi_gen.zig` and `@offsetOf(PerCore, ...)`: `swapgs`, park the user `rsp` in the per-core block, point `rsp` at the thread's save area, store `rcx` (user `rip`), `r11` (user `rflags`) and the general registers at their `abi/` words, switch to the core's stack, `call kernel_event` (Rust), then restore from the save area it returns, refuse a non-canonical `rip` before `sysretq` (sysret to a non-canonical address faults in ring 0 on Intel), mask `rflags` with `RFLAGS_USER_MASK`, `swapgs; sysretq`.
- **x86-64 IDT stubs**, 256 of them, generated by a comptime loop that knows which vectors push an error code (8, 10-14, 17, 21, 29, 30) and pushes a 0 for the others: `idt_stubs: pushq $0x0; pushq $0x0; jmp idt_common ...` in its own section.
- **x86-64 AP trampoline** in `.code16`, as global assembly in the Zig file: assembled correctly (`xorw %ax,%ax` is `31 c0` with no operand-size prefix, which is the 16-bit encoding; `llvm-objdump` decodes the section as 64-bit code, hence it prints `xorl`).
- **XSAVES** with the thread's mask in `edx:eax` through register constraints (`[lo] "{eax}"`, `[hi] "{edx}"`).
- **ARM64 vector table**: 16 entries of 128 bytes in a section aligned on 2 KB (`AddressAlignment: 2048` in `llvm-readobj`; VBAR_EL1 bits 10:0 are RES0, confirmed by the verification of the draft, item 20), and an `el0_sync` handler that saves x0-x30 with `stp`, `sp_el0`, `elr_el1`, `spsr_el1`, finds the core's block through `tpidr_el1`, calls `kernel_event`, restores and `eret`s.
- **RISC-V `stvec` handler**, 4-byte aligned: `csrrw t0, sscratch, t0` to reach the save area, save x1-x31, `sepc`, `sstatus`, call `kernel_event` with `scause`, restore, `sret`.

**What must stay in a `.S` file: nothing.** Naked functions, global `asm` blocks, `.pushsection`, `.code16` and `.balign` cover the entry paths, the vector tables and the trampoline. The same is true of Rust: a `#[unsafe(naked)]` function with `naked_asm!` and `const`/`sym` operands produced the same x86-64 bytes as the Zig stub, and `global_asm!` with `.rept 16; .balign 128` produced a 2 KB-aligned ARM64 table of the same size (1,924 bytes, `/tmp/dodos-zig/feat/entry.rs`). **Equal.** Zig's small advantage is generation by ordinary loops over data (`inline for`, `comptimePrint`), where Rust uses assembler macros or `macro_rules!`.

**The context switch** in this kernel has no per-thread kernel stack (kernel.md "Kernel shape"), so it is not a swap of callee-saved registers between stacks: it is "return to a different save area" (the exit half of the stub above, with `kernel_event` returning another thread's area), plus lazy save and restore of the vector state (XSAVES/XRSTORS, SVE and SME, RISC-V V) and the switch of root and tag, which G7 gives to the gate. The first two are Zig; the root switch is the gate's.

**Sections and linker script.** `linksection(".gate.text")` and `@export(..., .{ .section = ".text.entry" })` place code; a linker script decides the layout. Tested end to end (`/tmp/dodos-zig/link`): `zig build-exe -T kernel.ld` linking a Rust `staticlib` (rustc, `-Cpanic=abort -Ccodegen-units=1`) with the Zig entry objects, on the three targets; the ARM64 `vector_table` lands at `0xffffffff80000800`, 2 KB-aligned. One pitfall seen: unreferenced stub sections (the vector table, the IDT stubs, the trampoline) are dropped by `--gc-sections` unless the script `KEEP`s them; the first link lost them silently.

## 7. Safety modes and what crosses to Rust

`/tmp/dodos-zig/feat/safety.zig`, compiled in ReleaseSafe and ReleaseFast on the three targets.

- **One panic path.** The root declares `pub const panic = std.debug.FullPanic(stop);` (`lib/zig/std/debug.zig:103`), and `stop` calls Rust's `kernel_stop(reason, msg, len, return_address)`, which writes the stop record. So a Zig safety check and a Rust panic end in the same place. `FullPanic` formats messages and costs code: the ARM64 object grew from 376 to 3,653 bytes of text in ReleaseSafe. A kernel namespace like `std.debug.simple_panic` (`debug.zig:97`, a fixed handler per check, `debug/simple_panic.zig`) that passes a code instead of formatting is smaller.
- **ReleaseSafe checks** an index and an addition with two compares and two calls to the panic path (`cmp x2, x1; b.hs ...; adds x0, x8, x3; b.hs ...`). `@setRuntimeSafety(false)` in a scope removes both (`ldr x8,[x0,x2,lsl #3]; add x0,x8,x3; ret`). Wrapping arithmetic is explicit (`+%`) and never checked. In ReleaseFast an overflow of `+` is undefined behaviour, unlike Rust, where release builds wrap unless `overflow-checks` is on. Recommendation: the hardware layer in ReleaseSafe, with `@setRuntimeSafety(false)` only in the stubs' few computed paths, after measurement.
- **What crosses `extern`:**
  - An error union does not: `return type 'error{Busy,Invalid}!void' not allowed in function with calling convention 'x86_64_sysv'`. Errors cross as the contract's error codes (`map_one` returns a `u32` with a `switch` over the error set).
  - A slice does not: `parameter of type '[]const u8' not allowed`. Pass pointer and length.
  - An optional pointer does: `?*Thread` is a nullable pointer, which Rust reads as `Option<&Thread>` or `Option<NonNull<Thread>>` (null-pointer optimisation, guaranteed by Rust for those types).
  - A sentinel-terminated pointer `[*:0]const u8` crosses as a C string.
  - A packed struct with a backing integer crosses as the integer (section 4); an `extern struct` as a C struct.
  - Neither side may unwind into the other: Rust with `panic = "abort"`, Zig panics end in `kernel_stop`.

## 8. How the two builds are driven

kernel.md says "`zig build` drives cargo and does the linking" (`architecture/kernel.md:14`). What the tests show:

- **Without cross-language LTO** (the split of section 9), any driver works. Tested: rustc builds the Rust part as a `staticlib` of machine code, Zig compiles its part and links everything with its own linker and the kernel's script, on the three targets (section 6). That is kernel.md's arrangement, and it works as written. Reproducibility comes from pinning both toolchains in the flake (Rust 1.100.0 through `rust-overlay` with the three targets; Zig 0.17.1 as a pinned package), from `Cargo.lock`, and from a `zig build` step that runs `cargo build --locked --offline --target <t>` with fixed flags; the reduced register data and its specification hash are inputs of the build.
- **With cross-language LTO**, Zig cannot be the linker (section 2.2): `zig build` would still orchestrate but would have to call rustc or `rust-lld` for the final link, run LLVM 23's `opt --thinlto-bc` on Zig's bitcode, and keep Zig's `-mcpu` in step with Rust's target features. It also adds a standing constraint: every Rust or Zig upgrade must keep Rust's LLVM at least as new as Zig's. Rust moves to a new LLVM a few times a year; a Zig release with a newer LLVM than the pinned Rust would break the link.

**Recommendation:** keep `zig build` as the driver and the linker, as kernel.md says, and do not use cross-language LTO. Inside Rust, `lto = "fat"` and `codegen-units = 1` keep the Rust kernel optimised as one unit. This is only true if no hot path crosses the boundary, which is what the split below arranges.

## 9. The split I recommend, function by function

The rule: **a function lives on the side of the code that calls it per entry or per object; the boundary is crossed once per event or per operation.** Zig takes what faces devices and the CPU's entry, Rust what reads kernel objects.

| Function | Side | Reason |
|---|---|---|
| Generic walker over format descriptions, all CPU and IOMMU formats | **Rust** | Beside the G3 checks, the model's checks and Kani (draft, part 2.6). comptime gives nothing more here (section 3.1) |
| Gate checks G2-G6, G9, G14 | **Rust** | Same; the security core is proved in one language |
| Write one entry (plain store, or `WRSSQ` on x86-64 with shadow-stack-typed tables), read one entry | **Rust**, `asm!`, gate section | Called per entry; a call costs about 1.5 ns per entry on the M5, LTO inlining is fragile and an explicit section blocks it (section 2.5). One instruction; Rust's `asm!` is equal |
| Invalidate a page, a tag, everything (`INVLPG`/`INVPCID`, `DSB; TLBI; DSB; ISB`, `SFENCE.VMA`), load a root with its tag (`CR3`, `TTBR0_EL1`, `satp`) | **Rust**, `asm!`, gate section | G1 and G7 make them gate code; called from the walker; one to four instructions |
| Page-table start-up (`MAIR_EL1`, `TCR_EL1`, PAT, turning paging on) | **Zig** | Once per boot, part of bring-up; register accessors from the generated data |
| System register accessors and their classification | **Both, from one data file**: Zig accessors at comptime from ZON; the build step also emits a Rust macro for the gate's few registers | The classification is enforced at compile time on both sides (section 3.2); one source |
| Scan lists of G11 | **Build step**, data in the image (`.dodos.scan`) | From the same reduced specification |
| Entry and exit stubs, vector tables, IDT stubs, the gate's window rule on entry | **Zig** | Generated from `abi/` constants with compile-time checks; no `.S` file; one call into Rust per event (section 6) |
| Context switch: restore from another save area; vector state (XSAVES/XRSTORS, SVE, SME, V) | **Zig** | Asm with register constraints and mask handling; per event |
| IPC fast path | **Rust** (moved from Zig) | Reads the same slots, endpoints and threads as the slow path; in Zig it needs C-ABI mirrors of each and forbids Rust types in them, for no Zig strength shown; the stub calls it once per event in either language. The equivalence test against the slow path stays, as a test of two paths in one crate |
| Interrupt controllers (x2APIC, IOAPIC, GICv3 and ITS, APLIC and IMSIC) and timers (TSC deadline, generic timer, Sstc) | **Zig** | Packed register files and commands; called once per operation. Where G10 makes a write gate-only (end of interrupt and timer deadline on x86-64, every IPI on ARM64 and RISC-V), the Zig function sits in the gate section and the Rust gate calls it once per event |
| IOMMU units: register files, command and invalidation queues, fault queues, context and stream table entries, interrupt remapping entries | **Zig**, called by the Rust gate per operation | Packed descriptors are where Zig pays most; the gate checks the value (G9) and calls the write once per attach or invalidation. The IOMMU *tables* are the Rust walker's |
| Starting, parking and fencing cores (INIT/SIPI and the 16-bit trampoline, PSCI, SBI HSM) | **Zig** | Bring-up code and firmware call conventions |
| Boot and platform bring-up, firmware tables the kernel reads (MADT, DMAR, device tree) | **Zig** for bring-up; tables: either | Bring-up is Zig's by D-004; the table parsers are plain parsing with no Zig strength, so they can stay Zig with the rest of bring-up |
| Rings between kernels | **Rust** (moved from Zig) | They are grants (G6) and messages of the inter-kernel protocol, which is Rust; no hardware is touched beyond memory and an IPI, which is the call above |
| Low part of the debugger stub, console | **Zig** | Device-facing |
| Capabilities, objects, scheduling, slow path, inter-kernel protocol, tasks and marks, recovery | **Rust** | Unchanged |

Against the proposed split, three moves: the page-table primitives, the IPC fast path and the rings between kernels go to Rust. Zig keeps the entry, the context switch and the whole device side, and gains the generated register layer. "Entirely in Rust" is right for the gate with its primitives and for the fast path; "entirely in Zig" is right for the IOMMU units, the interrupt controllers and bring-up. The estimate of 1,000 to 2,500 lines of Zig per architecture undercounts what Zig then holds: the draft's per-part estimate (part 8.3) puts the IOMMU at 1,300 to 2,000 lines, interrupt controllers and timers at 1,000 to 1,500, core start and fencing at 350 to 600, firmware tables at 600 to 800, entry and context at 500 to 900 per architecture, so Zig would hold about 4,000 to 6,000 lines per architecture and Rust the rest. An estimate, not a count.

Why not the other consistent choice, the walker and the gate in Zig with comptime formats and the primitives beside them? It would also avoid the per-entry crossing, and comptime suits the formats. But the gate's checks are the part that must be proved and that the model already states in Rust; Kani works on Rust; and the gate reads the ownership words and grants that the Rust core also reads, so its data would need mirroring. The draft recommends Rust for the same reasons (its open point 1); the boundary test adds one more.

## 10. What the contract must say

| Where | Proposed sentence |
|---|---|
| [Language split](../../architecture/kernel-interface.md#language-split) | Zig: boot and platform bring-up; entry and exit stubs, vector tables and the context switch with vector state; interrupt controllers and timers; IOMMU units and their queues; starting, parking and fencing cores; the low part of the debugger stub and the console; system register accessors generated from the pinned specifications. Rust: the gate, its checks, the generic table walker and the table primitives (entry write, invalidation, root load) as inline assembly in the gate's section; the IPC fast and slow paths; the rings between kernels; capabilities, objects, scheduling, the inter-kernel protocol, tasks and marks, recovery |
| Same section, the rule | "No call crosses the boundary per table entry or per object on a hot path; the boundary is crossed once per event (an entry stub calls the common kernel) or once per hardware operation (the gate calls an IOMMU, interrupt-controller or IPI write). The kernel is linked without cross-language LTO." |
| kernel.md, Zig / Rust boundary | Replace the C header route by: "The Rust build prints the constants and offsets the Zig layer needs from `abi/` as a Zig source file; the Zig layer checks them at compile time." |
| kernel.md, the same row | Add: "MMIO registers are written as whole values built in a local, never field by field through a volatile pointer." (section 4) |
| G11 and kernel.md | "The register data reduced from the pinned specification by a build step feeds the Zig accessors, the Rust gate's accessors and the scan lists; a register classified `gate` cannot be written by an accessor outside the gate, enforced at compile time." |
| `abi/` (Values to add) | The ARM64 and RISC-V register blocks (words and offsets), as fixed for x86-64 in `abi/src/x86_64.rs` |

## 11. Not verified

- Timings on x86-64 and RISC-V hardware; all timings are from one Apple M5.
- Why an explicit section prevented the cross-language inlining (section 2.5); the effect is observed, the cause in LLVM's sources was not traced.
- Whether the Zig debug information survives the LLVM 22 to 23 upgrade in an LTO link.
- Whether `zig translate-c` works offline in 0.17.1 (it did not finish in 200 s).
- Why SoA was faster than AoS on independent random checks (section 5.2).
- The line counts of section 9 are an estimate derived from the draft's own estimate, not a count.
- The entry stubs of section 6 compile and link but were not run (no QEMU run was made); the ARM64 and RISC-V save-area layouts in them are mine, not `abi/`'s.
