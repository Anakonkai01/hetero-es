# Chức năng Backend và Frontend của ứng dụng web HeteroES

- **Mục tiêu:** xác định chức năng của từng phần, từ khái niệm đến công việc cần thực hiện.
- **Phạm vi:** ứng dụng web nhiều người dùng, kết nối với dịch vụ Coordinator để sử dụng khả năng thực thi ES.
- **Trạng thái:** nội dung đã được người dùng duyệt; các mục đánh dấu “Cần thống nhất” chưa phải quyết định cuối cùng.
- **Nguồn định hướng:** [HETEROES_LLM_MASTER.md](../../../../refs/HETEROES_LLM_MASTER.md), mục 7.3 và nội dung thảo luận của nhóm.
- **Notes về nguồn:** tài liệu MASTER nằm tại `IT_Project/refs/`, ngoài repository; liên kết chỉ hoạt động khi giữ cấu trúc thư mục local này, không truy cập được từ repository trên GitHub.
- **Notes:** đây là thiết kế dự kiến, không phải báo cáo chức năng đã triển khai.

## 1. Khái niệm và ranh giới hệ thống

| Thành phần | Ý nghĩa | Chức năng chính |
|---|---|---|
| Frontend | Phần giao diện chạy trong trình duyệt. | Hiển thị thông tin, tiếp nhận thao tác và giao tiếp với backend web. |
| Backend web | Phần xử lý phía máy chủ của ứng dụng web. | Quản lý người dùng, workspace, quyền, dữ liệu ứng dụng và kết nối Coordinator. |
| Coordinator Service | Dịch vụ điều phối thực thi ES. | Quản lý công việc tính toán, trạng thái thực thi và phối hợp với Worker. |
| Worker | Tiến trình thực hiện công việc trên máy có GPU. | Nhận công việc từ Coordinator, tính toán và gửi kết quả. |

- Luồng sử dụng chính: **Frontend ↔ Backend web ↔ Coordinator ↔ Worker**.
- Backend web quản lý việc người dùng sử dụng hệ thống.
- Coordinator quản lý việc thực thi ES.
- Frontend hiển thị trạng thái thực thi dựa trên dữ liệu được cung cấp.
- **Cần thống nhất:** thành phần quản lý hàng đợi experiment.

## 2. Chức năng Backend web

### 2.1. Đăng nhập và phân quyền

- **Khái niệm:** xác định người đang sử dụng hệ thống và kiểm tra họ được phép làm gì.
- **Công việc cần thực hiện:**
  - Cung cấp chức năng đăng nhập, đăng xuất và lấy thông tin phiên đăng nhập.
  - Xác định membership — quan hệ thành viên giữa người dùng và workspace.
  - Kiểm tra quyền theo vai trò Owner, Partner hoặc Viewer trong workspace.
  - Kiểm tra quyền cho từng yêu cầu xem, tạo, sửa, chạy, hủy hoặc tải dữ liệu.
- **Kết quả cần đạt:** người dùng không thể truy cập trái quyền bằng cách gọi API trực tiếp.
- **Cần thống nhất:** quyền chi tiết của từng vai trò.

### 2.2. Lưu thông tin người dùng, workspace và thành viên

- **Khái niệm:** lưu dữ liệu hiện tại để ứng dụng biết người dùng thuộc đâu và có quyền gì.
- **Công việc cần thực hiện:**
  - Lưu thông tin định danh người dùng cần thiết cho ứng dụng.
  - Lưu thông tin và cấu hình workspace.
  - Lưu membership và vai trò của từng thành viên.
  - Lưu quan hệ giữa workspace với tài nguyên được phép sử dụng.
- **Kết quả cần đạt:** dữ liệu vẫn tồn tại sau khi tải lại trang hoặc khởi động lại backend.
- **Notes:** chức năng quản trị tài khoản toàn hệ thống chưa được xác định trong phạm vi này.

### 2.3. Lưu lịch sử thay đổi workspace

- **Khái niệm:** ghi lại các thao tác làm thay đổi workspace.
- **Công việc cần thực hiện:**
  - Ghi người thực hiện, thời điểm, hành động và đối tượng bị thay đổi.
  - Ghi nội dung thay đổi cần thiết để tra cứu.
  - Cung cấp API xem lịch sử theo quyền.
- **(Ví dụ minh họa):** người A đổi tên workspace hoặc thay đổi vai trò của người B.
- **Kết quả cần đạt:** có thể biết ai đã thay đổi cấu hình và thay đổi vào lúc nào.
- **Notes:** không ghi mật khẩu, token hoặc thông tin bí mật vào nhật ký.

### 2.4. Quản lý thông tin experiment và lịch sử thao tác

- **Khái niệm:** quản lý experiment dưới góc nhìn người dùng và workspace.
- **Công việc cần thực hiện:**
  - Lưu tên, workspace, người tạo và cấu hình experiment.
  - Kiểm tra cấu hình trước khi gửi sang Coordinator.
  - Liên kết experiment với mã lần chạy do Coordinator cung cấp.
  - Ghi nhận thao tác tạo, chỉnh sửa, gửi chạy và yêu cầu hủy.
- **Kết quả cần đạt:** xác định được experiment thuộc về ai và tương ứng với lần chạy nào.
- **Cần thống nhất:**
  - Một experiment có một hay nhiều lần chạy?
  - Khi nào được chỉnh sửa cấu hình?
  - Những thao tác nào được hỗ trợ trong phiên bản đầu?

### 2.5. Cung cấp nhật ký và tiến độ thực thi ES

- **Khái niệm:** đưa thông tin thực thi từ Coordinator đến người dùng.
- **Công việc cần thực hiện:**
  - Lấy trạng thái, tiến độ và sự kiện từ Coordinator.
  - Liên kết thông tin thực thi với experiment tương ứng.
  - Cung cấp dữ liệu cho frontend trong phạm vi được phép xem.
  - Nếu lưu bản sao, ghi rõ nguồn và thời điểm cập nhật.
- **Kết quả cần đạt:** phân biệt được thao tác người dùng với sự kiện thực thi.
  - Người dùng yêu cầu hủy chưa có nghĩa experiment đã dừng.
  - Coordinator xác nhận trạng thái thực thi chính thức.
- **Cần thống nhất:** cơ chế nhận dữ liệu và thời gian lưu nhật ký.

### 2.6. Giao tiếp với Coordinator

- **Khái niệm:** chuyển yêu cầu của ứng dụng thành thao tác mà Coordinator hỗ trợ.
- **Công việc cần thực hiện:**
  - Xây một phần chuyên gọi Coordinator.
  - Gửi cấu hình đã được kiểm tra và cho phép thực thi.
  - Nhận mã lần chạy, trạng thái, sự kiện và thông tin kết quả.
  - Gửi yêu cầu hủy nếu Coordinator hỗ trợ.
  - Xử lý lỗi, mất kết nối và thời gian chờ quá lâu.
- **Kết quả cần đạt:** khi Coordinator không phản hồi, ứng dụng báo đúng tình trạng.
- **Cần thống nhất:** cách gửi lại yêu cầu để tránh tạo trùng lần chạy.
- **Notes:** backend web không tự sửa lease, chấp nhận kết quả candidate hoặc điều khiển thuật toán ES.

### 2.7. Giao tiếp với Frontend

- **Khái niệm:** cung cấp API để giao diện lấy dữ liệu và thực hiện thao tác.
- **Công việc cần thực hiện:**
  - Thống nhất đường dẫn API, đầu vào, đầu ra và lỗi.
  - Cung cấp các API cần thiết cho từng luồng sử dụng.
  - Áp dụng phân quyền trước khi trả dữ liệu hoặc thực hiện thay đổi.
  - Trả lỗi đủ rõ để frontend hướng dẫn người dùng.
- **Kết quả cần đạt:** frontend có thể sử dụng cùng một hợp đồng giao tiếp khi chạy mock hoặc backend thật.

### 2.8. Xem và tải kết quả experiment

- **Khái niệm:** giúp người dùng truy cập kết quả và tệp đầu ra theo quyền.
- **Công việc cần thực hiện:**
  - Lưu hoặc lấy danh sách kết quả và tệp gắn với lần chạy.
  - Kiểm tra quyền trước khi cho xem hoặc tải.
  - Cung cấp cách tải tệp từ nơi lưu trữ đã thống nhất.
  - Thông báo khi tệp chưa sẵn sàng hoặc không còn tồn tại.
- **(Ví dụ minh họa):** tải checkpoint — tệp lưu trạng thái mô hình, hoặc metrics — số liệu đo được.
- **Cần thống nhất:** vị trí lưu tệp và cách backend truy cập tệp.

## 3. Chức năng Frontend

| Phần chức năng | Công việc cần thực hiện | Kết quả người dùng nhận được |
|---|---|---|
| Đăng nhập và phiên sử dụng | Hiển thị đăng nhập, đăng xuất và xử lý phiên hết hạn. | Biết mình đang sử dụng tài khoản nào. |
| Chọn workspace | Hiển thị workspace được phép truy cập và workspace đang chọn. | Biết đang thao tác trong không gian nào. |
| Hiển thị theo quyền | Hiển thị trang và thao tác phù hợp với quyền backend cung cấp. | Biết mình được làm gì. |
| Workspace và thành viên | Hiển thị cấu hình, thành viên và biểu mẫu thay đổi theo quyền. | Quản lý workspace trong phạm vi được phép. |
| Tài nguyên GPU và Worker | Hiển thị tài nguyên được phép xem, trạng thái và khả năng. | Biết tài nguyên nào có thể sử dụng. |
| Experiment | Hiển thị danh sách, chi tiết, biểu mẫu cấu hình và thao tác được hỗ trợ. | Tạo và sử dụng experiment thuận tiện. |
| Tiến độ thực thi | Hiển thị trạng thái, generation, candidate, attempt và sự kiện cần thiết. | Theo dõi công việc đang diễn ra. |
| Kết quả và tệp đầu ra | Hiển thị số liệu, danh sách tệp và thao tác tải. | Xem và sử dụng kết quả. |
| Lịch sử thao tác | Hiển thị thay đổi workspace và thao tác experiment theo quyền. | Tra cứu hoạt động đã diễn ra. |
| Trạng thái giao diện | Xử lý đang tải, dữ liệu trống, lỗi, mất kết nối và thiếu quyền. | Hiểu tình trạng hiện tại và thao tác tiếp theo. |

- Frontend không tự thực thi thuật toán ES hoặc phân công candidate cho Worker.
- Việc ẩn nút trên giao diện không thay thế kiểm tra quyền ở backend.
- Thuật ngữ thực thi cần có giải thích tiếng Việt dễ hiểu.

## 4. Tổ chức Frontend để dễ thay đổi

- **(Đề xuất của trợ lý):** tổ chức các phần theo bảng dưới đây.

| Phần | Chức năng |
|---|---|
| Page — trang | Tổ chức nội dung và luồng thao tác của một trang. |
| Component — phần giao diện | Hiển thị một phần nội dung hoặc tiếp nhận thao tác. |
| Hook — hàm dùng logic React | Quản lý dữ liệu, trạng thái tải, lỗi và cập nhật. |
| API service — phần gọi API | Gửi yêu cầu và chuyển dữ liệu API sang dạng giao diện cần. |
| Types — mô tả kiểu dữ liệu | Mô tả cấu trúc dữ liệu được sử dụng. |
| Mocks — dữ liệu và phản hồi giả lập | Mô phỏng API để phát triển trước khi backend sẵn sàng. |

- Component không đọc trực tiếp dữ liệu mock.
- Cấu hình địa chỉ API được quản lý tập trung.
- Khi cấu trúc API thay đổi, chuyển đổi dữ liệu tại phần giao tiếp khi phù hợp.
- **Notes:** thay đổi quy tắc nghiệp vụ vẫn có thể yêu cầu sửa giao diện.

## 5. Hai hợp đồng giao tiếp cần thống nhất

| Hợp đồng | Nội dung cần xác định |
|---|---|
| Frontend ↔ Backend web | Thao tác người dùng, dữ liệu hiển thị, quyền và lỗi. |
| Backend web ↔ Coordinator | Cấu hình thực thi, mã lần chạy, trạng thái, sự kiện, hủy và kết quả. |

- **Data format — định dạng dữ liệu:** tên trường, kiểu dữ liệu, trường bắt buộc và giá trị được phép.
- **Data contract — thỏa thuận dữ liệu:** định dạng và ý nghĩa của dữ liệu.
- **API contract — thỏa thuận giao tiếp:** thao tác, đầu vào, đầu ra, lỗi và hành vi.
- **(Ví dụ minh họa):**
  - `run_id`: mã định danh lần chạy do Coordinator cung cấp.
  - Thời gian cập nhật: giúp giao diện biết dữ liệu được ghi nhận lúc nào.
  - Phản hồi yêu cầu hủy: phải phân biệt “đã tiếp nhận yêu cầu” với “đã dừng”.

## 6. Các điểm chưa thống nhất

- Bên quản lý hàng đợi experiment.
- Quyền cụ thể của Owner, Partner và Viewer.
- Quan hệ giữa experiment và lần chạy.
- Phạm vi tài nguyên GPU của từng workspace.
- Cấu hình và thao tác Coordinator hỗ trợ.
- Trạng thái thực thi và ý nghĩa từng trạng thái.
- Cơ chế cập nhật tiến độ.
- Vị trí lưu và cách tải tệp đầu ra.
- Thời gian lưu lịch sử và nhật ký.

## 7. Thứ tự thực hiện đề xuất

- **Luồng sử dụng:** chuỗi bước để người dùng hoàn thành một hoạt động, từ thao tác trên giao diện đến xử lý ở backend và trả kết quả.
- **(Ví dụ minh họa):** chọn experiment → gửi yêu cầu lấy chi tiết → kiểm tra quyền → lấy dữ liệu → hiển thị chi tiết hoặc lỗi.
- **(Đề xuất của trợ lý):** thực hiện theo từng hoạt động cụ thể như sau.

1. Chọn một hoạt động cụ thể của người dùng, mô tả các bước từ thao tác trên giao diện đến xử lý ở backend và trả kết quả; xác định quyền liên quan.
2. Thống nhất API và dữ liệu tối thiểu cho hoạt động đó.
3. Thiết kế giao diện và thực hiện bằng mock.
4. Xây backend lưu dữ liệu và kiểm tra quyền.
5. Kết nối Coordinator thông qua phần giao tiếp riêng.
6. Kiểm tra toàn bộ luồng, gồm thành công, lỗi và thiếu quyền.

- **Notes:** lặp lại theo từng luồng; không cần chốt toàn bộ hệ thống trước khi bắt đầu.
- **Cần thống nhất:** trách nhiệm hàng đợi trước khi hoàn thiện luồng gửi chạy và xếp hàng.
