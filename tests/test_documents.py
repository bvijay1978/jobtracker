import db
import documents


def test_insert_fetch_update_delete_round_trip(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        doc_id = documents.save(
            conn, name="My Resume", category="Resume", tags="FS, Delivery Lead",
            role_id=None, filename="resume.docx", data=b"fake docx bytes",
            mime_type=documents.DOCX_MIME,
        )
        conn.commit()

        listed = [dict(r) for r in db.fetch_documents(conn)]
        assert len(listed) == 1
        assert listed[0]["name"] == "My Resume"
        assert listed[0]["size_bytes"] == len(b"fake docx bytes")
        assert "data" not in listed[0]  # listing excludes the blob

        full = dict(db.fetch_document(conn, doc_id))
        assert bytes(full["data"]) == b"fake docx bytes"

        db.update_document(conn, doc_id, {"tags": "FS, Renamed"})
        conn.commit()
        assert dict(db.fetch_document(conn, doc_id))["tags"] == "FS, Renamed"

        db.delete_document(conn, doc_id)
        conn.commit()
        assert db.fetch_documents(conn) == []


def test_role_tags_uses_detected_sector_and_title():
    role = {"title": "Delivery Lead", "company": "Toyota Finance Australia", "fit_notes": "banking"}
    tags = documents.role_tags(role)
    assert "FS" in tags
    assert "Delivery Lead" in tags


def test_role_tags_defaults_to_general_without_sector_signal():
    role = {"title": "Office Coordinator", "company": "Acme"}
    assert "General" in documents.role_tags(role)


def test_document_role_id_links_to_a_job(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        job_id = db.insert_job(conn, {"title": "Delivery Lead", "company": "Acme"})
        doc_id = documents.save(
            conn, name="Tailored CV", category="Resume", tags="FS",
            role_id=job_id, filename="cv.docx", data=b"bytes",
        )
        conn.commit()
        full = dict(db.fetch_document(conn, doc_id))
        assert full["role_id"] == job_id
