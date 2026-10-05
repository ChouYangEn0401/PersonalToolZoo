from PIL import Image
import os

SUPPORTED_OUTPUT_FORMATS = {
    "PNG":  {"ext": ".png",  "params": {"optimize": True}},
    "JPEG": {"ext": ".jpg",  "params": {"quality": 95, "optimize": True}},
    "BMP":  {"ext": ".bmp",  "params": {}},
    "TIFF": {"ext": ".tiff", "params": {"compression": "tiff_lzw"}},
    "WEBP": {"ext": ".webp", "params": {"lossless": True, "quality": 100}},
    "ICO":  {"ext": ".ico",  "params": {}},
    "GIF":  {"ext": ".gif",  "params": {}},
    "TGA":  {"ext": ".tga",  "params": {}},
}

SUPPORTED_INPUT_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp",
    ".ico", ".gif", ".tga", ".ppm", ".pgm", ".pbm", ".pcx",
    ".dds", ".dib", ".eps", ".sgi", ".xbm", ".jfif",
}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _prepare_image(img, output_format):
    """Handle mode conversion for target format compatibility."""
    needs_rgb = output_format in ("JPEG", "BMP")

    if img.mode == "P":
        img = img.convert("RGBA")

    if needs_rgb and img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg

    if needs_rgb and img.mode not in ("RGB", "L"):
        return img.convert("RGB")

    return img


def convert_image(input_path, output_dir, output_format, ico_sizes=None):
    """Convert a single image to the target format. Returns output path."""
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(f"不支援的格式: {output_format}")

    fmt_info = SUPPORTED_OUTPUT_FORMATS[output_format]
    img = Image.open(input_path)
    img.load()

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, base_name + fmt_info["ext"])

    img = _prepare_image(img, output_format)

    if output_format == "ICO":
        sizes = [(s, s) for s in (ico_sizes or [256])]
        # Resize image to max ICO size first
        max_size = max(s[0] for s in sizes)
        if img.size[0] != max_size or img.size[1] != max_size:
            img_resized = img.copy()
            img_resized.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        else:
            img_resized = img
        if img_resized.mode != "RGBA":
            img_resized = img_resized.convert("RGBA")
        img_resized.save(output_path, format="ICO", sizes=sizes)
        return output_path

    params = fmt_info["params"].copy()
    img.save(output_path, format=output_format, **params)
    return output_path
