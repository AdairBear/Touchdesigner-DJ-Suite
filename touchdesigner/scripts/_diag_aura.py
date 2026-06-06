# Quick diagnostic — reports errors/warnings for every aura operator
ops = [
    'body_mask_top','edge_detect','edge_blur','fire_aura_glsl',
    'flame_layers','bloom_blur','bloom_post','burst_flash',
    'noise_embers','camera_in','final_composite','output','syphonOut1',
    'audio_in','audio_spectrum','audio_params','audio_reactive_mapper',
    'motion_energy_top','audio_energy_top',
    'osc_body_receiver','body_channels','aura_compositor',
]
bad = []
for n in ops:
    o = op('/project1/' + n)
    if o is None:
        bad.append((n, 'MISSING'))
        continue
    e = o.errors()
    w = o.warnings()
    if e:
        bad.append((n, 'ERR: ' + e[:120]))
    elif w:
        bad.append((n, 'WARN: ' + w[:120]))

print('\n=== AURA PIPELINE DIAGNOSTIC ===')
print('Total ops checked:', len(ops))
print('Issues found:', len(bad))
for n, msg in bad:
    print(' -', n, ':', msg)
if not bad:
    print('ALL CLEAN')
