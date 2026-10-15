# -*- coding: utf-8 -*-
"""Exercise image descriptions through an isolated app and real HTTP models."""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest
from PIL import Image

from tests.integration.helpers import (
    create_agent,
    delete_agent_quietly,
    scoped,
)


class VisionHandler(BaseHTTPRequestHandler):
    """Record model requests and answer with deterministic image evidence."""

    def log_message(self, _format, *args):
        pass

    def do_GET(self):
        data = json.dumps(
            {
                f"data": [
                    {f"id": f"fixture-text", f"object": f"model"},
                    {f"id": f"fixture-vision", f"object": f"model"},
                ]
            }
        ).encode()
        self.send_response(200)
        self.send_header(f"Content-Type", f"application/json")
        self.send_header(f"Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(
            self.rfile.read(int(self.headers[f"Content-Length"]))
        )
        self.server.requests.append(body)
        serialized = json.dumps(body.get(f"messages", []))
        if body[f"model"] == f"fixture-vision":
            text = (
                f"VISION_DESCRIPTION: red rectangle left; blue circle right."
                if f"image_url" in serialized
                else f"FAIL_NO_IMAGE"
            )
        else:
            text = (
                f"PASS_TEXT_MAIN: red rectangle left; blue circle right."
                if f"VISION_DESCRIPTION" in serialized
                and f"image_url" not in serialized
                else f"TEXT_WITHOUT_VISION"
            )
        response = {
            f"id": f"fixture-{time.time_ns()}",
            f"object": f"chat.completion",
            f"created": int(time.time()),
            f"model": body[f"model"],
            f"choices": [
                {
                    f"index": 0,
                    f"message": {f"role": f"assistant", f"content": text},
                    f"finish_reason": f"stop",
                }
            ],
            f"usage": {
                f"prompt_tokens": 20,
                f"completion_tokens": 10,
                f"total_tokens": 30,
            },
        }
        if body.get(f"stream"):
            chunk = {
                **response,
                f"object": f"chat.completion.chunk",
                f"choices": [
                    {
                        f"index": 0,
                        f"delta": {
                            f"role": f"assistant",
                            f"content": text,
                        },
                        f"finish_reason": None,
                    }
                ],
            }
            final = {
                **chunk,
                f"choices": [
                    {f"index": 0, f"delta": {}, f"finish_reason": f"stop"}
                ],
            }
            data = (
                f"data: {json.dumps(chunk)}\n\n"
                f"data: {json.dumps(final)}\n\n"
                f"data: [DONE]\n\n"
            ).encode()
            content_type = f"text/event-stream"
        else:
            data = json.dumps(response).encode()
            content_type = f"application/json"
        self.send_response(200)
        self.send_header(f"Content-Type", content_type)
        self.send_header(f"Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope=f"module")
def vision_endpoint():
    server = ThreadingHTTPServer((f"127.0.0.1", 0), VisionHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.integration
@pytest.mark.p1
def test_config_roundtrip_and_invalid_selection(app_server):
    agent_id = f"integ_vision_config"
    create_agent(app_server, agent_id)
    path = scoped(agent_id, f"/workspace/running-config")
    try:
        baseline = app_server.api_request(f"GET", path).json()
        assert baseline[f"multimodal_fallback"][f"enabled"] is False
        invalid = {**baseline, f"multimodal_fallback": {f"enabled": True}}
        rejected = app_server.api_request(f"PUT", path, json=invalid)
        assert rejected.status_code == 422
        config = {
            f"enabled": True,
            f"vision_provider": f"fixture",
            f"vision_model": f"vision",
            f"max_images_per_turn": 3,
            f"description_max_tokens": 512,
            f"timeout_seconds": 20,
        }
        saved = app_server.api_request(
            f"PUT",
            path,
            json={**baseline, f"multimodal_fallback": config},
            timeout=60,
        )
        assert saved.status_code == 200, app_server.logs_tail()
        readback = app_server.api_request(f"GET", path)
        assert readback.json()[f"multimodal_fallback"] == config
        other = app_server.api_request(
            f"GET",
            f"/api/workspace/running-config",
        )
        assert other.json()[f"multimodal_fallback"][f"enabled"] is False
    finally:
        delete_agent_quietly(app_server, agent_id)


@pytest.mark.integration
@pytest.mark.p1
def test_console_image_uses_vision_and_keeps_text_main(
    app_server,
    vision_endpoint,
):
    agent_id = f"integ_vision_chat"
    provider_id = f"integ-vision"
    port = vision_endpoint.server_address[1]
    provider = app_server.api_request(
        f"POST",
        f"/api/models/custom-providers",
        json={
            f"id": provider_id,
            f"name": f"Vision fixture",
            f"default_base_url": f"http://127.0.0.1:{port}/v1",
            f"api_key": f"local-fixture",
            f"models": [
                {
                    f"id": f"fixture-text",
                    f"name": f"Text main",
                    f"supports_image": False,
                    f"supports_multimodal": False,
                },
                {
                    f"id": f"fixture-vision",
                    f"name": f"Vision assistant",
                    f"supports_image": True,
                    f"supports_multimodal": True,
                },
            ],
        },
        timeout=60,
    )
    assert provider.status_code == 201, provider.text
    create_agent(app_server, agent_id)
    try:
        active = app_server.api_request(
            f"PUT",
            f"/api/models/active",
            json={
                f"scope": f"agent",
                f"agent_id": agent_id,
                f"provider_id": provider_id,
                f"model": f"fixture-text",
            },
            timeout=60,
        )
        assert active.status_code == 200, active.text
        path = scoped(agent_id, f"/workspace/running-config")
        running = app_server.api_request(f"GET", path).json()
        running[f"multimodal_fallback"] = {
            f"enabled": True,
            f"vision_provider": provider_id,
            f"vision_model": f"fixture-vision",
        }
        running[f"auto_title_config"][f"enabled"] = False
        saved = app_server.api_request(
            f"PUT",
            path,
            json=running,
            timeout=60,
        )
        assert saved.status_code == 200, saved.text
        png = BytesIO()
        Image.new(f"RGB", (20, 20), f"red").save(png, format=f"PNG")
        encoded = base64.b64encode(png.getvalue()).decode(f"ascii")
        content = [
            {f"type": f"text", f"text": f"Describe this attached image."},
            {
                f"type": f"image",
                f"image_url": f"data:image/png;base64,{encoded}",
            },
        ]
        request = {
            f"channel": f"console",
            f"user_id": f"vision-user",
            f"session_id": f"vision-acceptance",
            f"input": [
                {f"role": f"user", f"type": f"message", f"content": content}
            ],
        }
        output = app_server.api_request(
            f"POST",
            scoped(agent_id, f"/console/chat"),
            json=request,
            timeout=90,
        )
        assert output.status_code == 200, app_server.logs_tail()
        assert f"PASS_TEXT_MAIN" in output.text, app_server.logs_tail(12000)
        vision = [
            body
            for body in vision_endpoint.requests
            if body[f"model"] == f"fixture-vision"
        ]
        main = [
            body
            for body in vision_endpoint.requests
            if body[f"model"] == f"fixture-text"
        ]
        assert len(vision) == 1
        assert main
        assert vision[0][f"stream"] is False
        assert (
            vision[0].get(
                f"max_tokens",
                vision[0].get(f"max_completion_tokens"),
            )
            == 1024
        )
        assert f"image_url" in json.dumps(vision[0][f"messages"])
        assert f"VISION_DESCRIPTION" in json.dumps(main[-1][f"messages"])
        assert f"image_url" not in json.dumps(main[-1][f"messages"])
        current = app_server.api_request(
            f"GET",
            f"/api/models/active",
            params={
                f"scope": f"agent",
                f"agent_id": agent_id,
            },
        )
        assert current.json()[f"active_llm"][f"model"] == f"fixture-text"
        request[f"input"][0][f"content"] = [
            {f"type": f"text", f"text": f"Describe the same image again."},
        ]
        repeated = app_server.api_request(
            f"POST",
            scoped(agent_id, f"/console/chat"),
            json=request,
            timeout=90,
        )
        assert f"PASS_TEXT_MAIN" in repeated.text, app_server.logs_tail(12000)
        assert (
            sum(
                body[f"model"] == f"fixture-vision"
                for body in vision_endpoint.requests
            )
            == 1
        )
    finally:
        delete_agent_quietly(app_server, agent_id)
        app_server.api_request(
            f"DELETE",
            f"/api/models/custom-providers/{provider_id}",
        )
