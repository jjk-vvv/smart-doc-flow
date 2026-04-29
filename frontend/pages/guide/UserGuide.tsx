import React, {
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
  FileText,
  FileSpreadsheet,
  FileCode,
  FileImage,
  File,
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  motion,
  AnimatePresence,
  useScroll,
  useTransform,
  type TargetAndTransition,
  type Variants,
} from "framer-motion";

import guideLogo from "../../assets/app-logo.png";
import section1MainImage from "../../assets/首页.png";
import video from "../../assets/宣传视频.mp4";
import sec2_1 from "../../assets/痛点1.png";
import sec2_2 from "../../assets/痛点2.png";
import sec2_3 from "../../assets/痛点3.png";
import sec2_4 from "../../assets/痛点4.png";
import secfea_2Left from "../../assets/功能2左.png";
import secfea_2Right from "../../assets/功能2右.png";
import secfea_3 from "../../assets/功能3.png";
import secfea_4 from "../../assets/功能4.png";
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const featureExcelFileName = "2025年国考职位表（节选）.xlsx";

const featureSuggestionItems = [
  { label: "指标总览", type: "overview" },
  { label: "异常数据", type: "alert" },
  { label: "汇总统计", type: "summary" },
  { label: "趋势变化", type: "trend" },
  { label: "关键字段", type: "field" },
  { label: "结论表", type: "table" },
] as const;

const featureExtractionStats = [
  { label: "字段", value: "17", className: "text-[#3866d6]" },
  { label: "表格", value: "21", className: "text-[#17966b]" },
  { label: "图片", value: "6", className: "text-[#c9852c]" },
] as const;

const featureExtractionFields = [
  { label: "居民消费价格涨幅", value: "0.4", page: "页 2", confidence: "99%" },
  { label: "绝对值", value: "56987.55", page: "页 5", confidence: "94%" },
  { label: "比上年末增长", value: "10.8", page: "页 25", confidence: "94%" },
  { label: "常住人口城镇化率", value: "87.3", page: "页 1", confidence: "90%" },
  { label: "统计年份", value: "2024", page: "页 1", confidence: "98%" },
  { label: "常住人口", value: "957.7", page: "页 1", confidence: "90%" },
  {
    label: "新增就业（城市）",
    value: "21.94",
    page: "页 1",
    confidence: "90%",
  },
] as const;

const featureExtractionTableRows = [
  { name: "卷烟", unit: "万支", year: "347742", growth: "3.2" },
  { name: "乙烯", unit: "吨", year: "1407390", growth: "3.9" },
  { name: "化学纤维", unit: "吨", year: "119854", growth: "18.8" },
  { name: "塑料制品", unit: "吨", year: "177453", growth: "5.1" },
  { name: "水泥", unit: "吨", year: "3942301", growth: "-28.7" },
  { name: "生铁", unit: "吨", year: "17732522", growth: "0.5" },
] as const;

const FeatureExcelFilePill: React.FC<{ tone?: "blue" | "light" }> = ({
  tone = "light",
}) => (
  <div
    className={cn(
      "inline-flex max-w-full items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold lg:text-base",
      tone === "blue"
        ? "bg-white/[0.13] text-white shadow-[0_10px_30px_rgba(24,58,150,0.18)]"
        : "bg-[#f3f8ff] text-[#435a72]",
    )}
  >
    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] bg-[#35c978] text-white shadow-[0_4px_12px_rgba(53,201,120,0.28)]">
      <FileSpreadsheet className="h-3 w-3" />
    </span>
    <span className="truncate">{featureExcelFileName}</span>
  </div>
);

const FeatureSuggestionIcon: React.FC<{
  type: (typeof featureSuggestionItems)[number]["type"];
}> = ({ type }) => {
  if (type === "summary") {
    return (
      <span className="flex h-5 w-5 shrink-0 flex-col justify-center gap-0.5">
        <span className="h-[2px] w-4 rounded-full bg-current" />
        <span className="h-[2px] w-5 rounded-full bg-current" />
        <span className="h-[2px] w-3 rounded-full bg-current" />
      </span>
    );
  }

  if (type === "trend") {
    return (
      <span className="relative h-5 w-5 shrink-0">
        <span className="absolute bottom-1 left-0 h-[2px] w-3 rotate-[-35deg] rounded-full bg-current" />
        <span className="absolute right-0 top-1 h-[2px] w-3 rotate-[35deg] rounded-full bg-current" />
        <span className="absolute right-0 top-1 h-1.5 w-1.5 rounded-sm border-r-2 border-t-2 border-current" />
      </span>
    );
  }

  if (type === "field") {
    return (
      <span className="relative h-5 w-5 shrink-0 rounded-[5px] border-2 border-current">
        <span className="absolute -right-1.5 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-white" />
        <span className="absolute -left-1.5 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-white" />
      </span>
    );
  }

  if (type === "table") {
    return <FileText className="h-5 w-5 shrink-0" />;
  }

  return (
    <span className="relative h-5 w-5 shrink-0 rounded-full border-2 border-current">
      <span
        className={cn(
          "absolute left-1/2 top-1/2 block -translate-x-1/2 -translate-y-1/2 rounded-full bg-current",
          type === "alert" ? "h-2.5 w-[2px]" : "h-3 w-3",
        )}
      />
      {type === "alert" && (
        <span className="absolute bottom-0.5 left-1/2 h-[2px] w-[2px] -translate-x-1/2 rounded-full bg-current" />
      )}
    </span>
  );
};

const FeatureSuggestionButton: React.FC<{
  item: (typeof featureSuggestionItems)[number];
}> = ({ item }) => (
  <button
    type="button"
    className="flex h-9 items-center justify-center gap-2 rounded-full border border-[#e2ebfa] bg-white/[0.82] px-3 text-sm font-semibold text-[#4a627a] shadow-[0_8px_18px_-16px_rgba(13,28,46,0.7)] transition-colors hover:border-[#bad6ff] hover:bg-[#f8fbff] lg:text-base"
  >
    <FeatureSuggestionIcon type={item.type} />
    <span>{item.label}</span>
  </button>
);

const FeatureBusinessConclusionMockup: React.FC = () => (
  <div className="relative h-full w-full overflow-hidden rounded-[34px] border border-[#dde8fb] bg-[radial-gradient(circle_at_12%_10%,rgba(219,234,254,0.86),transparent_34%),linear-gradient(145deg,#ffffff_0%,#f8fbff_48%,#eef6ff_100%)] p-4 shadow-[0_26px_80px_-36px_rgba(37,99,235,0.5)] lg:p-5">
    <div className="flex h-full flex-col justify-between gap-4">
      <div className="ml-auto w-[86%] rounded-[28px] bg-[#2f61e8] px-5 py-4 text-white shadow-[0_24px_52px_-24px_rgba(47,97,232,0.82)] lg:px-6 lg:py-5">
        <p className="text-[17px] font-semibold leading-[1.48] tracking-[0.03em] lg:text-[21px]">
          基于《2025年国考职位表（节选）.xlsx》的数据
          <br />
          给我一个简明业务结论
        </p>
        <div className="mt-3 lg:mt-4">
          <FeatureExcelFilePill tone="blue" />
        </div>
      </div>

      <div className="w-[88%] rounded-[28px] border border-[#dfe8f7] bg-white/[0.96] px-4 py-4 shadow-[0_22px_56px_-34px_rgba(13,28,46,0.52)] lg:px-5 lg:py-5">
        <p className="text-[17px] font-medium leading-[1.5] tracking-[0.01em] text-[#2e3c51] lg:text-[20px]">
          我将基于《2025年国考职位表（节选）.xlsx》的
          <br />
          数据生成一个简明业务结论。
        </p>
        <div className="mt-3">
          <FeatureExcelFilePill />
        </div>

        <div className="mt-4 rounded-[24px] border border-[#e2ebfa] bg-white/[0.86] p-3 shadow-[0_16px_36px_-32px_rgba(13,28,46,0.48)] lg:p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-bold tracking-[0.18em] text-[#52677f] lg:text-base">
              <span className="text-[#2f61e8]">✦</span>
              猜你想问
            </div>
            <button
              type="button"
              className="rounded-full border border-[#dce8fa] bg-white px-3 py-1 text-xs font-semibold text-[#49627a] shadow-[0_8px_18px_-16px_rgba(13,28,46,0.7)] lg:text-sm"
            >
              ↻ 换一批
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-3">
            {featureSuggestionItems.map((item) => (
              <FeatureSuggestionButton key={item.label} item={item} />
            ))}
          </div>
        </div>
      </div>
    </div>
  </div>
);

const FeatureExtractionFieldCard: React.FC<{
  item: (typeof featureExtractionFields)[number];
}> = ({ item }) => (
  <div className="rounded-[16px] border border-[#e8edf5] bg-white px-4 py-3 shadow-[0_12px_30px_-26px_rgba(13,28,46,0.55)]">
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="inline-flex max-w-full rounded-full bg-[#f4f7fb] px-3 py-1 text-xs font-semibold text-[#526477]">
          <span className="truncate">{item.label}</span>
        </div>
        <div className="mt-2 text-lg font-medium leading-none text-[#1e293b]">
          {item.value}
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2">
        <span className="rounded-[7px] border border-[#e2e8f0] bg-white px-2 py-1 text-xs font-semibold text-[#64748b]">
          {item.page}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-[#bdebd8] bg-[#ecfdf5] px-2 py-1 text-xs font-bold text-[#15956c]">
          <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-current text-[9px] leading-none">
            ✓
          </span>
          {item.confidence}
        </span>
      </div>
    </div>
  </div>
);

const FeatureExtractionSourceCard: React.FC = () => (
  <div className="relative h-full w-full overflow-hidden rounded-2xl border border-[#dfe6ef] bg-white/[0.98] shadow-[0_22px_55px_-24px_rgba(13,28,46,0.4)] backdrop-blur">
    <div className="grid h-9 grid-cols-[1.4fr_0.85fr_1fr_1fr] items-center border-b border-[#d8dee7] bg-[#f7f9fc] px-3 text-[11px] font-bold text-[#334155]">
      <div>产品名称</div>
      <div>计量单位</div>
      <div>2024 年</div>
      <div>比上年增长（%）</div>
    </div>

    <div className="divide-y divide-[#edf1f6]">
      {featureExtractionTableRows.map((row) => (
        <div
          key={row.name}
          className="grid h-[29px] grid-cols-[1.4fr_0.85fr_1fr_1fr] items-center px-3 text-[11px] text-[#334155]"
        >
          <div className="truncate font-medium">{row.name}</div>
          <div className="truncate">{row.unit}</div>
          <div className="truncate tabular-nums">{row.year}</div>
          <div className="truncate tabular-nums">{row.growth}</div>
        </div>
      ))}
    </div>

    <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white to-white/0" />
  </div>
);

const FeatureExtractionMockup: React.FC = () => (
  <div className="h-full w-full overflow-hidden rounded-[24px] border border-[#dfe8f5] bg-[#fbfdff] shadow-[0_24px_70px_-34px_rgba(13,28,46,0.42)]">
    <div className="flex h-11 items-center justify-between border-b border-[#e8eef7] bg-white px-4">
      <div className="flex items-center gap-2 text-sm font-bold text-[#2d3b4d]">
        <span className="relative h-4 w-4 rounded-full border border-[#9aaabe]">
          <span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#9aaabe]" />
        </span>
        原文定位
      </div>

      <div className="flex items-center gap-3">
        {featureExtractionStats.map((item) => (
          <span
            key={item.label}
            className={cn(
              "rounded-full bg-[#f7f9fc] px-3 py-1 text-xs font-bold",
              item.className,
            )}
          >
            {item.label} {item.value}
          </span>
        ))}
      </div>
    </div>

    <div className="h-[calc(100%-44px)] px-3 py-3">
      <div className="mb-3 inline-flex rounded-[8px] bg-[#f3f6fb] px-3 py-1.5 text-sm font-bold text-[#526477]">
        字段
      </div>

      <div className="grid h-[calc(100%-42px)] content-start gap-2.5 overflow-hidden">
        {featureExtractionFields.map((item) => (
          <FeatureExtractionFieldCard key={item.label} item={item} />
        ))}
      </div>
    </div>
  </div>
);

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

interface UserGuideProps {
  onBackToDashboard?: () => void;
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
  const demoVideoSrc = video;

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

export const UserGuide: React.FC<UserGuideProps> = ({ onBackToDashboard }) => {
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
              <motion.span
                className="inline-block text-transparent bg-clip-text drop-shadow-[0_0_22px_rgba(96,165,250,0.34)]"
                style={{
                  backgroundImage:
                    "linear-gradient(90deg, #2563eb 0%, #3b82f6 45%, #2563eb 100%), radial-gradient(circle at 28% 46%, #ffffff 0%, rgba(240,249,255,1) 10%, rgba(147,197,253,0.96) 23%, rgba(59,130,246,0.16) 38%, transparent 52%), radial-gradient(circle at 72% 58%, rgba(255,255,255,1) 0%, rgba(219,234,254,0.98) 12%, rgba(96,165,250,0.74) 25%, rgba(37,99,235,0.14) 40%, transparent 54%)",
                  backgroundSize: "100% 100%, 145% 112%, 165% 122%",
                }}
                animate={{
                  backgroundPosition: [
                    "0% 0%, -70% 42%, -120% 62%",
                    "0% 0%, 125% 36%, 145% 48%",
                    "0% 0%, 220% 58%, 260% 38%",
                  ],
                }}
                transition={{
                  duration: 5.2,
                  ease: "linear",
                  repeat: Infinity,
                }}
              >
                智能文档
              </motion.span>
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
            <div className="relative z-10 h-[360px] w-full max-w-[640px] md:h-[430px]">
              <div className="absolute left-1/2 top-1/2 z-10 h-[108%] w-[112%] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[30px] border border-[#cfe8f7] bg-gradient-to-br from-white via-[#fbfdff] to-[#edf8ff] p-[5px] shadow-[0_18px_54px_-24px_rgba(37,99,235,0.42),0_0_0_1px_rgba(255,255,255,0.94)_inset,0_0_28px_rgba(186,230,253,0.5)]">
                <div className="h-full w-full overflow-hidden rounded-[25px] border border-white/95 bg-white p-[3px] shadow-[0_0_0_1px_rgba(207,232,247,0.72)_inset,0_12px_36px_-24px_rgba(13,28,46,0.5)]">
                  <img
                    src={section1MainImage}
                    alt="智能文档平台"
                    className="h-full w-full origin-top rounded-[21px] bg-white object-contain"
                  />
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

    const features = useMemo(
      () => [
        {
          title: "传统文档操作繁琐，自然语言指令易歧义且破坏格式",
          description:
            "传统办公软件依赖层级菜单与机械点击，操作繁琐、打断思维流；自然语言指令易产生歧义，且常因结构解析不足破坏文档格式，影响办公效率与文档合规性。",
          image: sec2_1,
        },
        {
          title: "传统提取方式不稳定，同时数据安全难以保障",
          description:
            "传统模板式提取易因版式变动失效，纯大模型提取易产生幻觉、数据失真，同时企业敏感数据上云存在隐私泄露与合规风险，安全难以保障。",
          image: sec2_2,
        },
        {
          title: "人工填表耗时易错，表格结构复杂且字段对齐困难",
          description:
            "工作人员通常需要在多个高分辨率屏幕之间频繁切换，从冗长文档中肉眼寻找对应数据，然后手动复制、校验并粘贴至目标表格的特定单元格中，是办公自动化流转中耗时最长、认知负荷最重且最易引发人为错误的环节之一。",
          image: sec2_3,
        },
        {
          title: "各行业结构信息分散，联系构建难且可视化易混乱",
          description:
            "各行业企业内部数据分散形成信息孤岛，缺乏有效关联；构建联系时实体关系难提取、易出错，可视化展示易因节点繁多出现混乱，不便使用。",
          image: sec2_4,
        },
      ],
      [],
    );
    const featureCount = features.length;
    const shouldContainFeatureImage = (index: number) => index < 2;
    const [activeIndex, setActiveIndex] = useState(0);

    useEffect(() => {
      return scrollYProgress.on('change', (latest) => {
        const nextIndex = Math.min(
          featureCount - 1,
          Math.max(0, Math.floor(latest * featureCount)),
        );
        setActiveIndex((current) =>
          current === nextIndex ? current : nextIndex,
        );
      });
    }, [featureCount, scrollYProgress]);

    return (
      <div className="w-full relative bg-white z-20 flex flex-col items-center my-36">
        {/* 背景：点阵底纹 */}
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
          <div
            className="absolute inset-0 bg-[radial-gradient(#dfe4e8_1px,transparent_1.2px)] [background-size:24px_24px] opacity-70"
            style={{
              WebkitMaskImage: 'radial-gradient(ellipse 60% 60% at 50% 50%, #000 70%, transparent 100%)',
              maskImage: 'radial-gradient(ellipse 60% 60% at 50% 50%, #000 70%, transparent 100%)',
            }}
          />
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
            <div className="group relative w-full aspect-square max-h-[70vh] rounded-[3rem] bg-slate-50/50 backdrop-blur-2xl border border-white/20 isolate overflow-hidden mx-auto">
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

              {/* 图片层直接放在外部容器内，避免额外白色双框 */}
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
                  className={cn(
                    "absolute inset-0 origin-center transition-transform duration-700 ease-out",
                    shouldContainFeatureImage(i)
                      ? "m-auto h-full w-wull object-contain group-hover:scale-[1.02]"
                      : "h-full w-full object-cover group-hover:scale-[1.05]",
                  )}
                  style={{
                    willChange: "opacity, transform",
                    zIndex: activeIndex === i ? 10 : 1,
                  }}
                />
              ))}
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
                  aria-hidden="true"
                  initial={false}
                  animate={{
                    opacity: activeIndex === i ? 0.22 : 0.08,
                    scale: activeIndex === i ? 1 : 0.96,
                  }}
                  transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  className="pointer-events-none absolute right-4 top-1/2 z-0 -translate-y-1/2 select-none text-[18rem] font-bold leading-none text-[#9bb9f5]"
                >
                  ?
                </motion.div>

                <motion.div
                  initial={false}
                  animate={{
                    opacity: activeIndex === i ? 1 : 0.2,
                    y: activeIndex === i ? 0 : 20,
                  }}
                  transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  className="relative z-10 pl-8 md:pl-16 pr-8 transition-all duration-500"
                >
                  <h3 className="text-3xl lg:text-[2.5rem] text-[#111827] mb-6 leading-[1.2] tracking-wide font-normal">
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
                  className={cn(
                    shouldContainFeatureImage(i)
                      ? "absolute inset-0 m-auto h-[86%] w-[86%] object-contain"
                      : "h-full w-full object-cover",
                  )}
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
    const documentBackgrounds = [
      {
        top: "7%",
        side: "left",
        offset: "4%",
        width: 92,
        height: 118,
        rotate: -12,
        opacity: 0.28,
        variant: "text",
      },
      {
        top: "17%",
        side: "right",
        offset: "5%",
        width: 108,
        height: 136,
        rotate: 10,
        opacity: 0.24,
        variant: "table",
      },
      {
        top: "28%",
        side: "left",
        offset: "1%",
        width: 118,
        height: 148,
        rotate: 8,
        opacity: 0.22,
        variant: "chart",
      },
      {
        top: "40%",
        side: "right",
        offset: "3%",
        width: 86,
        height: 112,
        rotate: -9,
        opacity: 0.26,
        variant: "checklist",
      },
      {
        top: "54%",
        side: "left",
        offset: "6%",
        width: 104,
        height: 132,
        rotate: -6,
        opacity: 0.2,
        variant: "table",
      },
      {
        top: "67%",
        side: "right",
        offset: "1%",
        width: 124,
        height: 154,
        rotate: 12,
        opacity: 0.22,
        variant: "text",
      },
      {
        top: "80%",
        side: "left",
        offset: "3%",
        width: 88,
        height: 116,
        rotate: 9,
        opacity: 0.24,
        variant: "checklist",
      },
      {
        top: "90%",
        side: "right",
        offset: "6%",
        width: 96,
        height: 124,
        rotate: -11,
        opacity: 0.2,
        variant: "chart",
      },
    ] as const;

    return (
      <div
        ref={ref}
        className="relative z-30 flex w-full flex-col items-center gap-16 overflow-hidden bg-white px-0 py-16 lg:gap-24 lg:pb-36 lg:pt-24"
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

        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-0 hidden overflow-hidden sm:block"
        >
          {documentBackgrounds.map((item, index) => (
            <div
              key={index}
              className="absolute rounded-md border border-gray-300/65 bg-gray-200/70 shadow-[0_18px_45px_rgba(15,23,42,0.07)] backdrop-blur-[1px]"
              style={
                {
                  top: item.top,
                  [item.side]: item.offset,
                  width: item.width,
                  height: item.height,
                  opacity: item.opacity,
                  transform: `rotate(${item.rotate}deg)`,
                } as React.CSSProperties
              }
            >
              <div className="absolute right-0 top-0 h-6 w-6 rounded-bl-md border-b border-l border-gray-300/65 bg-gray-200/75" />
              {item.variant === "text" && (
                <div className="absolute left-4 right-4 top-8 space-y-2">
                  <div className="h-1.5 w-3/5 rounded-full bg-gray-400/70" />
                  <div className="h-1 w-full rounded-full bg-gray-400/55" />
                  <div className="h-1 w-4/5 rounded-full bg-gray-400/50" />
                  <div className="h-1 w-11/12 rounded-full bg-gray-400/45" />
                  <div className="h-1 w-2/3 rounded-full bg-gray-400/40" />
                </div>
              )}
              {item.variant === "table" && (
                <div className="absolute left-4 right-4 top-8">
                  <div className="mb-2 flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-sm bg-gray-400/55" />
                    <div className="h-1.5 w-1/2 rounded-full bg-gray-400/60" />
                  </div>
                  <div className="overflow-hidden rounded-[3px] border border-gray-400/30">
                    {Array.from({ length: 5 }).map((_, rowIndex) => (
                      <div
                        key={rowIndex}
                        className="grid grid-cols-[1.15fr_0.75fr_0.9fr] border-b border-gray-400/25 last:border-b-0"
                      >
                        {Array.from({ length: 3 }).map((_, cellIndex) => (
                          <div
                            key={cellIndex}
                            className={cn(
                              "h-4 border-r border-gray-400/25 last:border-r-0 px-1.5 py-1",
                              rowIndex === 0
                                ? "bg-gray-400/38"
                                : rowIndex % 2 === 0
                                  ? "bg-gray-300/24"
                                  : "bg-gray-200/20",
                            )}
                          >
                            <div
                              className={cn(
                                "h-1 rounded-full bg-gray-500/38",
                                cellIndex === 1 ? "w-3/5" : "w-4/5",
                                rowIndex === 0 && "bg-gray-500/52",
                              )}
                            />
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {item.variant === "checklist" && (
                <div className="absolute left-4 right-4 top-8 space-y-3">
                  {Array.from({ length: 4 }).map((_, rowIndex) => (
                    <div key={rowIndex} className="flex items-center gap-2">
                      <div className="h-2.5 w-2.5 rounded-[2px] border border-gray-400/60 bg-gray-300/35" />
                      <div
                        className={cn(
                          "h-1 rounded-full bg-gray-400/55",
                          rowIndex % 2 === 0 ? "w-4/5" : "w-2/3",
                        )}
                      />
                    </div>
                  ))}
                </div>
              )}
              {item.variant === "chart" && (
                <div className="absolute left-4 right-4 top-8">
                  <div className="mb-3 h-1.5 w-1/2 rounded-full bg-gray-400/65" />
                  <div className="flex h-14 items-end gap-2 border-b border-l border-gray-400/30 pl-2">
                    <div className="h-5 w-3 rounded-t-sm bg-gray-400/40" />
                    <div className="h-9 w-3 rounded-t-sm bg-gray-400/55" />
                    <div className="h-7 w-3 rounded-t-sm bg-gray-400/45" />
                    <div className="h-12 w-3 rounded-t-sm bg-gray-400/62" />
                  </div>
                </div>
              )}
            </div>
          ))}
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
        <div className="relative z-10 grid w-full max-w-[1480px] grid-cols-1 gap-10 px-6 lg:min-h-[620px] lg:grid-cols-[minmax(0,1.02fr)_minmax(0,0.98fr)] lg:items-center lg:gap-14 lg:px-16">
          {/* Image Left */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherLeftVariants}
            className="order-1 h-[500px] w-full lg:order-1 lg:h-[580px] lg:max-w-[760px] lg:self-start xl:max-w-[820px]"
          >
            <FeatureBusinessConclusionMockup />
          </motion.div>
          {/* Text Right */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherRightVariants}
            className="order-2 flex flex-col items-start space-y-6 pl-0 lg:order-2 lg:max-w-[560px] lg:self-center lg:pl-4 lg:-translate-y-14 xl:pl-8 xl:-translate-y-[4.5rem]"
          >
            <div className="flex items-center gap-2 text-[#0058be] font-semibold tracking-[0.05em] uppercase text-sm font-['Inter',sans-serif]">
              <span className="w-8 h-[2px] bg-[#0058be]" />
              核心功能
            </div>
            <h2 className="text-4xl md:text-5xl font-bold text-[#0d1c2e] leading-tight font-['Inter',sans-serif] tracking-[-0.02em]">
              智能文档处理
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              基于自然语言处理与文档结构理解技术，将用户对文档的编辑、排版、格式调整、内容提取等操作需求，通过自然语言指令进行解析与转化，自动执行相应操作。
            </p>
          </motion.div>
        </div>

        {/* Feature 2: Share */}
        <div className="relative z-10 grid w-full max-w-[1480px] grid-cols-1 gap-10 px-6 lg:min-h-[640px] lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:items-center lg:gap-14 lg:px-16">
          {/* Text Left */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherLeftVariants}
            className="order-2 flex flex-col items-start space-y-6 pr-0 lg:order-1 lg:max-w-[560px] lg:self-center lg:pr-6 lg:-translate-y-6 xl:pr-10"
          >
            <div className="flex items-center gap-2 text-[#0058be] font-semibold tracking-[0.05em] uppercase text-sm font-['Inter',sans-serif]">
              <span className="w-8 h-[2px] bg-[#0058be]" />
              核心功能
            </div>
            <h2 className="text-4xl md:text-5xl font-bold text-[#0d1c2e] leading-tight font-['Inter',sans-serif] tracking-[-0.02em]">
              非结构化信息提取
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              自动识别用户导入的非结构化文档，利用人工智能技术提取文件中的关键信息、实体数据或用户指定内容，并进行规范的数据库存储操作。
            </p>
          </motion.div>
          {/* Image Right */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherRightVariants}
            className="order-1 relative flex h-[440px] w-full items-center justify-center overflow-visible lg:order-2 lg:h-[580px] lg:translate-x-2 xl:translate-x-6"
          >
            <div className="relative z-10 h-full w-full overflow-visible">
              <div className="absolute inset-y-[5%] left-[10%] right-[2%] z-10 overflow-hidden rounded-[30px] border border-[#cfe8f7] bg-gradient-to-br from-white via-[#fbfdff] to-[#edf8ff] p-[5px] shadow-[0_18px_54px_-24px_rgba(37,99,235,0.42),0_0_0_1px_rgba(255,255,255,0.94)_inset,0_0_28px_rgba(186,230,253,0.5)]">
                <div className="h-full w-full overflow-hidden rounded-[25px] border border-white/95 bg-white p-[3px] shadow-[0_0_0_1px_rgba(207,232,247,0.72)_inset,0_12px_36px_-24px_rgba(13,28,46,0.5)]">
                  <FeatureExtractionMockup />
                </div>
              </div>

              <div className="absolute left-[1%] top-[52%] z-20 h-[44%] w-[33%] -translate-y-1/2 overflow-hidden rounded-2xl bg-white shadow-[0_22px_55px_-24px_rgba(13,28,46,0.4)] lg:left-[-4%] lg:top-[56%] lg:h-[45%] lg:w-[32%]">
                <img
                  src={secfea_2Left}
                  className="h-full w-full object-contain"
                  alt="非结构化信息提取"
                />
              </div>

              <div className="absolute right-[0%] top-[70%] z-20 h-[52%] w-[27%] -translate-y-1/2 overflow-hidden rounded-2xl bg-white shadow-[0_22px_55px_-24px_rgba(13,28,46,0.4)] lg:right-[-4%] lg:top-[72%] lg:h-[55%] lg:w-[26%]">
                <img
                  src={secfea_2Right}
                  className="h-full w-full object-contain"
                  alt="非结构化信息提取"
                />
              </div>
            </div>
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
            className="order-1 lg:order-1 h-[400px] lg:h-[500px] w-full rounded-2xl overflow-hidden shadow-[0_18px_54px_-24px_rgba(37,99,235,0.42),0_0_0_1px_rgba(255,255,255,0.94)_inset,0_0_28px_rgba(186,230,253,0.5)] border border-[#d1d1e9] flex items-center justify-center bg-[#eff4ff]"
          >
            <img
              src={secfea_3}
              className="w-full h-full object-contain rounded-2xl"
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
              数据填充
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              自动从各类文档中提取信息，智能匹配目标表格字段，精准填入对应单元格，同时支持简单计算与格式保留，快速完成数据回填，大幅减少人工复制粘贴，提升填表效率与准确率。
            </p>
          </motion.div>
        </div>

        {/* Feature 4: Assistant */}
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
              知识图谱
            </h2>
            <p className="text-lg text-[#434655] leading-relaxed max-w-lg font-['Inter',sans-serif]">
              自动抽取文档中的关键信息与关联关系，构建企业知识图谱，打破各部门信息孤岛；同时实现图谱动态更新与清晰可视化展示，方便直观查询、分析和利用数据。
            </p>
          </motion.div>
          {/* Image Right */}
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={gatherRightVariants}
            className="order-1 lg:order-2 h-[400px] lg:h-[500px] w-full rounded-2xl overflow-hidden shadow-[0_18px_54px_-24px_rgba(37,99,235,0.42),0_0_0_1px_rgba(255,255,255,0.94)_inset,0_0_28px_rgba(186,230,253,0.5)] border border-[#d1d1e9] flex items-center justify-center bg-[#eff4ff]"
          >
            <img
              src={secfea_4}
              className="w-full h-full object-contain rounded-2xl"
              alt="全局智能助手"
            />
          </motion.div>
        </div>
      </div>
    );
  };

  const SectionCTA = () => {
    const ctaSectionRef = useRef<HTMLDivElement>(null);
    const backgroundTextRef = useRef<HTMLDivElement>(null);
    const backgroundSweepTimerRef = useRef<number | null>(null);
    const hasBackgroundSweepPlayedRef = useRef(false);
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
    const [isBackgroundSweepActive, setIsBackgroundSweepActive] =
      useState(false);
    const [isH2TypingComplete, setIsH2TypingComplete] = useState(false);
    const [isPTypingComplete, setIsPTypingComplete] = useState(false);

    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
      if (!backgroundTextRef.current || isBackgroundSweepActive) return;
      const rect = backgroundTextRef.current.getBoundingClientRect();

      // Calculate mouse position relative to the center of the text container
      // This ensures the radial gradient center exactly matches the cursor tip
      setMousePosition({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    };

    useEffect(() => {
      const target = ctaSectionRef.current;
      if (!target || typeof IntersectionObserver === "undefined") {
        return;
      }

      const observer = new IntersectionObserver(
        ([entry]) => {
          if (!entry?.isIntersecting || hasBackgroundSweepPlayedRef.current) {
            return;
          }

          hasBackgroundSweepPlayedRef.current = true;
          setIsBackgroundSweepActive(true);

          backgroundSweepTimerRef.current = window.setTimeout(() => {
            setIsBackgroundSweepActive(false);
            backgroundSweepTimerRef.current = null;
          }, 1600);
        },
        {
          root: containerRef.current,
          threshold: 0.35,
        },
      );

      observer.observe(target);

      return () => {
        observer.disconnect();
        if (backgroundSweepTimerRef.current) {
          window.clearTimeout(backgroundSweepTimerRef.current);
        }
      };
    }, []);

    return (
      <div
        ref={ctaSectionRef}
        className="w-full mt-20 flex justify-center bg-white relative z-40 flex-1"
      >
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
            ref={backgroundTextRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setMousePosition({ x: -1000, y: -1000 })}
            className="absolute inset-x-0 bottom-0 translate-y-[45%] md:translate-y-[35%] flex items-center justify-center select-none z-0 overflow-hidden w-full pointer-events-auto h-[40vw] max-h-[600px]"
          >
            <h1 className="relative text-[20vw] leading-none font-bold tracking-tighter whitespace-nowrap cursor-default origin-bottom w-full h-full flex items-center justify-center">
              {/* 底层文字：只有轮廓，浅灰色 */}
              <span className="inline-block text-[#cdcdcd53]">SmartDoc</span>

              <AnimatePresence mode="wait">
                {isBackgroundSweepActive ? (
                  <motion.span
                    key="sweep"
                    className="absolute left-0 top-0 w-full h-full inline-flex items-center justify-center bg-clip-text text-transparent bg-[#86b4ff] pointer-events-none"
                    style={{
                      WebkitMaskImage:
                        "linear-gradient(90deg, transparent 0%, black 35%, black 65%, transparent 100%)",
                      maskImage:
                        "linear-gradient(90deg, transparent 0%, black 35%, black 65%, transparent 100%)",
                      WebkitMaskSize: "34% 100%",
                      maskSize: "34% 100%",
                      WebkitMaskRepeat: "no-repeat",
                      maskRepeat: "no-repeat",
                    }}
                    initial={
                      {
                        opacity: 0,
                        WebkitMaskPosition: "-45% 0%",
                        maskPosition: "-45% 0%",
                      } as TargetAndTransition
                    }
                    animate={
                      {
                        opacity: 1,
                        WebkitMaskPosition: "145% 0%",
                        maskPosition: "145% 0%",
                      } as TargetAndTransition
                    }
                    exit={{ opacity: 0 }}
                    transition={{
                      duration: 1.6,
                      ease: "linear",
                    }}
                  >
                    SmartDoc
                  </motion.span>
                ) : (
                  <motion.span
                    key="flashlight"
                    className="absolute left-0 top-0 w-full h-full inline-flex items-center justify-center bg-clip-text text-transparent bg-[#86b4ff] pointer-events-none"
                    style={{
                      WebkitMaskImage: `radial-gradient(circle 5vw at ${mousePosition.x}px ${mousePosition.y}px, black 0%, transparent 100%)`,
                      maskImage: `radial-gradient(circle 5vw at ${mousePosition.x}px ${mousePosition.y}px, black 0%, transparent 100%)`,
                      WebkitMaskSize: "100% 100%",
                      maskSize: "100% 100%",
                      WebkitMaskRepeat: "no-repeat",
                      maskRepeat: "no-repeat",
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    SmartDoc
                  </motion.span>
                )}
              </AnimatePresence>
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
                    staggerChildren: 0.1,
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
                {"准备好提升团队效率了吗？立即体验文枢智动，开启高效工作"
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
              <button className="px-6 py-2.5 rounded-full bg-white text-[#0d1c2e] font-semibold border border-[#e2e8f0] shadow-sm hover:bg-gray-50 transition-all text-sm h-[44px]">
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
            <div className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-3 whitespace-nowrap md:ml-38">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-transparent">
                <img
                  src={guideLogo}
                  alt="文枢智动"
                  className="h-9 w-9 bg-transparent object-contain"
                />
              </span>
              <span className="hidden md:inline-block text-[#0d1c2e]">
                文枢智动
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
