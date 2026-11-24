import json

import pytest

from projectdavid.clients.synchronous_inference_wrapper import (
    SynchronousInferenceStream,
)
from projectdavid.events import WebStatusEvent


@pytest.fixture
def stream():
    instance = SynchronousInferenceStream(inference=None)
    instance.run_id = "run_parent"
    return instance


@pytest.fixture
def payload():
    return {
        "type": "web_status",
        "run_id": "run_parent",
        "status": "success",
        "tool": "read_web_page",
        "message": "Content retrieved successfully.",
        "tool_call_id": "call_123",
        "origin_run_id": "run_worker",
        "url": "https://docs.python.org/3/",
        "favicon": "data:image/png;base64,AA==",
    }


def test_legacy_web_status_constructor():
    event = WebStatusEvent(
        "run_parent",
        "running",
        "Reading page...",
        "read_web_page",
    )

    assert event.status == "running"
    assert event.tool_call_id is None
    assert event.origin_run_id is None
    assert event.url is None
    assert event.favicon is None


def test_legacy_web_status_mapping(stream):
    event = stream._map_chunk_to_event(
        {
            "type": "web_status",
            "status": "running",
            "tool": "read_web_page",
        }
    )

    assert isinstance(event, WebStatusEvent)
    assert event.run_id == "run_parent"
    assert event.favicon is None
    assert event.url is None


def test_web_status_metadata_round_trip(stream, payload):
    event = stream._map_chunk_to_event(payload)

    assert isinstance(event, WebStatusEvent)
    assert event.to_dict() == payload


def test_web_status_embedded_json(stream, payload):
    event = stream._map_chunk_to_event(
        {
            "type": "content",
            "content": json.dumps(payload),
        }
    )

    assert isinstance(event, WebStatusEvent)
    assert event.to_dict() == payload


def test_web_status_delegation_envelope(stream, payload):
    event = stream._map_chunk_to_event(
        {
            "stream_type": "delegation",
            "chunk": payload.copy(),
        }
    )

    assert isinstance(event, WebStatusEvent)
    assert event.to_dict() == payload


def test_web_status_preserves_worker_identity(stream, payload):
    event = stream._map_chunk_to_event(payload)

    assert event.run_id == "run_parent"
    assert event.origin_run_id == "run_worker"
    assert event.tool_call_id == "call_123"


def test_terminal_error_mapping_unchanged(stream):
    event = stream._map_chunk_to_event(
        {
            "type": "error",
            "message": "Inference failed.",
        }
    )

    assert isinstance(event, WebStatusEvent)
    assert event.status == "failed"
    assert event.message == "Inference failed."
    assert event.favicon is None
