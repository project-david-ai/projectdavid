from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from projectdavid_common.validation import StatusEnum

from projectdavid.clients.runs import RunsClient


def make_client():
    transport = Mock()
    transport.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://core/v1/runs"),
        json={"object": "list", "data": [], "has_more": False},
    )
    return SimpleNamespace(client=transport)


def test_list_all_runs_preserves_existing_positional_arguments():
    client = make_client()
    page = RunsClient.list_all_runs(client, 5, "desc")
    client.client.get.assert_called_once_with(
        "/v1/runs", params={"limit": 5, "order": "desc"}
    )
    assert page.data == []
    assert page.has_more is False


@pytest.mark.parametrize("status", ["completed", StatusEnum.completed, "failed"])
def test_list_all_runs_forwards_status(status):
    client = make_client()
    RunsClient.list_all_runs(client, limit=1, status=status)
    client.client.get.assert_called_once_with(
        "/v1/runs",
        params={
            "limit": 1,
            "order": "asc",
            "status": StatusEnum(status).value,
        },
    )


def test_list_all_runs_rejects_invalid_status_before_request():
    client = make_client()
    with pytest.raises(ValueError):
        RunsClient.list_all_runs(client, status="invalid")
    client.client.get.assert_not_called()


def test_list_all_runs_propagates_core_http_error():
    client = make_client()
    client.client.get.return_value = httpx.Response(
        422, request=httpx.Request("GET", "http://core/v1/runs")
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        RunsClient.list_all_runs(client, status="completed")
    assert exc.value.response.status_code == 422
