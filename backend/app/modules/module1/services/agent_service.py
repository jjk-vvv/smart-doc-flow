from __future__ import annotations

import base64
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Iterator, List, Optional

from dotenv import load_dotenv

from ..core.config import Settings, get_settings


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)
STREAM_END = object()

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

try:
    import sniffio  # type: ignore
except ImportError:  # pragma: no cover - local fallback for offline envs
    from ..utils import sniffio_compat as sniffio  # type: ignore

    sys.modules.setdefault("sniffio", sniffio)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]


class LayoutExpertAgent:
    """模块一的排版/文档处理智能体封装。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = str(self.settings.llm_api_key or "").strip()
        self.base_url = str(self.settings.llm_base_url or "").strip()
        self.text_model = str(self.settings.llm_model or "").strip()
        self.vision_model = str(self.settings.llm_vision_model or self.text_model).strip()
        self.timeout_sec = float(self.settings.llm_timeout_sec)
        self.client = self._build_client()

    def _build_client(self) -> Optional["OpenAI"]:
        if (
            not self.api_key
            or self.api_key == "your-api-key-here"
            or not self.base_url
            or not self.text_model
            or OpenAI is None
        ):
            logger.warning("未配置有效的模块一 LLM 客户端，模块一 AI 功能将不可用")
            return None

        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_sec,
            )
            logger.info(
                "模块一 LLM 客户端初始化成功: base_url=%s model=%s",
                self.base_url,
                self.text_model,
            )
            return client
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            logger.error("模块一 LLM 客户端初始化失败: %s", exc)
            return None

    @property
    def available(self) -> bool:
        return self.client is not None

    def _build_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_context: Optional[List[dict[str, str]]] = None,
    ) -> List[dict[str, str]]:
        messages: List[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in conversation_context or []:
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role not in {"system", "user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content[:1800]})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _guess_image_mime(self, image_path: str) -> str:
        return IMAGE_MIME_TYPES.get(Path(image_path).suffix.lower(), "image/jpeg")

    def _analyze_image(self, image_path: str, prompt: str, max_tokens: int = 700) -> str:
        if not self.client:
            return ""

        with open(image_path, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")

        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{self._guess_image_mime(image_path)};base64,{image_base64}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return str(response.choices[0].message.content or "").strip()

    def describe_images(self, image_paths: List[str], max_images: int = 3) -> str:
        if not self.client or not image_paths:
            return ""

        prompt = (
            "请严格基于图片内容进行识别和提取，不要编造。"
            "先输出图片中的文字和数字，保留日期、金额、单位、编号、专有名词；"
            "如果有表格、票据、清单或键值信息，请尽量按结构整理；"
            "如果有图表，请说明标题、图例、坐标轴、关键数值和趋势；"
            "如果局部模糊，请明确写“无法辨认”。"
            "最后再补充一段简短的图像内容说明。"
        )
        descriptions: List[str] = []
        for index, image_path in enumerate(image_paths[:max_images], start=1):
            try:
                extracted = self._analyze_image(image_path, prompt, max_tokens=700)
                descriptions.append(f"【图片{index}识别】\n{extracted or '未能识别出有效内容'}")
            except Exception as exc:  # pragma: no cover - API dependent
                logger.error("图片分析失败: %s", exc)
                descriptions.append(f"【图片{index}识别】图片分析失败")

        return "\n\n".join(descriptions)

    def stream_analysis(
        self,
        instruction: str,
        simple_content: str,
        conversation_context: Optional[List[dict[str, str]]] = None,
    ) -> Iterator[str]:
        if not self.client:
            raise RuntimeError("模块一 LLM 未配置")

        system_prompt = (
            "你是一个专业的文档内容分析助手。"
            "请严格基于当前上传文档和当前对话上下文回答，不能混入旧文档信息。"
            "如果用户当前上传了多份文档，要先识别它们之间的关系，再给出统一分析。"
            "输出必须为正式、结构化、可直接交付的分析/提取报告。"
            "全文只允许三级结构，禁止出现第四级及以下层级。"
            "一级标题统一使用“一、二、三”格式；"
            "二级标题统一使用“1. 2. 3.”格式；"
            "三级标题统一使用“(1)(2)(3)”格式。"
            "标题序号必须连续、唯一，不能混用 Markdown 标题、短横线列表、星号列表或其他编号样式。"
            "不要输出 #、##、###、*、-、>、``` 等 Markdown 符号。"
            "正文要自然分段，每段聚焦一个意思，避免大段堆叠和杂乱换行。"
            "段落之间保留适度空行，整体风格简洁、正式、美观。"
            "优先给出核心结论、关键事实/数据、问题或风险、下一步建议。"
            "如果用户更偏向提取，就把关键信息整理成分点、字段清单或简短表格式文本；"
            "如果用户更偏向分析，就在提取事实后补充趋势判断、原因归纳、影响分析和建议。"
            "避免空话和泛化表述，不要输出多余前言、免责声明或操作提示。"
        )
        user_prompt = (
            f"用户指令：{instruction}\n\n"
            f"当前文档内容：\n{simple_content[:12000]}\n\n"
            "请直接输出可阅读、可继续编辑的分析/提取报告。"
            "若内容较短，也必须保持规范标题层级和正式排版。"
        )

        response = self.client.chat.completions.create(
            model=self.text_model,
            messages=self._build_messages(system_prompt, user_prompt, conversation_context),
            temperature=0.45,
            max_tokens=3600,
            stream=True,
        )

        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def stream_analysis_with_first_token_timeout(
        self,
        instruction: str,
        simple_content: str,
        conversation_context: Optional[List[dict[str, str]]] = None,
        *,
        first_token_timeout_sec: float = 18.0,
        hard_timeout_sec: float | None = None,
    ) -> Iterator[str]:
        if not self.client:
            raise RuntimeError("模块一 LLM 未配置")

        result_queue: queue.Queue[object] = queue.Queue()
        soft_timeout_sec = max(0.0, float(first_token_timeout_sec))
        overall_timeout_sec = max(
            max(soft_timeout_sec, 1.0),
            float(hard_timeout_sec or self.settings.analysis_hard_timeout_sec or self.timeout_sec),
        )

        def worker() -> None:
            try:
                for chunk in self.stream_analysis(instruction, simple_content, conversation_context):
                    if chunk:
                        result_queue.put(chunk)
                result_queue.put(STREAM_END)
            except Exception as exc:  # pragma: no cover - runtime/network dependent
                result_queue.put(exc)

        threading.Thread(target=worker, daemon=True).start()
        received_first_chunk = False
        warned_slow_first_token = False
        start_at = time.monotonic()

        while True:
            try:
                if received_first_chunk:
                    item = result_queue.get()
                else:
                    elapsed_sec = time.monotonic() - start_at
                    remaining_sec = overall_timeout_sec - elapsed_sec
                    if remaining_sec <= 0:
                        raise TimeoutError(
                            f"分析结果整体等待超过 {overall_timeout_sec:.0f} 秒，仍未收到 AI 返回"
                        )
                    if soft_timeout_sec > 0:
                        wait_timeout_sec = min(soft_timeout_sec, remaining_sec)
                    else:
                        wait_timeout_sec = remaining_sec
                    item = result_queue.get(timeout=wait_timeout_sec)
            except queue.Empty as exc:
                elapsed_sec = time.monotonic() - start_at
                if elapsed_sec >= overall_timeout_sec:
                    raise TimeoutError(
                        f"分析结果整体等待超过 {overall_timeout_sec:.0f} 秒，仍未收到 AI 返回"
                    ) from exc
                if not warned_slow_first_token and soft_timeout_sec > 0:
                    warned_slow_first_token = True
                    logger.warning(
                        "模块一分析首包超过 %.0f 秒仍未返回，继续等待 AI 结果",
                        soft_timeout_sec,
                    )
                continue

            if item is STREAM_END:
                return
            if isinstance(item, Exception):
                raise item

            received_first_chunk = True
            yield str(item)

    def stream_chat(
        self,
        instruction: str,
        conversation_context: Optional[List[dict[str, str]]] = None,
    ) -> Iterator[str]:
        if not self.client:
            raise RuntimeError("模块一 LLM 未配置")

        system_prompt = (
            "你是一个直接回答问题的助手。"
            "不要自我介绍，不要列举功能。"
            "要承接当前对话历史继续回答，不要丢失上下文。"
        )
        user_prompt = instruction

        response = self.client.chat.completions.create(
            model=self.text_model,
            messages=self._build_messages(system_prompt, user_prompt, conversation_context),
            temperature=0.5,
            max_tokens=2000,
            stream=True,
        )

        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def plan_modifications(
        self,
        instruction: str,
        filename: str,
        doc_content: str,
        conversation_context: Optional[List[dict[str, str]]] = None,
    ) -> str:
        if not self.client:
            raise RuntimeError("模块一 LLM 未配置")

        system_prompt = (
            "你是一个专业的文档处理 AI 助手，能够理解用户的自然语言指令，并生成可执行的文档修改方案。"
            "请严格围绕当前焦点文件生成修改方案，不要把别的文档内容串进来。"
            "先用自然语言简要说明会怎么改，再输出一个 ```json``` 代码块。"
            "JSON 顶层必须是 {\"modifications\": [...]}。"
            "支持的修改类型只有三种："
            "1. text_run_format：用于标题/正文的加粗、斜体、下划线、颜色、字体、字号、对齐、标题级别、行距、段前段后；"
            "2. replace_text：用于替换现有文本；"
            "3. insert_text：用于插入新文本。"
            "text_run_format 可使用这些字段：paragraph_index, reference_text, run_indices, bold, italic, underline, color, font_name, font_size, alignment, heading_level, line_spacing, space_before, space_after。"
            "replace_text 可使用：old_text, new_text。"
            "insert_text 可使用：text, position, paragraph_index, line_index, reference_text。"
            "alignment 只能是 left、center、right、justify。heading_level 只能是 0、1、2、3，其中 0 表示正文。"
            "position 只能是 start、end、before、after。"
            "如果用户只提到一个或少数几个格式属性，只输出这些明确提到的字段，不要补充默认值。"
            "例如用户只要求改颜色时，不要输出 bold、heading_level、alignment、font_size 等无关字段。"
            "只有用户明确说取消某个样式时，才允许输出对应布尔字段为 false。"
            "不要为了看起来完整而重置未提到的样式。"
            "如果用户要求调整标题颜色、标题字体、标题字号、居中、段落格式、层级结构，就优先输出 text_run_format。"
            "如果用户明确说了‘替换某段文字’、‘把A替换成B’，就输出 replace_text。"
            "如果用户明确说了‘在开头/结尾/某段前后/某句话前后插入内容’，就输出 insert_text。"
            "只输出必要字段，不要杜撰无关属性。不要输出额外提示信息。"
        )
        user_prompt = (
            f"用户指令：{instruction}\n\n"
            f"焦点文档：{filename}\n"
            f"文档内容：{doc_content[:12000]}\n\n"
            "请生成修改方案。"
        )

        response = self.client.chat.completions.create(
            model=self.text_model,
            messages=self._build_messages(system_prompt, user_prompt, conversation_context),
            temperature=0.3,
            max_tokens=4000,
            stream=False,
        )
        return str(response.choices[0].message.content or "")
