import os
import img2pdf
from PIL import Image


SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif", ".tga",
}


def images_to_pdf(image_paths, output_path):
    """Convert a list of images to a single PDF file.

    Uses img2pdf for lossless embedding of JPEG images.
    Other formats are converted via Pillow.
    """
    if not image_paths:
        raise ValueError("沒有選擇任何圖片。")

    # Try img2pdf first for compatible images, fall back to Pillow
    try:
        _convert_with_img2pdf(image_paths, output_path)
    except Exception:
        _convert_with_pillow(image_paths, output_path)

    return output_path


def _convert_with_img2pdf(image_paths, output_path):
    """Use img2pdf for lossless JPEG embedding. Convert non-JPEG to temp PNG bytes."""
    pdf_bytes_list = []
    for p in image_paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in (".jpg", ".jpeg"):
            with open(p, "rb") as f:
                pdf_bytes_list.append(f.read())
        else:
            # Convert to PNG bytes in memory
            img = Image.open(p)
            img.load()
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            import io
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            pdf_bytes_list.append(buf.getvalue())

    pdf_data = img2pdf.convert(pdf_bytes_list)
    with open(output_path, "wb") as f:
        f.write(pdf_data)


def _convert_with_pillow(image_paths, output_path):
    """Fallback: use Pillow to build PDF."""
    images = []
    for p in image_paths:
        img = Image.open(p)
        img.load()
        if img.mode != "RGB":
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            else:
                img = img.convert("RGB")
        images.append(img)

    if not images:
        raise ValueError("無法讀取任何圖片。")

    first, *rest = images
    first.save(output_path, "PDF", save_all=True, append_images=rest)
