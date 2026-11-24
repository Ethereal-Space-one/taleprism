"""The backup summary counts exact importable decisions, not assets or sign-offs."""

import copy
import io
import zipfile

from test_plate_screening_workbench import MARK, apply, decision, get_review_job, state, timing
from test_reader_motion import motion, save, with_motion
from test_reader_motion import project as project  # noqa: PLC0414 -- pytest fixture


def result(plates, transferable, unassessed, blocked, timing_recorded):
    return {
        "plates": plates,
        "motion_transferable": transferable,
        "motion_unassessed": unassessed,
        "motion_blocked": blocked,
        "timing_recorded": timing_recorded,
    }


def test_counts_follow_placed_identity_and_current_bindings(project):
    c, pid, reader, asset, config = project
    prefix = f"/api/projects/{pid}"
    assert asset["status"] == "accepted"  # accepted but not a placed illustration
    assert state(c, prefix)["handoff"] == result(0, 0, 0, 0, 0)
    assert save(project, config).is_success
    one = state(c, prefix)
    assert one["handoff"] == result(1, 0, 1, 0, 0)
    one = decision(c, prefix, one).json()
    one = timing(c, prefix, one).json()
    assert one["handoff"] == result(1, 1, 0, 0, 1)

    # A repeated image is two independent placements. More images in the
    # library, or unused/outdated judgments, are not more ready decisions.
    multi = copy.deepcopy(config)
    multi["illustrations"].append(
        dict(config["illustrations"][0], id="later", after_byte=reader.blocks(pid)[-1]["byte_end"])
    )
    assert save(project, multi).is_success
    d = state(c, prefix)
    assert d["handoff"] == result(2, 1, 1, 0, 1)
    d = timing(c, prefix, d, "revise", plate_id="later").json()
    assert d["handoff"] == result(2, 1, 1, 0, 2)  # both clear and revise are saved, not approval

    changed = copy.deepcopy(multi)
    changed["illustrations"][0]["title"] = "新的公开图题"
    assert save(project, changed).is_success
    d = state(c, prefix)
    assert d["timing"]["plates"]["rain-court"]["stale"]
    assert d["handoff"] == result(2, 1, 1, 0, 1)  # timing invalidated, motion kept
    changed["illustrations"][0]["after_byte"] = reader.blocks(pid)[0]["byte_end"]
    assert save(project, changed).is_success
    d = state(c, prefix)
    assert d["changed"] == ["rain-court"]
    assert d["handoff"] == result(2, 0, 2, 0, 1)  # moving the anchor invalidates both
    changed["illustrations"] = [changed["illustrations"][0]]
    assert save(project, changed).is_success
    assert state(c, prefix)["handoff"] == result(1, 0, 1, 0, 0)  # orphan excluded


def test_same_transfer_rule_at_download_summary_and_restore_import(project):
    c, pid, _reader, _asset, config = project
    prefix = f"/api/projects/{pid}"
    assert save(project, config).is_success
    d = state(c, prefix)
    old = decision(c, prefix, d, "motion", proposed_effect="wave-impact-backwash").json()
    assert old["handoff"] == result(1, 1, 0, 0, 0)
    assert save(project, with_motion(project, motion(project, reviewed=True))).is_success
    conflicting = state(c, prefix)
    assert conflicting["handoff"] == result(1, 0, 0, 1, 0)
    back = c.get(prefix + "/bundle").content
    denied_copy = c.post("/api/project-bundles", files={"file": ("backup.zip", back)})
    assert denied_copy.status_code == 201
    p0 = f"/api/projects/{denied_copy.json()['id']}"
    assert apply(c, p0, state(c, p0), conflicting["worksheet"], exact_copy=True).status_code == 400

    # Intentionally choosing still with an active renderer blocks formal
    # delivery, but the editorial note is allowed in the private worksheet.
    d = decision(c, prefix, conflicting).json()
    d = timing(c, prefix, d, "revise", reason="TIMING_NOT_FOR_BACKUP").json()
    assert d["handoff"] == result(1, 1, 0, 0, 1)
    assert not d["report"]["ok"] and d["report"]["counts"]["screened"] == 0
    backup = c.get(prefix + "/bundle").content
    job, _ = get_review_job(c, prefix)
    reader = c.get(job["result"]["download_url"]).content
    for raw in [backup, reader]:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert all(b'"handoff"' not in z.read(n) for n in z.namelist() if n.endswith(".json"))
            assert not any(
                marker in z.read(n)
                for marker in [MARK.encode(), b"TIMING_NOT_FOR_BACKUP"]
                for n in z.namelist()
            )
    assert "handoff" not in c.get(prefix + "/reader/content").json()
    identities = {pid}
    for _ in range(2):
        restored = c.post("/api/project-bundles", files={"file": ("backup.zip", backup)})
        assert restored.status_code == 201, restored.text
        rid = restored.json()["id"]
        assert rid not in identities
        identities.add(rid)
        q = f"/api/projects/{rid}"
        fresh = state(c, q)
        assert fresh["handoff"] == result(1, 0, 1, 0, 0)
        assert apply(c, q, fresh, d["worksheet"]).status_code == 409
        moved = apply(c, q, fresh, d["worksheet"], exact_copy=True)
        assert moved.status_code == 200, moved.text
        assert moved.json()["handoff"] == result(1, 1, 0, 0, 0)
        assert moved.json()["worksheet"]["work_id"] != d["worksheet"]["work_id"]
