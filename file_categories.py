"""Extension -> category mapping used by the file filter panel.

Categories follow the spirit of GitHub Linguist (programming / markup / data /
prose) and cloc's language table, grouped into families relevant to a mixed
Python + C# + web toolbox repo. Each category has a `kind`:
  - "text":   line-diff (added/deleted) is meaningful
  - "binary": only the byte-size delta is meaningful
"""

from collections import OrderedDict
from typing import Dict, Iterable, List, Set, Tuple

CATEGORIES: "OrderedDict[str, dict]" = OrderedDict([
    ("python", {"label": "Python", "kind": "text", "exts": [
        ".py", ".pyw", ".pyi", ".pyx", ".pxd", ".ipynb",
    ]}),
    ("csharp", {"label": "C# / .NET", "kind": "text", "exts": [
        ".cs", ".csx", ".vb", ".fs", ".fsx", ".fsi",
        ".csproj", ".vbproj", ".fsproj", ".sln", ".slnx", ".slnf",
        ".xaml", ".razor", ".cshtml", ".resx", ".config", ".props", ".targets",
        ".ruleset", ".nuspec",
    ]}),
    ("web", {"label": "Web 前端", "kind": "text", "exts": [
        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
        ".vue", ".svelte", ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ]}),
    ("jvm", {"label": "JVM (Java/Kotlin)", "kind": "text", "exts": [
        ".java", ".kt", ".kts", ".scala", ".groovy", ".gradle",
    ]}),
    ("native", {"label": "C / C++", "kind": "text", "exts": [
        ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".inl", ".m", ".mm",
    ]}),
    ("other_lang", {"label": "其他語言", "kind": "text", "exts": [
        ".go", ".rs", ".rb", ".php", ".swift", ".lua", ".r", ".pl", ".dart", ".sql",
    ]}),
    ("scripts", {"label": "Shell / Script", "kind": "text", "exts": [
        ".sh", ".bash", ".zsh", ".ps1", ".psm1", ".psd1", ".bat", ".cmd", ".fish",
    ]}),
    ("config", {"label": "設定 / 資料", "kind": "text", "exts": [
        ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".conf",
        ".env", ".properties", ".proto", ".lock",
    ]}),
    ("docs", {"label": "文件 / 說明", "kind": "text", "exts": [
        ".md", ".rst", ".txt", ".adoc", ".tex", ".rtf", ".log",
    ]}),
    ("build", {"label": "建置 / 專案", "kind": "text", "exts": [
        ".cmake", ".mk", ".bazel", ".bzl", ".spec",
    ]}),
    ("office", {"label": "Office / PDF", "kind": "binary", "exts": [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    ]}),
    ("image", {"label": "圖片", "kind": "binary", "exts": [
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp", ".tiff", ".tif",
        ".psd", ".ai",
    ]}),
    ("media", {"label": "音訊 / 影片", "kind": "binary", "exts": [
        ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ]}),
    ("font", {"label": "字型", "kind": "binary", "exts": [
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ]}),
    ("archive", {"label": "壓縮檔", "kind": "binary", "exts": [
        ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz",
    ]}),
    ("compiled", {"label": "編譯 / 執行檔", "kind": "binary", "exts": [
        ".exe", ".dll", ".pdb", ".so", ".dylib", ".a", ".lib", ".obj", ".o",
        ".class", ".jar", ".war", ".pyc", ".pyd", ".whl", ".nupkg",
    ]}),
    ("other", {"label": "其他 / 未分類", "kind": "text", "exts": []}),
])

# Bare filenames (no extension per os.path.splitext) matched case-insensitively.
SPECIAL_FILENAMES: Dict[str, str] = {
    "dockerfile": "build", "makefile": "build", "gnumakefile": "build",
    "cmakelists.txt": "build", "vagrantfile": "build",
    ".gitignore": "config", ".gitattributes": "config", ".editorconfig": "config",
    ".dockerignore": "config", ".npmrc": "config", ".env": "config",
    "license": "docs", "license.txt": "docs", "license.md": "docs",
    "readme": "docs", "changelog": "docs", "notice": "docs", "authors": "docs",
}

_EXT_TO_CAT: Dict[str, str] = {
    ext: cat_key for cat_key, cat in CATEGORIES.items() for ext in cat["exts"]
}


def categorize(bucket_key: str) -> str:
    """Map a by_ext bucket key (an extension like '.py', or a bare filename
    like 'Dockerfile' / '.gitignore') to a category key."""
    key = bucket_key.lower()
    if key in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[key]
    return _EXT_TO_CAT.get(key, "other")


def group_by_category(by_ext: Dict[str, dict]) -> List[Tuple[str, dict]]:
    """Group a by_ext aggregate ({bucket_key: stats}) into categories.

    Returns [(cat_key, {"label", "kind", "members": [bucket_key, ...], "files": int}), ...]
    in CATEGORIES declaration order, omitting categories with no members present.
    """
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for cat_key, cat in CATEGORIES.items():
        groups[cat_key] = {"label": cat["label"], "kind": cat["kind"], "members": [], "files": 0}

    for bucket_key, stats in by_ext.items():
        g = groups[categorize(bucket_key)]
        g["members"].append(bucket_key)
        g["files"] += stats.get("files", 0)

    return [(k, g) for k, g in groups.items() if g["members"]]


def keys_by_kind(all_keys: Iterable[str], kind: str) -> Set[str]:
    return {k for k in all_keys if CATEGORIES[categorize(k)]["kind"] == kind}


# (preset_key, button label) in the order buttons should appear.
PRESETS: List[Tuple[str, str]] = [
    ("code", "代碼統計模式"),
    ("bytes", "Bytes 檔案統計模式"),
    ("all", "全選"),
    ("none", "清空"),
]


def resolve_preset(preset_key: str, all_keys: Iterable[str]) -> Set[str]:
    all_keys = set(all_keys)
    if preset_key == "none":
        return set()
    if preset_key == "code":
        return keys_by_kind(all_keys, "text")
    if preset_key == "bytes":
        return keys_by_kind(all_keys, "binary")
    return all_keys
