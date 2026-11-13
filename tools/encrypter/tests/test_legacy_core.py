"""讓舊的 7 個測試（test_mixture_modes.py、test_xorfold.py）也能用 unittest 跑。

那兩個檔是 pytest 風格的純函式，`unittest discover` 找不到裡面的測試；這裡把每個函式包成一個測試。
舊檔本身沒有改。舊程式需要 pycryptodome，環境裡沒有的話整組略過。
"""

import importlib
import unittest

import _support  # noqa: F401  （把工具資料夾加進 sys.path）

LEGACY_MODULES = ("test_mixture_modes", "test_xorfold")


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    try:
        import Crypto  # noqa: F401
    except ImportError:
        @unittest.skip("pycryptodome is not installed; legacy .isd tests skipped")
        def legacy_core_tests():
            pass
        suite.addTest(unittest.FunctionTestCase(legacy_core_tests))
        return suite
    for module_name in LEGACY_MODULES:
        module = importlib.import_module(module_name)
        for name, func in sorted(vars(module).items()):
            if name.startswith("test_") and callable(func):
                suite.addTest(unittest.FunctionTestCase(func, description=f"{module_name}.{name}"))
    return suite
