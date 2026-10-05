"""確認「目前這個 python」裝的套件符合給定的 requirements 檔。

由 scripts/build.ps1 與 scripts/setup-venv.ps1 呼叫，跑在工具自己的 venv 裡：

    python scripts/check_deps.py requirements-dev.txt tools/<name>/requirements.txt

全部符合 → exit 0；有缺的或版本不在範圍內 → 列出來並 exit 1。
--quiet：符合的不印，只印有問題的（build 時用）。
只用標準庫 + packaging（pyinstaller 本身就依賴 packaging，build 環境一定有）。
"""
import sys
from importlib import metadata

try:
    from packaging.requirements import InvalidRequirement, Requirement
except ImportError:
    print("  [check_deps] 這個環境沒有 packaging —— 先裝 requirements-dev.txt")
    sys.exit(1)


def read_requirements(path):
    reqs = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split(" #", 1)[0].strip()
            if not line or line.startswith(("#", "-")):
                continue
            try:
                reqs.append(Requirement(line))
            except InvalidRequirement as e:
                print(f"  [check_deps] {path}:{lineno} 看不懂這行: {line} ({e})")
                sys.exit(1)
    return reqs


def main(args):
    quiet = "--quiet" in args
    paths = [a for a in args if a != "--quiet"]
    problems = []
    for path in paths:
        for req in read_requirements(path):
            if req.marker and not req.marker.evaluate():
                continue
            try:
                installed = metadata.version(req.name)
            except metadata.PackageNotFoundError:
                problems.append(f"{req.name}: 沒有安裝（要求 {req}）")
                continue
            if req.specifier and not req.specifier.contains(installed, prereleases=True):
                problems.append(f"{req.name}: 裝的是 {installed}，不符合 {req.specifier}")
            elif not quiet:
                print(f"  ok  {req.name}=={installed}")

    if problems:
        if not quiet:
            print()
        for p in problems:
            print(f"  !!  {p}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
