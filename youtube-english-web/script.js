let subtitles = [];
let cards = [];
let currentVideoId = null;
let currentTranslationStatus = "idle";
let currentTranslationError = "";
let activeIndex = 0;
let captionMode = "both";
let showEnglish = true;
let showChinese = true;
let isPlaying = false;

const apiBase = "/api";
const subtitleList = document.querySelector("#subtitleList");
const selectionPopover = document.querySelector("#selectionPopover");
const selectionTranslateButton = document.querySelector("#selectionTranslateButton");
const selectionSaveButton = document.querySelector("#selectionSaveButton");
const selectionResult = document.querySelector("#selectionResult");
const saveToast = document.querySelector("#saveToast");
const saveToastIcon = document.querySelector(".save-toast-icon");
const saveToastText = document.querySelector("#saveToastText");
const toggleLibraryChineseButton = document.querySelector("#toggleLibraryChinese");
const currentCaption = document.querySelector("#currentCaption");
const statusText = document.querySelector("#statusText");
const translationStatus = document.querySelector("#translationStatus");
const cardList = document.querySelector("#cardList");
const cardCount = document.querySelector("#cardCount");
const chatLog = document.querySelector("#chatLog");
const historyList = document.querySelector("#historyList");
const videoTitle = document.querySelector("#videoTitle");
const videoChannel = document.querySelector("#videoChannel");
const videoDuration = document.querySelector("#videoDuration");
const videoThumbnail = document.querySelector(".video-thumbnail");
const youtubePlayerElement = document.querySelector("#youtubePlayer");
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
const languageCycleButton = document.querySelector("#languageCycleButton");
const hideCaptionButton = document.querySelector('[data-caption="none"]');
const coachPromptTitle = document.querySelector("#coachPromptTitle");
const coachPromptText = document.querySelector("#coachPromptText");
const coachModeButtons = document.querySelectorAll(".coach-mode-card");
const correctionOptionButtons = document.querySelectorAll(".correction-option");
const coachCorrectionHint = document.querySelector("#coachCorrectionHint");
const vocabList = document.querySelector("#vocabList");
const vocabResultCount = document.querySelector("#vocabResultCount");
const vocabFilterButtons = document.querySelectorAll(".vocab-filter");
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
let translationPollTimer = null;
let youtubePlayer = null;
let youtubePlayerReady = false;
let youtubeApiPromise = null;
let currentYoutubeVideoId = "";
let currentVocabThreshold = 5000;
let vocabularyRequestId = 0;
let hideLibraryChinese = false;
let currentCoachMode = "summary";
let shouldCorrectExpression = true;
const publicAppUrl = "https://tubeloop.ai-builders.space/";

const coachModes = {
  summary: {
    title: "复述视频内容",
    description: "用你自己的话概述这个视频讲了什么。你可以先说 2-3 句话。",
    opener: "先试着用 2-3 句话复述这个视频。你不用说得完美，我会先帮你把表达改自然，再继续追问视频内容。",
    placeholder: "Try: This video is mainly about...",
    starter: "This video is mainly about...",
  },
  experience: {
    title: "我的相关经历",
    description: "分享一个和视频主题相关的个人经历，哪怕很短也可以。",
    opener: "你可以讲一个和视频主题有关的经历。我会先帮你调整英文表达，然后继续问你经历里的细节。",
    placeholder: "Try: This reminds me of a time when...",
    starter: "This reminds me of a time when...",
  },
  expression: {
    title: "学到的表达",
    description: "说说你在这个视频里学到的词、短语或句子，并试着造句。",
    opener: "选一个你从视频里学到的表达，试着用它造一个自己的句子。我会先优化句子，再补充这个表达的自然用法。",
    placeholder: "Try: One useful expression I learned is...",
    starter: "One useful expression I learned is...",
  },
};

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
  if (showEnglish && showChinese) return line.en || line.zh;
  if (showEnglish) return line.en;
  if (showChinese) return line.zh;
  if (captionMode === "none") return "";
  return line.en;
}

function syncCaptionMode() {
  if (showEnglish && showChinese) {
    captionMode = "both";
  } else if (showEnglish) {
    captionMode = "en";
  } else if (showChinese) {
    captionMode = "zh";
  } else {
    captionMode = "none";
  }
  if (languageCycleButton) {
    const labelMap = {
      both: "字幕语言：双语",
      en: "字幕语言：英文",
      zh: "字幕语言：中文",
      none: "字幕语言：已隐藏",
    };
    languageCycleButton.dataset.mode = captionMode;
    languageCycleButton.setAttribute("aria-label", labelMap[captionMode] || labelMap.both);
    languageCycleButton.title = "切换字幕语言";
  }
  hideCaptionButton?.classList.toggle("is-active", captionMode === "none");
}

function hasChineseSubtitles() {
  return subtitles.some((line) => String(line.zh || "").trim());
}

function translatedSubtitleCount() {
  return subtitles.filter((line) => String(line.zh || "").trim()).length;
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
    empty.className = "subtitle-line is-active subtitle-hidden-state";
    empty.innerHTML = `<div class="subtitle-text"><p class="zh-text">粘贴 YouTube 链接后，这里会出现可点击学习的字幕。</p></div>`;
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

    const rail = document.createElement("div");
    rail.className = "subtitle-rail";
    rail.innerHTML = `<span class="subtitle-node" aria-hidden="true"></span>`;

    const textWrap = document.createElement("div");
    textWrap.className = "subtitle-text";

    if (showEnglish) {
      const en = document.createElement("p");
      en.className = "en-text";
      en.textContent = line.en;
      textWrap.append(en);
    }

    if (showChinese && line.zh) {
      const zh = document.createElement("p");
      zh.className = "zh-text";
      zh.textContent = line.zh;
      textWrap.append(zh);
    } else if (showChinese) {
      const zh = document.createElement("p");
      zh.className = "zh-text is-pending";
      zh.textContent =
        currentTranslationStatus === "pending" || currentTranslationStatus === "running"
          ? "翻译中..."
          : "暂无中文字幕";
      textWrap.append(zh);
    }

    if (!showEnglish && !showChinese) {
      textWrap.classList.add("is-hidden-caption");
    }

    row.append(timestamp, rail, textWrap);
    row.addEventListener("click", () => {
      const selectedText = window.getSelection()?.toString().trim();
      if (selectedText) return;
      setActiveLine(index, { seek: true, play: true, scroll: false });
    });
    subtitleList.append(row);
  });

  updateCaption();
}

function formatVocabThreshold(value) {
  return value >= 10000 ? "1万+" : String(value);
}

async function renderVocabularyPanel() {
  if (!vocabList) return;
  const threshold = currentVocabThreshold;
  const thresholdLabel = formatVocabThreshold(threshold);

  vocabFilterButtons.forEach((button) => {
    button.classList.toggle("is-active", Number(button.dataset.vocabThreshold) === threshold);
  });

  vocabList.replaceChildren();
  if (!currentVideoId) {
    vocabResultCount.textContent = "0 个";
    const empty = document.createElement("div");
    empty.className = "vocab-empty";
    empty.textContent = "导入视频后，这里会显示超出所选词汇量的单词。";
    vocabList.append(empty);
    return;
  }

  const requestId = ++vocabularyRequestId;
  vocabResultCount.textContent = "分析中";
  const loading = document.createElement("div");
  loading.className = "vocab-empty";
  loading.textContent = "正在分析当前视频字幕...";
  vocabList.append(loading);

  try {
    const result = await apiFetch(
      `/videos/${currentVideoId}/vocabulary?threshold=${threshold}&limit=30`,
    );
    if (requestId !== vocabularyRequestId) return;
    const items = result.items || [];
    vocabResultCount.textContent = `${result.total ?? items.length} 个`;
    vocabList.replaceChildren();

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "vocab-empty";
      empty.textContent = `当前字幕里暂时没有超过 ${thresholdLabel} 词汇量的单词。`;
      vocabList.append(empty);
      return;
    }

    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "vocab-card";
      const word = document.createElement("strong");
      word.textContent = item.surface || item.lemma;
      const translation = document.createElement("p");
      translation.textContent = item.translation || "暂无翻译";
      card.append(word, translation);
      vocabList.append(card);
    });
  } catch (error) {
    if (requestId !== vocabularyRequestId) return;
    vocabResultCount.textContent = "0 个";
    vocabList.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "vocab-empty";
    empty.textContent = error.message;
    vocabList.append(empty);
  }
}

function setCoachMode(mode, options = {}) {
  const normalizedMode = mode in coachModes ? mode : "summary";
  const config = coachModes[normalizedMode];
  currentCoachMode = normalizedMode;

  coachModeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.coachMode === currentCoachMode);
  });

  if (coachPromptTitle) coachPromptTitle.textContent = config.title;
  if (coachPromptText) coachPromptText.textContent = config.description;
  if (chatText && !isListening) {
    chatText.placeholder = config.placeholder;
    if (options.setStarter) {
      chatText.value = config.starter;
    }
  }
  if (options.resetChat && chatLog) {
    chatLog.replaceChildren();
    appendMessage("ai", config.opener);
  }
}

function setCoachCorrection(enabled) {
  shouldCorrectExpression = Boolean(enabled);
  correctionOptionButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.correction === String(shouldCorrectExpression));
  });
  if (coachCorrectionHint) {
    coachCorrectionHint.textContent = shouldCorrectExpression
      ? "AI 先给一句更自然的说法"
      : "AI 只回应内容和继续追问";
  }
}

function markActiveSubtitle() {
  subtitleList.querySelectorAll(".subtitle-line").forEach((row) => {
    row.classList.toggle("is-active", Number(row.dataset.index) === activeIndex);
  });
}

function updateCaption() {
  if (!subtitles.length) {
    currentCaption.textContent = "导入视频后，这里会显示当前句字幕。";
    updatePlaybackProgress();
    return;
  }
  const text = visibleText(subtitles[activeIndex]);
  if (text) {
    currentCaption.textContent = text;
  } else if (showChinese) {
    currentCaption.textContent =
      currentTranslationStatus === "pending" || currentTranslationStatus === "running"
        ? "中文字幕正在生成"
        : "暂无中文字幕";
  } else {
    currentCaption.textContent = "字幕已隐藏";
  }
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
  if (!subtitles.length) return;
  const startSeconds = getLineStartSeconds(subtitles[activeIndex]);
  if (youtubePlayerReady && youtubePlayer?.seekTo) {
    youtubePlayer.seekTo(startSeconds, true);
    if (play && youtubePlayer.playVideo) {
      youtubePlayer.playVideo();
    }
  } else if (currentYoutubeVideoId) {
    renderYoutubeIframe(currentYoutubeVideoId, { startSeconds, autoplay: play });
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

function showSaveToast(message = "已加入表达库", options = {}) {
  if (!saveToast || !saveToastText) return;
  window.clearTimeout(saveToastTimer);
  window.clearTimeout(saveToastHideTimer);

  const variant = options.variant || "success";
  if (saveToastIcon) {
    saveToastIcon.textContent = variant === "loading" ? "…" : variant === "error" ? "!" : "✓";
  }
  saveToast.dataset.variant = variant;
  saveToastText.textContent = message;
  saveToast.hidden = false;
  window.requestAnimationFrame(() => {
    saveToast.classList.add("is-visible");
  });

  if (options.sticky) return;

  saveToastTimer = window.setTimeout(() => {
    saveToast.classList.remove("is-visible");
    saveToastHideTimer = window.setTimeout(() => {
      saveToast.hidden = true;
    }, 180);
  }, 1800);
}

function hideSaveToast() {
  if (!saveToast) return;
  window.clearTimeout(saveToastTimer);
  window.clearTimeout(saveToastHideTimer);
  saveToast.classList.remove("is-visible");
  saveToastHideTimer = window.setTimeout(() => {
    saveToast.hidden = true;
  }, 180);
}

function stopTranslationPolling() {
  if (translationPollTimer) {
    window.clearInterval(translationPollTimer);
    translationPollTimer = null;
  }
}

function updateTranslationStatus(video = {}) {
  currentTranslationStatus = video.chinese_translation_status || currentTranslationStatus || "idle";
  currentTranslationError = video.chinese_translation_error || "";
  if (!translationStatus) return;

  const total = Number(video.chinese_translation_total || subtitles.length || 0);
  const translated = Number(video.chinese_translation_count || translatedSubtitleCount());
  const hasChinese = translated > 0 || hasChineseSubtitles();

  if (!currentVideoId || !total || (hasChinese && currentTranslationStatus === "complete")) {
    translationStatus.hidden = true;
    translationStatus.textContent = "";
    translationStatus.dataset.state = "";
    return;
  }

  if (currentTranslationStatus === "pending" || currentTranslationStatus === "running") {
    translationStatus.hidden = false;
    translationStatus.dataset.state = currentTranslationStatus;
    translationStatus.textContent = `正在生成中文字幕，英文字幕和视频可以先使用。已完成 ${translated}/${total} 条。`;
    return;
  }

  if (currentTranslationStatus === "partial") {
    translationStatus.hidden = false;
    translationStatus.dataset.state = "partial";
    translationStatus.textContent = `已生成部分中文字幕：${translated}/${total} 条。`;
    return;
  }

  if (currentTranslationStatus === "failed") {
    translationStatus.hidden = false;
    translationStatus.dataset.state = "failed";
    translationStatus.textContent = currentTranslationError || "中文字幕生成失败，请稍后重新导入或重试。";
    return;
  }

  if (!hasChinese && (captionMode === "zh" || captionMode === "both")) {
    translationStatus.hidden = false;
    translationStatus.dataset.state = "idle";
    translationStatus.textContent = "这个视频暂无中文字幕。点击中文或双语后，会用 AI Builder 生成并保存。";
    return;
  }

  translationStatus.hidden = true;
  translationStatus.textContent = "";
  translationStatus.dataset.state = "";
}

async function refreshTranslationStatus() {
  if (!currentVideoId) return;
  try {
    const result = await apiFetch(`/videos/${currentVideoId}/translation-status`);
    currentTranslationStatus = result.status || "idle";
    currentTranslationError = result.error || "";
    updateTranslationStatus({
      chinese_translation_status: currentTranslationStatus,
      chinese_translation_error: currentTranslationError,
      chinese_translation_total: result.total,
      chinese_translation_count: result.translated,
    });

    const localTranslated = translatedSubtitleCount();
    if (
      (currentTranslationStatus === "pending" || currentTranslationStatus === "running") &&
      result.translated > localTranslated
    ) {
      const loaded = await apiFetch(`/videos/${currentVideoId}`);
      subtitles = loaded.subtitles || subtitles;
      currentTranslationStatus = loaded.chinese_translation_status || currentTranslationStatus;
      currentTranslationError = loaded.chinese_translation_error || "";
      renderSubtitles();
      updateTranslationStatus(loaded);
    }

    if (currentTranslationStatus === "complete" || currentTranslationStatus === "partial") {
      const loaded = await apiFetch(`/videos/${currentVideoId}`);
      subtitles = loaded.subtitles || subtitles;
      currentTranslationStatus = loaded.chinese_translation_status || currentTranslationStatus;
      currentTranslationError = loaded.chinese_translation_error || "";
      renderSubtitles();
      updateTranslationStatus(loaded);
      stopTranslationPolling();
      showSaveToast(
        currentTranslationStatus === "complete" ? "中文字幕已生成" : "部分中文字幕已生成",
        { variant: "success" },
      );
    } else if (currentTranslationStatus === "failed") {
      stopTranslationPolling();
    }
  } catch (error) {
    console.warn(error.message);
  }
}

function startTranslationPolling(video = {}) {
  stopTranslationPolling();
  updateTranslationStatus(video);
  if (!currentVideoId) return;
  const status = video.chinese_translation_status || currentTranslationStatus;
  if (status !== "pending" && status !== "running") return;
  translationPollTimer = window.setInterval(refreshTranslationStatus, 4000);
  window.setTimeout(refreshTranslationStatus, 1200);
}

async function ensureChineseSubtitles() {
  if (!currentVideoId) {
    updateTranslationStatus();
    return;
  }

  const hasAllChinese = subtitles.length > 0 && translatedSubtitleCount() >= subtitles.length;
  if (hasAllChinese && currentTranslationStatus === "complete") {
    updateTranslationStatus();
    return;
  }

  if (currentTranslationStatus === "pending" || currentTranslationStatus === "running") {
    startTranslationPolling({
      chinese_translation_status: currentTranslationStatus,
      chinese_translation_error: currentTranslationError,
      chinese_translation_total: subtitles.length,
      chinese_translation_count: translatedSubtitleCount(),
    });
    return;
  }

  try {
    showSaveToast("正在生成中文字幕", { sticky: true, variant: "loading" });
    const result = await apiFetch(`/videos/${currentVideoId}/translate-subtitles`, {
      method: "POST",
      body: JSON.stringify({
        focus_index: activeIndex,
        window_size: 40,
      }),
    });
    currentTranslationStatus = result.status || "pending";
    currentTranslationError = result.error || "";
    renderSubtitles();
    startTranslationPolling({
      chinese_translation_status: currentTranslationStatus,
      chinese_translation_error: currentTranslationError,
      chinese_translation_total: result.total,
      chinese_translation_count: result.translated,
    });
  } catch (error) {
    currentTranslationStatus = "failed";
    currentTranslationError = error.message;
    updateTranslationStatus({
      chinese_translation_status: currentTranslationStatus,
      chinese_translation_error: currentTranslationError,
      chinese_translation_total: subtitles.length,
      chinese_translation_count: translatedSubtitleCount(),
    });
    showSaveToast("中文字幕生成失败", { variant: "error" });
  }
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
    if (toggleLibraryChineseButton) {
      toggleLibraryChineseButton.textContent = hideLibraryChinese ? "显示中文" : "隐藏中文";
      toggleLibraryChineseButton.classList.toggle("is-active", hideLibraryChinese);
    }
    return;
  }

  cards.forEach((card) => {
    const item = document.createElement("article");
    item.className = "expression-card";

    const title = document.createElement("strong");
    title.textContent = card.expression_text;

    const meaning = document.createElement("p");
    meaning.textContent = card.chinese_meaning || card.context;
    meaning.className = "card-meaning";
    meaning.hidden = hideLibraryChinese;

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.innerHTML = `<span class="source-badge">${card.timestamp || card.source_type}</span><span>${card.video_title || "当前视频"}</span>`;

    item.append(title, meaning, meta);
    cardList.append(item);
  });
  cardCount.textContent = `已保存 ${cards.length} 条`;
  if (toggleLibraryChineseButton) {
    toggleLibraryChineseButton.textContent = hideLibraryChinese ? "显示中文" : "隐藏中文";
    toggleLibraryChineseButton.classList.toggle("is-active", hideLibraryChinese);
  }
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

function supportedAudioMimeType() {
  if (!window.MediaRecorder?.isTypeSupported) return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) || "";
}

function audioFileName(mimeType) {
  if (mimeType.includes("mp4")) return "voice-input.m4a";
  if (mimeType.includes("ogg")) return "voice-input.ogg";
  return "voice-input.webm";
}

async function uploadAudioForTranscription(blob, filename) {
  const formData = new FormData();
  formData.append("file", blob, filename);
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
    chatText.placeholder = "当前浏览器不支持录音，请直接输入文字。";
    statusText.textContent = "当前浏览器不支持录音，请直接输入文字。";
    chatText.focus();
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = supportedAudioMimeType();
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

    mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    });

    mediaRecorder.addEventListener("stop", async () => {
      setListening(false);
      stream.getTracks().forEach((track) => track.stop());
      chatText.placeholder = "正在转写语音...";
      statusText.textContent = "正在转写语音...";

      try {
        if (!audioChunks.length) {
          throw new Error("没有录到声音，请确认麦克风权限已开启");
        }
        const actualMimeType = mediaRecorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(audioChunks, { type: actualMimeType });
        const result = await uploadAudioForTranscription(blob, audioFileName(actualMimeType));
        chatText.value = result.text || "";
        statusText.textContent = chatText.value.trim()
          ? "语音已转成文字，可以发送给 AI。"
          : "没有识别到内容，可以再试一次。";
        chatText.placeholder = coachModes[currentCoachMode]?.placeholder || "输入你想和 AI 讨论的内容";
        chatText.focus();
      } catch (error) {
        chatText.placeholder = "语音转文字失败，请重试或直接输入文字。";
        statusText.textContent = `语音转文字失败：${error.message}`;
        chatText.focus();
      }
    });

    mediaRecorder.start();
    setListening(true);
    chatText.value = "";
    chatText.placeholder = "正在录音...再点一次红色按钮结束";
    statusText.textContent = "正在录音，再点一次红色按钮结束。";
  } catch (error) {
    setListening(false);
    chatText.placeholder = "无法使用麦克风，请允许浏览器麦克风权限。";
    statusText.textContent = `无法使用麦克风：${error.message}`;
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

function renderYoutubeIframe(videoId, options = {}) {
  if (!youtubePlayerElement || !videoId) return;
  const params = new URLSearchParams({
    enablejsapi: "1",
    playsinline: "1",
    rel: "0",
    modestbranding: "1",
    controls: "0",
      cc_load_policy: "0",
      disablekb: "1",
      fs: "0",
      iv_load_policy: "3",
      showinfo: "0",
      origin: window.location.origin,
    });
  if (options.autoplay) params.set("autoplay", "1");
  if (Number(options.startSeconds) > 0) {
    params.set("start", String(Math.floor(Number(options.startSeconds))));
  }
  youtubePlayerElement.innerHTML = `
    <iframe
      id="youtubePlayerFrame"
      title="YouTube video player"
      src="https://www.youtube.com/embed/${encodeURIComponent(videoId)}?${params.toString()}"
      allow="autoplay; encrypted-media; picture-in-picture"
    ></iframe>
  `;
}

function loadYoutubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (youtubeApiPromise) return youtubeApiPromise;
  youtubeApiPromise = new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      reject(new Error("YouTube 精听控制加载超时，播放器仍可直接播放。"));
    }, 6000);
    const previousReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      window.clearTimeout(timeout);
      previousReady?.();
      resolve(window.YT);
    };
    const existingScript = Array.from(document.scripts).find((script) =>
      script.src.includes("youtube.com/iframe_api"),
    );
    if (!existingScript) {
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      script.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error("YouTube 精听控制加载失败，播放器仍可直接播放。"));
      };
      document.head.append(script);
    }
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
    markActiveSubtitle();
    updateCaption();
  } else {
    updateCaption();
  }
}

async function setupYoutubePlayer(video) {
  currentYoutubeVideoId = video.youtube_video_id || "";
  youtubePlayerReady = false;
  stopPlayerSync();
  youtubePlayer?.destroy?.();
  youtubePlayer = null;
  videoThumbnail.classList.toggle("has-player", Boolean(currentYoutubeVideoId));

  if (!currentYoutubeVideoId) {
    youtubePlayerElement.replaceChildren();
    setTransportIcon(false);
    return;
  }

  renderYoutubeIframe(currentYoutubeVideoId);

  try {
    const YT = await loadYoutubeApi();
    youtubePlayer = new YT.Player("youtubePlayerFrame", {
      events: {
        onReady: (event) => {
          youtubePlayerReady = true;
          event.target.setPlaybackRate?.(playbackSpeed);
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
  } catch (error) {
    console.warn(error.message);
  }
}

function setCurrentVideo(video) {
  currentVideoId = video.id;
  subtitles = video.subtitles || [];
  currentTranslationStatus = video.chinese_translation_status || "idle";
  currentTranslationError = video.chinese_translation_error || "";
  activeIndex = 0;
  setPlayState(false);
  videoTitle.textContent = video.title;
  videoChannel.textContent = video.channel;
  videoDuration.textContent = video.duration;
  statusText.textContent = `已载入 ${subtitles.length} 条字幕，点击任意字幕即可跳转播放。`;
  setCoachMode(currentCoachMode, { resetChat: true });
  renderSubtitles();
  renderVocabularyPanel();
  startTranslationPolling(video);
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
    currentVideoId = null;
    subtitles = [];
    stopTranslationPolling();
    activeIndex = 0;
    videoTitle.textContent = "请打开线上版 Tubeloop";
    videoChannel.textContent = publicAppUrl;
    videoDuration.textContent = "在线";
    currentCaption.textContent = "当前是静态 HTML 文件，不能解析 YouTube，也不能读取字幕。";
    cards = [];
    renderCards();
    renderHistory([]);
    renderSubtitles();
    renderVocabularyPanel();
    updateTranslationStatus();
    statusText.textContent = "当前打开的是静态文件。请使用线上地址：https://tubeloop.ai-builders.space/";
    return;
  }

  const config = await apiFetch("/config");
  videoUrlInput.value = "";
  statusText.textContent = config.builder_enabled
    ? "已连接 builder API。粘贴一个有英文字幕的 YouTube 链接开始。"
    : "当前使用 mock fallback：未检测到 builder token。";
  await Promise.all([loadCards(), loadHistory()]);
  renderSubtitles();
  renderVocabularyPanel();
}

document.querySelector("#importForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (location.protocol === "file:") {
    statusText.textContent = "正在打开线上版 Tubeloop...";
    window.location.href = publicAppUrl;
    return;
  }
  try {
    statusText.textContent = "正在读取 YouTube 视频和字幕，这可能需要几十秒...";
    showSaveToast("视频正在加载中", { sticky: true, variant: "loading" });
    const video = await apiFetch("/videos/import", {
      method: "POST",
      body: JSON.stringify({ url: videoUrlInput.value }),
    });
    setCurrentVideo(video);
    await Promise.all([loadCards(), loadHistory()]);
    showSaveToast("载入成功", { variant: "success" });
  } catch (error) {
    statusText.textContent = error.message;
    showSaveToast("载入失败", { variant: "error" });
  }
});

languageCycleButton?.addEventListener("click", async () => {
  const nextMode = captionMode === "both" ? "en" : captionMode === "en" ? "zh" : "both";
  showEnglish = nextMode === "en" || nextMode === "both";
  showChinese = nextMode === "zh" || nextMode === "both";
  syncCaptionMode();
  renderSubtitles();
  updateTranslationStatus();
  if (showChinese) {
    await ensureChineseSubtitles();
  }
});

hideCaptionButton?.addEventListener("click", () => {
  showEnglish = false;
  showChinese = false;
  syncCaptionMode();
  renderSubtitles();
  updateTranslationStatus();
});

document.querySelector("#prevLine").addEventListener("click", () =>
  setActiveLine(activeIndex - 1, { seek: true, play: isPlaying }),
);
document.querySelector("#nextLine").addEventListener("click", () =>
  setActiveLine(activeIndex + 1, { seek: true, play: isPlaying }),
);

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

  if (currentYoutubeVideoId) {
    renderYoutubeIframe(currentYoutubeVideoId, {
      startSeconds: subtitles.length ? getLineStartSeconds(subtitles[activeIndex]) : 0,
      autoplay: isPlaying,
    });
    statusText.textContent = isPlaying
      ? "正在使用 YouTube 原生播放器播放。"
      : "已暂停。";
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
    body: JSON.stringify({
      video_id: currentVideoId,
      message: text,
      correct_expression: shouldCorrectExpression,
    }),
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
    if (button.dataset.panel === "vocabulary") {
      renderVocabularyPanel();
    }
  });
});

vocabFilterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    currentVocabThreshold = Number(button.dataset.vocabThreshold);
    renderVocabularyPanel();
  });
});

coachModeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setCoachMode(button.dataset.coachMode, { resetChat: true, setStarter: true });
    chatText?.focus();
  });
});

correctionOptionButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setCoachCorrection(button.dataset.correction === "true");
    chatText?.focus();
  });
});

toggleLibraryChineseButton?.addEventListener("click", () => {
  hideLibraryChinese = !hideLibraryChinese;
  renderCards();
});

setCoachCorrection(shouldCorrectExpression);
setCoachMode(currentCoachMode, { resetChat: true, setStarter: true });

loadInitialData().catch((error) => {
  statusText.textContent = error.message;
  renderSubtitles();
  renderVocabularyPanel();
  renderCards();
});
