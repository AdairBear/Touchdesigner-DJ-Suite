// fire_aura.glsl — GLSL TOP Pixel Shader
// ==========================================
// Organic fire aura effect for DJ Sam body silhouette.
// Warm color palette (orange → red → yellow → magenta) with
// fluid morphing driven by simplex noise.
//
// INPUTS (GLSL TOP):
//   sTD2DInputs[0] = Body edge mask  (from Edge TOP)
//   sTD2DInputs[1] = Motion energy   (from body_channels, mapped to TOP)
//   sTD2DInputs[2] = Audio energy    (from audio_params, mapped to TOP)
//
// UNIFORMS (pushed by aura_compositor.py via GLSL TOP custom pars):
//   uniform float uFlameIntensity;  // value1 — bass-driven flame strength
//   uniform float uTurbulence;      // value2 — mid-driven turbulence
//   uniform float uDistortion;      // value3 — heat distortion amount
//   uniform float uSparkle;         // value4 — high-driven sparkle
//   uniform float uMotionEnergy;    // value5 — body motion energy
//   uniform float uBassEnergy;      // value6 — raw bass energy
//   uniform float uMidEnergy;       // value7 — raw mid energy
//   uniform float uHighEnergy;      // value8 — raw high energy
//   uniform float uBurstDecay;      // value9 — onset burst decay
//
// SETUP IN TOUCHDESIGNER:
//   1. Create GLSL TOP  →  name: "fire_aura_glsl"
//   2. Pixel Shader: paste this code (or point DAT to this file)
//   3. Add 3 inputs to GLSL TOP:
//      - Input 0: edge_detect (Edge TOP output)
//      - Input 1: motion_energy_top (CHOP to TOP from body motion)
//      - Input 2: audio_energy_top  (CHOP to TOP from audio params)
//   4. Custom Parameters (Uniform page):
//      - value1 through value9 (floats, default 0.0)
//   5. Resolution: Match camera resolution (1280x720)
//   6. Output: RGBA 16-bit float
// ==========================================

// TD provides these automatically
uniform float uTime;          // absTime.seconds

// Custom uniforms from GLSL TOP parameters
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
// SIMPLEX NOISE (3D)
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

// Fractal Brownian Motion with 4 octaves
float fbm(vec3 p, float persistence) {
    float total = 0.0;
    float amplitude = 1.0;
    float frequency = 1.0;
    float maxVal = 0.0;
    for (int i = 0; i < 4; i++) {
        total += snoise(p * frequency) * amplitude;
        maxVal += amplitude;
        amplitude *= persistence;
        frequency *= 2.0;
    }
    return total / maxVal;
}


// ==========================================
// WARM FIRE COLOR PALETTE
// ==========================================
vec3 fireColor(float t, float bassBoost) {
    // Organic warm palette: dark red → orange → yellow → white-hot
    // With magenta undertones when bass hits

    // Base fire gradient
    vec3 c0 = vec3(0.12, 0.02, 0.02);  // Deep ember (near black-red)
    vec3 c1 = vec3(0.70, 0.10, 0.05);  // Dark red
    vec3 c2 = vec3(1.00, 0.35, 0.05);  // Orange
    vec3 c3 = vec3(1.00, 0.65, 0.10);  // Amber-yellow
    vec3 c4 = vec3(1.00, 0.90, 0.40);  // Bright yellow
    vec3 c5 = vec3(1.00, 0.98, 0.85);  // White-hot core

    // Magenta injection on bass
    vec3 magenta = vec3(0.85, 0.10, 0.55);

    vec3 color;
    if (t < 0.15) {
        color = mix(c0, c1, t / 0.15);
    } else if (t < 0.3) {
        color = mix(c1, c2, (t - 0.15) / 0.15);
    } else if (t < 0.5) {
        color = mix(c2, c3, (t - 0.3) / 0.2);
    } else if (t < 0.7) {
        color = mix(c3, c4, (t - 0.5) / 0.2);
    } else {
        color = mix(c4, c5, (t - 0.7) / 0.3);
    }

    // Blend magenta on bass hits
    color = mix(color, magenta, bassBoost * 0.3 * (1.0 - t));

    return color;
}


// ==========================================
// MAIN SHADER
// ==========================================
void main()
{
    // Normalized coordinates
    vec2 uv = vUV.st;
    vec2 resolution = uTDOutputInfo.res.zw;

    // ---- Sample inputs ----
    float edgeMask = texture(sTD2DInputs[0], uv).r;

    // Optional: motion and audio as texture lookups (fallback to uniforms)
    float motionTex = texture(sTD2DInputs[1], uv).r;
    float audioTex  = texture(sTD2DInputs[2], uv).r;

    // Use uniforms as primary, textures as spatial modulation
    float flameInt = max(uFlameIntensity, 0.15);  // Always some flame
    float turb     = max(uTurbulence, 0.1);
    float dist     = uDistortion;
    float sparkle  = uSparkle;
    float motion   = max(uMotionEnergy, motionTex);
    float bass     = uBassEnergy;
    float burst    = uBurstDecay;

    // ---- Heat distortion (UV warp) ----
    float t = uTime;
    vec2 distortUV = uv;
    float heatWarp = fbm(vec3(uv * 3.0, t * 0.5), 0.5) * dist * 0.03;
    distortUV.x += heatWarp;
    distortUV.y += abs(heatWarp) * 0.5;

    // Re-sample edge mask with distorted UVs
    float edge = texture(sTD2DInputs[0], distortUV).r;

    // ---- Fire noise layers ----
    // Layer 1: Large-scale flame shape (slow, organic)
    float flame1 = fbm(vec3(
        uv.x * 2.5 + sin(t * 0.3) * 0.2,
        uv.y * 3.0 - t * 0.8,   // Flames rise upward
        t * 0.15
    ), 0.55 + turb * 0.15);

    // Layer 2: Medium turbulence
    float flame2 = fbm(vec3(
        uv.x * 5.0 + cos(t * 0.7) * 0.3,
        uv.y * 6.0 - t * 1.5,
        t * 0.3 + 10.0
    ), 0.5);

    // Layer 3: Fine detail / flickering
    float flame3 = snoise(vec3(
        uv * 12.0 + vec2(sin(t * 2.0), -t * 3.0),
        t * 0.8
    ));

    // Combine noise layers
    float flameMix = flame1 * 0.5 + flame2 * 0.3 + flame3 * 0.2;

    // ---- Build aura intensity ----
    // Start from edge mask, expand outward with noise
    float auraBase = edge;

    // Expand flame outward from body edge
    float flameExpand = edge * (0.5 + flameMix * 0.5);

    // Soften edge → wider aura when more energy
    float expansion = 0.02 + flameInt * 0.04 + motion * 0.03 + burst * 0.08;
    float softEdge = smoothstep(0.0, expansion, edge);

    // Combine into final intensity
    float intensity = softEdge * (0.4 + flameExpand * 0.6);
    intensity *= flameInt;

    // Boost on burst
    intensity += burst * 0.4 * softEdge;

    // Clamp
    intensity = clamp(intensity, 0.0, 1.0);

    // ---- Color mapping ----
    // Map intensity through fire color palette
    float colorIndex = pow(intensity, 0.7);  // Gamma for warmer look
    vec3 color = fireColor(colorIndex, bass);

    // ---- Sparkle (high frequency glints on highs) ----
    if (sparkle > 0.01 && edge > 0.1) {
        float sparkNoise = snoise(vec3(uv * 40.0, t * 5.0));
        float sparkMask = step(0.85, sparkNoise) * sparkle * edge;
        color += vec3(1.0, 0.95, 0.7) * sparkMask * 2.0;
        intensity += sparkMask;
    }

    // ---- Burst flash (white-hot on onset) ----
    if (burst > 0.05) {
        vec3 burstColor = vec3(1.0, 0.92, 0.75);
        color = mix(color, burstColor, burst * 0.5 * softEdge);
    }

    // ---- Alpha for compositing ----
    // Use intensity as alpha so aura composites cleanly over camera
    float alpha = intensity;

    // Premultiply for correct Over compositing in TD
    fragColor = TDOutputSwizzle(vec4(color * alpha, alpha));
}
