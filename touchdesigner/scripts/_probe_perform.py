# _probe_perform.py -- READ-ONLY probe of the running TD for Perform Mode setup.
# Writes JSON to /tmp/td_perform_probe.json. Creates/destroys nothing.
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_probe_perform.py').read())
import json

out = {}
try:
    out["td_version"] = app.version
    out["td_build"] = app.build
except Exception as e:
    out["td_version_err"] = str(e)

# Monitors: which index/name is the HISENSE display, and its resolution.
mons = []
try:
    for m in monitors:
        mons.append({
            "index": m.index,
            "description": getattr(m, "description", None),
            "width": m.width, "height": m.height,
            "left": m.left, "top": m.top,
            "isPrimary": getattr(m, "isPrimary", None),
            "scaling": getattr(m, "scaling", None),
        })
except Exception as e:
    out["monitors_err"] = str(e)
out["monitors"] = mons

# Does the perform target exist, and what feeds OBS?
for path in ("/project1/final_composite", "/project1/syphonOut1", "/project1/perform"):
    o = op(path)
    out[path] = None if o is None else {"type": o.type, "OPtype": o.OPType,
                                        "w": getattr(o, "width", None),
                                        "h": getattr(o, "height", None)}

# Current perform-window designation + relevant ui API surface.
try:
    pw = project.performWindow if hasattr(project, "performWindow") else None
    out["project.performWindow"] = None if pw is None else pw.path
except Exception as e:
    out["performWindow_err"] = str(e)

out["ui_has_performMode"] = hasattr(ui, "performMode")
try:
    out["ui_performMode_value"] = ui.performMode
except Exception as e:
    out["ui_performMode_err"] = str(e)

# Any existing Window COMPs anywhere under /project1.
try:
    wins = op('/project1').findChildren(type=windowCOMP, depth=99)
    out["existing_windowCOMPs"] = [w.path for w in wins]
except Exception as e:
    out["windowCOMP_scan_err"] = str(e)

with open("/tmp/td_perform_probe.json", "w") as f:
    json.dump(out, f, indent=2)
print("[_probe_perform] wrote /tmp/td_perform_probe.json")
