# Kết quả kiểm chứng — 2026-10-30

- Build riêng package bằng `colcon build --packages-select hri_multimodal --symlink-install`: thành công trên ROS 2 Humble / Python 3.10.
- `colcon test`: **46 test, 0 failure, 0 error, 0 skipped**.
- `test/check_runtime.py`: **16 kiểm tra qua DDS thực**, gồm startup, robot di chuyển, STOP ưu tiên với confidence thấp, chốt STOP, reset xóa lệnh cũ, mỗi kênh chạy riêng, hết hạn, xung đột, Come here đến người gọi, confidence thấp, câu không biết, JSON lỗi và simulator watchdog sau khi controller bị kill.
- `artifacts/hri_multimodal/runtime_validation.json` lưu từng kết quả và pose. `.log` lưu output của hai node.
- `artifacts/hri_multimodal/demo_48s.mp4`: **1120 × 780, 10 fps, 480 frame, 48.0 giây**, không âm thanh. Các đầu vào được mô phỏng để thể hiện và kiểm tra fusion. Ghi trực tiếp frame Qt bằng ffmpeg.
- `states.jsonl` lưu quyết định và pose trong demo; `arrived.png` xác nhận robot đến gần người gọi; `dashboard.png` là trạng thái kết thúc STOP.
- Đã cài Vosk, sounddevice và mô hình tiếng Anh nhỏ trong `.venv-hri` / `.models/hri`; PortAudio được giải nén cục bộ trong `.hri-runtime`.
- Đã mở được microphone mặc định ở 16 kHz mono và nhận thông báo `Microphone ready`. Adapter thử trong domain 69 riêng, dừng sau 5 giây.
- Vosk nhận đúng `Move forward`, `Come here`, `Stop` từ âm thanh tổng hợp bằng ffmpeg/libflite. Câu phủ định `do not move forward` được nhận thành câu không thuộc lệnh và không kích hoạt chuyển động. Kết quả ở `voice_validation.json`.

## Bổ sung Gazebo và webcam

- World `hri_lab.sdf` hợp lệ qua `ign sdf -k`, không dùng mô hình tải từ Fuel.
- Gazebo Fortress 6.18.0 chạy thật: robot hai bánh, va chạm/ma sát/trọng lực, phòng 8 × 6 m và mục tiêu người gọi cập nhật được.
- `test/check_gazebo_runtime.py`: **13 kiểm tra qua**. Vị trí model thật từ SceneBroadcaster được so sánh với wheel odometry; robot di chuyển và đến người gọi. Các kiểm tra dừng bao gồm Palm pending, Open Palm, chốt STOP, reset khi tay còn xòe, xung đột và mất heartbeat camera.
- Kiểm tra physics inject nhãn cử chỉ/heartbeat trong domain 72, không thay cho thử nhận dạng camera. Kết quả đầy đủ: `artifacts/hri_multimodal/gazebo_validation/runtime.json`.
- Webcam `/dev/video0` và MediaPipe chạy thật, công bố ảnh JPEG/landmarks và heartbeat. Cửa sổ Gazebo, dashboard và webcam đã mở cùng một launch.
- `test/test_vision.py` kiểm tra phân biệt Wave/Open Palm, độ ổn định Thumb Up, nhiều bàn tay và tracking dropout ngắn. Palm pending luôn khóa vận tốc về 0; STOP đã chốt không tự mở.
- `test/check_camera_replay.py` kiểm tra suy luận thực qua video webcam có sẵn. Wave được kiểm tra bằng chuyển động dịch ngang một ảnh bàn tay thực; kết quả ở `camera_replay.json`.
- `artifacts/hri_multimodal/gazebo.png` lưu hình giao diện physics thực. Ảnh/log webcam thô nằm trong thư mục được git-ignore.

Giới hạn: chưa đo độ chính xác nhận giọng nói của người dùng thật; chưa xác nhận trọn ba cử chỉ trong một lượt biểu diễn trực tiếp. Replay/synthetic motion và input tự động được phân biệt rõ với camera trực tiếp. Video 48 giây trước đó vẫn là chế độ 2D. Kiểm chứng mô phỏng không chứng minh an toàn cho robot vật lý.
