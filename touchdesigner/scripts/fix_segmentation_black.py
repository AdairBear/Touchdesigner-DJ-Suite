# fix_segmentation_black.py -- kill the body_mask_top 19s freeze WITHOUT the
# checkerboard. Replaces the segmentation reader callback with a cheap black
# emitter and un-bypasses the node, so downstream gets VALID input (black =
# "no body"), not TD's missing-input checker fallback. Idempotent.
#
# Run in TD Textport:
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/fix_segmentation_black.py').read())
#
# WHY: body_mask_top's segmentation reader cooks ~19s/frame (pre-existing bug),
# freezing the whole pipeline. Bypassing it made the Script TOP output invalid ->
# magenta/black checker on the Syphon feed. Emitting black keeps it cheap AND valid.
import numpy as np

bmt = op('/project1/body_mask_top')
cbname = bmt.par.callbacks.eval()
cb = op(cbname) if cbname else op('/project1/body_mask_top_callbacks')

_BLACK = '''import numpy as np
# Emit a black 640x480 RGBA frame (~0.004ms) instead of the 19s segmentation read.
def onCook(scriptOp):
    scriptOp.copyNumpyArray(np.zeros((480, 640, 4), dtype=np.float32))
def cook(scriptOp):
    scriptOp.copyNumpyArray(np.zeros((480, 640, 4), dtype=np.float32))
'''
cb.text = _BLACK
bmt.bypass = False          # must cook (fast now) so it outputs valid black, NOT bypass
bmt.cook(force=True)

a = bmt.numpyArray()[..., :3]
print('[fix_seg_black] body_mask_top cook=%.3fms bypass=%s out_max=%s (0,0,0 = clean black)'
      % (bmt.cookTime, bmt.bypass, [round(float(x), 3) for x in a.reshape(-1, 3).max(0)]))
print('[fix_seg_black] NOTE: this disables the body-outline visual until the reader is rewritten.')
