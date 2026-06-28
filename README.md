# YouTube English Learning MVP

一个用于 YouTube 英语学习的 MVP：导入视频链接，使用 mock 字幕完成精听/泛听、AI 讨论、选中字幕翻译和表达库保存。

## 功能

- FastAPI 单服务部署，同时提供网页和 API
- 字幕学习界面
- 选中字幕后翻译或加入表达库
- AI 教练聊天
- 语音转文字入口
- 历史视频和表达库
- SQLite MVP 数据存储

## 本地运行

```bash
pip install -r requirements.txt
uvicorn youtube_learning_app.main:app --host 0.0.0.0 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## Docker 运行

```bash
docker build -t youtube-english-mvp .
docker run -p 8000:8000 -e PORT=8000 youtube-english-mvp
```

## 部署到 AI Builder

部署平台会从 public GitHub 仓库拉取代码，并使用根目录的 `Dockerfile` 构建。

需要提供：

- GitHub public repo URL
- service name，例如 `youtube-english-mvp`
- branch，例如 `main`

平台会自动注入：

```text
AI_BUILDER_TOKEN
```

可选环境变量：

```text
APP_DB_PATH=/app/data/youtube_learning.sqlite3
AI_BUILDER_CHAT_MODEL=gpt-5
AI_BUILDER_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

## 备注

当前 MVP 的 YouTube 导入仍使用 mock 字幕数据。真实 YouTube 字幕抓取可以在下一阶段加入。
