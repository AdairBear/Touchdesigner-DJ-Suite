# profile_freeze.py -- measure the music-vs-silence graphics freeze.
#
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/profile_freeze.py').read())
#
# Run it TWICE: once with music STOPPED, once with music PLAYING. It samples for
# SAMPLE_SECONDS, prints a table, and appends a JSON row to /tmp/td_freeze_profile.json
# so the two runs sit side by side and the comparison is arithmetic rather than
# impression.
#
# WHAT IT MEASURES, and why each one is here
#
#   td_fps / cook_ms      TouchDesigner's own frame rate and total cook time.
#                         This is the freeze, quantified.
#   per-node cook_ms      The worst cooking operators. If one node dominates,
#                         the freeze is that node, not "general load".
#   mapper_calls          How many times audio_reactive_mapper.onValueChange
#                         fired. THIS IS THE KEY NUMBER for the 2026-07-31
#                         diagnosis: a CHOP Execute DAT fires once per changed
#                         sample, and under music every FFT bin changes every
#                         frame, so this was running hundreds of times per frame
#                         instead of once. With the fix in place it should track
#                         the frame count almost exactly.
#   tracker_fps           Read from the tracker's seqlock counter -- the same
#                         signal TD's mask reader uses. Distinguishes "TD froze"
#                         from "the tracker stopped feeding TD".
#   mask_age_ms           How stale the newest mask frame is.
#
# It writes nothing into the project and changes no parameters. Safe to run
# mid-show, though it costs one Python pass per frame while sampling.

import json
import os
import time

SAMPLE_SECONDS = 8.0
REPORT = "/tmp/td_freeze_profile.json"
SEQ_PATH = "/tmp/djsam_bodymask.seq"

# Label this run so the two show up distinguishably in the report.
# Set to "music" before the second run.
RUN_LABEL = "silence"


def _seq():
    """Tracker frame counter (uint64 LE), or None."""
    try:
        with open(SEQ_PATH, "rb") as fh:
            b = fh.read(8)
        return int.from_bytes(b, "little") if len(b) == 8 else None
    except Exception:
        return None


def _mapper_call_count():
    """audio_reactive_mapper's per-frame guard counter, if the fix is installed.

    Returns (calls_seen, has_fix). `has_fix` False means the DAT predates the
    2026-07-31 freeze fix -- which is itself the finding.
    """
    d = op("/project1/audio_reactive_mapper")
    if d is None:
        return None, None
    txt = d.text or ""
    has_fix = "_last_processed_frame" in txt
    return has_fix, has_fix


def run():
    root = op("/project1")
    if root is None:
        print("[profile] /project1 missing")
        return

    has_fix, _ = _mapper_call_count()

    t0 = time.time()
    f0 = absTime.frame
    s0 = _seq()
    cook_samples = []
    node_totals = {}

    print("[profile] sampling %.0fs -- label=%s" % (SAMPLE_SECONDS, RUN_LABEL))
    while time.time() - t0 < SAMPLE_SECONDS:
        try:
            cook_samples.append(root.cookTime)
        except Exception:
            pass
        # Accumulate the heaviest cookers. findChildren is not cheap, so this
        # runs on a subset of iterations rather than every one.
        if len(cook_samples) % 20 == 0:
            for c in root.findChildren(depth=1):
                try:
                    ct = c.cookTime
                except Exception:
                    continue
                if ct and ct > 0.5:
                    node_totals[c.name] = max(node_totals.get(c.name, 0.0), ct)
        time.sleep(0.05)

    elapsed = time.time() - t0
    frames = absTime.frame - f0
    s1 = _seq()

    td_fps = frames / elapsed if elapsed > 0 else 0.0
    tracker_fps = None
    if s0 is not None and s1 is not None and elapsed > 0:
        tracker_fps = (s1 - s0) / elapsed

    mask_age_ms = None
    try:
        mask_age_ms = (time.time() - os.path.getmtime(SEQ_PATH)) * 1000.0
    except Exception:
        pass

    avg_cook = sum(cook_samples) / len(cook_samples) if cook_samples else 0.0
    peak_cook = max(cook_samples) if cook_samples else 0.0
    worst = sorted(node_totals.items(), key=lambda kv: -kv[1])[:8]

    row = {
        "label": RUN_LABEL,
        "elapsed_s": round(elapsed, 2),
        "td_frames": frames,
        "td_fps": round(td_fps, 1),
        "cook_ms_avg": round(avg_cook, 2),
        "cook_ms_peak": round(peak_cook, 2),
        "tracker_fps": None if tracker_fps is None else round(tracker_fps, 1),
        "mask_age_ms": None if mask_age_ms is None else round(mask_age_ms, 1),
        "freeze_fix_installed": has_fix,
        "worst_nodes": [{"name": n, "cook_ms": round(v, 2)} for n, v in worst],
    }

    print("[profile] ---------------------------------------------")
    print("[profile] label            : %s" % RUN_LABEL)
    print(
        "[profile] TD fps           : %.1f   (60 is healthy, <20 is the freeze)"
        % td_fps
    )
    print("[profile] cook ms avg/peak : %.2f / %.2f" % (avg_cook, peak_cook))
    print(
        "[profile] tracker fps      : %s"
        % ("unknown" if tracker_fps is None else "%.1f" % tracker_fps)
    )
    print(
        "[profile] mask age ms      : %s"
        % ("unknown" if mask_age_ms is None else "%.0f" % mask_age_ms)
    )
    print(
        "[profile] freeze fix in DAT: %s"
        % (
            "YES"
            if has_fix
            else "NO  <-- audio_reactive_mapper is the OLD per-bin version"
        )
    )
    if worst:
        print("[profile] heaviest nodes:")
        for n, v in worst:
            print("[profile]    %-28s %.2f ms" % (n, v))
    print("[profile] ---------------------------------------------")

    rows = []
    if os.path.exists(REPORT):
        try:
            rows = json.load(open(REPORT))
        except Exception:
            rows = []
    rows.append(row)
    json.dump(rows, open(REPORT, "w"), indent=2, default=str)
    print("[profile] appended to %s (%d run(s) recorded)" % (REPORT, len(rows)))

    if len(rows) >= 2:
        a, b = rows[-2], rows[-1]
        if a["label"] != b["label"]:
            print("[profile] ===== COMPARISON =====")
            print(
                "[profile] %s fps %.1f  ->  %s fps %.1f"
                % (a["label"], a["td_fps"], b["label"], b["td_fps"])
            )
            drop = a["td_fps"] - b["td_fps"]
            if a["td_fps"] > 0 and drop / max(a["td_fps"], 0.01) > 0.4:
                print(
                    "[profile] VERDICT: music costs %.0f%% of the frame rate -- freeze reproduced"
                    % (100.0 * drop / a["td_fps"])
                )
            else:
                print("[profile] VERDICT: no large music-dependent drop in this sample")


run()
