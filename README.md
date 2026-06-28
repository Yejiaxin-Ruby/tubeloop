# Tubeloop

一个用于 YouTube 英语学习的 MVP：导入 YouTube 链接，读取真实字幕，完成精听/泛听、AI 讨论、选中字幕翻译和表达库保存。

## 功能

- FastAPI 单服务部署，同时提供网页和 API
- 真实 YouTube 视频嵌入播放
- 读取 YouTube 英文字幕，并尽量获取或生成中文字幕
- 点击字幕跳转到对应播放时间
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
docker build -t tubeloop .
docker run -p 8000:8000 -e PORT=8000 tubeloop
```

## 部署到 AI Builder

部署平台会从 public GitHub 仓库拉取代码，并使用根目录的 `Dockerfile` 构建。

需要提供：

- GitHub public repo URL
- service name，例如 `tubeloop`
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

当前 MVP 支持 1 小时以内、可读取英文字幕的 YouTube 视频。少数无字幕、字幕被关闭或被 YouTube 限制访问的视频会导入失败。
