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
- **說話者標註** - 通用標籤（Speaker A/B/…）：預設**停頓啟發式**，可選 **pyannote** 事後分段（`pyannote_v1`）；非具名說話者辨識
- **Acquisition Hardening** - 取得 YouTube 時的診斷與 fallback policy（僅本機，無遠端委派）

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

預設 Docker 後端映像僅安裝 **`requirements.txt`**（走 Whisper API，不含 PyTorch／pyannote）。若要使用 **pyannote** 分段，請在本機用 CLI 安裝 speaker 額外套件（見下節「說話者標註」），或自行擴充 Dockerfile。

## 說話者標註（多人／分段）

標籤為 **Speaker A/B/…** 等通用標籤，非真人姓名。

| 策略 | CLI `--speaker-strategy` | 額外 Python 依賴 | 說明 |
|------|------------------------|------------------|------|
| 停頓啟發式（預設） | `pause_heuristic_v1` | 僅基礎 `requirements.txt` | 快；準確度較低 |
| **pyannote** 分段 | `pyannote_v1` | PyTorch 與 `pyannote.audio` 等 | 品質較佳；需 Hugging Face token 與**各 gated 模型授權** |

### 使用 pyannote（`pyannote_v1`）的前置條件

1. **Python 3.11+** 與系統已安裝 **FFmpeg**（亦用於分段前對 MP3 等音訊做正規化）。
2. 擇一安裝 **CPU 或 GPU** 套件組（見 `requirements-speaker-cpu.txt`／`requirements-speaker-gpu.txt`）：
   ```bash
   pip install -r requirements.txt -r requirements-speaker-cpu.txt
   ```
   GPU 環境請依機器 CUDA 調整 GPU 檔內的 PyTorch index。
3. **Hugging Face**
   - 在 [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) 建立 **read** token。
   - 在 `.env` 設定 `PYANNOTE_AUTH_TOKEN`（見 `.env.example`）。
   - 對 pipeline 會用到的**每個** gated 模型頁面點選 **同意／存取**（至少包含 `pyannote/speaker-diarization-3.1` 及其相依，例如 `pyannote/speaker-diarization-community-1`）。同意後權限同步可能需要數分鐘。

### CLI 範例

```bash
python main.py --list-speaker-strategies

# 僅啟發式（不需 pyannote）
python main.py --speaker-attribution https://youtube.com/watch?v=VIDEO_ID

# 真實分段（需安裝 pyannote + PYANNOTE_AUTH_TOKEN）
python main.py --speaker-strategy pyannote_v1 "https://www.youtube.com/watch?v=VIDEO_ID"
```

啟用說話者標註時，輸出會包含 `*_speaker_segments.json` 與 metadata 內相關欄位。

## 使用方式

### CLI

> 需要 Python 3.11+ 與 FFmpeg

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 基本使用
python main.py https://youtube.com/watch?v=VIDEO_ID

# 說話者標註（詳見上方「說話者標註」）
python main.py --speaker-attribution https://youtube.com/watch?v=VIDEO_ID
python main.py --speaker-strategy pyannote_v1 https://youtube.com/watch?v=VIDEO_ID

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

## 文件

- Acquisition reasoning / failure classes / fallback logic：
  - `docs/acquisition-runbook.md`
- 已移除的 backup HTTP 委派（說明）：
  - `docs/backup-delegation-removed.md`
- 已合併的 OpenSpec **主規格**：
  - `openspec/specs/`
- 若仍存在的進行中 OpenSpec **change**：
  - `openspec/changes/harden-youtube-acquisition/`
- 已封存提案：
  - `openspec/changes/archive/`

## 環境變數

| 變數 | 說明 | 必填 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `PYANNOTE_AUTH_TOKEN` | Hugging Face token（`pyannote_v1`、gated 模型） | 僅使用 pyannote 策略時 |
| `HF_TOKEN` | 選填；部分 Hugging Face 工具亦會讀取 | No |
| `SERVICE_ROLE` | 選填；會反映在 `/api/health` | No |
| `YT_DLP_COOKIES_FILE` | Netscape 格式 cookies 檔案 | No |
| `YT_DLP_COOKIES_FROM_BROWSER` | 從瀏覽器讀 cookies 的 browser 名稱 | No |

請複製 `.env.example` 為 `.env` 後編輯；勿將真實金鑰提交至版本庫。

### 執行測試

`tests/` 內的測試會建立 `TranscriptionService`，進而在 `WhisperTranscriber` 初始化時建立 OpenAI client。**執行 `pytest` 前請在環境中設定 `OPENAI_API_KEY`**（單元測試可用占位值即可，例如 `test`；實際不會對外呼叫 API）。

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=test
python -m pytest tests/
```

## 目前專案狀態

目前包含：長影片逐字稿 pipeline、說話者標註（啟發式與可選 pyannote）、YouTube acquisition hardening 等。已完成封存的 OpenSpec 變更見 `openspec/changes/archive/`，合併後主規格見 `openspec/specs/`。

## 限制

- Whisper API 有 25MB 檔案大小限制；目前音訊品質預設壓低到 64kbps 以符合限制
- 轉錄品質仍受音訊清晰度與 Whisper 能力影響
- GPT 校正仍可能改動語意，建議人工審閱
- YouTube acquisition 的穩定度仍可能受 host / network / IP reputation 影響；請搭配 acquisition runbook 使用

## 授權

MIT License - 詳見 [LICENSE](LICENSE)

## Contributing

歡迎提出 Issue 與 Pull Request！

---

Developed and maintained by [Azetry](https://github.com/azetry)
