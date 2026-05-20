import pandas as pd
from remake.M2E1.GUI_ExtendTool.lib.rules_builder import (
    build_leave_rule, build_group_condition_rule,
    build_if_else_rule, build_basic_rule
)
from remake.M2E1.GUI_ExtendTool.lib.rule_definitions import LeaveMaxRule, GroupByConditionRule, FilterGreaterThanRule, IfElseRule


def test_build_leave_rule():
    rule = build_leave_rule("leave_max", ["ORGNAME"], "Score")
    assert isinstance(rule, LeaveMaxRule)
    assert rule.column == "Score"
    assert rule.group_by_columns == ["ORGNAME"]


def test_build_group_condition_same_content():
    class Dummy:
        def get(self):
            return "SAME_CONTENT"

    rule, cols = build_group_condition_rule("ORGNAME", Dummy(), None, None)
    assert isinstance(rule, GroupByConditionRule)
    assert cols == ["ORGNAME"]


def test_build_basic_rule_numeric():
    df = pd.DataFrame({"Score": [0.5, 0.9]})

    class Dummy:
        def get(self):
            return "0.8"

    rule = build_basic_rule(df, "filter_greater_than", "Score", Dummy())
    assert isinstance(rule, FilterGreaterThanRule)
    assert rule.column == "Score"
    assert rule.value == 0.8


def test_build_if_else_rule_numeric():
    df = pd.DataFrame({"Score": [0.5, 0.9]})

    class Dummy:
        def __init__(self, val):
            self.val = val

        def get(self):
            return self.val

    rule = build_if_else_rule(
        df, "Score", Dummy(">"), Dummy("0.6"),
        Dummy("set"), Dummy("1"),
        Dummy("delete"), Dummy("")
    )

    assert isinstance(rule, IfElseRule)
    assert rule.column == "Score"
    assert rule.operator == ">"
    assert rule.threshold == 0.6
    assert rule.then_action == ("set", 1.0)
    assert rule.else_action == ("delete", None)
