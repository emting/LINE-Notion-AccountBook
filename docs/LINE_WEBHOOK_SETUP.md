# LINE Messaging API Webhook 設定手冊

本手冊用於指引完成 LINE 官方帳號的 Webhook 設定，讓官方帳號能將使用者的記帳訊息（文字與圖片）傳送至部署好的 `LINE-Notion-AccountBook` 系統中。

## 🎯 前置準備

在開始前，請先準備以下資料：
1. **部署後公開網址**：例如 `https://your-app.up.railway.app`
2. **實際 Webhook URL**：加上 `/webhook` 路徑，例如 `https://your-app.up.railway.app/webhook`
3. 準備好寫入 `.env`（或部署平台環境變數）的兩個值：
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_CHANNEL_SECRET`

---

## 🛠 操作步驟

### 1. 進入 LINE Developers Console

1. 開啟 [LINE Developers Console](https://developers.line.biz/console/)。
2. 登入與 LINE 官方帳號綁定的帳號。
3. 進入對應的 Provider。
4. 開啟本專案使用的 **Messaging API Channel**。

### 2. 確認 Channel 基本資訊

在 Channel 頁面先確認以下資訊存在：
- Channel ID
- Channel secret
- Messaging API 已啟用
- 官方帳號已建立並綁定

**取得 Channel Secret：**
1. 進入 `Basic settings` 分頁。
2. 複製 `Channel secret`。
3. 寫入專案 `.env` 或部署平台的 `LINE_CHANNEL_SECRET`。

### 3. 產生或重新產生 Channel Access Token

1. 進入 `Messaging API` 分頁。
2. 找到最下方的 `Channel access token (long-lived)`。
3. 按 `Issue` 或重新產生長期 token。
4. 複製 token。
5. 寫入專案 `.env` 或部署平台的 `LINE_CHANNEL_ACCESS_TOKEN`。

---

## 🌐 設定與驗證 Webhook

### 4. 設定 Webhook URL

1. 在 `Messaging API` 分頁找到 `Webhook settings`。
2. 將 `Webhook URL` 設為：`https://你的部署網址/webhook`。
3. 按 `Update` 或 `Save`。

### 5. 驗證 Webhook URL

1. 點擊 `Verify` 按鈕。
2. **預期結果：** Console 顯示成功或跳出綠色提示。
3. **若驗證失敗，請依序檢查：**
   - 部署網址是否可從公網存取（HTTPS）。
   - `/webhook` 路徑是否正確加上。
   - 伺服器服務是否已成功啟動（是否有 502/503 錯誤）。
   - 平台環境變數是否已實裝完成。
   - 應用啟動時的 `validate_config()` 是否因缺少設定而導致應用程式崩潰。

### 6. 啟用 Webhook

1. 在 `Use webhook` 開關中切換為 **開啟**。
2. 確認狀態顯示為 `Enabled`。

---

## ⚙️ 關閉自動回覆避免衝突

請到 [LINE Official Account Manager](https://manager.line.biz/) 或 Messaging API 的對應設定處檢查：
- `Auto-reply messages`（自動回覆訊息）：**切換為停用/關閉**
- `Greeting messages`（加入好友歡迎訊息）：可依需求保留或關閉

**原因**：
若 LINE 官方後台自動回覆仍開啟，會與本記帳系統的回覆重疊或產生干擾。本專案的對話流程已全數交由 Flask + Messaging API 掌控。

---

## ✅ 實際驗證流程

### 文字訊息驗證
1. 用自己的 LINE 帳號加入該官方帳號好友。
2. 傳送測試訊息：`買了 30 本數學講義 $4500`
3. **預期結果**：
   - LINE 聊天室收到確認記帳成功的訊息。
   - Notion 記帳資料庫新增一筆 $4,500 教材費的資料。

### 圖片訊息驗證
1. 傳送一張清楚的發票或收據照片。
2. **預期結果**：
   - 系統先立即回覆「📸 收到圖片，正在進行 OCR 辨識中...」。
   - 稍等幾秒後，收到 Push Message 傳來的解析結果。
   - Notion 記帳資料庫新增由 OCR 解析出的對應資料。

---

## 🩺 常見問題排查

### ❌ Verify 失敗
- 檢查 URL 是否使用 `https`。
- 檢查網址尾端是否確實包含 `/webhook`。
- 檢查雲端服務日誌，觀看是否處於休眠或因環境變數不齊全導致啟動失敗。

### ❌ 有收到 LINE 訊息但系統沒反應
- 檢查 `LINE_CHANNEL_ACCESS_TOKEN` 是否貼錯或複製到空白。
- 檢查 `LINE_CHANNEL_SECRET` 是否與 Console 一致。
- 檢查遠端伺服器日誌（Logs）是否有因 X-Line-Signature 導致的「簽章驗證失敗 (403 invalid signature)」。

### ❌ 文字可用、但發圖片沒反應
- 檢查該圖片檔案是否超過 `10MB` 導致伺服器阻擋。
- 檢查 `GEMINI_API_KEY` 是否有效或額度耗盡。
- 檢查伺服器環境背景 threading 的流程是否出錯，或該 Channel 是否無權限發送 Push Message。
