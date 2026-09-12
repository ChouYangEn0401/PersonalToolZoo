# Key escrow / backdoor experiment notes

## 1. 什麼是後門 / 金鑰保留 (Key Escrow) / 中央私鑰

- Key escrow / 後門：系統設計者或管理者在加密流程中留下一個可以解密（或恢復）資料的秘密通道。常見形式有：
  - 在封包中加入一個由「中央」公鑰加密的會話金鑰副本
  - 把私鑰分片並存放於可信第三方（由多方共同保管，可需閾值解鎖）
  - 在客戶端或伺服器上植入弱點（硬編碼金鑰 / 固定種子）讓實作方可恢復

- 結果：擁有 escrow 私鑰或能觸發後門者可以解密所有受影響的資料。

- 與純密碼學不同：後門是設計與管理/政策層面的決策，並非加密數學必然；只要系統提供了額外密鑰或後門程式碼，就可以解密。

## 2. 為何有些系統會有後門或中央私鑰？

- 法律或政策要求：某些國家或企業要求能在授權情況下存取用戶資料（例如合規、監管或執法需求），因此實作會包含 key escrow 機制。
- 可用性 / 備援：為了資料恢復，組織可能把主金鑰分片到多個安全位置（threshold escrow）。
- 惡意或不小心的實作：程式碼錯誤或惡意植入會導致弱金鑰或後門。

## 3. 風險與注意事項

- 擁有 escrow 的任何實體若被破壞（被入侵、內部人員惡用、司法命令等）都能解密資料。
- 後門會大幅降低系統安全性：攻擊者只要取得 escrow 私鑰即可解密大量資料。
- 若要設計可恢復的機制，優先考慮 threshold schemes（多方共管，需 M-of-N 同意）與透明的審計機制。

## 4. 簡單實驗建議

目的：模擬一個含 escrow 的 hybrid 加密流程，與一個無 escrow 的普通流程，觀察差異。

步驟：
1. 使用 `crypto_tool/core/pgp.py` 的 `encrypt_multi` 範例來產生一個多收件人封包。
2. 模擬一個 escrow 公鑰（由你生成的一組特殊 RSA 金鑰），在加密時同時把會話金鑰以 escrow 公鑰加密並加入封包。保存 escrow 私鑰。
3. 用真實收件者私鑰嘗試解密（應成功）。
4. 用 escrow 私鑰嘗試解密（也應成功）——這就是後門效果。
5. 測試若 escrow 私鑰外洩，攻擊者可以恢復哪些檔案。

改進實驗：
- 把 escrow 私鑰分成多份（Shamir's Secret Sharing）並由多個實體保存，測試 threshold 恢復流程。
- 在密鑰產生時檢查 RNG 質量，嘗試用低熵種子重現金鑰以示範 RNG 弱點。

## 5. 文件/指令

- 參考檔案：`crypto_tool/core/pgp.py`（已包含 `encrypt_multi` / `decrypt`）
- 建議命令（Python REPL 範例）：

```py
from crypto_tool.core import pgp
# 產生 escrow
esk_priv, esk_pub = pgp.generate_rsa_keypair(4096)
# 產生使用者金鑰
priv, pub = pgp.generate_rsa_keypair(4096)
# 加密（同時加入 escrow）
# 方法：先使用 pgp.encrypt_multi([pub, esk_pub], data)
# 解密者：使用 priv 或 esk_priv 呼叫 pgp.decrypt(...)
```

## 6. 小結

- 後門/escrow 是設計決定或實作決定，不是密碼學上的必然。技術上只要把會話金鑰用額外的公鑰加密並保存，該額外私鑰就能解密所有資料。
- 若要實驗，從 `encrypt_multi` 開始並加入一組 escrow 公鑰是最直接的示範。

***
請告訴我你要我幫你：
- 實作一個包含 escrow 的示範腳本（自動產生 escrow，產生封包，示範用 escrow 解密），或
- 把 GUI 加上一個 "Add escrow" 選項，或
- 先跑一些單元測試範例。