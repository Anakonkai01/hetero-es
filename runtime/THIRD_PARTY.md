# THIRD_PARTY — mã, mô hình và thư viện bên ngoài (bản nháp của AI, 08/10/2026)

Theo MASTER §3.4: ghi nguồn gốc, phiên bản, loại sử dụng và giấy phép của mọi thứ không do dự án viết. **Phần "người kiểm tra" và mọi chỗ đánh dấu `CẦN CHỦ DỰ ÁN` chưa được xác nhận.**

## 1. Mã của công trình trước (đã đọc, KHÔNG sao chép)

| Công trình | Nguồn | Giấy phép (theo MASTER §3.4) | Cách dùng | Mã được chép vào repo |
|---|---|---|---|---|
| Evolution Strategies at Scale (Qiu et al.) | arXiv 2509.24372; kho `es-at-scale` | Academic Public License (phi thương mại) | đọc để lấy ý tưởng (mẫu seed nhiễu, z-score, N, sigma, alpha) | không |
| Understanding Evolution Strategies for LLM Reasoning | arXiv 2608.27351; kho `understanding-es` | MIT | trích dẫn kết quả | không |
| Agentic ESOpt | arXiv 2608.17310 | MIT | đọc để lấy ý tưởng (lịch giảm sigma) | không |
| Matching accuracy, different geometry (Hoy et al.) | arXiv 2604.01499 | — | trích dẫn kết quả | không |

Căn cứ cho "không sao chép": ghi chép của phiên 07/10 (STATUS, "ES-at-scale and Agentic-ESOpt were read for ideas: nothing was copied; the clones were in a scratch directory and are gone"). Đây là lời khai của AI đã viết mã; **CẦN CHỦ DỰ ÁN** xác nhận (ví dụ bằng cách tự so một vài file với các kho gốc). Vì Academic Public License ràng buộc cả bản sửa đổi, nếu sau này có bất kỳ đoạn nào hóa ra giống upstream thì phải thêm một dòng vào bảng này (origin URL, commit, file, loại reuse, người kiểm tra).

## 2. Mô hình

| Thành phần | Nguồn | Ghi chú |
|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct`, revision `7ae557604adf67be50417f59c2c2f167def9a775` | Hugging Face | Giấy phép Apache-2.0 theo thẻ mô hình của Qwen (chưa kiểm lại trong phiên này vì không có mạng/không mở thẻ; **CẦN CHỦ DỰ ÁN** hoặc phiên sau xác nhận). Trọng số không nằm trong git. |

## 3. Thư viện Python (giấy phép đọc từ metadata đã cài trong môi trường `heteroes-match`, 08/10/2026)

| Thư viện | Phiên bản | Giấy phép (metadata) | Dùng ở đâu |
|---|---|---|---|
| torch | 2.13.0+cu132 | Apache-2.0 và BSD/MIT/BSL (hỗn hợp, theo metadata) | `src/`, `scripts/` |
| numpy | 2.5.3 | BSD-3-Clause (và 0BSD, MIT, Zlib, CC0) | bộ sinh nhiễu CPU, `src/` |
| transformers | 5.17.0 | Apache-2.0 | nạp mô hình, `generate` |
| safetensors, tokenizers, huggingface-hub | 0.8.0, 0.23.2, 1.33.0 | Apache-2.0 | phụ thuộc của transformers |
| pytest | 9.1.1 | MIT | test |
| hypothesis | 6.168.5 | MPL-2.0 | test sổ cái (tuỳ chọn) |
| simpy | 4.1.2 | MIT | test mô phỏng thời gian (tuỳ chọn) |
| matplotlib | 3.10.9 (python hệ thống) | giấy phép kiểu PSF/matplotlib | chỉ `docs/report/make_figures.py` |

Thư viện chuẩn của Python (sqlite3, http, ...) không liệt kê. Máy 1660S dùng Python 3.14.4 với cùng phiên bản torch và transformers (ghi trong `environment` của mỗi profile).

## 4. Không nằm trong repo nhưng được dùng

- CUDA 13.2 (qua bản dựng torch), trình điều khiển NVIDIA: do nhà cung cấp, không phân phối lại.
- `notebooks/floating_point_testing.ipynb` (chưa theo dõi bởi git): không thuộc báo cáo; **CẦN CHỦ DỰ ÁN** cho biết nguồn nếu muốn đưa vào.

## 5. Quyền sở hữu và dùng AI

Xem `docs/report/REPORT.md` mục 10 và MASTER §16.6. Điều AI biết chắc: phần lớn `src/`, `scripts/`, `tests/`, `docs/` và các README trong `artifacts/` do AI viết theo hướng dẫn của chủ dự án (test trước, kiểm tra đột biến trên bản sao); chủ dự án chưa review gì từ G2 đến nay. Điều AI **không** biết và không được điền thay: ai (người) thiết kế phần nào, phần nào có người thứ hai (nếu có), các nguồn kiến thức ngoài. → `CẦN CHỦ DỰ ÁN`.
