# HeteroES — Workspace Authentication & Authorization

- Ngày ghi nhận: 01/10/2026.
- Loại tài liệu: ghi chú thảo luận.
- Trạng thái: đã thống nhất tên role; quyền chi tiết còn cần chốt.
- Phạm vi: xác thực và phân quyền cấp workspace.
  - Chưa đặc tả quản lý tài khoản toàn hệ thống.

## 1. Các role đã thống nhất

- Owner.
- Partner.
- Viewer.
- Notes: MASTER hiện sử dụng tên Admin, Researcher và Viewer.
- (Đề xuất của trợ lý) Mã role trong code là `OWNER`, `PARTNER`, `VIEWER`.
  - Chưa khóa mã role với backend.
- Notes: thống nhất tên role chưa đồng nghĩa thống nhất toàn bộ quyền.

## 2. Các khái niệm

- Identity: danh tính tài khoản, nhận diện bằng `userId`.
- Authentication: xác thực danh tính qua đăng nhập/session.
- Workspace: không gian cộng tác và phạm vi áp dụng quyền.
- Membership: liên kết user với workspace.
- Role: vai trò của user tại workspace, gắn với membership.
- Permission: quyền thực hiện một hành động.
- Authorization: kiểm tra quyền thực hiện hành động trên tài nguyên cụ thể.
- Policy: quy tắc xét membership, role, ownership và trạng thái tài nguyên.
- Notes: Owner của workspace khác chủ sở hữu experiment.
  - Partner vẫn có thể sở hữu experiment do mình tạo.

## 3. Mô hình membership

- (Đề xuất của trợ lý) Dùng Workspace-scoped RBAC.
  - Phân quyền theo role trong từng workspace.
  - Bổ sung điều kiện ownership và trạng thái tài nguyên.
- (Đề xuất của trợ lý) Một user có thể tham gia nhiều workspace.
- (Đề xuất của trợ lý) Mỗi cặp user–workspace có một membership.
  - Mỗi membership có một role.
- (Đề xuất của trợ lý) Quyền giữa các workspace độc lập.
- (Đề xuất của trợ lý) Membership hợp lệ là điều kiện truy cập dữ liệu riêng của workspace.
- (Ví dụ minh họa) Khang có các vai trò khác nhau theo workspace.
  - Lab A: Owner.
  - Lab B: Partner.
  - Lab C: Viewer.

## 4. Ý nghĩa và quyền từng role

- Notes: quyền trong mục này là đề xuất, chưa được chốt.

### 4.1. Owner

- (Đề xuất của trợ lý) Quản lý hoạt động product trong workspace.
- Xem cluster, Workers và admission.
- Xem experiments, queue và live runs.
- Xem/tải results và artifacts theo policy dữ liệu.
- Tạo experiment.
- Sửa cấu hình draft của mọi experiment nếu policy cho phép.
- Submit mọi experiment nếu policy cho phép.
- Cancel job đang chờ của mọi thành viên.
- Yêu cầu cancel run đang chạy của mọi thành viên.
- Quản lý memberships và roles.
  - Thêm hoặc loại thành viên khỏi workspace.
  - Đổi role của thành viên.
- Quản lý worker visibility/settings ở mức product nếu policy cho phép.
- Notes: số lượng Owner và cơ chế chuyển quyền chưa chốt.

### 4.2. Partner

- (Đề xuất của trợ lý) Thực hiện experiments trong workspace.
- Xem cluster, Workers và admission.
- Xem experiments, queue và live runs.
- Xem/tải results và artifacts theo policy dữ liệu.
- Tạo experiment.
- Sửa cấu hình draft của experiment mình sở hữu.
- Submit experiment mình sở hữu.
- Cancel job đang chờ của mình.
- Yêu cầu cancel run đang chạy của mình.
- Không quản lý memberships hoặc roles.
- Notes: giới hạn thao tác trên experiment của mình cần được xác nhận.
- Notes: quyền Add Worker và thay đổi worker settings chưa chốt.

### 4.3. Viewer

- (Đề xuất của trợ lý) Theo dõi thông tin được phép.
- Xem cluster, Workers và admission trong phạm vi được phép.
- Xem experiments, queue và live runs trong phạm vi được phép.
- Xem/tải results và artifacts theo policy dữ liệu.
- Không tạo, sửa hoặc submit experiment.
- Không cancel job hoặc run.
- Không quản lý memberships, roles hoặc worker settings.

## 5. Quy tắc kiểm tra quyền

- (Đề xuất của trợ lý) Backend kiểm tra quyền cho từng hành động.
  - Xác thực user.
  - Xác định workspace thực tế của tài nguyên.
  - Kiểm tra membership.
  - Kiểm tra permission theo role.
  - Kiểm tra ownership.
  - Kiểm tra trạng thái tài nguyên.
  - Cho phép hoặc từ chối.
- Frontend hiển thị hoặc khóa thao tác theo quyền.
  - Backend vẫn phải kiểm tra request.
- Không tin role, owner hoặc workspace do client khai báo để cấp quyền.
- Notes: quản lý membership không phải quản lý tài khoản toàn hệ thống.

## 6. Ranh giới Product–Runtime

- Theo MASTER, runtime sở hữu trạng thái generation, candidate, attempt và lease.
- Theo MASTER, runtime quyết định commit và model version.
- Không role người dùng nào được sửa trực tiếp các trạng thái runtime trên.
- Product queue điều phối experiments.
  - Candidate scheduling thuộc Coordinator.
- Theo MASTER, cấu hình gửi runtime là bất biến.
  - Cách sửa draft hoặc chạy lại cần contract cụ thể.
- Cancel được tiếp nhận chưa đồng nghĩa run đã dừng.
  - Giao diện chờ trạng thái runtime xác nhận.

## 7. Cần thống nhất

- Workspace có một hay nhiều Owner?
- Ai tạo workspace?
  - Người tạo có tự trở thành Owner không?
- Có cho phép chuyển quyền Owner không?
- Ai thêm Partner/Viewer?
  - Cơ chế join/invite của phiên bản đầu là gì?
- Có hỗ trợ một user tham gia nhiều workspace không?
- Có dùng một role trên mỗi membership không?
- Partner chỉ quản lý experiment của mình hay của mọi thành viên?
- Experiments/results mặc định chia sẻ trong workspace hay riêng tư?
- Quyền tải checkpoint/artifacts có giống quyền xem không?
- Khi loại thành viên, xử lý công việc và dữ liệu của họ thế nào?
  - Queue entries.
  - Runs đang chạy.
  - Experiments và artifacts.
- Có bảo vệ Owner cuối cùng khỏi bị loại hoặc hạ quyền không?
- Role nào được Add Worker hoặc thay đổi product settings?

## 8. Bước tiếp theo

- Chốt quyền theo từng user flow nhỏ.
- Thống nhất API contract tối thiểu với backend.
- Dùng mock để kiểm tra hành vi giao diện.
- Kiểm tra quyền từ chối request tại API khi có implementation backend.
- Notes: tài liệu này không phải bằng chứng Auth đã được triển khai.

## 9. Nguồn tham chiếu

- [HETEROES_LLM_MASTER.md](../../../../refs/HETEROES_LLM_MASTER.md).
  - Mục 7.3: product architecture và phân quyền.
  - Mục 16.3–16.4: roadmap và ranh giới subsystem.
- [HETEROES_LLM_STATUS.md](../../../../refs/HETEROES_LLM_STATUS.md).
  - Tiến độ được ghi nhận ngày 29/09/2026.
- Hội thoại hiện tại.
  - Tên role Owner, Partner, Viewer.
  - Phạm vi workspace và cách phát triển Agile.
- Notes: MASTER và STATUS nằm tại `IT_Project/refs/`, ngoài repository; các liên kết chỉ hoạt động theo cấu trúc thư mục local này, không truy cập được từ repository trên GitHub.
