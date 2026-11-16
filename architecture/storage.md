# Storage

Statuses are defined in the [README](../README.md#status-legend).

There is no global directory tree and no POSIX file system. The store holds **blobs** (immutable pieces of data, addressed by the hash of their content) and **objects** (named, possibly modifiable items that reference blobs), with SQLite for the metadata.

## On-disk format

**Aligned**, with the points marked Decided added on 14 November 2026.

- Written by the project on the model of Fuchsia's blobfs, with no POSIX file system.
- SQLite holds the metadata: blob index, map of free extents (contiguous runs of disk blocks), objects, versions, rights, agent memory.
- Data is in immutable blobs, each verified by a Merkle tree (a tree of hashes that lets any block be checked against the blob's root hash).
- A modifiable object is a sequence of blobs referenced by SQLite. Small objects are stored in SQLite itself.
- Objects have stable identifiers (rule 5 of the [ABI](wasm-abi.md#abi-rules)).
- USB sticks (FAT, exFAT) are handled by a separate driver, later.

Consistency (**Decided**, 14 November 2026):

- Consistency after a power cut comes from the SQLite journal. "Root switch" designates only the change of system slot (see [Updates](#updates)).
- There is one SQLite database per key domain: one for the machine and one for each user.
- An order is imposed between databases: allocate and commit in the machine database, reference afterwards, collect the leaks. This is tested by injecting power cuts.
- Deduplication does not cross two encrypted zones.
- Version 1 has one mutable type for heavily rewritten data: simple extent files, allocated in large chunks, used by application databases. Copy-on-write extents, per-block checksums and snapshot-based versions for that type are deferred until after the alpha.
- The store format stays readable by the previous version of the system, and this is tested.
- The store keeps a space reserve for the disk-full case, supports TRIM, and keeps copies and checksums of the database.
- The ABI has a durability point (`sync`).

SQLite with a custom VFS (its storage back end) in WAL mode is "from memory".

Comparison with Fuchsia (verified 14 November 2026, official documentation): bootfs (a read-only image loaded at boot) corresponds to the signed boot image; blobfs (packages, content-addressed) to the system and packages zones; minfs then Fxfs (modifiable data) to the objects. Fuchsia accepted to put blobs in Fxfs and to remove its volume manager (RFC-0225): a single store, as here.

## Partitions

**Proposed.** The disk carries two partitions:

1. An EFI partition in FAT32, required by the firmware. It carries the signed boot images of the A/B/R slots and is written only by the update.
2. The store, which carries everything else, plus a small raw region for the crash trace, encrypted with the device key, since the user ring and the black box can hold the user's data.

## Zones

**Proposed.** The store is divided into zones, which differ in scope, encryption, backup and lifetime. Zones are logical scopes inside the one store, not separate file systems; the on-disk format does not change.

| Zone | Content | Scope | Encrypted | Bytes copied into the user's backup | Lifetime |
|---|---|---|---|---|---|
| System | Blobs of the image, designated by the system hash | Machine, read-only | No (public, verified) | No: the backup keeps the system hash, the blobs are downloaded again | Until the slot is removed |
| Packages | Blobs and manifests of applications, models | Machine, shared between users | No | No: the backup keeps the list of packages and their hashes; a "full copy" option exists for offline use | Garbage-collected by references |
| Cache | Compiled code, thumbnails, indexes | Machine or user | Depends on the origin | No | Can be erased at any time |
| Device | Pairing keys, networks, hardware settings | Machine, available before the session | Yes, TPM key | No | Until factory reset |
| User | The person's collections, agent memory, versions | One user | Yes, user key | Yes | Permanent |
| Application | The `home` collection received at launch | One user and one application | Yes | Yes | Removed with the application, on confirmation |
| Snapshots | Frozen state of processes | One user | Yes | No | Replaced at each snapshot |
| Ephemeral | Temporary files, guest session | One task or one session, in memory | Not applicable | No | End of the task |
| Foreign | USB sticks, disks of other systems, network shares | Seen as a collection, through a reader component | Depends on the medium | No | While the medium is plugged in |

Notes:

- A **collection** is a set of objects designated by a capability; `home` is the collection an application receives at launch.
- The Snapshots zone holds automatic snapshots, which exist only for idle Wasm components. Moving a surface to another device goes through `suspend` and `resume`, not through this zone (see [platform.md](platform.md#process-state-suspend-resume-and-snapshots)).
- The POSIX view of ported software is built by the name table of the process: `/tmp` goes to the ephemeral zone, the home directory to the application zone (see [wasm-abi.md](wasm-abi.md#how-userland-builds-against-the-os)).
- Factory reset: erase the device and user zones.
- Embedded: system and device zones only.
- Start-up order: the boot image reads the system zone, which is not encrypted; the service manager starts the TPM driver and the key service from it; the key service unseals the device key and opens the device zone; the user's code then opens the user key.
- Marks: a read from the user, application, snapshot or device zone adds the mark `private`, whoever wrote the data; cache and ephemeral objects keep their writer's marks; system and package blobs carry none (**Proposed**, 16 November 2026; [security.md](security.md#provenance-marks)).

## Blobs

**Proposed.**

- Blobs are deduplicated by content between all packages: a library common to ten applications is stored once, and compiled once.
- There is nothing to mount or prepare at launch.
- Limit: a component that bundles its dependencies shares nothing. Language runtimes (Python, JS) are therefore shipped as separate components, identical from one application to the next.

## Open points and proposed answers

Each point below is **Open**, with a **Proposed** answer, except point 1, which is **Decided** (14 November 2026).

| # | Open point | Proposed answer |
|---|---|---|
| 1 | Heavily modified objects (an application's database, a disk image): a sequence of immutable blobs is expensive in random writes; a modifiable object type by extents, without a Merkle tree, is probably needed | Decided: in version 1, simple extent files allocated in large chunks, with no Merkle tree, used by application databases (see [On-disk format](#on-disk-format)). Copy-on-write, a checksum per block and versions as snapshots for that type are deferred until after the alpha |
| 2 | Several disks, mirroring | One disk for the store in version 1; another disk is one more store where zones can be placed; mirroring later |
| 3 | Quotas per application | The quota is carried by the capability of the collection |
| 4 | How long versions are kept | All versions for 30 days, then one per day, then one per week; adjustable |
| 5 | Swap: compression first, encrypted region afterwards | Compression in memory in version 1, encrypted overflow to disk afterwards (see [memory.md](memory.md#compression-and-swap)) |
| 6 | Packages installed by one user are visible to the others: accept or not | Accepted; a private installation goes into the user's zone |

## Packages and distribution

| Topic | Position | Status |
|---|---|---|
| Package | A package is a set of blobs and a signed manifest. Identity = publisher key + name (rule 3 of the ABI). Launch without installing. A central store later, never mandatory | Decided |
| Transport in version 1 | Blobs served by hash from static HTTPS hosting, with a signed manifest | Decided, 14 November 2026 |
| Container registry | After the alpha. To explore: a standard container registry, already the preferred route of the Bytecode Alliance for distributing components (`wkg` tool; verified 13 November 2026). Point to settle: the registry identifies a layer by its SHA-256, DodOS blobs by their Merkle root | Open |

Publisher keys, their delegation and revocation are in [security.md](security.md#publisher-keys).

## Updates

**Aligned**, with the points marked Decided added on 14 November 2026.

- The system is a hash: one hash designates the whole system image.
- Slots A/B/R: two system slots and a recovery slot, with automatic rollback. A reboot loop is handled by this rollback.
- TUF metadata (The Update Framework, a specification for signed update metadata).
- A signed boot image sits on the boot partition. Its services are listed in [memory.md](memory.md#boot-image-services).
- The A/B switch is done through the UEFI boot variables, not by a rename on FAT (**Decided**).
- A new right requested at update time requires the user's agreement (**Decided**; see [security.md](security.md#publisher-keys)).
- The recovery slot holds a minimal image and rescue tools (see [platform.md](platform.md#installer-and-recovery) and [wasm-abi.md](wasm-abi.md#rescue-tools)).

## Backup

**Proposed, 14 November 2026, to validate.**

- The user and application zones are backed up, encrypted before sending, to a device of the user's circle (see [devices.md](devices.md)), an external disk or S3-type object storage.
- The backup is incremental by construction, because blobs are designated by hash.
- Restore: the system hash, the list of packages, then the objects.
- Changing machine: pairing, then synchronisation.

## Throughput gates

One throughput gate per type of workload (**Decided**, 14 November 2026). See [plan/gates.md](../plan/gates.md#overhead-gates).
