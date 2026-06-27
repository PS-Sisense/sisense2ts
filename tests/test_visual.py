"""H8: the visual-QA validity check is pure (no cluster). The render() call is exercised
live by scripts/visual_qa.py."""
from sisense2ts.verify.visual import valid_image

_PNG = b"\x89PNG\r\n\x1a\n"


def test_valid_png_real():
    ok, why = valid_image(_PNG + b"x" * 20000, "PNG")
    assert ok and "20008" in why


def test_bad_header_rejected():
    ok, why = valid_image(b"<html>error</html>" * 100, "PNG")
    assert not ok and "header" in why


def test_too_small_is_blank():
    ok, why = valid_image(_PNG + b"x" * 50, "PNG")
    assert not ok and "blank" in why.lower()


def test_pdf_magic():
    ok, _ = valid_image(b"%PDF-1.4" + b"x" * 20000, "PDF")
    assert ok
