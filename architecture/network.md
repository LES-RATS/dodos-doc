# Network

Statuses are defined in the [README](../README.md#status-legend).

## Network stack

**Open; trial with priority.**

- The stack runs in user space. `wasi:http` and `wasi:sockets` (the WASI interfaces for HTTP and sockets) are backed by capabilities.
- First choice: Netstack3, through the project's own extraction from the Fuchsia tree. The crate `netstack3-core` 0.1.0 proves that it is feasible, but it comes from an anonymous account (`synaptic-void`) and its source repository cannot be found: it is not to be used as it is. Verified 13 November 2026.
- To do: make the extraction of the Netstack3 core from the Fuchsia tree, and judge the gap with upstream.
- Fallback: the NetBSD stack (rump).
- Rejected: smoltcp, lwIP and the Linux stack.

In the [build order](../plan/roadmap.md#build-order), a hosted network stack is planned on the hosted track and the network stack is in step 3 of the kernel track.

## The network service replaces a firewall

**Proposed, 14 November 2026, to validate**, unless marked.

- There is no separate firewall: the network service takes its place. An application has no access to the network without a capability, and the capability carries its scope (hosts, ports, outgoing or incoming). Every incoming packet with no matching listening capability is dropped.
- What remains of a firewall: rate limiting in the network service, and an administration policy that bounds the capabilities that can be granted.
- DNS is encrypted by default in the network service; mDNS is used locally.
- VPN: a WireGuard component that receives one network capability and provides another.
- TLS is in the network service; the trust roots are shipped as a system blob (**Decided**, 14 November 2026).
- The scheduling classes apply to the network queues (see [scheduling.md](scheduling.md#classes)).

### Opening a port

- The application requests a listening capability in its manifest: protocol, port, and scope (machine, circle of devices, local network or internet).
- The user grants it at installation or at first use; on a server, it is written in the configuration.
- Internet scope: the network service asks the router for the redirection (PCP, UPnP) or, better, exposes the service through the key-addressed transport, with no open port at all.
- Revoking the capability closes the port.

### Key-addressed services

- A service exposed by key listens on no port. The machine opens an outgoing connection to a relay, then the direct path is established when possible. A scan of the IP address shows nothing.
- The public key serves as an address, not as a secret: access also requires a capability handed over by the owner.
- Limits: the client must speak the project's transport, so an ordinary browser cannot reach the service; a public site needs a classic port or an HTTPS gateway. The relay sees who talks to whom, not the content.
- The transport is described in [devices.md](devices.md#transport).

## Wi-Fi

**Decided, 14 November 2026.** The Linux stack (mac80211 and iwlwifi) through the [emulation layer](drivers.md#linux-driver-emulation-layer), together with the laptops, after the alpha.

This closes the planned comparison with Fuchsia's stack (MLME and SME in Rust, an iwlwifi driver already adapted, softmac and fullmac interfaces; verified 13 November 2026). Wi-Fi is not on the critical path of the desktop. The Wi-Fi stack of FreeBSD is "from memory".

## Bluetooth

Bluetooth comes after the alpha (**Decided**, 14 November 2026). It is not on the critical path of the desktop.

- In Linux, the drivers (btusb) only transport HCI packets; the host stack is in the kernel and the audio profiles are in BlueZ. Only the transport driver is ported.
- Host stack, lead retained first (**Decided**): Sapphire of Fuchsia (host already extracted into Pigweed) with the profile components of the Fuchsia tree (bt-a2dp, bt-hfp-audio-gateway, bt-avrcp, bt-hid, bt-rfcomm), to adapt from FIDL to WIT, as for Netstack3. To do: read Sapphire and the profiles of the Fuchsia tree.
- Other leads: full BlueZ (requires emulating Bluetooth sockets and D-Bus); Zephyr (classic Bluetooth maintained by NXP, HFP still experimental, port outside Zephyr at prototype stage, a single controller); Android (huge).
- Rejected: the FreeBSD stack (little Bluetooth Low Energy, audio by makeshift means).

The Bluetooth stacks were verified on 13 November 2026.

## Server

A server runs `wasi:http` components and is administered through the key-addressed transport. See [platform.md](platform.md#server).
