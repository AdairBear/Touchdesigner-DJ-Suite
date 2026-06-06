#!/usr/bin/env python3
"""Test script for TouchDesigner generative OSC integration.

This script sends OSC messages to TouchDesigner to verify all generative
control receivers are working correctly.

Usage:
    python test_td_osc_integration.py
"""

import time
from pythonosc import udp_client

# Configuration
TD_HOST = "127.0.0.1"
TD_PORT = 7000


def test_geometry_control(client):
    """Test geometry type switching."""
    print("\n" + "=" * 70)
    print("1. Testing Geometry Control")
    print("=" * 70)
    
    geometries = ["particles", "sphere", "fractals", "mesh"]
    for geo in geometries:
        print(f"Switching to: {geo}")
        client.send_message("/td/gen/geometry/type", geo)
        time.sleep(2)
    
    print("✓ Geometry control test complete")


def test_shader_palette(client):
    """Test shader color palette system."""
    print("\n" + "=" * 70)
    print("2. Testing Shader Palette")
    print("=" * 70)
    
    # Red/Black (Jungle theme)
    print("Setting jungle theme (red/black)...")
    client.send_message("/td/gen/shader/palette/color0", "#FF0000")
    client.send_message("/td/gen/shader/palette/color1", "#000000")
    client.send_message("/td/gen/shader/palette/intensity", 0.9)
    time.sleep(3)
    
    # Blue/Cyan (Techno theme)
    print("Setting techno theme (blue/cyan)...")
    client.send_message("/td/gen/shader/palette/color0", "#0000FF")
    client.send_message("/td/gen/shader/palette/color1", "#00FFFF")
    client.send_message("/td/gen/shader/palette/intensity", 0.8)
    time.sleep(3)
    
    # Purple/Pink (Happy Hardcore theme)
    print("Setting happy hardcore theme (purple/pink)...")
    client.send_message("/td/gen/shader/palette/color0", "#FF00FF")
    client.send_message("/td/gen/shader/palette/color1", "#FF69B4")
    client.send_message("/td/gen/shader/palette/intensity", 1.0)
    time.sleep(3)
    
    print("✓ Shader palette test complete")


def test_background_color(client):
    """Test background color control."""
    print("\n" + "=" * 70)
    print("3. Testing Background Color")
    print("=" * 70)
    
    backgrounds = [
        ("#000000", "Black"),
        ("#1a1a1a", "Dark Gray"),
        ("#000033", "Dark Blue"),
    ]
    
    for color, name in backgrounds:
        print(f"Setting background: {name} ({color})")
        client.send_message("/td/gen/background/color", color)
        time.sleep(2)
    
    print("✓ Background color test complete")


def test_effect_triggers(client):
    """Test visual effect triggering."""
    print("\n" + "=" * 70)
    print("4. Testing Effect Triggers")
    print("=" * 70)
    
    # Particle burst
    print("Triggering particle burst (2s duration)...")
    client.send_message("/td/gen/effect/particle_burst/duration", 2.0)
    client.send_message("/td/gen/effect/particle_burst/intensity", 0.8)
    client.send_message("/td/gen/effect/particle_burst/trigger", 1)
    time.sleep(3)
    
    # Flash effect
    print("Triggering flash effect (0.5s duration)...")
    client.send_message("/td/gen/effect/flash/duration", 0.5)
    client.send_message("/td/gen/effect/flash/trigger", 1)
    time.sleep(2)
    
    # Pulse effect
    print("Triggering pulse effect (1.5s duration)...")
    client.send_message("/td/gen/effect/pulse/duration", 1.5)
    client.send_message("/td/gen/effect/pulse/trigger", 1)
    time.sleep(2)
    
    print("✓ Effect trigger test complete")


def test_sync_mappings(client):
    """Test audio-visual sync mapping system."""
    print("\n" + "=" * 70)
    print("5. Testing Sync Mappings")
    print("=" * 70)
    
    # Map bass RMS to particle spawn rate
    print("Mapping bass_rms → particle_spawn_rate (exponential, 5x)...")
    client.send_message("/td/gen/sync/bass_rms/target", "particle_spawn_rate")
    client.send_message("/td/gen/sync/bass_rms/curve", "exponential")
    client.send_message("/td/gen/sync/bass_rms/multiplier", 5.0)
    time.sleep(1)
    
    # Map onset strength to flash intensity
    print("Mapping onset_strength → flash_intensity (linear, 4x)...")
    client.send_message("/td/gen/sync/onset_strength/target", "flash_intensity")
    client.send_message("/td/gen/sync/onset_strength/curve", "linear")
    client.send_message("/td/gen/sync/onset_strength/multiplier", 4.0)
    time.sleep(1)
    
    # Map high frequency to color rotation
    print("Mapping high_freq → color_rotation (exponential, 2x)...")
    client.send_message("/td/gen/sync/high_freq/target", "color_rotation")
    client.send_message("/td/gen/sync/high_freq/curve", "exponential")
    client.send_message("/td/gen/sync/high_freq/multiplier", 2.0)
    time.sleep(1)
    
    print("✓ Sync mapping test complete")


def test_parameter_control(client):
    """Test arbitrary parameter control."""
    print("\n" + "=" * 70)
    print("6. Testing Arbitrary Parameter Control")
    print("=" * 70)
    
    # Control noise amplitude
    print("Setting noise amplitude to 0.5...")
    client.send_message("/td/gen/param/noise1/amplitude", 0.5)
    time.sleep(1)
    
    # Control rotation speed
    print("Setting rotation speed to 30...")
    client.send_message("/td/gen/param/rotate1/speed", 30.0)
    time.sleep(1)
    
    # Control blur amount
    print("Setting blur amount to 0.2...")
    client.send_message("/td/gen/param/blur1/size", 0.2)
    time.sleep(1)
    
    print("✓ Parameter control test complete")


def test_full_composition(client):
    """Test full composition scenario: jungle track with synchronized visuals."""
    print("\n" + "=" * 70)
    print("7. Full Composition Test: Jungle Track (174 BPM)")
    print("=" * 70)
    
    # Setup jungle visual theme
    print("Setting up jungle visual theme...")
    client.send_message("/td/gen/geometry/type", "particles")
    client.send_message("/td/gen/shader/palette/color0", "#FF0000")  # Deep red
    client.send_message("/td/gen/shader/palette/color1", "#8B0000")  # Dark red
    client.send_message("/td/gen/shader/palette/intensity", 0.95)
    client.send_message("/td/gen/background/color", "#0a0000")  # Very dark red
    time.sleep(2)
    
    # Setup audio-visual sync
    print("Configuring audio-visual sync for jungle bassline...")
    client.send_message("/td/gen/sync/bass_rms/target", "particle_spawn_rate")
    client.send_message("/td/gen/sync/bass_rms/curve", "exponential")
    client.send_message("/td/gen/sync/bass_rms/multiplier", 5.0)
    
    client.send_message("/td/gen/sync/onset_strength/target", "flash_intensity")
    client.send_message("/td/gen/sync/onset_strength/curve", "linear")
    client.send_message("/td/gen/sync/onset_strength/multiplier", 3.0)
    time.sleep(1)
    
    # Simulate transport play with burst effect
    print("Simulating transport play → particle burst...")
    client.send_message("/td/gen/effect/particle_burst/duration", 2.0)
    client.send_message("/td/gen/effect/particle_burst/intensity", 0.9)
    client.send_message("/td/gen/effect/particle_burst/trigger", 1)
    time.sleep(3)
    
    # Simulate beat flashes every 0.345s (174 BPM)
    print("Simulating beat-synced flashes...")
    for i in range(8):  # 2 bars of 4 beats
        client.send_message("/td/gen/effect/flash/duration", 0.1)
        client.send_message("/td/gen/effect/flash/trigger", 1)
        time.sleep(0.345)  # 174 BPM quarter note
    
    print("✓ Full composition test complete")


def main():
    """Run all tests."""
    print("\n" + "#" * 70)
    print("TouchDesigner Generative OSC Integration Test Suite")
    print("#" * 70)
    print(f"\nTarget: {TD_HOST}:{TD_PORT}")
    print("\nMake sure TouchDesigner is running with dj_visuals.toe open!")
    input("\nPress Enter to start tests...")
    
    # Create OSC client
    client = udp_client.SimpleUDPClient(TD_HOST, TD_PORT)
    
    try:
        # Run all tests
        test_geometry_control(client)
        test_shader_palette(client)
        test_background_color(client)
        test_effect_triggers(client)
        test_sync_mappings(client)
        test_parameter_control(client)
        test_full_composition(client)
        
        print("\n" + "=" * 70)
        print("All Tests Complete!")
        print("=" * 70)
        print("\nIf you saw visual changes in TouchDesigner, the integration is working!")
        print("If nothing happened, check:")
        print("  1. TouchDesigner is running")
        print("  2. OSC In CHOP is on port 7000")
        print("  3. Filter pattern is '/td/gen/*'")
        print("  4. CHOP Execute DATs are enabled")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n\nTest error: {e}")


if __name__ == "__main__":
    main()
