# GPU

Statuses are defined in the [README](../README.md#status-legend).

## GPU for applications

**Aligned.**

- WebGPU is the only GPU API exposed to components, through `wasi:webgpu` (a WASI proposal in phase 2). Wasm applications reach the GPU this way, without going through LibWeb.
- Implementation by wgpu (Rust), in a GPU service separate from the compositor. gpui and Rune already rest on wgpu, so there is a single stack to port.
- Dawn is set aside unless its client-server protocol is needed.
- `wgpu-native` does not yet implement the stable `webgpu.h` header: the Rust API is used.
- Pipelines are cached by hash.
- WebGPU remains to be added to LibWeb (see [web.md](web.md)).

## NVIDIA port

**Decided; mechanism verified 13 November 2026.**

- The OS-independent core of NVIDIA's open modules (the `src/` folder) is adapted by the project's own glue, without the Linux layer `kernel-open`. The NVIDIA driver does not go through the [Linux emulation layer](drivers.md#linux-driver-emulation-layer).
- The kernel side comes from NVIDIA's own repository (`NVIDIA/open-gpu-kernel-modules`), not from the Haiku port; the Haiku glue (`X547/nvidia-haiku`) is only an example to read.
- Vulkan by NVK, starting from the Mesa fork of the Haiku port (X547/mesa, branch `mesa-nvk-r2`), because official NVK talks only to nouveau. NVK has an internal interface to the kernel driver (`nvkmd`), and upstream ships one back end, for nouveau. The fork adds a second back end, `nvrm`, of about 2,800 lines in 27 commits, which talks to NVIDIA's resource manager through Haiku's device node. It is the work of one person, is based on Mesa of August 2025 and has not moved since 31 December 2025 (checked 14 November 2026). The project writes its own back end on this model, against current Mesa, speaking to its GPU service.
- Performance of NVK: less than half of the proprietary driver on average on an RTX 5080 (Phoronix, March 2026); about 70 % observed by the project on an older card (CS2 at 1440p); progressing fast. Performance on the reference machine's card remains to be measured (**Open**).
- For inference, Vulkan is behind CUDA by about 10 % in generation and 36 % in prompt reading, on the proprietary driver.
- The proprietary GSP firmware is required.
- Compute goes through Vulkan. CUDA and DLSS are out of scope.

### Trial at the head of the track

**Decided, 14 November 2026.** A two-week trial opens the track: the NVIDIA core compiled outside Linux, display planes, channel priorities, and llama.cpp on NVK under Linux.

- Direct scanout (see [ui.md](ui.md#compositor)) stays decided subject to this trial.
- The hardware planes and the channel priority exposed by the NVIDIA core without its Linux layer are "from memory".

## Fallback and test paths

**Decided, 14 November 2026.**

- Fallback path: a software compositor on the firmware framebuffer.
- Software rendering and a virtio-gpu driver, to test the compositor under QEMU and as a fallback path.

The reference desktop's processor has no integrated GPU: the first pixels come from the firmware framebuffer (UEFI GOP), then from NVIDIA alone (see [platform.md](platform.md#hardware-reference)).

## GPU scheduling

- The GPU service applies the scheduling classes to submissions, in the same deadline graph as the processor (**Proposed**; see [scheduling.md](scheduling.md#classes)).
- **Open.** The GPU service alone arbitrates GPU time and memory, with the same latency classes as the processor: compositor and audio first, inference as a background task, cut into small preemptible batches. This is what holds the gate "frame pacing during inference" (see [gates](../plan/gates.md#latency-gates)). The priority mechanism of NVIDIA channels remains to be verified.

## GPU memory

**Proposed, 14 November 2026.**

- GPU memory is managed by the GPU service with the same per-task budgets as main memory (see [memory.md](memory.md#budget-without-overcommit)). The weights of a model are mapped blobs, shared between processes.
- **GPU memory full** (requirement of the user: no crash). A GPU buffer is a memory object that can reside in video memory or in main memory. In order:
  1. move to main memory the buffers of background tasks and of non-visible surfaces;
  2. for inference, move layers to the processor (llama.cpp allows it, from memory);
  3. let the requesting task overflow into main memory, slower but alive;
  4. only then does general [memory pressure](memory.md#pressure) apply.
- Applications read their budget (Vulkan memory budget extension, from memory).
- What NVK and the NVIDIA core allow as eviction remains to be verified.

## Upscaling and frame generation at system level

**Open; deferred until after the alpha** (**Decided**, 14 November 2026).

- A 3D surface would hand over colour, depth and motion vectors at reduced resolution and rate, and the GPU service would do the rest. The agent's 3D applets would be the first clients.
- ANR (Apex Compute) is a candidate; its source code and its licence are awaited. ANR FG interpolates between two frames, so it holds one back, but it costs only about 1 ms of GPU per generated frame in 4K on an RTX 5090, 214 MB of memory and 0.17 MB of weights (figures of the publisher, not verified by a third party). It has a native Metal version, so it is portable.
- The GPU time freed goes to the local model, whose latency dominates the agent's.
- Proposal: enabled by default for the agent's applets and for any surface that asks for it, never imposed on a surface that asked for the low-latency path.

## Related

- Hardware video decoding through Vulkan Video: [media.md](media.md#hardware-video-decoding).
- The loading of the GPU firmware as a probable long point of boot: [gates](../plan/gates.md#boot-and-shutdown).
- Laptop graphics (Intel i915 or xe): [platform.md](platform.md#hardware-reference).
