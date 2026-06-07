# Quick diagnostic — reports errors/warnings for every aura operator.
# v2 op set (matches build_network_v2.py). v1 names removed:
#   flame_layers, burst_flash, noise_embers, camera_in, output,
#   audio_params, audio_reactive_mapper, motion_energy_top,
#   audio_energy_top, osc_body_receiver, body_channels
#   — camera_in is INTENTIONALLY absent in v2 (OBS owns the camera);
#     "output" is now the Null TOP "final_composite".
ops = [
    "body_mask_top",
    "edge_detect",
    "edge_blur",
    "zero_src",
    "fire_aura_glsl",
    "lightning_glsl",
    "visual_switch",
    "bloom_blur",
    "bloom_post",
    "final_composite",
    "syphonOut1",
    "audio_in",
    "audio_spectrum",
    "oscin1",
    "aura_compositor",
]
bad = []
for n in ops:
    o = op("/project1/" + n)
    if o is None:
        bad.append((n, "MISSING"))
        continue
    e = o.errors()
    w = o.warnings()
    if e:
        bad.append((n, "ERR: " + e[:120]))
    elif w:
        bad.append((n, "WARN: " + w[:120]))

print("\n=== AURA PIPELINE DIAGNOSTIC ===")
print("Total ops checked:", len(ops))
print("Issues found:", len(bad))
for n, msg in bad:
    print(" -", n, ":", msg)
if not bad:
    print("ALL CLEAN")
