"""Normalize a newly uploaded still for review; never reinterpret a saved plate."""

import io

from PIL import ImageCms, ImageOps


def normalize_still(image):
    if getattr(image, "is_animated", False):
        raise ValueError("此图会自行播放。请先选一帧并导出为静态 PNG、JPEG 或 WebP。")
    upright = ImageOps.exif_transpose(image)
    alpha = (
        upright.convert("RGBA").getchannel("A")
        if "A" in upright.getbands() or "transparency" in upright.info
        else None
    )
    icc = upright.info.get("icc_profile")
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            pixels = ImageCms.profileToProfile(
                upright if upright.mode in {"RGB", "CMYK", "LAB", "L"} else upright.convert("RGB"),
                source,
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
        except (ImageCms.PyCMSError, OSError, TypeError, ValueError):
            raise ValueError("无法读取图像色彩配置。请将图片导出为 sRGB 后再上传。") from None
    else:
        pixels = upright.convert("RGB")
    if alpha is not None:
        pixels.putalpha(alpha)
    # Do not deliver a device serial, coordinates, comments or thumbnails.
    # Geometry, review hash and stored PNG all describe these exact upright pixels.
    pixels.info.clear()
    output = io.BytesIO()
    pixels.save(output, "PNG")
    return output.getvalue(), pixels.size
