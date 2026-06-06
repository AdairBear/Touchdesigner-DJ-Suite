ai = op('/project1/audio_in')
s  = op('/project1/audio_spectrum')

# DDJ-SX2 USB audio interface - same source BUTT uses
DDJ_UID = 'AppleUSBAudioEngine:Pioneer:PIONEER DDJ-SX2:PIONEER DDJ-SX2:2,1'

ai.par.device = DDJ_UID
ai.cook(force=True)
s.cook(force=True)

chans = [abs(float(c)) for c in ai.chans()]
peak  = round(max(chans), 4)
spec_bins = [float(c) for c in s.chans()]
spec_max  = round(max(spec_bins), 5)

print('[ddj] device:', ai.par.device.val)
print('[ddj] chans:', ai.numChans)
print('[ddj] peak:', peak)
print('[ddj] spec_max:', spec_max)
if peak > 0.01:
    print('[ddj] *** AUDIO LIVE - DDJ-SX2 mix is flowing! ***')
elif peak > 0.001:
    print('[ddj] low signal - DDJ may be idle or fader down')
else:
    print('[ddj] silence - check DDJ-SX2 is connected and playing')
