import numpy as np
def onCook(scriptOp):
    scriptOp.copyNumpyArray(np.zeros((480,640,4),dtype=np.float32))
def cook(scriptOp):
    scriptOp.copyNumpyArray(np.zeros((480,640,4),dtype=np.float32))
