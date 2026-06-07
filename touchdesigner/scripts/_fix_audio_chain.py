# Diagnose + fix audio reactivity chain.
# After running, audio_reactive_mapper should be watching audio_spectrum
# and writing values into audio_params.

ROOT = '/project1'

def p(o, *names):
    out = {}
    for n in names:
        par = getattr(o.par, n, None)
        if par is None:
            out[n] = '<missing>'
        else:
            try:
                out[n] = par.val
            except Exception as e:
                out[n] = 'ERR:' + str(e)
    return out

# -------- 1. audio_in --------
ai = op(ROOT + '/audio_in')
print('\n=== audio_in ===')
print('  type:', ai.type if ai else None, '/', (ai.OPType if ai else None))
if ai is not None:
    print('  params:', p(ai, 'active', 'driver', 'device', 'format', 'samplerate'))
    print('  errors:', ai.errors() or 'none')
    print('  warnings:', ai.warnings() or 'none')
    # List device pulldown options
    for pname in ('device', 'driver'):
        par = getattr(ai.par, pname, None)
        if par is not None:
            try:
                print('  ' + pname + ' menuLabels:', list(par.menuLabels) if par.menuLabels else None)
                print('  ' + pname + ' menuNames :', list(par.menuNames)  if par.menuNames  else None)
            except Exception as e:
                print('  ' + pname + ' menu err:', e)
    # Show channel values
    try:
        chans = ai.chans()
        print('  chans:', [(c.name, float(c)) for c in chans[:4]])
    except Exception as e:
        print('  chans err:', e)

# -------- 2. audio_spectrum --------
asp = op(ROOT + '/audio_spectrum')
print('\n=== audio_spectrum ===')
if asp is not None:
    print('  type:', asp.type, '/', asp.OPType)
    print('  errors:', asp.errors() or 'none')
    print('  warnings:', asp.warnings() or 'none')
    try:
        print('  numSamples:', asp.numSamples)
        print('  numChans  :', asp.numChans)
        chans = asp.chans()
        if chans:
            c0 = chans[0]
            # Show first 6 bins to see if anything is flowing
            vals = [c0[i] for i in range(min(6, len(c0)))]
            mx = max((abs(c0[i]) for i in range(len(c0))), default=0.0)
            print('  first 6 bin values:', vals)
            print('  max abs across all bins:', mx)
    except Exception as e:
        print('  sample err:', e)

# -------- 3. audio_reactive_mapper --------
arm = op(ROOT + '/audio_reactive_mapper')
print('\n=== audio_reactive_mapper ===')
if arm is not None:
    print('  type:', arm.type, '/', arm.OPType)
    print('  errors:', arm.errors() or 'none')
    print('  warnings:', arm.warnings() or 'none')
    print('  pars:', p(arm, 'active', 'chop', 'valuechange', 'whileon', 'offtoon', 'ontooff', 'file', 'syncfile'))
    # Is script text actually present?
    try:
        txt = arm.text or ''
        print('  script length:', len(txt))
        print('  has onValueChange def:', 'def onValueChange' in txt)
    except Exception as e:
        print('  text err:', e)

# -------- 4. audio_params --------
apar = op(ROOT + '/audio_params')
print('\n=== audio_params ===')
if apar is not None:
    print('  type:', apar.type, '/', apar.OPType)
    print('  errors:', apar.errors() or 'none')
    print('  warnings:', apar.warnings() or 'none')
    try:
        chans = apar.chans()
        print('  channel count:', len(chans))
        for c in chans:
            print('    {0:20s} = {1:.4f}'.format(c.name, float(c)))
    except Exception as e:
        print('  chans err:', e)

# -------- 4b. AUTO-SET audio_in DRIVER + DEVICE --------
print('\n=== AUTO-SELECT audio_in DEVICE ===')
# Preferred device keywords in priority order (first hit wins).
# 1824c = PreSonus Studio 1824c (what OBS is using).
DEVICE_PRIORITIES = [
    '1824c', '1824', 'studio 1824',
    'presonus', 'djm-250', 'djm',
    'blackhole', 'loopback',
    'built-in', 'built in', 'macbook',
]

def _pick(labels, names, priorities):
    """Return the first (label,name) tuple where a priority keyword is a substring (case-insensitive)."""
    if not labels or not names:
        return (None, None)
    pairs = list(zip(labels, names))
    for kw in priorities:
        for lab, nm in pairs:
            if kw.lower() in (lab or '').lower() or kw.lower() in (nm or '').lower():
                return (lab, nm)
    return (None, None)

if ai is not None:
    # Driver: prefer Core Audio on macOS.
    try:
        drv_labels = list(ai.par.driver.menuLabels) if ai.par.driver.menuLabels else []
        drv_names  = list(ai.par.driver.menuNames)  if ai.par.driver.menuNames  else []
        print('  driver labels :', drv_labels)
        print('  driver names  :', drv_names)
        # Match any name/label containing 'core' (for 'Core Audio' on macOS, 'CoreAudio' also works).
        drv_pick_label, drv_pick_name = _pick(drv_labels, drv_names, ['core audio', 'coreaudio', 'core'])
        if drv_pick_name:
            ai.par.driver = drv_pick_name
            print('  => set driver =', drv_pick_name, '(label:', drv_pick_label, ')')
        else:
            print('  NO DRIVER MATCH -- leaving as:', ai.par.driver.val)
    except Exception as e:
        print('  driver err:', e)

    # Device: prefer 1824c (OBS capture). Need to refresh menu after driver change.
    try:
        # Force-cook to refresh device list with new driver
        ai.cook(force=True)
        dev_labels = list(ai.par.device.menuLabels) if ai.par.device.menuLabels else []
        dev_names  = list(ai.par.device.menuNames)  if ai.par.device.menuNames  else []
        print('  device labels :', dev_labels)
        print('  device names  :', dev_names)
        dev_pick_label, dev_pick_name = _pick(dev_labels, dev_names, DEVICE_PRIORITIES)
        if dev_pick_name:
            ai.par.device = dev_pick_name
            print('  => set device =', dev_pick_name, '(label:', dev_pick_label, ')')
        else:
            print('  NO DEVICE MATCH -- leaving as:', ai.par.device.val)
    except Exception as e:
        print('  device err:', e)

    # Ensure active and cook
    try:
        ai.par.active = True
        ai.cook(force=True)
        print('  audio_in errors :', ai.errors() or 'none')
        print('  audio_in warnings:', ai.warnings() or 'none')
        # Show sample values after reconfig
        try:
            chans = ai.chans()
            if chans:
                print('  audio_in chans :', [(c.name, float(c)) for c in chans[:4]])
        except Exception as e:
            print('  audio_in chans err:', e)
    except Exception as e:
        print('  audio_in active err:', e)

# Also force-cook audio_spectrum so it picks up audio_in's new signal
if asp is not None:
    try:
        asp.cook(force=True)
        chans = asp.chans()
        if chans:
            c0 = chans[0]
            mx = max((abs(c0[i]) for i in range(len(c0))), default=0.0)
            print('  audio_spectrum max abs bin:', mx)
    except Exception as e:
        print('  audio_spectrum cook err:', e)

# -------- 5. APPLY FIXES TO MAPPER --------
print('\n=== APPLYING FIXES ===')
if arm is not None:
    # Ensure script file is loaded & syncing
    try:
        mapper_script_path = project.folder + '/touchdesigner/scripts/audio_reactive_mapper.py'
        import os as _os
        if _os.path.exists(mapper_script_path):
            if arm.par.file.val != mapper_script_path:
                arm.par.file.val = mapper_script_path
                print('  set file =', mapper_script_path)
            arm.par.syncfile = True
            print('  syncfile = True')
        else:
            print('  WARNING: mapper script file not found at', mapper_script_path)
    except Exception as e:
        print('  file par err:', e)
    # Watch the spectrum CHOP
    try:
        arm.par.chop = 'audio_spectrum'
        print('  chop = audio_spectrum')
    except Exception as e:
        print('  chop par err:', e)
    # Fire onValueChange
    try:
        arm.par.valuechange = True
        print('  valuechange = True')
    except Exception as e:
        print('  valuechange err:', e)
    # Turn on
    try:
        arm.par.active = True
        print('  active = True')
    except Exception as e:
        print('  active err:', e)
    arm.cook(force=True)
    print('  post-fix errors:', arm.errors() or 'none')
    print('  post-fix warnings:', arm.warnings() or 'none')

# Make sure audio_in is on
if ai is not None:
    try:
        ai.par.active = True
        print('  audio_in.active = True')
    except Exception as e:
        print('  audio_in.active err:', e)

# -------- 6. REPORT AGAIN --------
print('\n=== audio_params AFTER FIX ===')
if apar is not None:
    try:
        chans = apar.chans()
        for c in chans:
            print('    {0:20s} = {1:.4f}'.format(c.name, float(c)))
    except Exception as e:
        print('  err:', e)
