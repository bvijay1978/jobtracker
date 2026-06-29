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


def test_detect_sector():
    assert cv_builder.detect_sector({"title": "Programme Manager - Financial Crime"}) == "fs"
    assert cv_builder.detect_sector({"title": "AI Governance Lead"}) == "ai"
    assert cv_builder.detect_sector({"title": "Insurance Transformation Director"}) == "fs"
    assert cv_builder.detect_sector(
        {"title": "Delivery Lead", "fit_notes": "public sector / government programme"}
    ) == "public"
    assert cv_builder.detect_sector({"title": "Office Manager"}) == "default"


def test_resolve_profile_leads_with_sector():
    prof = {
        "profiles": {"default": "D", "fs": "FS-summary", "ai": "AI-summary"},
        "leadCompetencies": {"fs": ["FS lead"], "ai": ["AI lead"]},
        "competencies": ["General one", "General two"],
    }
    fs_text, fs_comps = cv_builder.resolve_profile(prof, "fs")
    assert fs_text == "FS-summary"
    assert fs_comps[0] == "FS lead"  # sector competency promoted to the front

    # unknown sector falls back to the default profile, base competencies only
    def_text, def_comps = cv_builder.resolve_profile(prof, "default")
    assert def_text == "D"
    assert def_comps[0] == "General one"
