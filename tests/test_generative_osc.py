"""
Test script for TouchDesigner generative OSC integration.

Run this after implementing the TouchDesigner side to verify all OSC commands work.
Requires TouchDesigner project running with generative OSC receivers configured.
"""

import time
from pythonosc import udp_client

OSC_IP = "127.0.0.1"
OSC_PORT = 7000

def test_geometry_switching(client: udp_client.SimpleUDPClient):
    """Test geometry type switching."""
    print("\n[TEST] Geometry Switching")
    print("-" * 50)
    
    geometries = ["particles", "sphere", "fractals", "mesh"]
    
    for geo in geometries:
        print(f"  → Switching to: {geo}")
        client.send_message("/td/gen/geometry/type", geo)
        time.sleep(2)  # Give TouchDesigner time to switch
    
    print("  ✓ Geometry switching test complete")

def test_shader_palette(client: udp_client.SimpleUDPClient):
    """Test shader color palette updates."""
    print("\n[TEST] Shader Palette")
    print("-" * 50)
    
    palettes = [
        {"name": "Jungle (Red/Black)", "colors": ["#FF0000", "#000000"], "intensity": 0.9},
        {"name": "Techno (Cyan/Purple)", "colors": ["#00FFFF", "#FF00FF"], "intensity": 0.7},
        {"name": "Ambient (Blue/White)", "colors": ["#0000FF", "#FFFFFF"], "intensity": 0.5},
    ]
    
    for palette in palettes:
        print(f"  → {palette['name']}")
        client.send_message("/td/gen/shader/palette/color0", palette["colors"][0])
        client.send_message("/td/gen/shader/palette/color1", palette["colors"][1])
        client.send_message("/td/gen/shader/palette/intensity", palette["intensity"])
        time.sleep(3)
    
    print("  ✓ Shader palette test complete")

def test_effects(client: udp_client.SimpleUDPClient):
    """Test visual effect triggers."""
    print("\n[TEST] Effect Triggers")
    print("-" * 50)
    
    effects = [
        {"name": "particle_burst", "duration": 2.0, "intensity": 0.8},
        {"name": "flash", "duration": 0.5, "intensity": 1.0},
        {"name": "pulse", "duration": 1.5, "intensity": 0.9},
    ]
    
    for effect in effects:
        print(f"  → Triggering: {effect['name']} ({effect['duration']}s)")
        client.send_message(f"/td/gen/effect/{effect['name']}/trigger", 1)
        client.send_message(f"/td/gen/effect/{effect['name']}/duration", effect["duration"])
        client.send_message(f"/td/gen/effect/{effect['name']}/intensity", effect["intensity"])
        time.sleep(effect["duration"] + 1)  # Wait for effect to complete
    
    print("  ✓ Effect trigger test complete")

def test_sync_mapping(client: udp_client.SimpleUDPClient):
    """Test audio-visual sync mappings."""
    print("\n[TEST] Sync Mappings")
    print("-" * 50)
    
    mappings = [
        {"audio": "bass_rms", "visual": "particle_spawn_rate", "curve": "exponential", "mult": 5.0},
        {"audio": "onset_strength", "visual": "flash_intensity", "curve": "linear", "mult": 2.0},
        {"audio": "break_complexity", "visual": "rotation_speed", "curve": "logarithmic", "mult": 1.5},
    ]
    
    for mapping in mappings:
        print(f"  → Mapping: {mapping['audio']} → {mapping['visual']} ({mapping['curve']})")
        client.send_message(f"/td/gen/sync/{mapping['audio']}/target", mapping["visual"])
        client.send_message(f"/td/gen/sync/{mapping['audio']}/curve", mapping["curve"])
        client.send_message(f"/td/gen/sync/{mapping['audio']}/multiplier", mapping["mult"])
        time.sleep(1)
    
    print("  ✓ Sync mapping test complete")

def test_background_settings(client: udp_client.SimpleUDPClient):
    """Test background configuration."""
    print("\n[TEST] Background Settings")
    print("-" * 50)
    
    backgrounds = [
        {"type": "gradient", "color0": "#000000", "color1": "#330033"},
        {"type": "noise", "color0": "#001100", "color1": "#003300"},
        {"type": "solid", "color0": "#000000", "color1": "#000000"},
    ]
    
    for bg in backgrounds:
        print(f"  → Background: {bg['type']}")
        client.send_message("/td/gen/background/type", bg["type"])
        client.send_message("/td/gen/background/color0", bg["color0"])
        client.send_message("/td/gen/background/color1", bg["color1"])
        time.sleep(2)
    
    print("  ✓ Background settings test complete")

def test_arbitrary_params(client: udp_client.SimpleUDPClient):
    """Test arbitrary parameter control."""
    print("\n[TEST] Arbitrary Parameter Control")
    print("-" * 50)
    
    params = [
        {"path": "noise1/amplitude", "value": 0.5},
        {"path": "noise1/frequency", "value": 2.0},
        {"path": "level1/opacity", "value": 0.8},
    ]
    
    for param in params:
        print(f"  → Setting: {param['path']} = {param['value']}")
        client.send_message(f"/td/gen/param/{param['path']}", param["value"])
        time.sleep(1)
    
    print("  ✓ Arbitrary parameter test complete")

def run_full_demo(client: udp_client.SimpleUDPClient):
    """Run a full demo sequence combining all features."""
    print("\n[DEMO] Full Generative Sequence")
    print("=" * 50)
    
    # Setup: Particle system with jungle colors
    print("\n1. Setup: Jungle particle system")
    client.send_message("/td/gen/geometry/type", "particles")
    client.send_message("/td/gen/shader/palette/color0", "#FF0000")
    client.send_message("/td/gen/shader/palette/color1", "#000000")
    client.send_message("/td/gen/shader/palette/intensity", 0.9)
    time.sleep(2)
    
    # Map bass to particle spawn rate
    print("2. Map bass → particle spawn")
    client.send_message("/td/gen/sync/bass_rms/target", "particle_spawn_rate")
    client.send_message("/td/gen/sync/bass_rms/curve", "exponential")
    client.send_message("/td/gen/sync/bass_rms/multiplier", 5.0)
    time.sleep(1)
    
    # Trigger build-up effect
    print("3. Trigger particle burst (build-up)")
    client.send_message("/td/gen/effect/particle_burst/trigger", 1)
    client.send_message("/td/gen/effect/particle_burst/duration", 4.0)
    client.send_message("/td/gen/effect/particle_burst/intensity", 0.9)
    time.sleep(4)
    
    # Drop: flash + pulse
    print("4. Trigger drop effects")
    client.send_message("/td/gen/effect/flash/trigger", 1)
    client.send_message("/td/gen/effect/flash/duration", 1.0)
    client.send_message("/td/gen/effect/pulse/trigger", 1)
    client.send_message("/td/gen/effect/pulse/duration", 2.0)
    time.sleep(2)
    
    # Switch to fractals for breakdown
    print("5. Breakdown: Switch to fractals")
    client.send_message("/td/gen/geometry/type", "fractals")
    client.send_message("/td/gen/shader/palette/color0", "#0000FF")
    client.send_message("/td/gen/shader/palette/color1", "#330033")
    client.send_message("/td/gen/shader/palette/intensity", 0.5)
    time.sleep(3)
    
    # Back to particles for outro
    print("6. Outro: Return to particles")
    client.send_message("/td/gen/geometry/type", "particles")
    client.send_message("/td/gen/shader/palette/intensity", 0.3)
    time.sleep(2)
    
    print("\n  ✓ Full demo sequence complete\n")

def main():
    """Run all tests."""
    print("=" * 50)
    print("TouchDesigner Generative OSC Test Suite")
    print("=" * 50)
    print(f"\nTarget: {OSC_IP}:{OSC_PORT}")
    print("\nMake sure TouchDesigner is running with OSC receivers configured!")
    print("See: GENERATIVE_OSC_CHECKLIST.md for setup instructions")
    
    input("\nPress Enter to start tests...")
    
    # Create OSC client
    client = udp_client.SimpleUDPClient(OSC_IP, OSC_PORT)
    
    try:
        # Run individual tests
        test_geometry_switching(client)
        time.sleep(1)
        
        test_shader_palette(client)
        time.sleep(1)
        
        test_effects(client)
        time.sleep(1)
        
        test_sync_mapping(client)
        time.sleep(1)
        
        test_background_settings(client)
        time.sleep(1)
        
        test_arbitrary_params(client)
        time.sleep(1)
        
        # Run full demo
        input("\nPress Enter to run full demo sequence...")
        run_full_demo(client)
        
        print("\n" + "=" * 50)
        print("All tests complete!")
        print("=" * 50)
        print("\nIf you saw visual changes in TouchDesigner, the integration is working.")
        print("If not, check the troubleshooting section in GENERATIVE_OSC_CHECKLIST.md")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n\nError during tests: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
