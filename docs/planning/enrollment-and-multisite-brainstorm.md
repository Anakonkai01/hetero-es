# Brainstorm note: enrolling workers without Tailscale, and spreading over many sites (AI, 09/10/2026)

**Status: a NOTE, not a decision and not an ADR.** The owner will plan this part later with a stronger model; this file keeps what was said so that the planning starts from it. Nothing here is implemented or measured unless it says so. Related: `docs/adr/ADR-003-remote-workers-network.md` (proposed), `TODO.md` groups `scale-and-spread`, `ideas-remote-workers`, `admission-in-the-join-flow`, `remote-workers-from-ADR-003`.

## What the owner asked for (09/10)
* Scale and spread over many machines in many places (LAN, other cities), PCs and laptops **with NVIDIA GPUs**. MacBook / Apple Silicon: noted, postponed.
* Not to depend on Tailscale (a personal account). Track B (production) will have an admin and users.
* "Download and install, then log in, and the machine is registered as a worker."
* Hardware expected: a second 3060 (another city), a 5070 Ti, a 4060 (Ada, an architecture never checked), then internet cafes with a few machines.
* Large N and many workers: agreed to be studied by simulation (the real coordinator and ledger with hundreds of simulated workers).

## Constraints the AI inferred (not verified)
Internet-cafe machines: probably Windows, probably no administrator rights, probably only outgoing web traffic (443), possibly reset at each restart, GPU busy with games, owned by someone else (consent needed; not fully trusted). A VPN needs administrator rights and a driver, so it is a poor fit there.

## Options discussed
| | description | fits cafes | admin / users | note |
|---|---|---|---|---|
| A. Self-hosted overlay with identity (NetBird, Headscale) | like Tailscale, the owner runs the server | poor (needs rights for a VPN) | built in | a server to run |
| **B. Application-layer gateway over HTTPS** (leaning) | workers only call out to a public address on 443, authenticated; no VPN | good | to be designed | the worker protocol is already pull: only TLS and authentication in front |
| C. Hybrid | B by default, A optional inside a trusted network | good | good | more parts |

## Enrollment sketch
Like `gh auth login` (OAuth device flow): the worker shows a short code and opens a browser; the user logs in; an admin approves (or a policy does); the machine receives its own revocable credential (token or certificate). Then: a capability report (GPU, memory), a fast numerical qualification before any work, and a user policy (run only when idle, GPU temperature limit, time windows). Accounts and login should be a service of track B; track A defines the worker protocol (authentication by device token, capability report, lease, result). **Open: what track B has chosen for login.**

## Infrastructure sketch
The coordinator is behind a home router. A public point is needed: a small rented server running the HTTPS gateway and the enrollment service, the coordinator reaching it by an outgoing connection; or a rented GPU server running the coordinator itself. Open: cost and whether the owner accepts it.

## Facts that bear on the design (measured, 08 to 09/10)
* A worker needs only outgoing connections (pull protocol).
* The 3060 over home wifi through Tailscale: full synchronization 285 s (28 Mbit/s) against 10 s on the cable; by replay it catches up in 6 s and makes the cluster 1.29 times faster than the 5070 Ti alone (predicted 1.28). Replay makes a slow link acceptable; a joining worker can start from the base weights (downloaded from Hugging Face at the pinned revision) and replay the update records (`--replay-max-chain`).
* CUDA noise engine bit-equal on Turing (1660S), Ampere (3060) and Blackwell (5070 Ti); FP32 evaluation equal on all three (0 of 1,920 answers different). FP16 differs between GPUs. **Every new GPU model (the 4060 is Ada) needs the qualification; the Windows-native torch build has never been checked** (the 3060 ran in WSL2).
* A worker is trusted by design: a borrowed or cafe machine can return wrong rewards unseen. Idea: evaluate a fraction of the candidates twice on two machines and compare.

## Work packages the AI would propose (to be replaced by the real plan)
1. Worker protocol v2 with track B: device enrollment, authentication, capability report. 2. A fast numerical qualification as the admission gate (minutes, golden values from the 5070 Ti). 3. A test gateway on a small rented server, tried with the second 3060. 4. A Windows-native worker without administrator rights, portable (USB bundle: torch with CUDA is about 3 GB), qualified on the 4060. 5. Scale simulation. 6. A first real test in an internet cafe, with a checklist beforehand (OS, rights, GPU, ports, resets, bandwidth).

## Questions left for the planning
Strict or loose reproducibility across devices (bit-equal rewards, or only exact replay)? Who owns accounts and login (track B)? A rented server: yes or no? Windows or Linux on the 4060 and on the cafe machines? What is the trust model for borrowed and cafe machines? Where does the admin's policy live?
