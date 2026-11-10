# Validation — hri_object_reference

Đã kiểm tra ngày **30/10/2026**, Ubuntu 22.04 / ROS 2 Humble (Asia/Ho_Chi_Minh).

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| `colcon build --symlink-install --packages-select hri_object_reference` | PASS | Package, executable, resource index, launch và config |
| `colcon test --packages-select hri_object_reference` | **44 passed** | Hình học tia, ràng buộc lời nói, mơ hồ, mâu thuẫn, xác nhận, thời hạn, cảnh thay đổi, trích màu, kéo chuột, lọc ngón trỏ/cảnh thật và tiếng Việt |
| ROS integration, domain 169 | **17/17 PASS** | Topic DDS, service reset, ghép hai kênh, snapshot, hỏi lại, target một lần, confidence, xác nhận tiếng Việt, camera/mic lỗi và timeout |
| Demo Qt thật, domain 170 | PASS | Đủ bốn bước, 2 event target BLUE, 2 event hỏi lại, GUI/controller thoát sạch |
| Video và ảnh demo | PASS | AVI/MP4 đọc được, 181 frame, 4 ảnh tình huống đọc được |

Các ca ROS đã kiểm tra:

1. Chỉ BLUE + câu nói chung → chọn BLUE.
2. Cập nhật cảnh không tạo target lặp.
3. Chỉ giữa hai vật → hỏi lại, 0 target.
4. Nói RED, chỉ BLUE → hỏi lại, 0 target.
5. Xác nhận với request ID cũ → từ chối.
6. Xác nhận BLUE cho câu hỏi hiện tại → chọn BLUE.
7. Lời nói đến trước tia → chờ chỉ.
8. Tia mới đến sau lời nói → chọn BLUE.
9. Snapshot `ray:null` không lấy tia độc lập đã lưu trước đó.
10. Đổi cảnh làm mất hiệu lực xác nhận cũ.
11. Vector chỉ bằng 0 → từ chối đầu vào, không có target.
12. Không cập nhật cảnh hơn 1 giây → WAITING, không có target.
13. “Lấy vật màu đỏ” nhưng chỉ BLUE → hỏi lại.
14. Bản chép lời có confidence thấp → không xác nhận.
15. “Xác nhận màu xanh dương” với confidence hợp lệ → chọn BLUE.
16. Camera lỗi/chưa sẵn sàng → chặn target.
17. Microphone lỗi/chưa sẵn sàng → chặn target.

Unit tests cũng kiểm tra khoảng mất cảnh rồi khôi phục mà chưa có timer tick: xác nhận cũ vẫn bị hủy; câu phủ định và câu chứa tên màu nhưng không phải lệnh không tạo lựa chọn. Test perception di chuyển pixel vật độc lập với hàm dựng ảnh và kiểm tra tâm phát hiện thay đổi theo.

Bằng chứng đã tạo trong workspace:

- [Video demo MP4](../../artifacts/hri_object_reference/demo_check_20261030_180039/20261030_180041_067181/demo.mp4).
- [Chọn đúng](../../artifacts/hri_object_reference/demo_check_20261030_180039/20261030_180041_067181/01_selected.png).
- [Tia chỉ giữa hai vật](../../artifacts/hri_object_reference/demo_check_20261030_180039/20261030_180041_067181/02_ambiguous.png).
- [Lời nói và chỉ tay mâu thuẫn](../../artifacts/hri_object_reference/demo_check_20261030_180039/20261030_180041_067181/03_conflict.png).
- [Sau khi xác nhận](../../artifacts/hri_object_reference/demo_check_20261030_180039/20261030_180041_067181/04_confirmed.png).
- [Log controller gồm các lần hỏi lại](../../artifacts/hri_object_reference/demo_check_20261030_180039/events_1793358041101080333.jsonl).
- [Kết quả demo](../../artifacts/hri_object_reference/demo_check_20261030_180039/results.json).
- [Kết quả ROS runtime](../../artifacts/hri_object_reference/runtime_results.json).

Video/demo tự động ở trên dùng **ảnh mô phỏng + tia chuột + text**. Màu và tâm vật thực sự được trích từ ảnh; thao tác chỉ/lời nói trong demo tự động được tạo sẵn. Các ca xác nhận giọng nói trong ROS integration dùng JSON transcript tạo sẵn, không được tính là đo chất lượng STT.

## Bổ sung webcam + microphone tiếng Việt

Đã cài model Vosk `vosk-model-small-vn-0.4`, mở `/dev/video0` qua MediaPipe Hands và mở mic nội bộ qua PortAudio/PulseAudio. Live launch đồng thời khởi động controller, webcam, STT và dashboard; đóng dashboard sẽ dừng các thiết bị. Dashboard live đã mở và hiển thị luồng camera/mic trên desktop.

Đã đo tín hiệu mic tại mức thu 100%: RMS khoảng 28.417, tỷ lệ mẫu có biên độ ≥32.000 là **56,89%**, bị clipping. Giảm mức thu hệ thống xuống **35%**; phép đo lại RMS khoảng 3.631, **0% clipping**. Thay đổi này chỉ thực hiện trên máy hiện tại, không được tự động áp dụng bởi script.

Pipeline chỉ xuất ray sau ≥3 frame ngón trỏ ổn định ít nhất 0,2 giây, từ chối hai bàn tay và bàn tay mở. Cảnh thật cần một vật mỗi màu ổn định qua 3 frame; giữ tâm đo trong ngưỡng nhiễu nhỏ, mất vật/đổi vị trí thì không tiếp tục dùng khóa cũ. Mất sức khỏe camera hoặc mic chặn phát target.

[Báo cáo phần cứng live](../../artifacts/hri_object_reference/live/hardware_smoke.json) được tạo bằng `test/check_live_smoke.py`, chỉ lưu thống kê, không lưu audio thô. Dữ liệu live được `.gitignore` để tránh đưa ghi hình/lời nói thật vào source tree.

Lần kiểm tra cuối nhận **151 trạng thái camera khỏe, 75 ảnh webcam, 26 trạng thái mic khỏe**, model tiếng Việt nạp thành công và không ghi nhận clipping. Có 2 lần audio overrun khi camera/STT và demo GUI cùng hoạt động; đoạn audio trễ được bỏ và recognizer reset, không thực thi lệnh từ hàng đợi cũ. Bộ đệm mic đã tăng lên 200 ms để giảm overflow. Đây vẫn là giới hạn có thể gây bỏ lỡ câu nói khi máy bận, cần thử lại câu nếu không hiện bản chép lời cuối.

**Chưa xác minh**: chọn vật bằng ba vật thật và ngón trỏ thật trong một lượt có nhãn, độ chính xác của câu lệnh do người dùng nói, nhận góc 3D/camera chiều sâu hoặc gắp vật lý. Lần kiểm tra thiết bị chưa thấy đủ ba vật màu; hệ thống giữ WAITING. Không suy ra độ chính xác nhận dạng từ việc luồng thiết bị đang hoạt động.

## Chế độ mặc định: vật ảo + camera/mic thật

Theo yêu cầu dùng vật ảo, `live.launch.py` mặc định `scene_source=simulation`. Dashboard hiển thị ba vật ảo và ảnh webcam nhỏ, camera chỉ tạo tia ngón trỏ; microphone tiếp tục nhận tiếng Việt thật. Đã kiểm tra lại 44 unit tests và chạy live: có 3 vật trong cảnh, camera/mic cùng sẵn sàng, 136 thông báo camera khỏe, 69 ảnh, 33 thông báo mic khỏe và 7 frame có tia chỉ ổn định. Không có clipping; có 1 lần audio overrun được bỏ. Chưa có câu lệnh người dùng được chấp nhận trong cửa sổ đo, nên không coi đây là lượt chọn vật hoàn chỉnh. Báo cáo `live/hardware_smoke.json` hiện là lần chạy vật ảo này.
