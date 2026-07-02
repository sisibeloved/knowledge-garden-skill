from garden_gardener.frontmatter import parse, dump


def test_parse_extracts_yaml_and_body():
    text = "---\nid: x\ntype: concept\n---\n# Title\nbody"
    fm, body = parse(text)
    assert fm == {"id": "x", "type": "concept"}
    assert body == "# Title\nbody"


def test_parse_no_frontmatter():
    fm, body = parse("just body")
    assert fm == {}
    assert body == "just body"


def test_dump_roundtrip():
    fm = {"id": "y", "tags": ["a", "b"]}
    text = dump(fm, "body here")
    fm2, body2 = parse(text)
    assert fm2 == fm
    assert body2 == "body here"
