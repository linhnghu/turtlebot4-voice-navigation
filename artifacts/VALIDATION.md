# Kết quả kiểm thử TurtleBot 4 — 07/10/2026

Ubuntu 22.04.5, ROS 2 Humble, Gazebo Fortress 6.18.0; TurtleBot 4 Lite trong world maze.
Package turtlebot4_lab build thành công bằng colcon. Kiểm tra cú pháp Python/Bash đạt.
Launch từ chối map không tồn tại trước khi khởi động simulator và chặn mở hai phiên qua wrapper.

## Simulation và SLAM

Robot undock thành công, sau đó nhận Twist trên /cmd_vel và đi tới ba điểm
(-3, 0), (-3, 2), (-2, 2) theo odometry để kiểm tra chuyển động và cập nhật SLAM.
Đây là điều khiển vận tốc bằng script kiểm thử, không phải minh chứng sinh viên teleop bằng bàn phím.

check_topics.py đạt cho /scan, /odom, /clock, /cmd_vel và TF.
Map lưu thực từ SLAM: maps/map.yaml + maps/map.pgm, 354 x 401 ô, 0.05 m/ô,
origin (-10, -10). 86.341 ô chưa khảo sát vẫn là unknown sau khi load lại.
Bản đồ hiện tại là bản thử, chưa đáp ứng khảo sát phần lớn maze.

## Localization và Nav2

SLAM và simulator đã dừng trước khi khởi động lại trong cùng world.
AMCL + map server đạt active; Nav2 đạt active sau khi cấp initial pose (0, 0, yaw 0).
Goal được gửi qua action /navigate_to_pose, cùng API mà công cụ Nav2 Goal dùng.
Không có publisher điều khiển tay từ script kiểm thử trong giai đoạn Nav2.
Script chỉ gửi initial pose, undock và các goal; Nav2 tự lập kế hoạch/điều khiển.

| Goal (m) | Kết quả | Thời gian thực | Sai số vị trí Gazebo tới goal | AMCL gần nhất so với Gazebo | Thông báo bumper |
|---|---|---|---|---|---|
| (-3.0, 0.0) | SUCCEEDED (4) | 30.8 s | 0.186 m | 0.042 m | 0 |
| (-3.0, 4.0) | SUCCEEDED (4) | 39.6 s | 0.176 m | 0.056 m | 0 |
| (2.0, 0.0) | SUCCEEDED (4) | 55.0 s | 0.237 m | 0.076 m | 0 |

AMCL trong bảng là message gần nhất tại thời điểm trả kết quả; AMCL không publish
mỗi chu kỳ odometry. Sai số đánh giá vị trí thực dùng /sim_ground_truth_pose từ Gazebo.
Không có thông báo bumper được nhận trong lần kiểm thử; đây không thay thế video
quan sát va chạm theo yêu cầu nộp bài.

## Minh chứng

- topics_mapping.json, topics_navigation.json: dữ liệu topic và TF thực.
- mapping_motion.json: vị trí sau các lệnh vận tốc.
- navigation_results.json, navigation_validation.log: kết quả action cuối, sau sửa ngưỡng map.
- rviz_mapping.png: map, RobotModel, LiDAR khi mapping.
- rviz_navigation.png: robot, LiDAR, costmap và panel Nav2 active trong lúc chạy goal.
- gazebo_navigation_complete.png: mô hình maze và robot sau navigation.
- rviz_navigation_complete.png: trạng thái RViz sau các goal.

Cần hoàn tất teleoperation khảo sát phần lớn maze, lưu lại map và quay video
các goal bằng thao tác Nav2 Goal trên RViz để đủ minh chứng bài tập.
Hướng dẫn ở ../README_TURTLEBOT4.md.

## Sửa lỗi dừng phiên và khóa bị giữ

Đã phát hiện Gazebo server còn sống, giữ FD 9 trỏ tới turtlebot4_launch.lock, trong khi PID file của wrapper cũ đã mất. Script stop mới dọn được phiên cũ.

turtlebot4_session.py giữ khóa trong tiến trình quản lý, không truyền FD khóa cho tiến trình con, và thu gom các tiến trình Gazebo tự tách session. Đã kiểm tra: tiến trình con tách session được thu gom; mở phiên trùng bị chặn; dừng simulation thật kết thúc toàn bộ tiến trình con, xóa metadata và giải phóng khóa. Sau khi khởi động lại, check_topics.py đạt ở chế độ simulation. Minh chứng: topics_simulation_session_fix_final.json và simulation_session_fix_final_retry.log.

## Kiểm thử teleop khi mapping — 13/10/2026

Phiên simulation cũ đã đóng Gazebo/RViz nhưng còn node ROS, không có /scan, /odom và /clock. Đã dọn phiên còn sót và khởi động đúng mode mapping. run_teleop.bash nạp cùng ROS domain, đợi dữ liệu thực và undock trước khi nhận phím. Kiểm thử trực tiếp keyboard teleop trong PTY: undock SUCCEEDED, gửi phím i liên tiếp rồi k và Ctrl+C. Robot di chuyển 0.349 m theo /sim_ground_truth_pose. SLAM/map và các topic đạt kiểm tra. Minh chứng: teleop_validation.json, topics_mapping_teleop_fix.json và mapping_teleop_fix.log.

## Sửa initial pose cho localization/Nav2 — 13/10/2026

Log AMCL trước khi sửa cho thấy map load thành công, AMCL active nhưng chưa nhận initial pose. Planner chờ TF map. Các lỗi context invalid trong log được gửi xảy ra sau SIGINT/SIGTERM khi đang shutdown.

Launch mới giữ cấu hình TurtleBot 4, thêm set_initial_pose=true tại (initial_x, initial_y, initial_yaw), mặc định (0, 0, 0) trên map. Có thể dùng auto_initial_pose:=false để tự đặt pose bằng RViz.

Đã build và chạy với bản map 404 x 404 ô do người dùng lưu. AMCL, map_server, controller_server, planner_server và bt_navigator đều active; check_topics.py đạt cho sensor, map và TF. Script kiểm thử không gửi /initialpose. Undock SUCCEEDED và goal (-2, 0) SUCCEEDED. Sai số vị trí thực Gazebo tới goal là 0.258 m. Minh chứng: navigation_initial_pose_results.json, topics_navigation_initial_pose_fix.json, navigation_initial_pose_fix.log và rviz_navigation_initial_pose_fix.png.
