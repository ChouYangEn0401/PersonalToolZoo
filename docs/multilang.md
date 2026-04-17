# 多語言支援

Git Helper Pro 支援完整多語言介面，所有 UI 文字均可切換。

---

## 內建語言

| 語言代碼 | 語言名稱 |
|---------|---------|
| `zh-tw` | 繁體中文（預設） |
| `zh-cn` | 简体中文 |
| `en`    | English |

工具列右上方有語言下拉選單，選擇後立即生效。語言偏好自動儲存至 `language_config.json`。

```json
{ "language": "en" }
```

`language_config.json` 位於 exe 旁（若目錄可寫），或使用者主目錄（`~/.githelper_config.json`）。

---

## 語言載入機制（exe 版本）

程式採用「**內建預設 + 外部覆蓋**」的雙層合併策略：

### 優先順序

```
.lang/GitHelperPro/<lang>.json   ← 最優先（使用者自訂覆蓋）
language/<lang>.json             ← 次選（exe 旁，向下相容）
[bundled inside exe]             ← 預設（exe 內建，永遠可用）
```

1. 程式啟動時**永遠先從 exe 內建語言讀取**（打包時已包含 `en`, `zh-tw`, `zh-cn`）
2. 若 exe 旁有 `.lang/GitHelperPro/`（或 `language/`）資料夾，額外讀取其中的 JSON：
   - 同檔名（如 `en.json`）：外部版本的所有 key **覆蓋**內建版本
   - 外部沒有的 key：仍使用內建版本（不影響其他語言功能）
   - 新增的語言檔（如 `jp.json`）：直接出現在語言選單，不影響既有語言

### 實際效果一覽

| 情境 | 結果 |
|------|------|
| exe 旁沒有 `.lang/` | 載入內建 3 種語言，完全正常 |
| 加入 `.lang/.../jp.json` | 語言選單新增「日本語」，3 種預設語言不受影響 |
| 修改 `.lang/.../en.json` 的部分 key | 修改的 key 生效，其他 key 仍使用內建值 |
| 完整替換 `.lang/.../en.json` | 整個英文介面由外部版本提供 |

### 日誌診斷

- 程式啟動時會在 console 列印每個語言檔的實際載入路徑（`[lang] Loaded ...`）
- exe 執行時會在 exe 旁生成 `githelper_language.log` 供診斷使用
- 程式中可透過 `from src.core.language_manager import lm; print(lm.last_loaded)` 查看最後載入的檔案

---

## 新增語言（開發環境）

1. 複製 `language/_template.json` 為 `language/<語言代碼>.json`（例如 `jp.json`）
2. 修改 `_meta.display_name` 為語言名稱（例如 `日本語`）
3. 翻譯所有 key 的值
4. 儲存後重啟程式，語言選單會自動出現新語言

## 新增／覆蓋語言（exe 發佈版本）

1. 在 exe 同層建立 `.lang/GitHelperPro/` 資料夾
2. 將語言 JSON 放入：
   - 新語言：`jp.json`（全新 key/value）
   - 覆蓋既有語言：`en.json`（只需包含要修改的 key；未提供的 key 自動沿用內建）
3. 重新啟動 exe 即生效

> **注意事項**
> - JSON 中以 `_meta.display_name` 作為語言選單顯示的名稱；檔名（不含 `.json`）為語言代碼
> - 若外部檔案未提供 `_meta.display_name`，自動 fallback 到內建版本的名稱
> - 檔名不能以 `_` 開頭（`_template.json` 等不會被掃描）
