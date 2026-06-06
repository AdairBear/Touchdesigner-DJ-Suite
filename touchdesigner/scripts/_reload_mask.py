# _reload_mask.py — one-shot forced reload of file-backed DATs.
# Run from TD Textport:  exec(open(<this path>).read())
# Forces segmentation_mask_reader.py and aura_compositor.py to be re-read
# from disk into their respective DATs, then force-cooks body_mask_top.

def _run():
    targets = [
        '/project1/segmentation_mask_reader',
        '/project1/aura_compositor',
    ]
    for path in targets:
        d = op(path)
        if d is None:
            print('[reload] MISSING', path)
            continue
        src = None
        try:
            if hasattr(d.par, 'file'):
                src = d.par.file.eval()
        except Exception as e:
            print('[reload] file par error', path, e)
        if not src:
            base = ('/Users/thomasadair/projects/touchdesigner-dj-suite'
                    '/touchdesigner/scripts/')
            src = base + path.split('/')[-1] + '.py'
        try:
            with open(src, 'r') as fh:
                d.text = fh.read()
            print('[reload] OK', path, '<-', src, 'len=', len(d.text))
        except Exception as e:
            print('[reload] FAIL', path, '<-', src, e)

    top = op('/project1/body_mask_top')
    if top is not None:
        try:
            top.cook(force=True)
            print('[reload] body_mask_top cooked res=', top.width, 'x', top.height,
                  'errs=', (top.errors() or '').strip()[:120])
        except Exception as e:
            print('[reload] body_mask_top force-cook failed', e)
    else:
        print('[reload] body_mask_top MISSING')

_run()
