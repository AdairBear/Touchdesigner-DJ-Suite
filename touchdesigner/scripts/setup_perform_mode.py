# setup_perform_mode.py -- bulletproof PERFORM MODE setup for the DJ show.
# =============================================================================
# WHY: TD's editor UI redraws every frame ("Rendering a Window" = 47 ms in a
# live capture, ~3x the 60fps budget). Perform Mode replaces the editor with a
# single fullscreen output window on the HISENSE, freeing the GPU. The output is
# /project1/final_composite -- the exact TOP that feeds syphonOut1 -> OBS.
#
# DEFENSE IN DEPTH -- three independent layers all try to land in fullscreen:
#   L1 (primary): project.performOnStart = True + project.performWindowPath.
#        TD's OWN native "boot into Perform Mode" setting, persisted in the .toe.
#        No DAT, no sentinel, no keypress. This is what F1 was missing before.
#   L2 (re-assert): /project1/perform_autostart Execute DAT. ~2s after load it
#        re-pulses setperform + ui.performMode=True and writes a heartbeat file,
#        catching the case where L1 didn't stick. Frame-delayed so it runs AFTER
#        the project is fully deserialized (not onStart-timing-dependent).
#   L3 (manual): F1 (works once performWindowPath is set) / Esc to exit.
#
# DEV OPT-OUT: create /tmp/td_no_autoperform -> L2 drops back to the editor ~2s
#   after load. The launcher removes that file so shows ALWAYS perform.
# FAIL LOUD: L2 writes /tmp/td_perform_state.json {active,reason,ts}. The
#   runbook's check_perform_mode.sh reads it and screams CRITICAL if not active.
#
# RUN IN TD TEXTPORT (Dialogs > "Textport and DATs"), paste this ONE line:
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/setup_perform_mode.py').read())
# It AUTO-SAVES the .toe (after a .perfbak.toe backup), so no manual Cmd+S.
# =============================================================================

PROJECT = "/project1"
SOURCE_TOP = "/project1/final_composite"
PERFORM_PATH = "/project1/perform"
AUTOSTART_PATH = "/project1/perform_autostart"
FORCE_MONITOR_INDEX = None   # None = auto-detect the 1920x1080 HISENSE
AUTOSAVE = True              # save the .toe in place (with backup) at the end


def _hisense_monitor():
    """(index, w, h) for the HISENSE display, detected by NAME. TD's
    monitors[].description is empty on this machine, so we read the name from
    system_profiler and match its resolution to a TD monitor. HISENSE is the 4K
    (3840x2160) here; Samsung is 1080p -- hardcoding a 1080p index landed on the
    WRONG screen, which is why this is name-based now. Falls back to the largest
    non-primary display."""
    import subprocess, re
    if FORCE_MONITOR_INDEX is not None:
        m = [x for x in monitors if x.index == FORCE_MONITOR_INDEX]
        if m:
            return m[0].index, m[0].width, m[0].height
    res = None
    try:
        out = subprocess.run(['/usr/sbin/system_profiler', 'SPDisplaysDataType'],
                             capture_output=True, text=True, timeout=12).stdout
        lines = out.splitlines()
        for i, ln in enumerate(lines):
            if 'hisense' in ln.lower() and ln.rstrip().endswith(':'):
                for j in range(i + 1, min(i + 12, len(lines))):
                    mm = re.search(r'Resolution:\s*(\d+)\s*x\s*(\d+)', lines[j])
                    if mm:
                        res = (int(mm.group(1)), int(mm.group(2)))
                        break
                break
    except Exception as e:
        print("[setup_perform] system_profiler failed: %s" % e)
    if res:
        for m in monitors:
            if m.width == res[0] and m.height == res[1]:
                return m.index, m.width, m.height
    cand = [m for m in monitors if not getattr(m, "isPrimary", False)]
    if cand:
        m = max(cand, key=lambda x: x.width * x.height)
        print("[setup_perform] HISENSE name not matched -> fallback largest non-primary idx %d" % m.index)
        return m.index, m.width, m.height
    return 0, 1920, 1080


_AUTOSTART = r'''# perform_autostart -- Layer 2 re-assert + heartbeat + dev opt-out.
import os, json, time, subprocess, re

PERFORM = "/project1/perform"
SKIP = "/tmp/td_no_autoperform"
HEARTBEAT = "/tmp/td_perform_state.json"


def _hisense():
    """(index, w, h) of the HISENSE display, by NAME (system_profiler)."""
    res = None
    try:
        out = subprocess.run(['/usr/sbin/system_profiler', 'SPDisplaysDataType'],
                             capture_output=True, text=True, timeout=12).stdout
        lines = out.splitlines()
        for i, ln in enumerate(lines):
            if 'hisense' in ln.lower() and ln.rstrip().endswith(':'):
                for j in range(i + 1, min(i + 12, len(lines))):
                    mm = re.search(r'Resolution:\s*(\d+)\s*x\s*(\d+)', lines[j])
                    if mm:
                        res = (int(mm.group(1)), int(mm.group(2)))
                        break
                break
    except Exception:
        pass
    if res:
        for m in monitors:
            if m.width == res[0] and m.height == res[1]:
                return m.index, m.width, m.height
    cand = [m for m in monitors if not getattr(m, "isPrimary", False)]
    if cand:
        m = max(cand, key=lambda x: x.width * x.height)
        return m.index, m.width, m.height
    return 0, 1920, 1080


def _write_hb(active, reason):
    try:
        with open(HEARTBEAT, "w") as f:
            json.dump({"active": bool(active), "reason": reason, "ts": time.time()}, f)
    except Exception:
        pass


def _apply():
    # Dev opt-out: /tmp/td_no_autoperform -> stay in / return to the editor.
    if os.path.exists(SKIP):
        try:
            ui.performMode = False
        except Exception:
            pass
        _write_hb(False, "dev opt-out (/tmp/td_no_autoperform)")
        print("[perform_autostart] opt-out file present -> editor mode")
        return
    w = op(PERFORM)
    if w is None:
        _write_hb(False, "perform window missing")
        print("[perform_autostart] ERROR: %s missing" % PERFORM)
        return
    try:
        idx, hw, hh = _hisense()          # re-detect HISENSE by NAME (arrangement drift)
        w.par.monitor = idx
        w.par.size = "custom"
        w.par.winw = hw
        w.par.winh = hh
        w.par.dpiscaling = "native"
        w.par.setperform.pulse()          # re-designate as Perform Window
        ui.performMode = True             # enter Perform Mode
    except Exception as e:
        _write_hb(False, "enter error: %s" % e)
        print("[perform_autostart] enter error: %s" % e)
        return
    _write_hb(True, "auto")
    print("[perform_autostart] Perform Mode ACTIVE on HISENSE monitor %s" % w.par.monitor.eval())


_fired = False
_frames = 0
DELAY_FRAMES = 120   # ~2s at 60fps: let the project fully deserialize+cook first


def onStart():
    # Re-arm on every project load (a fresh cold open resets the counter).
    global _fired, _frames
    _fired = False
    _frames = 0
    return


def onFrameStart(frame):
    # Frame-driven delay -- reliable where run(delayFrames=...) did not fire.
    global _fired, _frames
    if _fired:
        return
    _frames += 1
    if _frames >= DELAY_FRAMES:
        _fired = True
        _apply()


def onCreate():
    return


def onExit():
    return
'''


def _run():
    p = op(PROJECT)
    if p is None:
        print("[setup_perform] ERROR: %s not found" % PROJECT)
        return
    if op(SOURCE_TOP) is None:
        print("[setup_perform] ERROR: %s not found -- is the network built?" % SOURCE_TOP)
        return
    mon, hw, hh = _hisense_monitor()
    print("[setup_perform] HISENSE monitor index = %d (%dx%d)" % (mon, hw, hh))

    # --- 1. Window COMP (idempotent) -----------------------------------------
    w = op(PERFORM_PATH) or p.create(windowCOMP, "perform")
    w.nodeX, w.nodeY = 1450, 175
    w.par.winop = SOURCE_TOP
    w.par.justifyoffsetto = "specifymonitor"
    w.par.monitor = mon
    # HARDCODED integer size -- size="fill" resolved to 0x0 on the HISENSE and
    # threw the "Invalid window size" modal at C++ open time. Custom 1920x1080
    # with native DPI is literal pixels, no expression that can evaluate to zero.
    w.par.size = "custom"
    w.par.winw = hw
    w.par.winh = hh
    w.par.winoffsetx = 0
    w.par.winoffsety = 0
    w.par.dpiscaling = "native"
    w.par.borders = False
    w.par.justifyh = "left"
    w.par.justifyv = "top"
    w.par.cursorvisible = "nocursor"
    w.par.interact = False
    w.par.closeescape = True
    w.par.title = "DJ PERFORM"

    # --- 2. NATIVE persisted Perform-on-Start (Layer 1) ----------------------
    # THIS is the fix for F1 doing nothing: performWindowPath was never persisted.
    project.performWindowPath = PERFORM_PATH   # F1 + native perform target
    project.performOnStart = True              # boot straight into Perform Mode
    try:
        w.par.setperform.pulse()               # also set it live this session
    except Exception as e:
        print("[setup_perform] setperform pulse warn: %s" % e)

    # --- 3. Layer-2 re-assert DAT --------------------------------------------
    dat = op(AUTOSTART_PATH) or p.create(executeDAT, "perform_autostart")
    dat.nodeX, dat.nodeY = 1450, 300
    dat.text = _AUTOSTART
    try:
        dat.par.active = True
        dat.par.start = True        # onStart re-arms the counter
        dat.par.framestart = True   # onFrameStart drives the delayed fire
    except Exception as e:
        print("[setup_perform] !! enable Start/Frame Start toggles by hand on %s: %s"
              % (AUTOSTART_PATH, e))

    # --- 4. save IN PLACE (explicit path = NO version increment) -------------
    # project.save() with no arg increments (.3 -> .4) and orphans the launcher's
    # .env target. Passing the explicit current path saves in place instead.
    if AUTOSAVE:
        try:
            import shutil
            cur = project.folder + "/" + project.name
            shutil.copy(cur, cur[:-4] + ".perfbak.toe")
            project.save(cur)   # explicit path -> in place, no increment
            print("[setup_perform] SAVED %s (backup: %s)" % (cur, cur[:-4] + ".perfbak.toe"))
        except Exception as e:
            print("[setup_perform] !! AUTOSAVE FAILED (%s) -- press Cmd+S yourself" % e)

    print("=" * 66)
    print("[setup_perform] DONE (defense-in-depth).")
    print("[setup_perform]   L1 project.performOnStart = %s" % project.performOnStart)
    print("[setup_perform]   L1 project.performWindowPath = %s" % project.performWindowPath)
    print("[setup_perform]   L2 perform_autostart DAT armed (Start=%s)" % dat.par.start.eval())
    print("[setup_perform]   L3 F1 opens it / Esc exits.")
    print("[setup_perform]   Output: %s on monitor %d (HISENSE), fill, no borders." % (SOURCE_TOP, mon))
    print("=" * 66)


_run()
