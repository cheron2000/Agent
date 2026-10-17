"""Tests for in-memory screen capture and OCR single-capture behavior."""

from unittest.mock import MagicMock, patch

import eyes


def test_read_text_captures_screen_only_once():
    fake_image = MagicMock()
    fake_image.width = 800
    fake_image.height = 600

    fake_pytesseract = MagicMock()
    fake_pytesseract.image_to_string.return_value = "hello world"
    deps = (
        MagicMock(),
        fake_pytesseract,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    with patch.object(eyes, "_get_deps", return_value=deps), \
         patch.object(eyes, "_find_tesseract", return_value="tesseract"), \
         patch.object(eyes, "_grab_screen", return_value=fake_image) as grab:
        result = eyes.read_text()

    assert result["success"] is True
    assert result["text"] == "hello world"
    grab.assert_called_once()
    fake_pytesseract.image_to_string.assert_called_once_with(fake_image)


def test_read_text_returns_capture_error_without_running_ocr():
    deps = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    with patch.object(eyes, "_get_deps", return_value=deps), \
         patch.object(eyes, "_find_tesseract", return_value="tesseract"), \
         patch.object(eyes, "_grab_screen", side_effect=OSError("capture denied")):
        result = eyes.read_text()

    assert result["success"] is False
    assert "capture denied" in result["error"]
