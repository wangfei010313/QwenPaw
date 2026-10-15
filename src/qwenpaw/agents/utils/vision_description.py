# -*- coding: utf-8 -*-
"""Select images or their associated descriptions in request copies."""

from __future__ import annotations

from typing import Any

from agentscope.message import Msg, TextBlock

from ...constant import MEDIA_UNSUPPORTED_PLACEHOLDER

VISION_DESCRIPTION_KEY = f"qwenpaw_vision_descriptions"


def block_attribute(value: Any, name: str, default: Any = None) -> Any:
    """Read a field from a typed or legacy block."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def is_image_block(block: Any) -> bool:
    """Recognize images without treating other modalities as images."""
    kind = block_attribute(block, f"type")
    source = block_attribute(block, f"source")
    mime = block_attribute(source, f"media_type", f"") or f""
    return kind == f"image" or (kind == f"data" and mime.startswith(f"image/"))


def description_records(owner: Any) -> dict:
    """Read description associations from a message or tool result."""
    metadata = block_attribute(owner, f"metadata", {}) or {}
    records = metadata.get(VISION_DESCRIPTION_KEY, {})
    return records if isinstance(records, dict) else {}


def project_image_descriptions(
    messages: list[Msg],
    *,
    supports_image: bool,
) -> None:
    """Choose image or description blocks in already detached messages."""

    def project(owner: Any, blocks: list) -> list:
        records = description_records(owner)
        image_ids = {
            block_attribute(block, f"id")
            for block in blocks
            if is_image_block(block)
        }
        result = []
        for block in blocks:
            block_id = block_attribute(block, f"id")
            record = records.get(block_id)
            if (
                supports_image
                and isinstance(record, dict)
                and record.get(f"image_id") in image_ids
            ):
                continue
            if not supports_image and is_image_block(block):
                continue
            for name in (f"output", f"hint"):
                nested = block_attribute(block, name)
                if isinstance(nested, list):
                    filtered = project(block, nested)
                    if isinstance(block, dict):
                        block[name] = filtered
                    else:
                        setattr(block, name, filtered)
            result.append(block)
        if blocks and not result:
            return [TextBlock(text=MEDIA_UNSUPPORTED_PLACEHOLDER)]
        return result

    for message in messages:
        if isinstance(message.content, list):
            message.content = project(message, message.content)
