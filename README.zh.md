# YouTube Transcripter

一個以 OpenAI Whisper API 進行語音轉文字、並結合 GPT 自動校正文稿的 YouTube 逐字稿處理工具。

[English](README.md)

## 功能特色

- **影片資訊擷取** - 透過 yt-dlp 取得 YouTube 影片資訊（標題、頻道、時長等）
- **語音轉文字** - 使用 OpenAI Whisper API（whisper-1）進行高品質轉錄
- **智慧校正** - 使用 GPT-4o-mini 自動修正文稿
- **差異比對** - 可檢視原始稿與校正版之間的 diff
- **雙介面** - 提供 CLI 與 Web 介面
- **Docker 部署** - 可用 Docker Compose 快速部署
- **長影片流程** - 支援 chunking、merge / dedupe 與長影片逐字稿流程
- **Acquisition Hardening** - 支援取得 YouTube 時的診斷、fallback policy 與 backup-service delegation 基礎能力

## 架構

```text
youtube-transcripter/
├── src/                      # 核心模組
│   ├── youtube_extractor.py  # YouTube 擷取（yt-dlp）
│   ├── whisper_transcriber.py# Whisper 語音轉文字
│   ├── text_corrector.py     # GPT 文稿校正
│   └── diff_viewer.py        # Diff 顯示
├── api/                      # FastAPI backend
│   └── main.py
├── web/                      # Vue 3 frontend
│   ├── src/
│   │   └── App.vue
│   └── Dockerfile
├── main.py                   # CLI 入口
├── docker-compose.yml        # 預設部署設定
└── requirements.txt          # Python 相依套件
```

## 快速開始

### 先決條件

- Docker + Docker Compose
- OpenAI API Key

### 部署

```bash
git clone https://github.com/azetry/youtube-transcripter.git
cd youtube-transcripter

# 設定環境變數
cp .env.example .env
# 編輯 .env，填入 OPENAI_API_KEY

# 啟動服務
docker compose up -d
```

前往： http://localhost:3000

## 使用方式

### CLI

> 需要 Python 3.11+ 與 FFmpeg

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

### API Endpoints

| Endpoint | Method | 說明 |
|----------|--------|------|
| `/api/health` | GET | 一般健康檢查 |
| `/api/video/info` | POST | 取得影片資訊 |
| `/api/transcribe` | POST | 啟動轉錄任務 |
| `/api/task/{id}` | GET | 查詢任務狀態 |
| `/delegate/health` | GET | Backup-service 健康檢查 |
| `/delegate/transcribe` | POST | Backup-service delegated transcription |

## 文件

- Acquisition reasoning / failure classes / fallback logic：
  - `docs/acquisition-runbook.md`
- A/B backup-service 部署與驗收操作手冊：
  - `docs/backup-service-deployment.md`
- Active OpenSpec changes：
  - `openspec/changes/upgrade-transcription-pipeline/`
  - `openspec/changes/harden-youtube-acquisition/`

## 環境變數

| 變數 | 說明 | 必填 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `BACKUP_SERVICE_URL` | A→B delegation 用的 backup-service URL | No |
| `BACKUP_SERVICE_TOKEN` | A/B 共用的 bearer token | No |
| `SERVICE_ROLE` | 服務角色標記（例如 `backup`） | No |
| `YT_DLP_COOKIES_FILE` | Netscape 格式 cookies 檔案 | No |
| `YT_DLP_COOKIES_FROM_BROWSER` | 從瀏覽器讀 cookies 的 browser 名稱 | No |

## Backup Deployment

若要把這個 repo 當成 B 端 backup service（只跑 backend、不啟 frontend）：

```bash
export BACKUP_SERVICE_TOKEN=<shared-secret>
export OPENAI_API_KEY=<key>

docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d
```

此模式會：
- 對外 publish backend `8000`
- 設定 `SERVICE_ROLE=backup`
- 不啟 frontend

更多細節請看：`docs/backup-service-deployment.md`

## 目前專案狀態

目前 repo 主要包含兩條主線：
1. 升級後的長影片逐字稿 pipeline
2. YouTube acquisition hardening + backup-service fallback MVP

OpenSpec changes 目前仍保留在 active state，尚未 archive。

## 限制

- Whisper API 有 25MB 檔案大小限制；目前音訊品質預設壓低到 64kbps 以符合限制
- 轉錄品質仍受音訊清晰度與 Whisper 能力影響
- GPT 校正仍可能改動語意，建議人工審閱
- YouTube acquisition 的穩定度仍可能受 host / network / IP reputation 影響；請搭配 acquisition runbook 與 backup deployment guide 使用

## 授權

MIT License - 詳見 [LICENSE](LICENSE)

## Contributing

歡迎提出 Issue 與 Pull Request！

---

Developed and maintained by [Azetry](https://github.com/azetry)
