# Verification of `zig-in-the-hardware-layer.md`

**Reviewer:** gemini-4-hydrogen  
**Date:** 16 November 2026  
**Target reviewed:** [zig-in-the-hardware-layer.md](../research/drafts/zig-in-the-hardware-layer.md) (answering `/private/tmp/claude-501/-Users-btw-Documents-repos/57992ac2-1573-4f43-a999-1ff9c7f97c7a/scratchpad/pass14/ZIG.md`)  
**Toolchains verified against:** Zig `0.17.1` (`/Users/btw/.nix-profile/bin/zig`, LLVM `22.1.8`), Rust `1.100.0` (`rustc` + `rust-lld`, LLVM `23.1.5` via [flake.nix](../../dodos-kernel/flake.nix) with `aarch64-unknown-none` and `riscv64gc-unknown-none-elf` added in an isolated test copy), LLVM `23.1.3` tools (`llvm-objdump`, `llvm-readobj`, `llvm-dwarfdump`, `opt`, `llvm-dis`), benchmarked on Apple M5.

All experiments were written to disk and executed with timeouts in a separate temporary workspace outside the repositories.

---

## Summary Verification Table

| Claim in draft | Verdict | How you know |
|---|---|---|
| §2.1, §2.4: Zig primitives inline into Rust across `x86_64`, `aarch64`, `riscv64` via LTO (`invlpg`, `tlbi`, `sfence.vma` inside `_start`/`map_run`/`unmap_one`) | **CONFIRMED** | Built `prim.zig` + `kmain_sec.rs` / `kmain_gate.rs` for all three targets; disassembled ELFs with `llvm-objdump` showing `invlpg`, `tlbi vae1is`, `sfence.vma` inlined with no call. |
| §2.2: Zig's LLVM 22 refuses `libcore` LLVM 23 bitcode (`Not an int attribute`) | **CONFIRMED** | Extracted `.llvmbc` from `libcore-*.rlib` and passed it to Zig 0.17.1: `error: Not an int attribute (Producer: 'LLVM23.1.5-rust-1.100.0-stable' Reader: 'LLVM 22.1.8')`. `zig ld.lld` also rejects Rust's ThinLTO summary (`Invalid summary version 14. Version should be in the range [1-12]`). |
| §2.3: Five conditions are all strictly necessary for cross-language inlining | **WRONG** (overstated) | Only x86-64 needed `-mcpu=x86_64-mmx-sse-sse2` (without needing `+soft_float`); ARM64 and RISC-V inlined with default Zig CPUs. Symbol internalization is automatic in `rust-lld` static links, not an extra step. Single partition works either via `opt --thinlto-bc` (ThinLTO) or stripping Rust's summary (Full LTO). |
| §2.5: A Zig primitive placed in `linksection(".gate.text")` is not inlined into Rust | **WRONG** (ThinLTO-only, not unavoidable) | True under **ThinLTO** (`not eligible to import` in `.index.dot` because Zig wraps an `internal` sectioned function behind an external `alias`), even when the Rust caller is also in `.gate.text`. **False under Full LTO**: stripping Rust's ThinLTO summary with `opt` inlines Zig's `.gate.text` function into Rust's `#[unsafe(link_section = ".gate.text")]` caller on all three targets. |
| §2.5, §11: Whether Zig DWARF debug info survives LLVM 22 → 23 LTO upgrade | **CONFIRMED** (now verified: it survives) | `llvm-dwarfdump --debug-info` on `kmain_gate-full.elf` shows Zig's `DW_TAG_compile_unit` (`DW_AT_name ("prim_sec")`, `DW_AT_language (DW_LANG_C99)`) and `.debug_line` survived the LTO link. |
| §2.5: Per-entry call vs inline store (`0.48` vs `2.18 ns` plain; `0.95–0.99` vs `1.57 ns` with G3 check) | **CONFIRMED** (same ~1–1.6 ns/entry penalty) | Re-ran on M5: plain `0.508–0.525 ns` inline vs `2.090–2.117 ns` call; read-only G3 `0.700–0.744 ns` vs `1.527–1.639 ns`; write-back G3 (`gate[idx] += 1`) `0.952–0.969 ns` vs `2.150–2.230 ns`. |
| §2.5, §11: Per-entry call / inline timings on x86-64 and RISC-V hardware | **NOT VERIFIED** | Only Apple M5 hardware is present in this environment. |
| §3.1: `pt_format.zig` compiles on 3 targets, passes encoding tests, and matches Rust const-generics codegen ("Equal") | **CONFIRMED** (with fairness caveat) | Compiles on all 3 targets; `zig test` passes all 5 encoding checks. Instruction counts match closely (ARM64 `18` vs `18`, `4` vs `4`; RV64 `44` vs `43`, `6` vs `6`). **Caveat**: Rust's `const CHECK: () = assert!(...)` silently skips evaluation unless explicitly referenced; Zig checks `comptime` blocks eagerly. |
| §3.2: ZON-driven registers enforce `.gate` vs `.kernel` at compile time; `S3_0_...` beats named `zcr_el1`; encodings match `llvm-objdump` | **CONFIRMED** | Tested exact compile error on `TTBR0_EL1`, `msr zcr_el1, x0` failure vs generic `S3_0_C1_C2_0` success, and all 6 encodings (`d5182000`, `d5182040`, `d518c000`, `d518cba0`, `d51be340`, `d5181000`). Rust `concat!("msr ", R::ENC, ", {}")` fails with `error: expected a literal`. |
| §3.3: `@cImport` is gone in Zig 0.17.1; Rust + Zig `syscall_entry` emit identical bytes | **CONFIRMED** | `cimport.zig` yields `error: invalid builtin function: '@cImport'`. Rust `#[unsafe(naked)]` `syscall_entry` and `vector_table` match Zig byte-for-byte (`65 48 89 24 25 ...`, 1,924-byte 2 KB-aligned `.text.vectors`). |
| §3.3, §11: `zig translate-c x.h` hangs (>200 s, waiting on a package) / offline status unverified | **WRONG** | `zig translate-c -target x86_64-freestanding test.h` finished offline in **0.041 s**; `zig build` with `b.addTranslateC` finished offline in **4.51 s** once the build runner was cached (first cold `zig build` compiled `configurer` in **70.77 s**, which likely caused timeout confusion). |
| §3.4: `switch (builtin.cpu.arch)` avoids cross-arch analysis; `comptimePrint` loop hits 17,000 backwards-branch quota | **CONFIRMED** (quota figure differs by path) | Cross-arch branches are skipped. Notice `asm volatile (comptime blk: ...)` in §6/snippet fails in 0.17.1 (`redundant comptime keyword`), and a 256-entry IDT `comptimePrint` loop hit `evaluation exceeded 35000 backwards branches` in `std/Io/Writer.zig:1642`, whereas 31-entry `stvec` save passed without `@setEvalBranchQuota`. |
| §4: Volatile packed struct store literal writes field-by-field (3 RMWs vs 1 store for local) | **CONFIRMED** | Inspected LLVM IR (`load volatile`/`store volatile`) and disassembly on all 3 targets: `st.* = .{ ... }` emits 3 volatile RMW pairs; `const v = ...; st.* = v` emits 1 volatile store; `apic_enable` and `apic_enable_explicit` fold to one address. |
| §5.1: `std.MultiArrayList` works on a static buffer with no allocator | **CONFIRMED** (with alignment bug in snippet) | Passes `zig test` for `u64`-aligned fields, **but** the snippet's `align(@alignOf(u64))` panics at `multi_array_list.zig:99` (`incorrect alignment`) if any struct field has alignment `> 8` (e.g. `align(16)`). |
| §5.2: SoA vs AoS (`0.171` vs `0.300–0.304 ns` scan; `98–119` vs `95–112 ns` dependent; `3.4–3.5` vs `4.8–4.9 ns` independent throughput) | **WRONG** on throughput; **CONFIRMED** on scan & latency | Scan (`0.145–0.156` vs `0.294–0.299 ns`, ~1.9–2.0×) and dependent chain (`106.0–127.7` vs `99.5–111.5 ns`) match. **Contradiction on independent random throughput**: both standard (`7.85–12.61` vs `4.54–5.27 ns`) and 4× unrolled (`8.80–9.90` vs `4.84–5.06 ns`) show **AoS is ~1.8–2.0× faster than SoA**, not slower. |
| §6: No `.S` file needed; `.code16`, `AddressAlignment: 2048`, `--gc-sections` drops vector table without `KEEP` | **CONFIRMED** | Verified `31 c0` (`xorw %ax,%ax`), 2,048-aligned `vector_table` at `0xffffffff80000800` with `KEEP`, and complete removal without `KEEP` when linking Rust `staticlib` via `zig build-exe -T kernel.ld`. |
| §7: `FullPanic` bloat (`376 → 3,653 B`), `ReleaseSafe` double check vs `@setRuntimeSafety(false)`, `extern` ABI errors (`!void`, `[]const u8`) | **CONFIRMED** (but `simple_panic` fails!) | ARM64 text grew `88 → 3,593 B` with `FullPanic`; `checked_add` emits `cmp/b.hs` + `adds/b.hs`, removed by `@setRuntimeSafety(false)`. **Error in §7**: `std.debug.simple_panic` fails to compile on `*-freestanding` (`std/Io/Threaded.zig:2104`, `std/posix.zig:94`) because it calls `lockStderr`. |
| §6, §11: Entry stubs run under QEMU | **NOT VERIFIED** | Compiled and linked only; not booted under QEMU. |
| §9: Line-count shift (`4,000–6,000` Zig lines/arch vs `1,000–2,500`) | **CONFIRMED** (arithmetic matches prior draft) | Summing [architecture-boundary.md](../research/drafts/architecture-boundary.md) §8.3 rows assigned to Zig gives `4,200` (RV64) to `5,800` (ARM64), excluding `.gate.text` and G10 shares; the draft omitted the TCB, debugging, and dual-language `.gate.text` costs. |

---

## Detailed Findings

### 1. Recompiling the Draft Snippets Across Three Targets

Every runnable snippet in the draft was reconstructed, written to disk, and compiled with `-OReleaseFast` (and `-OReleaseSafe` / `Debug` where applicable) for `x86_64-freestanding`, `aarch64-freestanding`, and `riscv64-freestanding`.

- **Confirmed cleanly across all three targets:** `prim.zig`, `pt_format.zig` (plus `zig test` on all five format assertions), `packed.zig`, `soa.zig` (plus `zig test`), `safety_full.zig` (ARM64 `.text` grew from `88 B` in ReleaseFast to `3,593 B` in ReleaseSafe with `FullPanic`; `checked_add` emitted `cmp x2, x1; b.hs ...` and `adds x0, x8, x3; b.hs ...`, both eliminated by `@setRuntimeSafety(false)`), and the `extern` rejection errors (`error{Busy,Invalid}!void` and `[]const u8` rejected on `x86_64_sysv`, `@cImport` rejected as `invalid builtin function`).
- **Discrepancies and snippet defects found:**
  1. **`regs.zig` is ARM64-only when instantiated:** `regs.zig` compiles for non-ARM64 only if `write()` is never called; instantiating `write("TPIDR_EL1", v)` emits `msr S3_1_C13_C0_4, ...`, which is ARM64-specific. On ARM64, the draft's exact findings hold: `msr zcr_el1, x0` fails (`expected writable system register or pstate`), `msr S3_0_C1_C2_0, x0` succeeds, and all six computed encodings (`TTBR0_EL1` `0xd5182000`, `TCR_EL1` `0xd5182040`, `VBAR_EL1` `0xd518c000`, `ICC_SGI1R_EL1` `0xd518cba0`, `CNTV_CVAL_EL0` `0xd51be340`, `SCTLR_EL1` `0xd5181000`) match `llvm-objdump`.
  2. **`asm volatile (comptime blk: ...)` syntax in Zig 0.17.1:** Putting `comptime` directly before `blk:` inside `asm volatile (...)` fails in Zig 0.17.1 with `error: redundant comptime keyword in already comptime scope` because the `asm` template argument is already a comptime expression. Removing `comptime` (`asm volatile (blk: { ... })`) compiles cleanly.
  3. **Comptime branch quota (`17000` vs `35000`):** A 31-register `sd x{d}, {d}(t0)` save loop compiled *without* `@setEvalBranchQuota`. A 256-vector IDT stub generator (`for (0..256)` calling `std.fmt.comptimePrint`) failed with `error: evaluation exceeded 35000 backwards branches` in `std/Io/Writer.zig:1642` (called from `std/fmt.zig:641`) until `@setEvalBranchQuota` was raised. The exact quota depends on loop size and helper calls (a combined save+restore loop or larger template crosses the threshold), so `@setEvalBranchQuota` is indeed needed for large asm generation.
  4. **`std.debug.simple_panic` does not compile on `*-freestanding`:** §7 states *"A kernel namespace like `std.debug.simple_panic` (`debug.zig:97`, a fixed handler per check, `debug/simple_panic.zig`) that passes a code instead of formatting is smaller."* Compiling `pub const panic = std.debug.simple_panic;` in `ReleaseSafe` for `aarch64-freestanding` fails inside Zig's stdlib (`std/Io/Threaded.zig:2104`: `struct 'posix.system__struct_0' has no member named 'getrandom'`; `std/posix.zig:94`: `no member named 'IOV_MAX'`) because `simple_panic.call` calls `std.debug.lockStderr(&.{})`. Freestanding code must either write a custom zero-format panic namespace modeled on `std.debug.no_panic` (`std/debug/no_panic.zig`) or route to `kernel_stop`.
  5. **`zig translate-c` works offline and fast:** The draft claimed `zig translate-c x.h` timed out after `200 s` ("appeared to wait on a package"). Testing directly: `zig translate-c -target x86_64-freestanding test.h` completed offline in **0.041 s** (emitting valid Zig declarations), and `zig build` using `b.addTranslateC` compiled `check_abi.zig` against `abi.h` offline in **4.51 s** once the build runner was cached. What actually takes long is the *very first* cold `zig build` invocation on a clean cache, which took **70.77 s** (`62.03 s` user CPU) compiling `std.Build`'s `configurer` binary via LLVM—no network or package fetch occurred.

### 2. Cross-Language Inlining From Scratch

Rebuilt from scratch with `prim.zig` / `prim_sec.zig` (Zig `0.17.1`) and `kmain_sec.rs` / `kmain_gate.rs` (Rust `1.100.0`, `panic=abort`, `codegen-units=1`), tested under both `rust-lld` directly and `rustc -Clinker-plugin-lto`.

#### Audit of the Draft's Five Conditions

| Draft's condition | Actually required? | Verification result |
|---|---|---|
| 1. Rust LLVM >= Zig LLVM | **Yes** (for LTO) | `zig ld.lld` (LLVM 22.1.8) rejects Rust bitcode with `Invalid summary version 14. Version should be in the range [1-12]`, and Zig's bitcode reader rejects `libcore` `.llvmbc` with `Not an int attribute (Producer: 'LLVM23.1.5-rust-1.100.0-stable' Reader: 'LLVM 22.1.8')`. |
| 2. Rust's linker runs LTO | **Yes** (for LTO) | `rust-lld` / `rustc -Clinker-plugin-lto` (LLVM 23) loads Zig's LLVM 22 bitcode cleanly on all three targets. |
| 3. Single partition via `opt --thinlto-bc` | **Half true** (two ways, both need `opt`) | `zig build-obj -flto` and `-flto=thin` emit bitcode *without* a ThinLTO summary, whereas `rustc` (`--emit=llvm-bc`, `-Clto=fat`, `-Clinker-plugin-lto`) always writes a ThinLTO summary, and `rust-lld --lto=full` fails (`unified LTO compilation must use compatible bitcode modules`). Either `opt --thinlto-bc` upgrades Zig to ThinLTO, or `opt kmain.bc -o kmain_nosum.bc` strips Rust's summary for Full LTO. Both require LLVM 23's `opt` (available via `rustup component add llvm-tools`, though absent from [flake.nix](../../dodos-kernel/flake.nix)'s default `rust-default`). |
| 4. CPU features matched by hand, per target | **Overstated** | Only `x86_64` failed with defaults (`+sse,+sse2,+mmx` vs `-mmx,-sse,-sse2`), and `-mcpu=x86_64-mmx-sse-sse2` alone fixed it—`+soft_float` was **not** required for inlining. `aarch64` and `riscv64` inlined with Zig's default target CPUs. |
| 5. Symbols internalized | **Not an extra step** | In a static binary link, `rust-lld` marks exported/alias symbols `pl` automatically; `opt -passes=internalize` is only needed when testing with `opt` outside the linker. |

#### Section Placement (`linksection(".gate.text")`) and DWARF Survival

- **The draft's central LTO argument against Zig primitives in `.gate.text` is false under Full LTO:**
  - Under **ThinLTO** (`opt --thinlto-bc`), `prim_sec.pt_invalidate_page` placed in `linksection(".gate.text")` is indeed **not inlined**—even when the Rust caller `gate_unmap` is *also* marked `#[unsafe(link_section = ".gate.text")]`. Inspecting `kmain_gate-thin2.elf.index.dot` reveals the exact cause: Zig emits an `internal` function with explicit `section ".gate.text"` behind an `@pt_invalidate_page = alias ...`, and ThinLTO flags `prim_sec.pt_invalidate_page` as `not eligible to import` because ThinLTO refuses to cross-module-import local symbols tied to explicit sections.
  - Under **Full LTO** (stripping Rust's ThinLTO summary with `opt`), all bitcode is merged into one module before inlining. When Rust `gate_unmap` is in `#[unsafe(link_section = ".gate.text")]` and `pt_invalidate_page` is in `linksection(".gate.text")`, **`pt_invalidate_page` was inlined directly into `gate_unmap` inside `.gate.text` on all three architectures** (`x86_64`, `aarch64`, `riscv64`). On `aarch64`, `.gate.text` holds `gate_unmap` with `dsb ishst; tlbi vae1is, x8; dsb ish; isb; ret` inline. (Conversely, if the Rust caller is in `.text`, Full LTO inlines `tlbi`/`invlpg`/`sfence.vma` into `.text`, violating G11 unless the caller is also in `.gate.text`.)
- **DWARF survival ("not verified" in §2.5 & §11):** `llvm-dwarfdump --debug-info` on `kmain_gate-full.elf` shows Zig's `DW_TAG_compile_unit` (`DW_AT_name ("prim_sec")`, `DW_AT_language (DW_LANG_C99)`) and line tables survived LLVM 22 → 23 LTO merging.

Despite Full LTO technically working, we **still agree** with avoiding cross-language LTO in production: requiring LLVM 23 `opt` outside `zig build` and pinning `Rust LLVM >= Zig LLVM` across upgrades is brittle for 1–4 instruction primitives that Rust `asm!` writes natively.

### 3. Call vs Inline and SoA vs AoS Benchmarks (Apple M5)

All measurements ran natively in Rust `-O` on Apple M5 (`16 Mi` chunks = `128 MB` per `u64` array, `256 MB` for interleaved `Pair { owner: u64, gate: u64 }`).

#### Per-Entry Call vs Inline Store (512 entries/run, 200,000 runs/round)

| Variant | Draft (M5) | Verification (M5) | Verdict |
|---|---|---|---|
| Plain store (inline vs Zig call) | `0.48` vs `2.18 ns` (`+1.70 ns`) | `0.508–0.525` vs `2.090–2.117 ns` (`+1.58 ns`) | **CONFIRMED** |
| Read-only G3 check (inline vs Zig call) | — | `0.700–0.744` vs `1.527–1.639 ns` (`+0.85 ns`) | Confirms penalty |
| G3 check + `gate[idx] += 1` (inline vs Zig call) | `0.95–0.99` vs `1.57 ns` (`+0.60 ns`) | `0.952–0.969` vs `2.150–2.230 ns` (`+1.23 ns`) | **CONFIRMED** (inline matches; call overhead larger here) |

#### SoA (`owners`, `gates`) vs AoS (`[Pair; 16 Mi]`)

| Access pattern | Draft (M5) | Verification (M5, 3 rounds) | Verdict |
|---|---|---|---|
| Linear scan of `owners` only (`16 Mi` entries) | `0.171` vs `0.300–0.304 ns` (SoA `1.75×` faster) | `0.145–0.156` vs `0.294–0.299 ns` (SoA `1.9–2.0×` faster) | **CONFIRMED** |
| Random chunk, dependent chain (latency) | `98–119` vs `95–112 ns` (AoS `3–14%` faster) | `106.0–127.7` vs `99.5–111.5 ns` (AoS `6–13%` faster) | **CONFIRMED** |
| Random chunk, independent (throughput, 1-wide) | `3.4–3.5` vs `4.8–4.9 ns` (**SoA faster**) | `7.85–12.61` vs `4.54–5.27 ns` (**AoS `1.7–2.5×` faster**) | **WRONG** |
| Random chunk, independent (throughput, 4× unrolled) | — | `8.80–9.90` vs `4.84–5.06 ns` (**AoS `1.74–1.99×` faster**) | **Contradicts draft** |

*(Note: an initial unrolled test where `black_box` wrapped only the return value allowed LLVM to hoist the pure loops in rounds 2–3; wrapping all slice and seed inputs fixed that and produced consistent `8.80–9.90` vs `4.84–5.06 ns` across all 3 rounds.)*

Why the draft's independent throughput result is wrong: reading both `owner` and `gate` at a random index out of `128 MB` arrays touches **two** 4 KB/16 KB pages (2 DTLB entries and 2 cache lines) in SoA versus **one** 16-byte aligned `Pair` (1 DTLB entry, 1 cache line) in AoS. AoS consistently wins by ~1.8–2.0× when both fields are read together at random indices. That reinforces the draft's practical conclusion not to refactor, though for the opposite reason on throughput: the contract keeps `ownership` and `gate` separate for writer/isolation reasons (G1/G4), and mapping runs amortize over up to 512 entries per chunk while whole-table reclaim scans only `ownership` (`1.9–2.0×` faster in SoA).

### 4. Volatile Packed Struct Store Trap (§4)

Compiled `packed.zig` with `-femit-llvm-ir` and `-OReleaseFast` across `x86_64-freestanding`, `aarch64-freestanding`, and `riscv64-freestanding`. Reading the generated LLVM IR and disassembly **100% confirms** the draft:

- `st.* = .{ .fault = true, .overflow = false };` emits **three consecutive volatile load + store pairs** in LLVM IR (`%1 = load volatile i32 ... store volatile i32`, `%3 = load volatile i32 ... store volatile i32`, `%5 = load volatile i32 ... store volatile i32`) on all three targets—one RMW per field (`fault`, `overflow`, and implicit default `_r0: u30 = 0`). On `aarch64`, `status_literal` compiles to `ldr/orr/str`, `ldr/and/str`, `ldr/and/str`; on `x86_64` to three RMW ops; on `riscv64` to three `lw/ori|andi/sw` sequences.
- `const v: Status = .{ ... }; st.* = v;` emits a single `store volatile i32 1` (`mov w8, #1; str w8, [x0]` on ARM64).
- Single-field `svr.enable = true` and explicit `@bitCast` RMW (`apic_enable` and `apic_enable_explicit`) compile identically and fold to the same address (`0x34`) on ARM64, x86-64, and RISC-V.

### 5. Fairness of `comptime` vs Rust Const Generics (§3.1)

Reimplemented `pt_format.zig` in Rust (`s5_comptime/pt_format.rs`) using a `Format` trait with associated constants/functions, `Sv<const L: u32>`, `Arm<const G: u64, const L: u32>`, and `Walker<F: Format>`, compiled with `-O` for `aarch64-unknown-none` and `riscv64gc-unknown-none-elf`.

| Function | Draft (Zig / Rust) | Verification (Zig / Rust) |
|---|---|---|
| `arm16k_entry_for` (ARM64) | `18` / `18` | `18` / `18` |
| `arm16k_leaf` (ARM64) | `9` / `8` | `4` / `4` |
| `sv48_entry_for` (RISC-V) | `44` / `43` | `44` / `43` |
| `sv48_leaf` (RISC-V) | `6` / `6` | `6` / `6` |
| `arm16k_entry_for` (RISC-V) | — | `31` / `29` |

*(The `arm16k_leaf` `4` vs `4` difference from the draft's `9` vs `8` reflects passing/omitting frame pointer and `Perm` struct-by-value vs boolean arguments.)*

**Is "Equal" fair?**
- **Fair for runtime codegen:** Both languages unroll walks and fold masks/shifts identically (`18/18`, `44/43`, `6/6`). Calling the Rust side "weak" would be wrong: our idiomatic Rust implementation hit the exact same instruction counts.
- **Unfairly understated for compile-time validation ergonomics:**
  1. **Silent non-evaluation of `const CHECK: ()` in Rust:** In `lazy_check.rs`, defining `trait Format { const CHECK: () = assert!(Self::LEVELS <= 5); }` with `struct Bad; impl Format for Bad { const LEVELS: u32 = 99; }` **compiled without error** (emitting only a dead-code warning) because Rust associated constants are lazily evaluated only where explicitly referenced (`let _ = F::CHECK;` in every entry point). Zig's `comptime` block inside `Format(d)` runs unconditionally whenever a format type is constructed.
  2. **Heterogeneous iteration & data:** Iterating over `[X86_4, Arm16K, Sv48]` for unit tests or format dispatch requires `inline for` in Zig vs `macro_rules!` in Rust.

### 6. Overlooked Zig Strengths and Uncounted Costs of the Draft's Split

#### Zig Strengths Dismissed Too Fast or Missed
1. **Comptime-checked layouts via C headers (`translate-c` / `b.addTranslateC`):** The draft dismissed `zig translate-c` because of an erroneous >200 s timeout and fell back to printing scalar constants into `abi_gen.zig`. While printing `abi_gen.zig` is cleaner for plain integer constants (`REG_RAX`), we verified `zig translate-c` (`0.041 s`) and `b.addTranslateC` (`4.51 s` cached) both work offline in Zig 0.17.1 and allow Zig to `@compileError`-check `@sizeOf` and `@offsetOf` of full `repr(C)` shared structs (e.g., hand-over blocks or device/MMIO headers) directly against C headers emitted from `abi`.
2. **`@Vector`:** Unmentioned in the draft. Testing `@Vector(4, u64)` across targets showed an important trade-off: on `x86_64 -mmx-sse-sse2` and `riscv64`, `@Vector(4, u64)` OR-reduction cleanly scalarizes into unrolled 64-bit register loops (`orq`, `ld`/`or`) without breaking `-mno-sse`; on default `aarch64-freestanding`, however, it emits NEON instructions (`movi v0.2d`, `ldp q2, q3`, `orr v0.16b`). In a kernel using lazy vector-register switching, NEON in kernel code silently corrupts user `v0..v31` state unless `-mcpu=generic-fp_armv8-neon` is passed. Thus `@Vector` is useful for SIMD-capable userland or host checks, not kernel trap paths on ARM64 without disabling NEON.
3. **`comptime` architecture interfaces (`arch_iface.zig`):** Beyond `switch (builtin.cpu.arch)`, Zig can validate a structural `ArchSpec` + typed function-pointer contract (`checkArch(Active)`) at compile time across all three freestanding targets and a host simulation backend without trait boilerplate or dynamic dispatch.
4. **`std.MultiArrayList` on fixed buffers:** The draft's §5.1 snippet contains a latent alignment bug: `var buf: [L.capacityInBytes(N)]u8 align(@alignOf(u64)) = undefined;` panics at runtime (`thread ... panic: incorrect alignment` at `std/multi_array_list.zig:99`) if `T` contains any field aligned to `> 8` bytes (verified with an `align(16)` field in `mal_align_bad.zig`; buffer alignment must be `@alignOf(T)` or `sizes.big_align`). Even then, hand-written parallel fixed arrays are less fragile than relying on `MultiArrayList`'s undocumented public `.bytes`/`.len`/`.capacity` fields.
5. **Build-system cross compilation caveats:** `zig build-exe -T kernel.ld` links Rust `staticlib`s cleanly across all three ELF targets, and `zig build-exe` builds UEFI PE32+ binaries out of the box for `x86_64-uefi` and `aarch64-uefi`, **but** `riscv64-uefi` fails in Zig 0.17.1 (`error: failed to open output binary: UnsupportedCoffArchitecture`)—relevant if the [architecture-boundary.md](../research/drafts/architecture-boundary.md) UEFI stub ever looked to Zig. Also, even with `-fno-unwind-tables`, Zig's ELF link keeps a `48 B` `.eh_frame` section unless the linker script discards it (`/DISCARD/ : { *(.eh_frame*) }`), and cold `zig build` compilation of `configurer` costs ~`71 s` on first run.

#### Uncounted Costs of the Draft's Recommended Split
1. **Two toolchains in the Trusted Computing Base (TCB):** Both `rustc` (LLVM `23.1.5`) and `zig` (LLVM `22.1.8`) emit ring-0 / EL1(EL2) / S-mode machine code. Every compiler bug, ABI mismatch (`Frame-pointer`, red-zone, `soft-float`/NEON defaults), and pin coordination stays in the TCB.
2. **Debugging across the boundary:** Even without LTO, the final ELF mixes LLVM 23 Rust CUs and LLVM 22 Zig CUs (`DW_LANG_C99`), with mismatched stack-frame defaults (`"frame-pointer"="all"` in Zig ReleaseFast freestanding vs Rust) and C-ABI symbol boundaries.
3. **Unwinding, panics, and safety inside `.gate.text`:**
   - Zig `ReleaseFast` turns integer overflow into UB (unlike Rust release wrapping), while `ReleaseSafe` (`FullPanic`) expands small functions by ~40× (`88 → 3,593 B`) and `std.debug.simple_panic` fails to build on freestanding.
   - **Critical safety flaw in §9's G10 placement:** §9 places G10 interrupt-controller/timer/IPI writes in Zig *inside `.gate.text`* called by the Rust gate. On gate mechanisms with an open window (CR3/TTBR1/satp), a Zig `ReleaseSafe` bounds/overflow panic inside `.gate.text` would jump out to Rust `kernel_stop` while the gate's translation window is still open, violating the gate window invariant unless every Zig gate function disables safety checks (`ReleaseFast` / `@setRuntimeSafety(false)`).
4. **4,000–6,000 lines of Zig per architecture instead of 1,000–2,500—and a split gate:** Keeping IOMMUs (`1,300–2,000` lines/arch), interrupt controllers (`1,000–1,500`), firmware tables (`600–800`), core start/fence (`350–600`), and entry/context (`500–900`) in Zig inflates Zig to `4,200–5,800` lines/arch—**more than double** the original `1,000–2,500` budget—while still splitting `.gate.text` (G9 IOMMU context/remapping writes and G10 EOI/timer/IPI writes) across two languages and blocking single-language Kani/Verus verification of the gate.

---

## Function-by-Function Split: Where I Agree and Where I Differ

Overall rule: **Rust owns 100% of `.gate.text` (including G9/G10 privileged writes and hardware checks), all table/capability/IPC/protocol logic, and pure data-structure parsing (ACPI/DT).** Zig owns only **boot bring-up, naked trap/entry/vector stubs, vector-register context save/restore, and pure non-gate packed-register device backends** (or stays strictly in the ~1,500–2,500 line/arch low-level hardware envelope).

| Function | Draft (§9) | My recommendation | Agree / Differ & why |
|---|---|---|---|
| Generic page-table walker (CPU & IOMMU formats) | **Rust** | **Rust** | **Agree.** Same codegen as `comptime`, stays beside G3 checks and Kani proofs. |
| Gate checks G2–G6, G9, G14 | **Rust** | **Rust** | **Agree.** Single language for the verified security invariant. |
| Page-table primitives (entry write/`WRSSQ`, read, `invlpg`/`tlbi`/`sfence.vma`, root load) | **Rust** (`asm!`, `.gate.text`) | **Rust** (`asm!`, `.gate.text`) | **Agree.** Removes per-entry boundary crossing and fragile cross-language LTO. |
| **G10 gate-only writes** (x2APIC EOI, timer deadline, IPIs / `ICC_SGI1R_EL1`, ACLINT/IMSIC/APLIC gate stores, port I/O, PSCI/SBI allow-list calls) | **Zig** inside `.gate.text`, called by Rust gate | **Rust** (`asm!` / volatile write, `.gate.text`) | **Differ.** Keeps `.gate.text` 100% Rust (single proof target for Kani, zero Zig `ReleaseSafe` panic-out-of-window hazard, no cross-language `gate` boundary). These are 1–5 line register/MMIO/SMC/ECALL writes. |
| **G9 IOMMU gate operations** (context/stream-table/interrupt-remapping entry writes, gate-mapped IOMMU invalidation & wait) | **Zig**, called by Rust gate | **Rust** in `.gate.text` (using Rust bitfield/newtype structs or generated masks) | **Differ.** Context/remapping entries are checked by G9 inside the gate; keeping the write in Rust keeps the entire gate boundary single-language, avoids duplicate descriptor structs across FFI, and shrinks Zig's line count by ~1,300–2,000 lines/arch. |
| IOMMU non-gate queue/init/fault-ring bring-up & descriptors | **Zig** | **Zig** (init/descriptors) or **Rust** (if G9 moved) | **Partially differ.** Once G9 writes sit in Rust `.gate.text`, keeping only non-gate IOMMU init in Zig adds FFI boilerplate for little gain; better to keep all runtime IOMMU queue ops in Rust alongside G9, leaving only boot-time IOMMU discovery/enable or raw packed descriptor tests in Zig (or keeping all IOMMU in Rust). |
| Interrupt controller & timer *non-gate* setup (APIC/IOAPIC/GICv3/ITS/APLIC init, IRQ line routing) | **Zig** | **Zig** (or Rust if unifying drivers) | **Agree** with caution: packed MMIO registers and ITS/GIC command queues are where Zig `packed struct` genuinely shines—provided writes use whole-value locals (never volatile struct literals) and G10 EOI/IPI/timer gate ops stay Rust. |
| Page-table start-up (`MAIR_EL1`, `TCR_EL1`, PAT, enabling paging) | **Zig** | **Zig** | **Agree.** Boot-only, before the gate's protection is active. |
| System register accessors & G11 scan list (`.dodos.scan`) | **Both** from reduced data (Zig ZON + Rust macro) | **Build step -> Rust gate macros + `.dodos.scan`** (plus Zig accessors if Zig keeps non-gate drivers) | **Agree**, conditioned on non-gate Zig drivers; note the build step also needs Intel XED / RISC-V UDB inputs, not only Arm `Registers.json`. |
| Entry/exit stubs, vector tables, IDT stubs, gate window entry stub | **Zig** | **Zig** (using `abi_gen.zig` + `b.addTranslateC` struct checks) | **Agree** (though Rust `naked_asm!` emits identical bytes, keeping stubs in Zig honors D-004 cleanly with one call per event into Rust). |
| Context switch: return to save area + vector state (`XSAVES`/`XRSTORS`, SVE, SME, RVV) | **Zig** | **Zig** (with `-fp_armv8-neon` / `-mmx-sse-sse2` enforced on kernel CUs) | **Agree.** Fits Zig's `abi_gen` + asm register constraints cleanly. |
| IPC fast path | **Rust** (moved from Zig) | **Rust** | **Agree.** Avoids C-ABI mirroring of capability slots/endpoints/threads; stub still makes one call per event. |
| Core start, park, and fence (INIT/SIPI, 16-bit trampoline, PSCI, SBI HSM) | **Zig** | **Zig** (non-gate park/trampoline/bring-up; G10 gate-checked `CPU_ON`/fence IPIs in **Rust**) | **Partially differ.** Keep the 16-bit `.code16` AP trampoline and local park/bring-up stubs in Zig; keep runtime G10-checked `core_start`/`fence` firmware calls inside the Rust gate. |
| **Firmware table parsing** (`MADT`, `DMAR`, `GICC`, `RHCT`, Device Tree) | **Zig** ("or either") | **Rust** | **Differ.** Pure byte-slice parsing (`600–800` lines/arch) has zero Zig advantage, benefits from Rust bounds-checked slices, and avoids C-ABI hand-off structs between Zig boot code and Rust core. |
| Rings between kernels | **Rust** (moved from Zig) | **Rust** | **Agree.** Grant/protocol logic is Rust. |
| Low part of debugger stub, early console | **Zig** | **Zig** | **Agree.** Small device-facing UART/16550/MMIO code; one call per log/debug event. |
| Capabilities, objects, scheduling, slow path, inter-kernel protocol, tasks/marks, recovery | **Rust** | **Rust** | **Agree.** |
