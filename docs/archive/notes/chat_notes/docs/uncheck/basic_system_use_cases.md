# Chức năng cơ bản và luồng sử dụng của ứng dụng web HeteroES

- **Mục tiêu:** xác định người dùng cần làm được gì trong phiên bản đầu.
- **Thuộc mục:** mục 1 — Thống nhất phạm vi và các quyết định còn mở.
- **Trạng thái tài liệu:** bản thảo đã được duyệt để lưu; phạm vi chức năng chưa chốt, giữ trong `uncheck/`.
- **Nguồn:** [tài liệu chức năng](../../web_service_functionality.md) và [checklist tổng](../../web_service_todolist.md).
- **Phạm vi:** ứng dụng web nhiều người dùng, kết nối dịch vụ Coordinator để thực hiện thí nghiệm ES.
- **Notes:** các chức năng dưới đây là đề xuất phạm vi phiên bản đầu; quyền chi tiết và khả năng Coordinator cần được xác nhận.

## 1. Khái niệm

| Khái niệm | Ý nghĩa |
|---|---|
| Use case — trường hợp sử dụng | Một việc người dùng thực hiện để đạt mục tiêu cụ thể. |
| Luồng sử dụng | Chuỗi bước từ thao tác người dùng đến xử lý và nhận kết quả. |
| Workspace — không gian làm việc | Nơi tổ chức thành viên, experiment và quyền truy cập tài nguyên. |
| Experiment — thí nghiệm ES | Thông tin thí nghiệm, gồm tên, cấu hình và người sở hữu. |
| Lần chạy | Một lần thực thi experiment, có tiến độ và kết quả riêng. |
| Coordinator | Dịch vụ điều phối thực thi ES và cung cấp trạng thái, kết quả. |

## 2. Mục tiêu phiên bản đầu

- **(Đề xuất của trợ lý):** hỗ trợ một nhóm nhỏ cùng sử dụng tài nguyên GPU để thực hiện experiment.
- Người dùng có thể vào workspace được phép truy cập.
- Người có quyền có thể chuẩn bị và gửi chạy experiment.
- Người dùng có thể theo dõi tiến độ và xem kết quả theo quyền.
- Hệ thống ghi nhận các thay đổi và thao tác cần thiết để tra cứu.

## 3. Luồng sử dụng trung tâm

1. Đăng nhập.
2. Chọn workspace.
3. Xem tài nguyên GPU.
4. Tạo và lưu cấu hình experiment.
5. Gửi yêu cầu chạy.
6. Theo dõi trạng thái, tiến độ và lỗi.
7. Xem kết quả và tải tệp được phép truy cập.

- Một người dùng không nhất thiết thực hiện tất cả các bước.
  - **(Ví dụ minh họa):** Viewer chỉ xem experiment và kết quả được phép.
- **Cần thống nhất:** trạng thái chờ chạy và thành phần quản lý hàng đợi.

## 4. Các chức năng bắt buộc đề xuất

### UC-01. Đăng nhập và chọn workspace

- **Mục tiêu:** vào đúng không gian làm việc.
- **Người thực hiện:** người có tài khoản.
- **Các bước:**
  - Đăng nhập.
  - Xem các workspace được tham gia.
  - Chọn workspace.
- **Kết quả:** giao diện hiển thị workspace và vai trò hiện tại.
- **Trường hợp cần xử lý:**
  - Đăng nhập không thành công hoặc phiên hết hạn.
  - Người dùng chưa thuộc workspace nào.
  - Người dùng không còn quyền truy cập workspace.

### UC-02. Xem và quản lý workspace

- **Mục tiêu:** xem cấu hình và thành viên; thay đổi trong phạm vi được phép.
- **Người thực hiện:** thành viên workspace; quyền thay đổi cần được chốt.
- **Các bước:**
  - Xem thông tin workspace và danh sách thành viên.
  - Chỉnh sửa nội dung được phép.
  - Lưu và nhận kết quả.
- **Kết quả:** thay đổi được lưu và ghi nhật ký.
- **Trường hợp cần xử lý:**
  - Dữ liệu không hợp lệ.
  - Không đủ quyền hoặc quyền đã thay đổi.
- **Cần thống nhất:** phiên bản đầu hỗ trợ thêm, bỏ thành viên và đổi vai trò đến mức nào.

### UC-03. Xem tài nguyên GPU và Worker

- **Mục tiêu:** biết tài nguyên có thể sử dụng và tình trạng hiện tại.
- **Người thực hiện:** thành viên có quyền xem tài nguyên.
- **Các bước:**
  - Xem danh sách Worker.
  - Mở chi tiết khả năng và trạng thái.
- **Kết quả:** người dùng hiểu tài nguyên nào đang sẵn sàng hoặc chưa thể sử dụng.
- **Trường hợp cần xử lý:**
  - Chưa có tài nguyên.
  - Không lấy được trạng thái mới từ Coordinator.
- **Cần thống nhất:** tài nguyên được chia sẻ giữa các workspace như thế nào.

### UC-04. Tạo và lưu experiment

- **Mục tiêu:** chuẩn bị cấu hình thí nghiệm trước khi thực thi.
- **Người thực hiện:** thành viên có quyền tạo experiment.
- **Các bước:**
  - Nhập tên và cấu hình được hỗ trợ.
  - Kiểm tra dữ liệu.
  - Lưu experiment.
- **Kết quả:** experiment có mã định danh, workspace và người sở hữu.
- **Trường hợp cần xử lý:**
  - Thiếu hoặc sai cấu hình.
  - Sử dụng tài nguyên không được phép.
- **Cần thống nhất:** các trường cấu hình và thời điểm được chỉnh sửa.

### UC-05. Gửi chạy experiment

- **Mục tiêu:** yêu cầu thực thi cấu hình đã chuẩn bị.
- **Người thực hiện:** thành viên có quyền chạy experiment.
- **Các bước:**
  - Chọn experiment và gửi yêu cầu.
  - Backend kiểm tra quyền và cấu hình.
  - Hệ thống tiếp nhận theo cơ chế đã thống nhất.
- **Kết quả:** người dùng nhận trạng thái rõ ràng và mã theo dõi khi có.
- **Trường hợp cần xử lý:**
  - Cấu hình bị từ chối.
  - Coordinator mất kết nối.
  - Yêu cầu bị gửi lặp.
- **Cần thống nhất:** hàng đợi, cách chọn tài nguyên và quan hệ experiment với lần chạy.
- **Notes:** tiếp nhận yêu cầu không đồng nghĩa đã bắt đầu chạy.

### UC-06. Theo dõi thực thi

- **Mục tiêu:** biết experiment đang diễn ra như thế nào.
- **Người thực hiện:** thành viên có quyền xem experiment.
- **Các bước:**
  - Mở experiment và lần chạy tương ứng.
  - Xem trạng thái, tiến độ và sự kiện.
  - Mở chi tiết thực thi khi cần.
- **Kết quả:** phân biệt được đang chạy, hoàn thành, lỗi hoặc chưa có thông tin mới.
- **Trường hợp cần xử lý:**
  - Chưa có dữ liệu thực thi.
  - Dữ liệu cập nhật bị gián đoạn.
- **Notes:** Coordinator là nguồn xác nhận trạng thái thực thi.

### UC-07. Yêu cầu hủy experiment

- **Mục tiêu:** yêu cầu dừng công việc không còn cần thiết.
- **Người thực hiện:** thành viên có quyền hủy.
- **Các bước:**
  - Gửi và xác nhận yêu cầu hủy.
  - Theo dõi phản hồi và trạng thái tiếp theo.
- **Kết quả:** hiển thị rõ yêu cầu đã được tiếp nhận hay công việc đã dừng.
- **Trường hợp cần xử lý:**
  - Experiment đã kết thúc.
  - Trạng thái hiện tại không cho phép hủy.
  - Không xác định được kết quả yêu cầu do mất kết nối.
- **Cần thống nhất:** khả năng hủy của Coordinator.
- **Notes:** chỉ đưa vào phạm vi bắt buộc sau khi xác nhận dịch vụ hỗ trợ.

### UC-08. Xem và tải kết quả

- **Mục tiêu:** sử dụng kết quả của experiment.
- **Người thực hiện:** thành viên có quyền xem hoặc tải.
- **Các bước:**
  - Xem kết quả và số liệu.
  - Xem danh sách tệp đầu ra.
  - Chọn tệp và tải xuống.
- **Kết quả:** nhận dữ liệu hoặc tệp thuộc đúng lần chạy.
- **Trường hợp cần xử lý:**
  - Chưa có kết quả.
  - Tệp chưa sẵn sàng hoặc không còn tồn tại.
  - Không đủ quyền tải.
- **Cần thống nhất:** loại đầu ra, vị trí lưu và cách truy cập.

### UC-09. Tra cứu lịch sử thao tác

- **Mục tiêu:** biết ai đã thay đổi hoặc thực hiện thao tác nào.
- **Người thực hiện:** thành viên có quyền xem lịch sử.
- **Các bước:**
  - Chọn lịch sử workspace hoặc experiment.
  - Xem người thực hiện, thời điểm, hành động và kết quả.
- **Kết quả:** tra cứu được thay đổi cấu hình và thao tác experiment.
- **Notes:** lịch sử người dùng khác với nhật ký tính toán từ Coordinator.

## 5. Các chức năng đề xuất làm sau

- So sánh nhiều experiment.
- Tùy chỉnh biểu đồ và bố cục cá nhân.
- Xuất báo cáo tổng hợp.
- Thông báo qua email hoặc dịch vụ bên ngoài.
- Quản trị tài khoản toàn hệ thống đầy đủ.
- Quản lý hạn mức hoặc tính phí sử dụng.
- **Notes:** danh sách này cần duyệt; không phải cam kết triển khai.

## 6. Điều kiện hoàn thành phiên bản đầu

- Người dùng hoàn thành được luồng trung tâm trong phạm vi quyền.
- Backend kiểm tra quyền khi truy cập dữ liệu và thực hiện thao tác.
- Thông tin workspace và experiment được lưu bền vững.
- Các thay đổi thuộc phạm vi được ghi nhật ký.
- Trạng thái thực thi và kết quả gắn với đúng lần chạy.
- Lỗi, thiếu quyền và mất kết nối được hiển thị rõ.
- Có bằng chứng kiểm tra với Coordinator thật cho phần tích hợp.
- **Notes:** chạy bằng mock chứng minh luồng ứng dụng, chưa chứng minh tích hợp Coordinator thật.

## 7. Cần thống nhất trước khi chốt phạm vi

- Use case nào bắt buộc, use case nào làm sau?
- Quyền thực hiện từng use case thuộc vai trò nào?
- Coordinator hỗ trợ những thao tác và dữ liệu nào?
- Bên nào quản lý hàng đợi experiment?
- Một experiment có bao nhiêu lần chạy?
- Người dùng chọn tài nguyên theo cách nào?
- Những kết quả và tệp nào phải được hỗ trợ?
