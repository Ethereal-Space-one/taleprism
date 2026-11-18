"""Uploaded art, its coordinates and its review hash must describe one still."""

import io

import pytest
from PIL import Image, ImageCms

from storygal.reader_image import normalize_still


def opened(original, fmt, **params):
    file = io.BytesIO()
    original.save(file, fmt, **params)
    return Image.open(io.BytesIO(file.getvalue()))


@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_new_photos_apply_exif_before_review_and_strip_metadata(orientation):
    original = Image.new("RGB", (40, 20), "blue")
    original.paste("red", (0, 0, 20, 20))
    exif = Image.Exif()
    exif[274], exif[270] = orientation, "private-camera-description"
    image = opened(original, "JPEG", exif=exif)
    data, dims = normalize_still(image)
    assert dims == ((20, 40) if orientation >= 5 else (40, 20))
    assert b"private-camera-description" not in data
    with Image.open(io.BytesIO(data)) as out:
        assert not out.getexif() and not out.info
        if orientation == 6:
            assert out.getpixel((10, 3))[0] > 230
            assert out.getpixel((10, 36))[2] > 230


def test_alpha_preserved_and_embedded_srgb_normalized():
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = Image.new("RGBA", (3, 4), (10, 22, 33, 98))
    data, size = normalize_still(opened(src, "PNG", icc_profile=icc))
    with Image.open(io.BytesIO(data)) as out:
        assert out.mode == "RGBA" and out.getpixel((0, 0)) == (10, 22, 33, 98)
        assert size == src.size
        assert "icc_profile" not in out.info


def test_opaque_public_art_retains_legacy_pixel_encoding():
    src = Image.new("RGB", (9, 7), (31, 52, 70))
    legacy = io.BytesIO()
    src.save(legacy, "PNG")
    assert normalize_still(opened(src, "PNG"))[0] == legacy.getvalue()


def test_animated_art_rejected_not_silently_flattened():
    seq = [Image.new("RGB", (10, 10), c) for c in ("red", "blue")]
    with pytest.raises(ValueError, match="静态"):
        normalize_still(opened(seq[0], "PNG", save_all=True, append_images=seq[1:]))
