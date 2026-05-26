(() => {
  const numberText = (value) => String(value || 0);

  const buildUrlWithMessage = (target, message) => {
    const url = new URL(target || window.location.href, window.location.origin);
    if (message) {
      url.searchParams.set("message", message);
    } else {
      url.searchParams.delete("message");
    }
    url.searchParams.set("_refresh", String(Date.now()));
    return url;
  };

  const navigateWithMessage = (target, message) => {
    const url = buildUrlWithMessage(target, message);
    const previousHref = window.location.href;
    window.location.assign(url.toString());
    window.setTimeout(() => {
      if (window.location.href === previousHref) {
        window.location.reload();
      }
    }, 1500);
  };

  const cleanRunningLabel = (value, fallback = "处理中") => {
    const label = String(value || fallback).trim().replace(/[.。…]+$/g, "");
    return label || fallback;
  };

  const SUMMARY_JOB_STORAGE_PREFIX = "arxivDaily.summaryJob.";
  const SUMMARY_JOB_TTL_MS = 12 * 60 * 60 * 1000;

  const summaryJobStorageKey = (jobUrl) => {
    const url = new URL(jobUrl, window.location.origin);
    return `${SUMMARY_JOB_STORAGE_PREFIX}${url.pathname}`;
  };

  const readStoredSummaryJob = (jobUrl) => {
    try {
      const raw = window.localStorage.getItem(summaryJobStorageKey(jobUrl));
      if (!raw) {
        return null;
      }
      const stored = JSON.parse(raw);
      if (!stored.jobId || Date.now() - Number(stored.updatedAt || stored.startedAt || 0) > SUMMARY_JOB_TTL_MS) {
        window.localStorage.removeItem(summaryJobStorageKey(jobUrl));
        return null;
      }
      return stored;
    } catch (_error) {
      return null;
    }
  };

  const storeSummaryJob = (jobUrl, jobId, job = {}) => {
    try {
      const previous = readStoredSummaryJob(jobUrl) || {};
      window.localStorage.setItem(summaryJobStorageKey(jobUrl), JSON.stringify({
        jobId,
        jobUrl,
        startedAt: previous.startedAt || Date.now(),
        updatedAt: Date.now(),
        status: job.status || previous.status || "running",
        percent: Number(job.percent || previous.percent || 0),
      }));
    } catch (_error) {
      // Browsers can disable localStorage; progress still works for the current page.
    }
  };

  const clearStoredSummaryJob = (jobUrl, jobId = "") => {
    try {
      const stored = readStoredSummaryJob(jobUrl);
      if (!stored || !jobId || stored.jobId === jobId) {
        window.localStorage.removeItem(summaryJobStorageKey(jobUrl));
      }
    } catch (_error) {
      // Ignore storage cleanup failures.
    }
  };

  const ensureInlineStatus = (form) => {
    let node = form.querySelector("[data-inline-progress-status]");
    if (!node) {
      node = document.createElement("span");
      node.className = "inline-progress-status";
      node.dataset.inlineProgressStatus = "";
      node.setAttribute("aria-live", "polite");
      form.appendChild(node);
    }
    form.classList.add("has-inline-progress");
    return node;
  };

  const renderInlineStatus = (statusNode, message, job = {}) => {
    statusNode.textContent = "";
    const textNode = document.createElement("span");
    textNode.textContent = message;
    statusNode.appendChild(textNode);

    if (job.status === "completed" && job.redirect_url) {
      const link = document.createElement("a");
      link.href = buildUrlWithMessage(job.redirect_url, "").toString();
      link.textContent = "查看结果";
      statusNode.appendChild(link);
    }
  };

  const setButtonProgress = (form, button, job, options = {}) => {
    const percent = Math.max(0, Math.min(100, Number(job.percent || 0)));
    const statusNode = ensureInlineStatus(form);
    const status = job.status || "running";
    const runningLabel = cleanRunningLabel(options.runningLabel || button.dataset.runningLabel, "处理中");
    const completedLabel = options.completedLabel || button.dataset.completedLabel || "已完成";
    const failedLabel = options.failedLabel || "重试";

    if (!button.dataset.defaultLabel) {
      button.dataset.defaultLabel = button.textContent.trim();
    }

    const isTerminalFailure = status === "failed" || status === "not_found";
    const isCompleted = status === "completed";
    button.style.setProperty("--progress", `${percent}%`);
    statusNode.style.setProperty("--progress", `${percent}%`);
    button.dataset.progressStatus = status;
    form.dataset.progressStatus = status;
    const progressScope = form.closest(".action-card, .paper-action-group, .paper-card-ai-actions");
    if (progressScope) {
      progressScope.dataset.progressStatus = status;
    }
    button.classList.toggle("is-progressing", !isTerminalFailure && !isCompleted);
    button.classList.toggle("is-complete", isCompleted);
    button.disabled = !isTerminalFailure && !isCompleted;

    if (isTerminalFailure) {
      button.disabled = false;
      button.textContent = failedLabel;
    } else if (isCompleted) {
      button.textContent = completedLabel;
    } else {
      button.textContent = `${runningLabel} ${Math.round(percent)}%`;
    }

    statusNode.dataset.status = status;
    renderInlineStatus(statusNode, job.message || job.stage_label || "任务正在执行。", job);
    return statusNode;
  };

  const setupFetchProgress = () => {
    const form = document.querySelector("[data-progress-fetch='true']");
    if (!form) {
      return;
    }

    const button = document.getElementById("fetch-button");
    if (!button) {
      return;
    }

    const applyFetchProgress = (job) => {
      const statusNode = setButtonProgress(form, button, job, {
        runningLabel: "抓取中",
        completedLabel: "抓取完成",
        failedLabel: "重新抓取",
      });
      if (job.status !== "failed") {
        const saved = numberText(job.saved);
        const matched = numberText(job.matched);
        const fetched = numberText(job.fetched);
        const network = numberText(job.network_requests);
        const cached = numberText(job.cached_pages);
        renderInlineStatus(statusNode, `${job.stage_label || "正在抓取"} · 读取 ${fetched} · 命中 ${matched} · 新增 ${saved} · API ${network} · 缓存 ${cached}`, job);
      }
    };

    const handleError = (error) => {
      applyFetchProgress({
        status: "failed",
        stage_label: "抓取失败",
        message: error.message || "抓取失败。",
        percent: 100,
      });
    };

    const poll = async (jobId, day) => {
      const response = await fetch(`/fetch-jobs/${jobId}`, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("无法读取抓取进度。");
      }
      const job = await response.json();
      applyFetchProgress(job);

      if (job.status === "completed") {
        window.setTimeout(() => {
          const target = job.redirect_url || `/?day=${encodeURIComponent(day)}`;
          const countText = job.current_count ? `当前共 ${job.current_count} 篇。` : "";
          const sourceText = `官方 API 请求 ${numberText(job.network_requests)} 次，缓存 ${numberText(job.cached_pages)} 页。`;
          navigateWithMessage(target, `抓取完成，论文列表已刷新。${countText}${sourceText}`);
        }, 900);
        return;
      }

      if (job.status === "failed" || job.status === "not_found") {
        applyFetchProgress({
          ...job,
          status: "failed",
          message: job.error || job.message || "抓取失败。",
        });
        return;
      }

      window.setTimeout(() => poll(jobId, day).catch(handleError), 800);
    };

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const day = data.get("day") || "";
      form.dataset.activeFetchJobId = "";
      applyFetchProgress({
        status: "queued",
        stage_label: "等待开始",
        message: "任务已创建，正在连接官方 arXiv API。",
        percent: 2,
      });

      try {
        const response = await fetch("/fetch-jobs", {
          method: "POST",
          body: data,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error("无法启动抓取任务。");
        }
        const payload = await response.json();
        await poll(payload.job_id, day);
      } catch (error) {
        handleError(error);
      }
    });

    if (form.dataset.activeFetchJobId) {
      const day = form.dataset.activeFetchDay || new FormData(form).get("day") || "";
      applyFetchProgress({
        status: "running",
        stage_label: "恢复进度",
        message: "页面已刷新，正在恢复抓取进度。",
        percent: 2,
      });
      poll(form.dataset.activeFetchJobId, day).catch(handleError);
    }
  };

  const setupSummaryProgress = () => {
    const forms = document.querySelectorAll("[data-progress-summary='true']");
    if (!forms.length) {
      return;
    }

    forms.forEach((form) => {
      const button = form.querySelector("button[type='submit']");
      const jobUrl = form.dataset.summaryJobUrl;
      if (!button || !jobUrl) {
        return;
      }

      let activeSummaryJobId = "";

      const applySummaryProgress = (job) => {
        const statusNode = setButtonProgress(form, button, job, {
          runningLabel: form.dataset.runningLabel || "生成中",
          completedLabel: form.dataset.completedLabel || button.dataset.completedLabel || "已完成",
          failedLabel: "重新生成",
        });
        const label = job.label ? `${job.label} · ` : "";
        const model = job.model ? ` · ${job.model}` : "";
        renderInlineStatus(statusNode, `${label}${job.message || job.stage_label || "正在处理。"}${model}`, job);
      };

      const handleError = (error) => {
        applySummaryProgress({
          status: "failed",
          stage_label: "生成失败",
          message: error.message || "生成失败。",
          percent: 100,
        });
      };

      const poll = async (jobId) => {
        const response = await fetch(`/summary-jobs/${jobId}`, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error("无法读取生成进度。");
        }
        const job = await response.json();
        applySummaryProgress(job);

        if (job.status === "completed") {
          clearStoredSummaryJob(jobUrl, jobId);
          activeSummaryJobId = "";
          window.setTimeout(() => {
            navigateWithMessage(window.location.href, "");
          }, 700);
          return;
        }

        if (job.status === "failed" || job.status === "not_found") {
          clearStoredSummaryJob(jobUrl, jobId);
          activeSummaryJobId = "";
          applySummaryProgress({
            ...job,
            status: "failed",
            message: job.status === "not_found" ? "任务状态已失效，可能服务已重启，请重新生成。" : job.error || job.message || "生成失败。",
          });
          return;
        }

        storeSummaryJob(jobUrl, jobId, job);
        window.setTimeout(() => poll(jobId).catch(handleError), 850);
      };

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(form);
        applySummaryProgress({
          status: "queued",
          stage_label: "等待开始",
          message: "任务已创建，正在整理上下文。",
          percent: 3,
        });

        try {
          const response = await fetch(jobUrl, {
            method: "POST",
            body: data,
            headers: { Accept: "application/json" },
          });
          if (!response.ok) {
            throw new Error("无法启动生成任务。");
          }
          const payload = await response.json();
          activeSummaryJobId = payload.job_id;
          storeSummaryJob(jobUrl, activeSummaryJobId, {
            status: "queued",
            stage_label: "等待开始",
            percent: 3,
          });
          await poll(activeSummaryJobId);
        } catch (error) {
          handleError(error);
        }
      });

      const storedJob = readStoredSummaryJob(jobUrl);
      if (storedJob && storedJob.jobId) {
        activeSummaryJobId = storedJob.jobId;
        applySummaryProgress({
          status: storedJob.status || "running",
          stage_label: "恢复进度",
          message: "页面已重新打开，正在恢复智能生成进度。",
          percent: storedJob.percent || 2,
        });
        poll(activeSummaryJobId).catch(handleError);
      }
    });
  };

  const setupPaperFilter = () => {
    const input = document.querySelector("[data-paper-filter]");
    if (!input) {
      return;
    }

    const rows = Array.from(document.querySelectorAll("[data-paper-row]"));
    const countNode = document.querySelector("[data-paper-filter-count]");
    const emptyNode = document.querySelector("[data-paper-filter-empty]");

    const applyFilter = () => {
      const query = input.value.trim().toLowerCase();
      let visibleCount = 0;

      rows.forEach((row) => {
        const haystack = row.dataset.paperSearch || "";
        const matched = !query || haystack.includes(query);
        row.hidden = !matched;
        if (matched) {
          visibleCount += 1;
        }
      });

      if (countNode) {
        countNode.textContent = numberText(visibleCount);
      }
      if (emptyNode) {
        emptyNode.hidden = !query || visibleCount > 0;
      }
    };

    input.addEventListener("input", applyFilter);
    applyFilter();
  };

  const setupSettingsPresets = () => {
    const presetButtons = Array.from(document.querySelectorAll("[data-settings-preset]"));
    if (!presetButtons.length) {
      return;
    }

    const fields = {
      single: document.querySelector("[name='max_tokens_single']"),
      fullText: document.querySelector("[name='max_tokens_full_text']"),
      fullTextChars: document.querySelector("[name='full_text_max_chars']"),
      figureLimit: document.querySelector("[name='full_text_figure_limit']"),
    };

    presetButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (fields.single) fields.single.value = button.dataset.single || fields.single.value;
        if (fields.fullText) fields.fullText.value = button.dataset.fullText || fields.fullText.value;
        if (fields.fullTextChars) fields.fullTextChars.value = button.dataset.fullTextChars || fields.fullTextChars.value;
        if (fields.figureLimit) fields.figureLimit.value = button.dataset.figureLimit || fields.figureLimit.value;

        presetButtons.forEach((item) => item.classList.remove("is-applied"));
        button.classList.add("is-applied");
      });
    });
  };

  const setupFigureLightbox = () => {
    const triggers = Array.from(document.querySelectorAll("[data-gallery-image]"));
    if (!triggers.length) {
      return;
    }

    const items = triggers.map((trigger) => ({
      src: trigger.dataset.gallerySrc || "",
      title: trigger.dataset.galleryTitle || "论文图片",
      meta: trigger.dataset.galleryMeta || "",
      caption: trigger.dataset.galleryCaption || "",
      reason: trigger.dataset.galleryReason || "",
    }));

    let dialog = null;
    let imageFrame = null;
    let image = null;
    let title = null;
    let meta = null;
    let caption = null;
    let reason = null;
    let footer = null;
    let originalLink = null;
    let counter = null;
    let previousButton = null;
    let nextButton = null;
    let zoomOutButton = null;
    let zoomResetButton = null;
    let zoomInButton = null;
    let infoToggleButton = null;
    let currentIndex = 0;
    let zoomLevel = 1;
    let detailsOpen = false;

    const isDialogOpen = () => Boolean(dialog && (dialog.open || dialog.classList.contains("is-open")));

    const frameSpace = () => {
      if (!imageFrame) {
        return { height: 0, width: 0 };
      }
      const style = getComputedStyle(imageFrame);
      const verticalPadding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
      const horizontalPadding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      return {
        height: Math.max(160, imageFrame.clientHeight - verticalPadding),
        width: Math.max(160, imageFrame.clientWidth - horizontalPadding),
      };
    };

    const renderItem = (index) => {
      if (!items.length) {
        return;
      }
      currentIndex = (index + items.length) % items.length;
      const item = items[currentIndex];

      image.src = item.src;
      image.alt = item.title;
      title.textContent = item.title;
      meta.textContent = item.meta;
      caption.textContent = item.caption;
      caption.hidden = !item.caption;
      reason.textContent = item.reason;
      reason.hidden = !item.reason;
      originalLink.href = item.src;
      counter.textContent = `${currentIndex + 1} / ${items.length}`;

      const hasMultipleItems = items.length > 1;
      previousButton.disabled = !hasMultipleItems;
      nextButton.disabled = !hasMultipleItems;
      resetZoom();
    };

    const applyZoom = () => {
      if (!image || !imageFrame) {
        return;
      }
      const isZoomed = zoomLevel > 1;
      const space = frameSpace();
      imageFrame.classList.toggle("is-zoomed", isZoomed);
      image.style.width = isZoomed ? `${Math.round(zoomLevel * 100)}%` : "";
      image.style.height = isZoomed ? "auto" : "";
      image.style.maxWidth = isZoomed ? "none" : `${space.width}px`;
      image.style.maxHeight = isZoomed ? "none" : `${space.height}px`;
      image.style.cursor = isZoomed ? "zoom-out" : "zoom-in";
      if (zoomOutButton) {
        zoomOutButton.disabled = zoomLevel <= 1;
      }
      if (zoomInButton) {
        zoomInButton.disabled = zoomLevel >= 2;
      }
    };

    function resetZoom() {
      zoomLevel = 1;
      applyZoom();
    }

    const setDetailsOpen = (open) => {
      detailsOpen = open;
      if (footer) {
        footer.hidden = !detailsOpen;
      }
      if (infoToggleButton) {
        infoToggleButton.setAttribute("aria-pressed", detailsOpen ? "true" : "false");
        infoToggleButton.textContent = detailsOpen ? "隐藏信息" : "信息";
      }
      requestAnimationFrame(applyZoom);
    };

    const showPrevious = () => {
      renderItem(currentIndex - 1);
    };

    const showNext = () => {
      renderItem(currentIndex + 1);
    };

    const closeDialog = () => {
      if (!dialog) {
        return;
      }
      if (typeof dialog.close === "function" && dialog.open) {
        dialog.close();
      }
      dialog.classList.remove("is-open");
      dialog.removeAttribute("open");
      document.body.classList.remove("has-paper-lightbox");
    };

    const ensureDialog = () => {
      if (dialog) {
        return dialog;
      }

      dialog = document.createElement("dialog");
      dialog.className = "paper-lightbox";
      dialog.setAttribute("aria-label", "图片放大预览");
      dialog.innerHTML = `
        <div class="paper-lightbox-panel" role="document">
          <div class="paper-lightbox-topbar">
            <span class="paper-lightbox-counter" aria-live="polite"></span>
            <div class="paper-lightbox-tools" aria-label="图片查看控制">
              <button type="button" class="paper-lightbox-tool paper-lightbox-zoom-out" aria-label="缩小">−</button>
              <button type="button" class="paper-lightbox-tool paper-lightbox-zoom-reset">适屏</button>
              <button type="button" class="paper-lightbox-tool paper-lightbox-zoom-in" aria-label="放大">＋</button>
              <button type="button" class="paper-lightbox-tool paper-lightbox-info-toggle" aria-pressed="false">信息</button>
              <a class="button secondary paper-lightbox-original" href="#" target="_blank" rel="noreferrer">打开原图</a>
              <button type="button" class="paper-lightbox-close">关闭</button>
            </div>
          </div>
          <div class="paper-lightbox-image-frame">
            <button type="button" class="paper-lightbox-nav paper-lightbox-prev" aria-label="上一张">‹</button>
            <img class="paper-lightbox-image" alt="">
            <button type="button" class="paper-lightbox-nav paper-lightbox-next" aria-label="下一张">›</button>
          </div>
          <div class="paper-lightbox-footer" hidden>
            <div class="paper-lightbox-copy">
              <span class="paper-lightbox-meta"></span>
              <strong class="paper-lightbox-title"></strong>
              <p class="paper-lightbox-caption"></p>
              <p class="paper-lightbox-reason"></p>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(dialog);

      imageFrame = dialog.querySelector(".paper-lightbox-image-frame");
      image = dialog.querySelector(".paper-lightbox-image");
      title = dialog.querySelector(".paper-lightbox-title");
      meta = dialog.querySelector(".paper-lightbox-meta");
      caption = dialog.querySelector(".paper-lightbox-caption");
      reason = dialog.querySelector(".paper-lightbox-reason");
      footer = dialog.querySelector(".paper-lightbox-footer");
      originalLink = dialog.querySelector(".paper-lightbox-original");
      counter = dialog.querySelector(".paper-lightbox-counter");
      previousButton = dialog.querySelector(".paper-lightbox-prev");
      nextButton = dialog.querySelector(".paper-lightbox-next");
      zoomOutButton = dialog.querySelector(".paper-lightbox-zoom-out");
      zoomResetButton = dialog.querySelector(".paper-lightbox-zoom-reset");
      zoomInButton = dialog.querySelector(".paper-lightbox-zoom-in");
      infoToggleButton = dialog.querySelector(".paper-lightbox-info-toggle");

      dialog.querySelector(".paper-lightbox-close")?.addEventListener("click", closeDialog);
      previousButton?.addEventListener("click", showPrevious);
      nextButton?.addEventListener("click", showNext);
      zoomOutButton?.addEventListener("click", () => {
        zoomLevel = Math.max(1, Math.round((zoomLevel - 0.25) * 100) / 100);
        applyZoom();
      });
      zoomResetButton?.addEventListener("click", resetZoom);
      zoomInButton?.addEventListener("click", () => {
        zoomLevel = Math.min(2, Math.round((zoomLevel + 0.25) * 100) / 100);
        applyZoom();
      });
      infoToggleButton?.addEventListener("click", () => {
        setDetailsOpen(!detailsOpen);
      });
      image?.addEventListener("click", () => {
        zoomLevel = zoomLevel > 1 ? 1 : 1.5;
        applyZoom();
      });
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) {
          closeDialog();
        }
      });
      dialog.addEventListener("cancel", () => {
        dialog.classList.remove("is-open");
        document.body.classList.remove("has-paper-lightbox");
      });
      dialog.addEventListener("close", () => {
        dialog.classList.remove("is-open");
        document.body.classList.remove("has-paper-lightbox");
      });
      return dialog;
    };

    triggers.forEach((trigger, index) => {
      trigger.addEventListener("click", () => {
        const modal = ensureDialog();
        renderItem(index);
        setDetailsOpen(false);

        document.body.classList.add("has-paper-lightbox");
        if (typeof modal.showModal === "function") {
          modal.showModal();
        } else {
          modal.setAttribute("open", "");
          modal.classList.add("is-open");
        }
        requestAnimationFrame(applyZoom);
      });
    });

    window.addEventListener("resize", () => {
      if (isDialogOpen()) {
        applyZoom();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (!isDialogOpen()) {
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        showPrevious();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        showNext();
      } else if (event.key === "Escape") {
        closeDialog();
      }
    });
  };

  const setupForest = () => {
    const dataNode = document.getElementById("forest-data");
    const grid = document.querySelector("[data-forest-grid]");
    if (!dataNode || !grid) {
      return;
    }
    const stage = document.querySelector("[data-forest-stage]");
    const experience = document.querySelector("[data-forest-experience]");
    const visibleCountNode = document.querySelector("[data-forest-visible-count]");

    let tiles = [];
    try {
      tiles = JSON.parse(dataNode.textContent || "[]");
    } catch (_error) {
      tiles = [];
    }
    const tileById = new Map(tiles.map((tile) => [tile.arxiv_id, tile]));
    const buttons = Array.from(document.querySelectorAll("[data-forest-tile]"));
    const filters = Array.from(document.querySelectorAll("[data-forest-filter]"));
    const groves = Array.from(document.querySelectorAll("[data-forest-grove]"));
    const moreButtons = Array.from(document.querySelectorAll("[data-forest-focus-grove]"));
    const pagerButtons = Array.from(document.querySelectorAll("[data-grove-page-prev], [data-grove-page-next]"));
    const focusClearButton = document.querySelector("[data-forest-focus-clear]");
    const detailCloseButton = document.querySelector("[data-forest-detail-close]");
    const empty = document.querySelector("[data-forest-empty]");
    const statusFilterKeys = new Set(["all", "summarized", "unsummarized", "full_text", "high_relevance"]);
    const activeFilters = {
      topic: "all",
      status: "all",
    };
    let focusedGrove = "";
    const grovePages = new Map();
    let resizeTimer = 0;

    const nodes = {
      kind: document.querySelector("[data-forest-detail-kind]"),
      title: document.querySelector("[data-forest-detail-title]"),
      paper: document.querySelector("[data-forest-detail-paper]"),
      score: document.querySelector("[data-forest-detail-score]"),
      rarity: document.querySelector("[data-forest-detail-rarity]"),
      growth: document.querySelector("[data-forest-detail-growth]"),
      category: document.querySelector("[data-forest-detail-category]"),
      authors: document.querySelector("[data-forest-detail-authors]"),
      arxiv: document.querySelector("[data-forest-detail-arxiv]"),
      keywords: document.querySelector("[data-forest-detail-keywords]"),
      categories: document.querySelector("[data-forest-detail-categories]"),
      status: document.querySelector("[data-forest-detail-status]"),
      abstract: document.querySelector("[data-forest-detail-abstract]"),
      plant: document.querySelector("[data-forest-detail-plant]"),
      sprite: document.querySelector("[data-forest-detail-sprite]"),
      growthDiary: document.querySelector("[data-forest-growth-diary]"),
      growthStatusBadge: document.querySelector("[data-forest-growth-status]"),
      growthStatusFill: document.querySelector("[data-forest-growth-fill]"),
      grownVisible: document.querySelector("[data-forest-grown-visible]"),
      growthVisible: document.querySelector("[data-forest-growth-visible]"),
      activeTopic: document.querySelector("[data-forest-active-topic]"),
      activeStatus: document.querySelector("[data-forest-active-status]"),
    };

    const text = (value, fallback = "") => {
      const normalized = Array.isArray(value) ? value.join(", ") : String(value || "");
      return normalized || fallback;
    };

    const matchedButtons = () => buttons.filter((button) => button.dataset.filterMatched === "true");
    const currentPageSize = () => (window.matchMedia("(max-width: 900px)").matches ? 20 : 36);
    const groveTiles = (grove) => Array.from(grove.querySelectorAll("[data-forest-tile]"));
    const matchedGroveTiles = (grove) => groveTiles(grove).filter((button) => button.dataset.filterMatched === "true");

    const updateGrowthStatusSummary = () => {
      const visible = matchedButtons();
      const grown = visible.filter((button) => button.dataset.summarized === "true").length;
      const growthPercent = visible.length ? Math.round((grown / visible.length) * 100) : 0;
      if (nodes.grownVisible) {
        nodes.grownVisible.textContent = String(grown);
      }
      if (nodes.growthVisible) {
        nodes.growthVisible.textContent = String(visible.length);
      }
      if (nodes.growthStatusBadge) {
        nodes.growthStatusBadge.classList.toggle("has-growth", grown > 0);
        nodes.growthStatusBadge.dataset.growthRatio = visible.length ? `${grown}/${visible.length}` : "0/0";
        nodes.growthStatusBadge.style.setProperty("--forest-grown-progress", `${growthPercent}%`);
      }
      if (nodes.growthStatusFill) {
        const badgeWidth = nodes.growthStatusBadge ? Math.max(nodes.growthStatusBadge.clientWidth - 10, 0) : 0;
        const fillWidth = growthPercent > 0 ? Math.max(3, Math.round((badgeWidth * growthPercent) / 100)) : 0;
        nodes.growthStatusFill.style.width = `${fillWidth}px`;
      }
    };

    const buttonGroup = (button) => button.dataset.filterGroup || (statusFilterKeys.has(button.dataset.forestFilter || "") ? "status" : "topic");

    const groveKeyForButton = (button) => button.dataset.groveKey || button.closest("[data-forest-grove]")?.dataset.groveKey || "";

    const matchesTopicFilter = (button) => {
      const topic = activeFilters.topic || "all";
      return topic === "all" || button.dataset.filterKey === topic;
    };

    const matchesStatusFilter = (button) => {
      const status = activeFilters.status || "all";
      if (status === "all") return true;
      if (status === "summarized") return button.dataset.summarized === "true";
      if (status === "unsummarized") return button.dataset.summarized !== "true";
      if (status === "full_text") return button.classList.contains("growth-full_text");
      if (status === "high_relevance") return button.dataset.highRelevance === "true";
      return true;
    };

    const matchesActiveFilters = (button, options = {}) => {
      const focusedMatch = options.ignoreFocus || !focusedGrove || groveKeyForButton(button) === focusedGrove;
      const statusIsFiltering = activeFilters.status !== "all";
      const overflowAllowed = options.ignoreOverflow || Boolean(focusedGrove) || statusIsFiltering;
      const overflowMatch = overflowAllowed || button.dataset.groveOverflow !== "true";
      return focusedMatch && overflowMatch && matchesTopicFilter(button) && matchesStatusFilter(button);
    };

    const selectedVisibleButton = () => buttons.find((button) => !button.hidden && button.classList.contains("is-selected"));

    const filterLabel = (group) => {
      const activeKey = activeFilters[group] || "all";
      const button = filters.find((item) => buttonGroup(item) === group && item.dataset.forestFilter === activeKey);
      return button?.dataset.filterLabel || (group === "topic" ? "全部主题" : "全部状态");
    };

    const updateActiveFilterLabels = () => {
      if (nodes.activeTopic) {
        nodes.activeTopic.textContent = filterLabel("topic");
      }
      if (nodes.activeStatus) {
        nodes.activeStatus.textContent = filterLabel("status");
      }
    };

    const updateFilterButtons = () => {
      filters.forEach((button) => {
        const active = activeFilters[buttonGroup(button)] === (button.dataset.forestFilter || "all");
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    };

    const updateMoreButtons = () => {
      const statusIsFiltering = activeFilters.status !== "all";
      moreButtons.forEach((button) => {
        const grove = button.closest("[data-forest-grove]");
        const overflowTiles = Array.from(grove?.querySelectorAll("[data-forest-tile][data-grove-overflow='true']") || []);
        const overflowVisible = overflowTiles.filter((tileButton) =>
          matchesActiveFilters(tileButton, { ignoreFocus: true, ignoreOverflow: true })
        ).length;
        button.hidden = Boolean(focusedGrove) || statusIsFiltering || !grove || grove.hidden || overflowVisible === 0;
        button.dataset.groveMoreCount = String(overflowVisible);
        const countNode = button.querySelector("strong");
        if (countNode) {
          countNode.textContent = `+${overflowVisible}`;
        }
      });
    };

    const shouldPageGrove = (grove, total) => {
      if (!grove || total <= currentPageSize()) return false;
      const key = grove.dataset.groveKey || "";
      return Boolean((focusedGrove && focusedGrove === key) || (!focusedGrove && activeFilters.status !== "all"));
    };

    const updateGrovePagination = () => {
      const pageSize = currentPageSize();
      groves.forEach((grove) => {
        const key = grove.dataset.groveKey || "";
        const tilesForGrove = groveTiles(grove);
        const matched = matchedGroveTiles(grove);
        const pager = grove.querySelector("[data-grove-pager]");
        const prev = grove.querySelector("[data-grove-page-prev]");
        const next = grove.querySelector("[data-grove-page-next]");
        const status = grove.querySelector("[data-grove-page-status]");
        const paged = shouldPageGrove(grove, matched.length);
        const totalPages = paged ? Math.max(1, Math.ceil(matched.length / pageSize)) : 1;
        const page = paged ? Math.max(0, Math.min(grovePages.get(key) || 0, totalPages - 1)) : 0;
        const start = page * pageSize;
        const end = Math.min(start + pageSize, matched.length);

        grovePages.set(key, page);
        tilesForGrove.forEach((button) => {
          const matchedFilter = button.dataset.filterMatched === "true";
          if (!matchedFilter) {
            button.hidden = true;
            button.dataset.pageHidden = "false";
            return;
          }
          const index = matched.indexOf(button);
          const visibleOnPage = !paged || (index >= start && index < end);
          button.hidden = !visibleOnPage;
          button.dataset.pageHidden = visibleOnPage ? "false" : "true";
        });

        if (pager) {
          pager.hidden = !paged;
        }
        if (prev) {
          prev.disabled = !paged || page <= 0;
        }
        if (next) {
          next.disabled = !paged || page >= totalPages - 1;
        }
        if (status) {
          const pageLabel = paged ? `${start + 1}-${end} / ${matched.length}` : `${matched.length} / ${matched.length}`;
          status.textContent = `第 ${page + 1} / ${totalPages} 页 · ${pageLabel}`;
        }
      });
    };

    const firstVisibleTileInGrove = (groveKey) =>
      buttons.find((button) => !button.hidden && (!groveKey || groveKeyForButton(button) === groveKey));

    const turnGrovePage = (button, direction) => {
      const grove = button.closest("[data-forest-grove]");
      if (!grove) return;
      const key = grove.dataset.groveKey || "";
      const total = matchedGroveTiles(grove).length;
      const pageSize = currentPageSize();
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      const current = grovePages.get(key) || 0;
      grovePages.set(key, Math.max(0, Math.min(current + direction, totalPages - 1)));
      applyFilterState(false);
      const first = firstVisibleTileInGrove(key);
      if (first) {
        setSelected(first);
        renderDetails(tileById.get(first.dataset.arxivId));
      }
      if (grid) {
        grid.scrollTo({ top: 0, behavior: "smooth" });
      }
    };

    const setFocusedGrove = (key) => {
      focusedGrove = key || "";
      if (focusedGrove && !grovePages.has(focusedGrove)) {
        grovePages.set(focusedGrove, 0);
      }
      if (stage) {
        stage.classList.toggle("is-focused-forest", Boolean(focusedGrove));
        if (focusedGrove) {
          stage.dataset.focusedGrove = focusedGrove;
        } else {
          delete stage.dataset.focusedGrove;
        }
      }
      if (focusClearButton) {
        focusClearButton.hidden = !focusedGrove;
      }
    };

    const closeDetailDrawer = () => {
      document.body.classList.remove("forest-detail-open");
      if (detailCloseButton) {
        detailCloseButton.setAttribute("aria-expanded", "false");
      }
    };

    const openDetailDrawer = () => {
      document.body.classList.add("forest-detail-open");
      if (detailCloseButton) {
        detailCloseButton.setAttribute("aria-expanded", "true");
      }
    };

    const setSelected = (button, animate = true) => {
      buttons.forEach((item) => {
        const selected = item === button;
        item.classList.toggle("is-selected", selected);
        item.setAttribute("aria-pressed", selected ? "true" : "false");
      });
      groves.forEach((grove) => {
        grove.classList.toggle("is-focused-grove", grove.contains(button));
      });
      if (!animate) {
        return;
      }
      if (stage) {
        const stageRect = stage.getBoundingClientRect();
        const buttonRect = button.getBoundingClientRect();
        const selectionX = ((buttonRect.left + buttonRect.width / 2 - stageRect.left) / stageRect.width) * 100;
        const selectionY = ((buttonRect.top + buttonRect.height / 2 - stageRect.top) / stageRect.height) * 100;
        stage.style.setProperty("--forest-selection-x", `${Math.max(0, Math.min(100, selectionX))}%`);
        stage.style.setProperty("--forest-selection-y", `${Math.max(0, Math.min(100, selectionY))}%`);
        stage.dataset.selectionKind = button.dataset.filterKey || "all";
        stage.classList.remove("is-selection-pulse");
        void stage.offsetWidth;
        stage.classList.add("is-selection-pulse");
        window.setTimeout(() => stage.classList.remove("is-selection-pulse"), 760);
      }
      button.classList.remove("is-planting");
      void button.offsetWidth;
      button.classList.add("is-planting");
      window.setTimeout(() => button.classList.remove("is-planting"), 720);
    };

    const spritePath = (tile) => {
      const prefix = tile.plant_stage === "sapling" ? "sapling-" : "tree-";
      return `/static/forest/generated/${prefix}${tile.asset}.png?v=20260526-ref-sprites`;
    };

    const growthSpritePath = (tile, step) => {
      const prefix = step.plant_stage === "tree" ? "tree-" : "sapling-";
      return `/static/forest/generated/${prefix}${tile.asset}.png?v=20260526-ref-sprites`;
    };

    const fallbackGrowthSteps = (tile) => [
      {
        key: tile.growth || "metadata",
        label: tile.growth_label || "树苗",
        detail: tile.summary_status || "元数据",
        rank: Number(tile.growth_rank || 0),
        plant_stage: tile.plant_stage || "sapling",
      },
    ];

    const normalizedGrowthSteps = (tile) => {
      const steps =
        Array.isArray(tile.growth_steps) && tile.growth_steps.length ? tile.growth_steps : fallbackGrowthSteps(tile);
      return steps.map((step) => ({
        key: step.key || "metadata",
        label: step.label || "树苗",
        detail: step.detail || "元数据",
        rank: Number(step.rank || 0),
        plant_stage: step.plant_stage === "tree" ? "tree" : "sapling",
      }));
    };

    const renderGrowthDiary = (tile) => {
      if (!nodes.growthDiary || !tile) return;
      const steps = normalizedGrowthSteps(tile);
      nodes.growthDiary.replaceChildren();
      nodes.growthDiary.dataset.currentGrowth = tile.growth || "metadata";
      nodes.growthDiary.dataset.stepCount = String(steps.length);
      nodes.growthDiary.style.setProperty("--forest-growth-step-count", String(steps.length));
      nodes.growthDiary.style.setProperty("--forest-growth-progress", steps.length > 1 ? "100%" : "0%");
      nodes.growthDiary.classList.toggle("is-single-step", steps.length === 1);
      nodes.growthDiary.setAttribute("aria-label", `论文成长进度：${tile.growth_label || "树苗"}`);

      const rail = document.createElement("span");
      rail.className = "forest-growth-rail";
      rail.setAttribute("aria-hidden", "true");
      nodes.growthDiary.append(rail);

      steps.forEach((step, index) => {
        const item = document.createElement("span");
        item.className = `forest-growth-step is-complete ${index === steps.length - 1 ? "is-current" : ""} is-${step.plant_stage}-step`;
        item.dataset.growthStep = step.key;
        item.dataset.growthRank = String(step.rank);

        const icon = document.createElement("i");
        icon.className = "forest-growth-icon";
        icon.setAttribute("aria-hidden", "true");
        const image = document.createElement("img");
        image.src = growthSpritePath(tile, step);
        image.alt = "";
        icon.append(image);

        const label = document.createElement("b");
        label.textContent = step.label;
        const detail = document.createElement("small");
        detail.textContent = step.detail;

        item.append(icon, label, detail);
        nodes.growthDiary.append(item);
      });
    };

    const renderDetails = (tile) => {
      if (!tile) {
        return;
      }
      const inspector = nodes.title ? nodes.title.closest(".forest-inspector") : null;
      if (inspector) {
        inspector.classList.remove("is-updating", "is-tree-stage", "is-sapling-stage");
        inspector.classList.add(tile.has_ai_summary ? "is-tree-stage" : "is-sapling-stage");
        void inspector.offsetWidth;
        inspector.classList.add("is-updating");
        window.setTimeout(() => inspector.classList.remove("is-updating"), 380);
      }
      if (nodes.kind) nodes.kind.textContent = tile.kind_label || tile.primary_category || "";
      if (nodes.title) nodes.title.textContent = tile.title || "";
      if (nodes.paper) nodes.paper.href = tile.detail_url || "#";
      if (nodes.score) nodes.score.textContent = `相关性 ${tile.score_display || tile.score || 0}`;
      if (nodes.rarity) nodes.rarity.textContent = tile.rarity_label || "";
      if (nodes.growth) nodes.growth.textContent = tile.growth_label || "";
      if (nodes.category) nodes.category.textContent = tile.primary_category || "";
      if (nodes.authors) nodes.authors.textContent = text(tile.authors_display || tile.authors, "作者未记录");
      if (nodes.arxiv) {
        nodes.arxiv.href = tile.abs_url || "#";
        nodes.arxiv.textContent = tile.arxiv_id || "arXiv";
      }
      if (nodes.keywords) nodes.keywords.textContent = text(tile.matched_terms_display || tile.matched_keywords, "暂无关键词");
      if (nodes.categories) nodes.categories.textContent = text(tile.categories_display || tile.categories, tile.primary_category || "-");
      if (nodes.status) nodes.status.textContent = tile.summary_status || "只有元数据";
      if (nodes.abstract) nodes.abstract.textContent = tile.abstract || "";
      renderGrowthDiary(tile);
      if (nodes.sprite && tile.asset) {
        nodes.sprite.src = spritePath(tile);
      }
      if (nodes.plant) {
        const plantClasses = [
          "forest-inspector-plant",
          `tree-${tile.kind || "other"}`,
          `is-${tile.plant_stage || "sapling"}-plant`,
        ];
        if (tile.high_relevance) {
          plantClasses.push("is-high-relevance-plant");
        }
        if (tile.growth === "full_text") {
          plantClasses.push("is-full-text-plant");
        }
        nodes.plant.className = plantClasses.join(" ");
        nodes.plant.dataset.growth = tile.growth || "";
      }
    };

    const densityForCount = (count) => {
      if (count >= 28) return "canopy";
      if (count >= 16) return "dense";
      return "open";
    };

    const groveSizeForCount = (count) => {
      if (count >= 48) return "canopy";
      if (count >= 18) return "large";
      if (count >= 7) return "medium";
      return "small";
    };

    const applyDensity = (count) => {
      const density = densityForCount(count);
      [grid, stage, experience].forEach((node) => {
        if (!node) return;
        node.classList.remove("forest-density-open", "forest-density-dense", "forest-density-canopy");
        node.classList.add(`forest-density-${density}`);
        node.dataset.density = density;
      });
      if (visibleCountNode) {
        visibleCountNode.textContent = String(count);
      }
      updateGrowthStatusSummary();
    };

    const applyGroveLayout = () => {
      groves.forEach((grove) => {
        const visibleButtonsForGrove = matchedGroveTiles(grove);
        const visible = visibleButtonsForGrove.length;
        const summarized = visibleButtonsForGrove.filter((button) => button.dataset.summarized === "true").length;
        const saplings = Math.max(visible - summarized, 0);
        const size = groveSizeForCount(visible);
        const countLabel = grove.querySelector("[data-grove-count-label]");
        const growthLabel = grove.querySelector("[data-grove-growth-label]");

        grove.hidden = visible === 0;
        grove.classList.remove("is-canopy-grove", "is-large-grove", "is-medium-grove", "is-small-grove", "is-major", "is-minor");
        grove.classList.add(`is-${size}-grove`, visible >= 48 ? "is-major" : "is-minor");
        if (countLabel) {
          countLabel.textContent = String(visible);
        }
        if (growthLabel) {
          growthLabel.textContent = `${summarized} 成长 / ${saplings} 树苗`;
        }
      });
      const selected = buttons.find((button) => button.classList.contains("is-selected"));
      groves.forEach((grove) => {
        const focused = focusedGrove ? grove.dataset.groveKey === focusedGrove : Boolean(selected && grove.contains(selected));
        grove.classList.toggle("is-focused-grove", focused);
      });
    };

    const applyFilterState = (selectFirst = true) => {
      let visible = 0;
      let firstVisible = null;
      buttons.forEach((button) => {
        const matched = matchesActiveFilters(button);
        button.dataset.filterMatched = matched ? "true" : "false";
        button.dataset.pageHidden = "false";
        button.hidden = !matched;
        if (matched) {
          visible += 1;
          firstVisible = firstVisible || button;
        }
      });
      updateFilterButtons();
      updateActiveFilterLabels();
      if (stage) {
        stage.dataset.activeTopic = activeFilters.topic;
        stage.dataset.activeStatus = activeFilters.status;
        stage.classList.toggle("has-status-filter", activeFilters.status !== "all");
        stage.classList.toggle("has-topic-filter", activeFilters.topic !== "all");
        stage.classList.remove("is-filtering");
        void stage.offsetWidth;
        stage.classList.add("is-filtering");
        window.setTimeout(() => stage.classList.remove("is-filtering"), 520);
      }
      updateGrovePagination();
      firstVisible = firstVisibleTileInGrove("");
      applyGroveLayout();
      updateMoreButtons();
      if (empty) {
        empty.hidden = visible > 0;
      }
      applyDensity(visible);
      if (selectFirst && firstVisible && !selectedVisibleButton()) {
        setSelected(firstVisible);
        renderDetails(tileById.get(firstVisible.dataset.arxivId));
      }
      if (grid && focusedGrove) {
        grid.scrollTo({ top: 0, behavior: "smooth" });
      }
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        setSelected(button);
        renderDetails(tileById.get(button.dataset.arxivId));
        openDetailDrawer();
      });
    });

    filters.forEach((button) => {
      button.addEventListener("click", () => {
        const group = buttonGroup(button);
        activeFilters[group] = button.dataset.forestFilter || "all";
        grovePages.clear();
        if (group === "topic" && focusedGrove && (activeFilters.topic === "all" || activeFilters.topic !== focusedGrove)) {
          setFocusedGrove("");
        }
        applyFilterState();
      });
    });

    moreButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.forestFocusGrove || "";
        grovePages.set(key, 0);
        setFocusedGrove(key);
        applyFilterState();
      });
    });

    pagerButtons.forEach((button) => {
      button.addEventListener("click", () => {
        turnGrovePage(button, button.matches("[data-grove-page-prev]") ? -1 : 1);
      });
    });

    if (focusClearButton) {
      focusClearButton.addEventListener("click", () => {
        setFocusedGrove("");
        applyFilterState();
      });
    }

    if (detailCloseButton) {
      detailCloseButton.addEventListener("click", closeDetailDrawer);
    }

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }
      if (document.body.classList.contains("forest-detail-open")) {
        closeDetailDrawer();
        return;
      }
      if (focusedGrove) {
        setFocusedGrove("");
        applyFilterState(false);
      }
    });

    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => applyFilterState(false), 120);
    });

    const initialButton = buttons.find((button) => button.classList.contains("is-selected")) || buttons[0];
    if (initialButton) {
      setSelected(initialButton, false);
      renderDetails(tileById.get(initialButton.dataset.arxivId));
    }
    setFocusedGrove("");
    closeDetailDrawer();
    applyFilterState(false);
  };

  setupFetchProgress();
  setupSummaryProgress();
  setupPaperFilter();
  setupSettingsPresets();
  setupFigureLightbox();
  setupForest();
})();
