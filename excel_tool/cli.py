"""Command-line front-end over the SAME operation registry the GUI uses.

    python -m excel_tool.cli list
    python -m excel_tool.cli apply drop_columns --in a.xlsx --out b.xlsx --param columns=foo,bar
    python -m excel_tool.cli apply sort_values  --in a.xlsx --out b.xlsx --param column=age --param ascending=false

This exists to prove the MVC split: no pandas logic is re-implemented here — it
just coerces params by the registry spec and calls ``core.registry.apply``.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from .core import registry
from .core import operations  # noqa: F401  (populates the registry)


def _coerce(param, raw: str):
    if param.kind == "columns":
        return [c.strip() for c in raw.split(",") if c.strip()]
    if param.kind == "int":
        return int(raw)
    if param.kind == "bool":
        return str(raw).strip().lower() in ("1", "true", "yes", "y", "t", "升冪")
    return raw  # column / text / choice


def _parse_params(op, kv_list):
    given = {}
    for kv in kv_list or []:
        if "=" not in kv:
            raise SystemExit(f"--param 需為 key=value，收到：{kv}")
        k, v = kv.split("=", 1)
        given[k] = v
    params = {}
    for p in op.params:
        if p.name in given:
            params[p.name] = _coerce(p, given[p.name])
        elif p.required and p.default is None:
            raise SystemExit(f"操作 '{op.name}' 缺少必要參數：{p.name}")
        elif p.default is not None:
            params[p.name] = p.default
    return params


def cmd_list():
    for info in registry.describe():
        ps = ", ".join(f"{p['name']}:{p['kind']}" for p in info["params"]) or "(無參數)"
        print(f"  {info['name']:<24} [{info['group']}] {info['label']}  — {ps}")


def cmd_apply(args):
    op = registry.get(args.op)
    df = pd.read_excel(getattr(args, "in"))
    params = _parse_params(op, args.param)
    result = op.fn(df, **params)
    result.to_excel(args.out, index=False)
    print(f"OK: {op.name} → {result.shape[0]} 列 × {result.shape[1]} 欄 已寫入 {args.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="excel_tool.cli",
                                description="Advanced Excel Tool — CLI（重用 GUI 的操作註冊表）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出所有可用操作與參數")
    ap = sub.add_parser("apply", help="對一份 Excel 套用單一操作並輸出")
    ap.add_argument("op", help="操作名稱（見 list）")
    ap.add_argument("--in", dest="in", required=True, help="輸入 Excel")
    ap.add_argument("--out", required=True, help="輸出 Excel")
    ap.add_argument("--param", action="append", help="key=value，可重複")
    args = p.parse_args(argv)

    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "apply":
        cmd_apply(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
