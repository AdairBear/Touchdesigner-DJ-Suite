// lightning.glsl — GLSL TOP Pixel Shader
// ==========================================
// Electric LIGHTNING look for DJ Sam body OUTLINE (net-new, Phase 1D).
// Sharp blue/white filaments that ride the silhouette contour and flicker on
// audio onsets. Companion to fire_aura.glsl — same input/uniform contract, so
// switching looks is just choosing which GLSL TOP is cooked (see
// docs/setup/visual_mode_toggle.md). fire_aura.glsl is unchanged.
//
// DESIGN INTENT (vs fire_aura):
//   - fire EXPANDS/blooms outward from the body -> aura.
//   - lightning is EDGE-CONFINED -> sharp filaments hug the contour line.
//   This matches the edge-confined outline fix (the Python side now emits a thin
//   contour via MORPH_GRADIENT; see baseline_outline_audit_2026-06-05.md).
//
// INPUTS (GLSL TOP) — identical to fire_aura.glsl:
//   sTD2DInputs[0] = Body edge/contour mask (from movement_tracker outline,
//                    optionally through the existing Edge TOP — works with both)
//   sTD2DInputs[1] = Motion energy (optional spatial modulation)
//   sTD2DInputs[2] = Audio energy  (optional spatial modulation)
//
// UNIFORMS (pushed by aura_compositor.py — SAME names as fire_aura.glsl, so no
// re-wiring is needed to swap shaders):
//   uniform float uFlameIntensity;  // value1 — bass-driven core brightness
//   uniform float uTurbulence;      // value2 — mid-driven filament chaos
//   uniform float uDistortion;      // value3 — jitter / arc displacement
//   uniform float uSparkle;         // value4 — high-driven micro-sparks
//   uniform float uMotionEnergy;    // value5 — body motion energy
//   uniform float uBassEnergy;      // value6 — raw bass energy
//   uniform float uMidEnergy;       // value7 — raw mid energy
//   uniform float uHighEnergy;      // value8 — raw high energy
//   uniform float uBurstDecay;      // value9 — ONSET burst decay (/audio/onset_strength)
//                                   //          -> drives the lightning flicker/strike
//
// SETUP IN TOUCHDESIGNER:
//   1. Create GLSL TOP  ->  name: "lightning_glsl"
//   2. Pixel Shader: point a DAT to this file (or paste)
//   3. Inputs 0/1/2 same as fire_aura_glsl (you can wire the same sources)
//   4. Custom Uniform page: value1..value9 (floats) — copy from fire_aura_glsl
//   5. Resolution: match camera (1280x720), Output RGBA 16-bit float
//   6. Feed lightning_glsl and fire_aura_glsl into a Switch TOP; drive the
//      Switch index from /visual/mode (0 = flame, 1 = lightning).
// ==========================================

// TD provides these automatically
uniform float uTime;          // absTime.seconds

// Custom uniforms (same contract as fire_aura.glsl)
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
// SIMPLEX NOISE (3D) — self-contained (matches fire_aura.glsl)
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

// ==========================================
// RIDGED FBM — sharp filaments for the lightning "branching" feel.
// ridged() turns smooth noise into knife-edge ridges (1 - |n|), which read as
// the bright cores of electric arcs. High frequency + extra octaves = fine,
// forking filaments rather than soft fire billows.
// ==========================================
float ridged(float n) {
    n = 1.0 - abs(n);   // fold valleys up into sharp ridge lines
    return n * n;       // square -> tighter, brighter cores
}

float ridgedFBM(vec3 p, float persistence, float lacunarity) {
    float total = 0.0;
    float amplitude = 1.0;
    float frequency = 1.0;
    float maxVal = 0.0;
    // 6 octaves: more high-frequency content than the fire shader's 4, for the
    // forked/branching look. lacunarity > 2 widens the frequency gap per octave.
    for (int i = 0; i < 6; i++) {
        total += ridged(snoise(p * frequency)) * amplitude;
        maxVal += amplitude;
        amplitude *= persistence;
        frequency *= lacunarity;
    }
    return total / maxVal;
}

// Cheap hash for the discrete strike timer.
float hash11(float x) { return fract(sin(x * 127.1) * 43758.5453123); }

// ==========================================
// ELECTRIC BLUE/WHITE COLOR RAMP
// t in [0,1]: deep indigo -> electric blue -> cyan -> white-hot core.
// highBoost shifts the hot end whiter on treble.
// ==========================================
vec3 lightningColor(float t, float highBoost) {
    vec3 c0 = vec3(0.02, 0.03, 0.12);  // near-black indigo
    vec3 c1 = vec3(0.10, 0.25, 0.85);  // electric blue
    vec3 c2 = vec3(0.35, 0.70, 1.00);  // bright sky-blue
    vec3 c3 = vec3(0.75, 0.92, 1.00);  // pale cyan
    vec3 c4 = vec3(1.00, 1.00, 1.00);  // white-hot core

    vec3 color;
    if (t < 0.25)      color = mix(c0, c1, t / 0.25);
    else if (t < 0.55) color = mix(c1, c2, (t - 0.25) / 0.30);
    else if (t < 0.80) color = mix(c2, c3, (t - 0.55) / 0.25);
    else               color = mix(c3, c4, (t - 0.80) / 0.20);

    // Treble pushes the core whiter/hotter.
    color = mix(color, c4, highBoost * 0.4 * smoothstep(0.5, 1.0, t));
    return color;
}

// ==========================================
// MAIN
// ==========================================
void main()
{
    vec2 uv = vUV.st;

    // ---- Read uniforms (same mapping as fire shader) ----
    float coreInt = max(uFlameIntensity, 0.12);   // bass -> brightness
    float turb    = max(uTurbulence, 0.1);         // mid  -> filament chaos
    float jitter  = uDistortion;                   // arc displacement
    float sparkle = uSparkle;                       // highs -> micro-sparks
    float motion  = max(uMotionEnergy, texture(sTD2DInputs[1], uv).r);
    float high    = uHighEnergy;
    float burst   = uBurstDecay;                    // ONSET -> strike/flicker
    float t       = uTime;

    // ---- Onset-triggered flicker / strike gate ----
    // Lightning is not continuous: it strikes. A fast discrete timer produces a
    // stochastic on/off strobe; onset energy (burst) both raises the strike
    // probability and the brightness, so strikes land on the beat. A small
    // baseline keeps faint arcs alive between hits.
    float strikeSlot = floor(t * 18.0);                       // ~18 slots/sec
    float strikeRng  = hash11(strikeSlot);
    float strikeProb = 0.06 + burst * 0.9;                    // onset drives it
    float strike     = step(1.0 - strikeProb, strikeRng);     // 0/1 this slot
    // Sub-slot flicker so a struck slot shimmers rather than being a flat block.
    float subFlicker = 0.6 + 0.4 * snoise(vec3(uv * 4.0, t * 30.0));
    float flicker    = mix(0.25, 1.0, strike) * subFlicker;   // 0.25 idle .. 1 strike

    // ---- Arc jitter (displace UV so filaments twitch like real arcs) ----
    float warp = snoise(vec3(uv * 6.0, t * 4.0)) * (0.01 + jitter * 0.03);
    vec2 luv = uv + vec2(warp, warp * 0.5);

    // ---- Contour mask (edge-confined; works for raw outline or Edge TOP) ----
    float edge = texture(sTD2DInputs[0], luv).r;

    // Fallback: no body mask -> faint ambient bolts so the look is visible when
    // testing standalone (parallels fire_aura's ambient fallback, but sparse).
    float maskPresence = max(texture(sTD2DInputs[0], vec2(0.5, 0.5)).r,
                             texture(sTD2DInputs[0], vec2(0.25, 0.25)).r);
    if (maskPresence < 0.01) {
        float bolt = ridgedFBM(vec3(uv * vec2(2.0, 8.0), t * 0.6), 0.55, 2.3);
        edge = smoothstep(0.78, 0.92, bolt) * 0.6;
    }

    // ---- Filament field along the contour ----
    // Stretch noise vertically so ridges read as descending bolts; advect in
    // time so they crawl along the line.
    vec3 np = vec3(luv.x * 9.0, luv.y * 16.0 - t * 2.5, t * 0.9);
    float filament = ridgedFBM(np, 0.5 + turb * 0.2, 2.3);
    // Tighten to bright cores; treble + motion sharpen the threshold.
    float core = smoothstep(0.55 - high * 0.1, 0.92, filament);

    // ---- Edge-confined intensity ----
    // Confine sharply to the contour band: a thin smoothstep, NOT the wide
    // expansion fire uses. Minimal, audio-nudged so strikes can fatten slightly.
    float bandWidth = 0.06 + burst * 0.05 + motion * 0.02;
    float band = smoothstep(0.0, bandWidth, edge);

    float intensity = band * (0.35 + core * 0.9) * coreInt * flicker;
    intensity += band * burst * 0.5;          // onset flash on the line
    intensity = clamp(intensity, 0.0, 1.0);

    // ---- Color ----
    float ci = pow(intensity, 0.8);
    vec3 color = lightningColor(ci, high);

    // Electric blue glow halo immediately around the hottest cores (kept tight).
    color += vec3(0.15, 0.35, 0.9) * pow(intensity, 2.0) * 0.6;

    // ---- Micro-sparks on highs ----
    if (sparkle > 0.01 && edge > 0.1) {
        float sp = snoise(vec3(uv * 60.0, t * 8.0));
        float spMask = step(0.9, sp) * sparkle * band;
        color += vec3(0.8, 0.95, 1.0) * spMask * 2.0;
        intensity += spMask;
    }

    // ---- Strike flash (white) on strong onsets ----
    if (burst > 0.05) {
        color = mix(color, vec3(0.9, 0.96, 1.0), burst * 0.55 * band * strike);
    }

    float alpha = clamp(intensity, 0.0, 1.0);
    fragColor = TDOutputSwizzle(vec4(color * alpha, alpha));  // premultiplied
}
