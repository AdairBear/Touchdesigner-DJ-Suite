"""
Pytest configuration for TouchDesigner DJ Suite tests
"""

import pytest
import sys
from pathlib import Path

# Add python directory to path for all tests
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))


# Pytest configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring hardware (camera, OBS, etc.)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Common fixtures
@pytest.fixture
def mock_frame():
    """Fixture providing a mock camera frame"""
    import numpy as np
    return np.zeros((720, 1280, 3), dtype=np.uint8)


@pytest.fixture
def mock_landmarks():
    """Fixture providing mock MediaPipe landmarks"""
    from unittest.mock import Mock
    
    landmarks = []
    for i in range(33):  # MediaPipe has 33 pose landmarks
        landmark = Mock()
        landmark.x = 0.5
        landmark.y = 0.5
        landmark.z = 0.0
        landmark.visibility = 0.8
        landmarks.append(landmark)
    
    return landmarks


@pytest.fixture
def test_config():
    """Fixture providing test configuration"""
    return {
        'osc_ip': '127.0.0.1',
        'osc_port': 7000,
        'obs_host': 'localhost',
        'obs_port': 4455,
        'camera_index': 0,
        'max_people': 4
    }
