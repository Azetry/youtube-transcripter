# YouTube Transcripter

一個強大的 YouTube 影片逐字稿工具，整合 OpenAI Whisper API 進行語音轉文字，並透過 GPT 自動校正轉錄結果。

## 功能特色

- **影片資訊擷取** - 透過 yt-dlp 免費擷取 YouTube 影片基本資料（標題、頻道、時長等）
- **語音轉文字** - 使用 OpenAI Whisper API (whisper-1) 進行高品質轉錄
- **智慧校正** - 透過 GPT-4o-mini 自動校正轉錄文字中的錯字與語句
- **差異比對** - 以 diff 格式呈現原始轉錄與校正後的差異
- **雙介面支援** - 提供 CLI 命令列工具與 Web 網頁介面
- **Docker 部署** - 支援 Docker Compose 一鍵部署

## 系統架構

```
youtube-transcripter/
├── src/                      # 核心模組
│   ├── youtube_extractor.py  # YouTube 影片擷取 (yt-dlp)
│   ├── whisper_transcriber.py# Whisper 語音轉文字
│   ├── text_corrector.py     # GPT 文字校正
│   └── diff_viewer.py        # 差異比對顯示
├── api/                      # FastAPI 後端
│   └── main.py
├── web/                      # Vue 3 前端
│   ├── src/
│   │   └── App.vue
│   └── Dockerfile
├── main.py                   # CLI 入口
├── docker-compose.yml        # Docker 部署設定
└── requirements.txt          # Python 依賴
```

## 快速開始

### 前置需求

- Docker + Docker Compose
- OpenAI API Key

### 部署

```bash
git clone https://github.com/azetry/youtube-transcripter.git
cd youtube-transcripter

# 設定環境變數
cp .env.example .env
# 編輯 .env 填入 OPENAI_API_KEY

# 啟動服務
docker compose up -d
```

開啟瀏覽器訪問 http://localhost:3000

## 使用方式

### CLI 命令列

> 需安裝 Python 3.11+、FFmpeg

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 基本使用
python main.py https://youtube.com/watch?v=VIDEO_ID

# 互動模式
python main.py -i

# 更多選項
python main.py --help
```

### API 端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/health` | GET | 健康檢查 |
| `/api/video/info` | POST | 取得影片資訊 |
| `/api/transcribe` | POST | 開始轉錄任務 |
| `/api/task/{id}` | GET | 查詢任務狀態 |

## 技術棧

### 後端
- **Python 3.11+**
- **FastAPI** - 現代高效能 Web 框架
- **yt-dlp** - YouTube 影片下載
- **OpenAI API** - Whisper 轉錄 + GPT 校正

### 前端
- **Vue 3** - 前端框架
- **Vite** - 建置工具
- **Tailwind CSS** - 樣式框架

### 部署
- **Docker** + **Docker Compose**
- **Nginx** - 反向代理

## 環境變數

| 變數名稱 | 說明 | 必填 |
|----------|------|------|
| `OPENAI_API_KEY` | OpenAI API 金鑰 | 是 |

## 限制說明

- Whisper API 單次上傳限制 25MB，本工具已將音訊品質調整為 64kbps 以符合限制
- 轉錄品質取決於音訊清晰度與 Whisper 模型能力
- GPT 校正可能會改變原意，建議人工複核

## 授權條款

MIT License - 詳見 [LICENSE](LICENSE) 檔案

## 貢獻指南

歡迎提交 Issue 與 Pull Request！

---

由 [Azetry](https://github.com/azetry) 開發維護
