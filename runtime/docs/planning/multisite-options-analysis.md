# Phân tích lựa chọn: nhiều máy, nhiều nơi, gia nhập không cần Tailscale (bản nháp của AI, 09/10/2026)

**Trạng thái: BẢN NHÁP KẾ HOẠCH, chủ dự án chưa review.** Không có code nào được viết, không có thí nghiệm nào được chạy cho tài liệu này. Đi kèm: `ADR-004-draft-enrollment-and-gateway.md` (quyết định đề xuất), `multisite-roadmap.md` (lộ trình, tiêu chí PASS/FAIL), `multisite-open-questions.md` (câu hỏi chủ dự án phải quyết).

Nguồn đã đọc: `enrollment-and-multisite-brainstorm.md` (ghi chú brainstorm của AI ngày 09/10: **suy nghĩ chưa kiểm, không phải kết luận**), `docs/adr/ADR-003-remote-workers-network.md` (PROPOSED, chưa review), đoạn "READ THIS FIRST" của `HETEROES_LLM_STATUS.md`, `docs/report/CLAIMS_AUDIT.md`, `TODO.md` (nhóm `scale-and-spread`, `ideas-remote-workers`, `admission-in-the-join-flow`, `remote-workers-from-ADR-003`), và đọc nhanh `src/heteroes/http_transport.py`, `replay.py`, `model/weights_io.py`, `scripts/run_worker.py` để kiểm vài điều kiện về code.

## Cách đọc nhãn

| nhãn | nghĩa |
|---|---|
| **[ĐO]** | có file đo trong repo; đường dẫn đi kèm. Giới hạn của phép đo vẫn áp dụng (một lần chạy, hai ba máy, một workload...). |
| **[CODE]** | AI đọc thấy trong code hôm nay (không phải phép đo, nhưng kiểm được bằng cách mở file). |
| **[SUY LUẬN]** | AI suy ra từ các số đo hoặc từ hiểu biết chung; **chưa kiểm**. Có thể sai. |
| **[BRAINSTORM]** | lấy từ ghi chú brainstorm 09/10; chưa kiểm. |
| **[CẦN KIỂM]** | sự thật bên ngoài (giá, giới hạn của dịch vụ, chính sách) mà AI không tra trong phiên này. |

---

## 1. Bài toán, nói từ đầu

Hôm nay hệ thống là **một coordinator** (trên máy 5070 Ti ở nhà) và vài **worker** (máy có GPU). Mỗi thế hệ ES có N ứng viên; worker **tự hỏi** coordinator "có việc không" (kiểu *pull*), nhận một ứng viên, chấm điểm, gửi phần thưởng (reward) về. Khi đủ N phần thưởng, coordinator tính bản cập nhật và mọi worker phải có trọng số mới trước thế hệ sau.

Chủ dự án muốn: máy ở nhiều nơi (cùng LAN → thành phố khác → tiệm net), PC và laptop NVIDIA; **tải về, cài, đăng nhập là thành worker**; không phụ thuộc Tailscale; track B (sản phẩm) sẽ có admin và người dùng.

Ba câu hỏi tách nhau, mỗi câu có lựa chọn riêng:
1. **Đường mạng**: worker ở xa nói chuyện với coordinator bằng cách nào? (mục 3)
2. **Danh tính và gia nhập**: ai được làm worker, chứng minh bằng gì, admin duyệt ở đâu? (mục 4)
3. **Đủ điều kiện và đáng tin**: máy mới có tính ra **đúng từng bit** như máy chuẩn không, có nhanh đủ để có lợi không, có trả kết quả thật không? (mục 5, 6)

Thêm một câu thứ tư, ít được nói tới trong brainstorm nhưng quyết định "nhiều máy" có ý nghĩa hay không: **hệ thống còn tăng tốc khi có hàng chục, hàng trăm worker không?** (mục 7)

## 2. Những sự thật đã có, phân loại

### Đo được
* **Giao thức là pull, hình sao.** Worker chỉ cần kết nối *đi ra* tới coordinator; không cần mở cổng nào ở nhà worker. [CODE: `http_transport.py`, các route `/v1/leases`, `/v1/results`, `/v1/heartbeats`, `/v1/job`, `/v1/models/<sha>`, `/v1/updates/<sha>`] [ĐO: mọi lần chạy hai/ba máy từ G3]
* **Replay làm đường mạng chậm trở nên chấp nhận được.** Bản ghi cập nhật khoảng 1,4 KB; 3060 bắt kịp mỗi thế hệ bằng replay trong 5,8–6,3 s, trong khi tải đủ 1 GB qua wifi + Tailscale mất 285 s (28 Mbit/s). Với replay, 3060 làm cụm nhanh 1,29 lần so với 5070 Ti một mình (dự đoán ghi trước: 1,28); với tải trọng số thì 1,00. [ĐO: `artifacts/experiments/2026-10-09-three-machines/README.md`, `2026-10-08-third-machine-3060/`] Giới hạn: một đường wifi trong nhà, chuỗi replay dài 1 bước, N = 24, 2 lần chạy.
* **Chi phí replay mỗi ứng viên**: 3060 khoảng 0,186 s; 5070 Ti 1,76 s / 24 ≈ 0,073 s; 1660S 12,27 s / 24 ≈ 0,51 s. Replay 100/100 thế hệ khớp hash trên hai máy. [ĐO: `2026-10-08-c4-replay/`, ADR-003]
* **Số học khớp từng bit trên ba kiến trúc** (Turing 1660S, Ampere 3060, Blackwell 5070 Ti) với engine nhiễu CUDA; đánh giá FP32: 0 trên 1.920 câu trả lời khác nhau; FP16 thì khác giữa các GPU. [ĐO: `2026-10-08-third-machine-3060/`, `2026-10-07-g7-restore-tradeoff/`] Giới hạn: một bộ phần mềm (torch 2.13.0+cu132), Linux/WSL2, một workload với chunk 64; Windows bản địa và Ada (4060) **chưa từng kiểm**.
* **Dự đoán admission sai hai lần cho 1660S**: dự đoán +3,3%, đo +12% và +14%; thời gian tuyệt đối dự đoán cao hơn 26–40%; tỉ lệ lợi ích (CB) đoán tốt hơn thời gian. [ĐO: `2026-10-08-c1-v2/`, `2026-10-09-three-machines/`]
* **Máy thật hỏng theo những cách không ai lường**: 1660S mất liên lạc ba lần dưới tải (lỗi PCI/GPU theo chủ dự án, chưa kiểm log); `apt install nvitop` trong WSL của 3060 làm hỏng CUDA (thư viện NVIDIA của Ubuntu che thư viện của driver Windows). [ĐO: STATUS "READ THIS FIRST", README ba máy]
* **Kịch bản lỗi có kiểm soát** (kill worker, pause worker, cắt mạng, kill coordinator giữa bản ghi và lúc áp dụng): 0 lỗi trong mọi lần kịch bản xảy ra thật. [ĐO: `2026-10-08-failure-campaign-x3/`, `-long-workers/`] Giới hạn: hai worker, một sự cố mỗi lần.

### Đọc thấy trong code hôm nay (không phải phép đo)
* Coordinator dùng `http.server.ThreadingHTTPServer` của thư viện chuẩn, HTTP thường, tối đa 64 kết nối đồng thời (`DEFAULT_MAX_CONNECTIONS`). [CODE]
* Xác thực là **một token dùng chung** (`Authorization: Bearer`), đi dạng rõ; docstring ghi "không phải danh tính". Server từ chối nghe trên địa chỉ không phải loopback nếu không có token. [CODE: `http_transport.py`]
* **`worker_id` do worker tự khai** (`run_worker.py --worker-id`, gửi trong thân yêu cầu `lease`). Hệ quả: quarantine (cách ly worker sau `RESTORE_MISMATCH`, ADR-002 quyết định 6) có thể bị né bằng cách đổi tên. Trong mạng riêng thì chấp nhận được; với máy lạ thì không. [CODE] [SUY LUẬN về hệ quả]
* **File trọng số là byte FP16 thô, đặt tên theo SHA-256, worker kiểm hash trước khi chạm vào mô hình**; không dùng pickle. Nghĩa là trọng số có thể lấy từ **bất kỳ nguồn nào** (máy chủ trung gian, kho lưu trữ, máy bên cạnh) mà không cần tin nguồn đó. [CODE: `model/weights_io.py`]
* Worker không nhận code từ coordinator: workload là tên dựng sẵn (`--workload cot_l1_q128`), recipe là dữ liệu có hash. [CODE] Đây là một tính chất an toàn đáng giữ (mục 6).
* `fetch_chain` dừng ở 8 bước theo mặc định (`MAX_CHAIN = 8`), chỉnh được bằng `--replay-max-chain`. [CODE: `replay.py`]
* Worker hỏi lại mỗi 0,25 s khi không có việc (`--poll-seconds`). [CODE]

### Chỉ là suy luận hoặc brainstorm (chưa kiểm)
* Máy tiệm net: có lẽ Windows, không có quyền admin, chỉ ra được cổng web 443, bị khôi phục (reset) mỗi lần khởi động lại, GPU bận chơi game, thuộc người khác. [BRAINSTORM] **Chưa ai ghé một tiệm net nào để kiểm.** Toàn bộ thiết kế cho tiệm net dựa trên giả định này; giai đoạn 7 của lộ trình bắt đầu bằng một bảng kiểm thực địa chính vì thế.
* Coordinator nằm sau router nhà, có thể sau CGNAT (nhà mạng dùng chung một địa chỉ IP công khai cho nhiều khách), nên không mở cổng vào nhà được. [SUY LUẬN, chưa kiểm đường truyền nhà chủ dự án]
* Băng thông upload ở nhà chủ dự án: **chưa đo**. Nó quyết định coordinator ở nhà có phục vụ được checkpoint 1 GB cho nhiều worker hay không.

## 3. Đường mạng: các lựa chọn

Điều kiện chốt (từ yêu cầu): không phụ thuộc Tailscale; máy tiệm net (giả định) không có quyền admin, nên **không cài được VPN** (mọi VPN trên Windows cần driver mạng ảo, cần admin) [SUY LUẬN, hiểu biết chung về Windows]; nhà chủ dự án có thể không nhận kết nối từ ngoài vào.

| | mô tả | máy không quyền admin | không phụ thuộc Tailscale | việc phải làm | rủi ro chính |
|---|---|---|---|---|---|
| **A. Tailscale** (hôm nay) | mesh WireGuard có quản lý | không (cần cài client) | **không** | không | trái yêu cầu; tài khoản cá nhân |
| **B. Headscale / NetBird tự host** | máy chủ điều khiển của mình, client WireGuard | không | Headscale vẫn dùng client của Tailscale; NetBird có client riêng [CẦN KIỂM] | chạy một máy chủ | vẫn là VPN: tiệm net không dùng được |
| **C. WireGuard hình sao tự dựng** (ADR-003 phương án C) | VPS là hub, mọi máy là nhánh | không | có | script khóa và cấu hình | như B: cần admin trên worker |
| **D. Mở cổng coordinator ra Internet** (port forward ở router nhà) | worker gọi thẳng IP nhà | có | có | ít | CGNAT có thể làm không được; mọi lỗi của server thư viện chuẩn thành lỗi từ xa; lộ IP nhà |
| **E. Cổng HTTPS trên VPS nhỏ** (brainstorm "B") | VPS chạy reverse proxy có TLS; coordinator ở nhà nối **ra** VPS bằng một đường hầm chỉ giữa máy của chủ dự án; worker gọi `https://<tên miền>` cổng 443 | **có** | có | proxy + đường hầm + xác thực theo thiết bị | một máy chủ phải chạy và trả tiền; một điểm hỏng mới |
| **F. Đường hầm của nhà cung cấp** (Cloudflare Tunnel, ngrok...) | coordinator nối ra dịch vụ, được một tên miền HTTPS công khai | có | có, nhưng phụ thuộc nhà cung cấp khác | ít | điều khoản dịch vụ với file lớn, giới hạn kích thước [CẦN KIỂM]; đổi Tailscale lấy một nhà cung cấp khác |
| **G. Coordinator chạy luôn trên máy thuê** | không còn "nhà" | có | có | dời coordinator | engine CUDA cần GPU ở coordinator [STATUS]; GPU thuê đắt; với engine CPU thì cập nhật chậm trên VPS rẻ [SUY LUẬN] |

**Đề xuất: E** (khớp hướng nghiêng của brainstorm, nhưng với lý do được kiểm lại dưới đây), và giữ A chỉ làm đường **đo đối chứng** trong lúc phát triển.

Lý do, theo thứ tự quan trọng:
1. **Chỉ E, D, F, G đi được tới tiệm net** (không cần admin trên worker). D phụ thuộc vào CGNAT và phơi server ra ngoài; F đổi một nhà cung cấp lấy nhà cung cấp khác; G cần GPU thuê. [SUY LUẬN]
2. **Giao thức đã sẵn sàng cho E.** Pull + hình sao nghĩa là không cần xuyên NAT giữa các máy (phần khó của mesh VPN); chỉ cần một điểm công khai mà mọi bên nối ra. [CODE + ĐO]
3. **Replay làm độ trễ thêm của đường đi qua VPS gần như không quan trọng.** Mỗi thế hệ chỉ vài yêu cầu JSON nhỏ và một bản ghi 1,4 KB mỗi worker. Thời gian thêm do vòng qua VPS **chưa đo** (giai đoạn 3 đo nó); độ trễ khứ hồi Tailscale relay đo được 140–200 ms trong vài giây đầu [ĐO: ADR-003], nhỏ so với thế hệ ~117 s. [SUY LUẬN từ số đo]
4. **Trọng số không cần đi qua đường hầm.** File trọng số được kiểm hash (mục 2), nên mô hình gốc tải thẳng từ Hugging Face ở revision ghim; checkpoint có thể để ở bộ nhớ đệm của VPS hoặc một kho lưu trữ đối tượng; đường lên nhà chỉ mang mỗi checkpoint **một lần**, không phải một lần cho mỗi worker. [CODE + SUY LUẬN]
5. **Không viết mật mã của mình.** TLS do một reverse proxy có sẵn (Caddy hoặc nginx, chứng chỉ Let's Encrypt) lo; server thư viện chuẩn **không bao giờ** đứng thẳng trên Internet. [SUY LUẬN, phù hợp ADR-003 điểm 5]

Đường hầm nhà → VPS (chỉ máy của chủ dự án, nên cần admin là được): bắt đầu bằng **SSH reverse tunnel** (có sẵn OpenSSH, dựng trong vài phút, gỡ bằng cách tắt tiến trình); nếu đo thấy hay rớt thì đổi sang **một đường WireGuard điểm-điểm** giữa máy coordinator và VPS (đây là "Tailscale của mình" duy nhất cần có, và nó chỉ một cạnh). [SUY LUẬN; cả hai đều chưa thử]

Điều E **không** giải quyết: VPS là điểm hỏng mới; phải trả tiền thuê [CẦN KIỂM giá, ước chừng vài USD/tháng cho máy nhỏ]; khi coordinator ở nhà tắt máy thì cả cụm dừng (như hôm nay).

## 4. Danh tính và gia nhập

### Vấn đề hôm nay
Token dùng chung + `worker_id` tự khai [CODE]: biết token là làm được mọi worker, đổi tên là thoát cách ly, thu hồi một máy nghĩa là đổi token của tất cả.

### Lựa chọn
| | cách | hợp tiệm net | hợp "đăng nhập" | việc |
|---|---|---|---|---|
| 1. Token dùng chung (hôm nay) | một chuỗi bí mật | có | không | 0 |
| 2. **Thông tin xác thực riêng cho từng thiết bị** (token ngẫu nhiên, lưu dạng hash phía server, gửi qua TLS) | admin hoặc dịch vụ phát khi gia nhập | có | có (là thứ "đăng nhập" trả về) | vừa |
| 3. Chứng chỉ client (mTLS) | mỗi máy một chứng chỉ | có, nhưng proxy phải chuyển danh tính vào trong | có | lớn hơn: cấp và thu hồi chứng chỉ |
| 4. Đăng nhập OAuth "device flow" (RFC 8628, kiểu `gh auth login`) | máy hiện mã ngắn, người dùng đăng nhập trên điện thoại, admin duyệt, máy nhận thông tin xác thực kiểu 2 | có (không cần trình duyệt trên máy) | **có, đúng yêu cầu** | cần một nhà cung cấp danh tính (của track B) |

**Đề xuất: 2 làm nền, 4 là cách lấy được nó.** Track A định nghĩa *hợp đồng*: "một thông tin xác thực thiết bị → `device_id`, chủ sở hữu, trạng thái (đang chờ / được duyệt / bị thu hồi), phạm vi". Coordinator **tự suy `worker_id` từ thông tin xác thực**, không đọc từ thân yêu cầu; dòng ledger, quarantine, nhật ký đều gắn với `device_id`. Trong lúc track B chưa có hệ đăng nhập, track A dùng **mã gia nhập một lần** do admin tạo bằng dòng lệnh (giai đoạn 1); khi track B sẵn sàng, device flow thay chỗ mã gia nhập mà không đổi giao thức worker. [SUY LUẬN; brainstorm cũng gợi ý device flow]

Lý do tách: track B chọn hệ đăng nhập nào (tự host Keycloak/Authentik/Zitadel, hay dịch vụ ngoài) **chưa biết** [BRAINSTORM: câu hỏi mở], và track A không nên chờ nó để thử đường mạng với 3060 thứ hai.

### Máy tiệm net bị reset
Nếu máy bị khôi phục mỗi lần khởi động, thông tin xác thực mất theo. [SUY LUẬN từ giả định BRAINSTORM] Hai cách: đăng nhập lại mỗi phiên (người dùng phiền, admin phải duyệt lại), hoặc **tài khoản theo địa điểm**: admin duyệt một lần "tiệm X", mỗi ngày tiệm X có một mã gia nhập dùng cho mọi máy ở đó, mỗi máy vẫn nhận `device_id` riêng cho phiên. Chủ dự án quyết (câu hỏi mở).

## 5. Đủ điều kiện (admission) khi máy tự gia nhập

### Hai việc khác nhau
1. **Đủ điều kiện về số học** (có/không, không ai được ghi đè): engine nhiễu cho đúng hash, perturb/restore đúng từng bit, phần thưởng của vài ứng viên tham chiếu đúng giá trị vàng (golden) đo trên 5070 Ti. `admission.py` đã có cổng INELIGIBLE không ai ghi đè được [CODE]; cái thiếu là một bộ kiểm **nhanh** (vài phút) chạy được lúc gia nhập. Profile đầy đủ hôm nay mất hàng giờ trên 1660S [ĐO: STATUS].
2. **Có lợi về tốc độ không**: dự đoán đã sai hai lần với 1660S [ĐO]. Với dispatch pull + greedy, một worker chậm tự lấy ít ứng viên hơn; cái hại thật duy nhất là nó giữ **ứng viên cuối** làm cả thế hệ chờ. [SUY LUẬN từ thiết kế B3/B4] Vì vậy đề xuất: **nhận vào dựa trên đủ điều kiện, rồi quan sát tốc độ thật vài thế hệ đầu**, chỉ hạ cấp (không giao ứng viên cuối, hoặc cho nghỉ) khi số đo thật cho thấy nó làm chậm. Profile nhanh chỉ để có ước lượng ban đầu. [SUY LUẬN]

### Chính sách tái lập (reproducibility) phải được chọn trước
Có hai mức, và chúng khác nhau ở chỗ quan trọng:
* **Bắt buộc dù chọn gì**: engine nhiễu và phép cập nhật phải khớp từng bit trên mọi worker. Nếu không, worker chấm một ứng viên khác với ứng viên mà bản cập nhật giả định, và replay ra trọng số khác hash. [CODE + ĐO: replay 100/100]
* **Chặt**: phần thưởng cũng phải khớp từng bit (hôm nay đúng với FP32 trên ba GPU, một workload [ĐO]). Được: chạy lại cho ra đúng cùng kết quả; **kiểm chéo bằng so sánh bằng nhau tuyệt đối** (mục 6). Mất: mỗi tổ hợp (kiến trúc GPU × hệ điều hành × khoảng phiên bản driver × bộ phần mềm) phải được kiểm; tổ hợp nào lệch là không dùng được.
* **Lỏng**: phần thưởng được phép lệch rất nhỏ. Được: nhận nhiều máy hơn. Mất: không chạy lại được từng bit; kiểm chéo phải có ngưỡng sai số, và một worker gian có thể nấp trong ngưỡng.

**Đề xuất: chặt** cho track A (đó là claim cốt lõi của dự án, và nó cho kiểm chéo miễn phí). Rủi ro cần nói trước [SUY LUẬN]: (a) máy tiệm net có driver cũ; bản torch cu132 cần driver mới; dùng bản CUDA cũ hơn để chạy trên driver cũ là **một bộ phần mềm khác** và phải được kiểm lại từ đầu; (b) TODO "chunk riêng cho từng worker" đổi kích thước batch, có thể đổi kernel và làm lệch phần thưởng FP32: phải kiểm trước khi gộp với chính sách chặt.

## 6. Tin cậy: máy của người khác

Hôm nay worker **được tin** theo thiết kế (MASTER §7, CLAIMS_AUDIT "không claim an toàn trước worker độc hại"). Một máy mượn hoặc máy tiệm net có thể trả phần thưởng sai mà không ai thấy; với chuẩn hóa z-score, một phần thưởng cực đoan có thể kéo cả bản cập nhật. [SUY LUẬN]

Lựa chọn:
1. Chỉ nhận máy của người tin được; ghi rõ trong báo cáo. (0 việc; không đi tới tiệm net một cách an toàn.)
2. **Kiểm chéo**: một phần f ứng viên được chấm hai lần trên hai thiết bị khác chủ; với chính sách chặt, so sánh là **bằng nhau tuyệt đối**. Xác suất bắt được một thiết bị làm sai k kết quả: 1 − (1 − f)^k; ví dụ f = 0,1: k = 10 → 65%, k = 30 → 96%. Chi phí: thêm f phần tính toán. [SUY LUẬN: toán, chưa đo] Khi lệch: cách ly cả hai thiết bị, chấm lần ba trên máy tin cậy để biết ai sai.
3. Giới hạn ảnh hưởng của một kết quả (định hình phần thưởng theo hạng thay vì z-score). **Đổi thuật toán và hợp đồng số học**; không đề xuất trong giai đoạn này, chỉ ghi lại.

**Đề xuất: 1 cho tới khi 2 được xây và đo**; giai đoạn có máy không tin được chỉ bắt đầu sau khi kiểm chéo qua được bài thử "worker nói dối" (lộ trình giai đoạn 6).

Hai tính chất an toàn cho **chính máy worker** (ngược chiều: người cho mượn máy cần được bảo vệ khỏi hệ thống), nên giữ thành bất biến:
* Coordinator chỉ gửi **dữ liệu** (tên recipe, hash, bản ghi), không gửi code; workload dựng sẵn trong bản phát hành. [CODE: đúng hôm nay]
* Trọng số là byte thô có kiểm hash, không pickle. [CODE: đúng hôm nay] Phần mềm worker chỉ được cập nhật bằng bản phát hành mới (có chữ ký, câu hỏi mở cho track B).

## 7. Mở rộng tới nhiều worker: một trần cần biết trước

Đây là phần **không có trong brainstorm** và là suy luận từ các số đo, chưa kiểm ở quy mô lớn.

Với replay, **mỗi worker phải replay toàn bộ bản cập nhật của mỗi thế hệ**: N ứng viên × t_upd, bất kể nó chỉ chấm N/W ứng viên (W = số worker). Phần việc có ích của nó là (N/W) × t_eval. Tỉ lệ thời gian có ích:

  hiệu suất ≈ t_eval / (t_eval + W × t_upd)  (N triệt tiêu)

Ví dụ với số đo của 3060 [ĐO: t_upd ≈ 0,186 s] và t_eval ≈ 17–18 s mỗi ứng viên [SUY LUẬN: suy từ 19/72 ứng viên ở ~117 s/thế hệ trong `2026-10-09-three-machines/`, không đo trực tiếp], giả sử W máy giống hệt nhau:

| W | phần thời gian dành cho replay | tăng tốc so với 1 máy (xấp xỉ) |
|---|---|---|
| 10 | ~10% | ~9× |
| 50 | ~35% | ~32× |
| 100 | ~51% | ~49× |
| ∞ | → 100% | trần ≈ 1 + t_eval / t_upd ≈ 95× |

Ý nghĩa thực dụng [SUY LUẬN]:
* Vài chục máy thì ổn. Hàng trăm máy thì một nửa thời gian là replay.
* Đòn bẩy là **workload dài hơn mỗi ứng viên** (t_eval lớn) hoặc **replay rẻ hơn** (nhiễu cấu trúc thấp hạng: một hướng nghiên cứu riêng, đổi thuật toán, ngoài lộ trình này). Máy yếu (1660S: t_upd ≈ 0,51 s) chạm trần sớm gần 3 lần.
* Tải xuống từ máy bên cạnh trong LAN (≈ 10 s/GB trên cáp gigabit [ĐO]) **không** rẻ hơn replay trên GPU khá (≈ 4,5 s ở N = 24 trên 3060), nên "một máy đầu mối mỗi tiệm" không giải quyết trần này. [SUY LUẬN]
* Chưa tính: cập nhật nối tiếp của coordinator (2,4 s [ĐO: STATUS]), thế hệ phải chờ ứng viên chậm nhất, worker rớt giữa chừng, tải của coordinator.

**Tải của coordinator chưa từng đo quá 3 worker.** Server thư viện chuẩn, tối đa 64 kết nối, SQLite một người ghi, worker hỏi lại mỗi 0,25 s khi rảnh [CODE]: 1.000 worker rảnh ở ranh giới thế hệ là cỡ 4.000 yêu cầu/giây qua TLS. [SUY LUẬN] Mô phỏng (TODO `scale-and-spread`) phải đo cái này trước khi tin bất kỳ con số nào về "hàng trăm worker"; có thể cần long-poll (giữ yêu cầu tới khi có việc) hoặc giãn thời gian hỏi.

**Người gia nhập muộn**: tải mô hình gốc (1 GB, một lần, lưu cache) rồi replay G thế hệ × N × t_upd. Với 3060, N = 24: G = 100 → ~7,5 phút; G = 1.000 → ~75 phút. [SUY LUẬN từ số đo] Cần **checkpoint định kỳ** (mỗi K thế hệ) đặt ở VPS/kho lưu trữ để giới hạn thời gian gia nhập; `MAX_CHAIN` mặc định 8 phải được thay bằng quy tắc "tải checkpoint gần nhất rồi replay phần còn lại". [CODE + SUY LUẬN]

## 8. Cài đặt: "tải về, cài, đăng nhập"

| | cách | không admin | rủi ro |
|---|---|---|---|
| WSL2 | môi trường Linux đã kiểm số học | **không** (bật WSL cần admin) [SUY LUẬN] | vụ `nvitop` [ĐO]: hệ thống bên dưới đổi được |
| **Windows bản địa, môi trường Python cục bộ trong thư mục người dùng** (ví dụ `uv` cài Python độc lập + file khóa phiên bản) | không cần admin [SUY LUẬN, chưa thử] | **số học trên Windows bản địa chưa từng kiểm** |
| File chạy đóng gói (PyInstaller...) | không admin | torch + CUDA rất to (~3 GB [BRAINSTORM]), dễ vỡ [SUY LUẬN] |
| Container (Docker) | cần admin | không hợp tiệm net |

**Đề xuất**: một gói cài vào thư mục người dùng, phiên bản khóa cứng (lock file; `pyproject.toml` hôm nay không ghim gì [TODO `ideas-remote-workers`]), chạy được từ USB; mọi lần khởi động chạy lại bộ kiểm nhanh (vì môi trường bên dưới có thể đổi như vụ `nvitop`). Linux và laptop dùng cùng gói. Laptop thêm chính sách người dùng: chỉ chạy khi cắm sạc, giới hạn nhiệt độ GPU, khung giờ. [BRAINSTORM]

Ai làm gói cài, ai phát hành và ký: **câu hỏi mở** (ranh giới track A/B).

## 9. Ranh giới track A và track B (đề xuất)

| thuộc track A (hệ thống lõi) | thuộc track B (sản phẩm) |
|---|---|
| giao thức worker v2: xác thực bằng thông tin thiết bị, `worker_id` suy từ danh tính, báo cáo năng lực, lease/kết quả | tài khoản, đăng nhập (OIDC, device flow), giao diện admin |
| bộ kiểm số học nhanh + danh sách nền tảng đã kiểm + giá trị vàng | chính sách duyệt (admin duyệt tay hay tự động theo quy tắc) |
| quy tắc admission (đủ điều kiện, quan sát, hạ cấp) | chính sách người dùng (giờ chạy, nhiệt độ) hiển thị và lưu ở đâu |
| replay từ checkpoint, đường dữ liệu theo hash | trình cài đặt, phát hành, cập nhật, chữ ký |
| kiểm chéo, cách ly theo thiết bị | thông báo, bảng điều khiển, sự đồng ý của chủ máy / chủ tiệm |
| mô phỏng quy mô | (nếu có) nhiều người dùng gửi nhiều thí nghiệm |

## 10. Đề xuất tóm tắt

1. **Mạng**: cổng HTTPS trên một VPS nhỏ + đường hầm đi ra từ nhà (E). Không VPN trên worker, không tự viết VPN, không mở cổng ở router nhà. Tailscale chỉ còn là đường đối chứng lúc phát triển.
2. **Danh tính**: thông tin xác thực riêng từng thiết bị, coordinator suy `worker_id` từ đó; mã gia nhập một lần ở track A trước, device flow của track B sau.
3. **Admission**: bộ kiểm số học nhanh là cổng cứng; tốc độ được **quan sát** thay vì chỉ dự đoán.
4. **Tái lập**: chính sách chặt, kiểm theo nền tảng.
5. **Tin cậy**: chỉ máy tin được cho tới khi kiểm chéo bằng-nhau-tuyệt-đối được xây và đo.
6. **Quy mô**: đo bằng mô phỏng trước khi hứa hàng trăm worker; biết trước trần do replay.
7. **Thứ tự**: làm trên LAN trước (giai đoạn 1–2), rồi WAN với 3060 thứ hai qua cổng (3), rồi Windows bản địa / 4060 (4), mô phỏng (5), kiểm chéo (6), nhiều nơi rồi tiệm net (7). Chi tiết: `multisite-roadmap.md`.

## 11. Những gì tài liệu này KHÔNG chứng minh
Không có gì ở đây được thử. Không đo độ trễ hay độ ổn định của đường qua VPS; không biết giá VPS; không biết tiệm net thật trông thế nào; không biết Windows bản địa hay Ada có khớp từng bit; con số trần ở mục 7 dựa trên một t_eval suy ra chứ không đo trực tiếp và giả sử các máy giống nhau; track B có thể đã chọn những thứ làm đổi ranh giới ở mục 9.
