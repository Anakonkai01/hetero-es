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

## Ghi chú buổi bàn với chủ dự án, 09/10/2026 sáng (tiếng Việt; vẫn là ghi chú, chưa phải quyết định kỹ thuật)

**Chủ dự án đã nói:** tạm quên tiệm net; **không thuê máy chủ**; danh tính riêng cho từng máy: đồng ý; độ tin cậy của máy lạ: để sau; track B chờ track A giao bản cơ bản, nên cách đăng nhập chưa biết (track A tự làm bản tối thiểu: mã gia nhập một lần cho mỗi máy -> thông tin xác thực riêng, thu hồi được; coordinator suy tên worker từ đó, không tin `--worker-id` tự khai).

**Mạng nhà chủ dự án (đo 09/10 09:30 trên 5070 Ti):** nhà mạng FPT Telecom (AS18403); IPv4 sau CGNAT (chủ dự án xác nhận; hop thứ 2 của traceroute bị ẩn); **có IPv6 công khai thật**: prefix /64 `2405:4803:cb11:b6d0::/64` do nhà mạng cấp, địa chỉ máy nhìn từ ngoài chính là địa chỉ của máy (không NAT); `ufw` bật cho IPv6, mặc định chặn vào. Chưa biết: modem FPT có chặn kết nối IPv6 từ ngoài vào không (cần thử từ một mạng khác: điện thoại 4G có IPv6, hoặc nơi đặt 3060 thứ hai); prefix có đổi khi modem khởi động lại không (thời hạn hiện tại ~5 giờ, gia hạn liên tục). Hệ quả nếu IPv6 vào được: coordinator ở nhà nhận kết nối trực tiếp mà không cần Tailscale hay máy chủ thuê, với điều kiện nơi đặt worker cũng có IPv6; vẫn phải có TLS, danh tính riêng và một reverse proxy có sẵn đứng trước server Python.

**Giả thuyết về điểm nghẽn của replay (AI, chưa đo, chủ dự án cho phép đo):** engine nhiễu CUDA sinh nhiễu bằng khoảng 21.900 lần gọi `normal_` nhỏ (22.528 phần tử mỗi lần) cho mỗi ứng viên, mỗi lần gọi là một lần gọi Python và một lần khởi động kernel. Chia chi phí replay đo được cho số lần gọi: 3060 ≈ 8,5 µs, 5070 Ti ≈ 3,3 µs, 1660S ≈ 23 µs mỗi lần, cỡ chi phí gọi kernel thông thường; nếu đúng, thứ chậm là số lần gọi chứ không phải phép toán. **Đọc code (`noise/cuda_engine.py`) cho biết thêm:** 22.528 là kích thước LỚN NHẤT mà hai GPU có số SM khác nhau còn cho cùng số (đo ở `2026-10-07-g7-restore-tradeoff/rng-*.json`), nên KHÔNG thể đơn giản gộp thành lần gọi lớn hơn mà vẫn giữ khớp từng bit; docstring cũng ghi "lần gọi lớn hơn là ít lần khởi động hơn, đó là thứ tốn thời gian". Hướng còn lại nếu giả thuyết đúng (chưa thử): ghi lại chuỗi lần gọi bằng CUDA Graph (cùng kernel, cùng tham số, ít chi phí CPU hơn; phải kiểm từng bit), hoặc một engine mới với kernel của mình (đổi hợp đồng số học, phiên bản engine mới). Script đo đang ở scratchpad của AI, chạy khi benchmark N = 48/96 xong (không đo khi GPU đang bận).

**Vì sao điều này quan trọng (suy luận):** mỗi worker phải replay đủ N ứng viên mỗi thế hệ dù chỉ chấm N/W ứng viên; tỉ lệ thời gian có ích ≈ t_eval / (t_eval + W × t_upd). Với số của 3060 (t_upd 0,186 s đo; t_eval ≈ 18 s suy ra): 10 worker ~10% thời gian là replay, 100 worker ~50%. Replay nhanh hơn k lần thì trần này lùi ra k lần.

**Quyết định của chủ dự án, 09/10 sáng (tiếp):**
* Lý do bỏ Tailscale: **mỗi lần đăng ký worker phải nhập tài khoản cá nhân của chủ dự án** trên máy người khác. Không phải vì không muốn dùng dịch vụ ngoài. (Ghi chú của AI: Tailscale có auth key để máy vào mà không đăng nhập, nhưng người cho mượn vẫn phải cài VPN; nên hướng dưới vẫn hợp hơn.)
* Nếu triển khai rộng mà chỉ đi thẳng bằng IPv6 thì máy ở mạng không có IPv6 không vào được: đó là giới hạn của CÁCH TRIỂN KHAI, không phải của lõi (giao thức chỉ cần một địa chỉ HTTPS). Triển khai rộng về sau gần như chắc cần một điểm công khai; quyết định ở giai đoạn sản phẩm.
* **Cloudflare Tunnel:** coordinator tự gọi ra Cloudflare (CGNAT không còn là vấn đề), worker chỉ gọi một địa chỉ HTTPS, không cài thêm gì, không cần tài khoản của chủ dự án. Quick Tunnel (miễn phí, không tài khoản, không tên miền, địa chỉ đổi mỗi lần khởi động lại, tối đa 200 yêu cầu đồng thời, chỉ để thử) dùng để **thử với 3060 thứ hai**; tunnel có tên cần tài khoản + tên miền riêng. Giới hạn liên quan: thân yêu cầu tối đa 100 MB, phải trả lời trong 100 s (lỗi 524), điều khoản hạn chế phục vụ file lớn lưu ngoài Cloudflare: không tải trọng số 1 GB qua đường hầm (mô hình gốc từ Hugging Face, bắt kịp bằng replay). Nhược điểm: phụ thuộc một hãng (chỉ phía coordinator); Cloudflare giải mã HTTPS nên thấy token và phần thưởng.
* **Tên miền: chưa có, mua thì tính sau.** Cho tới lúc đó không có địa chỉ cố định: mã gia nhập mang địa chỉ hiện tại.
* **Worker nhận một DANH SÁCH địa chỉ coordinator** (tunnel, IPv6 đi thẳng, sau này máy chủ công khai), để đổi cách kết nối không bắt người cho mượn cài lại.
* 3060 thứ hai: chiều 09/10, một người bạn (không làm IT) thao tác giúp; chủ dự án muốn một quy trình đúng kiểu "tải, cài, đăng nhập".
