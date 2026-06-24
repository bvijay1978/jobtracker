import datetime as dt

from normalize import clean, norm_date, norm_status, parse_job_id, tc_key


def test_norm_date_uk_format():
    assert norm_date("23/06/2026") == "2026-06-23"


def test_norm_date_iso_format():
    assert norm_date("2026-06-09") == "2026-06-09"


def test_norm_date_object():
    assert norm_date(dt.date(2026, 6, 9)) == "2026-06-09"


def test_norm_date_blank_is_none():
    assert norm_date(None) is None
    assert norm_date("") is None


def test_norm_date_unparseable_passes_through():
    assert norm_date("ASAP") == "ASAP"


def test_parse_job_id_extracts_numeric_id():
    assert parse_job_id("https://www.example.com/jobs/x/56970300") == "56970300"


def test_parse_job_id_none_when_absent():
    assert parse_job_id(None) is None
    assert parse_job_id("https://www.example.com/jobs/no-id-here") is None


def test_tc_key_normalises_whitespace_and_case():
    assert tc_key("  AI   Lead ", "ACME Ltd") == "ai lead|acme ltd"


def test_norm_status_defaults_to_found():
    assert norm_status(None) == "Found"
    assert norm_status("") == "Found"


def test_norm_status_maps_legacy_not_applied():
    assert norm_status("Not Applied") == "Found"


def test_clean_trims_and_blanks_to_none():
    assert clean("  hello ") == "hello"
    assert clean("") is None
    assert clean(None) is None
