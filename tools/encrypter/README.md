# Encrypter — CryptoTool Pro

簡短說明

此專案提供多種加密工具與 GUI，重點功能包含 `Layered` 與 `Nested` 兩種 Mixture 加密模式：

- Layered：多階段加密結果融合成單一 `.isd`（fused）。單次用 File Tab 解密通常無法還原原始資料；必須以完整的 stage chain 在 Mixture Tab 中執行還原。
- Nested：每次加密會產生一個完整的 `.isd`（outer→inner→...）。用 File Tab 可逐層解鎖（每次解密會得到下一層 `.isd`），最終還原原始檔案。

快速上手

以下指令都在 PersonalToolZoo repo 根目錄執行。依賴寫在 `tools/encrypter/requirements.txt`（ttkbootstrap 釘在 1.x，原因見該檔註解）。

建立環境（只要一次）：
```powershell
.\scripts\setup-venv.ps1 encrypter
```

啟動 GUI：
```powershell
.\tools\encrypter\.venv\Scripts\python.exe tools\encrypter\crypto_tool\GUI__Encrypter.py
```

執行測試（pytest 是開發用，不在 requirements 裡；要在 `tools\encrypter` 底下跑，測試才 import 得到 `crypto_tool`）：
```powershell
cd tools\encrypter
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```

打包：
```powershell
.\scripts\build.ps1 encrypter -Smoke
```

關於 Mixture 模式的驗證

1. 測試 Nested：使用 Mixture Tab 建立兩層（例如 AES with keyA, then AES with keyB）並輸出 `outer.isd`；在 File Tab 用外層密碼解出 `inner.isd`，再用內層密碼還原原始檔案。
2. 測試 Layered：使用相同兩個 stage 選 Layered 模式，產生 `fused.isd`；用 File Tab 解密一次通常會得到不可識別的亂碼，完整還原需在 Mixture Tab 以相同 chain 做 Decrypt。

更多細節請見 `del_dev_plan.md`。

