import config
import cv_builder


def test_generate_cv_from_example_profile(tmp_path):
    cv = cv_builder.generate_cv(
        {"title": "Senior Delivery Manager"},
        profile_path=config.PROJECT_ROOT / "profile.example.json",
        out_dir=tmp_path,
    )
    assert cv.exists()
    assert cv.suffix == ".docx"

    from docx import Document

    doc = Document(str(cv))
    # The title line (2nd paragraph) should echo the role title.
    assert doc.paragraphs[1].text == "Senior Delivery Manager"


def test_missing_profile_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        cv_builder.generate_cv(
            {"title": "X"}, profile_path=tmp_path / "nope.json", out_dir=tmp_path
        )
