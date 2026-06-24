import db
import seed


def test_crud_round_trip(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        job_id = db.insert_job(conn, {
            "title": "Backend Engineer", "company": "Acme",
            "status": "Found", "link": "https://x/57000001", "source_job_id": "57000001",
        })
        db.update_job(conn, job_id, {"status": "Applied", "date_applied": "2026-06-24"})
        conn.commit()
        row = dict(db.fetch_all(conn)[0])
        assert row["status"] == "Applied"
        assert row["date_applied"] == "2026-06-24"

        db.delete_job(conn, job_id)
        conn.commit()
        assert db.fetch_all(conn) == []


def test_upsert_inserts_then_updates_in_place(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        first_id, action = db.upsert_job(conn, {"title": "X", "source_job_id": "57000002"})
        conn.commit()
        assert action == "inserted"

        same_id, action = db.upsert_job(conn, {
            "title": "X", "status": "Interview", "source_job_id": "57000002",
        })
        conn.commit()
        assert action == "updated"
        assert same_id == first_id
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        status = conn.execute("SELECT status FROM jobs WHERE id=?", (first_id,)).fetchone()
        assert status[0] == "Interview"


def test_upsert_without_job_id_always_inserts(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        db.upsert_job(conn, {"title": "No Id Role"})
        db.upsert_job(conn, {"title": "No Id Role"})
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2


def test_seed_loads_sample_csv(tmp_path):
    path = tmp_path / "seeded.db"
    count = seed.load_csv(seed.DEFAULT_CSV, path)
    assert count == 8
    with db.connect(path) as conn:
        with_ids = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE source_job_id IS NOT NULL"
        ).fetchone()[0]
    assert with_ids == 8
