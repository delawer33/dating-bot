from api.services import telegram_file_service as tg


def test_sniff_jpeg() -> None:
    b = b"\xff\xd8\xff" + b"\0" * 9
    assert tg.sniff_image_content_type(b) == "image/jpeg"


def test_sniff_png() -> None:
    b = b"\x89\x50\x4e\x47" + b"\0" * 8
    assert tg.sniff_image_content_type(b) == "image/png"


def test_sniff_webp() -> None:
    b = b"RIFF" + b"\0\0\0\0" + b"WEBP"
    assert len(b) == 12
    assert tg.sniff_image_content_type(b) == "image/webp"


def test_sniff_too_short() -> None:
    assert tg.sniff_image_content_type(b"abc") is None


def test_sniff_rejects_gif() -> None:
    assert tg.sniff_image_content_type(b"GIF89a" + b"\0" * 6) is None
