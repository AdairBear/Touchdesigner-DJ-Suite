ai = op('/project1/audio_in')
s  = op('/project1/audio_spectrum')

# Serato Virtual Audio — enabled via Serato Prefs > Audio > "Make Audio Available to Other Applications"
ai.par.device = 'VirtualAudio_UID'
ai.cook(force=True)
s.cook(force=True)

chans = [abs(float(c)) for c in ai.chans()]
peak  = round(max(chans), 4)
spec_bins = [float(c) for c in s.chans()]
spec_max  = round(max(spec_bins), 5)
top5 = sorted(spec_bins, reverse=True)[:5]

print('[serato-va] device:', ai.par.device.val)
print('[serato-va] chans:', ai.numChans, '| peak:', peak)
print('[serato-va] spec_max:', spec_max)
print('[serato-va] top5 bins:', [round(x,4) for x in top5])
if peak > 0.05:
    print('[serato-va] *** AUDIO LIVE - Serato mix is flowing! ***')
elif peak > 0.005:
    print('[serato-va] weak signal - track may need to be louder / fader up')
else:
    print('[serato-va] silence')
