# ADR-003 — Reaching workers on other networks (and whether to build our own overlay)

- **Status:** PROPOSED. Draft by Claude, 2026-10-08 (night), **pending owner review**. Nothing here is implemented except what is marked "measured".
- **Deciders:** A (Systems/Core owner)
- **Related:** `docs/third-machine-checklist.md`, `TODO.md` groups `ideas-remote-workers` and `admission-in-the-join-flow`, `src/heteroes/replay.py`, `src/heteroes/http_transport.py`

## Context
Today the workers are on one cable (10.10.10.x) or reach the coordinator through Tailscale. The owner can borrow machines that stay at other people's homes (one 3060 is already here in WSL2; a second one is in another city on 09/10). The owner floated "a kind of Tailscale of our own".

Facts (measured on 08/10, not assumed):
* The worker protocol is **pull**: a worker only needs an outgoing connection to the coordinator (`/v1/job`, `/v1/leases`, `/v1/results`, `/v1/heartbeats`, `/v1/models/<sha>`, `/v1/updates/<sha>`). Nothing has to be opened at the worker's home.
* The coordinator speaks plain HTTP; the token travels in clear text (`http_transport.py` says: acceptable only on a private network). A worker is **trusted**: it can return any reward.
* Tailscale between the 5070 Ti (wifi) and the 3060 (wifi, same home) became a *direct* path after a few minutes; first seconds went through a relay (DERP, 140 to 200 ms). The measured download of the 1 GB weights over it: about 2.5 to 3.5 MB/s (20 to 28 Mbit/s): one full synchronization takes 5 to 7 minutes, against 10 s on the cable.
* A replay of one generation on the 3060 costs about 5 s (update 0.186 s per candidate x 24 + 0.3 + check 0.5); the record is 1.4 KB. `scripts/predict_cluster.py` and the policy `auto` use exactly these numbers.
* The firewall of the 5070 Ti (`ufw`) allows 8765 only from the 1660S on the cable and everything on `tailscale0`.

## What decides the design
1. **With replay the bandwidth stops being the problem.** A worker that has the base weights (it can download them from Hugging Face at the pinned revision, no transfer from the coordinator at all) needs only the update records: kilobytes. The expensive full synchronization is needed only to recover from a broken state. Therefore a slow or relayed link is acceptable. This is the strongest argument against building anything fast or clever at the network layer.
2. The topology is a **star**: every worker talks only to the coordinator. Peer-to-peer NAT traversal (the hard part of a mesh) is not needed; only "the coordinator must be reachable by outgoing connections from the workers".
3. The hard parts of a VPN are cryptography, key management and NAT traversal. A home-made one is a security liability and months of work, with no gain over the existing ones.

## Options
| | what it is | reaches a worker behind NAT/CGNAT | encrypted | work for us | main risk |
|---|---|---|---|---|---|
| A. Tailscale (now) | managed WireGuard mesh | yes (hole punching, relay) | yes | none | the default ACL lets every device of the tailnet reach every other; vendor control plane |
| B. Headscale / NetBird self-hosted | the same clients, our own control server | yes | yes | a small server to run | we maintain a server |
| C. Own hub-and-spoke WireGuard | a cheap VPS with a public IP is the hub; coordinator and workers are spokes | yes (all connect out to the VPS) | yes | a script that creates keys and configs; no cryptography of our own | traffic passes through the VPS (cost, bandwidth: fine with replay) |
| D. TLS and per-worker tokens in our own protocol, coordinator behind a reverse tunnel or a public endpoint | authentication at the application layer | yes, if the coordinator is reachable | yes | real work in `http_transport.py` | exposes the coordinator to the Internet: every bug becomes a remote bug |
| E. Own mesh VPN (cryptography, NAT traversal, relays written by us) | what the owner floated | yes, if done right | only if done right | months | not recommended |

## Proposed decision
1. **Keep A for now** (it works, measured above), with an ACL written *before* any machine of another person joins: tags `tag:coordinator` and `tag:worker`; a worker may reach only the coordinator's port; nothing else of the tailnet. Nodes of borrowed machines get a key that expires.
2. **Make replay the way a remote worker joins**: allow a long chain (a late worker replays from the base weights; `fetch_chain` stops at 8 steps today) and a periodic checkpoint to keep the chain short. This removes the dependence on bandwidth and is the real "remote worker" feature.
3. **Add application-layer authentication anyway** (per-worker tokens, constant-time compare already exists) and refuse `--allow-unauthenticated` outside a loopback or cable address in `cluster_runner.py`; then a mistake in the network layer does not give the world a coordinator.
4. **Plan C as the answer to "our own Tailscale"** if the owner wants independence from a vendor: it reuses WireGuard (no cryptography written by us) and is a few hundred lines of scripts, because the star topology removes the mesh. Build it only after items 1 to 3, and measure it against A on the same pairs of machines.
5. **Do not build E.**

## Consequences and what is not decided
* Trust is unchanged: a borrowed machine can return wrong rewards unseen. Possible mitigation (not built): evaluate a fraction of the candidates on two workers and compare.
* The initial parent for a joining worker must be the base weights with the pinned hash; the join flow (TODO `admission-in-the-join-flow`) should check it.
* The second 3060 (another city) is the first real test of items 1 and 2 over a WAN; whatever happens there (relayed path, CGNAT, packet loss) should be written down in an evidence folder like the others.
* Open: the cost and the availability of a VPS for plan C; whether the owner wants the coordinator reachable when the 5070 Ti sleeps (it must be on during a run).
