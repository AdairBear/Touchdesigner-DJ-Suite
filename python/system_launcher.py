"""
System Launcher - Start all components
Orchestrates the complete generative stream graphics system
"""

import subprocess
import time
import sys
import os
from pathlib import Path

class SystemLauncher:
    def __init__(self):
        self.processes = []
        self.project_root = Path(__file__).parent.parent
        
    def check_dependencies(self):
        """Check if required software is available"""
        print("Checking dependencies...")
        
        # Check Python packages
        required_packages = [
            'mediapipe', 'cv2', 'pythonosc', 
            'librosa', 'numpy', 'obswebsocket'
        ]
        
        missing = []
        for package in required_packages:
            try:
                __import__(package)
                print(f"  ✓ {package}")
            except ImportError:
                print(f"  ✗ {package} - MISSING")
                missing.append(package)
        
        if missing:
            print(f"\nMissing packages: {', '.join(missing)}")
            print("Run: pip install -r requirements.txt")
            return False
        
        return True
    
    def check_camera(self):
        """Check if camera is available"""
        import cv2
        print("\nChecking camera...")
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print("  ✓ Camera detected")
            cap.release()
            return True
        else:
            print("  ✗ Camera not found")
            return False
    
    def start_movement_tracker(self):
        """Start movement tracking script"""
        print("\nStarting movement tracker...")
        script_path = self.project_root / "python" / "movement_tracker.py"
        
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.processes.append(("Movement Tracker", process))
        print("  ✓ Movement tracker started")
        return process
    
    def start_obs_controller(self):
        """Start OBS controller"""
        print("\nStarting OBS controller...")
        script_path = self.project_root / "python" / "obs_controller.py"
        
        # Check if OBS is running first
        # This is platform-specific, simplified here
        
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.processes.append(("OBS Controller", process))
        print("  ✓ OBS controller started")
        return process
    
    def start_chat_bridge(self, extra_args=None):
        """Start the audience chat bridge as a third OSC producer.

        Opt-in, and deliberately so. The bridge needs an OpenAI key and YouTube
        access; a normal show must start without either. It is also the only
        component that lets strangers touch the visuals, so it should be a
        thing Thomas turns on for a stream, not a thing that happens to him.

        Enable with CHAT_BRIDGE=1 in the environment, or call this directly.

        Args:
            extra_args (list[str] | None): Extra flags for ``python -m
                chat_bridge``, e.g. ``["--dry-run"]``.

        Returns:
            subprocess.Popen | None: The process, or None if it was not started.
        """
        if not os.environ.get("OPENAI_API_KEY"):
            print("\n  ! Chat bridge skipped: OPENAI_API_KEY is not set")
            return None

        print("\nStarting audience chat bridge...")
        env = dict(os.environ)
        python_dir = str(self.project_root / "python")
        env["PYTHONPATH"] = os.pathsep.join(
            [python_dir, str(self.project_root / "touchdesigner" / "scripts"),
             env.get("PYTHONPATH", "")]).rstrip(os.pathsep)

        process = subprocess.Popen(
            [sys.executable, "-m", "chat_bridge"] + list(extra_args or []),
            cwd=python_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        self.processes.append(("Chat Bridge", process))
        print("  ✓ Chat bridge started")
        print("    Quitting it (or Ctrl-C here) stops all audience input;")
        print("    the rig continues on its current validated look.")
        return process

    def launch_touchdesigner(self):
        """Launch TouchDesigner project"""
        print("\nLaunching TouchDesigner...")
        td_project = self.project_root / "touchdesigner" / "main.toe"
        
        if not td_project.exists():
            print(f"  ✗ TouchDesigner project not found: {td_project}")
            return None
        
        # Platform-specific TouchDesigner launch
        if sys.platform == "darwin":
            # macOS
            td_app = "/Applications/TouchDesigner.app"
            if Path(td_app).exists():
                process = subprocess.Popen(["open", "-a", "TouchDesigner", str(td_project)])
                print("  ✓ TouchDesigner launched")
                return process
        elif sys.platform == "win32":
            # Windows
            td_exe = "C:/Program Files/Derivative/TouchDesigner/bin/TouchDesigner.exe"
            if Path(td_exe).exists():
                process = subprocess.Popen([td_exe, str(td_project)])
                print("  ✓ TouchDesigner launched")
                return process
        
        print("  ! Please open TouchDesigner manually")
        return None
    
    def monitor_processes(self):
        """Monitor running processes"""
        print("\n" + "="*50)
        print("System running. Press Ctrl+C to stop all components.")
        print("="*50 + "\n")
        
        try:
            while True:
                time.sleep(1)
                
                # Check if any process died
                for name, process in self.processes:
                    if process.poll() is not None:
                        print(f"Warning: {name} stopped unexpectedly")
                
        except KeyboardInterrupt:
            print("\n\nShutting down system...")
            self.cleanup()
    
    def cleanup(self):
        """Stop all processes"""
        print("Stopping all components...")
        
        for name, process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"  ✓ Stopped {name}")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"  ! Force killed {name}")
        
        print("\nSystem stopped")
    
    def run(self):
        """Main launch sequence"""
        print("="*50)
        print("Generative Stream Graphics System Launcher")
        print("="*50)
        
        # Pre-flight checks
        if not self.check_dependencies():
            print("\nCannot start - missing dependencies")
            return
        
        if not self.check_camera():
            print("\nWarning: Camera not detected, continuing anyway...")
        
        # Launch components
        self.start_movement_tracker()
        time.sleep(2)  # Let tracker initialize
        
        # self.start_obs_controller()
        # time.sleep(1)

        if os.environ.get("CHAT_BRIDGE") == "1":
            self.start_chat_bridge()

        self.launch_touchdesigner()
        
        # Monitor
        self.monitor_processes()


if __name__ == "__main__":
    launcher = SystemLauncher()
    launcher.run()
