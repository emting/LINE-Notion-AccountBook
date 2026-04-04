# LINE-Notion-Sync

這個專案展示了 Manus 1.6 Max 的跨平台整合能力。透過建立一個 Flask Webhook 伺服器，我們能夠接收使用者從 LINE 官方帳號傳送的訊息，經過自然語言處理（NLP）解析出結構化的任務資訊（如標題、優先級、日期等），最後自動透過 Notion API 將這些任務寫入指定的 Notion 資料庫中。

## 系統架構

1. **Input Layer (LINE)**: 使用者透過 LINE 發送訊息，LINE 平台將訊息封裝為 Webhook Event 發送至我們的伺服器。
2. **Processing Layer (Manus Agent 模擬)**: 伺服器接收並驗證請求，提取文字內容，並將非結構化的自然語言轉換為結構化的任務資料。
3. **Output Layer (Notion)**: 透過 Notion API 將結構化資料寫入指定的 Notion 資料庫，並透過 LINE 回傳確認訊息。

## 專案結構

```
line-notion-sync/
├── app/
│   ├── __init__.py
│   ├── main.py              # Flask 應用程式與 Webhook 進入點
│   ├── line_handler.py      # LINE Messaging API 處理邏輯
│   ├── notion_client.py     # Notion API 整合模組
│   └── data_processor.py    # 核心資料處理與解析邏輯
├── config/
│   ├── __init__.py
│   └── settings.py          # 環境變數設定檔
├── tests/
│   └── test_processor.py    # 測試程式
├── requirements.txt         # 依賴套件
└── README.md                # 專案說明文件
```

## 前置準備

1. **LINE Official Account**:
   - 前往 [LINE Developers Console](https://developers.line.biz/) 建立一個 Messaging API Channel。
   - 取得 `Channel Secret` 與 `Channel Access Token`。
   - 設定 Webhook URL（例如使用 ngrok 將本地伺服器暴露至外網：`https://<your-ngrok-url>/webhook`）。

2. **Notion Integration**:
   - 前往 [Notion Developers](https://www.notion.so/my-integrations) 建立一個 Internal Integration。
   - 取得 `Internal Integration Token` (API Key)。
   - 在 Notion 中建立一個資料庫，並將該資料庫分享給剛建立的 Integration。
   - 取得資料庫的 ID（從資料庫網址中提取）。

## 執行環境設定

1. 建立虛擬環境並安裝依賴：
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. 設定環境變數：
   ```bash
   export LINE_CHANNEL_ACCESS_TOKEN="your_line_token"
   export LINE_CHANNEL_SECRET="your_line_secret"
   export NOTION_API_KEY="your_notion_api_key"
   export NOTION_DATABASE_ID="your_notion_database_id"
   ```

3. 啟動伺服器：
   ```bash
   python -m app.main
   ```

## 使用方式

在 LINE 中向您的機器人發送以下格式的訊息：

1. **自由輸入**：
   `明天下午三點要開會，優先級高`
2. **結構化輸入**：
   `標題: 準備簡報 | 日期: 2026-04-10 | 優先級: 高`
3. **指令輸入**：
   `/task 寄送發票 --priority medium --date 2026-04-06`

系統會自動解析並將任務寫入 Notion 資料庫，同時在 LINE 中回覆確認訊息。
