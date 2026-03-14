from app.services.gemini_service import _build_prompt, _extract_json_block


def test_build_prompt_keeps_json_braces_intact():
    template = 'Return JSON: {"title": "x"} for {keyword} in {language} tone {tone}'
    prompt = _build_prompt(template, "sql", "vi", "professional")
    assert '{"title": "x"}' in prompt
    assert "sql" in prompt


def test_extract_json_block_with_wrapper_text():
    raw = 'Here is output:\n```json\n{"title":"A","slug":"a","meta_description":"m","excerpt":"e","content_html":"<p>x</p>"}\n```\nThanks'
    payload = _extract_json_block(raw)
    assert payload["title"] == "A"
    assert payload["slug"] == "a"


def test_extract_json_block_repairs_control_chars_inside_json_strings():
    raw = '{"title":"A","slug":"a","meta_description":"m","excerpt":"e","content_html":"<p>line 1\nline 2\x0bline 3</p>"}'
    payload = _extract_json_block(raw)
    assert payload["title"] == "A"
    assert "line 2" in payload["content_html"]


def test_extract_json_block_from_mixed_text_with_embedded_object():
    raw = (
        "Tom tat nhanh: bai viet da san sang.\n"
        "Random notes...\n"
        "{\"title\":\"Node.js Interview\",\"slug\":\"nodejs-interview\","
        "\"meta_description\":\"m\",\"excerpt\":\"e\",\"content_html\":\"<p>x</p>\"}\n"
        "Ket thuc."
    )
    payload = _extract_json_block(raw)
    assert payload["slug"] == "nodejs-interview"


def test_extract_json_block_from_array_returns_first_object():
    raw = '[{"title":"A","slug":"a","meta_description":"m","excerpt":"e","content_html":"<p>x</p>"}]'
    payload = _extract_json_block(raw)
    assert payload["title"] == "A"


def test_extract_json_block_salvages_fields_from_malformed_json():
    raw = (
        '{"title":"T", "meta_description":"M", "excerpt":"E", '
        '"content_html":"<p>One</p>\\n<p>Two</p>"  BROKEN }'
    )
    payload = _extract_json_block(raw)
    assert payload["title"] == "T"
    assert payload["meta_description"] == "M"
    assert "<p>One</p>" in payload["content_html"]
