# Simulation assets

`person_standing` was downloaded from the OSRF Gazebo model database:
https://github.com/osrf/gazebo_models/tree/master/person_standing

Author: Marina Kollmitz, as recorded in the unchanged upstream `model.config`.
The model was created with MakeHuman. Original meshes, textures and metadata
are retained. The demo loads a static instance; it does not change the saved map.

YOLO weights are downloaded separately from Ultralytics and are not vendored:
https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
Ultralytics code/models retain their upstream licensing (AGPL-3.0 or an
applicable Ultralytics license): https://docs.ultralytics.com/help/license/
