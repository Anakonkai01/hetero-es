# Danh sách việc: thêm máy thứ ba (RTX 3060 12 GB) — bản nháp của AI, 08/10/2026

Mục tiêu: có một worker thứ ba chạy đúng, rồi đo ba máy so với hai máy (EQ3, mức SUPPORTING). Thứ tự bắt buộc: **chuẩn bị máy → kiểm tra số giống nhau → profile → mới chạy thí nghiệm**. Bỏ bước 2 thì mọi kết quả sau đó không đáng tin.
Đánh dấu: [BẠN] chỉ bạn làm được; [AI] mình làm; [CẢ HAI] cần phối hợp. Mỗi bước có tiêu chí PASS/FAIL.

## Giai đoạn 0 — Mình làm trước khi máy tới (không cần máy)
- [AI] Sửa `cluster_runner.py`, `run_benchmark.py`, `failure_campaign.py` để nhận danh sách worker từ xa (hiện viết cứng hai máy), có test. PASS: test mới xanh, kết quả cấu hình hai máy giữ nguyên.
- [AI] Viết sẵn kịch bản `scripts/setup_worker_machine.sh` kiểm tra điều kiện của máy mới (phiên bản Python/torch/transformers/NumPy, driver, GPU, model snapshot, đường tới coordinator) và in báo cáo PASS/FAIL. Chỉ đọc, không cài gì.
- [AI] Chuẩn bị `git bundle` của nhánh hiện tại.

## Giai đoạn 1 — Chuẩn bị máy [BẠN, mình hướng dẫn từng lệnh]
Cho mình biết trước: hệ điều hành, phiên bản driver NVIDIA (`nvidia-smi`), máy nối mạng thế nào với 5070 Ti (cáp riêng, LAN hay Tailscale), có SSH không.
1. Python ≥ 3.12 trong một môi trường ảo riêng.
2. `torch 2.13.0+cu132`, `transformers 5.17.0`, cùng NumPy với máy tham chiếu (xem `environment` trong profile của 5070 Ti). Driver phải hỗ trợ CUDA 13.2. PASS: `scripts/setup_worker_machine.sh` báo khớp.
3. Mô hình `Qwen/Qwen2.5-0.5B-Instruct` đúng revision `7ae557604adf67be50417f59c2c2f167def9a775` trong cache Hugging Face.
4. Repo: `git fetch` từ bundle, `merge --ff-only`. PASS: `git log -1` trùng commit của 5070 Ti.
5. Mạng: máy 3060 gọi được `http://<địa chỉ 5070 Ti>:8765/v1/health` (cần token). Nếu bị chặn, bạn quyết định có mở cổng không; mình không đổi tường lửa.

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
- Driver không đủ mới cho CUDA 13.2 → có thể phải dùng bản torch khác, khi đó cổng phần mềm từ chối và không còn là so sánh công bằng (ghi nhận chứ không ép).
- GPU Ampere cho kết quả số khác hai GPU kia → FAIL ở giai đoạn 2, là kết quả có giá trị.
- Máy mượn có thể thu hồi giữa chừng: ghi kết quả từng phần ra file, không chờ cuối.
- Không nhớ gì về mật khẩu sudo: mình không cần sudo trên máy 3060.
