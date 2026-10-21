# Kế hoạch sửa toàn diện: máy chết giữa run, agent không tự chạy lại, run đêm bị kẹt

Viết 2026-10-22 ~06:30 +07, branch `feat/gsm8k-demo`. Nguồn: `docs/evidence/2026-10-22-gsm8k-demo/RESULTS.md` (tier 1, 2,
2b), code đã đọc lại sáng nay (`backend/agent_scheduling.py`, `runtime/src/heteroes/product/run_supervisor.py`, `agent.py`).

## Tóm tắt một câu

Phần tính toán đúng (tier 1, 2, 2b đều khớp từng bit, mọi audit khớp). Cái hỏng là **vòng đời máy**: một máy chết hoặc
khởi động lại giữa chừng thì run đã xong không được "chốt", GPU của *mọi* máy bị giữ mãi, và agent không tự chạy lại sau
khi máy khởi động. Kế hoạch này sửa đúng chỗ đó, rồi mới chạy lại.

## Giải thích nhanh vài chữ

- **Chốt run (release):** khi run xong, lab phải "trả" các máy (xóa giữ chỗ GPU) thì run khác mới bắt đầu được. Lab chỉ
  trả khi *chắc chắn* mọi tiến trình của run đã dừng, để không bao giờ có hai run cùng chạy trên một GPU.
- **DRAINING:** run đã tính xong nhưng đang chờ các máy xác nhận "đã dừng".
- **LEFT:** máy đã rời run (chủ tắt Contribution, hoặc bị gỡ).
- **Coordinator:** máy điều phối run (5070ti-nhan). **Agent:** chương trình nền trên mỗi máy, nhận lệnh từ lab.

## Danh sách lỗi

| # | Lỗi | Nơi | Mức | Trạng thái |
| - | --- | --- | --- | ---------- |
| L1 | Máy **đã rời run** rồi chết → lab giữ GPU của run mãi | lab `release_left_members` | nặng | đã sửa trên branch `1a11763`, chưa deploy |
| L2 | Máy **chưa rời** mà chết (ví dụ 1660S lúc 23:39) → lab không bao giờ chốt run, vì `_release_confirmed` đòi *mọi* máy liên lạc trong 30 giây và tự báo "đã dừng" | lab `_release_confirmed` | **nặng, chưa sửa** | mới phát hiện khi đọc lại code sáng nay; `1a11763` không phủ trường hợp này |
| L3 | Coordinator chờ máy chết xác nhận dừng mãi → kẹt DRAINING ngay trên coordinator (đang xảy ra với tier 2b) | coordinator `poll_workers` | nặng | đã sửa trên branch `e8f26a2` (10 phút không liên lạc = coi là đã dừng), chưa deploy; **đổi một luật an toàn có chủ đích → cần bạn duyệt** |
| L4 | Máy mất mạng (chưa chết) quá 10 phút, rồi có mạng lại: lab đã trả GPU cho run khác, nhưng agent **không dừng** worker cũ của run đã chốt (`agent.py` chỉ ghi "released", không dừng tiến trình) → có thể hai run trên một GPU | agent | nặng, **điều kiện để L1–L3 an toàn** | chưa sửa |
| L5 | Agent CLI (Linux, WSL) **không tự chạy sau khi máy khởi động lại**: 1660S khởi động lại 23:42, ngồi không đến 00:14 lúc AI chạy tay; máy Quang (WSL) cũng phải chạy tay | bộ cài `heteroes-worker install` | nặng cho run đêm | chưa sửa |
| L6 | Contribution luôn về OFF sau khi khởi động (thiết kế có chủ đích: chủ máy phải bật lại) → máy tự khởi động lại thì không quay lại run được dù agent có chạy | agent + lab | quyết định sản phẩm | **cần bạn quyết** |
| L7 | `/api/v1/events` dựng lại sự kiện của mọi run mỗi lần gọi → HTTP 524 khi đang chạy | lab | vừa | chưa sửa (demo đã né bằng timeline từng run) |
| L8 | Đường public không chở được dataset (Thao tắt Tailscale thì không chạy được run có dataset) | agent `study/prepare.py` | giới hạn thiết kế | để sau, cần bạn quyết |
| L9 | Script demo báo "recovered" khi máy thật ra đã chết trước lúc tắt (tier 2b b1) | `.scratch` / `stage_events.py` | lỗi công cụ của AI | chưa sửa |
| L10 | Máy Quang hỏng phần cứng (WHEA fatal, 3 lần sập/30 ngày); 1660S cũng sập 23:39 chưa điều tra | phần cứng | vận hành | Quang: loại khỏi run dài; 1660S: điều tra log |
| L11 | Chạy đêm bị đứng vì AI ngồi chờ bạn đồng ý, và vì bộ lọc quyền của Claude Code chặn thao tác sửa file trạng thái / DB | cách làm việc | nặng cho run đêm | đã ghi nhớ; cần cho phép trước (giai đoạn 6) |

"Rejoin phải `add` tay sau khi LEFT" (ADR-009) **không phải lỗi**, là thiết kế; kịch bản demo đã kỳ vọng sai cơ chế.

## Kế hoạch, theo thứ tự

### Giai đoạn 0: gỡ kẹt tier 2b hiện tại (5 phút, không đổi code)

Hiện coordinator DRAINING vì máy Quang, lab giữ GPU của 5 máy. Hai cách:

- **A (khuyên dùng, nhanh):** bạn chạy một lệnh `!` mình đưa (vì bộ lọc quyền chặn mình): sao lưu `state.json` của
  coordinator, đánh dấu riêng quang-3060 `left/đã dừng` → coordinator chuyển COMPLETED → chạy `release_tier2b.py --apply`
  (bạn đã duyệt) → lab trả máy.
- **B:** không gỡ tay, để bản sửa ở giai đoạn 2 tự gỡ sau khi deploy. Chậm hơn, nhưng là phép thử thật cho bản sửa.

### Giai đoạn 1: chặn nguy cơ "hai run trên một GPU" (L4), làm trước vì L1–L3 dựa vào nó

1. Agent: khi lab báo một assignment đã `released`, agent **dừng ngay** mọi worker/coordinator của assignment đó còn sống
   trên máy (dùng lại `_worker(ar, "stop")` / `manager.cancel`), rồi mới nhận lệnh mới.
2. Lab: không giao run mới cho một máy vừa liên lạc lại cho đến khi nó báo không còn tiến trình của assignment cũ.
3. Test: giả lập máy mất mạng 11 phút rồi có lại → worker cũ bị dừng, run mới chỉ bắt đầu sau đó.

### Giai đoạn 2: run xong là chốt được, dù có máy chết (L1, L2, L3)

1. Giữ `1a11763` (L1) và `e8f26a2` (L3).
2. Sửa L2 trong `_release_confirmed`: một máy worker (không phải coordinator) mất liên lạc ≥ 10 phút **và** coordinator
   đã ghi nó `lost`/đã dừng → bỏ qua máy đó khi chốt, trả GPU của nó luôn. Coordinator chết thì vẫn giữ nguyên (không có
   ai xác nhận gì cả).
3. Dùng **một** hằng số 10 phút chung cho lab và coordinator, ghi vào ADR-009 (thêm mục "máy chết").
4. Test đơn vị cho từng trường hợp + mutation check, như mọi lần.

### Giai đoạn 3: máy tự quay lại sau khi khởi động (L5, L6)

1. Linux: `heteroes-worker install` tạo systemd **user service** + `loginctl enable-linger` (để chạy cả khi không ai đăng
   nhập); `uninstall` gỡ nó. Cần sudo một lần cho linger.
2. WSL (máy Quang): Windows Scheduled Task "lúc đăng nhập / lúc khởi động" gọi `wsl -e` chạy agent (kèm
   `LD_LIBRARY_PATH=/usr/lib/wsl/lib`).
3. Windows desktop app (Thao): kiểm lại xem đã tự chạy lúc đăng nhập chưa.
4. L6, chờ bạn quyết (xem dưới). Nếu chọn "giữ ON", lab thêm cờ theo từng máy, chủ máy bật trong giao diện.

### Giai đoạn 4: lab nhẹ hơn khi đang chạy (L7)

`/api/v1/events` trả theo trang và theo `since` (chỉ sự kiện mới), có cache theo từng run; test thời gian trả lời khi có
5 run lớn trong DB.

### Giai đoạn 5: thử thật trên lab thử nghiệm riêng trước, rồi deploy

1. Chạy toàn bộ test backend + runtime.
2. Thử "rút dây" thật trên lab thử nghiệm riêng (cổng 8790, không phải lab thật): chạy run 3 máy, ngắt mạng một máy
   worker giữa chừng (tắt Tailscale), kiểm: run vẫn xong, coordinator COMPLETED, lab chốt trong ≤ 11 phút, cắm lại thì
   worker cũ bị dừng. Lặp lại với "khởi động lại máy" để kiểm agent tự chạy.
3. Deploy lên lab thật kiểu flag day: sao lưu DB + app, có lệnh rollback, bạn duyệt trước khi bấm.
4. Cập nhật agent trên cả 5 máy.

### Giai đoạn 6: chạy lại cho đúng

1. Tier 2b lặp lại (5 gen, có cảnh rút dây thật một máy) → phải chốt run tự động, không gỡ tay.
2. Tier 3 (G=300) chạy đêm với mọi máy còn sống, không có máy Quang.
3. Trước khi bạn đi ngủ: bạn cho phép sẵn các thao tác AI cần (sửa `state.json`, release DB, khởi động lại agent qua SSH)
   bằng permission rule, để không có gì phải chờ.

### Giai đoạn 7 (sau): L8 đường public chở dataset; sửa script demo (L9); điều tra 1660S sập (L10)

## Quyết định của bạn (2026-10-22 sáng)

1. L3: **đồng ý, chỉ sau khi giai đoạn 1 xong** (luật 10 phút bật cùng lúc với cơ chế dừng worker cũ).
2. L6: **cho chủ máy chọn "giữ ON sau khi khởi động"**, mặc định vẫn OFF.
3. Giai đoạn 0: **bỏ**, không gỡ tay; bản sửa deploy xong sẽ tự gỡ tier 2b (cũng là phép thử thật của bản sửa).
4. L8: **làm trong đợt này** → thành giai đoạn 4b (dưới), trước giai đoạn 5.

### Giai đoạn 4b: đường public chở được dataset (L8)

Thiết kế trước, bạn duyệt rồi mới code: file study (dataset) đi qua đường public của lab có giới hạn kích thước, kiểm
sha256 đã khai trong grant, chỉ cho assignment đang giữ máy đó. Thử bằng cách tắt Tailscale trên máy Thao như tier 1.

## Mở rộng phạm vi (bạn, 2026-10-22 sáng): bộ cài, CLI, chunk theo máy

Quyết định:

- **Linux chỉ còn CLI.** Bỏ hẳn app desktop Linux của **cả Worker lẫn Server** (bản tar.gz/AppImage/unpacked phát
  hành). Lab trên Linux chạy như service bằng lệnh, đúng như lab thật đang chạy (`deploy/heteroes-lab.user.service`).
- **Windows chỉ còn app desktop, bỏ đường WSL.** Máy Quang chuyển từ WSL + CLI sang app Worker desktop.
- **CLI Linux:** làm cả 4 nhóm cải thiện (dưới).
- **Chunk theo từng máy, ghi vào sổ (ledger).**

### Giai đoạn 3 (viết lại): bộ cài

**3a. Bỏ app desktop Linux.** `scripts/build-apps.sh` thôi phát hành bản Linux của `desktop/worker` và `desktop/server`;
bỏ `pack:linux`, link tải trên web/lab, các đoạn trong `docs/quickstart-vi.md` và handoff hướng dẫn cài bản đó. Lỗi
backlog #1 (tar.gz không khởi động trên 5070) tự hết. *Mặc định mình chọn, bạn có thể đổi:* vẫn giữ bản Linux unpacked
**chỉ để chạy test tự động** (`check-linux-server.cjs`, `check-linux-packaged.cjs` kiểm giao diện app trên máy này),
không phát hành. Nếu bỏ luôn thì app desktop chỉ còn kiểm được qua Wine/máy Windows thật. Lab thử nghiệm riêng (cổng 8790,
hiện đang chạy bằng app Server Linux unpacked) chuyển sang chạy bằng service như lab thật.

**3b. CLI Linux (`heteroes-worker`): làm lại trải nghiệm, không chỉ vá.**

*Hiện trạng đã soi (`runtime/src/heteroes/product/worker_cli.py`, 387 dòng; `scripts/install-worker.sh.in`), và đêm qua
đã đụng thật:*

| # | Chỗ tệ | Bằng chứng |
| - | ------ | ---------- |
| C1 | 4 lệnh rời (`install`, `selftest`, `join`, `run`) phải gõ đúng thứ tự, mỗi bước in "next: …" rồi bỏ đó | cài máy Nhựt mất nhiều lượt |
| C2 | `run` chạy tiền cảnh, muốn chạy nền phải `nohup setsid … &` tay; không tự chạy sau khởi động | 1660S ngồi không 30 phút |
| C3 | Không bật/tắt Contribution được từ CLI (chỉ qua web; agent cũ có lệnh `on/off` đòi mật khẩu chủ, CLI mới không có) | đêm qua AI phải gọi API tay |
| C4 | Lỗi là mã khô: `LAB_HTTP_409`, `ALREADY_PAIRED`, `COMPATIBILITY_FAILED`, `PIP_INSTALL_FAILED`, không nói nguyên nhân hay cách sửa | join nhầm cổng 8790 chỉ ra `LAB_HTTP_409` |
| C5 | `status` đổ JSON thô; không nói được câu "máy đang làm gì": đã duyệt chưa, ON hay OFF, đang trong run nào, thế hệ mấy, liên lạc lab lần cuối khi nào | |
| C6 | `selftest` im lặng nhiều phút (`capture_output=True`), không tiến độ, không ước lượng | |
| C7 | Tải file bằng `urllib`: không thử lại, không tải tiếp, không thanh tiến độ (gói CUDA hàng trăm MB, 56 gói) | backlog #2 |
| C8 | `join`: không cho biết đang vào lab nào; `--coordinator` bắt gõ `--host` IP tay; không chờ duyệt, phải sang web | nhầm lab 8790 |
| C9 | Không có `logs`, `stop`, `restart`, `update`, `uninstall`, `forget`, `rename`, `doctor` | backlog #3 |
| C10 | Đĩa phình mãi: `artifacts` 13 GB trên 5070 này, `downloads` giữ 2.7 GB wheel sau khi cài xong, runtime cũ không dọn | `du` sáng nay |
| C11 | Không kiểm trước driver NVIDIA/CUDA/đĩa/mạng tới lab trước khi tải ~3 GB; hỏng thì hỏng giữa chừng | |
| C12 | Cập nhật = chạy lại `curl | bash`, không biết bản đang chạy có cũ hơn lab yêu cầu không | |

*Thiết kế mới:*

1. **Một lệnh cài là xong:** `curl -fsSL https://lab.heteroes.site/install-worker.sh | bash` tự chạy luôn trình
   `heteroes-worker setup`: kiểm máy (`doctor`) → tải và cài (tiến độ, thử lại, tải tiếp) → self-test (có tiến độ) → hỏi
   địa chỉ lab (mặc định lab đã tải script) và mã ghép đôi → **hiện tên lab + chủ lab, hỏi xác nhận** → cài service →
   chờ duyệt (in "đang chờ quản trị viên duyệt…", tự đi tiếp khi được duyệt) → hỏi có bật ON không. Dừng giữa chừng thì
   chạy lại `setup` đi tiếp từ bước dở. Có chế độ không tương tác cho cài hàng loạt (`--lab`, mã đọc từ file/stdin).
2. **Service, không tiền cảnh:** systemd user service + linger; `start`, `stop`, `restart`, `logs [-f]`. `run` giữ lại
   cho debug.
3. **Bật/tắt ngay ở máy:** `heteroes-worker on [--keep-after-reboot]`, `off`. Xác thực bằng chủ máy (đăng nhập một lần
   bằng thiết bị-mã trên web, không gõ mật khẩu vào terminal), hoặc lab cho phép máy đã duyệt tự bật nếu chủ đã tick
   "giữ ON".
4. **`status` người đọc được** (JSON chỉ khi `--json`), ví dụ:
   ```
   5070ti-nhut · lab.heteroes.site · đã duyệt · ON (giữ sau khởi động)
   Đang chạy: GSM8K tier 3 · thế hệ 41/300 · ứng viên vừa xong 18.2 s
   Lab liên lạc 2 s trước · GPU RTX 5070 Ti 9.1/16 GB · runtime 9a553d2 (mới nhất)
   ```
5. **Lỗi có câu và cách sửa**, giữ mã ở cuối để tra: ví dụ "Lab này không nhận máy (HTTP 409). Có thể bạn đang trỏ tới
   lab thử nghiệm cũ ở cổng 8790; lab thật là https://lab.heteroes.site. [LAB_HTTP_409]".
6. **Quản lý:** `rename`, `forget` (bỏ ghép đôi, xóa token), `update` (so phiên bản với lab, tải bản mới, khởi động lại
   service khi không đang trong run), `uninstall` (gỡ service, hỏi có giữ model/dữ liệu không), `doctor` (driver,
   CUDA, đĩa, giờ hệ thống, mạng tới lab và tới coordinator, Tailscale), `clean` + tự dọn: xóa wheel sau khi cài, xóa
   artifacts của assignment đã released quá N ngày, runtime cũ không dùng.
7. **Coordinator:** `--coordinator` tự dò IP Tailscale, chỉ hỏi khi có nhiều lựa chọn.
8. Ngôn ngữ thông báo: tiếng Anh (như web), mã lỗi giữ nguyên.
9. Test: unit test từng lệnh (lab giả), test `setup` dừng giữa chừng rồi chạy tiếp; thử thật trên máy Nhựt và 1660S:
   gỡ sạch → `curl | bash` một lệnh → khởi động lại máy → tự online, tự ON nếu "giữ ON", tự quay lại run.

**3c. Windows: chỉ app desktop.** App Worker tự chạy khi đăng nhập (kiểm lại; thêm nếu chưa có), có tùy chọn "giữ ON sau
khởi động"; bỏ hướng dẫn WSL. Máy Quang: gỡ agent WSL, cài app Worker. Máy Thao: cập nhật app.

### Giai đoạn 8: chunk theo từng máy

Hiện tại: `evaluation.chunk` là một số cố định trong recipe cho mọi máy (`v3/documents.py`, `v3/options.py`
`EXACT_CHUNKS = {"float32": (16, 32, 64), "float16": (1,)}`); 1660S (6 GB) quyết định cho cả nhóm.

Cách làm (đã chọn):

1. Recipe khai **danh sách chunk cho phép** (mỗi giá trị đã qua probe khớp chéo GPU), thay cho một số duy nhất.
2. Mỗi máy chọn chunk lớn nhất trong danh sách vừa VRAM của nó (đo ở self-test, có thể ghi đè bằng tay).
3. Mỗi kết quả ứng viên ghi **chunk đã dùng** vào ledger.
4. Audit: chỉ giao cho máy chạy được chunk đó, và chạy lại **đúng chunk đó**. Kiểm parity (`verify_managed_run.py
   --regenerate`) cũng dùng chunk ghi trong ledger.
5. Replay trọng số không cần chunk (chỉ dùng seed + hệ số), nên không đổi.
6. Tài liệu `runtime/docs/numerical-contract.md` + ADR mới: phần thưởng là hàm của (ứng viên, batch, chunk); đổi chunk có
   thể lệch ~1 token / 768 bài, chấp nhận được về mặt ES vì audit vẫn kiểm đúng từng bit.
7. Đo: probe chunk 128 trên 5070 Ti (RUNTIME-TODO `chunk-128`) để biết máy 16 GB có lợi thật bao nhiêu; chunk mới chỉ
   được vào danh sách khi probe khớp chéo GPU.
8. Test: run 3 máy chunk khác nhau (5070 Ti 64, 3060 32, 1660S 16) → audit khớp, parity ALL EQUAL, thời gian mỗi ứng viên
   của 5070 Ti giảm.

### Thứ tự tổng thể (mới)

1 (dừng worker cũ) → 2 (chốt run khi máy chết) → 3 (bộ cài, CLI, Windows) → 4 (events nhẹ) → 4b (đường public chở
dataset) → 5 (rút dây thử trên lab riêng, deploy có rollback) → 6 (tier 2b lặp lại, tier 3 đêm) → 8 (chunk theo máy, một
đợt deploy riêng vì đổi định dạng recipe/ledger) → 7 (script demo, 1660S).

## Câu hỏi ban đầu (đã trả lời ở trên)

1. **L3, luật an toàn:** đồng ý "10 phút không liên lạc = coi như đã dừng" không? (Khuyên: đồng ý, *với điều kiện* giai đoạn
   1 xong trước, vì giai đoạn 1 mới là thứ bảo đảm không bao giờ có hai run trên một GPU.)
2. **L6:** máy khởi động lại thì Contribution (a) vẫn về OFF như hiện nay, hay (b) cho chủ máy chọn "giữ ON sau khi khởi
   động"? (Khuyên: (b), mặc định vẫn OFF.)
3. **Giai đoạn 0:** gỡ tay ngay (A) hay để bản sửa gỡ (B)?
4. **L8** có làm trong đợt này không? (Khuyên: để sau.)
