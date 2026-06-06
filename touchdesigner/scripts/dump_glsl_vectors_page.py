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
            if not any(k in low for k in ("vector", "uniform", "value", "array")):
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

    # --- 3. SEQUENCE groups + per-block parameters ---------------------------
    # The Vectors page is sequence-backed. Print each sequence's block count
    # and the actual par names inside block 0 so we know the true base names.
    try:
        _p("  --- sequence groups ---")
        for sg in g.seq:
            try:
                _p("    seq '%s'  numBlocks=%s" % (sg.name, sg.numBlocks))
                if len(sg.blocks) > 0:
                    blk = sg.blocks[0]
                    bpars = [bp.name for bp in blk.pars]
                    _p("      block[0] par names: " + str(bpars))
            except Exception as e:
                _p("    seq dump err: " + str(e))
    except Exception as e:
        _p("  seq-walk err: " + str(e))

    # --- 4. Direct probe of the names the build script TARGETS ---------------
    # For each uniformname1..12 / value1..12: does the par exist, and what is
    # its current value? This shows EXACTLY which slots are present + named.
    _p("  --- uniformname1..12 / value1..12 presence + current value ---")
    for i in range(1, 13):
        nm = getattr(g.par, "uniformname" + str(i), None)
        vl = getattr(g.par, "value" + str(i), None)
        nm_state = ("'%s'" % nm.eval()) if nm is not None else "<PAR MISSING>"
        if vl is not None:
            try:
                vl_state = repr(vl.eval())
            except Exception:
                # multi-component value par — read the tuplet
                try:
                    vl_state = repr([c.eval() for c in g.par[("value%d" % i)]])
                except Exception as e:
                    vl_state = "<read err %s>" % e
        else:
            vl_state = "<PAR MISSING>"
        _p("    slot %2d: uniformname=%s  value=%s" % (i, nm_state, vl_state))


_p("==== GLSL VECTORS-PAGE PROBE (read-only) ====")
for _path in ("/project1/fire_aura_glsl", "/project1/lightning_glsl"):
    _dump_one(_path)
_p("==== END PROBE — copy everything above and send back ====")
