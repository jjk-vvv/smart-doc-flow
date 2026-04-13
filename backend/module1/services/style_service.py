from __future__ import annotations

from schemas import StyleTransferStatus


class StyleTransferService:
    """样式克隆接口占位，后续可以在这里接入真实实现。"""

    def get_status(self) -> StyleTransferStatus:
        return StyleTransferStatus()
