# obs_websocket_td.py — CHOP Execute DAT
# Paste into a CHOP Execute DAT. Set CHOPs = your beat detection Null CHOP.
#
# SETUP (do this first in TouchDesigner):
#   1. Download TD-OBSWebSocket.tox from github.com/acdvs/TD-OBSWebSocket
#   2. Drag .tox into your network — it creates a Base COMP
#   3. Inside the Base COMP, set:
#        Host     = 127.0.0.1
#        Port     = 4455
#        Password = (whatever you set in OBS → Tools → WebSocket Server Settings)
#   4. Click Connect button inside the tox
#   5. Green light = connected. Then wire this DAT to your beat CHOP.
#
# OBS WebSocket must be enabled:
#   OBS → Tools → WebSocket Server Settings → Enable WebSocket Server ✓
#   Port: 4455, set a password, note it down.

# ─── CONSTANTS ───────────────────────────────────────────────────────────────
KICK_SCENE_THRESHOLD  = 0.90    # kick_onset must exceed this to trigger scene switch
KICK_FRAMES_REQUIRED  = 3       # consecutive frames above threshold before switching
SCENE_COOLDOWN_SEC    = 8.0     # minimum seconds between scene switches

# Scene names — match exactly what's in OBS (case-sensitive)
SCENES = {
    'drop':   'Drop Scene',
    'build':  'Build Scene',
    'normal': 'Main Scene',
}

# State
_kick_frames_high    = 0
_last_switch_time    = -999.0

def _get_obs_tox():
    """Find the TD-OBSWebSocket Base COMP in the network."""
    obs = op('TD-OBSWebSocket') or op('obswebsocket') or op('obs_ws')
    if not obs:
        # Try searching from root
        obs = op('/project1/TD-OBSWebSocket')
    return obs

def switch_scene(scene_name):
    """Send SetCurrentProgramScene request via TD-OBSWebSocket tox."""
    obs = _get_obs_tox()
    if not obs:
        print('[obs] ERROR: TD-OBSWebSocket tox not found in network')
        print('[obs]   Download from github.com/acdvs/TD-OBSWebSocket and drag into TD')
        return False

    # TD-OBSWebSocket tox uses a sendMessage() method or a Table DAT input
    # Send via the tox's built-in call interface
    try:
        payload = {
            "op": 6,
            "d": {
                "requestType": "SetCurrentProgramScene",
                "requestId": "td_auto_switch",
                "requestData": {"sceneName": scene_name}
            }
        }
        obs.call('sendMessage', payload)
        print(f'[obs] Scene → "{scene_name}"')
        return True
    except AttributeError:
        # Fallback: some tox versions use a text DAT input
        try:
            import json
            msg_dat = obs.op('messages_in') or obs.op('input')
            if msg_dat:
                msg_dat.text = json.dumps(payload)
                print(f'[obs] Scene → "{scene_name}" (via DAT input)')
                return True
        except Exception as e:
            print(f'[obs] Send failed: {e}')
    return False

def onValueChange(channel, sampleIndex, val, prev):
    global _kick_frames_high, _last_switch_time
    name = channel.name

    # ── Auto scene switch on sustained heavy kick ─────────────────────────
    if name == 'kick_onset':
        if val > KICK_SCENE_THRESHOLD:
            _kick_frames_high += 1
        else:
            _kick_frames_high = 0

        if _kick_frames_high >= KICK_FRAMES_REQUIRED:
            elapsed = absTime.seconds - _last_switch_time
            if elapsed >= SCENE_COOLDOWN_SEC:
                switch_scene(SCENES['drop'])
                _last_switch_time = absTime.seconds
                _kick_frames_high = 0  # reset to prevent rapid re-fire

def whileOn(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass

def onOffToOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass
