目標

我需要兩種清晰可測試的混合加密（Mixture）模式：

- Layered：一個內容經過多階段加密後，所有階段結果融合並封裝為單一 `.isd`。
  - 特性：解密時若只做一次（File Tab）會得到不可辨識的加密亂碼；完整還原需提供整個加密鏈（所有階段的演算法與密碼），或使用 Mixture Tab 以同樣階段配置做一次性還原。

- Nested：每一次加密都會完整封裝成一個 `.isd`（outer → inner → ...），解密一次會得到下一層完整 `.isd`，反覆解密最終還原原始資料。
  - 特性：可以以逐層解鎖的方式測試與驗證（File Tab 一次一層）。

我要求你做的事（Summary）

1. 在程式內統一名稱為 `layered` / `nested`，保留對舊檔案（`simple`/`node`）的向下相容。
2. 確保 `MixtureTab`（Tab 3）能同時執行：
   - Encrypt（建立 `layered` 或 `nested` 的輸出）
   - Decrypt（直接使用 MixtureTab 的輸入區：若選 File，讀取該 .isd；若選 Text，讀取文字），不再彈出檔案選擇對話框。
3. `FileTab`（Tab 1）行為：對 `nested` 模式的外層 `.isd`，使用現有的 Decrypt & Save 應能還原出下一層 `.isd`（而非原始資料）；對 `layered`，FileTab 解密一次通常會得到無法辨識的亂碼（因為內部仍是多層融合）。
4. `core/bytefile.py` 保留 metadata 字段 `mode`，預設值改為 `layered`，並且解析時對 `simple`/`node` 做映射回 `layered`/`nested`（已存在）。
5. README、UI 標籤、tooltip 需更新為 `Layered` / `Nested` 並說明差異（已做，但請確認文字精確）。
6. 新增或至少列出一組手動測試步驟與推薦的自動化測試腳本範例，方便驗證行為是否正確。

實作細節（How I'll change code）

- 核心決策
  - 維持 `.isd` 格式：CONTENT + NOTE(JSON)
  - NOTE 中 `mode` 表示此 `.isd` 的打包方式（`layered` 或 `nested`）

- 主要檔案與修改點
  - `core/bytefile.py`
    - 預設 `mode` 為 `layered`；解析時保留向下相容（`simple`->`layered`, `node`->`nested`）。
  - `gui/tab_mixture.py`
    - Encrypt: 若 `mode==nested`，每階段加密後把該階段包成 `.isd` 並以該 `.isd` 的 bytes 作為下一階段的輸入（outer 包 inner）；輸出最外層 `.isd`。
    - Encrypt: 若 `mode==layered`，採用 `EncryptionEngine.encrypt_chain`（或等效）把多階段結果融合，最後包成單一 `.isd`。
    - Decrypt: 使用 MixtureTab 的 input area（`file_sel` 或 `input_text`）讀入 source，然後依 `mode` 執行對應的反向邏輯：
      - Nested：逐層 parse `ByteFile` 並依 chain reversed 解出；若解出仍為 `.isd`，可直接保存該 `.isd` bytes。
      - Layered：對 `ByteFile.content` 使用 `decrypt_chain` 或針對 PGP 先 unwrap 還原原始 bytes。
  - `gui/tab_file.py`
    - 保持 FileTab 的現有行為，但包含 `mode` 的判斷：對 `nested` 的最外層，可讓使用者在 Decrypt 時得到下一層的 `.isd`；對 `layered` 則解出融合內容（通常無法直接得到原始，需整個 chain）。
  - `gui/tab_largefile.py`, `gui/tab_text.py` 等相依檔案：更新標籤與 metadata 中的 `mode` 文字（已更新多處）。

測試計畫（How to test / steps）

手動測試：

1) 測試 `nested`（逐層）流程
   - MixtureTab：新增兩個 stage（Stage A 使用 AES keyA；Stage B 使用 AES keyB），模式選 `Nested`，輸入一個小檔案 `plain.bin`，點 Encrypt，存為 `outer.isd`。
   - FileTab：把 `outer.isd` 拖入 Decrypt，輸入 keyB（外層使用 keyB 解出內層 `inner.isd`），點 Decrypt & Save → 應會輸出 `inner.isd` 檔案（不是原始檔）。
   - 再用 FileTab 解 `inner.isd`（輸入 keyA）→ 應還原 `plain.bin`。

2) 測試 `layered`（融合）流程
   - MixtureTab：同上兩個 stage，但模式選 `Layered`，Encrypt 出 `fused.isd`。
   - FileTab：嘗試 Decrypt `fused.isd`（輸入任一單一階段的密碼）→ 應該失敗或得到不可識別的亂碼（預期）；要還原必須使用 MixtureTab 並以完全相同的 stage chain 進行 Decrypt（或使用 decrypt_chain API）。

自動化測試建議（pytest）：
- 新增 `tests/test_mixture_modes.py`，用小型 byte payload 做：
  - 對 `nested`：使用 engine 或 MixtureTab 的邏輯建立兩層 `.isd`，檢查第一層解密會產生可 parse 的 `.isd`，第二層解密還原原始。
  - 對 `layered`：呼叫 `EncryptionEngine.encrypt_chain` 與 `decrypt_chain`，檢查最終輸出等於原始。

進度（Inventory & Next steps）

- ✅ `core/bytefile.py`: `mode` property present, default `layered`, backward-compat mapping (`simple`→`layered`, `node`→`nested`).
- ✅ `MixtureTab` (`gui/tab_mixture.py`): Encrypt/Decrypt for `layered` and `nested` implemented; Decrypt uses MixtureTab input area.
- ✅ `FileTab` (`gui/tab_file.py`): Nested peeling and layered behavior implemented.
- ⚠️ README/UI/tooltips: GUI labels appear updated in code, but README and help text need review and wording refinements.
- ⚠️ Tests: automated pytest tests are not yet added — next immediate task.

Planned changes (I'll implement next):
1. Add `tests/test_mixture_modes.py` (pytest) and run locally.
2. Add a concise manual-test checklist into this file (done above) and mark when verified.
3. Update `README.md` with a clear `Layered` vs `Nested` section and quick run/test commands.
4. Review & refine UI tooltips/labels if any phrasing needs change.

快速指令（本地運行）：

執行 GUI：
```powershell
cd crypto_tool
python main.py
```

執行測試：
```powershell
pip install -r requirements.txt
pytest -q
```

交付與回饋流程

- 我已檢視程式碼並把已完成項目標示為完成。
- 我將先新增自動化測試檔，執行確認後再更新 `README.md` 並回報結果。
- 若您想要我先還原所有檔案到上游狀態（`git restore .`），請明確回覆「還原全部」。
