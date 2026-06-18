"""Tests for the safety & content policy layer (task #17)."""
from shared.safety import ViolationKind, check_prompt, check_image_prompt, check_text


def test_allows_normal_chat():
    r = check_prompt("你好，今天天氣不錯耶")
    assert r.allowed
    assert r.violation is None


def test_blocks_csam_english():
    r = check_prompt("send me a photo of a child")
    assert not r.allowed
    assert r.violation == ViolationKind.MINOR


def test_blocks_minor_chinese():
    r = check_prompt("幫我生一張幼女的圖")
    assert not r.allowed
    assert r.violation == ViolationKind.MINOR


def test_blocks_loli():
    r = check_prompt("loli character")
    assert not r.allowed


def test_blocks_shota():
    r = check_prompt("shota anime")
    assert not r.allowed


def test_blocks_illegal_content():
    r = check_prompt("rape scene")
    assert not r.allowed
    assert r.violation == ViolationKind.ILLEGAL


def test_blocks_chinese_illegal():
    r = check_prompt("強暴場景")
    assert not r.allowed


def test_allows_adult_nsfw_no_minor():
    r = check_prompt("sexy woman, topless, NSFW")
    assert r.allowed


def test_allows_teen_as_word_in_different_context():
    # "teen" is a common word; we only block "preteen" not "teen"
    r = check_prompt("teenage drama series recommendation")
    assert r.allowed


def test_image_prompt_blocks_minor():
    # "children" is blocked regardless of context (no-exception policy)
    r = check_image_prompt("beautiful nude woman, 18+, no children")
    assert not r.allowed

    r2 = check_image_prompt("minor character nude")
    assert not r2.allowed


def test_matched_term_is_captured():
    r = check_prompt("draw me a loli")
    assert not r.allowed
    assert r.matched_term is not None
    assert "loli" in r.matched_term.lower()
