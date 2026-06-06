ai = op('/project1/audio_in')
s  = op('/project1/audio_spectrum')
ai.par.device = 'BlackHole2ch_UID'
ai.cook(force=True)
s.cook(force=True)
peak = round(max([abs(float(c)) for c in ai.chans()]), 4)
spec = round(max([float(c) for c in s.chans()]), 4)
print('[blackhole] device:', ai.par.device.val)
print('[blackhole] chans:', ai.numChans)
print('[blackhole] peak:', peak)
print('[blackhole] spec_max:', spec)
if peak > 0.01:
    print('[blackhole] AUDIO FLOWING!')
else:
    print('[blackhole] silent - route Serato output to BlackHole in Serato Prefs > Audio')
