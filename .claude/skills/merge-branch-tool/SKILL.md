---
name: merge-branch-tool
description: Bring a tool (or more commits of a tool) from one of the archived per-tool branches into master's tools/ layout, following the repo's four-commit procedure. Use when the user wants to 收 / merge / 整併 a branch listed in README "整併的判準".
---

# Merge an archived branch tool into master

Read `AGENTS.md` → "把封存分支上的工具收進來" first; this is the detailed checklist.

## 0. Decide the merge point

- `git log --oneline master..origin/<branch>` — list what is not merged yet.
- The merge point must be a "finished" commit: the last commit is a build / build-settings commit
  (usually with a version bump). If the branch tip is not finished, merge up to the last finished
  commit (`git merge <sha>`) and record the rest in README "整併的判準".
- If the tool is already in `tools/<name>/` (merging *more* commits), the branch still has the old
  root layout: merge with `-X subtree=tools/<name>` or cherry-pick and re-path; check every hunk.

## 1. Merge commit

`git merge --no-ff <branch-or-sha>` with a body saying which point was merged and why.
Conflicts on the root `README.md` / `.gitignore`: keep master's version.

## 2. `refactor: move <Tool> into tools/<name>/`

`git mv` only — no content changes. Leave out root-level leftovers of the old template
(`data/**/del`, `src/**/del`, `old_release/del`, the branch's own `.gitignore`).

## 3. `build: switch <Tool> to the shared spec + tool.json`

- Delete the branch's `*.spec` and `builder.bat`; carry every setting over to `tool.json`
  (entry, console, data files → `include`, `collect_all`, hidden imports). Compare with the old spec line by line.
- `version_from` + `tag_prefix` (reuse the branch's existing tag naming).
- `requirements.txt` = real runtime deps only, each with a major-version upper bound
  (check the branch's commit dates against the dependency's release dates to choose the bound).
- Window title imports `__version__`.

## 4. `docs: list <Tool> in the hub README`

Root README tool table row, tool README "交接" section (copy the table from `tools/_template/README.md`),
update the "整併的判準" table.

## Verify before reporting done

- Byte-compare every file in `tools/<name>/` with the branch tree at the merge point
  (`git ls-tree -r <sha>` vs `git ls-tree -r HEAD tools/<name>/`); the only differences should be the removed
  spec/builder/placeholders, `tool.json`, `requirements.txt` and the title line.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 <name>` → `OK` (includes the smoke test;
  warn the user a window will open).
- Run the tool's tests if it has any.
- `git status` clean.
