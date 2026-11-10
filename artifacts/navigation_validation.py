import json, math, time
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from irobot_create_msgs.action import Undock
from irobot_create_msgs.msg import HazardDetectionVector
from lifecycle_msgs.srv import GetState
rclpy.init(); n=Node('lab_navigation_validation',parameter_overrides=[Parameter('use_sim_time',value=True)])
poses=[]; odom=[]; ground_truth=[]; bumps=[]
n.create_subscription(PoseWithCovarianceStamped,'/amcl_pose',lambda m: poses.__setitem__(slice(None),[m]),qos_profile_sensor_data)
n.create_subscription(Odometry,'/odom',lambda m: odom.__setitem__(slice(None),[m]),qos_profile_sensor_data)
n.create_subscription(Odometry,'/sim_ground_truth_pose',lambda m: ground_truth.__setitem__(slice(None),[m]),qos_profile_sensor_data)
def hazard(msg):
    if any(h.type==1 for h in msg.detections): bumps.append(n.get_clock().now().nanoseconds)
n.create_subscription(HazardDetectionVector,'/hazard_detection',hazard,qos_profile_sensor_data)
def wait(future, timeout=30):
    start=time.monotonic()
    while not future.done():
        rclpy.spin_once(n,timeout_sec=.1)
        if time.monotonic()-start>timeout: raise RuntimeError('Timed out waiting for action/service')
    return future.result()
for name in ['amcl','map_server']:
    c=n.create_client(GetState,'/'+name+'/get_state')
    if not c.wait_for_service(timeout_sec=40): raise RuntimeError('Missing '+name)
    start=time.monotonic()
    while True:
        result=wait(c.call_async(GetState.Request()))
        if result.current_state.id==3: break
        rclpy.spin_once(n,timeout_sec=.3)
        if time.monotonic()-start>45: raise RuntimeError(name+' is not active')
    print(name,result.current_state.label,flush=True)
pub=n.create_publisher(PoseWithCovarianceStamped,'/initialpose',10)
start=time.monotonic()
while not poses:
    p=PoseWithCovarianceStamped();p.header.frame_id='map';p.header.stamp=n.get_clock().now().to_msg();p.pose.pose.orientation.w=1.
    p.pose.covariance[0]=p.pose.covariance[7]=.05;p.pose.covariance[35]=.05;pub.publish(p)
    end=time.monotonic()+1
    while time.monotonic()<end: rclpy.spin_once(n,timeout_sec=.1)
    if time.monotonic()-start>30: raise RuntimeError('No AMCL pose after initialpose')
print('initial_amcl',poses[-1].pose.pose.position,flush=True)
undock=ActionClient(n,Undock,'/undock')
if not undock.wait_for_server(timeout_sec=20): raise RuntimeError('No undock server')
handle=wait(undock.send_goal_async(Undock.Goal()))
result=wait(handle.get_result_async(),40)
print('undock',result.status,result.result,flush=True)
if result.status!=4: raise RuntimeError('Undock failed')
nav=ActionClient(n,NavigateToPose,'/navigate_to_pose')
if not nav.wait_for_server(timeout_sec=60): raise RuntimeError('No navigation server')
results=[]
for x,y in [(-3.,0.),(-3.,4.),(2.,0.)]:
    g=NavigateToPose.Goal();g.pose.header.frame_id='map';g.pose.header.stamp=n.get_clock().now().to_msg();g.pose.pose.position.x=x;g.pose.pose.position.y=y;g.pose.pose.orientation.w=1.
    goal=wait(nav.send_goal_async(g));print('accepted',[x,y],goal.accepted,flush=True)
    if not goal.accepted: raise RuntimeError('Goal rejected')
    started=time.monotonic();future=goal.get_result_async()
    try: result=wait(future,150)
    except Exception:
        wait(goal.cancel_goal_async(),10)
        raise
    a=poses[-1].pose.pose.position;o=odom[-1].pose.pose.position
    record={'goal':[x,y],'status':result.status,'wall_seconds':time.monotonic()-started,'amcl_xy':[a.x,a.y],'odom_xy':[o.x,o.y],'goal_error_amcl_last_message_m':math.hypot(a.x-x,a.y-y),'gazebo_xy':[ground_truth[-1].pose.pose.position.x,ground_truth[-1].pose.pose.position.y] if ground_truth else None,'bump_messages':len(bumps)}
    results.append(record);open('artifacts/navigation_results.json','w').write(json.dumps(results,indent=2));print(json.dumps(record),flush=True)
    if result.status!=4: raise RuntimeError('Navigation failed')
n.destroy_node();rclpy.shutdown()
