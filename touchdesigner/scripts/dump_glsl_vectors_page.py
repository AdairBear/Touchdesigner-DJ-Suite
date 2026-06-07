# dump_glsl_vectors_page.py — GLSL TOP uniform-binding probe
# =====================================================================
# WHY THIS EXISTS:
#   Only 3 of 10 vector uniforms (slots 1, 3, 8) bind on fire_aura_glsl /
#   lightning_glsl; the other 7 show "Uniform '<name>' is not assigned.
#   Please assign it on the Vectors page." The build helper assumes the
#   uniform-name parameters form a contiguous `uniformname1..10` sequence,
#   but the 1/3/8 binding pattern says that assumption is wrong on this
#   TD build (2022.35320). This probe dumps the GROUND TRUTH so the exact
#   fix can be written instead of guessed.
#
# HOW TO RUN (TouchDesigner Textport):
#   1. Open Textport (Alt+T).
#   2. Paste this entire file and press Enter, OR:
#        exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/'
#                  'touchdesigner/scripts/dump_glsl_vectors_page.py').read())
#   3. Copy ALL the [probe] output and send it back.
#
# READ-ONLY: this script does NOT modify any parameter. Safe to run live.
# =====================================================================


def _p(msg):
    print("[probe] " + str(msg))


def _dump_one(path):
    g = op(path)
    _p("================================================================")
    _p("TARGET: " + path)
    if g is None:
        _p("  !! op not found")
        return
    _p("  type=%s  family=%s" % (g.type, g.family))

    # --- 1. The shader's DECLARED uniforms (from the pixel-shader source) ----
    # Reconcile what the shader expects vs what the Vectors page actually names.
    declared = []
    try:
        src_dat = g.par.pixeldat.eval()
        if src_dat is not None:
            for ln in src_dat.text.splitlines():
                s = ln.strip()
                if s.startswith("uniform "):
                    declared.append(s)
        _p("  --- shader DECLARED uniforms (%d) ---" % len(declared))
        for d in declared:
            _p("    " + d)
    except Exception as e:
        _p("  shader-source read err: " + str(e))

    # --- 2. EVERY parameter, grouped by its parameter PAGE -------------------
    # This reveals the real page name ("Vectors"?) and the real par names
    # (uniformname1..? value1..? OR something else entirely).
    try:
        pages = {}
        for par in g.pars():
            pg = par.page.name if par.page is not None else "<no page>"
            pages.setdefault(pg, []).append(par)
        _p("  --- parameter PAGES on this TOP ---")
        for pg in pages:
            _p("    page '%s'  (%d pars)" % (pg, len(pages[pg])))
        # Dump the full contents of any page that looks uniform-related.
        for pg, plist in pages.items():
            low = pg.lower()
            if not any(
                k in low
                for k in ("vector", "uniform", "value", "array", "glsl", "const")
            ):
                continue
            _p("  --- FULL DUMP of page '%s' ---" % pg)
            for par in plist:
                try:
                    _p(
                        "    name=%-16s label=%-20s style=%-8s val=%r"
                        % (par.name, par.label, par.style, par.eval())
                    )
                except Exception as e:
                    _p("    name=%s  (read err: %s)" % (par.name, e))
    except Exception as e:
        _p("  page-walk err: " + str(e))

    # --- 3. Count parameters (slots are FIXED on this build, not a sequence) --
    # The probe's first run proved glsl.seq raises AttributeError ('sequences')
    # here, so the Vectors page is NOT sequence-backed — slots are a fixed,
    # contiguous set of pars. Look for any numeric count par that gates how
    # many vector-uniform slots are exposed.
    _p("  --- count pars (if any gate the slot total) ---")
    found_count = False
    for cnt in (
        "numuniforms",
        "numconstants",
        "uniforms",
        "numvecuniforms",
        "numuniform",
        "numvec",
    ):
        par = getattr(g.par, cnt, None)
        if par is not None:
            found_count = True
            try:
                _p("    '%s' = %r" % (cnt, par.eval()))
            except Exception as e:
                _p("    '%s' present (read err: %s)" % (cnt, e))
    if not found_count:
        _p("    none found — slot total is fixed by the GLSL TOP itself.")

    # --- 4. Slot-by-slot truth: name + per-COMPONENT value (value{i}x..w) -----
    # value{i} is a parGroup (XYZW) — accessing g.par.value{i} raises tdError,
    # which is what crashed the first probe. Read the per-component pars
    # value{i}x/y/z/w directly. Probe 1..16 to discover the true max slot count
    # and reveal EXACTLY which uniformname slots are empty (the 2/4/5/6/7/9
    # mystery). getattr(..., None) safely returns None for absent components.
    # NOTE: par names are 0-INDEXED on this build — uniname{i} / value{i}x..w
    # (probe v2 proved the Vectors page uses 'uniname0', not 'uniformname1').
    _p("  --- slot 0..15: uniname{i} + value{i}[x,y,z,w] ---")
    max_slot = -1
    for i in range(0, 16):
        nm = getattr(g.par, "uniname" + str(i), None)
        comps = [
            getattr(g.par, "value%d%s" % (i, c), None) for c in ("x", "y", "z", "w")
        ]
        if nm is None and all(c is None for c in comps):
            continue  # slot doesn't exist on this build
        max_slot = i
        try:
            nm_state = "'%s'" % nm.eval() if nm is not None else "<no name par>"
        except Exception as e:
            nm_state = "<name read err %s>" % e
        vals = []
        for c in comps:
            if c is None:
                vals.append("--")
            else:
                try:
                    vals.append("%g" % c.eval())
                except Exception as e:
                    vals.append("err:%s" % e)
        _p("    slot %2d: uniname=%-18s value=[%s]" % (i, nm_state, ", ".join(vals)))
    _p("    >>> highest existing slot on %s = %d" % (g.name, max_slot))


_p("==== GLSL VECTORS-PAGE PROBE (read-only) ====")
for _path in ("/project1/fire_aura_glsl", "/project1/lightning_glsl"):
    _dump_one(_path)
_p("==== END PROBE — copy everything above and send back ====")
