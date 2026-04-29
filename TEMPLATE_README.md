# Template usage

Place `template.toml` at your project root and edit the keys under `[tool.pyinstaller_template]`.

Quick steps:

1. Update `name`, `entry_script`, and either `package_name` or `version_file`.
2. Put any folders you want bundled into `include_folders`.
3. Run:

```powershell
python -m PyInstaller template.spec
```

Notes:
- `template.spec` uses `importlib.metadata.version()` if `package_name` is set and the package is installed.
- If not installed, it will ast-parse `version_file` to obtain `__version__` without executing package code.
- `build/version.txt` will be generated and bundled when `embed_version_file` is true.
