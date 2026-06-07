"""
Tests for obs_controller.py
Tests OBS websocket connection and control functions
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from obs_controller import OBSController


class TestOBSControllerInit:
    """Test OBSController initialization"""
    
    def test_init_default_parameters(self):
        """Test initialization with default parameters"""
        controller = OBSController()
        
        assert controller.host == "localhost"
        assert controller.port == 4455
        assert controller.password == ""
        assert controller.connected is False
        assert controller.ws is None
    
    def test_init_custom_parameters(self):
        """Test initialization with custom parameters"""
        controller = OBSController(
            host="192.168.1.100",
            port=4444,
            password="test123"
        )
        
        assert controller.host == "192.168.1.100"
        assert controller.port == 4444
        assert controller.password == "test123"


class TestConnection:
    """Test OBS websocket connection"""
    
    @patch('obs_controller.obsws')
    def test_connect_success(self, mock_obsws_class):
        """Test successful connection to OBS"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        
        controller = OBSController()
        result = controller.connect()
        
        # Verify connection established
        assert result is True
        assert controller.connected is True
        mock_obsws_class.assert_called_once_with("localhost", 4455, "")
        mock_ws.connect.assert_called_once()
    
    @patch('obs_controller.obsws')
    def test_connect_failure(self, mock_obsws_class):
        """Test failed connection to OBS"""
        mock_obsws_class.return_value.connect.side_effect = Exception("Connection failed")
        
        controller = OBSController()
        result = controller.connect()
        
        # Verify connection failed
        assert result is False
        assert controller.connected is False
    
    @patch('obs_controller.obsws')
    def test_disconnect(self, mock_obsws_class):
        """Test disconnection from OBS"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        
        controller = OBSController()
        controller.connect()
        controller.disconnect()
        
        # Verify disconnection
        mock_ws.disconnect.assert_called_once()
        assert controller.connected is False


class TestSceneControl:
    """Test OBS scene control functions"""
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_get_current_scene_success(self, mock_requests, mock_obsws_class):
        """Test getting current scene name"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        
        # Mock response
        mock_response = Mock()
        mock_response.datain = {'currentProgramSceneName': 'Main Scene'}
        mock_ws.call.return_value = mock_response
        
        controller = OBSController()
        controller.connect()
        
        scene_name = controller.get_current_scene()
        
        assert scene_name == 'Main Scene'
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_get_current_scene_not_connected(self, mock_requests, mock_obsws_class):
        """Test get current scene when not connected"""
        controller = OBSController()
        
        scene_name = controller.get_current_scene()
        
        assert scene_name is None
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_switch_scene_success(self, mock_requests, mock_obsws_class):
        """Test switching to a scene"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        mock_requests.SetCurrentProgramScene = Mock()
        
        controller = OBSController()
        controller.connect()
        
        result = controller.switch_scene("Performance Scene")
        
        assert result is True
        mock_requests.SetCurrentProgramScene.assert_called_once_with(
            sceneName="Performance Scene"
        )
    
    @patch('obs_controller.obsws')
    def test_switch_scene_not_connected(self, mock_obsws_class):
        """Test switch scene when not connected"""
        controller = OBSController()
        
        result = controller.switch_scene("Test Scene")
        
        assert result is False


class TestRecordingControl:
    """Test OBS recording control functions"""
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_start_recording_success(self, mock_requests, mock_obsws_class):
        """Test starting recording"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        mock_requests.StartRecord = Mock()
        
        controller = OBSController()
        controller.connect()
        
        result = controller.start_recording()
        
        assert result is True
        mock_requests.StartRecord.assert_called_once()
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_stop_recording_success(self, mock_requests, mock_obsws_class):
        """Test stopping recording"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        mock_requests.StopRecord = Mock()
        
        controller = OBSController()
        controller.connect()
        
        result = controller.stop_recording()
        
        assert result is True
        mock_requests.StopRecord.assert_called_once()
    
    @patch('obs_controller.obsws')
    def test_recording_not_connected(self, mock_obsws_class):
        """Test recording control when not connected"""
        controller = OBSController()
        
        assert controller.start_recording() is False
        assert controller.stop_recording() is False


class TestSourceControl:
    """Test OBS source visibility control"""
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_toggle_source_visibility_show(self, mock_requests, mock_obsws_class):
        """Test showing a source"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        mock_requests.SetSceneItemEnabled = Mock()
        
        controller = OBSController()
        controller.connect()
        
        result = controller.toggle_source_visibility(
            "Main Scene",
            "Webcam",
            True
        )
        
        assert result is True
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_toggle_source_visibility_hide(self, mock_requests, mock_obsws_class):
        """Test hiding a source"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        mock_requests.SetSceneItemEnabled = Mock()
        
        controller = OBSController()
        controller.connect()
        
        result = controller.toggle_source_visibility(
            "Main Scene",
            "Webcam",
            False
        )
        
        assert result is True


class TestStreamStatus:
    """Test OBS stream status functions"""
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_get_stream_status_success(self, mock_requests, mock_obsws_class):
        """Test getting stream status"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        
        # Mock response
        mock_response = Mock()
        mock_response.datain = {
            'outputActive': True,
            'outputDuration': 3600,
            'outputBytes': 1024000
        }
        mock_ws.call.return_value = mock_response
        
        controller = OBSController()
        controller.connect()
        
        status = controller.get_stream_status()
        
        assert status['streaming'] is True
        assert status['duration'] == 3600
        assert status['bytes'] == 1024000
    
    @patch('obs_controller.obsws')
    def test_get_stream_status_not_connected(self, mock_obsws_class):
        """Test get stream status when not connected"""
        controller = OBSController()
        
        status = controller.get_stream_status()
        
        assert status == {}


class TestErrorHandling:
    """Test error handling in OBS controller"""
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_connection_error_handling(self, mock_requests, mock_obsws_class):
        """Test graceful handling of connection errors"""
        mock_obsws_class.side_effect = Exception("Network error")
        
        controller = OBSController()
        result = controller.connect()
        
        assert result is False
        assert controller.connected is False
    
    @patch('obs_controller.obsws')
    @patch('obs_controller.requests')
    def test_scene_error_handling(self, mock_requests, mock_obsws_class):
        """Test error handling when switching scenes"""
        mock_ws = Mock()
        mock_obsws_class.return_value = mock_ws
        mock_ws.call.side_effect = Exception("Scene not found")
        
        controller = OBSController()
        controller.connect()
        
        result = controller.switch_scene("NonexistentScene")
        
        assert result is False


# Integration test placeholder
class TestIntegration:
    """Integration tests requiring OBS running"""
    
    @pytest.mark.skip(reason="Requires OBS Studio running")
    def test_full_obs_workflow(self):
        """Test complete OBS workflow (requires OBS)"""
        # This would test the actual workflow with OBS running
        pass
