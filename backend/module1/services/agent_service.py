from __future__ import annotations

import base64
import logging
import sys
from pathlib import Path
from typing import Iterator, List, Optional

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)

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
    from utils import sniffio_compat as sniffio  # type: ignore

    sys.modules.setdefault("sniffio", sniffio)

try:
    from zhipuai import ZhipuAI
except ImportError:  # pragma: no cover - optional dependency
    ZhipuAI = None


class LayoutExpertAgent:
    """模块一的排版/文档处理智能体封装。"""

    def __init__(self, api_key: str) -> None:
        self.api_key = (api_key or "").strip()
        self.client = self._build_client()

    def _build_client(self) -> Optional["ZhipuAI"]:
        if not self.api_key or self.api_key == "your-api-key-here" or ZhipuAI is None:
            logger.warning("未配置有效的智谱 AI 客户端，模块一 AI 功能将不可用")
            return None

        try:
            client = ZhipuAI(api_key=self.api_key)
            logger.info("智谱 AI 客户端初始化成功")
            return client
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            logger.error("智谱 AI 客户端初始化失败: %s", exc)
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
            model="glm-4v",
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
            raise RuntimeError("智谱AI未配置")

        system_prompt = (
            "你是一个专业的文档内容分析助手。"
            "请严格基于当前上传文档和当前对话上下文回答，不能混入旧文档信息。"
            "如果用户当前上传了多份文档，要先识别它们之间的关系，再给出统一分析。"
            "输出时默认使用清晰的 Markdown 分层结构，只允许使用 #、##、### 三级标题。"
            "优先给出核心结论、关键事实/数据、问题或风险、下一步建议。"
            "如果用户更偏向提取，就把关键信息整理成分点、字段清单或简短表格式文本；"
            "如果用户更偏向分析，就在提取事实后补充趋势判断、原因归纳、影响分析和建议。"
            "避免空话和泛化表述，不要输出多余前言、免责声明或操作提示。"
        )
        user_prompt = (
            f"用户指令：{instruction}\n\n"
            f"当前文档内容：\n{simple_content[:12000]}\n\n"
            "请直接输出可阅读、可继续编辑的分析/提取报告。"
        )

        response = self.client.chat.completions.create(
            model="glm-4",
            messages=self._build_messages(system_prompt, user_prompt, conversation_context),
            temperature=0.45,
            max_tokens=3600,
            stream=True,
        )

        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def stream_chat(
        self,
        instruction: str,
        conversation_context: Optional[List[dict[str, str]]] = None,
    ) -> Iterator[str]:
        if not self.client:
            raise RuntimeError("智谱AI未配置")

        system_prompt = (
            "你是一个直接回答问题的助手。"
            "不要自我介绍，不要列举功能。"
            "要承接当前对话历史继续回答，不要丢失上下文。"
        )
        user_prompt = instruction
        
        response = self.client.chat.completions.create(
            model="glm-4",
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
            raise RuntimeError("智谱AI未配置")

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
            model="glm-4",
            messages=self._build_messages(system_prompt, user_prompt, conversation_context),
            temperature=0.3,
            max_tokens=4000,
            stream=False,
        )
        return response.choices[0].message.content
