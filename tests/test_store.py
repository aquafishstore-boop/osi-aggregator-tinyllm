"""Store round-trip tests across backends (via a real pipeline-shaped flow)."""

from __future__ import annotations

from cryptography.fernet import Fernet

from osi_sandbox.config import Settings
from osi_sandbox.store import Store
from tests.http_object_store import running_object_store

TOKEN = "store-pat"


def _exercise_store(store: Store) -> None:
    run_id = store.create_run("20260101T000000Z")
    store.write_status({"state": "running", "run_id": run_id})
    store.write_raw(run_id, "health", {"status": "ok"})
    store.write_consolidated(run_id, {"stats": {"quakes": 3}, "feed_ok_count": 1})
    store.write_report_text(run_id, "broad.md", "# broad briefing")
    store.write_report_text(run_id, "fine.md", "# fine briefing")
    store.write_meta(run_id, {"run_id": run_id, "mode": "full"})

    assert store.read_status()["run_id"] == run_id
    assert store.latest_run_id() == run_id
    assert store.list_runs() == [run_id]
    assert store.report_exists(run_id)
    assert store.read_report(run_id, "broad.md") == "# broad briefing"
    assert store.read_meta(run_id)["mode"] == "full"
    assert store.read_consolidated(run_id)["stats"] == {"quakes": 3}

    # A newer run makes prior_stats resolve the older stats block.
    newer = store.create_run("20260102T000000Z")
    store.write_meta(newer, {"run_id": newer})
    assert store.prior_stats(before_run_id=newer) == {"quakes": 3}


def test_store_local(tmp_path):
    s = Settings(DATA_DIR=str(tmp_path), STORAGE_BACKEND="local")
    _exercise_store(Store(s))


def test_store_local_encrypted(tmp_path):
    s = Settings(
        DATA_DIR=str(tmp_path),
        STORAGE_BACKEND="local",
        STORAGE_ENCRYPTION=True,
        STORAGE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    store = Store(s)
    _exercise_store(store)
    assert store.backend.encrypted is True


def test_store_http_token(tmp_path):
    with running_object_store(TOKEN) as (base_url, _objects):
        s = Settings(
            DATA_DIR=str(tmp_path),
            STORAGE_BACKEND="http",
            STORAGE_HTTP_URL=base_url,
            STORAGE_HTTP_TOKEN=TOKEN,
        )
        _exercise_store(Store(s))
