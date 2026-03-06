import React, { useRef, useEffect, useMemo, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
// @ts-ignore
import { GPUComputationRenderer } from 'three/examples/jsm/misc/GPUComputationRenderer.js';
import { EffectComposer, Bloom, DepthOfField } from '@react-three/postprocessing';

const SIZE = 64; // 64x64 = 4096 particles (Even fewer for subtle, elegant background)

/* ══════════════════════════════════════════════════════════════
   GLSL: Simplex 3D Noise
   ══════════════════════════════════════════════════════════════ */
const NOISE_GLSL = /* glsl */ `
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}

float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(
    i.z+vec4(0.0,i1.z,i2.z,1.0))
    +i.y+vec4(0.0,i1.y,i2.y,1.0))
    +i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=1.0/7.0;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}

vec3 curlNoise(vec3 p){
  const float e=0.1;
  float n1=snoise(p);
  float a=snoise(p+vec3(e,0,0));float b=snoise(p-vec3(e,0,0));
  float c=snoise(p+vec3(0,e,0));float d=snoise(p-vec3(0,e,0));
  float f=snoise(p+vec3(0,0,e));float g=snoise(p-vec3(0,0,e));
  return vec3((c-d)-(f-g),(f-g)-(a-b),(a-b)-(c-d))/(2.0*e);
}
`;

/* ══════════════════════════════════════════════════════════════
   GLSL: Velocity Computation
   ══════════════════════════════════════════════════════════════ */
const velocityShader = NOISE_GLSL + /* glsl */ `
uniform float uTime;
uniform float uDelta;
uniform vec3 uMouse;
uniform float uMouseRadius;
uniform float uCurlStr;
uniform float uAttractStr;
uniform float uDamping;
uniform sampler2D textureHome;

void main(){
  vec2 uv=gl_FragCoord.xy/resolution.xy;
  vec3 pos=texture2D(texturePosition,uv).xyz;
  vec3 vel=texture2D(textureVelocity,uv).xyz;
  vec3 home=texture2D(textureHome,uv).xyz;

  // 1. Extremely gentle curl noise for floating feeling
  vec3 curl=curlNoise(pos*1.2+uTime*0.03)*uCurlStr;

  // 2. Strong attraction precisely to home position
  vec3 attract=(home-pos)*uAttractStr;

  // 3. Mouse repulsion
  vec3 toMouse=pos-uMouse;
  float mDist=length(toMouse);
  float mForce=smoothstep(uMouseRadius,0.0,mDist);
  vec3 repel=normalize(toMouse+vec3(0.001))*mForce*mForce*4.0;

  // 4. Compose velocity
  vel=vel*uDamping+curl+attract+repel;

  // Clamp speed carefully to prevent explosions, keep it lower for calm effect
  float spd=length(vel);
  if(spd>2.0) vel=vel/spd*2.0;

  gl_FragColor=vec4(vel,spd);
}
`;

/* ══════════════════════════════════════════════════════════════
   GLSL: Position Integration
   ══════════════════════════════════════════════════════════════ */
const positionShader = /* glsl */ `
uniform float uDelta;

void main(){
  vec2 uv=gl_FragCoord.xy/resolution.xy;
  vec3 pos=texture2D(texturePosition,uv).xyz;
  vec3 vel=texture2D(textureVelocity,uv).xyz;
  pos+=vel*uDelta;
  gl_FragColor=vec4(pos,1.0);
}
`;

/* ══════════════════════════════════════════════════════════════
   GLSL: Particle Rendering
   ══════════════════════════════════════════════════════════════ */
const particleVert = /* glsl */ `
uniform sampler2D tPosition;
uniform sampler2D tVelocity;
uniform float uSize;
uniform float uIsDark;
attribute vec2 ref;
varying float vSpeed;
varying float vDepth;
varying float vAlpha;

void main(){
  vec4 posData=texture2D(tPosition,ref);
  vec4 velData=texture2D(tVelocity,ref);
  vec3 pos=posData.xyz;
  float speed=velData.w;

  vec4 mv=modelViewMatrix*vec4(pos,1.0);
  gl_Position=projectionMatrix*mv;

  float depth=-mv.z;
  gl_PointSize=uSize*(6.0/depth);
  gl_PointSize=clamp(gl_PointSize,0.2,10.0); // Slightly smaller points

  vSpeed=speed;
  vDepth=depth;
  vAlpha=smoothstep(10.0,2.0,depth);
}
`;

const particleFrag = /* glsl */ `
uniform float uIsDark;
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform vec3 uHighlight;
varying float vSpeed;
varying float vDepth;
varying float vAlpha;

void main(){
  vec2 c = gl_PointCoord - 0.5;
  float dist = length(c);
  if (dist > 0.5) discard;
  
  // Sharp inner core, very soft outer edge
  float alpha = pow(1.0 - smoothstep(0.0, 0.5, dist), 1.8);
  if (alpha < 0.01) discard;

  float speedF=smoothstep(0.0,0.8,vSpeed);
  vec3 col=mix(uColorA,uColorB,speedF*0.4);
  col=mix(col,uHighlight,speedF*0.6);

  float brightness=vAlpha*alpha;

  if(uIsDark>0.5){
    // Dark mode: very subtle glow
    gl_FragColor=vec4(col*brightness*0.4,brightness*0.4);
  } else {
    // Light mode: clear Morandi blue without dark edge blending issues
    gl_FragColor=vec4(col,brightness*0.85);
  }
}
`;

/* ══════════════════════════════════════════════════════════════
   Helper: 3D Book Target Generator
   ══════════════════════════════════════════════════════════════ */
function generateBookTargets(scale: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = [];
  const hw = scale * 0.40;
  const hh = scale * 0.32;
  const gap = scale * 0.03;
  const curl = hh * 0.15;

  const qb = (t: number, a: number, b: number, c: number) => { const m = 1 - t; return m * m * a + 2 * m * t * b + t * t * c; };

  const addLine = (p1: THREE.Vector3, p2: THREE.Vector3, count: number) => {
    for (let i = 0; i < count; i++) {
      const t = i / (count - 1 || 1);
      pts.push(new THREE.Vector3(p1.x + (p2.x - p1.x) * t, p1.y + (p2.y - p1.y) * t, p1.z + (p2.z - p1.z) * t));
    }
  };

  // Spine
  addLine(new THREE.Vector3(0, -hh, -0.05 * scale), new THREE.Vector3(0, hh, -0.05 * scale), 80);

  for (const s of [-1, 1]) {
    const inner = s * gap;
    const outer = s * (gap + hw);

    // Top & Bottom curved edges
    for (let i = 0; i < 80; i++) {
      const t = i / 79;
      const x = inner + (outer - inner) * t;
      const z = qb(t, -0.05 * scale, -curl, 0);
      pts.push(new THREE.Vector3(x, hh, z));
      pts.push(new THREE.Vector3(x, -hh, z));
    }
    // Outer & Inner edges
    addLine(new THREE.Vector3(outer, -hh, 0), new THREE.Vector3(outer, hh, 0), 80);
    addLine(new THREE.Vector3(inner, -hh, -0.05 * scale), new THREE.Vector3(inner, hh, -0.05 * scale), 80);

    // Text lines
    const textInner = inner + s * hw * 0.15;
    const textOuter = inner + s * hw * 0.85;
    const rows = 12;
    for (let r = 0; r < rows; r++) {
      const y = -hh * 0.70 + r * (hh * 1.4 / rows);
      const endX = r === rows - 1 ? inner + s * hw * 0.5 : textOuter;
      const count = Math.max(10, Math.floor(Math.abs(endX - textInner) / (scale * 0.015)));

      for (let j = 0; j < count; j++) {
        const t = j / (count - 1 || 1);
        const x = textInner + (endX - textInner) * t;
        const pageT = Math.abs(x - inner) / hw;
        const z = qb(pageT, -0.05 * scale, -curl, 0);

        const rx = x + (Math.random() - 0.5) * 0.04 * scale;
        const ry = y + (Math.random() - 0.5) * 0.015 * scale;
        pts.push(new THREE.Vector3(rx, ry, z + 0.02));
      }
    }
  }

  // Exact target array of length SIZE*SIZE
  const FINAL_COUNT = SIZE * SIZE;
  const finalPts: THREE.Vector3[] = [];
  const baseLen = pts.length;
  for (let i = 0; i < FINAL_COUNT; i++) {
    const base = pts[i % baseLen];
    const sx = base.x + (Math.random() - 0.5) * 0.02 * scale;
    const sy = base.y + (Math.random() - 0.5) * 0.02 * scale;
    const sz = base.z + (Math.random() - 0.5) * 0.02 * scale;
    finalPts.push(new THREE.Vector3(sx, sy, sz));
  }

  // Shuffle to avoid regular patterns when particles return
  for (let i = finalPts.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [finalPts[i], finalPts[j]] = [finalPts[j], finalPts[i]];
  }
  return finalPts;
}

/* ══════════════════════════════════════════════════════════════
   React Component: BookParticles
   ══════════════════════════════════════════════════════════════ */
function BookParticles({ isDark, positionOffset }: { isDark: boolean, positionOffset: [number, number, number] }) {
  const { gl, viewport, pointer } = useThree();
  const gpuRef = useRef<any>(null);
  const velVarRef = useRef<any>(null);
  const posVarRef = useRef<any>(null);
  const clockRef = useRef(0);

  // GPGPU setup
  useEffect(() => {
    const gpu = new GPUComputationRenderer(SIZE, SIZE, gl);

    const posTex = gpu.createTexture();
    const velTex = gpu.createTexture();
    const homeTex = gpu.createTexture();

    const pd = posTex.image.data as Float32Array;
    const vd = velTex.image.data as Float32Array;
    const hd = homeTex.image.data as Float32Array;

    const targets = generateBookTargets(3.0); // 3.0 scale in 3D world units

    for (let i = 0; i < SIZE * SIZE; i++) {
      const t = targets[i];

      // Initial position (spawn slightly scattered)
      pd[i * 4 + 0] = t.x + (Math.random() - 0.5) * 0.5;
      pd[i * 4 + 1] = t.y + (Math.random() - 0.5) * 0.5;
      pd[i * 4 + 2] = t.z + (Math.random() - 0.5) * 0.5;
      pd[i * 4 + 3] = 1;

      // Velocity
      vd[i * 4] = vd[i * 4 + 1] = vd[i * 4 + 2] = vd[i * 4 + 3] = 0;

      // Home exactly matches target
      hd[i * 4 + 0] = t.x;
      hd[i * 4 + 1] = t.y;
      hd[i * 4 + 2] = t.z;
      hd[i * 4 + 3] = 1;
    }

    const velVar = gpu.addVariable('textureVelocity', velocityShader, velTex);
    const posVar = gpu.addVariable('texturePosition', positionShader, posTex);

    gpu.setVariableDependencies(velVar, [velVar, posVar]);
    gpu.setVariableDependencies(posVar, [posVar, velVar]);

    const vu = velVar.material.uniforms;
    vu.uTime = { value: 0 };
    vu.uDelta = { value: 0.016 };
    vu.uMouse = { value: new THREE.Vector3(-999, -999, 0) };
    vu.textureHome = { value: homeTex };
    vu.uMouseRadius = { value: 1.0 };
    vu.uCurlStr = { value: 0.005 }; // Extremely low noise for a very calm feeling
    vu.uAttractStr = { value: 0.03 }; // Gentle attraction
    vu.uDamping = { value: 0.92 }; // High friction for smooth deceleration

    posVar.material.uniforms.uDelta = { value: 0.016 };

    const err = gpu.init();
    if (err) { console.error('GPGPU init error:', err); return; }

    gpuRef.current = gpu;
    velVarRef.current = velVar;
    posVarRef.current = posVar;

    return () => { gpu.dispose(); };
  }, [gl]);

  // Geometry + Ref Array
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(SIZE * SIZE * 3);
    const refs = new Float32Array(SIZE * SIZE * 2);
    for (let i = 0; i < SIZE * SIZE; i++) {
      refs[i * 2] = (i % SIZE + 0.5) / SIZE;
      refs[i * 2 + 1] = (Math.floor(i / SIZE) + 0.5) / SIZE;
    }
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('ref', new THREE.BufferAttribute(refs, 2));
    return geo;
  }, []);

  // Material
  const material = useMemo(() => {
    return new THREE.ShaderMaterial({
      vertexShader: particleVert,
      fragmentShader: particleFrag,
      uniforms: {
        tPosition: { value: null },
        tVelocity: { value: null },
        uSize: { value: 300.0 }, // Base size before depth scaling: slightly larger for clarity
        uIsDark: { value: isDark ? 1.0 : 0.0 },
        uColorA: { value: new THREE.Color(isDark ? '#6366f1' : '#4a6b8c') },
        uColorB: { value: new THREE.Color(isDark ? '#c084fc' : '#6d94b3') },
        uHighlight: { value: new THREE.Color(isDark ? '#22d3ee' : '#87b3d4') },
      },
      transparent: true,
      depthWrite: false,
      blending: isDark ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
  }, []);

  // Theme Sync
  useEffect(() => {
    if (!material) return;
    material.uniforms.uIsDark.value = isDark ? 1.0 : 0.0;
    material.uniforms.uColorA.value.set(isDark ? '#6366f1' : '#4a6b8c');
    material.uniforms.uColorB.value.set(isDark ? '#c084fc' : '#6d94b3');
    material.uniforms.uHighlight.value.set(isDark ? '#22d3ee' : '#87b3d4');
    material.blending = isDark ? THREE.AdditiveBlending : THREE.NormalBlending;
  }, [isDark, material]);

  // Render Loop
  useFrame((_, delta) => {
    const gpu = gpuRef.current;
    const velVar = velVarRef.current;
    const posVar = posVarRef.current;
    if (!gpu || !velVar || !posVar) return;

    clockRef.current += delta;
    const dt = Math.min(delta, 0.05);

    // The canvas is exactly 100vh tall and aligned to the top of the document.
    // R3F pointer [-1, 1] perfectly maps to the hero section screen space.
    const mx = (pointer.x * viewport.width / 2) - positionOffset[0];
    const my = (pointer.y * viewport.height / 2) - positionOffset[1];

    velVar.material.uniforms.uMouse.value.set(mx, my, 0);
    velVar.material.uniforms.uTime.value = clockRef.current;
    velVar.material.uniforms.uDelta.value = dt;
    posVar.material.uniforms.uDelta.value = dt;

    gpu.compute();

    material.uniforms.tPosition.value = gpu.getCurrentRenderTarget(posVar).texture;
    material.uniforms.tVelocity.value = gpu.getCurrentRenderTarget(velVar).texture;
  });

  return (
    <group position={positionOffset} rotation={[0.4, -0.4, 0]}>
      <points geometry={geometry} material={material} />
    </group>
  );
}

export default function BookScene({ isDark }: { isDark: boolean }) {
  return (
    <div className="absolute inset-0 w-full h-full pointer-events-auto">
      <Canvas
        camera={{ position: [0, 0, 4.5], fov: 45 }}
        dpr={[1, 1.5]}
        gl={{ antialias: false, alpha: true, powerPreference: 'high-performance' }}
      >
        <BookSceneContent isDark={isDark} />
      </Canvas>
    </div>
  );
}

function BookSceneContent({ isDark }: { isDark: boolean }) {
  const [ready, setReady] = useState(false);
  const { viewport } = useThree();

  // Calculate a dynamic position offset to place the book upper-right
  const offsetX = viewport.width * 0.22;
  const offsetY = viewport.height * 0.15;

  return (
    <>
      <EffectComposer disableNormalPass>
        <DepthOfField focusDistance={0.05} focalLength={0.15} bokehScale={3} height={480} />
        <Bloom
          intensity={isDark ? 2.5 : 0.0}
          luminanceThreshold={isDark ? 0.3 : 0.8}
          luminanceSmoothing={0.5}
          mipmapBlur
        />
      </EffectComposer>
      {/* Set ready after a small delay to ensure Canvas is fully sized before GPGPU init */}
      <group onUpdate={() => !ready && setReady(true)}>
        {ready && <BookParticles isDark={isDark} positionOffset={[offsetX, offsetY, 0]} />}
      </group>
    </>
  );
}
