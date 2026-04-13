﻿﻿import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import {
  Menu,
  X,
  Play,
  Database,
  GitBranch,
  FileText,
  FileSpreadsheet,
  FileCode,
  FileImage,
  File,
  Lock,
  RefreshCw,
  Zap,
  ShieldCheck,
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  motion,
  AnimatePresence,
  useScroll,
  useTransform,
  type Variants,
} from "framer-motion";
import { Label } from "recharts";
import deepreadWorkbenchImage from "../../assets/deepread-workbench.svg";
import knowledgeGraphImage from "../../assets/knowledge-graph.svg";
import documentFlowImage from "../../assets/文档.png";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type ByteStyleCard = {
  title: string;
  desc: string;
  gradient: string;
  icon: string;
};

type GuideNavId =
  | "overview"
  | "demonstration"
  | "capabilities"
  | "features"
  | "start";

type GuideNavItem = {
  id: GuideNavId;
  label: string;
  sectionIndex?: number;
  focusCardIndex?: number;
  action?: "back";
};

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

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
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
          (distanceFromCenter -
            Math.min(centerSafeRadiusX, centerSafeRadiusY) * 0.76) /
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
        const dashLength = particle.length * (1 + Math.min(0.85, speed * 0.4));
        const alpha =
          particle.opacity * visibility * (0.76 + Math.min(0.24, speed * 0.12));

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
    window.addEventListener("pointermove", handlePointerMove, {
      passive: true,
    });
    window.addEventListener("pointerdown", handlePointerMove, {
      passive: true,
    });
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

interface UserGuideProps {
  onBackToDashboard?: () => void;
  onOpenLogin?: () => void;
}

const GuideSectiondemonstration: React.FC<{
  containerRef: React.RefObject<HTMLDivElement | null>;
  currentSection: number;
}> = ({ containerRef, currentSection }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const modalVideoRef = useRef<HTMLVideoElement>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const [isVideoModalOpen, setIsVideoModalOpen] = useState(false);
  const lastVideoPointerTypeRef = useRef("mouse");
  const [isVideoHovering, setIsVideoHovering] = useState(false);
  const [videoHintPosition, setVideoHintPosition] = useState({
    x: 180,
    y: 180,
  });
  const demoVideoSrc =
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4";

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    container: containerRef,
    offset: ["start end", "end start"],
  });

  const scale = useTransform(
    scrollYProgress,
    [0, 0.4, 0.6, 1],
    [0.8, 1, 1, 0.8],
  );
  const borderRadius = useTransform(
    scrollYProgress,
    [0, 0.4, 0.6, 1],
    ["48px", "20px", "20px", "48px"],
  );

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            if (!isVideoModalOpen && videoRef.current) {
              videoRef.current
                .play()
                .catch((e) => console.log("Video play error:", e));
            }
          } else {
            if (videoRef.current) {
              videoRef.current.pause();
            }
          }
        });
      },
      { threshold: 0.3 },
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, [isVideoModalOpen]);

  useEffect(() => {
    if (!isVideoModalOpen || typeof window === "undefined") {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsVideoModalOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isVideoModalOpen]);

  useEffect(() => {
    if (isVideoModalOpen) {
      if (videoRef.current) {
        videoRef.current.pause();
      }
      if (modalVideoRef.current) {
        modalVideoRef.current.currentTime = 0;
        modalVideoRef.current.muted = false;
        modalVideoRef.current
          .play()
          .catch((e) => console.log("Modal video play error:", e));
      }
      return;
    }

    if (modalVideoRef.current) {
      modalVideoRef.current.pause();
      modalVideoRef.current.currentTime = 0;
    }

    if (currentSection === 3 && videoRef.current) {
      videoRef.current
        .play()
        .catch((e) => console.log("Preview video resume error:", e));
    }
  }, [currentSection, isVideoModalOpen]);

  const openVideoModal = () => {
    setIsVideoHovering(false);
    setIsVideoModalOpen(true);
  };

  const closeVideoModal = () => {
    setIsVideoModalOpen(false);
  };

  const updateVideoHintPosition = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.pointerType && event.pointerType !== "mouse") {
        return;
      }

      const bounds = event.currentTarget.getBoundingClientRect();
      setVideoHintPosition({
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });
      setIsVideoHovering(true);
    },
    [],
  );

  const handleVideoPointerEnter = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      lastVideoPointerTypeRef.current = event.pointerType || "mouse";
      if (event.pointerType && event.pointerType !== "mouse") {
        return;
      }

      setIsVideoHovering(true);
      updateVideoHintPosition(event);
    },
    [updateVideoHintPosition],
  );

  const handleVideoPointerLeave = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      lastVideoPointerTypeRef.current = event.pointerType || "mouse";
      if (event.pointerType && event.pointerType !== "mouse") {
        return;
      }

      setIsVideoHovering(false);
    },
    [],
  );

  const handleVideoPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      lastVideoPointerTypeRef.current = event.pointerType || "mouse";
    },
    [],
  );

  return (
    <>
      <div
        ref={sectionRef}
        className="h-screen w-full relative overflow-hidden flex items-center justify-center pt-24 px-6 pb-6"
      >
        <motion.div
          onClick={openVideoModal}
          onPointerDown={handleVideoPointerDown}
          onPointerEnter={handleVideoPointerEnter}
          onPointerMove={updateVideoHintPosition}
          onPointerLeave={handleVideoPointerLeave}
          className="w-full h-full overflow-hidden shadow-2xl relative bg-black text-left group cursor-pointer"
          style={{
            scale,
            borderRadius,
          }}
        >
          <video
            ref={videoRef}
            className="w-full h-full object-cover transition-transform duration-[800ms] ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-[1.02] scale-[1]"
            loop
            muted
            playsInline
            autoPlay
          >
            <source src={demoVideoSrc} type="video/mp4" />
          </video>
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-black/40 pointer-events-none" />
          <AnimatePresence>
            {isVideoHovering && !isVideoModalOpen ? (
              <motion.button
                type="button"
                className="absolute z-[3] flex w-max max-w-none pointer-events-none items-center gap-3 rounded-full border border-white/14 bg-white/16 px-4 py-3 text-white backdrop-blur-[20px] shadow-[0_20px_40px_rgba(13,28,46,0.28)]"
                style={{
                  left: videoHintPosition.x,
                  top: videoHintPosition.y,
                  x: "-50%",
                  y: "-50%",
                  transition: "left 0.1s ease-out, top 0.1s ease-out",
                }}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{
                  opacity: { duration: 0.18, ease: "easeOut" },
                  scale: { duration: 0.18, ease: "easeOut" },
                }}
                aria-label="Play demo video"
                whileTap={{ scale: 0.97 }}
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#f8f9ff] text-[#0d1c2e] shadow-[0_12px_24px_rgba(13,28,46,0.18)]">
                  <Play size={16} className="ml-0.5" fill="currentColor" />
                </span>
                <span className="flex shrink-0 flex-col items-start leading-tight font-['Inter',sans-serif]">
                  <span className="whitespace-nowrap text-sm font-semibold tracking-[0.02em]">
                    点击播放视频
                  </span>
                  <span className="whitespace-nowrap text-[11px] text-white/72">
                    在弹窗中打开演示
                  </span>
                </span>
                <span className="hidden">
                  <span className="hidden text-sm font-semibold tracking-[0.02em]">
                    任意点击播放
                  </span>
                  <span className="hidden text-[11px] text-white/72">
                    弹出窗口自动播放
                  </span>
                  <span className="text-sm font-semibold tracking-[0.02em]">
                    播放演示
                  </span>
                  <span className="text-[11px] text-white/72">
                    点击打开视频窗口
                  </span>
                </span>
              </motion.button>
            ) : null}
          </AnimatePresence>
        </motion.div>
      </div>

      <AnimatePresence>
        {isVideoModalOpen ? (
          <motion.div
            className="fixed inset-0 z-[80] bg-[#0d1c2e]/88 backdrop-blur-md flex items-center justify-center px-4 md:px-8 py-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.24, ease: "easeOut" }}
            onClick={closeVideoModal}
          >
            <motion.div
              className="relative w-full max-w-6xl rounded-[28px] overflow-hidden bg-black shadow-[0_40px_120px_rgba(13,28,46,0.58)]"
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 18, scale: 0.97 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              onClick={(event) => event.stopPropagation()}
            >
              <button
                type="button"
                onClick={closeVideoModal}
                className="absolute right-4 top-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-black/48 text-white border border-white/12 backdrop-blur-md hover:bg-black/62 transition-colors"
                aria-label="关闭视频弹窗"
              >
                <X size={20} />
              </button>
              <video
                ref={modalVideoRef}
                className="w-full max-h-[82vh] bg-black object-contain"
                controls
                autoPlay
                playsInline
                preload="auto"
              >
                <source src={demoVideoSrc} type="video/mp4" />
              </video>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
};

export const UserGuide: React.FC<UserGuideProps> = ({
  onBackToDashboard,
  onOpenLogin,
}) => {
  const [currentSection, setCurrentSection] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeNavId, setActiveNavId] = useState<GuideNavId>("overview");
  const [featureFocusIndex, setFeatureFocusIndex] = useState(0);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const lastScrollTop = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<(HTMLDivElement | null)[]>([]);
  const sectionCount = 6;

  const { scrollYProgress } = useScroll({ container: containerRef });

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    const scrollPos = containerRef.current.scrollTop + window.innerHeight / 2;

    let activeIdx = 0;
    for (let i = 0; i < sectionCount; i++) {
      const el = sectionRefs.current[i];
      if (el) {
        const { offsetTop, offsetHeight } = el;
        if (scrollPos >= offsetTop && scrollPos < offsetTop + offsetHeight) {
          activeIdx = i;
          break;
        }
      }
    }

    if (activeIdx !== currentSection) {
      setCurrentSection(activeIdx);
    }
  }, [currentSection, sectionCount]);

  // 页面切换函数
  const goToSection = useCallback((index: number) => {
    const el = sectionRefs.current[index];
    if (el && containerRef.current) {
      containerRef.current.scrollTo({
        top: el.offsetTop,
        behavior: "smooth",
      });
    }
  }, []);

  const guideNavItems = useMemo<GuideNavItem[]>(
    () => [
      { id: "overview", label: "平台概览", sectionIndex: 0 },
      { id: "demonstration", label: "功能演示", sectionIndex: 1 },
      {
        id: "capabilities",
        label: "直击痛点",
        sectionIndex: 2,
        focusCardIndex: 0,
      },
      { id: "features", label: "核心功能", sectionIndex: 3 },
      { id: "start", label: "开始体验", action: "back" },
    ],
    [],
  );

  const guidePrimaryNavItems = useMemo(
    () => guideNavItems.filter((item) => item.id !== "start"),
    [guideNavItems],
  );

  useEffect(() => {
    setActiveNavId((prev) => {
      if (currentSection === 0) return "overview";
      if (currentSection === 1) return "demonstration";
      if (currentSection === 2) return "capabilities";
      if (currentSection === 4 || currentSection === 3) return "features";

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
        goToSection(item.sectionIndex);
        return;
      }

      if (item.action === "back") {
        onBackToDashboard?.();
      }
    },
    [goToSection, onBackToDashboard],
  );

  // 页面内容组件
  const Section1 = () => {
    const ref = useRef<HTMLDivElement>(null);
    const { scrollYProgress } = useScroll({
      target: ref,
      container: containerRef,
      offset: ["start end", "end start"],
    });

    const staggerContainerVariants: Variants = {
      hidden: { opacity: 0 },
      visible: {
        opacity: 1,
        transition: { staggerChildren: 0.1, delayChildren: 0.1 },
      },
    };

    const topVariants: Variants = {
      hidden: { opacity: 0, y: -100 },
      visible: {
        opacity: 1,
        y: 0,
        transition: { type: "spring", damping: 25, stiffness: 100 },
      },
    };

    const leftVariants: Variants = {
      hidden: { opacity: 0, x: -100 },
      visible: {
        opacity: 1,
        x: 0,
        transition: { type: "spring", damping: 25, stiffness: 100 },
      },
    };

    const rightVariants: Variants = {
      hidden: { opacity: 0, x: 100 },
      visible: {
        opacity: 1,
        x: 0,
        transition: { type: "spring", damping: 25, stiffness: 100, delay: 0.2 },
      },
    };

    const bottomVariants: Variants = {
      hidden: { opacity: 0, y: 100 },
      visible: {
        opacity: 1,
        y: 0,
        transition: { type: "spring", damping: 25, stiffness: 100, delay: 0.3 },
      },
    };

    return (
      <div
        ref={ref}
        className="w-full bg-[#fcfcfc] relative overflow-hidden pt-32 pb-24 lg:pt-48 lg:pb-40 z-10 flex justify-center min-h-screen items-center font-['Inter',sans-serif]"
      >
        {/* Abstract Dot Pattern Background */}
        <div
          className="absolute inset-0 z-0 opacity-[0.15] pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(#d1d5db 2px, transparent 2px)`,
            backgroundSize: "32px 32px",
          }}
        ></div>
        {/* Blue Glow */}
        <div className="absolute top-1/2 right-1/4 w-[600px] h-[600px] z-0 pointer-events-none translate-x-1/4 -translate-y-1/2">
          <motion.div
            className="w-full h-full bg-[#60a5fa] rounded-full blur-[120px]"
            animate={{
              opacity: [0.3, 0.6, 0.3],
              scale: [1, 1.05, 1],
            }}
            transition={{
              duration: 4,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        </div>
        <div className="relative max-w-[1440px] mx-auto px-6 lg:px-16 w-full grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center z-10">
          {/* Left Content */}
          <motion.div
            variants={staggerContainerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            className="flex flex-col items-start justify-center"
          >
            <motion.h1
              variants={topVariants}
              className="text-[3.5rem] md:text-[4.5rem] lg:text-[5rem] text-[#1f2937] leading-[1.05] mb-6 -tracking-normal font-bold"
            >
              寻找最强大的
              <br className="hidden lg:block" />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#3f82ff] via-[#60a5fa] to-[#3f82ff] bg-[length:200%_auto] animate-gradient">
                智能文档
              </span>
              <span>平台</span>
            </motion.h1>

            <motion.p
              variants={leftVariants}
              className="text-lg md:text-xl text-[#4b5563] mb-12 leading-relaxed max-w-[540px]"
            >
              了解为什么顶尖企业选择我们的平台，从一个集中管理的中心快速、轻松地处理、搜索和共享文档资产，并全面掌握其流转与使用情况。
            </motion.p>

            <motion.div variants={bottomVariants}>
              <button
                onClick={() => onBackToDashboard?.()}
                className="group px-8 py-3.5 text-white rounded-md text-base hover:text-white/70 font-bold uppercase tracking-widest bg-[#3b82f6] hover:bg-[#1c4fbd] transition-all flex items-center gap-3 shadow-sm hover:shadow-md"
              >
                立即体验
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="transition-transform duration-300 ease-in-out group-hover:animate-bounce-x"
                >
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </motion.div>
          </motion.div>

          {/* Right Card */}
          <motion.div
            variants={rightVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            className="relative w-full perspective-[2000px] flex items-center justify-center lg:justify-end"
          >
            <div className="bg-white rounded-[24px] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] border border-gray-100 p-8 w-full max-w-[640px] relative z-10">
              {/* Header */}
              <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-[#1f2937] rounded-xl flex items-center justify-center overflow-hidden">
                    <svg
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path d="M12 4L4 20H20L12 4Z" fill="white" />
                    </svg>
                  </div>
                  <h3 className="text-xl font-medium text-[#1f2937]">
                    AI Impact Report
                  </h3>
                </div>
                <div className="text-sm text-gray-500 font-medium">
                  Powered by span-detect-1
                </div>
              </div>

              {/* Inner Card */}
              <div className="bg-[#fafafa] rounded-[16px] border border-gray-100 p-8">
                <div className="flex items-center justify-center gap-2 mb-10 cursor-pointer hover:text-gray-900 transition-colors group">
                  <span className="text-sm font-medium text-gray-600 group-hover:text-gray-900">
                    Baseline vs. Comparison
                  </span>
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-gray-400 group-hover:text-gray-900"
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  {/* Metric 1 */}
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                      ADOPTION
                    </span>
                    <span className="text-xs font-medium text-gray-600 mb-3">
                      AI code ratio
                    </span>
                    <div className="flex items-baseline gap-2 mb-4">
                      <span className="text-2xl font-medium text-[#16a34a]">
                        35%
                      </span>
                      <span className="text-[10px] font-bold text-[#16a34a]">
                        +6%
                      </span>
                    </div>
                  </div>

                  {/* Metric 2 */}
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                      VELOCITY
                    </span>
                    <span className="text-xs font-medium text-gray-600 mb-3">
                      PR throughput
                    </span>
                    <div className="flex items-baseline gap-2 mb-4 whitespace-nowrap">
                      <span className="text-2xl font-medium text-[#16a34a]">
                        55% <span className="text-base">faster</span>
                      </span>
                      <span className="text-[10px] font-bold text-[#16a34a]">
                        +8%
                      </span>
                    </div>
                    <div className="space-y-2 mt-2">
                      <div>
                        <div className="text-[10px] text-gray-500 mb-1">
                          Comparison
                        </div>
                        <div className="bg-[#dcfce7] text-[#166534] text-xs font-medium px-2 py-1 rounded w-fit">
                          1,258 PRS
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 mb-1">
                          Baseline
                        </div>
                        <div className="bg-gray-100 text-gray-600 text-xs font-medium px-2 py-1 rounded w-fit">
                          812 PRS
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Metric 3 */}
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                      CODE REVIEW
                    </span>
                    <span className="text-xs font-medium text-gray-600 mb-3">
                      Review cycles
                    </span>
                    <div className="flex items-baseline gap-2 mb-4 whitespace-nowrap">
                      <span className="text-2xl font-medium text-[#ea580c]">
                        17% <span className="text-base">more</span>
                      </span>
                      <span className="text-[10px] font-bold text-[#ea580c]">
                        +3%
                      </span>
                    </div>
                    <div className="space-y-2 mt-2">
                      <div>
                        <div className="text-[10px] text-gray-500 mb-1">
                          Comparison
                        </div>
                        <div className="bg-[#ffedd5] text-[#9a3412] text-xs font-medium px-2 py-1 rounded w-fit">
                          1.4
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 mb-1">
                          Baseline
                        </div>
                        <div className="bg-gray-100 text-gray-600 text-xs font-medium px-2 py-1 rounded w-fit">
                          1.2
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Metric 4 */}
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                      QUALITY
                    </span>
                    <span className="text-xs font-medium text-gray-600 mb-3 whitespace-nowrap">
                      Est. bug density
                    </span>
                    <div className="flex items-baseline gap-2 mb-4 whitespace-nowrap">
                      <span className="text-2xl font-medium text-[#dc2626]">
                        9% <span className="text-base">higher</span>
                      </span>
                      <span className="text-[10px] font-bold text-[#dc2626]">
                        +3%
                      </span>
                    </div>
                    <div className="space-y-2 mt-2">
                      <div>
                        <div className="text-[10px] text-gray-500 mb-1">AI</div>
                        <div className="bg-[#fee2e2] text-[#991b1b] text-xs font-medium px-2 py-1 rounded w-fit">
                          2.5%
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 mb-1">
                          Human
                        </div>
                        <div className="bg-gray-100 text-gray-600 text-xs font-medium px-2 py-1 rounded w-fit">
                          2.3%
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
        {/* Bottom Text */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 w-full flex justify-center pointer-events-none">
          <motion.div
            variants={bottomVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            className="text-[10px] font-bold tracking-[0.2em] text-gray-400 uppercase"
          >
            Powering many of the best engineering orgs
          </motion.div>
        </div>
      </div>
    );
  };

  const gatherContainerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.2,
      },
    },
  };

  const gatherTopVariants: Variants = {
    hidden: { opacity: 0, y: -100 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: "spring",
        damping: 25,
        stiffness: 100,
        duration: 0.5,
      },
    },
  };

  const gatherLeftVariants: Variants = {
    hidden: { opacity: 0, x: -100 },
    visible: {
      opacity: 1,
      x: 0,
      transition: {
        type: "spring",
        damping: 25,
        stiffness: 100,
        duration: 0.5,
      },
    },
  };

  const gatherBottomVariants: Variants = {
    hidden: { opacity: 0, y: 100 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: "spring",
        damping: 25,
        stiffness: 100,
        duration: 0.5,
      },
    },
  };

  const gatherRightVariants: Variants = {
    hidden: { opacity: 0, x: 100 },
    visible: {
      opacity: 1,
      x: 0,
      transition: {
        type: "spring",
        damping: 25,
        stiffness: 100,
        duration: 0.5,
      },
    },
  };

  const Section2 = () => {
    const ref = useRef<HTMLDivElement>(null);
    const { scrollYProgress } = useScroll({
      target: ref,
      container: containerRef,
      offset: ["start start", "end end"],
    });

    const [activeIndex, setActiveIndex] = useState(0);

    useEffect(() => {
      return scrollYProgress.onChange((latest) => {
        if (latest < 0.25) setActiveIndex(0);
        else if (latest < 0.75) setActiveIndex(1);
        else setActiveIndex(2);
      });
    }, [scrollYProgress]);

    const features = [
      {
        title: "还在靠人工复制粘贴填表，浪费大量人力？",
        description:
          "由于传统办公缺少自动化工具，只能手动抄录。我们平台通过自动抽取 + 自动填充，上传模板和文件即可一键生成结果，完全替代重复人工劳动。",
        image:
          "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=800&auto=format&fit=crop",
      },
      {
        title: "处理不同格式文档需要切换一堆软件，效率极低？",
        description:
          "我们平台提供了全格式一站式能力，只需一个模块便可以支持 Word/PDF/TXT/MD/CSV/XLSX/ 图片全格式，覆盖转换、识别、分析、编辑。",
        image:
          "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=800&auto=format&fit=crop",
      },
      {
        title: "检查填写结果要下载？",
        description:
          "我们平台支持预览填写后的文件，极大地节省了用户的时间，简化了繁琐的操作。",
        image:
          "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?q=80&w=800&auto=format&fit=crop",
      },
    ];

    return (
      <div className="w-full relative bg-white z-20 flex flex-col items-center my-36">
        {/* 背景：点阵底纹 */}
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:24px_24px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_70%,transparent_100%)] opacity-70" />
        </div>

        {/* 标题部分 */}
        <motion.h1
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={gatherTopVariants}
          className="text-3xl md:text-[2.5rem] lg:text-5xl text-[#094067] leading-[1.1] text-center pb-12 lg:pb-10 tracking-tighter font-bold relative z-10"
        >
          项目应用，直击社会痛点
        </motion.h1>

        {/* Desktop: 联动叙事布局 */}
        <div
          ref={ref}
          className="hidden lg:flex w-full max-w-[1440px] px-12 relative z-10 items-start justify-between gap-16 xl:gap-24"
        >
          {/* 左侧：粘性固定图片 (45%) */}
          <div className="sticky top-0 h-screen w-[45%] flex flex-col justify-center py-20">
            {/* 玻璃态展架容器 (Glassmorphism Frame) - 缩小最大高度和整体缩放 */}
            <div className="relative w-full aspect-square max-h-[70vh] rounded-[3rem] bg-slate-50/50 backdrop-blur-2xl border border-white/20 isolate overflow-hidden mx-auto">
              {/* 底层动态环境光 (基于原图提取的真实光晕) */}
              <div className="absolute inset-0 -z-10 pointer-events-none overflow-hidden rounded-[3rem]">
                {features.map((feature, i) => (
                  <motion.div
                    key={`glow-${i}`}
                    initial={false}
                    animate={{ opacity: activeIndex === i ? 0.4 : 0 }}
                    transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
                    className="absolute inset-0"
                  >
                    {/* 直接复用原图，配合 scale、blur 和 saturate 形成完美的动态环境光 */}
                    <img
                      src={feature.image}
                      alt=""
                      className="w-full h-full object-cover blur-[80px] md:blur-[100px] scale-[1.5] saturate-150"
                    />
                  </motion.div>
                ))}
              </div>

              {/* 预加载所有图片，确保切换时不卡顿 */}
              <div className="hidden">
                {features.map((feature, i) => (
                  <link
                    key={`preload-${i}`}
                    rel="preload"
                    as="image"
                    href={feature.image}
                  />
                ))}
              </div>

              {/* 悬浮双层边框影像容器 (Double-layered Floating Image) - 定位在右下角形成溢出裁切 */}
              <div className="absolute top-10 left-10 md:top-14 md:left-14 lg:top-15 lg:left-20 w-full h-full rounded-[2rem] md:rounded-[2.5rem] p-2 md:p-3 bg-white/40 backdrop-blur-2xl border-[2px] border-white/80 shadow-[-20px_-20px_60px_-15px_rgba(0,0,0,0.15)] isolate transition-transform duration-700 ease-out hover:scale-[1.02]">
                {/* 内层内容容器 */}
                <div className="relative w-full h-full rounded-2xl md:rounded-[2rem] overflow-hidden bg-white ring-1 ring-black/5 shadow-inner isolate group">
                  {/* 层叠式布局：使用 Framer Motion 的 animate 动态控制 opacity，消除剧烈形变 */}
                  {features.map((feature, i) => (
                    <motion.img
                      key={i}
                      src={feature.image}
                      alt={feature.title}
                      loading="eager"
                      initial={false}
                      animate={{
                        opacity: activeIndex === i ? 1 : 0,
                        scale: activeIndex === i ? 1 : 1.02,
                      }}
                      transition={{
                        duration: 0.8,
                        ease: [0.22, 1, 0.36, 1],
                        // 让当前图片立即开始显示，非当前图片延迟消失，形成交叉淡入淡出消除白闪
                        opacity: {
                          delay: activeIndex === i ? 0 : 0.1,
                          duration: 0.8,
                          ease: [0.22, 1, 0.36, 1],
                        },
                      }}
                      className="absolute inset-0 w-full h-full object-cover origin-center transition-transform duration-700 ease-out group-hover:scale-[1.05]"
                      style={{
                        willChange: "opacity, transform",
                        zIndex: activeIndex === i ? 10 : 1, // 确保当前激活层在最上，同时非激活层不会立刻掉到底部
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 右侧：滚动文本块 (50%) */}
          <div className="w-[45%] flex flex-col relative">
            {features.map((feature, i) => (
              <div
                key={i}
                className="h-screen flex flex-col justify-center py-20 relative"
              >
                {/* 顶部分割线（除第一个块外） */}
                {i > 0 && (
                  <div className="absolute top-0 left-8 md:left-16 right-8 h-[1px] bg-gray-200/80" />
                )}

                <motion.div
                  initial={false}
                  animate={{
                    opacity: activeIndex === i ? 1 : 0.2,
                    y: activeIndex === i ? 0 : 20,
                  }}
                  transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  className="pl-8 md:pl-16 pr-8 transition-all duration-500"
                >
                  <h3 className="text-3xl lg:text-[2.75rem] text-[#111827] mb-6 leading-[1.2] tracking-wide font-normal">
                    {feature.title}
                  </h3>
                  <p className="text-lg lg:text-[1.125rem] text-[#4b5563] leading-[1.6] tracking-wide">
                    {feature.description}
                  </p>
                </motion.div>
              </div>
            ))}
          </div>
        </div>

        {/* Mobile: 普通垂直堆叠 */}
        <div className="lg:hidden w-full px-6 flex flex-col gap-12 relative z-10 pb-20">
          {features.map((feature, i) => (
            <motion.div
              key={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-100px" }}
              variants={gatherContainerVariants}
              className="w-full bg-[#eff4ff] rounded-2xl shadow-xl overflow-hidden flex flex-col border border-white/40"
            >
              <div className="h-64 sm:h-80 relative overflow-hidden">
                <img
                  src={feature.image}
                  className="w-full h-full object-cover"
                  alt={feature.title}
                />
              </div>
              <div className="p-8 flex flex-col">
                <h3 className="text-2xl font-bold text-[#0d1c2e] mb-4 leading-tight tracking-tighter">
                  {feature.title}
                </h3>
                <p className="text-[#434655] text-base leading-relaxed">
                  {feature.description}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    );
  };

  const SectionFeatures = () => {
    const ref = useRef<HTMLDivElement>(null);
    const { scrollYProgress } = useScroll({
      target: ref,
      container: containerRef,
      offset: ["start end", "end start"],
    });

    return (
      <div
        ref={ref}
        className="w-full relative flex flex-col items-center py-16 lg:pb-40 lg:pt-30 gap-20 lg:gap-32 overflow-hidden z-30 bg-white"
      >
        {/* Diffused Halo Background */}
        <div className="absolute inset-x-0 top-0 h-[30%] z-0 pointer-events-none">
          {/* Top-left soft blue glow */}
          <div className="absolute top-[-10%] left-[20%] w-[60%] h-[50%] bg-[#dbe8ff] rounded-[100%] mix-blend-multiply filter blur-[140px] opacity-70 transform rotate-12" />
          {/* Top-right soft purple glow */}
          <div className="absolute top-[0%] right-[20%] w-[50%] h-[40%] bg-[#efe8ff] rounded-[100%] mix-blend-multiply filter blur-[140px] opacity-70 transform -rotate-12" />
          {/* Diagonal light from top-center */}
          <div className="absolute top-[5%] left-[20%] w-[60%] h-[50%] bg-[#f4f8ff] rounded-[100%] filter blur-[120px] opacity-80 transform -rotate-12" />
        </div>

        <motion.h1
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={gatherTopVariants}
          className="text-3xl md:text-[2.5rem] lg:text-5xl text-[#094067] leading-[1.1] center z-10 tracking-wide font-bold"
        >
          <span className="relative inline-block">
            特色功能，解决大部分
            <span className="bg-gradient-to-r from-[#9497ff] to-[#e995f8] bg-clip-text text-transparent">
              问题
            </span>
            {/* 高光装饰容器 */}
            <div className="absolute top-[-8px] right-[4px] md:top-[-10px] md:right-[4px] lg:top-[-14px] lg:right-[6px] pointer-events-none scale-90 md:scale-110 lg:scale-150 origin-bottom rotate-[45deg]">
              {/* 线条 1 (最左) */}
              <div className="w-[3px] h-2.5 bg-gradient-to-b from-[#6366F1] to-[#D946EF] -rotate-[30deg] rounded-full origin-bottom-left" />
              {/* 线条 2 (中间，稍长) */}
              <div className="absolute top-[-5px] left-2 w-[3px] h-3 bg-gradient-to-b from-[#6366F1] to-[#D946EF] rounded-full" />
              {/* 线条 3 (最右) */}
              <div className="absolute top-[-2px] left-4 w-[3px] h-2.5 bg-gradient-to-b from-[#6366F1] to-[#D946EF] rotate-[40deg] rounded-full origin-bottom-left" />
            </div>
          </span>
        </motion.h1>

        {/* Feature 1: Search */}
        <div className="relative z-10 w-full max-w-[1440px] px-6 lg:px-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Image Left */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherLeftVariants}
            className="order-1 lg:order-1 h-[400px] lg:h-[500px] w-full rounded-2xl overflow-hidden shadow-2xl border border-[#d1d1e9] flex items-center justify-center bg-[#eff4ff] p-6"
          >
            <img
              src={deepreadWorkbenchImage}
              className="w-full h-full object-cover"
              alt="智能文档解析"
            />
          </motion.div>
          {/* Text Right */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherRightVariants}
            className="order-2 lg:order-2 flex flex-col items-start space-y-6 pl-0 lg:pl-12"
          >
            <div className="flex items-center gap-2 text-[#0058be] font-semibold tracking-[0.05em] uppercase text-sm font-['Inter',sans-serif]">
              <span className="w-8 h-[2px] bg-[#0058be]" />
              核心功能
            </div>
            <h2 className="text-4xl md:text-5xl font-bold text-[#0d1c2e] leading-tight font-['Inter',sans-serif] tracking-[-0.02em]">
              智能文档解析
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              支持 PDF / DOCX / XLSX / TXT / MD
              多格式文档批量上传，按自定义字段规则自动完成结构化抽取，并返回字段值、置信度和来源定位。
            </p>
          </motion.div>
        </div>

        {/* Feature 2: Share */}
        <div className="relative z-10 w-full max-w-[1440px] px-6 lg:px-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Text Left */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherLeftVariants}
            className="order-2 lg:order-1 flex flex-col items-start space-y-6 pr-0 lg:pr-12"
          >
            <div className="flex items-center gap-2 text-[#0058be] font-semibold tracking-[0.05em] uppercase text-sm font-['Inter',sans-serif]">
              <span className="w-8 h-[2px] bg-[#0058be]" />
              核心功能
            </div>
            <h2 className="text-4xl md:text-5xl font-bold text-[#0d1c2e] leading-tight font-['Inter',sans-serif] tracking-[-0.02em]">
              模板回填
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              支持上传一个模板和一组资料文档，自动识别模板字段，从多份文档中匹配候选答案并回填到
              Excel 或 Word，生成可预览、可下载的结果文件。
            </p>
          </motion.div>
          {/* Image Right */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherRightVariants}
            className="order-1 lg:order-2 h-[400px] lg:h-[500px] w-full rounded-2xl overflow-hidden shadow-2xl border border-[#d1d1e9] flex items-center justify-center bg-[#eff4ff] p-6"
          >
            <img
              src={documentFlowImage}
              className="w-full h-full object-cover"
              alt="模板回填"
            />
          </motion.div>
        </div>

        {/* Feature 3: Self Service */}
        <div className="relative z-10 w-full max-w-[1440px] px-6 lg:px-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Image Left */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherLeftVariants}
            className="order-1 lg:order-1 h-[400px] lg:h-[500px] w-full rounded-2xl overflow-hidden shadow-2xl border border-[#d1d1e9] flex items-center justify-center bg-[#eff4ff] p-6"
          >
            <img
              src={knowledgeGraphImage}
              className="w-full h-full object-cover"
              alt="知识图谱"
            />
          </motion.div>
          {/* Text Right */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherRightVariants}
            className="order-2 lg:order-2 flex flex-col items-start space-y-6 pl-0 lg:pl-12"
          >
            <div className="flex items-center gap-2 text-[#0058be] font-semibold tracking-[0.05em] uppercase text-sm font-['Inter',sans-serif]">
              <span className="w-8 h-[2px] bg-[#0058be]" />
              核心功能
            </div>
            <h2 className="text-4xl md:text-5xl font-bold text-[#0d1c2e] leading-tight font-['Inter',sans-serif] tracking-[-0.02em]">
              知识图谱
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              把文档、字段、风险和证据组织成可视化关系网络，帮助用户从“单篇文档抽取”升级到“跨对象关联分析”。
            </p>
          </motion.div>
        </div>
      </div>
    );
  };

  const SectionCTA = () => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
    const [isH2TypingComplete, setIsH2TypingComplete] = useState(false);
    const [isPTypingComplete, setIsPTypingComplete] = useState(false);

    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();

      // Calculate mouse position relative to the center of the text container
      // This ensures the radial gradient center exactly matches the cursor tip
      setMousePosition({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    };

    return (
      <div className="w-full mt-20 flex justify-center bg-white relative z-40 flex-1">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={gatherBottomVariants}
          className="relative w-full bg-gradient-to-b from-[#f2f6ff] via-[#f9fbff] to-white overflow-hidden flex flex-col items-center justify-center text-center pt-16 md:pt-24 px-6 border border-[#f0f4f8] pb-[100px] md:pb-[160px] xl:pb-[180px] 2xl:pb-[220px] cursor-default"
        >
          {/* Floating Document Icons */}
          {[
            {
              Icon: FileText,
              color: "text-blue-400",
              size: 48,
              top: "15%",
              left: "10%",
              delay: 0,
            },
            {
              Icon: FileSpreadsheet,
              color: "text-emerald-400",
              size: 56,
              top: "45%",
              left: "5%",
              delay: 1.5,
            },
            {
              Icon: FileCode,
              color: "text-purple-400",
              size: 40,
              top: "20%",
              right: "12%",
              delay: 0.5,
            },
            {
              Icon: FileImage,
              color: "text-amber-400",
              size: 52,
              top: "60%",
              right: "8%",
              delay: 2,
            },
            {
              Icon: File,
              color: "text-red-400",
              size: 44,
              top: "75%",
              left: "15%",
              delay: 1,
            },
            {
              Icon: FileText,
              color: "text-indigo-400",
              size: 36,
              top: "30%",
              right: "25%",
              delay: 2.5,
            },
            {
              Icon: FileSpreadsheet,
              color: "text-green-400",
              size: 32,
              top: "70%",
              right: "18%",
              delay: 0.8,
            },
            {
              Icon: FileText,
              color: "text-sky-300",
              size: 64,
              top: "10%",
              left: "30%",
              delay: 1.2,
            },
          ].map((item, idx) => (
            <motion.div
              key={idx}
              className={cn(
                "absolute opacity-20 pointer-events-none z-0",
                item.color,
              )}
              style={{ top: item.top, left: item.left, right: item.right }}
              animate={{
                y: [0, -15, 0],
                rotate: [-5, 5, -5],
              }}
              transition={{
                duration: 6,
                repeat: Infinity,
                ease: "easeInOut",
                delay: item.delay,
              }}
            >
              <item.Icon size={item.size} strokeWidth={1.5} />
            </motion.div>
          ))}

          {/* Background Text Watermark (Flashlight Effect) */}
          <div
            ref={containerRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setMousePosition({ x: -1000, y: -1000 })}
            className="absolute inset-x-0 bottom-0 translate-y-[45%] md:translate-y-[35%] flex items-center justify-center select-none z-0 overflow-hidden w-full pointer-events-auto h-[40vw] max-h-[600px]"
          >
            <h1 className="relative text-[20vw] leading-none font-bold tracking-tighter whitespace-nowrap cursor-default origin-bottom w-full h-full flex items-center justify-center">
              {/* 底层文字：只有轮廓，浅灰色 */}
              <span className="inline-block text-[#cdcdcd53]">SmartDoc</span>

              {/* 上层文字：手电筒高亮效果 */}
              <span
                className="absolute left-0 top-0 w-full h-full inline-flex items-center justify-center bg-clip-text text-transparent bg-[#86b4ff] pointer-events-none"
                style={{
                  WebkitMaskImage: `radial-gradient(circle 5vw at ${mousePosition.x}px ${mousePosition.y}px, black 0%, transparent 100%)`,
                  maskImage: `radial-gradient(circle 5vw at ${mousePosition.x}px ${mousePosition.y}px, black 0%, transparent 100%)`,
                  WebkitMaskSize: "100% 100%",
                  maskSize: "100% 100%",
                  WebkitMaskRepeat: "no-repeat",
                  maskRepeat: "no-repeat",
                }}
              >
                SmartDoc
              </span>
            </h1>
          </div>

          {/* Content */}
          <div className="relative z-10 flex flex-col items-center pt-0 md:pt-4">
            <motion.h2
              className="text-4xl md:text-5xl lg:text-6xl font-bold text-[#0d1c2e] mb-8 tracking-tight font-['Inter',sans-serif] min-h-[1.5em] flex items-center justify-center"
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-50px" }}
              onAnimationComplete={() => setIsH2TypingComplete(true)}
              variants={{
                hidden: { opacity: 1 },
                visible: {
                  opacity: 1,
                  transition: {
                    staggerChildren: 0.2,
                  },
                },
              }}
            >
              {"开启智能文档流转之旅".split("").map((char, index) => (
                <motion.span
                  key={index}
                  variants={{
                    hidden: { opacity: 0, display: "none" },
                    visible: { opacity: 1, display: "inline-block" },
                  }}
                >
                  {char}
                </motion.span>
              ))}
              <motion.span
                className="inline-block w-[3px] md:w-[4px] lg:w-[5px] h-[0.9em] bg-[#3b82f6] ml-2 lg:ml-3 rounded-sm overflow-hidden origin-bottom"
                initial={{ opacity: 0 }}
                animate={
                  isH2TypingComplete
                    ? {
                        opacity: 0,
                        width: 0,
                        marginLeft: 0,
                        transition: { duration: 0.3, ease: "easeOut" },
                      }
                    : {
                        opacity: [1, 0, 1],
                        transition: {
                          repeat: Infinity,
                          duration: 0.8,
                          ease: "easeInOut",
                        },
                      }
                }
              />
            </motion.h2>

            <div className="inline-flex flex-col items-center justify-center relative mb-10 min-h-[46px] md:min-h-[50px]">
              <div className="absolute inset-0 bg-white/60 backdrop-blur-md rounded-full shadow-[0_0_20px_rgba(255,255,255,0.8)] -z-10"></div>
              <motion.p
                className="text-[#434655] text-sm md:text-base max-w-lg rounded-full px-8 py-3 border border-white relative z-10 font-medium whitespace-nowrap text-center flex items-center justify-center"
                initial="hidden"
                animate={isH2TypingComplete ? "visible" : "hidden"}
                onAnimationComplete={() => setIsPTypingComplete(true)}
                variants={{
                  hidden: { opacity: 1 },
                  visible: {
                    opacity: 1,
                    transition: {
                      staggerChildren: 0.05,
                    },
                  },
                }}
              >
                {"准备好提升团队效率了吗？立即体验智能文档流转平台，开启高效工作"
                  .split("")
                  .map((char, index) => (
                    <motion.span
                      key={index}
                      variants={{
                        hidden: { opacity: 0, display: "none" },
                        visible: { opacity: 1, display: "inline-block" },
                      }}
                    >
                      {char}
                    </motion.span>
                  ))}
                <motion.span
                  className="inline-block w-[2px] md:w-[3px] h-[1em] bg-[#3b82f6] ml-1 rounded-sm overflow-hidden origin-bottom"
                  initial={{ opacity: 0 }}
                  animate={
                    isPTypingComplete
                      ? {
                          opacity: 0,
                          width: 0,
                          marginLeft: 0,
                          transition: { duration: 0.3, ease: "easeOut" },
                        }
                      : isH2TypingComplete
                        ? {
                            opacity: [1, 0, 1],
                            transition: {
                              repeat: Infinity,
                              duration: 0.8,
                              ease: "easeInOut",
                            },
                          }
                        : { opacity: 0 }
                  }
                />
              </motion.p>
            </div>

            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => {
                  if (onOpenLogin) {
                    onOpenLogin();
                    return;
                  }
                  onBackToDashboard?.();
                }}
                className="px-6 py-2.5 rounded-full bg-white text-[#0d1c2e] font-semibold border border-[#e2e8f0] shadow-sm hover:bg-gray-50 transition-all text-sm h-[44px]"
              >
                登录账号
              </button>
              <button
                onClick={() => onBackToDashboard?.()}
                className="px-6 py-2.5 rounded-full bg-[#3b82f6] text-white font-semibold shadow-[0_4px_14px_0_rgba(59,130,246,0.39)] hover:bg-[#86b4ff] transition-all text-sm h-[44px]"
              >
                立即开始
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    );
  };

  const sections = [
    { render: Section1, wrapperClassName: "min-h-0" },
    {
      render: () => (
        <GuideSectiondemonstration
          containerRef={containerRef}
          currentSection={currentSection}
        />
      ),
    },
    { render: Section2, wrapperClassName: "min-h-0" },
    { render: SectionFeatures, wrapperClassName: "min-h-0" },
    { render: SectionCTA, wrapperClassName: "min-h-0" },
  ];

  return (
    <div className="relative h-screen w-full overflow-hidden bg-white">
      {/* 导航栏 */}
      <motion.nav
        className="fixed left-0 right-0 z-50 bg-[#f8f9ff]/70 backdrop-blur-md shadow-sm border-b border-[#d5e3fc] overflow-hidden font-['Inter',sans-serif]"
        initial={{ top: 0, height: 72 }}
        animate={{
          top: navCollapsed ? -72 : 0,
          height: navCollapsed ? 0 : 72,
        }}
        transition={{
          type: "spring",
          stiffness: 300,
          damping: 30,
          duration: 0.3,
        }}
      >
        <div className="w-full h-full px-6 lg:px-10 flex items-center justify-between text-[#0d1c2e]">
          <div
            className="flex items-center gap-6 xl:gap-10 cursor-pointer"
            onClick={() => handleGuideNavClick(guideNavItems[0])}
          >
            <div className="text-xl md:text-2xl font-bold tracking-tight flex items-center whitespace-nowrap">
              <span className="hidden md:inline-block text-[#0d1c2e] ml-38">
                智能文档流转平台
              </span>
              <span className="md:hidden text-[#0d1c2e]">SmartDoc</span>
            </div>
          </div>
          <div className="hidden lg:flex items-center justify-end gap-6 xl:gap-10 font-medium text-[17px] ml-auto mr-35">
            <div className="relative flex items-center gap-2 xl:gap-4">
              {guidePrimaryNavItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleGuideNavClick(item)}
                  className={cn(
                    "cursor-pointer transition-colors relative whitespace-nowrap px-4 py-2 rounded-lg",
                    activeNavId === item.id
                      ? "bg-[#d5e3fc] text-[#0d1c2e] font-semibold"
                      : "text-[#434655] hover:bg-[#eff4ff] hover:text-[#0d1c2e]",
                  )}
                >
                  <span className="inline-block">{item.label}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() =>
                handleGuideNavClick(
                  guideNavItems.find((item) => item.id === "start") ??
                    guideNavItems[guideNavItems.length - 1],
                )
              }
              className="ml-2 px-6 py-2 bg-[#0058be] text-white rounded-full font-bold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 active:scale-95"
            >
              {guideNavItems.find((item) => item.id === "start")?.label}
            </button>
          </div>
          <button
            className="lg:hidden p-2 text-[#0d1c2e]"
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
              <div className="rounded-2xl bg-[#eff4ff] border border-[#d5e3fc] p-3 flex flex-col gap-1 shadow-inner">
                {guideNavItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleGuideNavClick(item)}
                    className={cn(
                      "w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition-colors",
                      activeNavId === item.id
                        ? "bg-[#d5e3fc] text-[#0d1c2e]"
                        : "text-[#434655] hover:bg-[#d5e3fc]/50",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.nav>

      {/* 页面内容 */}
      <div
        ref={containerRef}
        className="relative h-full w-full overflow-y-auto overflow-x-hidden"
        onScroll={handleScroll}
      >
        {sections.map((section, idx) => {
          return (
            <div
              key={idx}
              ref={(el) => {
                sectionRefs.current[idx] = el;
              }}
              className={cn(
                "relative w-full flex flex-col",
                section.wrapperClassName ?? "min-h-screen",
              )}
            >
              <div
                className="flex-1 w-full flex flex-col"
                style={{ backgroundColor: "transparent" }}
              >
                {section.render()}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
