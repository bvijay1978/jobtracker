import config
import cover_letter

EXAMPLE = config.PROJECT_ROOT / "profile.example.json"


def _text(path):
    from docx import Document

    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_offline_default_seeds_from_profile(tmp_path):
    role = {"title": "AI Governance Lead", "company": "Acme", "fit_notes": "Strong regulatory fit"}
    path = cover_letter.generate_cover_letter(role, out_dir=tmp_path, profile_path=EXAMPLE)
    assert path.exists()
    text = _text(path)
    assert "[add two or three sentences" not in text  # seeded, not left blank
    assert "[Your name]" not in text  # signed with the real name


def test_offline_falls_back_to_brackets_without_a_profile(tmp_path):
    role = {"title": "Analyst", "company": "Acme"}
    path = cover_letter.generate_cover_letter(
        role, out_dir=tmp_path, profile_path=tmp_path / "no_such_profile.json"
    )
    text = _text(path)
    assert "[add two or three sentences" in text
    assert "[Your name]" in text


def test_body_paragraphs_override_replaces_offline_summary(tmp_path):
    role = {"title": "AI Governance Lead", "company": "Acme", "fit_notes": "irrelevant here"}
    tailored = [
        "In my current role I lead AI governance for a regulated bank, mirroring the "
        "risk-and-controls language in your advert.",
        "I have delivered exactly the assurance framework this role describes.",
    ]
    path = cover_letter.generate_cover_letter(
        role, out_dir=tmp_path, profile_path=EXAMPLE, body_paragraphs=tailored
    )
    text = _text(path)
    for para in tailored:
        assert para in text
    # The offline fit-notes sentence is only appended to the untailored body.
    assert "irrelevant here" not in text
