# -*- coding: utf-8 -*-
"""Regression coverage for bounded image-to-text fallback."""

import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from pydantic import ValidationError
from agentscope.message import (
    Base64Source,
    DataBlock,
    Msg,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    ToolResultState,
    URLSource,
)
from agentscope.model import ChatModelBase
from agentscope.model._model_response import ChatResponse

from agentscope.state import AgentState

from qwenpaw.agents.react_agent import QwenPawAgent
from qwenpaw.agents.context.scroll.history import HistoryStore
from qwenpaw.agents.context.scroll.manager import ScrollContextManager
from qwenpaw.agents.context.scroll.serialize import msg_to_entries
from qwenpaw.agents.utils.message_request_normalizer import (
    normalize_messages_for_model_request,
)
from qwenpaw.agents.utils.vision_description import VISION_DESCRIPTION_KEY
from qwenpaw.agents.utils.vision_fallback import (
    VisionFallbackChatModel,
    VisionFallbackContext,
    image_support,
    is_image_capability_error,
)
from qwenpaw.config.config import (
    AgentsRunningConfig,
    MultimodalFallbackConfig,
)
from qwenpaw.providers.fallback_chat_model import FallbackChatModel
from qwenpaw.providers.model_capability_cache import get_capability_cache


def image(color=f"red"):
    """Produce valid image bytes with a distinct content fingerprint."""
    output = BytesIO()
    Image.new(f"RGB", (20, 20), color).save(output, format=f"PNG")
    return DataBlock(
        source=Base64Source(
            data=base64.b64encode(output.getvalue()).decode(f"ascii"),
            media_type=f"image/png",
        )
    )


def messages(block=None):
    return [
        Msg(
            name=f"user",
            role=f"user",
            content=[
                TextBlock(text=f"Describe this image"),
                block or image(),
            ],
        )
    ]


def response(text=f"A red rectangle."):
    return ChatResponse(content=[TextBlock(text=text)], is_last=True)


class FakeModel(ChatModelBase):
    def __init__(self, behavior=None):
        super().__init__(
            credential=None,
            model=f"test-vision",
            stream=False,
            parameters=ChatModelBase.Parameters(),
            context_size=32768,
        )
        self.calls = []
        self.behavior = behavior
        self.model_key = f"fixture:test-vision"
        self.formatter = SimpleNamespace()

    async def __call__(self, messages, **kwargs):
        self.calls.append(messages)
        if isinstance(self.behavior, Exception):
            raise self.behavior
        if self.behavior is not None:
            return await self.behavior()
        return response()


def context(model=None, cache=None, **kwargs):
    model = model or FakeModel()
    config = MultimodalFallbackConfig(
        enabled=True,
        vision_provider=f"fixture",
        vision_model=f"vision",
        **kwargs,
    )
    build = AsyncMock(return_value=(model, model.formatter))
    return (
        VisionFallbackContext(
            config, cache if cache is not None else {}, build
        ),
        model,
    )


def wrapped(model, support=False):
    result = VisionFallbackChatModel(
        model,
        supports_image=support,
        capability_error=is_image_capability_error,
    )
    result.vision_context, vision = context()
    return result, vision


def test_defaults_and_enabled_selection():
    assert not AgentsRunningConfig().multimodal_fallback.enabled
    with pytest.raises(ValidationError):
        MultimodalFallbackConfig(enabled=True)
    with pytest.raises(ValidationError):
        MultimodalFallbackConfig(max_images_per_turn=0)
    with pytest.raises(ValidationError):
        MultimodalFallbackConfig(description_max_tokens=4097)
    assert (
        image_support(
            SimpleNamespace(
                supports_image=False,
                supports_multimodal=True,
            )
        )
        is False
    )
    assert (
        image_support(
            SimpleNamespace(
                supports_image=None,
                supports_multimodal=True,
            )
        )
        is None
    )


async def test_description_preserves_original_and_deduplicates():
    ctx, model = context()
    msgs = messages()
    original = msgs[0].content[1].model_dump()
    await ctx.prepare(msgs)
    described = msgs[0].model_dump()
    await ctx.prepare(msgs)
    assert msgs[0].model_dump() == described
    assert len(model.calls) == 1
    assert msgs[0].content[1].model_dump() == original
    assert len(msgs[0].content) == 3
    assert f"red rectangle" in msgs[0].get_text_content()
    before = msgs[0].model_dump()
    text = normalize_messages_for_model_request(
        msgs,
        supports_multimodal=False,
    )
    native = normalize_messages_for_model_request(
        msgs,
        supports_multimodal=True,
    )
    assert all(block.type == f"text" for block in text[0].content)
    assert len(native[0].content) == 2
    assert msgs[0].model_dump() == before
    assert VISION_DESCRIPTION_KEY in msg_to_entries(msgs[0])[0].metadata


async def test_tool_result_reuses_uploaded_description():
    ctx, model = context()
    block = image()
    msgs = messages(block)
    call = ToolCallBlock(id=f"call", name=f"view_image", input=f"{{}}")
    tool = ToolResultBlock(
        id=f"call",
        name=f"view_image",
        state=ToolResultState.SUCCESS,
        output=[block.model_copy(deep=True)],
    )
    msgs.extend(
        [
            Msg(name=f"agent", role=f"assistant", content=[call]),
            Msg(name=f"agent", role=f"assistant", content=[tool]),
        ]
    )
    await ctx.prepare(msgs)
    assert len(model.calls) == 1
    assert len(tool.output) == 2
    text = normalize_messages_for_model_request(
        msgs,
        supports_multimodal=False,
    )
    result = text[-1].content[0]
    assert result.output[0].type == f"text"
    assert f"red rectangle" in result.output[0].text


async def test_budget_partial_failure_and_cache_recovery():
    ctx, model = context(max_images_per_turn=1)
    msgs = messages()
    msgs[0].content.append(image(f"blue"))
    await ctx.prepare(msgs)
    assert len(model.calls) == 1
    assert f"image limit reached" in msgs[0].get_text_content()
    restored, second = context(cache=ctx.cache, max_images_per_turn=1)
    await restored.prepare(msgs)
    assert len(second.calls) == 1
    assert f"image limit reached" not in msgs[0].get_text_content()
    assert len(msgs[0].content) == 5


async def test_failure_is_attempted_once_per_turn():
    ctx, model = context(FakeModel(ValueError(f"bad credentials")))
    msgs = messages()
    await ctx.prepare(msgs)
    await ctx.prepare(msgs)
    assert len(model.calls) == 1
    assert not ctx.cache
    assert f"vision request failed" in msgs[0].get_text_content()


async def test_timeout_and_cancellation():
    async def pending():
        await asyncio.Event().wait()

    ctx, model = context(FakeModel(pending))
    ctx._remaining = 0.01
    msgs = messages()
    await ctx.prepare(msgs)
    assert f"timed out" in msgs[0].get_text_content()
    ctx, model = context(FakeModel(pending))
    task = asyncio.create_task(ctx.prepare(messages()))
    while not model.calls:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not ctx.cache


async def test_text_candidate_and_token_count_have_no_extra_calls():
    main = FakeModel()
    model, vision = wrapped(main)
    msgs = messages()
    await model(msgs)
    await model.count_tokens(msgs, None)
    await model(msgs)
    assert len(vision.calls) == 1
    assert all(block.type == f"text" for block in main.calls[0][0].content)
    assert any(block.type == f"data" for block in msgs[0].content)


async def test_native_candidate_uses_images_without_vision_call():
    main = FakeModel()
    model, vision = wrapped(main, True)
    await model(messages())
    assert not vision.calls
    assert main.calls[0][0].content[1].type == f"data"


class HttpError(Exception):
    status_code = 400


@pytest.mark.parametrize(
    f"text,expected",
    [
        (f"This model does not support image input", True),
        (f"This model does not support audio input", False),
        (f"Invalid image format", False),
        (f"This model does not support multiple images", False),
        (f"Invalid request parameters", False),
    ],
)
def test_capability_error_classification(text, expected):
    assert is_image_capability_error(HttpError(text)) is expected


async def test_unknown_candidate_retries_with_description():
    main = FakeModel()
    calls = 0

    async def behavior():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HttpError(f"This model does not support image input")
        return response(f"Answer from main")

    main.behavior = behavior
    model, vision = wrapped(main, None)
    cache = get_capability_cache()
    cache.forget(main.model_key, f"rejects_image")
    try:
        result = await model(messages())
        assert result.content[0].text == f"Answer from main"
        assert len(vision.calls) == 1
        assert len(main.calls) == 2
        assert main.calls[0][0].content[1].type == f"data"
        assert all(b.type == f"text" for b in main.calls[1][0].content)
    finally:
        cache.forget(main.model_key, f"rejects_image")


async def test_model_fallback_selects_descriptions_per_candidate():
    primary = FakeModel(HttpError(f"HTTP 503"))
    primary.behavior.status_code = 503
    primary.model_key = f"fixture:primary"
    text = FakeModel()
    native = VisionFallbackChatModel(
        primary,
        supports_image=True,
        capability_error=is_image_capability_error,
    )
    target, vision = wrapped(text, False)
    native.vision_context = target.vision_context
    chain = FallbackChatModel([native, target])
    msgs = messages()
    await chain(messages=msgs)
    assert len(vision.calls) == 1
    assert primary.calls[0][0].content[1].type == f"data"
    assert all(b.type == f"text" for b in text.calls[0][0].content)
    assert await chain.count_tokens(msgs, None) == await native.count_tokens(
        msgs,
        None,
    )
    assert len(vision.calls) == 1


async def test_scroll_refreshes_descriptions_added_after_tool_persistence(
    tmp_path,
):
    block = image()
    tool = ToolResultBlock(
        id=f"late-image",
        name=f"view_image",
        output=[block],
        state=ToolResultState.SUCCESS,
    )
    msg = Msg(
        name=f"agent",
        role=f"assistant",
        content=[
            ToolCallBlock(id=f"late-image", name=f"view_image", input=f"{{}}"),
            tool,
        ],
    )
    agent = SimpleNamespace(state=SimpleNamespace(context=[msg]))
    history = HistoryStore(tmp_path / f"history.db")
    manager = ScrollContextManager(
        history=history,
        session_id=f"vision",
        agent_id=f"default",
    )
    try:
        manager._persist_new(agent)
        ctx, model = context()
        await ctx.prepare([msg])
        manager._persist_new(agent)
        row = history._conn.execute(
            f"SELECT content, metadata FROM conversation_history "
            f"WHERE kind = 'tool_result'",
        ).fetchone()
        assert f"red rectangle" in row[f"content"]
        assert VISION_DESCRIPTION_KEY in row[f"metadata"]
        identity = history._conn.execute(
            f"SELECT tool_call_id, name, tool_state "
            f"FROM conversation_history WHERE kind = 'tool_result'",
        ).fetchone()
        assert identity[f"tool_call_id"] == f"late-image"
        assert identity[f"name"] == f"view_image"
        assert identity[f"tool_state"] == f"success"
        snapshot = manager.to_dict()
        manager.load_state(snapshot)
        manager._persist_new(agent)
        assert history.count(f"vision") == 2
        assert len(model.calls) == 1
    finally:
        history.close()


async def test_session_state_restores_cache_without_vision_call():
    ctx, model = context()
    agent = object.__new__(QwenPawAgent)
    agent.state = AgentState()
    agent.state.context = messages()
    agent.state.middle_context[f"qwenpaw_vision_cache"] = ctx.cache
    agent._context_manager = None
    await ctx.prepare(agent.state.context)
    saved = agent.state_dict()
    restored = object.__new__(QwenPawAgent)
    restored._context_manager = None
    restored.load_state_dict(saved)
    repeated, second = context(
        cache=restored.state.middle_context[f"qwenpaw_vision_cache"],
    )
    await repeated.prepare(restored.state.context)
    assert not second.calls
    assert len(model.calls) == 1
    assert len(restored.state.context[0].content) == 3


async def test_stream_capability_failure_retries_before_output_only():
    main = FakeModel()
    attempts = 0
    closed = []

    async def behavior():
        nonlocal attempts
        attempts += 1
        number = attempts

        async def stream():
            try:
                if number == 1:
                    raise HttpError(f"This model does not support image input")
                yield response(f"stream answer")
            finally:
                closed.append(number)

        return stream()

    main.behavior = behavior
    main.model_key = f"fixture:stream"
    model, vision = wrapped(main, None)
    cache = get_capability_cache()
    try:
        stream = await model(messages())
        outputs = [chunk async for chunk in stream]
        assert outputs[-1].content[0].text == f"stream answer"
        assert len(vision.calls) == 1
        assert closed == [1, 2]
    finally:
        cache.forget(main.model_key, f"rejects_image")


async def test_plain_text_error_does_not_learn_image_rejection():
    main = FakeModel(HttpError(f"This model does not support image input"))
    main.model_key = f"fixture:plain"
    model, vision = wrapped(main, None)
    with pytest.raises(HttpError):
        await model(
            [
                Msg(
                    name=f"user",
                    role=f"user",
                    content=[TextBlock(text=f"Hello")],
                )
            ]
        )
    assert not vision.calls
    assert not get_capability_cache().get(
        main.model_key,
        f"rejects_image",
        False,
    )


async def test_persisted_description_survives_cache_eviction():
    ctx, first = context()
    msgs = messages()
    await ctx.prepare(msgs)
    before = msgs[0].model_dump()
    ctx.cache.clear()
    resumed, second = context()
    await resumed.prepare(msgs)
    assert not second.calls
    assert len(first.calls) == 1
    assert msgs[0].model_dump() == before


async def test_same_local_path_with_changed_bytes_is_not_cached(tmp_path):
    path = tmp_path / f"fixture.png"
    ctx, model = context()
    for color in (f"red", f"blue"):
        Image.new(f"RGB", (20, 20), color).save(path)
        msgs = messages(
            DataBlock(
                source=URLSource(
                    url=path.as_uri(),
                    media_type=f"image/png",
                )
            )
        )
        await ctx.prepare(msgs)
        assert msgs[0].content[1].source.type == f"base64"
    assert len(model.calls) == 2


async def test_remote_image_is_frozen_and_reused(monkeypatch):
    from qwenpaw.agents.tools import view_media

    data = base64.b64decode(image().source.data)
    download = AsyncMock(return_value=(data, None))
    monkeypatch.setattr(view_media, f"_download_remote_image", download)
    ctx, model = context()
    msgs = messages(
        DataBlock(
            source=URLSource(
                url=f"https://example.com/image.png",
                media_type=f"image/png",
            )
        )
    )
    await ctx.prepare(msgs)
    await ctx.prepare(msgs)
    assert download.await_count == 1
    assert len(model.calls) == 1
    assert msgs[0].content[1].source.type == f"base64"


async def test_cache_is_invalidated_when_visual_model_changes():
    ctx, first = context()
    msgs = messages()
    await ctx.prepare(msgs)
    other, second = context(cache=ctx.cache)
    other.config.vision_model = f"different-vision"
    await other.prepare(msgs)
    assert len(first.calls) == len(second.calls) == 1
    assert len(msgs[0].content) == 3
