"""
Tests for movement_tracker.py
Tests OSC messaging, metrics calculation, and multi-person tracking
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from movement_tracker import MovementTracker


class TestMovementTrackerInit:
    """Test MovementTracker initialization"""
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_init_default_parameters(self, mock_cap, mock_osc, mock_pose):
        """Test initialization with default parameters"""
        tracker = MovementTracker()
        
        # Verify OSC client created with defaults
        mock_osc.assert_called_once_with("127.0.0.1", 7000)
        
        # Verify camera setup
        mock_cap.assert_called_once_with(0)
        
        # Verify default max_people
        assert tracker.max_people == 4
        
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_init_custom_parameters(self, mock_cap, mock_osc, mock_pose):
        """Test initialization with custom parameters"""
        tracker = MovementTracker(
            osc_ip="192.168.1.100",
            osc_port=8000,
            max_people=2
        )
        
        mock_osc.assert_called_once_with("192.168.1.100", 8000)
        assert tracker.max_people == 2


class TestMetricsCalculation:
    """Test movement metrics calculation"""
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_calculate_metrics_basic(self, mock_cap, mock_osc, mock_pose):
        """Test basic metrics extraction from landmarks"""
        tracker = MovementTracker()
        
        # Create mock landmarks
        mock_landmarks = []
        for i in range(33):  # MediaPipe has 33 pose landmarks
            landmark = Mock()
            landmark.x = 0.5
            landmark.y = 0.5
            landmark.z = 0.0
            landmark.visibility = 0.8
            mock_landmarks.append(landmark)
        
        # Set specific positions for testing
        mock_landmarks[15].x = 0.3  # Left wrist
        mock_landmarks[15].y = 0.4
        mock_landmarks[16].x = 0.7  # Right wrist
        mock_landmarks[16].y = 0.4
        
        metrics = tracker.calculate_metrics(mock_landmarks, person_id=0)
        
        # Verify metrics structure
        assert 'left_hand_x' in metrics
        assert 'right_hand_x' in metrics
        assert 'hand_spread' in metrics
        assert 'motion_energy' in metrics
        
        # Verify hand spread calculation
        assert metrics['hand_spread'] == pytest.approx(0.4, rel=0.01)


class TestOSCMessaging:
    """Test OSC message sending"""
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_send_osc_messages_person1(self, mock_cap, mock_osc_class, mock_pose):
        """Test OSC messages sent for person 1"""
        mock_osc_instance = Mock()
        mock_osc_class.return_value = mock_osc_instance
        
        tracker = MovementTracker()
        
        metrics = {
            'left_hand_x': 0.5,
            'left_hand_y': 0.6,
            'motion_energy': 50.0
        }
        
        tracker.send_osc_messages(metrics, person_id=0)
        
        # Verify OSC messages sent with correct addresses
        calls = mock_osc_instance.send_message.call_args_list
        
        # Check that messages were sent
        assert mock_osc_instance.send_message.call_count >= 3
        
        # Verify person1 addressing
        addresses = [call[0][0] for call in calls]
        assert any('/movement/person1/' in addr for addr in addresses)
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_send_global_stats(self, mock_cap, mock_osc_class, mock_pose):
        """Test global statistics OSC messages"""
        mock_osc_instance = Mock()
        mock_osc_class.return_value = mock_osc_instance
        
        tracker = MovementTracker()
        tracker.tracking_active = [True, True, False, False]
        tracker.motion_energy = [50.0, 30.0, 0.0, 0.0]
        
        tracker.send_global_stats(num_people=2)
        
        # Verify num_people message
        calls = mock_osc_instance.send_message.call_args_list
        addresses = [call[0][0] for call in calls]
        
        assert '/movement/num_people' in addresses
        assert '/movement/avg_energy' in addresses


class TestMultiPersonTracking:
    """Test multi-person tracking functionality"""
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_detect_people_regions_single(self, mock_cap, mock_osc, mock_pose):
        """Test region detection for single person"""
        tracker = MovementTracker(max_people=1)
        
        # Create mock frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        regions = tracker.detect_people_regions(frame)
        
        assert len(regions) == 1
        assert regions[0] == (0, 0, 1280, 720)  # Full frame
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_detect_people_regions_two(self, mock_cap, mock_osc, mock_pose):
        """Test region detection for two people"""
        tracker = MovementTracker(max_people=2)
        
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        regions = tracker.detect_people_regions(frame)
        
        assert len(regions) == 2
        # Should split frame vertically
        assert regions[0][0] == 0  # First region starts at left
        assert regions[1][2] == 1280  # Second region ends at right


class TestFPSCalculation:
    """Test FPS calculation"""
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_calculate_fps(self, mock_cap, mock_osc, mock_pose):
        """Test FPS calculation from frame times"""
        tracker = MovementTracker()
        
        # Simulate 30 FPS (33.33ms per frame)
        for _ in range(10):
            tracker.calculate_fps(0.0333)
        
        # Should be approximately 30 FPS
        assert tracker.fps == pytest.approx(30.0, rel=0.1)
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_calculate_fps_rolling_average(self, mock_cap, mock_osc, mock_pose):
        """Test that FPS uses rolling average"""
        tracker = MovementTracker()
        
        # Fill with 30 frames at 60 FPS
        for _ in range(30):
            tracker.calculate_fps(0.0166)
        
        assert len(tracker.frame_times) == 30
        
        # Add one more, should maintain max 30 frames
        tracker.calculate_fps(0.0166)
        assert len(tracker.frame_times) == 30


class TestTrackingLost:
    """Test tracking lost scenarios"""
    
    @patch('movement_tracker.mp.solutions.pose.Pose')
    @patch('movement_tracker.udp_client.SimpleUDPClient')
    @patch('movement_tracker.cv2.VideoCapture')
    def test_send_tracking_lost(self, mock_cap, mock_osc_class, mock_pose):
        """Test tracking lost signal"""
        mock_osc_instance = Mock()
        mock_osc_class.return_value = mock_osc_instance
        
        tracker = MovementTracker()
        tracker.send_tracking_lost(person_id=0)
        
        # Verify tracking_active set to 0.0
        mock_osc_instance.send_message.assert_called_with(
            '/movement/person1/tracking_active',
            0.0
        )


# Integration test placeholder
class TestIntegration:
    """Integration tests requiring full system"""
    
    @pytest.mark.skip(reason="Requires camera and display")
    def test_full_tracking_loop(self):
        """Test complete tracking loop (requires hardware)"""
        # This would test the actual run() method
        # Requires camera access and display
        pass
