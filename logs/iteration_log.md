# Performance Iteration Log

Track systematic changes and their impact on the Generative Stream Graphics system.

## Guidelines

- **ONE variable at a time** - Change only one parameter per iteration
- **Quantify everything** - Record FPS, latency, CPU usage, accuracy
- **Test consistently** - Use same test tracks and movement patterns
- **Document subjectively** - Note feel, vibe, visual impact
- **Keep or revert** - Don't accumulate uncertain changes

---

## Iteration Template

Use VS Code snippet: Type `itlog` in this file to generate new entry

---

## Example Iteration

## Iteration 0 - 2025-12-28

### Hypothesis
Baseline measurement - no changes, establish performance targets

### Changed Variable
**Changed:** None (baseline)
**From:** N/A
**To:** N/A

### Expected Outcome
Establish baseline metrics for all components

### Test Results
- **FPS:** 32 fps (movement tracking)
- **Latency:** 48 ms (audio)
- **Tracking Accuracy:** 94%
- **Subjective Quality:** Smooth tracking, responsive to movement

### Audio Test Tracks
- [x] Amen roller - Good break detection
- [x] Reese bassline - Bass tracking responsive
- [x] Ragga jungle - Vocal samples not interfering
- [ ] Minimal tech-step
- [ ] Double drop

### Movement Test Scenarios
- [x] Standing still - No jitter
- [x] Arm raise on drop - Smooth response
- [x] Dancing to beat - Tracks well
- [ ] Rapid hand movements
- [ ] Big gesture on drop

### Decision
**Status:** Keep

**Reasoning:** Baseline performance meets all targets. Ready for optimization iterations.

### Notes
- Camera positioned 1.5m from DJ booth
- Lighting is key - need consistent overhead light
- MediaPipe model_complexity=1 provides good balance

---
