from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Callable, Optional


EngineFactory = Callable[[], Any]


class OcrEngineRuntime:
    """Lazy OCR engine bootstrap with cached success/error state."""

    _ocr_engine: Any = None
    _ocr_engine_init_error: Optional[str] = None

    @classmethod
    def reset(cls) -> None:
        cls._ocr_engine = None
        cls._ocr_engine_init_error = None

    @classmethod
    def get_ocr_engine(cls, engine_factory: EngineFactory | None = None) -> Any:
        if cls._ocr_engine is None:
            if cls._ocr_engine_init_error:
                raise RuntimeError(cls._ocr_engine_init_error)

            timeout_sec = max(2.0, float(os.getenv("MODULE2_OCR_ENGINE_INIT_TIMEOUT_SEC", "15")))

            def _build_engine() -> Any:
                if engine_factory is not None:
                    return engine_factory()
                from rapidocr_onnxruntime import RapidOCR

                return RapidOCR()

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_build_engine)
            try:
                cls._ocr_engine = future.result(timeout=timeout_sec)
            except Exception as exc:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                cls._ocr_engine_init_error = (
                    f"OCR engine init failed within {timeout_sec:.1f}s: {type(exc).__name__}: {exc}"
                )
                raise RuntimeError(cls._ocr_engine_init_error) from exc
            executor.shutdown(wait=False, cancel_futures=True)
        return cls._ocr_engine
