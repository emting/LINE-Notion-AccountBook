# LINE-Notion-Sync 完整實作與部署指南

這份指南將帶領您從零開始，逐步完成 LINE 官方帳號申請、Notion 資料庫建立、OpenAI API 串接，直到將系統部署上線。整個過程預計需要約 30 分鐘。

## 第一階段：申請與設定 LINE Messaging API

根據 LINE 官方最新的開發者指南 [1]，建立 Messaging API 頻道需要先建立 LINE 官方帳號。

### 1. 建立 LINE 官方帳號
首先，您需要註冊並建立一個 LINE 官方帳號作為機器人的本體：
1. 前往 [LINE Business ID 註冊頁面](https://account.line.biz/signup)，選擇使用您的個人 LINE 帳號或電子郵件進行註冊。
2. 登入後，填寫官方帳號申請表單（[LINE Entry Form](https://entry.line.biz/)），輸入您的機器人名稱與相關資訊。
3. 完成後，系統會引導您進入 [LINE Official Account Manager](https://manager.line.biz/)。

### 2. 啟用 Messaging API
在 LINE Official Account Manager 中，您需要啟用 API 功能：
1. 點擊右上角的「設定」（Settings）。
2. 在左側選單中選擇「Messaging API」。
3. 點擊「啟用 Messaging API」（Enable Messaging API）。
4. 系統會要求您選擇或建立一個 Provider（提供者），請輸入您的公司或個人名稱。請注意，一旦選定 Provider 後將無法更改 [1]。
5. 填寫隱私權政策與服務條款網址（可選填），完成啟用。

### 3. 取得 API 金鑰
接下來，我們需要前往開發者後台取得兩把關鍵的鑰匙：
1. 登入 [LINE Developers Console](https://developers.line.biz/console/)。
2. 選擇您剛剛建立的 Provider，點擊您的 Channel 進入設定頁面。
3. 在 **Basic settings** 頁籤中，向下捲動找到 `Channel secret`，點擊複製並妥善保存。
4. 切換到 **Messaging API** 頁籤，向下捲動找到 `Channel access token (long-lived)`，點擊「Issue」按鈕生成一組長效權杖，點擊複製並妥善保存 [2]。

### 4. 關閉自動回覆功能
為了避免 LINE 內建的自動回覆與我們的程式衝突，必須將其關閉：
1. 回到 [LINE Official Account Manager](https://manager.line.biz/)。
2. 點擊右上角的「設定」，選擇左側的「回應設定」（Response settings）。
3. 將「加入好友的歡迎訊息」（Greeting message）與「自動回應訊息」（Auto-reply messages）都設定為「停用」（Disabled）[2]。

---

## 第二階段：設定 Notion 資料庫與 API

我們需要建立一個 Notion 資料庫來儲存任務，並申請 API 金鑰讓程式能夠寫入資料。

### 1. 申請 Notion API 金鑰
根據 Notion 開發者文件 [3]，內部整合（Internal Integration）是最適合單一工作區的認證方式：
1. 前往 [Notion My Integrations](https://www.notion.so/my-integrations) 頁面。
2. 點擊左側的「New integration」按鈕。
3. 填寫整合名稱（例如：LINE-Notion-Sync），並選擇您要關聯的工作區（Associated workspace）。
4. 點擊「Submit」送出。
5. 在建立完成後的 **Configuration** 頁面，您會看到一組 `Internal Integration Secret`（通常以 `ntn_` 開頭），請點擊「Show」並複製保存。

### 2. 建立任務資料庫
在您的 Notion 工作區中建立一個新的頁面：
1. 新增一個頁面，選擇 **Table** 視圖的資料庫（Database - Full page）。
2. 設定以下八個必要的欄位（請確保名稱完全一致，大小寫也需相符）：
   - `Name`：屬性為 Title（預設欄位，可重新命名為 Name）
   - `Category`：屬性為 Select（選項可包含：Meeting, Todo, Feature, Bug, Idea 等）
   - `Priority`：屬性為 Select（選項：High, Medium, Low）
   - `Due Date`：屬性為 Date
   - `Description`：屬性為 Text
   - `Source`：屬性為 Text（記錄發送訊息的使用者名稱）
   - `Status`：屬性為 Select（選項：Not Started, In Progress, Done）
   - `Created At`：屬性為 Date（記錄任務建立時間）

### 3. 連接 Integration 與取得 Database ID
1. 在剛剛建立的資料庫頁面右上角，點擊「...」圖示。
2. 向下捲動找到「Connections」選項，點擊「Connect to」。
3. 在搜尋框中輸入您剛剛建立的 Integration 名稱（LINE-Notion-Sync），點擊確認連接 [3]。
4. 接著，從瀏覽器網址列複製該頁面的 URL。網址格式通常為 `https://www.notion.so/<workspace_name>/<database_id>?v=<view_id>`。
5. 提取問號 `?` 之前、斜線 `/` 之後的 32 個字元，這就是您的 `Database ID`。

---

## 第三階段：取得 OpenAI API 金鑰

為了讓系統具備強大的自然語言解析能力，我們需要 OpenAI 的 API。

1. 前往 [OpenAI API 平台](https://platform.openai.com/) 並登入您的帳號。
2. 在左側選單中選擇 **API keys**。
3. 點擊「Create new secret key」，為金鑰命名（例如：LINE-Bot）。
4. 點擊建立後，複製顯示的 API 金鑰（以 `sk-` 開頭）。請注意，這把金鑰只會顯示一次。

---

## 第四階段：環境變數整理

到目前為止，您應該已經收集了以下六個關鍵的環境變數，請將它們整理好，我們在部署時會用到：

| 變數名稱 | 來源平台 | 說明 |
|---------|---------|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Developers | 長效存取權杖，用於發送訊息 |
| `LINE_CHANNEL_SECRET` | LINE Developers | 頻道密鑰，用於驗證 Webhook 簽章 |
| `NOTION_API_KEY` | Notion Integrations | 內部整合密鑰（以 ntn_ 開頭） |
| `NOTION_DATABASE_ID` | Notion 網址列 | 32 字元的資料庫識別碼 |
| `OPENAI_API_KEY` | OpenAI Platform | OpenAI API 金鑰（以 sk- 開頭） |
| `LLM_MODEL` | 自訂 | 建議設定為 `gpt-4.1-mini` |

---

## 第五階段：部署系統至 Railway

我們選擇 Railway 作為部署平台，因為它提供簡單的 GitHub 整合與免費的基礎額度 [4]。

### 1. 建立 Railway 專案
1. 登入 [Railway 控制台](https://railway.app/)。
2. 點擊右上角的「New Project」。
3. 選擇「Deploy from GitHub repo」。
4. 如果是第一次使用，需要授權 Railway 存取您的 GitHub 帳號。
5. 選擇您的 `line-notion-sync` 儲存庫。
6. 點擊「Deploy Now」。

### 2. 設定環境變數
1. 在 Railway 的專案畫面上，點擊剛剛建立的服務。
2. 切換到 **Variables** 頁籤。
3. 點擊「New Variable」，將第四階段整理的六個環境變數逐一新增進去。
4. 新增完成後，Railway 會自動重新部署您的應用程式。

### 3. 取得公開網址 (Public URL)
1. 切換到 **Settings** 頁籤。
2. 向下捲動到 **Networking** 區塊。
3. 點擊「Generate Domain」按鈕，Railway 會為您生成一個公開的 HTTPS 網址（例如：`line-notion-sync-production.up.railway.app`）[4]。
4. 複製這個網址，並在後方加上 `/webhook`，這就是我們完整的 Webhook URL（例如：`https://line-notion-sync-production.up.railway.app/webhook`）。

---

## 第六階段：完成 LINE Webhook 設定與測試

最後一步，我們要把部署好的伺服器網址告訴 LINE。

### 1. 設定 Webhook URL
1. 回到 [LINE Developers Console](https://developers.line.biz/console/)。
2. 進入您的 Channel，切換到 **Messaging API** 頁籤。
3. 找到 **Webhook URL** 區塊，點擊「Edit」。
4. 貼上您在 Railway 取得的完整 Webhook URL（包含 `/webhook`），點擊「Update」[2]。
5. 點擊旁邊的「Verify」按鈕，如果顯示 Success，代表 LINE 成功連線到您的伺服器。
6. 將下方的「Use webhook」開關打開。

### 2. 最終測試
1. 在 Messaging API 頁籤中找到您官方帳號的 QR Code。
2. 使用手機的 LINE 掃描加入好友。
3. 傳送測試訊息：「幫我訂明天下午三點的會議室，優先級很高」。
4. 系統應該會在幾秒內回覆確認訊息，顯示已透過 AI 智慧解析並寫入 Notion。
5. 打開您的 Notion 資料庫，確認資料是否正確寫入對應的欄位。

恭喜！您已經成功部署了結合 LLM 智慧解析的 LINE-Notion-Sync 自動化系統。

---

## 參考資料
[1] Get started with the Messaging API | LINE Developers. https://developers.line.biz/en/docs/messaging-api/getting-started/
[2] Build a bot | LINE Developers. https://developers.line.biz/en/docs/messaging-api/building-bot/
[3] Build your first integration | Notion Developers. https://developers.notion.com/docs/create-a-notion-integration
[4] Deploy a Flask App | Railway Guides. https://docs.railway.com/guides/flask
