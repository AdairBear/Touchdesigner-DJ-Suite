ai = op('/project1/audio_in')
# AudioIn CHOP exposes menuSource for its device parameter
# We can iterate the menu items to see all available devices
menu = ai.par.device.menuNames
labels = ai.par.device.menuLabels
print('[devices] count:', len(menu))
for uid, label in zip(menu, labels):
    print(f'  UID: {repr(uid)}')
    print(f'  Label: {repr(label)}')
    print()
