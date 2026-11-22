import asyncio
import builtins
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import numpy as np
import pytest
from projectdavid_common import ValidationInterface as V

from projectdavid.clients.vectors import VectorStoreClient


def store():
    return V.VectorStoreRead(
        id="store",
        name="test",
        user_id="owner",
        collection_name="collection",
        vector_size=2,
        distance_metric="COSINE",
        config={},
        status="active",
        file_count=0,
        created_at=1,
    )


@pytest.fixture
def client():
    client = VectorStoreClient(base_url="http://localhost:80", api_key="secret")
    yield client
    client.close()


def test_constructor_never_opens_qdrant(monkeypatch):
    import qdrant_client

    constructor = Mock(side_effect=AssertionError("Qdrant connection forbidden"))
    monkeypatch.setattr(qdrant_client, "QdrantClient", constructor)
    with pytest.warns(DeprecationWarning, match="server-owned"):
        client = VectorStoreClient(
            base_url="http://localhost:80",
            vector_store_host="unreachable",
            file_processor_kwargs={"chunk_size": 99},
        )
    assert client.file_processor._requested_chunk_size == 99
    assert client.file_processor._embedding_model is None
    constructor.assert_not_called()
    assert not hasattr(client, "vector_manager")
    client.close()


@pytest.mark.parametrize("admin", [False, True])
def test_create_is_http_only(client, admin):
    client._request = AsyncMock(return_value=store().model_dump(mode="json"))
    result = (
        client.create_vector_store_for_user("owner", "test", vector_size=2)
        if admin
        else client.create_vector_store("test", vector_size=2)
    )
    assert result.id == "store"
    assert client._request.call_args.args == ("POST", "/v1/vector-stores")
    assert client._request.call_args.kwargs["json"]["vector_size"] == 2


def test_add_file_processes_locally_and_posts_vectors_with_metadata(client, tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("local text")
    events = []

    async def process(p):
        events.append("embed")
        assert p == path
        return {
            "chunks": ["local text"],
            "vectors": [[1.0, 0.0]],
            "line_data": [{"line_start": 1}],
        }

    client.file_processor.process_file = process

    async def request(method, route, **kw):
        events.append("http")
        assert route == "/v1/vector-stores/store/vectors"
        payload = kw["json"]
        assert payload["vectors"] == [[1.0, 0.0]]
        assert payload["metadata"][0]["file_path"] == str(path)
        assert payload["metadata"][0]["line_start"] == 1
        record = {
            **payload["file"],
            "id": payload["file"]["file_id"],
            "vector_store_id": "store",
        }
        return {"status": "success", "points_inserted": 1, "file": record}

    client._request = request
    result = client.add_file_to_vector_store("store", path, {"custom": "value"})
    assert result.file_path == str(path)
    assert events == ["embed", "http"]


def test_search_embeds_locally_then_posts_query_vector(client):
    client.retrieve_vector_store_sync = Mock(return_value=store())
    client.file_processor.encode_text = Mock(return_value=np.array([1.0, 0.0]))
    hits = [
        {
            "id": "p",
            "vector_id": "p",
            "score": 0.9,
            "text": "x",
            "metadata": {},
            "meta_data": {},
        }
    ]
    client._request = AsyncMock(return_value=hits)
    with pytest.warns(DeprecationWarning):
        result = client.vector_file_search_raw(
            "store", "local query", filters={"must": []}, vector_store_host="forbidden"
        )
    client.file_processor.encode_text.assert_called_once_with("local query")
    client._request.assert_awaited_once_with(
        "POST",
        "/v1/vector-stores/store/search",
        json={
            "query_vector": [1.0, 0.0],
            "top_k": 5,
            "filters": {"must": []},
            "vector_field": None,
        },
    )
    assert result == hits


@pytest.mark.parametrize("permanent", [False, True])
def test_store_delete_only_http(client, permanent):
    client._request = AsyncMock(return_value=None)
    result = client.delete_vector_store("store", permanent)
    client._request.assert_awaited_once_with(
        "DELETE", "/v1/vector-stores/store", params={"permanent": permanent}
    )
    assert result["permanent"] is permanent


def test_file_delete_only_http(client):
    client._request = AsyncMock(return_value=None)
    client.delete_file_from_vector_store("store", "file.txt")
    client._request.assert_awaited_once_with(
        "DELETE", "/v1/vector-stores/store/files", params={"file_path": "file.txt"}
    )


def test_missing_embeddings_does_not_affect_http_operations(client, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kw):
        if name.startswith("sentence_transformers"):
            raise ModuleNotFoundError(
                "missing embeddings", name="sentence_transformers"
            )
        return original(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", guarded)
    client._request = AsyncMock(return_value=store().model_dump(mode="json"))
    assert client.create_vector_store("test", vector_size=2).id == "store"
    client.retrieve_vector_store_sync = Mock(return_value=store())
    with pytest.raises(ImportError, match=r"projectdavid\[embeddings\]"):
        client.vector_file_search_raw("store", "query")


def test_non_rag_sdk_without_ml_imports():
    code = """
import sys
class NoML:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'sentence_transformers', 'torch'}:
            raise AssertionError('ML imported by normal SDK: ' + fullname)
sys.meta_path.insert(0, NoML())
from projectdavid import Entity
from projectdavid.clients.vectors import VectorStoreClient
client = VectorStoreClient(base_url='http://localhost:80', api_key='key')
assert client.file_processor._embedding_model is None
client.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_post_not_retried_to_prevent_duplicate_vectors(client, monkeypatch):
    calls = []

    class Transport:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def request(self, *a, **kw):
            calls.append(a)
            raise httpx.ReadTimeout("response lost")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Transport())
    from projectdavid.clients.vectors import VectorStoreClientError

    with pytest.raises(VectorStoreClientError):
        asyncio.run(client._request("POST", "/v1/vector-stores/store/vectors", json={}))
    assert len(calls) == 1


def test_embeddings_extra_is_declared():
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.optional-dependencies]" in pyproject_text
    assert 'embeddings = ["sentence-transformers>=3.0,<6.0"]' in pyproject_text

    dependencies_block = pyproject_text.split("[project.optional-dependencies]", 1)[0]

    assert "sentence-transformers" not in dependencies_block
    assert '"torch' not in dependencies_block


def test_http_transport_uses_gateway_and_authentication(monkeypatch):
    monkeypatch.setenv("PROJECTDAVID_BASE_URL", "http://localhost:80")
    client = VectorStoreClient(api_key="secret")
    original = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    assert client.list_my_vector_stores() == []
    assert len(requests) == 1
    assert requests[0].url == httpx.URL("http://localhost/v1/vector-stores")
    assert requests[0].headers["X-API-Key"] == "secret"
    client.close()


def test_file_processor_encode_does_not_pass_unsupported_truncate_kwarg():
    import asyncio

    import numpy as np

    from projectdavid.clients.file_processor import FileProcessor

    class FakeEmbeddingModel:
        def __init__(self):
            self.calls = []

        def encode(self, texts, **kwargs):
            if "truncate" in kwargs:
                raise AssertionError(
                    "FileProcessor passed unsupported 'truncate' kwarg"
                )

            self.calls.append(
                {
                    "texts": texts,
                    "kwargs": kwargs,
                }
            )

            return np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

    processor = FileProcessor(max_workers=1)
    model = FakeEmbeddingModel()
    processor._embedding_model = model

    try:
        sync_vector = processor.encode_text("sync embedding probe")

        async_vector = asyncio.run(
            processor._encode_chunk_async("async embedding probe")
        )

        assert sync_vector.shape == (3,)
        assert async_vector.shape == (3,)

        assert len(model.calls) == 2

        sync_call = model.calls[0]
        async_call = model.calls[1]

        assert sync_call["kwargs"]["convert_to_numpy"] is True
        assert sync_call["kwargs"]["normalize_embeddings"] is True
        assert "truncate" not in sync_call["kwargs"]

        assert async_call["kwargs"]["convert_to_numpy"] is True
        assert async_call["kwargs"]["normalize_embeddings"] is True
        assert async_call["kwargs"]["show_progress_bar"] is False
        assert "truncate" not in async_call["kwargs"]
    finally:
        processor._executor.shutdown(wait=True)
