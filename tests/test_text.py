import pytest

from listinglens.text import capacities_gb, excerpt, html_to_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("iPhone 13 128GB", {128}),
        ("iPhone 13 128 gb", {128}),
        ("MacBook 1TB SSD", {1024}),
        ("16GB RAM 512GB SSD", {16, 512}),
        ("model 1128GBX", set()),  # not a standalone capacity
        ("no capacity here", set()),
        (None, set()),
    ],
)
def test_capacities_gb(text, expected):
    assert capacities_gb(text) == expected


def test_html_to_text_collapses_whitespace():
    assert html_to_text("<p>Hello</p>\n<p>  world</p>") == "Hello world"


def test_excerpt_truncates_long_text():
    out = excerpt("x" * 500, max_chars=20)
    assert len(out) == 20 and out.endswith("…")
