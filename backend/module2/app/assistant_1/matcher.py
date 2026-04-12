from __future__ import annotations

from dataclasses import dataclass

from .models import ContentItem, MatchResult, VisualFigure, VisualTable
from .text_utils import bbox_iou, normalize_image_key, similarity


@dataclass
class _Candidate:
    kind: str
    object_id: str
    page_no: int
    image_key: str
    bbox_raw: list[float]
    caption: str
    nearby_heading: str = ""


class Assistant1Matcher:
    VISUAL_CONTENT_TYPES = {"image", "equation", "formula", "table"}

    def match(
        self,
        content_items: list[ContentItem],
        tables: list[VisualTable],
        figures: list[VisualFigure],
    ) -> tuple[dict[str, MatchResult], list[str], list[str]]:
        candidates: list[_Candidate] = []
        for table in tables:
            candidates.append(
                _Candidate(
                    kind="table",
                    object_id=table.object_id,
                    page_no=table.page_no,
                    image_key=normalize_image_key(table.image_path),
                    bbox_raw=table.bbox_raw,
                    caption=table.caption or table.title,
                    nearby_heading=normalize_image_key(table.title) if table.title and not table.caption else "",
                )
            )
        for figure in figures:
            candidates.append(
                _Candidate(
                    kind="figure",
                    object_id=figure.object_id,
                    page_no=figure.page_no,
                    image_key=normalize_image_key(figure.image_path),
                    bbox_raw=figure.bbox_raw,
                    caption=figure.caption or figure.title,
                    nearby_heading=normalize_image_key(figure.title) if figure.title and not figure.caption else "",
                )
            )

        assignments: dict[str, MatchResult] = {}
        used_object_ids: set[str] = set()
        for item in content_items:
            if item.item_type not in self.VISUAL_CONTENT_TYPES:
                continue
            best: MatchResult | None = None
            for candidate in candidates:
                if candidate.object_id in used_object_ids:
                    continue
                score, reasons = self._score(item, candidate)
                if best is None or score > best.score:
                    best = MatchResult(
                        content_item_id=item.item_id,
                        matched_kind=candidate.kind,
                        matched_object_id=candidate.object_id,
                        score=score,
                        status="exact" if score >= 0.78 else "probable" if score >= 0.45 else "unmatched",
                        reasons=reasons,
                    )
            if best and best.status != "unmatched":
                assignments[item.item_id] = best
                used_object_ids.add(best.matched_object_id)

        unmatched_content = [
            item.item_id
            for item in content_items
            if item.item_type in self.VISUAL_CONTENT_TYPES and item.item_id not in assignments
        ]
        unmatched_objects = [candidate.object_id for candidate in candidates if candidate.object_id not in used_object_ids]
        return assignments, unmatched_content, unmatched_objects

    def _score(self, item: ContentItem, candidate: _Candidate) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        item_image_key = normalize_image_key(item.img_path)
        if item_image_key and item_image_key == candidate.image_key:
            score += 0.70
            reasons.append("image basename match")
        if item.page_no and candidate.page_no:
            page_dist = abs(item.page_no - candidate.page_no)
            if page_dist == 0:
                score += 0.15
                reasons.append("same page")
            elif page_dist == 1:
                score += 0.07
                reasons.append("adjacent page")
        overlap = bbox_iou(item.bbox, candidate.bbox_raw)
        if overlap > 0:
            score += min(0.20, overlap * 0.20)
            reasons.append(f"bbox iou={overlap:.3f}")
        caption_score = similarity(item.image_caption or item.image_footnote, candidate.caption)
        if caption_score > 0:
            score += min(0.15, caption_score * 0.15)
            reasons.append(f"caption similarity={caption_score:.3f}")
        if candidate.nearby_heading:
            heading_score = similarity(item.image_caption or item.image_footnote, candidate.nearby_heading)
            if heading_score > 0:
                score += min(0.30, heading_score * 0.30)
                reasons.append(f"heading similarity={heading_score:.3f}")
        return score, reasons
