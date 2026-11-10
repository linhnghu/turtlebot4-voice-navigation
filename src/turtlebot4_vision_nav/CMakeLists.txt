cmake_minimum_required(VERSION 3.8)
project(turtlebot4_vision_nav)
find_package(ament_cmake REQUIRED)
install(DIRECTORY launch config models DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/mission.py scripts/yolo_detector.py scripts/record_goals.py
  DESTINATION lib/${PROJECT_NAME})
ament_package()
