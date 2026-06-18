"""Tests for the referral deep-link funnel (task #23)."""
from shared.referral import StartPayload, make_deep_link, parse_start_payload


def test_parse_ref_only():
    p = parse_start_payload("ref123456789")
    assert p.referrer_id == 123456789
    assert p.source is None


def test_parse_ref_with_source():
    p = parse_start_payload("ref987654321_channel")
    assert p.referrer_id == 987654321
    assert p.source == "channel"


def test_parse_src_only():
    p = parse_start_payload("src_web")
    assert p.referrer_id is None
    assert p.source == "web"


def test_parse_empty():
    p = parse_start_payload("")
    assert p.referrer_id is None
    assert p.source is None


def test_parse_unknown_payload():
    p = parse_start_payload("somethingelse")
    assert p.referrer_id is None
    assert p.source is None


def test_make_deep_link():
    link = make_deep_link("videogirl_bot", 112233)
    assert link == "https://t.me/videogirl_bot?start=ref112233"
    assert "ref112233" in link
