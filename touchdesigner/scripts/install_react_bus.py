# install_react_bus.py -- runs INSIDE TouchDesigner. Adds the §8 reactivity bus
# (fx_react + gates + fast energy) to an already-built rig WITHOUT rebuilding it.
#
# Run it one of two ways:
#   bridge:   python3 touchdesigner/scripts/bridge_send.py --timeout 20 \
#                 --file touchdesigner/scripts/install_react_bus.py
#   textport: exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/install_react_bus.py').read())
#
# What it does, in order:
#   1. Fingerprints every parameter UV_RAVE binds (expressions, values, band code).
#   2. extend_dj_graphics.install_react_bus() -- creates ONLY fx_energy_fast,
#      fx_kick_gate, fx_snare_gate, fx_react_cb, fx_react. It never touches
#      fx_audio_bands, the envs, palette, trails or Syphon routing.
#   3. Reloads the aura_compositor DAT from the repo (adds the per-profile flame
#      floor read; default floor unchanged) and the dj_graphics_profiles module
#      (registers GLITCH).
#   4. Re-fingerprints and prints UNCHANGED / CHANGED -- the UV_RAVE receipt.
# It does NOT save the project. Cmd+S is the operator's call.
#
# Revert: exec extend with EXTEND_NO_AUTORUN=True and call uninstall_react_bus(),
# or simply close the project without saving.
import hashlib
import importlib
import json
import sys

_REPO = "/Users/thomasadair/projects/touchdesigner-dj-suite"
_SCRIPTS = _REPO + "/touchdesigner/scripts"
_PARENT = "/project1"

# Every parameter UV_RAVE's look depends on (td_startup_hooks._apply_rave_look +
# the extend_dj_graphics chain). If any of these moves, the install regressed it.
_UV_RAVE_PARS = {
    "outline_level": ["brightness1"],
    "outline_glow": ["size"],
    "fx_kick_bright": ["brightness1"],
    "fx_kick_expand": ["sx", "sy"],
    "fx_trail_hsv": ["valuemult"],
    "fx_kick_env": ["threshold", "attack", "release"],
    "fx_snare_env": ["threshold", "attack", "release"],
    "fx_kick_sel": ["channames"],
    "fx_snare_sel": ["channames"],
    "fx_energy": ["width"],
    "fx_master": ["torange1", "torange2"],
    "audio_in": ["device"],
}
_UV_RAVE_TEXTS = ("fx_audio_bands_cb", "fx_palette_engine_cb")


def _fingerprint():
    """Snapshot every UV_RAVE-bound parameter (mode, expr, value) and callback text."""
    fp = {}
    root = op(_PARENT)  # noqa: F821 - TD global
    for name, pars in _UV_RAVE_PARS.items():
        node = root.op(name)
        for p in pars:
            key = "%s.%s" % (name, p)
            par = getattr(node.par, p, None) if node is not None else None
            if par is None:
                fp[key] = None
                continue
            fp[key] = [str(par.mode), par.expr, str(par.eval())]
    for name in _UV_RAVE_TEXTS:
        node = root.op(name)
        text = node.text if node is not None else ""
        fp[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return fp


def _install():
    before = _fingerprint()

    ns = dict(globals())
    ns["EXTEND_NO_AUTORUN"] = True
    with open(_SCRIPTS + "/extend_dj_graphics.py") as f:
        exec(f.read(), ns)
    bus = ns["install_react_bus"]()
    if not bus["ok"]:
        print("[install_react_bus] FAILED -- bus incomplete, compositor/profiles NOT reloaded:",
              json.dumps(bus))
        return bus

    comp = op(_PARENT + "/aura_compositor")  # noqa: F821
    if comp is not None:
        with open(_SCRIPTS + "/aura_compositor.py") as f:
            comp.text = f.read()
    if _SCRIPTS not in sys.path:
        sys.path.insert(0, _SCRIPTS)
    import dj_graphics_profiles as gp
    gp = importlib.reload(gp)

    after = _fingerprint()
    changed = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    result = {
        "bus": bus,
        "compositor_reloaded": comp is not None,
        "glitch_registered": "GLITCH" in gp.PROFILES,
        "uv_rave_pars_checked": len(before),
        "uv_rave_changed": changed,
    }
    print("[install_react_bus] fx_react channels:", " ".join(bus["channels"]))
    print("[install_react_bus] GLITCH registered:", result["glitch_registered"])
    print("[install_react_bus] UV_RAVE fingerprint (%d pars): %s"
          % (len(before), "UNCHANGED" if not changed else "CHANGED " + json.dumps(changed)))
    return result


_install()
