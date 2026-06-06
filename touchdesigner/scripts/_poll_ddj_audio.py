import time
ai = op('/project1/audio_in')
s  = op('/project1/audio_spectrum')

# Switch to DDJ-SX2
DDJ_UID = 'AppleUSBAudioEngine:Pioneer:PIONEER DDJ-SX2:PIONEER DDJ-SX2:2,1'
ai.par.device = DDJ_UID
ai.cook(force=True)
s.cook(force=True)
time.sleep(0.5)  # let the buffer fill

max_peak = 0.0
max_spec = 0.0
for i in range(10):
    ai.cook(force=True)
    s.cook(force=True)
    chans = [abs(float(c)) for c in ai.chans()]
    peak = max(chans) if chans else 0.0
    spec_bins = [float(c) for c in s.chans()]
    spec = max(spec_bins) if spec_bins else 0.0
    max_peak = max(max_peak, peak)
    max_spec = max(max_spec, spec)
    time.sleep(0.1)

print(f'[ddj-poll] device: {ai.par.device.val}')
print(f'[ddj-poll] chans: {ai.numChans}')
print(f'[ddj-poll] max_peak over 1s: {round(max_peak, 4)}')
print(f'[ddj-poll] max_spec over 1s: {round(max_spec, 5)}')
if max_peak > 0.01:
    print('[ddj-poll] *** AUDIO LIVE - DDJ mix is flowing! ***')
elif max_peak > 0.001:
    print('[ddj-poll] very weak signal - check DDJ levels')
else:
    print('[ddj-poll] silence - DDJ record output not reaching TD')
