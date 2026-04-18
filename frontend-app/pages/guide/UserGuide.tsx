import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Menu,
  X,
  LayoutGrid,
  FileSearch,
  Database,
  GitBranch,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { motion, AnimatePresence } from "framer-motion";

type ByteStyleCard = {
  title: string;
  desc: string;
  gradient: string;
  icon: string;
};

type GuideNavId =
  | "overview"
  | "capabilities"
  | "highlights"
  | "milestones"
  | "start";

type GuideNavItem = {
  id: GuideNavId;
  label: string;
  sectionIndex?: number;
  focusCardIndex?: number;
  action?: "back";
};

const guideSectionBackdropStyles: Array<{
  backgroundColor: string;
  backgroundImage: string;
}> = [
  {
    backgroundColor: "#1e293b",
    backgroundImage:
      "linear-gradient(180deg, rgba(15,23,42,1) 0%, rgba(30,41,59,1) 100%)",
  },
  {
    backgroundColor: "#ffffff",
    backgroundImage: "none",
  },
  {
    backgroundColor: "#ddf4ff",
    backgroundImage: [
      "radial-gradient(circle at 14% 78%, rgba(90,253,165,0.18) 0%, rgba(90,253,165,0) 26%)",
      "radial-gradient(circle at 86% 18%, rgba(38,198,255,0.18) 0%, rgba(38,198,255,0) 26%)",
      "radial-gradient(circle at 52% -10%, rgba(255,255,255,0.68) 0%, rgba(255,255,255,0) 28%)",
      "linear-gradient(180deg, #ffe8fa 0%, #ddf4ff 56.25%)",
    ].join(", "),
  },
];

const guideGlassPanelStyle: React.CSSProperties = {
  border: "1px solid rgba(255,255,255,0.72)",
  boxShadow:
    "0 28px 90px rgba(0,26,81,0.16), 0 10px 24px rgba(0,26,81,0.08), inset 0 1px 0 rgba(255,255,255,0.9)",
  backdropFilter: "blur(20px)",
  WebkitBackdropFilter: "blur(20px)",
};

const guideGlassOverlay =
  "linear-gradient(135deg, rgba(255,255,255,0.84) 0%, rgba(255,255,255,0.34) 42%, rgba(221,244,255,0.22) 100%)";

const clampGuidePointer = (value: number): number =>
  Math.max(0, Math.min(1, value));

type GuideParticleDash = {
  angle: number;
  radius: number;
  length: number;
  thickness: number;
  opacity: number;
  depth: number;
  sway: number;
  phase: number;
  color: string;
};

type GuideParticleBody = GuideParticleDash & {
  x: number;
  y: number;
  vx: number;
  vy: number;
  homeX: number;
  homeY: number;
  collisionRadius: number;
};

type GuideAmbientSpeck = {
  x: number;
  y: number;
  radius: number;
  opacity: number;
  color: string;
  driftX: number;
  driftY: number;
  phase: number;
};

const createGuideParticleDashes = (count: number): GuideParticleDash[] => {
  let seed = 17;
  const rand = () => {
    const value = Math.sin(seed * 78.233) * 43758.5453123;
    seed += 1;
    return value - Math.floor(value);
  };

  return Array.from({ length: count }, () => {
    const angle = rand() * Math.PI * 2;
    const violetBias = Math.cos(angle) * 0.5 + 0.5;
    const accentChance = rand();
    let color = "#2f63ff";

    if (accentChance > 0.985) {
      color = "#d75aa0";
    } else if (violetBias > 0.72 || accentChance > 0.9) {
      color = rand() > 0.5 ? "#6d58ff" : "#7f63ff";
    } else {
      color = rand() > 0.55 ? "#2456ff" : "#3d6cff";
    }

    return {
      angle,
      radius: 0.24 + Math.pow(rand(), 0.92) * 0.82,
      length: 1.6 + rand() * 6.2,
      thickness: 0.85 + rand() * 1.35,
      opacity: 0.18 + rand() * 0.7,
      depth: 0.35 + rand() * 0.95,
      sway: (rand() - 0.5) * 0.95,
      phase: rand() * Math.PI * 2,
      color,
    };
  });
};

const createGuideAmbientSpecks = (count: number): GuideAmbientSpeck[] => {
  let seed = 211;
  const rand = () => {
    const value = Math.sin(seed * 53.121) * 24634.63451;
    seed += 1;
    return value - Math.floor(value);
  };

  return Array.from({ length: count }, () => {
    const tint = rand();
    let color = "rgba(76, 112, 255, 1)";
    if (tint > 0.9) {
      color = "rgba(204, 108, 180, 1)";
    } else if (tint > 0.72) {
      color = "rgba(131, 103, 255, 1)";
    } else if (tint < 0.18) {
      color = "rgba(160, 178, 210, 1)";
    }
    return {
      x: rand(),
      y: rand(),
      radius: 0.9 + rand() * 2.4,
      opacity: 0.08 + rand() * 0.22,
      color,
      driftX: (rand() - 0.5) * 18,
      driftY: (rand() - 0.5) * 18,
      phase: rand() * Math.PI * 2,
    };
  });
};

const createGuideEdgeSpecks = (count: number): GuideAmbientSpeck[] => {
  let seed = 977;
  const rand = () => {
    const value = Math.sin(seed * 61.913) * 18643.13571;
    seed += 1;
    return value - Math.floor(value);
  };

  return Array.from({ length: count }, () => {
    const edgeZone = rand();
    let x = rand();
    let y = rand();

    if (edgeZone < 0.25) {
      x = rand() * 0.14;
      y = rand();
    } else if (edgeZone < 0.5) {
      x = 0.86 + rand() * 0.14;
      y = rand();
    } else if (edgeZone < 0.75) {
      x = rand();
      y = rand() * 0.14;
    } else {
      x = rand();
      y = 0.86 + rand() * 0.14;
    }

    const tint = rand();
    let color = "rgba(84, 118, 255, 1)";
    if (tint > 0.88) {
      color = "rgba(204, 116, 184, 1)";
    } else if (tint > 0.68) {
      color = "rgba(136, 112, 255, 1)";
    } else if (tint < 0.16) {
      color = "rgba(186, 198, 226, 1)";
    }

    return {
      x,
      y,
      radius: 0.7 + rand() * 2.1,
      opacity: 0.1 + rand() * 0.22,
      color,
      driftX: (rand() - 0.5) * 12,
      driftY: (rand() - 0.5) * 12,
      phase: rand() * Math.PI * 2,
    };
  });
};

const CapabilitiesInteractiveBackdrop: React.FC<{ active: boolean }> = ({
  active,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dashes = useMemo(() => createGuideParticleDashes(560), []);
  const ambientSpecks = useMemo(() => createGuideAmbientSpecks(180), []);
  const edgeSpecks = useMemo(() => createGuideEdgeSpecks(220), []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof window === "undefined") {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pointer = {
      x: 0.5,
      y: 0.5,
      targetX: 0.5,
      targetY: 0.5,
    };

    let animationFrame = 0;
    let canvasWidth = 0;
    let canvasHeight = 0;
    let deviceScale = 1;
    let particles: GuideParticleBody[] = [];

    const buildParticles = () => {
      const centerX = canvasWidth * 0.5;
      const centerY = canvasHeight * 0.5;
      const radiusBase = Math.hypot(canvasWidth, canvasHeight) * 0.58;
      const verticalScale = 0.98;

      particles = dashes.map((dash, index) => {
        const homeRadius = dash.radius * radiusBase;
        const homeX = centerX + Math.cos(dash.angle) * homeRadius;
        const homeY =
          centerY + Math.sin(dash.angle) * homeRadius * verticalScale;
        const jitterAngle = dash.angle + index * 0.071;
        const jitter = 14 + dash.depth * 24;
        return {
          ...dash,
          homeX,
          homeY,
          x: homeX + Math.cos(jitterAngle) * jitter,
          y: homeY + Math.sin(jitterAngle) * jitter,
          vx: 0,
          vy: 0,
          collisionRadius: Math.max(
            2.6,
            dash.length * 0.7 + dash.thickness * 0.9,
          ),
        };
      });
    };

    const resizeCanvas = () => {
      const bounds = canvas.getBoundingClientRect();
      canvasWidth = Math.max(1, Math.round(bounds.width));
      canvasHeight = Math.max(1, Math.round(bounds.height));
      deviceScale = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      canvas.width = Math.round(canvasWidth * deviceScale);
      canvas.height = Math.round(canvasHeight * deviceScale);
      context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
      buildParticles();
    };

    const renderFrame = (timestamp: number) => {
      pointer.x += (pointer.targetX - pointer.x) * 0.11;
      pointer.y += (pointer.targetY - pointer.y) * 0.11;

      context.clearRect(0, 0, canvasWidth, canvasHeight);
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, canvasWidth, canvasHeight);

      const sceneCenterX = canvasWidth * 0.5;
      const sceneCenterY = canvasHeight * 0.5;
      const pointerPixelX = pointer.x * canvasWidth;
      const pointerPixelY = pointer.y * canvasHeight;
      const centerSafeWidth = Math.min(canvasWidth * 0.56, 920);
      const centerSafeHeight = Math.min(canvasHeight * 0.4, 360);
      const centerSafeRadiusX = centerSafeWidth * 0.5;
      const centerSafeRadiusY = centerSafeHeight * 0.5;
      const pointerInfluence = Math.hypot(canvasWidth, canvasHeight) * 0.24;

      const halo = context.createRadialGradient(
        sceneCenterX,
        sceneCenterY,
        Math.min(canvasWidth, canvasHeight) * 0.08,
        sceneCenterX,
        sceneCenterY,
        Math.min(canvasWidth, canvasHeight) * 0.44,
      );
      halo.addColorStop(0, "rgba(255,255,255,1)");
      halo.addColorStop(0.26, "rgba(255,255,255,0.985)");
      halo.addColorStop(0.62, "rgba(249,251,255,0.92)");
      halo.addColorStop(1, "rgba(255,255,255,1)");
      context.fillStyle = halo;
      context.fillRect(0, 0, canvasWidth, canvasHeight);

      for (const speck of ambientSpecks) {
        const driftWave = timestamp * 0.00022 + speck.phase;
        const x =
          speck.x * canvasWidth +
          Math.cos(driftWave) * speck.driftX +
          (pointer.x - 0.5) * 22;
        const y =
          speck.y * canvasHeight +
          Math.sin(driftWave * 1.13) * speck.driftY +
          (pointer.y - 0.5) * 16;

        context.beginPath();
        context.fillStyle = speck.color;
        context.globalAlpha = speck.opacity;
        context.arc(x, y, speck.radius, 0, Math.PI * 2);
        context.fill();
      }

      for (const speck of edgeSpecks) {
        const driftWave = timestamp * 0.00018 + speck.phase;
        const x =
          speck.x * canvasWidth +
          Math.cos(driftWave) * speck.driftX +
          (pointer.x - 0.5) * 10;
        const y =
          speck.y * canvasHeight +
          Math.sin(driftWave * 1.08) * speck.driftY +
          (pointer.y - 0.5) * 8;

        context.beginPath();
        context.fillStyle = speck.color;
        context.globalAlpha = speck.opacity;
        context.arc(x, y, speck.radius, 0, Math.PI * 2);
        context.fill();
      }

      for (const particle of particles) {
        const homeForce = reduceMotion ? 0.016 : 0.028;
        let ax = (particle.homeX - particle.x) * homeForce;
        let ay = (particle.homeY - particle.y) * homeForce;

        const driftWave = timestamp * 0.00055 + particle.phase;
        ax += Math.cos(driftWave) * 0.02 * particle.depth;
        ay += Math.sin(driftWave * 1.13) * 0.018 * particle.depth;

        const dxPointer = particle.x - pointerPixelX;
        const dyPointer = particle.y - pointerPixelY;
        const pointerDistance = Math.hypot(dxPointer, dyPointer) || 1;
        if (pointerDistance < pointerInfluence) {
          const influence = 1 - pointerDistance / pointerInfluence;
          const repel = 0.46 * particle.depth * influence;
          ax += (dxPointer / pointerDistance) * repel;
          ay += (dyPointer / pointerDistance) * repel;
          ax += (-dyPointer / pointerDistance) * 0.062 * influence;
          ay += (dxPointer / pointerDistance) * 0.062 * influence;
          ax += (pointer.x - 0.5) * 0.08 * particle.depth * influence;
          ay += (pointer.y - 0.5) * 0.08 * particle.depth * influence;
        }

        const dxSafe = particle.x - sceneCenterX;
        const dySafe = particle.y - sceneCenterY;
        const safeMetric =
          (dxSafe * dxSafe) / (centerSafeRadiusX * centerSafeRadiusX) +
          (dySafe * dySafe) / (centerSafeRadiusY * centerSafeRadiusY);
        if (safeMetric < 1.12) {
          const safeNorm = Math.sqrt(safeMetric) || 0.0001;
          const push = (1.18 - safeMetric) * 0.42;
          ax += (dxSafe / (centerSafeRadiusX * safeNorm)) * push;
          ay += (dySafe / (centerSafeRadiusY * safeNorm)) * push;
        }

        particle.vx += ax;
        particle.vy += ay;
        particle.vx *= reduceMotion ? 0.86 : 0.948;
        particle.vy *= reduceMotion ? 0.86 : 0.948;
      }

      for (let i = 0; i < particles.length; i += 1) {
        const current = particles[i];
        for (let j = i + 1; j < particles.length; j += 1) {
          const other = particles[j];
          const dx = other.x - current.x;
          const dy = other.y - current.y;
          const distance = Math.hypot(dx, dy) || 0.0001;
          const minDistance =
            current.collisionRadius + other.collisionRadius + 1.2;

          if (distance >= minDistance) {
            continue;
          }

          const nx = dx / distance;
          const ny = dy / distance;
          const overlap = minDistance - distance;
          const separation = overlap * 0.5;

          current.x -= nx * separation;
          current.y -= ny * separation;
          other.x += nx * separation;
          other.y += ny * separation;

          const relativeVelocityX = other.vx - current.vx;
          const relativeVelocityY = other.vy - current.vy;
          const normalVelocity =
            relativeVelocityX * nx + relativeVelocityY * ny;

          if (normalVelocity < 0) {
            const bounce = 0.58;
            const impulse = (-(1 + bounce) * normalVelocity) / 2;
            current.vx -= impulse * nx;
            current.vy -= impulse * ny;
            other.vx += impulse * nx;
            other.vy += impulse * ny;
          }
        }
      }

      for (const particle of particles) {
        particle.x += particle.vx;
        particle.y += particle.vy;

        if (particle.x < 0) {
          particle.x = 0;
          particle.vx *= -0.56;
        } else if (particle.x > canvasWidth) {
          particle.x = canvasWidth;
          particle.vx *= -0.56;
        }

        if (particle.y < 0) {
          particle.y = 0;
          particle.vy *= -0.56;
        } else if (particle.y > canvasHeight) {
          particle.y = canvasHeight;
          particle.vy *= -0.56;
        }

        const distanceFromCenter = Math.hypot(
          particle.x - sceneCenterX,
          particle.y - sceneCenterY,
        );
        const maxRadius = Math.hypot(canvasWidth, canvasHeight) * 0.72;
        const centerFade = clampGuidePointer(
          (distanceFromCenter - Math.min(centerSafeRadiusX, centerSafeRadiusY) * 0.76) /
            132,
        );
        const edgeFade = clampGuidePointer(
          (maxRadius * 1.16 - distanceFromCenter) / 260,
        );
        const visibility = centerFade * edgeFade;

        if (visibility <= 0.01) {
          continue;
        }

        const speed = Math.hypot(particle.vx, particle.vy);
        const rotation =
          Math.atan2(particle.vy || 0.0001, particle.vx || 0.0001) +
          Math.PI / 2 +
          particle.sway * 0.26;
        const dashLength =
          particle.length * (1 + Math.min(0.85, speed * 0.4));
        const alpha =
          particle.opacity *
          visibility *
          (0.76 + Math.min(0.24, speed * 0.12));

        context.save();
        context.translate(particle.x, particle.y);
        context.rotate(rotation);
        context.strokeStyle = particle.color;
        context.globalAlpha = alpha;
        context.lineWidth = particle.thickness;
        context.lineCap = "round";
        context.beginPath();
        context.moveTo(-dashLength / 2, 0);
        context.lineTo(dashLength / 2, 0);
        context.stroke();
        context.restore();
      }

      animationFrame = window.requestAnimationFrame(renderFrame);
    };

    const updatePointer = (clientX: number, clientY: number) => {
      pointer.targetX = clampGuidePointer(clientX / window.innerWidth);
      pointer.targetY = clampGuidePointer(clientY / window.innerHeight);
    };

    const resetPointer = () => {
      pointer.targetX = 0.5;
      pointer.targetY = 0.5;
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!active) {
        return;
      }
      updatePointer(event.clientX, event.clientY);
    };

    resizeCanvas();
    animationFrame = window.requestAnimationFrame(renderFrame);

    window.addEventListener("resize", resizeCanvas);
    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("pointerdown", handlePointerMove, { passive: true });
    window.addEventListener("pointerleave", resetPointer);
    window.addEventListener("blur", resetPointer);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", resizeCanvas);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerdown", handlePointerMove);
      window.removeEventListener("pointerleave", resetPointer);
      window.removeEventListener("blur", resetPointer);
    };
  }, [active, ambientSpecks, dashes, edgeSpecks]);

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at center, rgba(255,255,255,0) 0%, rgba(255,255,255,0) 28%, rgba(255,255,255,0.38) 52%, rgba(255,255,255,0.78) 74%, rgba(255,255,255,0.98) 100%)",
        }}
      />
    </div>
  );
};

// SVG 波浪过渡组件
const WaveTransition: React.FC<{ direction: "up" | "down"; color: string }> = ({
  direction,
  color,
}) => {
  return (
    <motion.div
      className="absolute left-0 right-0 z-30 pointer-events-none overflow-hidden"
      style={{ [direction === "up" ? "bottom" : "top"]: 0, height: "150px" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <svg
        viewBox="0 0 1440 150"
        className="absolute w-full h-full"
        preserveAspectRatio="none"
      >
        <motion.path
          fill={color}
          d="M0,64L48,80C96,96,192,128,288,128C384,128,480,96,576,85.3C672,75,768,85,864,101.3C960,117,1056,139,1152,133.3C1248,128,1344,96,1392,80L1440,64L1440,150L1392,150C1344,150,1248,150,1152,150C1056,150,960,150,864,150C768,150,672,150,576,150C480,150,384,150,288,150C192,150,96,150,48,150L0,150Z"
          initial={{
            d:
              direction === "up"
                ? "M0,150L48,150C96,150,192,150,288,150C384,150,480,150,576,150C672,150,768,150,864,150C960,150,1056,150,1152,150C1248,150,1344,150,1392,150L1440,150L1440,150L1392,150C1344,150,1248,150,1152,150C1056,150,960,150,864,150C768,150,672,150,576,150C480,150,384,150,288,150C192,150,96,150,48,150L0,150Z"
                : "M0,0L48,0C96,0,192,0,288,0C384,0,480,0,576,0C672,0,768,0,864,0C960,0,1056,0,1152,0C1248,0,1344,0,1392,0L1440,0L1440,0L1392,0C1344,0,1248,0,1152,0C1056,0,960,0,864,0C768,0,672,0,576,0C480,0,384,0,288,0C192,0,96,0,48,0L0,0Z",
          }}
          animate={{
            d: "M0,64L48,80C96,96,192,128,288,128C384,128,480,96,576,85.3C672,75,768,85,864,101.3C960,117,1056,139,1152,133.3C1248,128,1344,96,1392,80L1440,64L1440,150L1392,150C1344,150,1248,150,1152,150C1056,150,960,150,864,150C768,150,672,150,576,150C480,150,384,150,288,150C192,150,96,150,48,150L0,150Z",
          }}
          transition={{ duration: 0.8, ease: "easeInOut" }}
        />
      </svg>
    </motion.div>
  );
};

const GuideBackgroundTransition: React.FC<{ sectionIndex: number }> = ({
  sectionIndex,
}) => {
  const backdrop =
    guideSectionBackdropStyles[sectionIndex] ?? guideSectionBackdropStyles[0];

  return (
    <AnimatePresence mode="sync">
      <motion.div
        key={sectionIndex}
        className="absolute inset-0"
        initial={{ opacity: 0, scale: 1.03 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.985 }}
        transition={{ duration: 0.95, ease: [0.22, 1, 0.36, 1] }}
      >
        <div
          className="absolute inset-0"
          style={{
            backgroundColor: backdrop.backgroundColor,
            backgroundImage: backdrop.backgroundImage,
          }}
        />
        {sectionIndex === 1 && <CapabilitiesInteractiveBackdrop active />}
        {sectionIndex > 0 && sectionIndex !== 1 && (
          <motion.div
            className="absolute inset-0"
            style={{
              backgroundImage:
                "linear-gradient(rgba(0,26,81,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(0,26,81,0.045) 1px, transparent 1px)",
              backgroundSize: "120px 120px",
              maskImage:
                "linear-gradient(180deg, rgba(0,0,0,0.18) 0%, rgba(0,0,0,0.08) 30%, rgba(0,0,0,0) 100%)",
              WebkitMaskImage:
                "linear-gradient(180deg, rgba(0,0,0,0.18) 0%, rgba(0,0,0,0.08) 30%, rgba(0,0,0,0) 100%)",
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.32 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
};

const StackedCardsCarousel: React.FC<{
  byteStyles: ByteStyleCard[];
  focusIndex?: number;
}> = ({ byteStyles, focusIndex }) => {
  const [activeIndex, setActiveIndex] = useState(0);
  const [pressedIndex, setPressedIndex] = useState<number | null>(null);
  const [leavingIndex, setLeavingIndex] = useState<number | null>(null);
  const [enteringIndex, setEnteringIndex] = useState<number | null>(null);
  const transitionTimersRef = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      transitionTimersRef.current.forEach((timer) =>
        window.clearTimeout(timer),
      );
      transitionTimersRef.current = [];
    };
  }, []);

  useEffect(() => {
    if (typeof focusIndex !== "number" || byteStyles.length === 0) return;
    const normalizedIndex = ((focusIndex % byteStyles.length) + byteStyles.length) % byteStyles.length;
    transitionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    transitionTimersRef.current = [];
    setPressedIndex(null);
    setLeavingIndex(null);
    setEnteringIndex(null);
    setActiveIndex(normalizedIndex);
  }, [byteStyles.length, focusIndex]);

  const queueStackChange = (nextIndex: number) => {
    if (nextIndex === activeIndex) return;

    transitionTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    transitionTimersRef.current = [];

    const currentIndex = activeIndex;
    // 设置下一张卡片为进入状态（从四周移到中间）
    setEnteringIndex(nextIndex);
    // 设置当前卡片为离开状态（从中间移到四周）
    setLeavingIndex(currentIndex);
    
    // 短暂延迟后切换到下一张卡片
    transitionTimersRef.current.push(
      window.setTimeout(() => {
        setActiveIndex(nextIndex);
        setEnteringIndex(null);
      }, 80),
    );

    // 动画完成后清除离开状态
    transitionTimersRef.current.push(
      window.setTimeout(() => {
        setLeavingIndex(null);
      }, 600),
    );
  };

  const handlePrev = () => {
    queueStackChange((activeIndex - 1 + byteStyles.length) % byteStyles.length);
  };

  const handleNext = () => {
    queueStackChange((activeIndex + 1) % byteStyles.length);
  };

  const getCardStyle = (index: number) => {
    // 定义5个位置：中心 + 四周4个位置
    const positions = [
      { x: 0, y: 6, scale: 1, opacity: 1, zIndex: 120, rotate: 0, width: 222, height: 222 },
      { x: -238, y: -84, scale: 1, opacity: 0.96, zIndex: 90, rotate: -2.8, width: 218, height: 126 },
      { x: 238, y: -70, scale: 0.98, opacity: 0.94, zIndex: 80, rotate: 2.6, width: 212, height: 118 },
      { x: -230, y: 104, scale: 0.98, opacity: 0.94, zIndex: 70, rotate: 1.2, width: 228, height: 170 },
      { x: 238, y: 92, scale: 0.96, opacity: 0.92, zIndex: 60, rotate: -1.4, width: 190, height: 178 },
    ];

    if (byteStyles.length === 0) {
      return {
        x: 0,
        y: 0,
        scale: 0,
        opacity: 0,
        zIndex: 0,
        rotate: 0,
        width: 0,
        height: 0,
      };
    }

    // 计算相对位置索引，只取前5个位置（中心+四周4个）
    let positionIndex = ((index - activeIndex) % byteStyles.length + byteStyles.length) % byteStyles.length;
    
    // 如果超过4个位置（即第5个及以后），隐藏这些卡片
    if (positionIndex >= 5) {
      return {
        x: 0,
        y: 300,
        scale: 0.5,
        opacity: 0,
        zIndex: 0,
        rotate: 0,
        width: 0,
        height: 0,
      };
    }

    const position = positions[positionIndex];

    if (index === activeIndex && pressedIndex === activeIndex) {
      return {
        ...position,
        y: position.y + 26,
        scale: position.scale * 0.94,
        zIndex: position.zIndex + 50,
      };
    }

    // 下一张卡片从四周移到中间的动画
    if (index === enteringIndex) {
      return {
        x: position.x * 2.5,
        y: position.y * 2.5,
        scale: position.scale * 0.6,
        opacity: 0.2,
        zIndex: position.zIndex + 30,
        rotate: position.rotate * 2,
        width: position.width,
        height: position.height,
      };
    }

    if (index === leavingIndex && index !== activeIndex) {
      // 当前卡片从中间移到四周的动画
      return {
        x: position.x * 1.8,
        y: position.y * 1.8,
        scale: position.scale * 0.85,
        opacity: 0.4,
        zIndex: position.zIndex - 30,
        rotate: position.rotate * 2,
        width: position.width,
        height: position.height,
      };
    }

    return position;
  };

  const floatingDots = [
    { left: "6%", top: "10%", size: 5, opacity: 0.2 },
    { left: "18%", top: "72%", size: 4, opacity: 0.26 },
    { left: "30%", top: "18%", size: 4, opacity: 0.22 },
    { left: "63%", top: "12%", size: 5, opacity: 0.16 },
    { left: "74%", top: "70%", size: 4, opacity: 0.24 },
    { left: "90%", top: "8%", size: 5, opacity: 0.16 },
    { left: "86%", top: "56%", size: 4, opacity: 0.26 },
    { left: "58%", top: "86%", size: 4, opacity: 0.22 },
  ];

  return (
    <div className="relative flex h-[500px] w-full items-center justify-center">
      <div className="pointer-events-none absolute inset-0">
        {floatingDots.map((dot, index) => (
          <div
            key={index}
            className="absolute rounded-full bg-slate-400"
            style={{
              left: dot.left,
              top: dot.top,
              width: dot.size,
              height: dot.size,
              opacity: dot.opacity,
            }}
          />
        ))}
      </div>

      <div className="relative h-[430px] w-[920px]">
        {byteStyles.map((style, index) => {
          const cardStyle = getCardStyle(index);
          const isActive = index === activeIndex;
          const positionIndex = ((index - activeIndex) % 7 + 7) % 7;
          const accentPalette = [
            "rgba(34,197,94,0.95)",
            "rgba(245,158,11,0.95)",
            "rgba(14,165,233,0.95)",
            "rgba(99,102,241,0.95)",
            "rgba(15,23,42,0.95)",
            "rgba(148,163,184,0.95)",
          ];
          const accentColor = accentPalette[index % accentPalette.length];

          return (
            <motion.div
              key={index}
              className={cn(
                "absolute overflow-hidden",
                isActive ? "rounded-[34px]" : "rounded-[26px]",
                "select-none",
                isActive ? "cursor-default" : "cursor-pointer",
              )}
              style={{
                left: "50%",
                top: "50%",
                marginLeft: -(cardStyle.width / 2),
                marginTop: -(cardStyle.height / 2),
                width: cardStyle.width,
                height: cardStyle.height,
                border: isActive
                  ? "1px solid rgba(255,255,255,0.18)"
                  : "1px solid rgba(255,255,255,0.88)",
                background: isActive
                  ? "linear-gradient(180deg, rgba(6,10,36,0.98) 0%, rgba(20,22,46,0.94) 44%, rgba(55,55,74,0.88) 100%)"
                  : "linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(255,255,255,0.82) 100%)",
                backdropFilter: "blur(18px)",
                WebkitBackdropFilter: "blur(18px)",
                boxShadow: isActive
                  ? "0 38px 100px rgba(9,12,44,0.24), 0 18px 34px rgba(9,12,44,0.16), inset 0 1px 0 rgba(255,255,255,0.08)"
                  : "0 18px 44px rgba(15,23,42,0.12), 0 4px 14px rgba(15,23,42,0.06), inset 0 1px 0 rgba(255,255,255,0.92)",
                transformOrigin: "center",
                pointerEvents: cardStyle.opacity === 0 ? "none" : "auto",
              }}
              initial={false}
              animate={{
                x: cardStyle.x,
                y: cardStyle.y,
                scale: cardStyle.scale,
                opacity: cardStyle.opacity,
                zIndex: cardStyle.zIndex,
                rotate: cardStyle.rotate,
                width: cardStyle.width,
                height: cardStyle.height,
                marginLeft: -(cardStyle.width / 2),
                marginTop: -(cardStyle.height / 2),
              }}
              transition={{
                type: "spring",
                stiffness: 250,
                damping: 30,
                mass: 1,
              }}
              onClick={() => {
                if (index !== activeIndex) {
                  queueStackChange(index);
                }
              }}
            >
              {isActive ? (
                <>
                  <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_18%,rgba(255,255,255,0.18),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02))]" />
                  <div className="pointer-events-none absolute inset-x-10 bottom-0 h-24 bg-[radial-gradient(circle_at_50%_100%,rgba(255,255,255,0.12),transparent_72%)]" />
                  <div className="relative z-10 flex h-full flex-col items-center justify-between px-6 py-6 text-center">
                    <div className="rounded-full border border-white/12 bg-white/6 px-3 py-1 text-[10px] font-semibold tracking-[0.24em] text-white/56">
                      CORE CAPABILITY
                    </div>
                    <div className="relative flex h-[96px] w-[96px] items-center justify-center rounded-[30px] bg-white shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_18px_36px_rgba(255,255,255,0.14)]">
                      <div className="flex h-[42px] w-[42px] items-center justify-center rounded-[14px] bg-[#04071b] text-xl shadow-[0_10px_20px_rgba(0,0,0,0.28)]">
                        {style.icon}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <h3 className="text-xl font-bold tracking-tight text-white">
                        {style.title}
                      </h3>
                      <p className="mx-auto max-w-[170px] text-[11px] leading-5 text-white/68">
                        {style.desc}
                      </p>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.65)_0%,rgba(255,255,255,0.12)_48%,rgba(226,232,240,0.2)_100%)]" />
                  <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-white/95" />
                  <div className="pointer-events-none absolute -right-10 top-2 h-32 w-32 rounded-full bg-white/36 blur-3xl" />
                  <div className="pointer-events-none absolute left-0 top-0 h-full w-full bg-[linear-gradient(34deg,transparent_45%,rgba(226,232,240,0.4)_47%,transparent_52%)]" />
                  <div className="relative z-10 flex h-full flex-col px-6 py-5">
                    <div className="mb-4 text-center text-[15px] font-semibold tracking-tight text-slate-400">
                      {style.title}
                    </div>
                    {positionIndex === 1 && (
                      <div className="mt-1 space-y-4">
                        <div
                          className="h-4 w-[56%] rounded-full"
                          style={{ background: "rgba(3,6,31,0.98)" }}
                        />
                        <div className="h-4 w-[66%] rounded-md bg-slate-200/85" />
                      </div>
                    )}
                    {positionIndex === 2 && (
                      <div className="ml-auto mt-1 flex w-[68%] flex-col gap-3">
                        {[0, 1, 2].map((line) => (
                          <div
                            key={line}
                            className="flex items-center gap-3"
                          >
                            <div
                              className="h-3.5 w-3.5 rounded-full"
                              style={{ background: line === 0 ? accentColor : "rgba(226,232,240,0.95)" }}
                            />
                            <div className="h-2.5 flex-1 rounded-full bg-[#06091f]" />
                          </div>
                        ))}
                      </div>
                    )}
                    {positionIndex === 3 && (
                      <div className="mt-auto space-y-3">
                        <div className="h-5 w-full rounded-md bg-slate-800/88" />
                        <div className="h-4 w-[78%] rounded-md bg-slate-500/86" />
                        <div className="h-4 w-[66%] rounded-md bg-slate-400/82" />
                      </div>
                    )}
                    {positionIndex === 4 && (
                      <div className="mt-2 space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="h-4 w-4 rounded-md bg-[#05081d]" />
                          <div className="h-3.5 flex-1 rounded-full bg-slate-200/92" />
                        </div>
                        {[0, 1, 2].map((line) => (
                          <div key={line} className="flex items-center gap-3">
                            <div className="h-4 w-4 rounded-md bg-slate-200/92" />
                            <div className="h-3.5 flex-1 rounded-full bg-slate-200/92" />
                          </div>
                        ))}
                      </div>
                    )}
                    {(positionIndex === 5 || positionIndex === 6) && (
                      <div className="flex h-full items-center justify-center">
                        <div className="w-full space-y-3">
                          <div
                            className="h-4 rounded-md"
                            style={{ background: accentColor, opacity: 0.22 }}
                          />
                          <div className="h-4 rounded-md bg-slate-200/86" />
                          <div className="h-4 rounded-md bg-slate-200/72" />
                          <div className="h-4 rounded-md bg-slate-200/58" />
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
              {!isActive && (
                <div className="pointer-events-none absolute bottom-4 left-1/2 h-1.5 w-14 -translate-x-1/2 rounded-full bg-slate-200/70" />
              )}
              {isActive && (
                <div className="pointer-events-none absolute inset-x-8 bottom-5 h-8 rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.12)_0%,transparent_72%)] blur-xl" />
              )}
            </motion.div>
          );
        })}
      </div>

      <button
        onClick={handlePrev}
        className="absolute left-6 top-1/2 z-40 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-[18px] border border-white/75 bg-white/60 text-[#001a51] backdrop-blur-xl shadow-[0_18px_40px_rgba(0,26,81,0.12)] transition-colors hover:bg-white/78"
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
      <button
        onClick={handleNext}
        className="absolute right-6 top-1/2 z-40 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-[18px] border border-white/75 bg-white/60 text-[#001a51] backdrop-blur-xl shadow-[0_18px_40px_rgba(0,26,81,0.12)] transition-colors hover:bg-white/78"
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
      </button>
    </div>
  );
};

interface UserGuideProps {
  onBackToDashboard?: () => void;
}

export const UserGuide: React.FC<UserGuideProps> = ({ onBackToDashboard }) => {
  const [currentSection, setCurrentSection] = useState(0);
  const [isScrolling, setIsScrolling] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [timelineIndex, setTimelineIndex] = useState(0);
  const [heroSlideIndex, setHeroSlideIndex] = useState(0);
  const [activeNavId, setActiveNavId] = useState<GuideNavId>("overview");
  const [featureFocusIndex, setFeatureFocusIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const sectionCount = 3;

  // 页面切换函数
  const goToSection = useCallback(
    (index: number) => {
      if (index === currentSection) return;
      if (index >= 0 && index < sectionCount && !isScrolling) {
        setIsScrolling(true);
        setCurrentSection(index);
        setTimeout(() => setIsScrolling(false), 1000);
      }
    },
    [currentSection, isScrolling],
  );

  // 鼠标滚轮事件处理
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (isScrolling) return;

      if (e.deltaY > 0 && currentSection < sectionCount - 1) {
        goToSection(currentSection + 1);
      } else if (e.deltaY < 0 && currentSection > 0) {
        goToSection(currentSection - 1);
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener("wheel", handleWheel, { passive: false });
    }

    return () => {
      if (container) {
        container.removeEventListener("wheel", handleWheel);
      }
    };
  }, [currentSection, isScrolling, goToSection]);

  // 键盘导航
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isScrolling) return;
      if (e.key === "ArrowDown" || e.key === "PageDown") {
        e.preventDefault();
        goToSection(currentSection + 1);
      } else if (e.key === "ArrowUp" || e.key === "PageUp") {
        e.preventDefault();
        goToSection(currentSection - 1);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentSection, isScrolling, goToSection]);

  const byteStyles: ByteStyleCard[] = [
    {
      title: "自然语言指令",
      desc: "像聊天一样告诉 AI 你的需求，自动理解并执行文档处理任务。",
      icon: "💬",
      gradient: "linear-gradient(135deg, #FF9D6C 0%, #BB4E75 100%)",
    },
    {
      title: "智能文档解析",
      desc: "AI 自动识别 PDF、Word、Excel 内容，精准提取表格和关键字段。",
      icon: "🚀",
      gradient: "linear-gradient(135deg, #00C9FF 0%, #92FE9D 100%)",
    },
    {
      title: "自定义智能填表",
      desc: "跨文档自动对齐信息，智能合并多来源数据，消除重复与冲突。",
      icon: "🌈",
      gradient: "linear-gradient(135deg, #F6D365 0%, #FDA085 100%)",
    },
    {
      title: "可视化预览",
      desc: "实时预览提取结果，高亮显示数据来源，一键定位原文位置。",
      icon: "👁️",
      gradient: "linear-gradient(135deg, #84FAB0 0%, #8FD3F4 100%)",
    },
    {
      title: "模板自动生成",
      desc: "根据需求自动生成标准化报告，支持 Word、Excel 等格式导出。",
      icon: "📄",
      gradient: "linear-gradient(135deg, #A18CD1 0%, #FBC2EB 100%)",
    },
    {
      title: "AI 知识助手",
      desc: "智能问答解答文档疑问，基于知识库提供决策建议和业务洞察。",
      icon: "🤖",
      gradient: "linear-gradient(135deg, #FFECD2 0%, #FCB69F 100%)",
    },
  ];

  const guideNavItems: GuideNavItem[] = [
    { id: "overview", label: "平台概览", sectionIndex: 0 },
    {
      id: "capabilities",
      label: "核心能力",
      sectionIndex: 1,
      focusCardIndex: 0,
    },
    { id: "highlights", label: "功能亮点", sectionIndex: 1, focusCardIndex: 4 },
    { id: "milestones", label: "发展历程", sectionIndex: 2 },
    { id: "start", label: "开始体验", action: "back" },
  ];

  const slides = [
    {
      image:
        "https://images.unsplash.com/photo-1497215728101-856f4ea42174?q=80&w=2070&auto=format&fit=crop",
      title: "文档智慧\n重塑未来",
      subtitle: "核心愿景",
    },
    {
      image:
        "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop",
      title: "高效协同\n无界流转",
      subtitle: "卓越效能",
    },
    {
      image:
        "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?q=80&w=2664&auto=format&fit=crop",
      title: "数据洞察\n决策之源",
      subtitle: "深度智能",
    },
  ];

  // 首页轮播图自动播放
  useEffect(() => {
    const timer = setInterval(() => {
      setHeroSlideIndex((prev) => (prev + 1) % slides.length);
    }, 5000);
    return () => clearInterval(timer);
  }, [slides.length]);

  useEffect(() => {
    setActiveNavId((prev) => {
      if (currentSection === 0) return "overview";
      if (currentSection === 1) {
        return prev === "highlights" ? "highlights" : "capabilities";
      }
      if (currentSection === 2) return "milestones";
      return prev;
    });
  }, [currentSection]);

  const handleGuideNavClick = useCallback(
    (item: GuideNavItem) => {
      setMobileMenuOpen(false);
      setActiveNavId(item.id);

      if (typeof item.focusCardIndex === "number") {
        setFeatureFocusIndex(item.focusCardIndex);
      }

      if (typeof item.sectionIndex === "number") {
        if (item.sectionIndex !== currentSection) {
          goToSection(item.sectionIndex);
        }
        return;
      }

      if (item.action === "back") {
        onBackToDashboard?.();
      }
    },
    [currentSection, goToSection, onBackToDashboard],
  );

  const timelineData = [
    {
      year: "2023",
      month: "",
      title: "推出全新的大模型及相关产品",
      desc: "全球员工数持续增长，业务覆盖超过150个国家和地区",
      color: "from-blue-500 to-indigo-600",
      icon: "🚀",
    },
    {
      year: "2021",
      month: "",
      title: '正式提出"字节范"企业文化',
      desc: "发布社会责任报告，致力于可持续发展",
      color: "from-purple-500 to-pink-600",
      icon: "💡",
    },
    {
      year: "2016",
      month: "",
      title: "抖音上线，开启短视频新纪元",
      desc: "头条号创作者平台全面爆发，内容生态繁荣发展",
      color: "from-red-500 to-orange-600",
      icon: "🎵",
    },
    {
      year: "2012",
      month: "",
      title: "字节跳动在北京成立",
      desc: '推出首款产品"今日头条"，开启个性化推荐时代',
      color: "from-emerald-500 to-teal-600",
      icon: "🌱",
    },
  ];

  // 页面内容组件
  const Section1 = () => (
    <div className="h-full w-full relative overflow-hidden">
      {/* Hero Carousel */}
      <div className="absolute inset-0">
        <AnimatePresence mode="wait">
          <motion.div
            key={heroSlideIndex}
            className="absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.8 }}
          >
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-[5000ms] ease-linear"
              style={{
                backgroundImage: `url(${slides[heroSlideIndex].image})`,
                transform: "scale(1.1)",
              }}
            />
            <div className="absolute inset-0 bg-gradient-to-r from-slate-900/80 via-slate-900/50 to-transparent" />
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Content */}
      <div className="relative z-10 h-full flex items-center px-6 lg:px-20">
        <div className="max-w-2xl">
          <AnimatePresence mode="wait">
            <motion.div
              key={heroSlideIndex}
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -30 }}
              transition={{ duration: 0.5 }}
            >
              <h1 className="text-5xl md:text-7xl font-black text-white leading-tight mb-6 whitespace-pre-line ml-30">
                {slides[heroSlideIndex].title}
              </h1>
              <p className="text-xl text-white/70 mb-8 ml-30">
                {slides[heroSlideIndex].subtitle}
              </p>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );

  const Section2 = () => (
    <div className="h-full w-full relative overflow-hidden">
      <div className="relative z-20 flex h-full items-center justify-center px-6 lg:px-12">
        <div className="w-full max-w-[1320px]">
          <StackedCardsCarousel
            byteStyles={byteStyles}
            focusIndex={featureFocusIndex}
          />
        </div>
      </div>
    </div>
  );

  const Section3 = () => (
    <div className="h-full w-full relative overflow-hidden">
      {/* 装饰背景 - 黄色圆弧（右上角） */}
      <motion.div
        className="absolute -right-[280px] -top-[120px] w-[520px] h-[520px] rounded-full pointer-events-none blur-3xl"
        style={{
          background:
            "radial-gradient(circle, rgba(38,198,255,0.24) 0%, rgba(221,244,255,0.54) 42%, rgba(221,244,255,0) 76%)",
        }}
        animate={{
          y: Math.sin(Date.now() * 0.001) * 15,
          x: Math.cos(Date.now() * 0.001) * 10,
        }}
        transition={{ type: "spring", stiffness: 120, damping: 20 }}
      />
      {/* 装饰背景 - 浅绿色圆弧（左下角） */}
      <motion.div
        className="absolute -left-[260px] -bottom-[170px] w-[520px] h-[520px] rounded-full pointer-events-none blur-3xl"
        style={{
          background:
            "radial-gradient(circle, rgba(90,253,165,0.28) 0%, rgba(227,255,238,0.52) 40%, rgba(227,255,238,0) 76%)",
        }}
        animate={{
          y: Math.cos(Date.now() * 0.001) * 15,
          x: Math.sin(Date.now() * 0.001) * 10,
        }}
        transition={{ type: "spring", stiffness: 120, damping: 20 }}
      />

      <div className="h-full max-w-[1400px] mx-auto px-6 lg:px-12 flex flex-col justify-center">
        {/* 标题区域 */}
        <div className="mb-12">
          <h2 className="text-5xl md:text-6xl font-black text-slate-900 tracking-tight">
            发展历程
          </h2>
          <p className="mt-4 text-xl text-slate-500 leading-relaxed max-w-2xl">
            记录平台能力演进与关键节点，见证每一步的建设历程。
          </p>
        </div>

        {/* 轮播内容区域 */}
        <div className="relative">
          <div
            className="relative overflow-hidden rounded-[42px] bg-white/58"
            style={guideGlassPanelStyle}
          >
            <div
              className="pointer-events-none absolute inset-0"
              style={{ background: guideGlassOverlay }}
            />
            <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-white/95" />
            <div className="pointer-events-none absolute -right-16 top-8 h-56 w-56 rounded-full bg-cyan-200/20 blur-3xl" />
            <div className="pointer-events-none absolute -left-12 bottom-0 h-52 w-52 rounded-full bg-pink-200/20 blur-3xl" />
            <motion.div
              className="relative flex"
              animate={{ x: `-${timelineIndex * 100}%` }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
            >
              {timelineData.map((item, idx) => (
                <div key={idx} className="w-full flex-shrink-0">
                  <div className="flex flex-col lg:flex-row">
                    {/* 左侧：图片/图标区域 */}
                    <div
                      className={cn(
                        "lg:w-1/2 h-[300px] lg:h-[400px] flex items-center justify-center bg-gradient-to-br",
                        item.color,
                      )}
                    >
                      <div className="text-center text-white">
                        <div className="text-8xl mb-4">{item.icon}</div>
                        <div className="text-6xl font-black">{item.year}</div>
                      </div>
                    </div>
                    {/* 右侧：文字描述区域 */}
                    <div className="lg:w-1/2 flex flex-col justify-center border-white/35 bg-white/58 p-10 backdrop-blur-md lg:border-l lg:p-16">
                      <div className="text-sm font-medium text-slate-400 mb-2">
                        {item.year}年
                      </div>
                      <h3 className="text-3xl lg:text-4xl font-black text-slate-900 mb-6 leading-tight">
                        {item.title}
                      </h3>
                      <p className="text-xl text-slate-500 leading-relaxed">
                        {item.desc}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </motion.div>
          </div>

          {/* 底部循环式导航 */}
          <div className="mt-12 relative">
            <div className="relative h-20 flex items-center justify-center">
              <div className="flex items-center">
                {[LayoutGrid, FileSearch, Database, GitBranch].map(
                  (Icon, idx) => {
                    // 计算与选中项的距离，实现循环效果
                    const totalItems = 4;
                    let distance = idx - timelineIndex;

                    // 处理循环：如果距离超过一半，从另一方向计算
                    if (distance >= totalItems / 2) {
                      distance -= totalItems;
                    } else if (distance <= -totalItems / 2) {
                      distance += totalItems;
                    }

                    // 计算位置和样式
                    const isActive = idx === timelineIndex;
                    const baseSpacing = 100; // 基础间距
                    const xOffset = distance * baseSpacing;

                    // 根据距离调整大小和透明度
                    const absDistance = Math.abs(distance);
                    const scale = isActive
                      ? 1.2
                      : Math.max(0.7, 1 - absDistance * 0.15);
                    const opacity = isActive
                      ? 1
                      : Math.max(0.4, 1 - absDistance * 0.25);
                    const zIndex = isActive ? 30 : 20 - absDistance * 5;

                    return (
                      <motion.button
                        key={idx}
                        onClick={() => setTimelineIndex(idx)}
                        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
                        animate={{
                          x: xOffset,
                          scale: scale,
                          opacity: opacity,
                          zIndex: zIndex,
                        }}
                        transition={{
                          type: "spring",
                          stiffness: 300,
                          damping: 30,
                        }}
                      >
                        <div className="relative group">
                          <motion.div
                            className={cn(
                              "flex h-14 w-14 items-center justify-center rounded-[20px] border transition-all duration-300 backdrop-blur-xl",
                              isActive
                                ? "border-[#001a51]/5 bg-[#001a51] shadow-[0_18px_40px_rgba(0,26,81,0.24)]"
                                : "border-white/75 bg-white/55 shadow-[0_14px_28px_rgba(0,26,81,0.10)] group-hover:bg-white/72",
                            )}
                            whileHover={{ scale: isActive ? 1.2 : 1.1 }}
                          >
                            <Icon
                              size={24}
                              className={cn(
                                "transition-colors duration-300",
                                isActive
                                  ? "text-white"
                                  : "text-slate-500 group-hover:text-[#001a51]",
                              )}
                            />
                          </motion.div>
                          {/* 选中指示器 */}
                          <motion.div
                            className="absolute -bottom-3 left-1/2 h-2.5 w-2.5 rounded-full bg-[#26c6ff]"
                            initial={false}
                            animate={{
                              opacity: isActive ? 1 : 0,
                              scale: isActive ? 1 : 0,
                              x: "-50%",
                            }}
                            transition={{ duration: 0.2 }}
                          />
                        </div>
                      </motion.button>
                    );
                  },
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const sections = [{ render: Section1 }, { render: Section2 }, { render: Section3 }];

  return (
    <div
      ref={containerRef}
      className="relative h-screen w-full overflow-hidden bg-white"
    >
      <div className="absolute inset-0">
        <GuideBackgroundTransition sectionIndex={currentSection} />
      </div>
      {/* 导航栏 */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#5b8ff9] py-4 shadow-md">
        <div className="w-full px-6 lg:px-10 flex items-center justify-between text-white">
          <div
            className="flex items-center gap-6 xl:gap-10 cursor-pointer"
            onClick={() => handleGuideNavClick(guideNavItems[0])}
          >
            <div className="text-xl md:text-2xl font-bold tracking-tight flex items-center whitespace-nowrap">
              <span className="hidden md:inline-block text-white ml-38">
                文枢智动
              </span>
              <span className="md:hidden text-white">SmartDoc</span>
            </div>
          </div>
          <div className="hidden lg:flex items-center justify-end gap-6 xl:gap-10 font-medium text-[17px] ml-auto">
            {guideNavItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => handleGuideNavClick(item)}
                className={cn(
                  "cursor-pointer transition-colors relative group whitespace-nowrap",
                  activeNavId === item.id
                    ? "text-white"
                    : "hover:text-indigo-100",
                )}
              >
                {item.label}
                <span
                  className={cn(
                    "absolute -bottom-1 left-0 h-0.5 bg-white transition-all duration-300",
                    activeNavId === item.id
                      ? "w-full"
                      : "w-0 group-hover:w-full",
                  )}
                />
              </button>
            ))}
          </div>
          <button
            className="lg:hidden p-2 text-white"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.2 }}
              className="lg:hidden px-6 pb-4"
            >
              <div className="rounded-2xl bg-white/12 backdrop-blur-md border border-white/20 p-3 flex flex-col gap-1">
                {guideNavItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleGuideNavClick(item)}
                    className={cn(
                      "w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition-colors",
                      activeNavId === item.id
                        ? "bg-white/20 text-white"
                        : "text-white/90 hover:bg-white/10",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* 页面指示器 */}
      <div className="fixed right-8 top-1/2 -translate-y-1/2 z-50 flex flex-col gap-4">
        {sections.map((_, idx) => (
          <button
            key={idx}
            onClick={() => goToSection(idx)}
            className={cn(
              "w-3 h-3 rounded-full transition-all duration-500 border-2",
              currentSection === idx
                ? currentSection === 1
                  ? "bg-slate-900 border-slate-900 scale-125"
                  : "bg-white border-white scale-125"
                : currentSection === 1
                  ? "bg-transparent border-slate-300 hover:border-slate-500"
                  : "bg-transparent border-white/50 hover:border-white",
            )}
            aria-label={`Go to section ${idx + 1}`}
          />
        ))}
      </div>

      {/* 页面内容 */}
      <div className="relative h-full w-full">
        <AnimatePresence mode="wait">
          {sections.map((section, idx) => {
            return (
              <motion.div
                key={idx}
                className="absolute inset-0 h-full w-full"
                initial={{
                  y: idx > currentSection ? "100%" : "-100%",
                  zIndex: idx,
                }}
                animate={{
                  y:
                    idx === currentSection
                      ? 0
                      : idx < currentSection
                        ? "-100%"
                        : "100%",
                  zIndex:
                    idx === currentSection ? 10 : idx < currentSection ? 5 : 0,
                }}
                exit={{
                  y: idx < currentSection ? "-100%" : "100%",
                  zIndex: 5,
                }}
                transition={{
                  type: "spring",
                  stiffness: 100,
                  damping: 30,
                  duration: 0.8,
                }}
                style={{
                  pointerEvents: idx === currentSection ? "auto" : "none",
                }}
              >
                {/* SVG 波浪过渡 - 只在切换到第二页时显示 */}
                {idx === 1 && idx === currentSection && (
                  <WaveTransition direction="up" color="#ffffff" />
                )}
                {idx === 2 && idx === currentSection && (
                  <WaveTransition direction="up" color="#ddf4ff" />
                )}
                <div
                  className="h-full w-full"
                  style={{ backgroundColor: "transparent" }}
                >
                  {section.render()}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
};
