# Hash Comparator Pro 🚀

這是一個基於 Python `tkinterdnd2` 開發的進階檔案雜湊（Hash）比對工具。專為需要快速辨識、比對大量檔案唯一性的開發者或系統管理員設計。

## 🌟 核心功能

- **拖放支援 (Drag & Drop)**：直接將多個檔案或資料夾中的檔案拖入視窗即可開始計算。
- **路徑防重過濾**：自動識別並跳過已存在於列表中的相同路徑，避免重複處理。
- **內容視覺化比對**：
    - 使用 **SHA-256** 作為內容唯一性判斷標準。
    - **自動著色機制**：內容完全相同的檔案（即使檔名不同、路徑不同）會被標記為**相同的底色**。
- **多演算法支援**：同步計算 MD5、SHA-1、SHA-256。
- **動態排序**：點擊任意標題（如 SHA256 或檔案大小）即可對列表進行即時排序，方便對齊相同內容的檔案。
- **效能優化**：採用 64KB Buffer 分段讀取機制，穩定處理 GB 級大檔案而不消耗過量記憶體。

## 🛠 系統需求

- **Python 3.8+**
- **tkinterdnd2**: 用於處理原生作業系統的拖放事件。

## 📦 安裝步驟

1. **複製專案**
```bash
git clone [https://github.com/your-repo/hash-comparator.git](https://github.com/your-repo/hash-comparator.git)
cd hash-comparator
```

## 🚀 快速上手
1. 執行程式： 
```bash
python main.py
```
2. 導入檔案：從檔案總管直接拖入一或多個檔案至視窗中。
3. 比對策略：
- 相同顏色：代表檔案內容完全相同（SHA-256 碰撞率極低）。
- 排序對齊：點擊標題可按檔名、雜湊值排序，方便對齊重複檔案。

## 🏗️ 系統架構
本專案遵循邏輯與介面分離（Decoupling）的設計原則：
- FileHasher: 負責 hashlib 調用、緩衝區讀取與 I/O 例外處理。
- HashApp: 負責 Tkinter 事件循環、拖放註冊、Treeview 渲染與顏色管理。
- Unique Control: 使用 set() 儲存絕對路徑，確保路徑唯一性檢查效率為 $O(1)$。

## 📝 核心代碼參考Python
```python
# 高效能分段讀取邏輯
with open(file_path, 'rb') as f:
    for chunk in iter(lambda: f.read(65536), b""):
        for obj in hash_objs.values():
            obj.update(chunk)
```

## 📜 授權本專案採用 MIT License。
