from pathlib import Path
import yt_dlp
import os
import re


# --- strategy pattern for download modes ----------------------------------
from abc import ABC, abstractmethod


class DownloadMode(ABC):
    """Base class for download strategies.  """

    @abstractmethod
    def options(self) -> dict:
        """Return a dictionary of yt‑dlp options specific to this mode."""
        pass


class BestVideoMode(DownloadMode):
    def options(self) -> dict:
        # choose highest resolution video and best audio, merged if necessary
        return {"format": "bestvideo+bestaudio/best"}


class BestAudioMode(DownloadMode):
    def options(self) -> dict:
        # only audio track, good for podcasts or music
        return {"format": "bestaudio/best"}


class BestTwoMode(DownloadMode):
    def options(self) -> dict:
        # fall back to best mp4 if separate tracks not available
        return {"format": "best[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"}


class FastestMode(DownloadMode):
    def options(self) -> dict:
        # small size, faster download (may sacrifice quality)
        return {"format": "worst"}


# mapping helpers ----------------------------------------------------------
_MODE_MAP = {
    "best-video": BestVideoMode,
    "best-audio": BestAudioMode,
    "best-two": BestTwoMode,
    "fastest": FastestMode,
}


def _resolve_mode(mode):
    if isinstance(mode, DownloadMode):
        return mode
    if isinstance(mode, str):
        cls = _MODE_MAP.get(mode)
        if cls:
            return cls()
        raise ValueError(f"unknown download mode: {mode}")
    raise TypeError("mode must be a string or DownloadMode instance")


# unified downloader -------------------------------------------------------
def download_youtube(
    url: str,
    output_folder: str = "data",
    filename: str | None = None,
    mode: str | DownloadMode = "best-audio",
) -> tuple[str, str]:
    """Download a YouTube URL to *output_folder*.

    Args:
        url: the video URL.
        output_folder: local directory to save the file.
        filename: if provided the file will be named using this value
            (illegal characters stripped).  Otherwise yt‑dlp's title is used.
        mode: one of ``"best-video"``, ``"best-audio"``, ``"best-two"``
            or ``"fastest"`` (see :class:`DownloadMode`).  Can also be an
            instance of :class:`DownloadMode` if you prefer to construct your
            own strategy.

    Returns:
        A tuple ``(filepath, actual_name)`` where ``actual_name`` is the
        basename that was written (including extension).
    """

    os.makedirs(output_folder, exist_ok=True)
    mode_obj = _resolve_mode(mode)

    if filename is not None:
        # sanitize user‑provided filename
        filename = re.sub(r"[\\/*?:\"<>|]", "", filename)
        output_template = os.path.join(output_folder, f"{filename}.%(ext)s")
    else:
        # let yt‑dlp generate a title for us
        output_template = os.path.join(output_folder, "%(title)s.%(ext)s")

    # base options shared by all modes
    ydl_opts = {
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
    }
    # update with strategy-specific settings
    ydl_opts.update(mode_obj.options())

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        final_path = ydl.prepare_filename(info)

    print(f"下載完成: {final_path}")
    return final_path, Path(final_path).resolve().name


# backward-compatible wrappers ---------------------------------------------
def download_youtube_video(url: str, output_folder="data", filename="my_meeting"):
    """Old API that kept only the path return value."""
    path, _ = download_youtube(url, output_folder=output_folder, filename=filename)
    return path

def download_youtube_video_with_its_name(url: str, output_folder="data"):
    """Legacy helper that returns (path, filename).

    Underneath it simply delegates to :func:`download_youtube` using the
    default mode so existing callers keep working with no behavior change.
    """
    return download_youtube(url, output_folder=output_folder)

if __name__ == "__main__":
    url = input("URL ------------>")
    # download_youtube_video(url, filename="meeting")
    download_youtube_video_with_its_name(url, output_folder="../../data")

