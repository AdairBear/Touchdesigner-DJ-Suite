"""
Tests for system_launcher.py
Tests system orchestration and component launching
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import subprocess
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from system_launcher import SystemLauncher


class TestSystemLauncherInit:
    """Test SystemLauncher initialization"""
    
    def test_init(self):
        """Test initialization"""
        launcher = SystemLauncher()
        
        assert launcher.processes == []
        assert isinstance(launcher.project_root, Path)


class TestDependencyChecking:
    """Test dependency checking functionality"""
    
    @patch('system_launcher.__import__')
    def test_check_dependencies_all_present(self, mock_import):
        """Test when all dependencies are present"""
        launcher = SystemLauncher()
        
        # Mock all imports to succeed
        mock_import.return_value = Mock()
        
        result = launcher.check_dependencies()
        
        assert result is True
    
    @patch('system_launcher.__import__')
    def test_check_dependencies_missing(self, mock_import):
        """Test when dependencies are missing"""
        launcher = SystemLauncher()
        
        # Mock some imports to fail
        def side_effect(name):
            if name in ['mediapipe', 'cv2']:
                return Mock()
            raise ImportError(f"No module named '{name}'")
        
        mock_import.side_effect = side_effect
        
        result = launcher.check_dependencies()
        
        assert result is False


class TestCameraCheck:
    """Test camera availability checking"""
    
    @patch('system_launcher.cv2.VideoCapture')
    def test_check_camera_available(self, mock_capture):
        """Test when camera is available"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_capture.return_value = mock_cap
        
        launcher = SystemLauncher()
        result = launcher.check_camera()
        
        assert result is True
        mock_cap.release.assert_called_once()
    
    @patch('system_launcher.cv2.VideoCapture')
    def test_check_camera_unavailable(self, mock_capture):
        """Test when camera is not available"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = False
        mock_capture.return_value = mock_cap
        
        launcher = SystemLauncher()
        result = launcher.check_camera()
        
        assert result is False


class TestComponentStartup:
    """Test starting individual components"""
    
    @patch('system_launcher.subprocess.Popen')
    @patch('system_launcher.sys.executable', '/usr/bin/python')
    def test_start_movement_tracker(self, mock_popen):
        """Test starting movement tracker"""
        mock_process = Mock()
        mock_popen.return_value = mock_process
        
        launcher = SystemLauncher()
        process = launcher.start_movement_tracker()
        
        # Verify subprocess was called
        assert mock_popen.called
        assert process == mock_process
        assert len(launcher.processes) == 1
        assert launcher.processes[0][0] == "Movement Tracker"
    
    @patch('system_launcher.subprocess.Popen')
    @patch('system_launcher.sys.executable', '/usr/bin/python')
    def test_start_obs_controller(self, mock_popen):
        """Test starting OBS controller"""
        mock_process = Mock()
        mock_popen.return_value = mock_process
        
        launcher = SystemLauncher()
        process = launcher.start_obs_controller()
        
        assert mock_popen.called
        assert process == mock_process
        assert len(launcher.processes) == 1
        assert launcher.processes[0][0] == "OBS Controller"


class TestTouchDesignerLaunch:
    """Test TouchDesigner launching (macOS)"""
    
    @patch('system_launcher.subprocess.Popen')
    @patch('system_launcher.sys.platform', 'darwin')
    @patch('system_launcher.Path.exists')
    def test_launch_touchdesigner_macos_success(self, mock_exists, mock_popen):
        """Test launching TouchDesigner on macOS"""
        mock_exists.return_value = True  # TD app exists
        mock_process = Mock()
        mock_popen.return_value = mock_process
        
        launcher = SystemLauncher()
        process = launcher.launch_touchdesigner()
        
        # Verify open command was used (macOS)
        assert mock_popen.called
        args = mock_popen.call_args[0][0]
        assert 'open' in args or args[0] == 'open'
    
    @patch('system_launcher.subprocess.Popen')
    @patch('system_launcher.sys.platform', 'darwin')
    @patch('system_launcher.Path.exists')
    def test_launch_touchdesigner_not_found(self, mock_exists, mock_popen):
        """Test when TouchDesigner project file not found"""
        mock_exists.return_value = False
        
        launcher = SystemLauncher()
        process = launcher.launch_touchdesigner()
        
        # Should return None when file not found
        assert process is None
        assert not mock_popen.called


class TestProcessMonitoring:
    """Test process monitoring"""
    
    @patch('system_launcher.time.sleep')
    def test_monitor_processes_keyboard_interrupt(self, mock_sleep):
        """Test monitoring stops on keyboard interrupt"""
        mock_sleep.side_effect = KeyboardInterrupt()
        
        launcher = SystemLauncher()
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process still running
        launcher.processes = [("Test Process", mock_process)]
        
        # Should not raise exception, should call cleanup
        with patch.object(launcher, 'cleanup') as mock_cleanup:
            launcher.monitor_processes()
            mock_cleanup.assert_called_once()
    
    @patch('system_launcher.time.sleep')
    def test_monitor_processes_detects_crash(self, mock_sleep):
        """Test monitoring detects crashed process"""
        mock_process = Mock()
        mock_process.poll.side_effect = [None, 1, 1]  # Process crashes after first check
        
        launcher = SystemLauncher()
        launcher.processes = [("Test Process", mock_process)]
        
        # Run once and simulate keyboard interrupt
        mock_sleep.side_effect = [None, KeyboardInterrupt()]
        
        with patch.object(launcher, 'cleanup'):
            launcher.monitor_processes()


class TestCleanup:
    """Test cleanup functionality"""
    
    def test_cleanup_graceful_termination(self):
        """Test graceful process termination"""
        mock_process1 = Mock()
        mock_process1.poll.return_value = None
        mock_process1.terminate.return_value = None
        mock_process1.wait.return_value = None
        
        mock_process2 = Mock()
        mock_process2.poll.return_value = None
        mock_process2.terminate.return_value = None
        mock_process2.wait.return_value = None
        
        launcher = SystemLauncher()
        launcher.processes = [
            ("Process 1", mock_process1),
            ("Process 2", mock_process2)
        ]
        
        launcher.cleanup()
        
        # Verify both processes terminated
        mock_process1.terminate.assert_called_once()
        mock_process2.terminate.assert_called_once()
        mock_process1.wait.assert_called_once()
        mock_process2.wait.assert_called_once()
    
    def test_cleanup_force_kill_timeout(self):
        """Test force kill when process doesn't terminate"""
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.terminate.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired('cmd', 5)
        
        launcher = SystemLauncher()
        launcher.processes = [("Stubborn Process", mock_process)]
        
        launcher.cleanup()
        
        # Verify force kill was called
        mock_process.kill.assert_called_once()


class TestMainRun:
    """Test main run sequence"""
    
    @patch.object(SystemLauncher, 'check_dependencies')
    @patch.object(SystemLauncher, 'check_camera')
    @patch.object(SystemLauncher, 'start_movement_tracker')
    @patch.object(SystemLauncher, 'launch_touchdesigner')
    @patch.object(SystemLauncher, 'monitor_processes')
    def test_run_success(self, mock_monitor, mock_td, mock_tracker, 
                        mock_camera, mock_deps):
        """Test successful system launch"""
        mock_deps.return_value = True
        mock_camera.return_value = True
        mock_tracker.return_value = Mock()
        mock_td.return_value = Mock()
        
        launcher = SystemLauncher()
        launcher.run()
        
        # Verify launch sequence
        mock_deps.assert_called_once()
        mock_camera.assert_called_once()
        mock_tracker.assert_called_once()
        mock_td.assert_called_once()
        mock_monitor.assert_called_once()
    
    @patch.object(SystemLauncher, 'check_dependencies')
    def test_run_fails_missing_dependencies(self, mock_deps):
        """Test run fails when dependencies missing"""
        mock_deps.return_value = False
        
        launcher = SystemLauncher()
        launcher.run()
        
        # Should stop after dependency check
        mock_deps.assert_called_once()
        # Should not proceed to camera check or launch
        assert len(launcher.processes) == 0
    
    @patch.object(SystemLauncher, 'check_dependencies')
    @patch.object(SystemLauncher, 'check_camera')
    @patch.object(SystemLauncher, 'start_movement_tracker')
    @patch.object(SystemLauncher, 'launch_touchdesigner')
    @patch.object(SystemLauncher, 'monitor_processes')
    @patch('system_launcher.time.sleep')
    def test_run_continues_without_camera(self, mock_sleep, mock_monitor, 
                                          mock_td, mock_tracker, mock_camera, 
                                          mock_deps):
        """Test run continues with warning if camera not available"""
        mock_deps.return_value = True
        mock_camera.return_value = False  # Camera not available
        mock_tracker.return_value = Mock()
        mock_td.return_value = Mock()
        
        launcher = SystemLauncher()
        launcher.run()
        
        # Should continue despite camera warning
        mock_tracker.assert_called_once()
        mock_td.assert_called_once()
        mock_monitor.assert_called_once()


# Integration test placeholder
class TestIntegration:
    """Integration tests requiring full system"""
    
    @pytest.mark.skip(reason="Requires all components installed")
    def test_full_system_launch(self):
        """Test launching complete system (requires hardware)"""
        # This would test the actual system launch
        # Requires camera, OBS, TouchDesigner
        pass
