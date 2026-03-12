"""
OBS Controller - Automate OBS Studio operations
Control scenes, sources, recording via websocket
"""

from obswebsocket import obsws, requests
import time
from typing import Optional

class OBSController:
    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        """
        Initialize OBS websocket connection
        
        Args:
            host: OBS websocket host
            port: OBS websocket port (default 4455 for v5)
            password: OBS websocket password (if set)
        """
        self.host = host
        self.port = port
        self.password = password
        self.ws: Optional[obsws] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to OBS websocket"""
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            print(f"Connected to OBS at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect to OBS: {e}")
            print("Make sure OBS is running with websocket server enabled")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from OBS"""
        if self.ws:
            self.ws.disconnect()
            self.connected = False
            print("Disconnected from OBS")
    
    def get_current_scene(self) -> Optional[str]:
        """Get name of current scene"""
        if not self.connected:
            return None
        
        try:
            response = self.ws.call(requests.GetCurrentProgramScene())
            return response.datain['currentProgramSceneName']
        except Exception as e:
            print(f"Error getting current scene: {e}")
            return None
    
    def switch_scene(self, scene_name: str) -> bool:
        """
        Switch to specified scene
        
        Args:
            scene_name: Name of scene to switch to
            
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        try:
            self.ws.call(requests.SetCurrentProgramScene(sceneName=scene_name))
            print(f"Switched to scene: {scene_name}")
            return True
        except Exception as e:
            print(f"Error switching scene: {e}")
            return False
    
    def start_recording(self) -> bool:
        """Start recording"""
        if not self.connected:
            return False
        
        try:
            self.ws.call(requests.StartRecord())
            print("Recording started")
            return True
        except Exception as e:
            print(f"Error starting recording: {e}")
            return False
    
    def stop_recording(self) -> bool:
        """Stop recording"""
        if not self.connected:
            return False
        
        try:
            self.ws.call(requests.StopRecord())
            print("Recording stopped")
            return True
        except Exception as e:
            print(f"Error stopping recording: {e}")
            return False
    
    def toggle_source_visibility(self, scene_name: str, source_name: str, visible: bool) -> bool:
        """
        Toggle visibility of a source in a scene
        
        Args:
            scene_name: Scene containing the source
            source_name: Name of source to toggle
            visible: True to show, False to hide
        """
        if not self.connected:
            return False
        
        try:
            self.ws.call(requests.SetSceneItemEnabled(
                sceneName=scene_name,
                sceneItemId=source_name,
                sceneItemEnabled=visible
            ))
            status = "shown" if visible else "hidden"
            print(f"Source '{source_name}' {status}")
            return True
        except Exception as e:
            print(f"Error toggling source: {e}")
            return False
    
    def get_stream_status(self) -> dict:
        """Get streaming status"""
        if not self.connected:
            return {}
        
        try:
            response = self.ws.call(requests.GetStreamStatus())
            return {
                'streaming': response.datain['outputActive'],
                'duration': response.datain.get('outputDuration', 0),
                'bytes': response.datain.get('outputBytes', 0)
            }
        except Exception as e:
            print(f"Error getting stream status: {e}")
            return {}


def main():
    """Example usage and testing"""
    controller = OBSController()
    
    if not controller.connect():
        return
    
    try:
        # Get current scene
        current = controller.get_current_scene()
        print(f"Current scene: {current}")
        
        # Get stream status
        status = controller.get_stream_status()
        print(f"Stream status: {status}")
        
        # Keep connection alive
        print("\nOBS Controller running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        controller.disconnect()


if __name__ == "__main__":
    main()
