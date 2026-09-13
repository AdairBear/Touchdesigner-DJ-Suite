// ascii_lightning.glsl — GLSL TOP Pixel Shader
// ==========================================
// ASCII + LIGHTNING look — a NEW, standalone, full-frame audio-reactive LAYER.
// Luminance is quantized to a character-cell grid (procedural 5x5 glyph ramp, no
// atlas asset needed) and struck through with procedural branching lightning bolts
// that fire on onsets. Tuned for a 150-180 BPM breakbeat/jungle set.
//
// This is NOT part of the flame<->lightning body-outline toggle. It is an
// independent look published to its OWN Syphon/Spout output and its OWN OBS scene
// (see docs/setup/DROP_IN.md). It does NOT require the body-tracking pipeline.
//
// MODES:
//   A) GENERATIVE (default): fully self-contained. Wire NO inputs. The ASCII
//      source is an internal lightning/plasma field. Works standalone.
//   B) CAMERA/TOP ASCII-IFY (optional): wire any TOP (camera, movie, feedback)
//      into sTD2DInputs[0]; its luminance becomes the ASCII source, still struck
//      by the bolts. Auto-detected: if input 0 is black/unwired -> generative.
//
// INPUTS (GLSL TOP):
//   sTD2DInputs[0] = OPTIONAL source TOP to ASCII-ify (camera/movie/feedback).
//                    Leave unconnected for pure generative mode.
//
// UNIFORMS — SAME contract/names as fire_aura.glsl & lightning.glsl, so the
// existing aura_compositor.py uniform push and _bind_uniforms_v4.py slot layout
// wire it up with zero new plumbing (slot0=uTime, slots1..9 = value1..value9):
//   uniform float uFlameIntensity;  // value1 — bass_rms   -> glyph brightness + bolt core
//   uniform float uTurbulence;      // value2 — mid        -> bolt filament chaos
//   uniform float uDistortion;      // value3 — distortion -> cell jitter / arc twitch
//   uniform float uSparkle;         // value4 — highs      -> random bright glyph sparks
//   uniform float uMotionEnergy;    // value5 — motion     -> subtle scroll speed
//   uniform float uBassEnergy;      // value6 — raw bass   -> glyph DENSITY (grid size pulse)
//   uniform float uMidEnergy;       // value7 — raw mid    -> color body
//   uniform float uHighEnergy;      // value8 — raw high   -> COLOR SHIFT (blue->cyan/white)
//   uniform float uBurstDecay;      // value9 — onset_strength -> TRIGGER lightning strikes
//
// SETUP IN TOUCHDESIGNER: see docs/setup/DROP_IN.md (turnkey steps).
// Tuned for 16:9 output (e.g. 1280x720); the cell grid is aspect-corrected for 16:9.
// ==========================================

// TD provides this automatically (slot 0, expression absTime.seconds)
uniform float uTime;

// Custom uniforms (identical contract to fire_aura.glsl / lightning.glsl)
uniform float uFlameIntensity;
uniform float uTurbulence;
uniform float uDistortion;
uniform float uSparkle;
uniform float uMotionEnergy;
uniform float uBassEnergy;
uniform float uMidEnergy;
uniform float uHighEnergy;
uniform float uBurstDecay;

out vec4 fragColor;

// ==========================================
// SIMPLEX NOISE (3D) — self-contained, identical to lightning.glsl/fire_aura.glsl
// ==========================================
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(
        i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

// Ridged FBM -> sharp branching filaments (same technique as lightning.glsl)
float ridged(float n) { n = 1.0 - abs(n); return n * n; }
float ridgedFBM(vec3 p, float persistence, float lacunarity) {
    float total = 0.0, amplitude = 1.0, frequency = 1.0, maxVal = 0.0;
    for (int i = 0; i < 6; i++) {
        total += ridged(snoise(p * frequency)) * amplitude;
        maxVal += amplitude;
        amplitude *= persistence;
        frequency *= lacunarity;
    }
    return total / maxVal;
}
float hash11(float x) { return fract(sin(x * 127.1) * 43758.5453123); }
float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

// ==========================================
// PROCEDURAL ASCII GLYPH RAMP (no atlas asset)
// 8 glyphs, 5x5, bit-packed as bit = x + 5*y (y up). Ordered dark->bright by
// pixel coverage. Ints generated + verified offline (space,.,:,+,@,#,*,block).
// ==========================================
const int GLYPHS[8] = int[8](0, 256, 262400, 4357252, 15267630, 11512810, 22511061, 33554431);

// Sample glyph n at cell-local coords p in [0,1]; returns 0/1.
float glyphBit(int n, vec2 p) {
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return 0.0;
    ivec2 g = ivec2(floor(p * 5.0));
    if (g.x < 0 || g.x > 4 || g.y < 0 || g.y > 4) return 0.0;
    int bit = g.x + 5 * g.y;
    return float((n >> bit) & 1);
}

// Map a luminance level [0,1] to a glyph from the ramp.
float rampGlyph(float level, vec2 cellP) {
    int idx = int(clamp(floor(level * 8.0), 0.0, 7.0));
    return glyphBit(GLYPHS[idx], cellP);
}

// ==========================================
// ELECTRIC COLOR RAMP (matches lightning.glsl identity), high-energy color shift.
// ==========================================
vec3 electricColor(float t, float highShift) {
    vec3 c0 = vec3(0.02, 0.03, 0.12);  // near-black indigo
    vec3 c1 = vec3(0.10, 0.25, 0.85);  // electric blue
    vec3 c2 = vec3(0.35, 0.70, 1.00);  // sky blue
    vec3 c3 = vec3(0.75, 0.92, 1.00);  // pale cyan
    vec3 c4 = vec3(1.00, 1.00, 1.00);  // white-hot
    vec3 color;
    if (t < 0.25)      color = mix(c0, c1, t / 0.25);
    else if (t < 0.55) color = mix(c1, c2, (t - 0.25) / 0.30);
    else if (t < 0.80) color = mix(c2, c3, (t - 0.55) / 0.25);
    else               color = mix(c3, c4, (t - 0.80) / 0.20);
    // Treble shifts the hot end whiter/cyan (spectral color shift).
    color = mix(color, c4, highShift * 0.5 * smoothstep(0.4, 1.0, t));
    return color;
}

// ==========================================
// MAIN
// ==========================================
void main()
{
    vec2 uv = vUV.st;

    // ---- Uniforms (same mapping as the existing shaders) ----
    float bright  = max(uFlameIntensity, 0.10);  // value1 bass -> glyph brightness / bolt core
    float turb    = max(uTurbulence, 0.10);      // value2 mid  -> filament chaos
    float jitter  = uDistortion;                 // value3      -> cell / arc jitter
    float sparkle = uSparkle;                    // value4 high -> glyph sparks
    float motion  = uMotionEnergy;               // value5      -> scroll speed
    float bassRaw = uBassEnergy;                 // value6      -> grid density pulse
    float highRaw = uHighEnergy;                 // value8      -> color shift
    float burst   = uBurstDecay;                 // value9 onset-> strike trigger
    float t       = uTime;

    // ---- Onset-triggered strike gate (same idea as lightning.glsl) ----
    float strikeSlot = floor(t * 16.0);                   // ~16 slots/sec (breakbeat-punchy)
    float strikeRng  = hash11(strikeSlot);
    float strikeProb = 0.05 + burst * 0.9;                // onset raises strike probability
    float strike     = step(1.0 - strikeProb, strikeRng); // 0/1 this slot
    float boltX      = hash11(strikeSlot * 1.7 + 3.0);    // bolt column shifts per strike

    // ---- Generative lightning field (self-contained ASCII source) ----
    float scroll = t * (1.5 + motion * 3.0);
    // vertical branching bolts, advected downward; bass fattens the cores
    vec3 bp = vec3(uv.x * (7.0 + bassRaw * 4.0),
                   uv.y * 16.0 - scroll,
                   t * 0.7);
    float bolt = ridgedFBM(bp, 0.5 + turb * 0.2, 2.3);
    // concentrate near the per-strike bolt column so strikes read as discrete forks
    float colFocus = 1.0 - smoothstep(0.03, 0.35, abs(uv.x - boltX));
    float boltCore = smoothstep(0.60 - highRaw * 0.1, 0.92, bolt) * (0.35 + colFocus * 0.9);
    float boltLum  = boltCore * mix(0.15, 1.0, strike);   // dim idle, bright on strike
    boltLum += boltCore * burst * 0.6;                     // onset flash
    // soft moving plasma so the grid is never fully empty between strikes
    float plasma = 0.12 + 0.10 * snoise(vec3(uv * 3.0, t * 0.5));
    float genLum = clamp(plasma + boltLum * bright, 0.0, 1.0);

    // ---- Optional camera/TOP source (mode B): ASCII-ify live input ----
    // Auto-detect: black/unwired input 0 -> stay generative.
    vec3 camCol = texture(sTD2DInputs[0], uv).rgb;
    float camPresent = step(0.01, luma(texture(sTD2DInputs[0], vec2(0.5)).rgb)
                                 + luma(texture(sTD2DInputs[0], vec2(0.25)).rgb)
                                 + luma(texture(sTD2DInputs[0], vec2(0.75)).rgb));
    // when a camera is present, its luma drives the glyphs; bolts still strike over it
    float srcLum = mix(genLum, clamp(luma(camCol) + boltLum * bright, 0.0, 1.0), camPresent);

    // ---- ASCII grid (aspect-corrected for 16:9); bass pulses the density ----
    float cols = floor(58.0 + bassRaw * 34.0);            // more/denser glyphs on bass
    vec2  grid = vec2(cols, floor(cols * 9.0 / 16.0));    // square cells at 16:9
    // per-cell jitter on distortion so the wall of text twitches like arcs
    vec2  juv  = uv + vec2(snoise(vec3(uv.yx * 5.0, t * 3.0))) * (jitter * 0.01);
    vec2  cell = fract(juv * grid);                       // [0,1] within a cell
    vec2  cellCenter = (floor(juv * grid) + 0.5) / grid;  // sample source at cell center

    // one luminance per cell -> one glyph per cell
    vec3  cCol   = texture(sTD2DInputs[0], cellCenter).rgb;
    float cGen   = clamp((0.12 + 0.10 * snoise(vec3(cellCenter * 3.0, t * 0.5)))
                         + smoothstep(0.60 - highRaw * 0.1, 0.92,
                             ridgedFBM(vec3(cellCenter.x * (7.0 + bassRaw * 4.0),
                                            cellCenter.y * 16.0 - scroll, t * 0.7),
                                       0.5 + turb * 0.2, 2.3))
                           * (0.35 + (1.0 - smoothstep(0.03, 0.35, abs(cellCenter.x - boltX))) * 0.9)
                           * mix(0.15, 1.0, strike) * bright,
                         0.0, 1.0);
    float cellLum = mix(cGen, clamp(luma(cCol) + (cGen - 0.12), 0.0, 1.0), camPresent);

    // ---- Glyph coverage for this fragment ----
    float g = rampGlyph(cellLum, cell);

    // ---- Color the glyph (electric ramp, treble color shift) ----
    float tone = pow(clamp(cellLum, 0.0, 1.0), 0.8);
    vec3 color = electricColor(tone, highRaw) * g * (0.4 + bright);

    // subtle dark-navy background scanline so empty cells still read as "screen"
    vec3 bg = vec3(0.015, 0.02, 0.05) * (0.6 + 0.4 * step(0.5, fract(uv.y * grid.y)));
    color = max(color, bg);

    // ---- Highs -> random bright glyph sparks ----
    if (sparkle > 0.01) {
        float sp = hash11(dot(floor(juv * grid), vec2(13.0, 71.0)) + strikeSlot);
        float spMask = step(0.94 - sparkle * 0.2, sp) * g;
        color += vec3(0.8, 0.95, 1.0) * spMask * (0.5 + sparkle);
    }

    // ---- Onset -> whole-frame white strike flash on the glyphs ----
    if (burst > 0.05) {
        color = mix(color, vec3(0.9, 0.96, 1.0), burst * 0.5 * g * strike);
    }

    // Standalone full-frame scene -> opaque. (For a transparent OVERLAY variant,
    // replace the line below with premultiplied alpha:
    //   float a = clamp(luma(color), 0.0, 1.0);
    //   fragColor = TDOutputSwizzle(vec4(color * a, a));   )
    fragColor = TDOutputSwizzle(vec4(color, 1.0));
}
