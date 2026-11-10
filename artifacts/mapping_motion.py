import json, math, time
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from rclpy.qos import qos_profile_sensor_data
rclpy.init(); n=rclpy.create_node('mapping_velocity_validation')
pose=[]; scans=[]
n.create_subscription(Odometry,'/odom',lambda m: pose.__setitem__(slice(None),[m]),qos_profile_sensor_data)
n.create_subscription(LaserScan,'/scan',lambda m: scans.__setitem__(slice(None),[m]),qos_profile_sensor_data)
pub=n.create_publisher(Twist,'/cmd_vel',10)
def stop():
    for _ in range(5): pub.publish(Twist()); rclpy.spin_once(n,timeout_sec=.05)
def yaw(p):
    q=p.orientation; return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
results=[]
try:
    start=time.monotonic()
    while not pose or not scans:
        rclpy.spin_once(n,timeout_sec=.1)
        if time.monotonic()-start>10: raise RuntimeError('No odom or scan')
    for x,y in [(-3.,0.),(-3.,2.),(-2.,2.)]:
        start=time.monotonic()
        while True:
            rclpy.spin_once(n,timeout_sec=.05)
            p=pose[-1].pose.pose
            dx,dy=x-p.position.x,y-p.position.y; distance=math.hypot(dx,dy)
            if distance<.12: break
            if time.monotonic()-start>100: raise RuntimeError('Motion timeout')
            error=math.atan2(math.sin(math.atan2(dy,dx)-yaw(p)),math.cos(math.atan2(dy,dx)-yaw(p)))
            command=Twist(); command.angular.z=max(-.6,min(.6,1.5*error))
            if abs(error)<.20:
                s=scans[-1]
                front=[r for i,r in enumerate(s.ranges) if abs(s.angle_min+i*s.angle_increment)<.35 and math.isfinite(r)]
                if front and min(front)<.45: raise RuntimeError('Front obstacle too close')
                command.linear.x=min(.22,.6*distance)
            pub.publish(command)
        stop(); p=pose[-1].pose.pose.position
        results.append({'target':[x,y],'odom':[p.x,p.y]})
        print(json.dumps(results[-1]),flush=True)
finally:
    stop()
    open('artifacts/mapping_motion.json','w').write(json.dumps(results,indent=2))
    n.destroy_node();rclpy.shutdown()
