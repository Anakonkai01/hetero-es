# Danh sách việc: thêm máy thứ ba (RTX 3060 12 GB) — bản nháp của AI, 08/10/2026

Mục tiêu: có một worker thứ ba chạy đúng, rồi đo ba máy so với hai máy (EQ3, mức SUPPORTING). Thứ tự bắt buộc: **chuẩn bị máy → kiểm tra số giống nhau → profile → mới chạy thí nghiệm**. Bỏ bước 2 thì mọi kết quả sau đó không đáng tin.
Đánh dấu: [BẠN] chỉ bạn làm được; [AI] mình làm; [CẢ HAI] cần phối hợp. Mỗi bước có tiêu chí PASS/FAIL.

## Giai đoạn 0 — Mình làm trước khi máy tới (không cần máy)
- [AI] Sửa `cluster_runner.py`, `run_benchmark.py`, `failure_campaign.py` để nhận danh sách worker từ xa (hiện viết cứng hai máy), có test. PASS: test mới xanh, kết quả cấu hình hai máy giữ nguyên.
- [AI] Viết sẵn kịch bản `scripts/setup_worker_machine.sh` kiểm tra điều kiện của máy mới (phiên bản Python/torch/transformers/NumPy, driver, GPU, model snapshot, đường tới coordinator) và in báo cáo PASS/FAIL. Chỉ đọc, không cài gì.
- [AI] Chuẩn bị `git bundle` của nhánh hiện tại.

## Giai đoạn 1 — Chuẩn bị máy Windows 11 [BẠN làm theo lệnh của mình]
Máy chạy Windows 11 nên dùng **WSL2** (Ubuntu chạy bên trong Windows, dùng GPU qua driver Windows): cùng bản torch Linux mà hệ thống đã kiểm số học, không phải cài lại hệ điều hành. Đường dự phòng là Python thuần trên Windows, chỉ dùng nếu WSL2 không chạy được, và khi đó coi là nền tảng mới cần kiểm số học lại từ đầu.

Việc chuẩn bị trên Windows (cần quyền quản trị, có thể phải khởi động lại một lần):
0. Trong Windows: tắt chế độ ngủ và tắt ngủ đông khi cắm điện (nếu không máy sẽ ngắt giữa lúc chạy); cắm sạc nếu là laptop; đóng game và ứng dụng chiếm GPU.
1. PowerShell quản trị: `wsl --install -d Ubuntu-24.04`, khởi động lại nếu được yêu cầu, tạo tài khoản Ubuntu. Ubuntu 24.04 có sẵn Python 3.12.
2. Driver NVIDIA bản mới nhất ở phía Windows (KHÔNG cài driver trong WSL). PASS: trong Ubuntu `nvidia-smi` thấy RTX 3060 và dòng "CUDA Version" từ 13.2 trở lên. Nếu thấp hơn: dừng, báo mình (torch cu132 sẽ không chạy và cổng phần mềm sẽ từ chối).
3. Trong Ubuntu: `python3 -m venv`, cài đúng `torch 2.13.0+cu132`, `transformers 5.17.0` và NumPy cùng bản với 5070 Ti (mình đưa lệnh chính xác, lấy từ trường `environment` của profile). PASS: `scripts/setup_worker_machine.sh` báo khớp mọi phiên bản.
4. Mô hình `Qwen/Qwen2.5-0.5B-Instruct` đúng revision `7ae557604adf67be50417f59c2c2f167def9a775` trong cache Hugging Face của Ubuntu (khoảng 1 GB tải về).
5. Repo: `git fetch` từ bundle, `merge --ff-only`. PASS: `git log -1` trùng commit của 5070 Ti.
6. Mạng: WSL2 chỉ cần gọi RA được `http://<địa chỉ 5070 Ti>:8765/v1/health` (worker kéo việc, không cần mở cổng nào ở máy 3060). Địa chỉ này phụ thuộc cách hai máy nối nhau (cáp, cùng mạng nhà hay Tailscale): bạn cho mình biết khi có máy. Nếu cổng 8765 trên 5070 Ti không mở cho địa chỉ đó, bạn quyết định có mở không; mình không đổi tường lửa.

## Giai đoạn 2 — Kiểm tra số học [CẢ HAI]
1. [BẠN] Chạy bộ test trên 3060 với mô hình thật. PASS: không có test đỏ (số test bỏ qua giống 1660S).
2. [AI] Kiểm engine nhiễu CUDA: `cuda_engine_crossgpu.py` trên 3060 và so JSON với 5070 Ti và 1660S. PASS: mọi hash và fingerprint **bằng nhau từng bit**. FAIL = dừng, ghi nhận (đây là phát hiện, không phải lỗi phải giấu).
3. [AI] Kiểm chéo GPU của đánh giá FP32 (`cross_gpu_sweep.py`, cùng cấu hình G6). PASS: 0 phần thưởng khác và (mục tiêu) 0 văn bản khác. Có lệch thì kết quả của cụm phụ thuộc máy chấm → báo bạn, chưa chạy tiếp.

## Giai đoạn 3 — Profile và admission [AI]
1. Profile 3060 với đúng cấu hình của các lần đo trước (`cot_l1_q128`, engine CUDA, 8 ứng viên probe, chunk 1 và 64, `--measure-update`, `--sync-url`). Chạy ngầm; ước tính 1–1,5 giờ vì 3060 nhanh hơn 1660S.
2. Dự đoán admission cặp 5070 Ti–3060 TRƯỚC khi chạy, ghi file không sửa.

## Giai đoạn 4 — Thí nghiệm [AI]
1. B0 (5070 Ti một mình), hai máy (5070 Ti + 3060), ba máy (5070 Ti + 1660S + 3060), N = 24, 3 thế hệ, ≥ 3 lần chạy mỗi điều kiện nếu thời gian cho phép.
2. Kiểm tra hash cuối **bằng nhau giữa mọi điều kiện** (nếu không: dừng, so lại theo giai đoạn 2).
3. Đo replay `auto` so với đồng bộ đầy đủ trên đường mạng của máy này.
4. Một kịch bản lỗi: kill worker 3060 giữa lúc giữ ứng viên.

## Giai đoạn 5 — Ghi chép [AI]
README của thư mục bằng chứng (nói rõ cái gì KHÔNG chứng minh: một lần mượn máy, ít lần lặp, mạng khác cáp), cập nhật EQ3 trong `CLAIMS_AUDIT.md` từ `NOT_RUN` thành MỘT PHẦN, STATUS, báo cáo, commit trên nhánh mới.

## Rủi ro đã biết
- WSL2 không bật được (BIOS tắt ảo hoá, Windows bản Home cũ, không có quyền quản trị): thử Python thuần trên Windows, ghi rõ là nền tảng mới, chạy lại toàn bộ giai đoạn 2.
- Driver không đủ mới cho CUDA 13.2 → có thể phải dùng bản torch khác, khi đó cổng phần mềm từ chối và không còn là so sánh công bằng (ghi nhận chứ không ép).
- GPU Ampere cho kết quả số khác hai GPU kia → FAIL ở giai đoạn 2, là kết quả có giá trị.
- Máy mượn có thể thu hồi giữa chừng: ghi kết quả từng phần ra file, không chờ cuối.
- Không nhớ gì về mật khẩu sudo: mình không cần sudo trên máy 3060.
