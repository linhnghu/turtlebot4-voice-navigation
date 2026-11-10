#!/usr/bin/env python3
"""Own the lab lock and reap Gazebo children, including detached sessions."""
import ctypes
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

WORKSPACE = Path(__file__).resolve().parent
ARTIFACTS = WORKSPACE / 'artifacts'
LOCK = ARTIFACTS / 'turtlebot4_launch.lock'
PID = ARTIFACTS / 'turtlebot4_launch.pid'
SESSION = ARTIFACTS / 'turtlebot4_launch.session.json'


def process(pid):
    try:
        path = Path('/proc') / str(pid)
        fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': int(pid), 'ppid': int(fields[1]), 'state': fields[0],
                'started': fields[19],
                'argv': (path / 'cmdline').read_bytes().split(b'\0')}
    except (OSError, ValueError):
        return None


def descendants(root):
    rows = [process(p.name) for p in Path('/proc').iterdir() if p.name.isdigit()]
    found = {root}
    while True:
        more = {r['pid'] for r in rows if r and r['ppid'] in found}
        if more <= found:
            return [r for r in rows if r and r['pid'] in found - {root}]
        found |= more


def send(rows, sig):
    for row in rows:
        current = process(row['pid'])
        if current and current['started'] == row['started']:
            try:
                os.kill(row['pid'], sig)
            except ProcessLookupError:
                pass


def reap():
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def cleanup():
    # Gazebo can create its own process group. The subreaper keeps it in our
    # process tree, so cleanup is not limited to the ros2 launch process group.
    for sig, grace in [(signal.SIGINT, 4), (signal.SIGTERM, 2), (signal.SIGKILL, 1)]:
        deadline = time.monotonic() + grace
        signalled = set()
        while True:
            rows = descendants(os.getpid())
            fresh = [r for r in rows if (r['pid'], r['started']) not in signalled]
            send(fresh, sig)
            signalled.update((r['pid'], r['started']) for r in fresh)
            reap()
            if not descendants(os.getpid()):
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)


def supervise(command):
    ARTIFACTS.mkdir(exist_ok=True)
    with LOCK.open('a') as lock:
        # Python file descriptors are non-inheritable; only this supervisor
        # owns the lock. Gazebo cannot retain it after the supervisor exits.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('TurtleBot 4 is already running. Use ./stop_turtlebot4.bash first.',
                  file=sys.stderr)
            return 1
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), 'Cannot supervise detached Gazebo processes')
        stopping = False

        def request_stop(_sig, _frame):
            nonlocal stopping
            stopping = True

        old_handlers = {s: signal.signal(s, request_stop)
                        for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        row = process(os.getpid())
        SESSION.write_text(json.dumps({'pid': row['pid'], 'started': row['started']}))
        PID.write_text(str(os.getpid()) + '\n')
        try:
            child = subprocess.Popen(command, cwd=WORKSPACE, start_new_session=True,
                                     close_fds=True)
            while not stopping and child.poll() is None:
                time.sleep(0.1)
            return 0 if stopping else child.returncode
        finally:
            cleanup()
            SESSION.unlink(missing_ok=True)
            PID.unlink(missing_ok=True)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)


def legacy_lock_holders():
    """Recover the old wrapper's inherited lock without stopping other robots."""
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid() or (path / 'cwd').resolve() != WORKSPACE:
                continue
            row = process(path.name)
            command = b' '.join(row['argv']) if row else b''
            if not any(token in command for token in (b'ign gazebo', b'ros2 launch', b'rviz2',
                                                       b'run_turtlebot4.bash', b'turtlebot4_session.py')):
                continue
            if any(fd.resolve() == LOCK for fd in (path / 'fd').iterdir()):
                rows.append(row)
        except (OSError, RuntimeError):
            continue
    return rows


def orphan_lab_launches():
    """Find our exact launch when its terminal/supervisor has disappeared."""
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid() or (path / 'cwd').resolve() != WORKSPACE:
                continue
            row = process(path.name)
            args = row['argv'] if row else []
            launches = [(b'turtlebot4_lab', b'lab.launch.py'),
                        (b'turtlebot4_vision_nav', b'vision_demo.launch.py'),
                        (b'turtlebot4_gesture', b'gesture_demo.launch.py'),
                        (b'turtlebot4_voice_nav', b'voice_nav.launch.py')]
            if any(args[i:i + 3] == [b'launch', package, launch_file]
                   for i in range(len(args)) for package, launch_file in launches):
                rows.append(row)
        except (OSError, RuntimeError):
            continue
    return rows


def stop():
    try:
        saved = json.loads(SESSION.read_text())
        row = process(saved['pid'])
    except (OSError, ValueError, KeyError):
        saved, row = {}, None
    if (row and row['started'] == saved.get('started') and
            str(Path(__file__).resolve()).encode() in row['argv']):
        print(f"Stopping TurtleBot 4 session {row['pid']}...", flush=True)
        send([row], signal.SIGTERM)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            current = process(row['pid'])
            if not current or current['state'] == 'Z' or current['started'] != row['started']:
                print('TurtleBot 4 stopped.')
                return 0
            time.sleep(0.1)
        print('Session has not finished stopping. Check artifacts and retry.', file=sys.stderr)
        return 1
    roots = legacy_lock_holders() + orphan_lab_launches()
    rows_by_pid = {r['pid']: r for root in roots
                   for r in [root, *descendants(root['pid'])]}
    rows = list(rows_by_pid.values())
    if rows:
        print('Stopping leftover TurtleBot 4 processes from this workspace...', flush=True)
        for sig, grace in [(signal.SIGINT, 4), (signal.SIGTERM, 2), (signal.SIGKILL, 1)]:
            send(rows, sig)
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                live = [r for r in rows if (p := process(r['pid'])) and
                        p['started'] == r['started'] and p['state'] != 'Z']
                if not live:
                    break
                time.sleep(0.1)
        if live:
            print('Some TurtleBot 4 processes have not stopped.', file=sys.stderr)
            return 1
    SESSION.unlink(missing_ok=True)
    PID.unlink(missing_ok=True)
    print('TurtleBot 4 stopped.' if rows else 'No TurtleBot 4 session is running.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('start', 'start-vision', 'start-gesture', 'start-voice', 'stop'):
        raise SystemExit('Usage: turtlebot4_session.py start|start-vision|start-gesture|start-voice [launch arguments] | stop')
    package, launch_file = {
        'start-vision': ('turtlebot4_vision_nav', 'vision_demo.launch.py'),
        'start-gesture': ('turtlebot4_gesture', 'gesture_demo.launch.py'),
        'start-voice': ('turtlebot4_voice_nav', 'voice_nav.launch.py'),
    }.get(sys.argv[1], ('turtlebot4_lab', 'lab.launch.py'))
    raise SystemExit(stop() if sys.argv[1] == 'stop' else supervise(
        ['ros2', 'launch', package, launch_file, *sys.argv[2:]]))
