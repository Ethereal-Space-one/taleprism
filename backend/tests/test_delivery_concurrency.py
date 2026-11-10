"""Final review must recheck production revisions inside the write transaction."""

import json

import pytest

# Reuse the synthetic, fully checked project; no cloud generation is involved.
from test_reliability_integration import compiled as compiled  # noqa: PLC0414 -- pytest fixture
from test_reliability_integration import export, request

from storygal.delivery import REVIEW_CHECKS


def review_records(client, pid):
    with client.app.state.store.db() as db:
        records = [
            json.loads(row[0])
            for row in db.execute("SELECT data FROM delivery_reviews WHERE project_id=?", (pid,))
        ]
        audits = db.execute(
            "SELECT COUNT(*) FROM review_audit WHERE project_id=? AND action='delivery.review'",
            (pid,),
        ).fetchone()[0]
    return records, audits


@pytest.mark.parametrize("decision", ["rejected", "revoked"])
@pytest.mark.parametrize("already_reviewed", [False, True])
def test_production_change_before_review_commit_is_conflict(
    compiled, monkeypatch, decision, already_reviewed
):
    client, prefix, _, _ = compiled
    pid = prefix.rsplit("/", 1)[1]
    job = export(client, prefix)
    assert job["state"] == "completed", job
    url = prefix + f"/exports/{job['id']}/review"
    payload = {"checks": {key: True for key in REVIEW_CHECKS}, "notes": "合成回归复核"}
    if already_reviewed:
        response = client.post(url, json=payload)
        assert response.status_code == 200, response.text
    before = review_records(client, pid)
    delivery = client.app.state.delivery
    versions = delivery.versions(pid, reader=True)
    editorial = client.app.state.reader.editorial
    original_state = editorial.state
    changed = False

    def state_then_change_production(project_id):
        nonlocal changed
        state = original_state(project_id)
        assert not changed
        # This hook runs after Delivery.accept's initial version comparison and
        # commits a second request before its BEGIN IMMEDIATE. No timing sleeps.
        request(
            client,
            prefix,
            "shot-0/continuity-check",
            decision=decision,
            notes="最终复核并发回归：检查已撤销，必须重新确认。",
        )
        changed = True
        return state

    with monkeypatch.context() as patch:
        patch.setattr(editorial, "state", state_then_change_production)
        response = client.post(url, json=payload | {"notes": "不应写入的并发复核"})

    assert changed
    current = delivery.versions(pid, reader=True)
    assert current == versions | {"production_revision": versions["production_revision"] + 1}
    assert response.status_code == 409, response.text
    assert "制作状态" in response.json()["detail"]
    # A failed first review must not insert anything; a failed re-review must
    # preserve the existing record and must not add an audit event.
    assert review_records(client, pid) == before
    assert not client.get(prefix + "/delivery").json()["ready"]
    assert client.get(job["result"]["download_url"]).status_code == 200


def test_unchanged_reader_export_can_be_reviewed(compiled):
    client, prefix, _, _ = compiled
    pid = prefix.rsplit("/", 1)[1]
    job = export(client, prefix)
    assert job["state"] == "completed", job
    response = client.post(
        prefix + f"/exports/{job['id']}/review",
        json={"checks": {key: True for key in REVIEW_CHECKS}, "notes": "当前版本合成回归复核"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["versions"] == client.app.state.delivery.versions(pid, reader=True)
    records, audits = review_records(client, pid)
    assert records == [response.json()]
    assert audits == 1
