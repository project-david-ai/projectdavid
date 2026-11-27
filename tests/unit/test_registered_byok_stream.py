from types import SimpleNamespace

import pytest

from projectdavid.clients.synchronous_inference_wrapper import (
    SynchronousInferenceStream,
)
from projectdavid.events import ContentEvent, ToolCallRequestEvent


class RecordingTransport:
    def __init__(self, *turns):
        self.turns = turns
        self.requests = []

    async def stream_inference_response(self, **kwargs):
        index = len(self.requests)
        self.requests.append(kwargs)
        for chunk in self.turns[index]:
            yield dict(chunk)


def setup_stream(transport, **kwargs):
    stream = SynchronousInferenceStream(transport)
    configure(stream, **kwargs)
    return stream


def configure(stream, **kwargs):
    stream.setup(
        thread_id="thread_test",
        assistant_id="asst_test",
        message_id="message_test",
        run_id="run_test",
        **kwargs,
    )


def test_registered_key_survives_managed_continuation():
    transport = RecordingTransport(
        [
            {
                "type": "tool_call_manifest",
                "tool": "test_tool",
                "args": {},
                "action_id": "act_test",
                "tool_call_id": "call_test",
            }
        ],
        [{"type": "content", "content": "done"}],
    )
    stream = setup_stream(transport, provider_key_id="pk_test")
    stream.validator = SimpleNamespace(validate_args=lambda *_: None)
    events = []
    for event in stream.stream_events(model="test/model"):
        events.append(event)
        if isinstance(event, ToolCallRequestEvent):
            # Simulate successful external execution; no network calls.
            event.executed = True

    assert len(transport.requests) == 2
    assert all(r["provider_key_id"] == "pk_test" for r in transport.requests)
    assert all(r["api_key"] is None for r in transport.requests)
    assert isinstance(events[-1], ContentEvent)
    assert events[-1].content == "done"


@pytest.mark.parametrize("key", [None, "direct-test-key"])
def test_existing_transport_contract_is_preserved(key):
    transport = RecordingTransport([{"type": "content", "content": "done"}])
    stream = setup_stream(transport, api_key=key)
    list(stream.stream_chunks(model="test/model"))
    assert transport.requests[0]["api_key"] == key
    assert "provider_key_id" not in transport.requests[0]


def test_setup_rejects_conflicting_credentials():
    transport = RecordingTransport()
    with pytest.raises(ValueError, match="not both"):
        setup_stream(transport, api_key="direct-test-key", provider_key_id="pk_test")
    assert not transport.requests


def test_raw_stream_rejects_conflicting_credential_override():
    transport = RecordingTransport()
    stream = setup_stream(transport, provider_key_id="pk_test")
    with pytest.raises(ValueError, match="not both"):
        list(stream.stream_chunks(model="test/model", api_key="direct-test-key"))
    assert not transport.requests


def test_setup_clears_previous_registered_credential():
    transport = RecordingTransport([{"type": "content", "content": "done"}])
    stream = setup_stream(transport, provider_key_id="pk_test")
    configure(stream)
    list(stream.stream_chunks(model="test/model"))
    assert "provider_key_id" not in transport.requests[0]
