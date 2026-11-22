"""Current Core ledger wire projections, including redacted evidence and cursors."""

import json

import httpx
import pytest

from projectdavid.clients.runs import RunsClient

CASES = [
    (
        "get_execution",
        "execution",
        "epoch_next",
        {
            "id": "epoch_1",
            "run_id": "run_root",
            "root_run_id": "run_root",
            "epoch_number": 1,
            "state": "completed",
            "created_at": 1,
            "actors": [
                {
                    "id": "actor_1",
                    "epoch_id": "epoch_1",
                    "slot": "root",
                    "execution_role": "supervisor",
                    "ephemeral": False,
                    "state": "retired",
                    "reserved_at": 1,
                }
            ],
        },
    ),
    (
        "list_delegations",
        "delegations",
        "delegation_next",
        {
            "id": "delegation_1",
            "root_run_id": "run_root",
            "parent_epoch_id": "epoch_1",
            "parent_run_id": "run_root",
            "parent_action_id": "action_1",
            "child_epoch_id": "epoch_2",
            "child_run_id": "run_child",
            "created_at": 1,
        },
    ),
    (
        "list_execution_events",
        "execution-events",
        42,
        {
            "id": 42,
            "epoch_id": "epoch_1",
            "origin_run_id": "run_root",
            "event_type": "execution_started",
            "schema_version": 1,
            "evidence_class": "metadata",
            "occurred_at_us": 1234567890123456,
            "recorded_at_us": 1234567890123457,
            "details": {"state": "running"},
            "evidence_ref": None,
        },
    ),
]


@pytest.mark.parametrize("method,path,cursor,item", CASES)
def test_ledger_wire_contract_and_pagination(method, path, cursor, item):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "root_run_id": "run_root",
                "data": [item],
                "has_more": True,
                "next_cursor": cursor,
            },
        )

    with RunsClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        client.client.close()
        client.client = httpx.Client(
            base_url=client.base_url,
            headers={"X-API-Key": client.api_key},
            transport=httpx.MockTransport(handler),
        )
        page = getattr(client, method)("run_root", limit=2, after=cursor)
    assert page.has_more and page.next_cursor == cursor
    assert page.root_run_id == "run_root"
    assert page.data[0].id == item["id"]
    for key, value in item.items():
        if key != "actors":
            assert page.data[0].model_dump()[key] == value
    assert requests[0].url.path == f"/v1/runs/run_root/{path}"
    assert dict(requests[0].url.params) == {"limit": "2", "after": str(cursor)}
    assert requests[0].headers["X-API-Key"] == "platform-test-key"
    assert "evidence/" not in str(requests[0].url)


@pytest.mark.parametrize("method,path,cursor,item", CASES)
def test_ledger_owner_access_failures_propagate(method, path, cursor, item):
    with RunsClient(
        base_url="https://core.test", api_key="platform-test-key"
    ) as client:
        client.client.close()
        client.client = httpx.Client(
            base_url=client.base_url,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(404, json={"detail": "Not found"})
            ),
        )
        with pytest.raises(httpx.HTTPStatusError):
            getattr(client, method)("run_other_owner")
