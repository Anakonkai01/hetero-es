# Thí nghiệm HeteroES trên lab — cách chạy

Thư mục này chứa các thí nghiệm của đề tài dưới dạng notebook (tiếng Việt). Mỗi notebook chạy theo đúng luồng của
người dùng lab: đăng nhập → chọn mô hình, dữ liệu, bộ chấm → gửi run lên lab → lab chia việc cho các GPU → xem kết quả.

| Notebook | Nội dung |
|---|---|
| `00-chuan-bi.ipynb` | Đăng nhập lab, xem các GPU, thêm một máy GPU (lệnh cài, mã ghép), duyệt máy, kiểm thử GPU, lỗi hay gặp |
| `e1-gsm8k-qwen05.ipynb` | GSM8K × Qwen2.5-0.5B-Instruct, 512 token |
| `e3-gsm8k-qwen15.ipynb` | GSM8K × Qwen2.5-1.5B-Instruct, 512 token |
| `e4-countdown-qwen15.ipynb` | Countdown × Qwen2.5-1.5B-Instruct, 384 token, hai đoạn (đoạn 2 chạy tiếp từ thế hệ 110) |
| `e5-countdown-qwen05.ipynb` | Countdown × Qwen2.5-0.5B-Instruct, 384 token (chạy lại qua lab run ngoài lab ngày 24/11) |
| `tong-hop.ipynb` | Bảng kết quả, tốc độ 1 GPU so với nhiều GPU, bài học từ lần 1 |
| `v1/` | Lần 1 (đêm 24 → 25/11): notebook, kết quả và quyết định, giữ lại để so sánh |

## Mỗi notebook thí nghiệm gồm

1. **Chuẩn bị**: kết nối lab, liệt kê GPU.
2. **Dữ liệu**: tạo các dòng train / validation / test → `Dataset.from_rows` (lab ghim mã băm từng phần).
3. **Mô hình**: `Model.from_hf(repo, revision)` ghim một commit Hugging Face; mỗi máy tự tải và kiểm SHA-256 từng tệp.
4. **Bộ chấm**: bộ chấm khai báo có sẵn của lab (`boxed-number` hoặc `countdown`), thử trên vài câu trả lời mẫu.
5. **Cấu hình**: `ESConfig` (32 candidate, σ = 0,001, α = 5·10⁻⁴, bộ suy luận nghiêm ngặt `strict_b22_v1`).
6. **Chạy trên lab**: `ESTrainer.submit(lab, coordinator, workers)`, rồi chờ. Dừng sớm khi validation không vượt mức
   tốt nhất trong 2 lần chấm liên tiếp (`runner.wait_or_stop`). Thêm một run ngắn 6 thế hệ chỉ trên một GPU
   để có mốc tốc độ.
7. **Quá trình học**: reward train và validation theo thế hệ, số candidate mỗi máy chấm.
8. **Chấm test một lần**: mô hình gốc và checkpoint được chọn bằng validation; McNemar, khoảng tin cậy bootstrap, tỉ lệ
   đúng trên các câu trả lời xong.
9. **Ví dụ trước / sau**, và **lưu tóm tắt** vào `results/` cho notebook tổng hợp.

## Chạy lại và demo

- Mặc định (`CHAY_MOI = False`), notebook **gắn lại** vào các run đã có (mã run trong `state/<tên>.json`), nên chạy lại
  chỉ mất vài phút và không tốn GPU. Điểm test đã chấm được lưu cạnh dữ liệu run nên không chấm lại.
- Đặt `CHAY_MOI = True` để chạy một run mới vài thế hệ (demo trực tiếp).
- Các đoạn và lý do chọn tham số nằm ở `decisions/<tên>.json`. Thêm một đoạn vào đó rồi chạy lại notebook = chạy tiếp từ
  trọng số cuối đã kiểm chứng của đoạn trước.
- Notebook được sinh từ `build_experiments.py` (sửa ở đó, không sửa tay notebook):

```bash
.venv-notebook/bin/python runtime/notebooks/experiments/build_experiments.py            # tất cả
.venv-notebook/bin/python runtime/notebooks/experiments/build_experiments.py tong-hop   # chỉ một notebook
```

- Chạy một notebook đến hết và giữ output (máy có GPU, kernel `heteroes-experiments`):

```bash
cd runtime/notebooks/experiments
../../../.venv-notebook/bin/jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=heteroes-experiments --ExecutePreprocessor.timeout=-1 e5-countdown-qwen05.ipynb
```

## Vì sao không có E2

E2 dự kiến là GSM8K × SmolLM2-1.7B (họ Llama). Mô hình này không dùng GQA (32 đầu KV), nên bộ suy luận nghiêm ngặt cần
khoảng 6,1 GB cho lô 8 câu, vượt ngân sách 4,8 GB của decoder trên RTX 3060 12 GB; Llama 3.2 dùng RoPE `llama3` mà
decoder chưa hỗ trợ. Bộ suy luận nghiêm ngặt hiện cần mô hình có GQA và RoPE mặc định (Qwen2, Llama và Mistral loại đó)
để chạy trên GPU 12 GB.

## Yêu cầu

- Phiên lab: `python3 scripts/lab-login.py` (12 giờ; notebook đang chạy tự đọc lại phiên mới).
- Chấm test chạy trên GPU của máy chạy notebook (RTX 30 trở lên, như mọi GPU của run).
- Dữ liệu run nằm ngoài repo, ở `~/heteroes-experiments/<tên>/`; cache Hugging Face sạch ở
  `~/heteroes-experiments/hf-cache`.
- Bảng tốc độ đọc ledger của coordinator, nên chỉ có số khi notebook chạy trên máy coordinator.
