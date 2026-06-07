# Audit the audio reactivity chain end-to-end.
ops_to_check = [
    'audio_in',            # Audio Device In CHOP
    'audio_spectrum',      # Audio Spectrum CHOP
    'audio_params',        # Constant CHOP (output of audio_reactive_mapper)
    'audio_reactive_mapper', # Execute DAT / script CHOP that fills audio_params
    'audio_energy_top',    # Motion/energy debug TOP
]

print('\n=== AUDIO CHAIN AUDIT ===')
for name in ops_to_check:
    o = op('/project1/' + name)
    if o is None:
        print(f'{name}: MISSING')
        continue
    print(f'\n--- {name}  ({o.type}/{o.OPType}) ---')
    err = o.errors(); warn = o.warnings()
    print('  errors:', err or 'none')
    print('  warnings:', warn or 'none')
    # Print a few key pars
    for pname in ('device','driver','format','active','source','sample'):
        p = getattr(o.par, pname, None)
        if p:
            try:
                print(f'  par.{pname} = {p.val!r} (menu={getattr(p,"menuLabels",None)!r})' if getattr(p,"menuLabels",None) else f'  par.{pname} = {p.val!r}')
            except Exception:
                pass
    # For CHOPs dump channels + ranges
    if hasattr(o, 'chans'):
        try:
            chans = o.chans()
            print(f'  channels ({len(chans)}):')
            for c in chans[:16]:
                print(f'    {c.name:20s} val={float(c):.4f}')
            if len(chans) > 16:
                print(f'    ... and {len(chans)-16} more')
        except Exception as e:
            print('  chans err:', e)

# Also list connectors
print('\n=== CONNECTIONS ===')
for name in ops_to_check:
    o = op('/project1/' + name)
    if o is None: continue
    ins = [c.connections for c in o.inputConnectors]
    outs = [c.connections for c in o.outputConnectors]
    in_names = [[i.owner.name for i in group] for group in ins]
    out_names = [[i.owner.name for i in group] for group in outs]
    print(f'{name:22s} in={in_names}  out={out_names}')
