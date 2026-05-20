

class RuleEngine:
    def __init__(self):
        self.rules = []
    def add_rule(self, rule):
        self.rules.append(rule)
    def clear(self):
        self.rules.clear()
    def apply_all(self, df):
        for rule in self.rules:
            df = rule.apply(df)
        return df
    def describe_all(self):
        return "\n".join([rule.describe() for rule in self.rules])

