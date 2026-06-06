ai = op('/project1/audio_in')
s  = op('/project1/audio_spectrum')
chans = [abs(float(c)) for c in ai.chans()]
peak  = round(max(chans), 4)
spec_bins = [float(c) for c in s.chans()]
spec_max  = round(max(spec_bins), 5)
spec_top5 = sorted(spec_bins, reverse=True)[:5]
print('[audio-check] device:', ai.par.device.val)
print('[audio-check] chans:', ai.numChans, '| peak:', peak)
print('[audio-check] spectrum chans:', s.numChans, '| spec_max:', spec_max)
print('[audio-check] top 5 bins:', [round(x, 4) for x in spec_top5])
if peak > 0.01:
    print('[audio-check] *** AUDIO LIVE ***')
elif peak > 0.001:
    print('[audio-check] low signal - check Serato is routing to BlackHole')
else:
    print('[audio-check] silence')
