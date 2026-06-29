let subtitles = [];
let cards = [];
let currentVideoId = null;
let activeIndex = 0;
let captionMode = "both";
let isPlaying = false;

const apiBase = "/api";
const subtitleList = document.querySelector("#subtitleList");
const selectionPopover = document.querySelector("#selectionPopover");
const selectionTranslateButton = document.querySelector("#selectionTranslateButton");
const selectionSaveButton = document.querySelector("#selectionSaveButton");
const selectionResult = document.querySelector("#selectionResult");
const saveToast = document.querySelector("#saveToast");
const saveToastText = document.querySelector("#saveToastText");
const currentCaption = document.querySelector("#currentCaption");
const statusText = document.querySelector("#statusText");
const cardList = document.querySelector("#cardList");
const cardCount = document.querySelector("#cardCount");
const chatLog = document.querySelector("#chatLog");
const historyList = document.querySelector("#historyList");
const videoTitle = document.querySelector("#videoTitle");
const videoChannel = document.querySelector("#videoChannel");
const videoDuration = document.querySelector("#videoDuration");
const videoThumbnail = document.querySelector(".video-thumbnail");
const playbackProgress = document.querySelector("#playbackProgress");
const playbackTime = document.querySelector("#playbackTime");
const voiceButton = document.querySelector("#voiceButton");
const chatText = document.querySelector("#chatText");
const playButton = document.querySelector("#playButton");
const playButtonSmall = document.querySelector("#playButtonSmall");
const playIcon = document.querySelector("#playIcon");
const speedRange = document.querySelector("#speedRange");
const speedLabel = document.querySelector("#speedLabel");
const globalPanel = document.querySelector("#globalPanel");
const videoUrlInput = document.querySelector("#videoUrl");
const demoVideoButton = document.querySelector("#demoVideoButton");
let isListening = false;
let mediaRecorder = null;
let audioChunks = [];
let playbackTimer = null;
let playerSyncTimer = null;
let playbackSpeed = 1;
let selectedExpression = null;
let lastSelectionPoint = null;
let selectionChangeTimer = null;
let saveToastTimer = null;
let saveToastHideTimer = null;
let youtubePlayer = null;
let youtubePlayerReady = false;
let youtubeApiPromise = null;
let currentYoutubeVideoId = "";
const demoYoutubeUrl = "https://www.youtube.com/watch?v=arj7oStGLkU";

const fileModeVideo = {
  id: 1,
  title: "How to Think in English",
  channel: "English Learning Podcast",
  duration: "18:42",
  subtitles: [
    {
      time: "00:18",
      start_time: "00:18",
      end_time: "00:23",
      en: "The real shift happens when you stop translating every sentence in your head.",
      zh: "真正的转变发生在你不再在脑子里逐句翻译的时候。",
    },
    {
      time: "00:24",
      start_time: "00:24",
      end_time: "00:32",
      en: "Instead, you begin to connect English directly with images, actions, and feelings.",
      zh: "相反，你会开始把英语直接和画面、动作、感受连接起来。",
    },
    {
      time: "00:33",
      start_time: "00:33",
      end_time: "00:43",
      en: "That is why repetition with meaningful content matters much more than isolated vocabulary.",
      zh: "这就是为什么有意义内容里的重复，比孤立背单词更重要。",
    },
  ],
};

function timeToSeconds(value) {
  if (!value) return 0;
  const parts = value.split(":").map(Number);
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return 0;
}

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
  const seconds = Math.floor(totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function getPlaybackBounds() {
  if (!subtitles.length) return { current: 0, total: 0 };
  const current = getCurrentPlaybackSeconds();
  const lastLine = subtitles[subtitles.length - 1];
  const playerDuration =
    youtubePlayerReady && youtubePlayer?.getDuration ? Number(youtubePlayer.getDuration()) : 0;
  const total =
    playerDuration ||
    getLineEndSeconds(lastLine) ||
    current ||
    1;
  return { current, total };
}

function updatePlaybackProgress() {
  const { current, total } = getPlaybackBounds();
  const percent = total ? Math.min(100, Math.max(0, (current / total) * 100)) : 0;
  playbackProgress.style.width = `${percent}%`;
  playbackTime.textContent = `${formatTime(current)} / ${formatTime(total)}`;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

function visibleText(line) {
  if (captionMode === "en") return line.en;
  if (captionMode === "zh") return line.zh;
  if (captionMode === "none") return "";
  return line.en;
}

function getLineStartSeconds(line) {
  return Number(line?.start_seconds ?? timeToSeconds(line?.start_time || line?.time || ""));
}

function getLineEndSeconds(line) {
  return Number(line?.end_seconds ?? timeToSeconds(line?.end_time || line?.time || ""));
}

function getCurrentPlaybackSeconds() {
  if (youtubePlayerReady && youtubePlayer?.getCurrentTime) {
    return Number(youtubePlayer.getCurrentTime()) || 0;
  }
  if (!subtitles.length) return 0;
  return getLineStartSeconds(subtitles[activeIndex]);
}

function findSubtitleIndexByTime(seconds) {
  if (!subtitles.length) return 0;
  const exact = subtitles.findIndex((line) => {
    const start = getLineStartSeconds(line);
    const end = getLineEndSeconds(line);
    return seconds >= start && seconds < Math.max(end, start + 0.5);
  });
  if (exact >= 0) return exact;

  let previous = 0;
  subtitles.forEach((line, index) => {
    if (getLineStartSeconds(line) <= seconds) previous = index;
  });
  return previous;
}

function renderSubtitles() {
  subtitleList.replaceChildren();

  if (!subtitles.length) {
    const empty = document.createElement("article");
    empty.className = "subtitle-line is-active";
    empty.innerHTML = `<div class="timestamp">--:--</div><div class="subtitle-text"><p class="zh-text">粘贴 YouTube 链接后，这里会出现可点击学习的字幕。</p></div>`;
    subtitleList.append(empty);
    updateCaption();
    return;
  }

  subtitles.forEach((line, index) => {
    const row = document.createElement("article");
    row.className = `subtitle-line${index === activeIndex ? " is-active" : ""}`;
    row.dataset.index = index;

    const timestamp = document.createElement("div");
    timestamp.className = "timestamp";
    timestamp.textContent = line.time;

    const textWrap = document.createElement("div");
    textWrap.className = "subtitle-text";

    if (captionMode === "both" || captionMode === "en") {
      const en = document.createElement("p");
      en.className = "en-text";
      en.textContent = line.en;
      textWrap.append(en);
    }

    if (captionMode === "both" || captionMode === "zh") {
      const zh = document.createElement("p");
      zh.className = "zh-text";
      zh.textContent = line.zh;
      textWrap.append(zh);
    }

    if (captionMode === "none") {
      const hidden = document.createElement("p");
      hidden.className = "zh-text";
      hidden.textContent = "字幕已隐藏";
      textWrap.append(hidden);
    }

    row.append(timestamp, textWrap);
    row.addEventListener("click", () => {
      const selectedText = window.getSelection()?.toString().trim();
      if (selectedText) return;
      setActiveLine(index, { seek: true, play: true, scroll: false });
    });
    subtitleList.append(row);
  });

  updateCaption();
}

function updateCaption() {
  if (!subtitles.length) {
    currentCaption.textContent = "导入视频后，这里会显示当前句字幕。";
    updatePlaybackProgress();
    return;
  }
  const text = visibleText(subtitles[activeIndex]);
  currentCaption.textContent = text || "字幕已隐藏";
  updatePlaybackProgress();
}

function setActiveLine(index, options = {}) {
  activeIndex = Math.max(0, Math.min(index, subtitles.length - 1));
  renderSubtitles();
  if (options.seek) {
    seekToActiveLine({ play: Boolean(options.play) });
  }
  if (options.scroll) {
    scrollActiveSubtitleIntoView();
  }
}

function scrollActiveSubtitleIntoView() {
  const activeRow = subtitleList.querySelector(".subtitle-line.is-active");
  activeRow?.scrollIntoView({ block: "nearest" });
}

function seekToActiveLine({ play = false } = {}) {
  if (!subtitles.length || !youtubePlayerReady || !youtubePlayer?.seekTo) return;
  youtubePlayer.seekTo(getLineStartSeconds(subtitles[activeIndex]), true);
  if (play && youtubePlayer.playVideo) {
    youtubePlayer.playVideo();
  }
  updatePlaybackProgress();
}

function advancePlayback() {
  if (!subtitles.length || activeIndex >= subtitles.length - 1) {
    setPlayState(false);
    return;
  }
  setActiveLine(activeIndex + 1, { seek: true, play: isPlaying });
}

function showSaveToast(message = "已加入表达库") {
  if (!saveToast || !saveToastText) return;
  window.clearTimeout(saveToastTimer);
  window.clearTimeout(saveToastHideTimer);

  saveToastText.textContent = message;
  saveToast.hidden = false;
  window.requestAnimationFrame(() => {
    saveToast.classList.add("is-visible");
  });

  saveToastTimer = window.setTimeout(() => {
    saveToast.classList.remove("is-visible");
    saveToastHideTimer = window.setTimeout(() => {
      saveToast.hidden = true;
    }, 180);
  }, 1800);
}

async function saveSelectedExpression() {
  if (!selectedExpression) return;
  if (!currentVideoId) {
    statusText.textContent = "请先导入视频，再保存表达。";
    return;
  }
  const savedText = selectedExpression.text;
  await apiFetch("/expression-cards", {
    method: "POST",
    body: JSON.stringify({
      video_id: currentVideoId,
      source_type: "subtitle_selection",
      expression_text: selectedExpression.text,
      chinese_meaning: selectedExpression.translation || "",
      context: selectedExpression.context,
      timestamp: selectedExpression.timestamp,
    }),
  });
  await loadCards();
  hideSelectionPopover();
  window.getSelection()?.removeAllRanges();
  statusText.textContent = `已保存“${savedText}”到表达库。`;
  showSaveToast("已加入表达库");
}

function hideSelectionPopover() {
  selectionPopover.hidden = true;
  selectionResult.hidden = true;
  selectionResult.textContent = "";
  selectedExpression = null;
}

function clampPopoverPosition(left, top) {
  const popoverWidth = Math.min(320, window.innerWidth - 24);
  const popoverHeight = selectionPopover.offsetHeight || 96;
  return {
    left: Math.min(window.innerWidth - popoverWidth - 12, Math.max(12, left)),
    top: Math.min(window.innerHeight - popoverHeight - 12, Math.max(12, top)),
  };
}

function showSelectionPopover(range, subtitleRow, text) {
  const index = Number(subtitleRow.dataset.index);
  const line = subtitles[index] || subtitles[activeIndex] || {};
  const rect = range.getBoundingClientRect();
  const sourcePoint = lastSelectionPoint || {
    x: rect.left + rect.width / 2,
    y: rect.top,
  };

  selectedExpression = {
    text,
    context: line.en || text,
    timestamp: line.time || "",
    translation: "",
  };
  selectionResult.hidden = true;
  selectionResult.textContent = "";
  selectionPopover.hidden = false;

  const { left, top } = clampPopoverPosition(sourcePoint.x + 10, sourcePoint.y + 12);
  selectionPopover.style.left = `${left}px`;
  selectionPopover.style.top = `${top}px`;
}

function handleSubtitleSelection() {
  const selection = window.getSelection();
  const text = selection?.toString().trim().replace(/\s+/g, " ");
  if (!selection || !text || selection.rangeCount === 0) {
    hideSelectionPopover();
    return;
  }

  const range = selection.getRangeAt(0);
  const parent =
    range.commonAncestorContainer.nodeType === Node.TEXT_NODE
      ? range.commonAncestorContainer.parentElement
      : range.commonAncestorContainer;
  const subtitleRow = parent?.closest?.(".subtitle-line");
  const subtitleText = parent?.closest?.(".subtitle-text");

  if (!subtitleRow || !subtitleText || !subtitleList.contains(subtitleRow)) {
    hideSelectionPopover();
    return;
  }

  showSelectionPopover(range, subtitleRow, text);
}

async function translateSelectedExpression() {
  if (!selectedExpression) return;
  selectionResult.hidden = false;
  selectionResult.textContent = "正在翻译...";

  try {
    const result = await apiFetch("/translate", {
      method: "POST",
      body: JSON.stringify({ text: selectedExpression.text }),
    });
    selectedExpression.translation = result.translation || "";
    selectionResult.textContent = selectedExpression.translation || "没有返回翻译结果。";
  } catch (error) {
    selectionResult.textContent = error.message;
  }
}

function renderCards() {
  cardList.replaceChildren();
  if (!cards.length) {
    const empty = document.createElement("article");
    empty.className = "expression-card";
    empty.innerHTML = "<strong>还没有表达卡片</strong><p>选中字幕里的词、短语或句子，可以保存进表达库。</p>";
    cardList.append(empty);
    cardCount.textContent = "已保存 0 条";
    return;
  }

  cards.forEach((card) => {
    const item = document.createElement("article");
    item.className = "expression-card";

    const title = document.createElement("strong");
    title.textContent = card.expression_text;

    const meaning = document.createElement("p");
    meaning.textContent = card.chinese_meaning || card.context;

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.innerHTML = `<span class="source-badge">${card.timestamp || card.source_type}</span><span>${card.video_title || "当前视频"}</span>`;

    item.append(title, meaning, meta);
    cardList.append(item);
  });
  cardCount.textContent = `已保存 ${cards.length} 条`;
}

function appendMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;

  const label = document.createElement("span");
  label.textContent = role === "ai" ? "AI" : "You";

  const content = document.createElement("p");
  content.textContent = text;

  message.append(label, content);
  chatLog.append(message);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function setListening(nextState) {
  isListening = nextState;
  voiceButton.classList.toggle("is-listening", isListening);
  voiceButton.setAttribute("aria-label", isListening ? "停止语音输入" : "语音输入");
}

async function uploadAudioForTranscription(blob) {
  const formData = new FormData();
  formData.append("file", blob, "voice-input.webm");
  const response = await fetch(`${apiBase}/audio/transcriptions`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `语音转文字失败：${response.status}`);
  }
  return response.json();
}

async function startVoiceInput() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    chatText.value = "I learned that meaningful input helps me think in English.";
    statusText.textContent = "当前浏览器不支持录音，已填入一条测试文本。";
    chatText.focus();
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    });

    mediaRecorder.addEventListener("stop", async () => {
      setListening(false);
      stream.getTracks().forEach((track) => track.stop());
      statusText.textContent = "正在转写语音...";

      try {
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        const result = await uploadAudioForTranscription(blob);
        chatText.value = result.text || "";
        statusText.textContent = chatText.value.trim()
          ? "语音已转成文字，可以发送给 AI。"
          : "没有识别到内容，可以再试一次。";
        chatText.focus();
      } catch (error) {
        chatText.value = "I learned that meaningful input helps me think in English.";
        statusText.textContent = `${error.message}；已填入一条测试文本。`;
        chatText.focus();
      }
    });

    mediaRecorder.start();
    setListening(true);
    statusText.textContent = "正在录音，再点一次红色按钮结束。";
  } catch (error) {
    setListening(false);
    chatText.value = "I learned that meaningful input helps me think in English.";
    statusText.textContent = "无法使用麦克风，已填入一条测试文本。";
    chatText.focus();
  }
}

function stopVoiceInput() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    return;
  }
  setListening(false);
}

function setTransportIcon(nextIsPlaying) {
  const icon = nextIsPlaying ? "Ⅱ" : "▶";
  playIcon.textContent = icon;
  playButtonSmall.textContent = icon;
  videoThumbnail.classList.toggle("is-playing", nextIsPlaying);
}

function loadYoutubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (youtubeApiPromise) return youtubeApiPromise;
  youtubeApiPromise = new Promise((resolve, reject) => {
    const previousReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previousReady?.();
      resolve(window.YT);
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.async = true;
    script.onerror = () => reject(new Error("YouTube 播放器加载失败"));
    document.head.append(script);
  });
  return youtubeApiPromise;
}

function startPlayerSync() {
  if (playerSyncTimer) return;
  playerSyncTimer = window.setInterval(syncPlayerState, 500);
}

function stopPlayerSync() {
  if (playerSyncTimer) {
    clearInterval(playerSyncTimer);
    playerSyncTimer = null;
  }
}

function syncPlayerState() {
  if (!youtubePlayerReady || !subtitles.length) {
    updatePlaybackProgress();
    return;
  }
  const currentSeconds = getCurrentPlaybackSeconds();
  const nextIndex = findSubtitleIndexByTime(currentSeconds);
  if (nextIndex !== activeIndex) {
    activeIndex = nextIndex;
    renderSubtitles();
    scrollActiveSubtitleIntoView();
  } else {
    updateCaption();
  }
}

async function setupYoutubePlayer(video) {
  currentYoutubeVideoId = video.youtube_video_id || "";
  youtubePlayerReady = false;
  stopPlayerSync();
  videoThumbnail.classList.toggle("has-player", Boolean(currentYoutubeVideoId));

  if (!currentYoutubeVideoId) {
    setTransportIcon(false);
    return;
  }

  try {
    const YT = await loadYoutubeApi();
    if (!youtubePlayer) {
      youtubePlayer = new YT.Player("youtubePlayer", {
        videoId: currentYoutubeVideoId,
        playerVars: {
          playsinline: 1,
          rel: 0,
          modestbranding: 1,
          controls: 1,
        },
        events: {
          onReady: (event) => {
            youtubePlayerReady = true;
            event.target.setPlaybackRate?.(playbackSpeed);
            event.target.cueVideoById?.(currentYoutubeVideoId);
            updatePlaybackProgress();
          },
          onStateChange: (event) => {
            const state = event.data;
            isPlaying = state === YT.PlayerState.PLAYING;
            setTransportIcon(isPlaying);
            if (isPlaying) {
              startPlayerSync();
            } else if (state === YT.PlayerState.PAUSED || state === YT.PlayerState.ENDED) {
              stopPlayerSync();
              syncPlayerState();
            }
          },
        },
      });
    } else {
      youtubePlayerReady = true;
      youtubePlayer.cueVideoById(currentYoutubeVideoId);
      youtubePlayer.setPlaybackRate?.(playbackSpeed);
      updatePlaybackProgress();
    }
  } catch (error) {
    statusText.textContent = error.message;
  }
}

function setCurrentVideo(video) {
  currentVideoId = video.id;
  subtitles = video.subtitles || [];
  activeIndex = 0;
  setPlayState(false);
  videoTitle.textContent = video.title;
  videoChannel.textContent = video.channel;
  videoDuration.textContent = video.duration;
  statusText.textContent = `已载入 ${subtitles.length} 条字幕，点击任意字幕即可跳转播放。`;
  chatLog.replaceChildren();
  appendMessage("ai", "你可以先概述视频主要内容，说说你学到了什么，AI 会围绕你的回答继续和你交流。");
  renderSubtitles();
  setupYoutubePlayer(video);
}

function renderHistory(videos) {
  historyList.replaceChildren();
  if (!videos.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "还没有导入过视频。";
    historyList.append(empty);
    return;
  }
  videos.forEach((video) => {
    const button = document.createElement("button");
    button.className = `history-item${video.id === currentVideoId ? " is-current" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <span class="history-thumb ${video.thumbnail_tone || ""}"></span>
      <span>
        <strong>${video.title}</strong>
        <small>${video.channel} · 已保存 ${video.expression_count || 0} 条表达 · 学到 ${video.last_position || "00:00"}</small>
      </span>
      <em>${video.updated_at ? "最近" : "今天"}</em>
    `;
    button.addEventListener("click", async () => {
      const loaded = await apiFetch(`/videos/${video.id}`);
      setCurrentVideo(loaded);
      closeGlobalPanel();
    });
    historyList.append(button);
  });
}

async function loadCards() {
  cards = await apiFetch("/expression-cards");
  renderCards();
}

async function loadHistory() {
  const videos = await apiFetch("/videos");
  renderHistory(videos);
}

async function loadInitialData() {
  if (location.protocol === "file:") {
    setCurrentVideo(fileModeVideo);
    cards = [];
    renderCards();
    renderHistory([]);
    statusText.textContent = "当前是静态预览；完整功能请打开 http://127.0.0.1:8011/";
    return;
  }

  const config = await apiFetch("/config");
  videoUrlInput.value = "";
  statusText.textContent = config.builder_enabled
    ? "已连接 builder API。粘贴一个有英文字幕的 YouTube 链接开始。"
    : "当前使用 mock fallback：未检测到 builder token。";
  await Promise.all([loadCards(), loadHistory()]);
  renderSubtitles();
}

document.querySelector("#importForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    statusText.textContent = "正在读取 YouTube 视频和字幕，这可能需要几十秒...";
    const video = await apiFetch("/videos/import", {
      method: "POST",
      body: JSON.stringify({ url: videoUrlInput.value }),
    });
    setCurrentVideo(video);
    await Promise.all([loadCards(), loadHistory()]);
  } catch (error) {
    statusText.textContent = error.message;
  }
});

demoVideoButton.addEventListener("click", () => {
  videoUrlInput.value = demoYoutubeUrl;
  statusText.textContent = "已填入示例视频，点击导入即可开始体验。";
  videoUrlInput.focus();
});

document.querySelectorAll(".chip").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    captionMode = button.dataset.caption;
    renderSubtitles();
  });
});

document.querySelector("#prevLine").addEventListener("click", () =>
  setActiveLine(activeIndex - 1, { seek: true, play: isPlaying }),
);
document.querySelector("#nextLine").addEventListener("click", () =>
  setActiveLine(activeIndex + 1, { seek: true, play: isPlaying }),
);

document.querySelector("#hideCaptionToggle").addEventListener("change", (event) => {
  currentCaption.classList.toggle("is-hidden", event.target.checked);
});

speedRange.addEventListener("input", (event) => {
  const speed = `${Number(event.target.value).toFixed(2).replace(/\.00$/, "").replace(/0$/, "")}x`;
  playbackSpeed = Number(event.target.value);
  speedLabel.textContent = speed;
  statusText.textContent = `播放速度已切换为 ${speed}。`;
  if (youtubePlayerReady && youtubePlayer?.setPlaybackRate) {
    youtubePlayer.setPlaybackRate(playbackSpeed);
  }
  if (isPlaying) {
    setPlayState(true);
  }
});

function setPlayState(nextState) {
  isPlaying = nextState;
  setTransportIcon(isPlaying);

  if (playbackTimer) {
    clearInterval(playbackTimer);
    playbackTimer = null;
  }

  if (youtubePlayerReady && youtubePlayer) {
    youtubePlayer.setPlaybackRate?.(playbackSpeed);
    if (isPlaying) {
      if (subtitles.length && getCurrentPlaybackSeconds() >= getLineEndSeconds(subtitles[subtitles.length - 1])) {
        setActiveLine(0, { seek: true, play: false });
      }
      youtubePlayer.playVideo?.();
      startPlayerSync();
      statusText.textContent = "正在播放 YouTube 视频，字幕会跟随同步。";
    } else {
      youtubePlayer.pauseVideo?.();
      stopPlayerSync();
      updatePlaybackProgress();
    }
    return;
  }

  if (isPlaying) {
    if (subtitles.length && activeIndex >= subtitles.length - 1) {
      setActiveLine(0);
    }
    playbackTimer = window.setInterval(advancePlayback, 2600 / playbackSpeed);
    statusText.textContent = "正在播放，字幕会自动推进。";
  }
}

function togglePlayback() {
  if (!currentVideoId) {
    statusText.textContent = "请先导入一个 YouTube 视频。";
    return;
  }
  setPlayState(!isPlaying);
}

playButton.addEventListener("click", togglePlayback);
playButtonSmall.addEventListener("click", togglePlayback);

document.querySelector("#chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!currentVideoId) {
    appendMessage("ai", "请先导入一个 YouTube 视频，我才能围绕它和你讨论。");
    return;
  }
  const text = chatText.value.trim();
  if (!text) return;
  appendMessage("user", text);
  chatText.value = "";
  apiFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ video_id: currentVideoId, message: text }),
  })
    .then((message) => appendMessage("ai", message.text))
    .catch((error) => appendMessage("ai", error.message));
});

voiceButton.addEventListener("click", () => {
  if (isListening) {
    stopVoiceInput();
    return;
  }
  startVoiceInput();
});

subtitleList.addEventListener("pointerdown", (event) => {
  lastSelectionPoint = { x: event.clientX, y: event.clientY };
});

subtitleList.addEventListener("pointermove", (event) => {
  if (event.buttons) {
    lastSelectionPoint = { x: event.clientX, y: event.clientY };
  }
});

subtitleList.addEventListener("pointerup", (event) => {
  lastSelectionPoint = { x: event.clientX, y: event.clientY };
  window.setTimeout(handleSubtitleSelection, 0);
});

subtitleList.addEventListener("keyup", handleSubtitleSelection);

document.addEventListener("selectionchange", () => {
  if (selectionChangeTimer) {
    clearTimeout(selectionChangeTimer);
  }
  selectionChangeTimer = window.setTimeout(handleSubtitleSelection, 80);
});

subtitleList.addEventListener("scroll", hideSelectionPopover);

selectionPopover.addEventListener("mousedown", (event) => {
  event.preventDefault();
});

selectionTranslateButton.addEventListener("click", () => {
  translateSelectedExpression().catch((error) => {
    selectionResult.hidden = false;
    selectionResult.textContent = error.message;
  });
});

selectionSaveButton.addEventListener("click", () => {
  saveSelectedExpression().catch((error) => {
    statusText.textContent = error.message;
    hideSelectionPopover();
  });
});

document.addEventListener("mousedown", (event) => {
  if (
    !selectionPopover.hidden &&
    !selectionPopover.contains(event.target) &&
    !subtitleList.contains(event.target)
  ) {
    hideSelectionPopover();
  }
});

function closeGlobalPanel() {
  globalPanel.hidden = true;
  document.querySelector(".studio-shell").classList.remove("is-global-view");
  document.querySelectorAll(".global-tab").forEach((item) => item.classList.remove("is-active"));
  document.querySelectorAll(".global-view").forEach((item) => item.classList.remove("is-active"));
}

function openGlobalView(viewName) {
  globalPanel.hidden = false;
  document.querySelector(".studio-shell").classList.add("is-global-view");
  document.querySelectorAll(".global-tab").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === viewName);
  });
  document.querySelectorAll(".global-view").forEach((item) => item.classList.remove("is-active"));
  document.querySelector(`#${viewName}View`).classList.add("is-active");
}

document.querySelectorAll(".global-tab").forEach((button) => {
  button.addEventListener("click", () => {
    const isAlreadyOpen = button.classList.contains("is-active") && !globalPanel.hidden;
    if (isAlreadyOpen) {
      closeGlobalPanel();
      return;
    }
    openGlobalView(button.dataset.view);
  });
});

document.querySelectorAll(".back-home-button").forEach((button) => {
  button.addEventListener("click", closeGlobalPanel);
});

document.querySelectorAll(".console-tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".console-tab").forEach((item) => item.classList.remove("is-active"));
    document.querySelectorAll(".console-panel").forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    document.querySelector(`#${button.dataset.panel}Panel`).classList.add("is-active");
  });
});

loadInitialData().catch((error) => {
  statusText.textContent = error.message;
  renderSubtitles();
  renderCards();
});
