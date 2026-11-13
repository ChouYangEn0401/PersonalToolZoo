# age 測試向量的出處與授權

## 出處

- 來源：C2SP CCTV（Community Cryptography Test Vectors），<https://github.com/C2SP/CCTV>，
  目錄 `age/testdata/`，commit `b88c4b206254ac543df240097e0f1fcc6a664821`（2026-11-01）。
- 取得方式：以資料方式下載（git 稀疏取出），只讀取檔案內容，沒有執行來源裡的任何程式
  （包括產生向量用的 Go 程式）。
- `cctv/` 裡的檔案逐位元組照抄，沒有修改；`SHA256SUMS` 是本 repo 另外產生的雜湊清單，
  測試會先比對它，避免 git 換行轉換弄壞向量（本資料夾的 `.gitattributes` 關掉了轉換）。

## 選了哪些

原始 147 個向量中放了 128 個：除了下面這些之外全部。

- 沒放：`hybrid*` 與 `armor_hybrid`（共 19 個）。它們使用後量子 `mlkem768x25519` 收件人，
  本工具不支援（`cryptography` 42 沒有 ML-KEM）。

## 授權

CCTV 的 README 說明：`testdata` 資料夾裡的向量以
[Zero-Clause BSD](https://opensource.org/licenses/0BSD)、
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) 或
[Unlicense](https://unlicense.org/) 授權，由使用者任選；README 也說明可以不附出處直接複製。
本 repo 選用 0BSD，原文如下：

```text
Copyright (c) 2022 The age Authors

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

## 向量檔的格式

每個檔案先是幾行 `鍵: 值`，一個空行，然後是 age 檔（可能用 zlib 壓縮）。
`expect` 是預期結果（`success`、`no match`、`HMAC failure`、`header failure`、
`payload failure`、`armor failure`）；`payload` 是應該釋出的明文的 SHA-256
（失敗的向量則是「出錯之前已釋出的明文」）；`identity`／`passphrase` 是要用的鑰匙。
詳細說明見 CCTV 的 `age/README.md`。
