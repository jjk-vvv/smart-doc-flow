import type { LegendEdgeItem, LegendNodeItem } from './legendModel';
import { cn } from '../../lib/utils';

type KnowledgeGraphLegendProps = {
  nodeItems: LegendNodeItem[];
  edgeItems: LegendEdgeItem[];
  className?: string;
};

const NodeGlyph = ({ item }: { item: LegendNodeItem }) => {
  if (item.shape === 'panel') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <rect x="2.25" y="3.25" width="11.5" height="9.5" rx="3" fill={item.color} stroke="rgba(15,23,42,0.12)" />
      </svg>
    );
  }

  if (item.shape === 'diamond') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <rect
          x="3.1"
          y="3.1"
          width="9.8"
          height="9.8"
          rx="2"
          transform="rotate(45 8 8)"
          fill={item.color}
          stroke="rgba(15,23,42,0.12)"
        />
      </svg>
    );
  }

  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="5.1" fill={item.color} stroke="rgba(15,23,42,0.12)" />
    </svg>
  );
};

const EdgeGlyph = ({ item }: { item: LegendEdgeItem }) => {
  if (item.style === 'primary-flow') {
    return (
      <svg width="34" height="12" viewBox="0 0 34 12" aria-hidden="true">
        <path d="M2 6 H32" stroke={item.color} strokeWidth="2" strokeLinecap="round" opacity="0.45" />
        <path d="M2 6 H32" stroke={item.color} strokeWidth="1.5" strokeLinecap="round" />
        <path d="M2 6 H32" stroke="#ffffff" strokeWidth="1.25" strokeLinecap="round" strokeDasharray="6 18" />
      </svg>
    );
  }

  if (item.style === 'support') {
    return (
      <svg width="34" height="12" viewBox="0 0 34 12" aria-hidden="true">
        <path d="M2 6 H32" stroke={item.color} strokeWidth="1.8" strokeLinecap="round" opacity="0.28" />
        <path d="M2 6 H32" stroke={item.color} strokeWidth="1.4" strokeLinecap="round" strokeDasharray="4 4" />
      </svg>
    );
  }

  if (item.style === 'folded') {
    return (
      <svg width="34" height="12" viewBox="0 0 34 12" aria-hidden="true">
        <circle cx="17" cy="6" r="5" fill="rgba(15,23,42,0.9)" />
        <text
          x="17"
          y="6"
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="6"
          fontWeight="700"
          fill="#F8FAFC"
        >
          3
        </text>
      </svg>
    );
  }

  return (
    <svg width="34" height="12" viewBox="0 0 34 12" aria-hidden="true">
      <path d="M2 6 H32" stroke={item.color} strokeWidth="1.4" strokeLinecap="round" opacity="0.42" />
    </svg>
  );
};

export const KnowledgeGraphLegend = ({
  nodeItems,
  edgeItems,
  className = '',
}: KnowledgeGraphLegendProps) => {
  if (nodeItems.length === 0 && edgeItems.length === 0) return null;

  return (
    <div
      className={cn(
        'pointer-events-none absolute bottom-4 left-4 z-10 w-[220px] rounded-2xl border border-slate-200/90 bg-white/92 px-3 py-2.5 shadow-[0_8px_18px_rgba(15,23,42,0.04)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/78',
        className,
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] font-semibold tracking-[0.18em] text-slate-500 dark:text-slate-400">
          图例
        </div>
        <div className="text-[10px] text-slate-400 dark:text-slate-500">节点 / 连线</div>
      </div>

      {nodeItems.length > 0 && (
        <div className="space-y-1.5">
          {nodeItems.map((item) => (
            <div key={item.key} className="flex items-center gap-2.5">
              <div className="shrink-0">
                <NodeGlyph item={item} />
              </div>
              <div className="min-w-0 truncate text-[11px] font-medium text-slate-700 dark:text-slate-200">
                {item.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {edgeItems.length > 0 && (
        <div className="mt-2.5 space-y-1.5 border-t border-slate-200/80 pt-2.5 dark:border-slate-800/80">
          {edgeItems.map((item) => (
            <div key={item.key} className="flex items-center gap-2.5">
              <div className="shrink-0">
                <EdgeGlyph item={item} />
              </div>
              <div className="min-w-0 truncate text-[11px] font-medium text-slate-700 dark:text-slate-200">
                {item.label}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
