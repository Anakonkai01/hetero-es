# HeteroES Lab — hướng dẫn nhanh cho bạn bè (tiếng Việt)

Đây là bản thử nghiệm riêng, chưa phát hành chính thức. Bộ cài **chưa được ký số**, nên Windows sẽ hỏi lại một lần.

Bản đang cung cấp: **lf1-20261012-r5**. Tải trực tiếp tại
**https://lab.heteroes.site/#downloads**; chọn **Worker** để tham gia lab này,
hoặc **Lab Server** nếu muốn dựng lab riêng. Không cần chép file từ máy chủ.

Bạn muốn làm gì?
- **A. Cho lab mượn GPU của bạn** (Worker): đọc phần A.
- **B. Tự dựng một lab riêng** (Lab Server): đọc phần B.

---

## A. Cho mượn GPU (Worker)

**Cần có:** Windows 11 (64-bit) hoặc Linux (64-bit); card NVIDIA có driver mới; khoảng 10 GB trống; mạng Internet cho lần cài đầu (tải khoảng 3–4 GB).

1. **Đăng ký tài khoản.** Mở link lab (hiện là **https://lab.heteroes.site**), bấm *Register an account*. Mật khẩu từ 12 ký tự trở lên. Tài khoản ở trạng thái chờ cho đến khi quản trị viên duyệt.
2. **Tải bộ cài** ngay ở trang chủ, mục *Desktop apps*, hoặc trang *Workers* sau khi đăng nhập (Windows: file `.exe`; Linux: file `.tar.gz`, giải nén rồi mở `heteroes-worker`).
3. **Cài đặt.** Windows hiện cảnh báo "Windows protected your PC" vì bộ cài chưa ký: bấm *More info* rồi *Run anyway*. Nếu báo thiếu DLL, cài *Microsoft Visual C++ x64 runtime* (app có sẵn đường dẫn).
4. **Nhập địa chỉ lab** (cùng link ở bước 1) rồi đăng nhập bằng tài khoản của bạn.
5. Bấm **Install isolated runtime** (tải Python, thư viện, model; chỉ lần đầu). Rồi bấm **Run compatibility check**: máy chạy thử một phép tính GPU và so với kết quả chuẩn. Nếu lỗi, giữ OFF và gửi báo cáo cho quản trị viên.
6. **Đặt tên máy và ghép cặp.** Chờ quản trị viên duyệt thiết bị.
7. **Bật ON** chỉ khi bạn muốn chia sẻ GPU. Mỗi lần mở lại app, trạng thái luôn về OFF.
8. Trước khi tắt máy hoặc trả máy: bấm **Stop safely**, chờ app báo đã dừng, rồi **Quit safely**.

**Máy bạn ở mạng khác với lab thì sao?** Không cần Tailscale. Nếu app không thấy đường mạng riêng của lab, nó tự dùng link công khai và chỉ **bắt kịp bằng replay** (tải vài trăm byte mỗi bước thay vì cả 1 GB trọng số). Đã chạy thử thật trên GPU: job 4 thế hệ hoàn thành, không tải trọng số đầy đủ lần nào.
Giới hạn: máy bạn chỉ được tụt tối đa 64 bước so với lab. Nếu tụt quá, hoặc cần tải đầy đủ trọng số, worker sẽ dừng và báo *needs_private_route*. Lúc đó cài Tailscale (hoặc vào cùng mạng với lab) rồi bật lại.

---

## B. Tự dựng lab riêng (Lab Server)

**Cần có:** một máy làm "văn phòng" (không cần GPU). Linux là bản đã được thử cài sạch; Windows có bộ cài nhưng **chưa được kiểm tra trên máy thật**.

1. Tải **HeteroES Lab Server** từ link lab, cài và mở.
2. Bấm **Install Server** (tải thư viện nhỏ, chỉ lần đầu).
3. Chọn **địa chỉ của máy này** (LAN hoặc Tailscale). **Địa chỉ phải cố định**: hãy đặt IP tĩnh hoặc "DHCP reservation" trong router, vì đổi địa chỉ là cả lab hỏng.
4. Chọn ổ đĩa lưu checkpoint, tạo tài khoản quản trị (mật khẩu từ 12 ký tự).
5. Bấm **Start Server**, rồi **Open lab**. Hàng đợi ban đầu đang *giữ* để tránh chạy ngoài ý muốn: vào *Operations* khi sẵn sàng để mở.
6. Mời người khác tham gia: họ đăng ký trên trang lab của bạn, bạn duyệt tài khoản và thiết bị trong *Operations*.

**Giới hạn hiện tại:**
- **Coordinator** (máy điều phối chạy job) chỉ có trên Linux, phải đạt kiểm tra tương thích và có ít nhất 11000 MB VRAM. Worker r5 có nút *Allow this computer to coordinate experiments*. Địa chỉ riêng của máy này phải tới được từ các Worker. Nếu dựng lab riêng để phục vụ máy khác mạng, người vận hành vẫn phải thiết lập tuyến HTTPS công khai; app chưa tự làm bước này.
- Mạng thường không mã hóa (HTTP). Trên mạng chung (trường, ký túc xá) hãy dùng Tailscale hoặc WireGuard.
- Không cần Internet sau khi cài xong. Lần cài đầu cần tải thư viện, hoặc chép sẵn bộ cache.

---

## Lỗi thường gặp
| Hiện tượng | Cách xử lý |
|---|---|
| Windows chặn bộ cài | *More info* → *Run anyway* (bộ cài chưa ký) |
| Worker báo OFFLINE | Kiểm tra link lab; thử mở link bằng trình duyệt |
| Không vào được lab sau khi máy chủ khởi động lại | Địa chỉ máy chủ có thể đã đổi; đặt IP cố định |
| Lỗi self-test | Cập nhật driver NVIDIA, giữ OFF và gửi báo cáo |
