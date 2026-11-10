# Kiểm chứng bài cử chỉ tay — 27/10/2026

Môi trường máy thực hành: Ubuntu 22.04, ROS 2 Humble, Gazebo Fortress,
TurtleBot 4 Lite; MediaPipe 0.10.21, OpenCV 4.11.0, NumPy 1.26.4.

## Đã kiểm tra

- `./setup_gesture.bash`: cài môi trường riêng, tải model chính thức, mở
  Gesture Recognizer thành công, build package bằng colcon.
- 18 kiểm thử tự động qua: chọn chưa chạy, xác nhận một lần rồi hạ tay,
  không tự lặp lại hành vi, hết hạn lựa chọn chưa xác nhận, chống nhiễu/lặp lệnh,
  dừng/hủy, mất luồng camera/timeout, cảm biến không sẵn sàng, đủ 4 chu kỳ, unwrap
  góc vòng tròn, nhận Wave từ chuyển động và phân biệt xòe tay đứng yên.
- Chạy webcam thật qua OpenCV và suy luận MediaPipe; cửa sổ có ảnh/landmarks,
  nhãn, score và trạng thái; `/detected_gesture` có dữ liệu.
- Kiểm tra cuối với webcam và Gazebo chạy đồng thời: nhận 16 bản tin nhận diện
  trong 4 giây, có odometry và scan 640 mẫu; khoảng cách tường gần nhất 9,995 m.
- Công cụ quay hai cửa sổ tạo được MP4 1760 × 720, dài 3 giây; ffprobe đọc
  được stream hoàn chỉnh. Clip này chỉ là thử công cụ ghi hình.
- Gazebo sân trống: controller `joint_state_broadcaster` và
  `diffdrive_controller` active, có odometry và LiDAR; robot khởi động ngoài dock.
- Kiểm thử controller với **nhãn ROS tổng hợp** qua topic thật, sử dụng
  odometry/LiDAR/hazards thật của Gazebo: cả ba hành vi `COMPLETE`, không
  phát lệnh chuyển động khi mới chọn, dừng với Open Palm, Closed Fist và timeout.

Kết quả máy đọc được: [gesture_controller_validation.json](gesture_controller_validation.json).
Lần kiểm thử controller thành công nằm trong
`artifacts/gesture_runs/20261027_075121/`, gồm `controller_integration.json`
và `behavior.jsonl`. Nhãn tổng hợp chỉ dùng kiểm chứng logic điều khiển,
không được trình bày như kết quả nhận diện từ bàn tay thật.

Sau bốn chu kỳ tiến–lùi robot trở về gần vị trí đầu, sai lệch cuối khoảng
3.9 mm theo odometry tại thời điểm hoàn tất. Sau vòng tròn, chênh lệch vị trí
đầu/cuối khoảng 4.3 mm. Đây là số đo trong mô phỏng ở thời điểm báo COMPLETE,
không phải cam kết độ chính xác trên robot vật lý.

## Chưa có video nộp bài đầy đủ

Chưa kiểm chứng đủ sáu cử chỉ bằng người thật đứng trước webcam và chưa quay
video đầy đủ cử chỉ–xác nhận–hành vi. Cần người biểu diễn theo kịch bản trong
[README_GESTURE_CONTROL.md](../README_GESTURE_CONTROL.md). Video thử công cụ
ghi hình chỉ xác minh đường ghi Gazebo + webcam, không thay cho bài nộp.

Chưa kiểm chứng va chạm/vách vực bằng thử nghiệm vật lý hay camera bị rút USB;
các nhánh bảo vệ tương ứng đã được triển khai. Kiểm thử mất luồng camera đã chạy
trong Gazebo bằng ngừng publish nhãn, và các nhánh timeout được kiểm thử tự động.

## Cập nhật xác nhận một lần

Theo yêu cầu mới, Thumbs Up chỉ xác nhận bắt đầu; robot tiếp tục khi hạ tay,
không nhận diện được cử chỉ hoặc không còn tay trong ảnh. Open Palm và
Closed Fist vẫn dừng/hủy ngay. Mất hẳn luồng bản tin camera, lỗi camera
và các điều kiện bảo vệ cảm biến vẫn dừng robot.

Kiểm thử controller hiện gửi Thumbs Up trong 0,7 giây rồi chỉ gửi `No_Hand`
đến khi hoàn tất từng hành vi; thử dừng/hủy sau khi đã hạ tay hơn 0,8 giây.
Kiểm thử phiên bản này đã qua cả ba hành vi, Open Palm, Closed Fist và
timeout khi mất hẳn luồng bản tin. Kết quả và JSON ở trên là của phiên bản mới.

## Các sửa lỗi tích hợp quan trọng

- Truyền namespace rỗng cho URDF và control để controller manager khớp
  `robot_state_publisher` và các topic ROS ở root.
- Chạy Gazebo server và GUI thành hai tiến trình; tránh tình trạng combined
  launcher treo đã gặp khi khởi động lại. Thêm đường dẫn system plugin từ ROS
  để `libign_ros2_control-system.so` được nạp.
- Không coi `BACKUP_LIMIT` như bumper/cliff. Source Create 3 Humble cảnh báo
  khi buffer lùi ≤ 0,05 m; motion_control chặn thật ở buffer 0, tối đa 0,15 m.
  Mỗi đoạn lùi 0,12 m, luôn sau đoạn tiến tương ứng; không tắt safety override.
- Tiếp tục dùng Ogre2 overlay sẵn của workspace để LiDAR hoạt động đúng.

Chi tiết buffer lùi đối chiếu với
[source motion_control_node.cpp của Create 3 Humble](https://github.com/iRobotEducation/create3_sim/blob/humble/irobot_create_common/irobot_create_nodes/src/motion_control_node.cpp).
