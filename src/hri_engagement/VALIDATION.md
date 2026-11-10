# Validation — hri_engagement

Đã chạy trên Ubuntu 22.04 / ROS 2 Humble ngày **30/10/2026** (Asia/Ho_Chi_Minh).

| Kiểm tra | Kết quả | Phạm vi xác minh |
|---|---|---|
| `colcon build --symlink-install --packages-select hri_engagement` | PASS | Package, entry points, resource index, launch và cấu hình cài được |
| `colcon test --packages-select hri_engagement` | **19 passed** | FSM, nhiễu, thời hạn tín hiệu, cooldown, mất camera, khôi phục, chuẩn hóa lời chào, metrics, hình học hướng đầu/tay |
| `colcon test-result --test-result-base build/hri_engagement --verbose` | 19 tests, 0 errors, 0 failures, 0 skipped | Kết quả pytest qua colcon |
| Replay 15 tình huống | **15/15 PASS** | Boolean synthetic, không phải webcam/người thật |
| `test/check_runtime.py` qua ROS domain 168 | **10/10 PASS** | Launch, DDS topic, reset service, phản hồi một lần, recorder CSV |
| Webcam `/dev/video0`, chạy headless và ghi AVI | **181 frame khỏe**, 181 frame video đọc được | MediaPipe và pipeline webcam thật hoạt động trong khoảng 11,96 giây |
| Preview webcam có GUI | PASS | Cửa sổ OpenCV chạy được; camera và controller dừng sạch khi nhận SIGINT |

Runtime kiểm tra: chỉ nhìn → ATTENTION; đầu + tay → ENGAGED; không chào lặp; timeout camera → IDLE; đầu + lời chào → ENGAGED; không có tín hiệu → IDLE; lời chào không hướng đầu → ATTENTION; câu không phải lời chào bị bỏ qua; payload vision sai → IDLE; recorder thực hiện reset/chờ frame/ghi CSV đúng với nguồn synthetic.

Replay synthetic có TP=9, TN=6, FP=0, FN=0, tỷ lệ chào nhầm **0/6**. Con số này chỉ đánh giá logic trên tín hiệu tạo sẵn, **không phải độ chính xác nhận dạng ngoài thực tế**.

Trong lần smoke webcam không theo kịch bản: 99 frame có đúng một mặt, 63 frame được phân loại hướng về robot, 0 frame giơ tay, 0 lời chào. Không suy ra accuracy từ lần chạy này vì không có nhãn ground truth theo từng tình huống. Video và quan sát camera được lưu cục bộ, đã đưa vào `.gitignore`.

Bằng chứng trong workspace:

- [15 lượt synthetic](../../artifacts/hri_engagement/synthetic_trials.csv).
- [10 ca ROS integration](../../artifacts/hri_engagement/runtime_results.json).
- [Thông số smoke webcam](../../artifacts/hri_engagement/camera_smoke_results.json).
- Video webcam và JSONL: `artifacts/hri_engagement/camera_smoke/<run>/` ở gốc workspace.

**Chưa thực hiện**: 15 lượt có người thật và nhãn ground truth, video 3 tình huống có người thực hiện, STT microphone, loa/TTS hoặc tích hợp robot vật lý. Package hỗ trợ text đúng lựa chọn của đề bài; README có kế hoạch 15 lượt, lệnh ghi video và recorder để thực hiện phần đánh giá người thật.
