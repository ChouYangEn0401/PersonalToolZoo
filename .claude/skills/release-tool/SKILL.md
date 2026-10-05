---
name: release-tool
description: Release one PersonalToolZoo tool — bump its version, clean build, smoke test, commit the version file and tag it. Use when the user asks to release / 發布 / 發新版 / 出版本 a tool, or to tag the current version of a tool.
---

# Release a tool

Everything is done by `scripts/release.ps1`; this skill is about using it safely.

## Steps

1. **Resolve which tool and which bump.** Tool names are forgiving (`hash`, `excel`, `githelper`, `diff`, `table`, `enc`).
   If the user did not say patch / minor / major / X.Y.Z, ask — show the current version from
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 -List`.
   Use `keep` only to tag the current version without bumping (e.g. Git Helper Pro v1.6.4 has no tag yet).
2. **Pre-check yourself** so the script does not refuse halfway:
   - `git status --porcelain -- tools/<tool>` must be empty — commit pending work on that tool first
     (one topic per commit, see AGENTS.md).
   - `git diff --cached --name-only` must be empty.
3. **Tell the user** the smoke test will open the tool's window on their desktop for ~10 seconds.
4. Run non-interactively:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\release.ps1 <tool> <patch|minor|major|X.Y.Z|keep> -Yes
   ```

5. **Read the result.** Success ends with `================ 完成`, the exe path, the `release(<tool>): vX.Y.Z`
   commit and the tag. On failure the script restores the version file — report the failing step and its output;
   do not retry blindly.
6. **Do not push.** Show the two `git push` commands the script printed and let the user decide.
7. If the tool's README 交接 table or the root README tool table shows the version, update them in a
   follow-up `docs:` commit.
