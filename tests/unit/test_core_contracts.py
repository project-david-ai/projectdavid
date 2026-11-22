"""Offline regressions for the protected Assistant and inference contracts."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from projectdavid import Entity
from projectdavid.clients.assistants_client import AssistantsClient
from projectdavid.clients.inference_client import InferenceClient
from projectdavid.clients.runs import RunsClient
from projectdavid.clients.synchronous_inference_wrapper import (
    SynchronousInferenceStream,
)
from projectdavid.events import ContentEvent, ToolCallRequestEvent, WebStatusEvent

MODEL = "hyperbolic/deepseek-v4-flash-0731"
REQUEST = dict(
    model=MODEL,
    thread_id="thread_test",
    message_id="message_test",
    run_id="run_test",
    assistant_id="asst_core",
)
ASSISTANT = dict(
    id="asst_core",
    object="assistant",
    created_at=1,
    name="Playground",
    model=MODEL,
    tools=[],
    top_p=1.0,
    temperature=1.0,
    response_format="auto",
    max_turns=1,
    agent_mode=False,
    web_access=False,
    deep_research=False,
    engineer=False,
    decision_telemetry=False,
)


def client_with_transport(cls, handler):
    client = cls(base_url="https://core.test", api_key="platform-test-key")
    headers = client.client.headers
    client.client.close()
    client.client = httpx.Client(
        base_url=client.base_url,
        headers=headers,
        transport=httpx.MockTransport(handler),
    )
    return client


def install_async_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )


def collect(client, **overrides):
    async def consume():
        return [
            chunk
            async for chunk in client.stream_inference_response(
                **{**REQUEST, **overrides}
            )
        ]

    return asyncio.run(consume())


def test_bootstrap_is_idempotent_and_uses_core_identity():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=ASSISTANT)

    with client_with_transport(AssistantsClient, handler) as client:
        assert client.bootstrap_playground_assistant(model=MODEL).id == "asst_core"
        assert client.bootstrap_playground_assistant(model=MODEL).id == "asst_core"
    assert len(requests) == 2
    for request in requests:
        assert request.method == "POST"
        assert request.url.path == "/v1/assistants/playground/bootstrap"
        assert json.loads(request.content) == {"model": MODEL}
        assert request.headers["X-API-Key"] == "platform-test-key"


@pytest.mark.parametrize("status", [401, 403])
def test_bootstrap_auth_errors_never_fall_back(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"detail": "Not authorized"})

    with client_with_transport(AssistantsClient, handler) as client:
        with pytest.raises(httpx.HTTPStatusError) as exc:
            client.bootstrap_playground_assistant(model=MODEL)
    assert exc.value.response.status_code == status
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/playground/bootstrap")
    assert "platform-test-key" not in str(exc.value)


@pytest.mark.parametrize("model", ["", "x" * 129, None])
def test_bootstrap_validates_before_http(model):
    handler = Mock()
    with client_with_transport(AssistantsClient, handler) as client:
        with pytest.raises(ValidationError):
            client.bootstrap_playground_assistant(model=model)
    handler.assert_not_called()


def make_stream(chunks, assistants):
    class Inference:
        async def stream_inference_response(self, **kwargs):
            for chunk in chunks:
                yield dict(chunk)

    stream = SynchronousInferenceStream.for_request(
        Inference(), Mock(), Mock(), Mock(), assistants
    )
    stream.setup(**{k: v for k, v in REQUEST.items() if k != "model"})
    return stream


def hidden_assistant():
    request = httpx.Request("GET", "https://core.test/v1/assistants/asst_core")
    response = httpx.Response(404, request=request)
    return Mock(
        retrieve_assistant=Mock(
            side_effect=httpx.HTTPStatusError(
                "hidden", request=request, response=response
            )
        )
    )


def test_hidden_toolless_assistant_can_stream_content():
    stream = make_stream([{"type": "content", "content": "hello"}], hidden_assistant())
    events = list(stream.stream_events(model=MODEL))
    assert len(events) == 1
    assert isinstance(events[0], ContentEvent)
    assert events[0].content == "hello"


def test_hidden_assistant_tool_calls_cannot_bypass_validation():
    stream = make_stream(
        [{"type": "tool_call_manifest", "tool": "weather", "args": {}}],
        hidden_assistant(),
    )
    with pytest.raises(ValueError, match="Cannot validate tool call"):
        list(stream.stream_events(model=MODEL))
    stream.messages_client.submit_tool_output.assert_not_called()


@pytest.mark.parametrize("args, valid", [({}, False), ({"city": "Accra"}, True)])
def test_normal_assistant_tool_validation(args, valid):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    assistants = Mock(
        retrieve_assistant=Mock(return_value=SimpleNamespace(tools=tools))
    )
    stream = make_stream(
        [
            {
                "type": "tool_call_manifest",
                "tool": "weather",
                "args": args,
                "action_id": "action_test",
            }
        ],
        assistants,
    )
    events = list(stream.stream_events(model=MODEL, max_turns=1))
    if valid:
        assert len(events) == 1 and isinstance(events[0], ToolCallRequestEvent)
        stream.messages_client.submit_tool_output.assert_not_called()
    else:
        assert events == []
        assert (
            "city"
            in stream.messages_client.submit_tool_output.call_args.kwargs["content"]
        )


def test_entity_returns_isolated_stream_state():
    entity = Entity(base_url="https://core.test", api_key="platform-test-key")
    for attr in (
        "_inference_client",
        "_runs_client",
        "_actions_client",
        "_messages_client",
        "_assistants_client",
    ):
        setattr(entity, attr, Mock())
    first, second = (
        entity.synchronous_inference_stream,
        entity.synchronous_inference_stream,
    )
    first.setup("thread_a", "asst_a", "message_a", "run_a", meta_data={"a": 1})
    second.setup("thread_b", "asst_b", "message_b", "run_b")
    first.validator.build_registry_from_assistant(
        [
            {
                "type": "function",
                "function": {"name": "weather", "parameters": {"required": ["city"]}},
            }
        ]
    )
    assert first is not second
    assert (first.run_id, second.run_id) == ("run_a", "run_b")
    assert second.meta_data is None
    assert second.validator.schema_registry == {}


@pytest.mark.parametrize("override", [None, "provider/override"])
def test_run_model_is_resolved_by_core_and_used_for_inference(monkeypatch, override):
    persisted = {}

    def runs_handler(request):
        payload = json.loads(request.content)
        assert ("model" in payload) == (override is not None)
        assert payload["meta_data"] == {"source": "test"}
        assert "truncation_strategy" not in payload
        persisted.update(payload, model=payload.get("model", MODEL))
        # Core's read response includes nullable fields omitted from RunCreate.
        persisted.update(
            cancelled_at=None,
            completed_at=None,
            failed_at=None,
            incomplete_details=None,
            last_error=None,
            required_action=None,
            started_at=None,
            usage=None,
            tool_resources={},
        )
        return httpx.Response(200, json=persisted)

    with client_with_transport(RunsClient, runs_handler) as client:
        run = client.create_run(
            "asst_core", "thread_test", model=override, meta_data={"source": "test"}
        )
    assert run.model == (override or MODEL)

    def inference_handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == persisted["model"]
        assert payload["run_id"] == run.id
        return httpx.Response(
            200, json={"type": "content", "content": "answer", "model": run.model}
        )

    install_async_transport(monkeypatch, inference_handler)
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        assert (
            collect(client, model=run.model, run_id=run.id, stream=False)[0]["content"]
            == "answer"
        )


@pytest.mark.parametrize("stream", [True, False])
def test_stateful_credentials_and_content(monkeypatch, stream):
    def handler(request):
        assert request.url.path == "/v1/completions"
        assert request.headers["X-API-Key"] == "platform-test-key"
        payload = json.loads(request.content)
        assert payload == {**REQUEST, "api_key": "provider-test-key", "stream": stream}
        if stream:
            return httpx.Response(
                200,
                text=': heartbeat\n\nevent: message\ndata: {"type":"content","content":"hello"}\n\ndata: {"type":"status","status":"complete"}\n\ndata: [DONE]\n\ndata: {"type":"content","content":"ignored"}\n',
            )
        return httpx.Response(
            200, json={"content": "hello", "type": "content", "model": MODEL}
        )

    install_async_transport(monkeypatch, handler)
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        chunks = collect(client, stream=stream, api_key="provider-test-key")
    assert chunks[0]["content"] == "hello"
    if stream:
        assert chunks[1] == {"type": "status", "status": "complete"}
        assert len(chunks) == 2


@pytest.mark.parametrize("status", [401, 403, 409, 500])
@pytest.mark.parametrize("stream", [True, False])
def test_inference_http_errors_propagate(monkeypatch, status, stream):
    install_async_transport(
        monkeypatch, lambda request: httpx.Response(status, json={"detail": "error"})
    )
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        with pytest.raises(httpx.HTTPStatusError) as exc:
            collect(client, stream=stream)
    assert exc.value.response.status_code == status


def test_raw_sse_error_maps_to_failure_without_content(monkeypatch):
    install_async_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            text='data: {"type":"error","message":"missing run_id"}\n\ndata: [DONE]\n',
        ),
    )
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        stream = SynchronousInferenceStream(client)
        stream.setup(**{k: v for k, v in REQUEST.items() if k != "model"})
        events = list(stream.stream_events(model=MODEL))
    assert len(events) == 1 and isinstance(events[0], WebStatusEvent)
    assert events[0].status == "failed"
    assert events[0].message == "missing run_id"


def test_buffered_completion_contract(monkeypatch):
    install_async_transport(
        monkeypatch, lambda request: httpx.Response(200, json={"content": "hello"})
    )
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        completion = asyncio.run(client.create_completion(**REQUEST))
    assert completion["object"] == "chat.completion"
    assert completion["model"] == MODEL
    assert completion["choices"][0]["message"]["content"] == "hello"


def test_buffered_error_is_not_fabricated_content(monkeypatch):
    install_async_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"type": "error", "message": "failed"}
        ),
    )
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        assert collect(client, stream=False) == [{"type": "error", "message": "failed"}]
        with pytest.raises(ValueError, match="Inference failed"):
            asyncio.run(client.create_completion(**REQUEST))


def test_validation_errors_do_not_expose_provider_keys(caplog):
    with InferenceClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        with pytest.raises(ValidationError) as exc:
            collect(client, api_key={"secret": "provider-secret-value"})
    assert "provider-secret-value" not in str(exc.value)
    assert "provider-secret-value" not in exc.value.json()
    assert "provider-secret-value" not in caplog.text


@pytest.mark.parametrize(
    "chunk,event_type",
    [
        (
            {
                "stream_type": "code_execution",
                "chunk": {"type": "hot_code_output", "content": "result"},
            },
            "CodeExecutionOutputEvent",
        ),
        (
            {
                "stream_type": "delegation",
                "chunk": {"type": "content", "content": "delegate"},
            },
            "ContentEvent",
        ),
        ({"type": "shell_status", "activity": "running"}, "ShellStatusEvent"),
        (
            {
                "stream_type": "shell",
                "chunk": {"type": "computer_file", "filename": "out.txt"},
            },
            "ComputerGeneratedFileEvent",
        ),
        (
            {"type": "tool_intercept", "tool_name": "weather", "args": {}},
            "ToolInterceptEvent",
        ),
        (
            {"stream_type": "shell", "chunk": {"type": "content", "content": "pty"}},
            None,
        ),
    ],
)
def test_existing_execution_event_routing(chunk, event_type):
    stream = SynchronousInferenceStream(Mock())
    event = stream._map_chunk_to_event(chunk)
    assert (type(event).__name__ if event else None) == event_type
