(() => {
  const numberText = (value) => String(value || 0);

  const emptyArxivFetchMessage = (day, sourceText) => {
    const text = String(day || "").trim();
    const parts = text.split("-").map((part) => Number(part));
    if (parts.length === 3 && parts.every((part) => Number.isFinite(part))) {
      const weekday = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2])).getUTCDay();
      if (weekday === 0 || weekday === 6) {
        return `arXiv 没有返回 ${text} 的论文。该日期是周末；arXiv 通常不在周末发布新的公开公告批次，周末提交会进入后续工作日批次。${sourceText}`;
      }
      return `arXiv 没有返回 ${text} 的论文；通常是该日期尚未发布新批次、节假日暂停，或本地日期与 arXiv 公告批次存在时差。${sourceText}`;
    }
    return `arXiv 没有返回这一天的论文；通常是该日期尚未发布新批次，或周末/节假日没有新提交。${sourceText}`;
  };

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

  const resetButtonProgress = (form, button, defaultLabel = "") => {
    const label = defaultLabel || button.dataset.defaultLabel || button.textContent.trim();
    if (label) {
      button.textContent = label;
      button.dataset.defaultLabel = label;
    }
    button.disabled = false;
    button.classList.remove("is-progressing", "is-complete");
    button.style.removeProperty("--progress");
    delete button.dataset.progressStatus;
    delete form.dataset.progressStatus;
    form.classList.remove("has-inline-progress");

    const statusNode = form.querySelector("[data-inline-progress-status]");
    if (statusNode) {
      statusNode.remove();
    }
    const progressScope = form.closest(".action-card, .paper-action-group, .paper-card-ai-actions");
    if (progressScope) {
      delete progressScope.dataset.progressStatus;
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
          const fetchedCount = Number(job.fetched || 0);
          const currentCount = Number(job.current_count || 0);
          const countText = currentCount ? `当前共 ${currentCount} 篇。` : "";
          const sourceText = `官方 API 请求 ${numberText(job.network_requests)} 次，缓存 ${numberText(job.cached_pages)} 页。`;
          const fallbackMessage =
            fetchedCount === 0 && currentCount === 0
              ? emptyArxivFetchMessage(day, sourceText)
              : `抓取完成，论文列表已刷新。${countText}${sourceText}`;
          navigateWithMessage(target, job.message || fallbackMessage);
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
      const initialJobUrl = form.dataset.summaryJobUrl;
      if (!button || !initialJobUrl) {
        return;
      }

      let activeSummaryJobId = "";

      const currentJobUrl = () => form.dataset.summaryJobUrl || initialJobUrl;
      const isCurrentJobUrl = (jobUrl) => currentJobUrl() === jobUrl;

      const applySummaryProgress = (job, trackedJobUrl = currentJobUrl()) => {
        if (!isCurrentJobUrl(trackedJobUrl)) {
          return null;
        }
        form.dataset.activeSummaryJobUrl = trackedJobUrl;
        const statusNode = setButtonProgress(form, button, job, {
          runningLabel: form.dataset.runningLabel || "生成中",
          completedLabel: form.dataset.completedLabel || button.dataset.completedLabel || "已完成",
          failedLabel: "重新生成",
        });
        const label = job.label ? `${job.label} · ` : "";
        const model = job.model ? ` · ${job.model}` : "";
        renderInlineStatus(statusNode, `${label}${job.message || job.stage_label || "正在处理。"}${model}`, job);
        return statusNode;
      };

      const handleError = (error, trackedJobUrl = currentJobUrl()) => {
        if (!isCurrentJobUrl(trackedJobUrl)) {
          return;
        }
        applySummaryProgress({
          status: "failed",
          stage_label: "生成失败",
          message: error.message || "生成失败。",
          percent: 100,
        }, trackedJobUrl);
      };

      const poll = async (jobId, trackedJobUrl = currentJobUrl()) => {
        const response = await fetch(`/summary-jobs/${jobId}`, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error("无法读取生成进度。");
        }
        const job = await response.json();
        applySummaryProgress(job, trackedJobUrl);

        if (job.status === "completed") {
          clearStoredSummaryJob(trackedJobUrl, jobId);
          activeSummaryJobId = "";
          if (isCurrentJobUrl(trackedJobUrl)) {
            window.setTimeout(() => {
              navigateWithMessage(window.location.href, "");
            }, 700);
          }
          return;
        }

        if (job.status === "failed" || job.status === "not_found") {
          clearStoredSummaryJob(trackedJobUrl, jobId);
          activeSummaryJobId = "";
          if (isCurrentJobUrl(trackedJobUrl)) {
            applySummaryProgress({
              ...job,
              status: "failed",
              message: job.status === "not_found" ? "任务状态已失效，可能服务已重启，请重新生成。" : job.error || job.message || "生成失败。",
            }, trackedJobUrl);
          }
          return;
        }

        storeSummaryJob(trackedJobUrl, jobId, job);
        window.setTimeout(() => poll(jobId, trackedJobUrl).catch((error) => handleError(error, trackedJobUrl)), 850);
      };

      const restoreCurrentSummaryJob = () => {
        resetButtonProgress(form, button, button.dataset.defaultLabel || button.textContent.trim());
        const jobUrl = currentJobUrl();
        const storedJob = readStoredSummaryJob(jobUrl);
        if (!storedJob || !storedJob.jobId) {
          activeSummaryJobId = "";
          return;
        }
        activeSummaryJobId = storedJob.jobId;
        applySummaryProgress({
          status: storedJob.status || "running",
          stage_label: "恢复进度",
          message: "正在恢复这篇论文的智能生成进度。",
          percent: storedJob.percent || 2,
        }, jobUrl);
        poll(activeSummaryJobId, jobUrl).catch((error) => handleError(error, jobUrl));
      };

      form.addEventListener("summary-job-url-change", restoreCurrentSummaryJob);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const jobUrl = currentJobUrl();
        form.dataset.activeSummaryJobUrl = jobUrl;
        const data = new FormData(form);
        applySummaryProgress({
          status: "queued",
          stage_label: "等待开始",
          message: "任务已创建，正在整理上下文。",
          percent: 3,
        }, jobUrl);

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
          await poll(activeSummaryJobId, jobUrl);
        } catch (error) {
          handleError(error, jobUrl);
        }
      });

      const storedJob = readStoredSummaryJob(initialJobUrl);
      if (storedJob && storedJob.jobId) {
        activeSummaryJobId = storedJob.jobId;
        applySummaryProgress({
          status: storedJob.status || "running",
          stage_label: "恢复进度",
          message: "页面已重新打开，正在恢复智能生成进度。",
          percent: storedJob.percent || 2,
        }, initialJobUrl);
        poll(activeSummaryJobId, initialJobUrl).catch((error) => handleError(error, initialJobUrl));
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
      const favoritesOnly = rows.some((row) => row.closest("[data-favorites-only='true']"));

      rows.forEach((row) => {
        const haystack = row.dataset.paperSearch || "";
        const favoriteMatched = !row.closest("[data-favorites-only='true']") || row.dataset.favoriteVisible !== "false";
        const matched = favoriteMatched && (!query || haystack.includes(query));
        row.hidden = !matched;
        if (matched) {
          visibleCount += 1;
        }
      });

      if (countNode) {
        countNode.textContent = numberText(visibleCount);
      }
      if (emptyNode) {
        emptyNode.hidden = (!query && !favoritesOnly) || visibleCount > 0;
      }
    };

    input.addEventListener("input", applyFilter);
    document.addEventListener("paper-filter-refresh", applyFilter);
    applyFilter();
  };

  const setFavoriteButtonState = (button, favorite) => {
    if (!button) return;
    button.classList.toggle("is-favorite", favorite);
    button.setAttribute("aria-pressed", favorite ? "true" : "false");
    button.title = favorite ? "取消收藏" : "收藏论文";
    const label = button.querySelector("[data-favorite-label]");
    if (label) {
      label.textContent = favorite ? "已收藏" : "收藏";
    } else {
      button.textContent = favorite ? "已收藏" : "收藏";
    }
  };

  const syncFavoriteState = (arxivId, favorite, favoriteCount = null) => {
    if (!arxivId) return;
    document.querySelectorAll("[data-favorite-form]").forEach((form) => {
      if (form.dataset.arxivId !== arxivId) return;
      form.dataset.favorite = favorite ? "true" : "false";
      const button = form.querySelector("[data-favorite-label]")?.closest("button") || form.querySelector("button");
      setFavoriteButtonState(button, favorite);
      if (button) {
        button.disabled = false;
      }
    });
    document.querySelectorAll("[data-paper-row]").forEach((row) => {
      if (row.dataset.arxivId !== arxivId) return;
      row.classList.toggle("is-favorite", favorite);
      row.dataset.favoriteVisible = favorite ? "true" : "false";
    });
    document.querySelectorAll("[data-favorite-count]").forEach((node) => {
      if (favoriteCount !== null) node.textContent = numberText(favoriteCount);
    });
    document.dispatchEvent(new CustomEvent("paper-favorite-change", {
      detail: { arxivId, favorite, favoriteCount },
    }));
    document.dispatchEvent(new CustomEvent("paper-filter-refresh"));
  };

  const setupFavoriteToggles = () => {
    const forms = Array.from(document.querySelectorAll("[data-favorite-form]"));
    if (!forms.length) {
      return;
    }
    forms.forEach((form) => {
      const button = form.querySelector("button");
      setFavoriteButtonState(button, form.dataset.favorite === "true");
      form.addEventListener("submit", async (event) => {
        if (!window.fetch) {
          return;
        }
        event.preventDefault();
        const submitButton = form.querySelector("button");
        if (submitButton) {
          submitButton.disabled = true;
        }
        try {
          const response = await fetch(form.action, {
            method: "POST",
            body: new FormData(form),
            headers: { Accept: "application/json" },
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.error || "收藏失败。");
          }
          syncFavoriteState(payload.arxiv_id || form.dataset.arxivId, Boolean(payload.favorite), payload.favorite_count);
        } catch (_error) {
          if (submitButton) {
            submitButton.disabled = false;
          }
        }
      });
    });
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
    const filterSelects = Array.from(document.querySelectorAll("[data-forest-filter-select]"));
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
      kindEn: document.querySelector("[data-forest-detail-kind-en]"),
      kindZh: document.querySelector("[data-forest-detail-kind-zh]"),
      title: document.querySelector("[data-forest-detail-title]"),
      titleTranslation: document.querySelector("[data-forest-detail-title-translation]"),
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
      translationCard: document.querySelector("[data-forest-detail-translation-card]"),
      translatedTitle: document.querySelector("[data-forest-detail-translated-title]"),
      translatedAbstract: document.querySelector("[data-forest-detail-translated-abstract]"),
      plant: document.querySelector("[data-forest-detail-plant]"),
      sprite: document.querySelector("[data-forest-detail-sprite]"),
      favoriteForm: document.querySelector("[data-forest-detail-favorite-form]"),
      favoriteButton: document.querySelector("[data-forest-detail-favorite-button]"),
      aiForm: document.querySelector("[data-forest-detail-ai-form]"),
      aiForce: document.querySelector("[data-forest-detail-ai-force]"),
      aiSubmit: document.querySelector("[data-forest-detail-ai-submit]"),
      aiStatus: document.querySelector("[data-forest-detail-ai-status]"),
      translationLink: document.querySelector("[data-forest-detail-translation-link]"),
      translationLinkSecondary: document.querySelector("[data-forest-detail-translation-link-secondary]"),
      summaryLink: document.querySelector("[data-forest-detail-summary-link]"),
      fullLink: document.querySelector("[data-forest-detail-full-link]"),
      growthDiary: document.querySelector("[data-forest-growth-diary]"),
      growthStatusBadge: document.querySelector("[data-forest-growth-status]"),
      growthStatusFill: document.querySelector("[data-forest-growth-fill]"),
      grownVisible: document.querySelector("[data-forest-grown-visible]"),
      growthVisible: document.querySelector("[data-forest-growth-visible]"),
      filterVisible: document.querySelector("[data-forest-filter-visible]"),
      filterTotal: document.querySelector("[data-forest-filter-total]"),
      activeTopic: document.querySelector("[data-forest-active-topic]"),
      activeStatus: document.querySelector("[data-forest-active-status]"),
    };

    const text = (value, fallback = "") => {
      const normalized = Array.isArray(value) ? value.join(", ") : String(value || "");
      return normalized || fallback;
    };

    const setRichText = (node, html, fallback = "") => {
      if (!node) return;
      const rendered = String(html || "");
      if (rendered) {
        node.innerHTML = rendered;
      } else {
        node.textContent = fallback;
      }
    };

    const matchedButtons = () => buttons.filter((button) => button.dataset.filterMatched === "true");
    const basePageSize = () => {
      const width = window.innerWidth || document.documentElement.clientWidth || 0;
      if (width <= 900) return 36;
      if (width >= 1500) return 72;
      return 54;
    };
    const groveTiles = (grove) => Array.from(grove.querySelectorAll("[data-forest-tile]"));
    const matchedGroveTiles = (grove) => groveTiles(grove).filter((button) => button.dataset.filterMatched === "true");

    const groveColumnCount = (grove) => {
      const trees = grove?.querySelector(".forest-grove-trees");
      if (!trees) return 1;
      const declaredColumns = Number.parseInt(trees.dataset.groveColumns || "", 10);
      if (Number.isFinite(declaredColumns) && declaredColumns > 0) {
        return declaredColumns;
      }
      const style = window.getComputedStyle(trees);
      const tileWidth = Number.parseFloat(style.getPropertyValue("--grove-tile-width")) || 84;
      const columnGap = Number.parseFloat(style.columnGap) || 0;
      const paddingX = (Number.parseFloat(style.paddingLeft) || 0) + (Number.parseFloat(style.paddingRight) || 0);
      const availableWidth = Math.max(1, trees.clientWidth - paddingX);
      return Math.max(1, Math.floor((availableWidth + columnGap) / (tileWidth + columnGap)));
    };

    const pageSizeForGrove = (grove) => {
      const columns = groveColumnCount(grove);
      return Math.max(columns, Math.ceil(basePageSize() / columns) * columns);
    };

    const isExpandedGroveLayout = () => Boolean(focusedGrove) || activeFilters.topic !== "all" || activeFilters.status !== "all";

    const updateOverviewPreviewLimits = () => {
      if (isExpandedGroveLayout()) return;
      groves.forEach((grove) => {
        const moreButton = grove.querySelector(".forest-grove-more");
        if (!moreButton || moreButton.hidden) return;
        const previewCapacity = Math.max(1, groveColumnCount(grove) * 2 - 1);
        let visiblePreviewCount = 0;
        let matchedPreviewCount = 0;
        groveTiles(grove).forEach((button) => {
          if (button.dataset.filterMatched !== "true") return;
          matchedPreviewCount += 1;
          const visibleInPreview = visiblePreviewCount < previewCapacity;
          button.hidden = !visibleInPreview;
          button.dataset.pageHidden = visibleInPreview ? "false" : "true";
          if (visibleInPreview) {
            visiblePreviewCount += 1;
          }
        });
        const hiddenPreviewCount = Math.max(0, matchedPreviewCount - visiblePreviewCount);
        const templateOverflowCount = Number.parseInt(moreButton.dataset.groveMoreCount || "0", 10) || 0;
        const remainingCount = templateOverflowCount + hiddenPreviewCount;
        moreButton.dataset.groveMoreCount = String(remainingCount);
        const countNode = moreButton.querySelector("strong");
        if (countNode) {
          countNode.textContent = `余 ${remainingCount}`;
        }
      });
    };

    const updateGroveTreeHeights = () => {
      const expandedLayout = isExpandedGroveLayout();
      groves.forEach((grove) => {
        const trees = grove.querySelector(".forest-grove-trees");
        if (!trees || grove.hidden) {
          trees?.style.removeProperty("--grove-trees-min-height");
          grove.style.removeProperty("--grove-min-height");
          return;
        }
        const visibleTiles = groveTiles(grove).filter(
          (button) => button.dataset.filterMatched === "true" && button.dataset.pageHidden !== "true" && !button.hidden
        ).length;
        const moreButton = grove.querySelector(".forest-grove-more");
        const visibleItems = visibleTiles + (moreButton && !moreButton.hidden ? 1 : 0);
        if (!visibleItems) {
          trees.style.removeProperty("--grove-trees-min-height");
          return;
        }

        const style = window.getComputedStyle(trees);
        const columns = groveColumnCount(grove);
        const rows = Math.max(1, Math.ceil(visibleItems / columns));
        const rowGap = Number.parseFloat(style.rowGap) || 0;
        const paddingY = (Number.parseFloat(style.paddingTop) || 0) + (Number.parseFloat(style.paddingBottom) || 0);
        const tile = grove.querySelector("[data-forest-tile]");
        const tileHeight = tile ? Number.parseFloat(window.getComputedStyle(tile).height) || tile.getBoundingClientRect().height : 88;
        const moreHeight = moreButton ? Number.parseFloat(window.getComputedStyle(moreButton).height) || moreButton.getBoundingClientRect().height : 0;
        const itemHeight = Math.max(tileHeight, moreHeight, 1);
        const minHeight = rows * itemHeight + Math.max(0, rows - 1) * rowGap + paddingY;
        const groveStyle = window.getComputedStyle(grove);
        const label = grove.querySelector(".forest-grove-label");
        const pager = grove.querySelector("[data-grove-pager]");
        const labelHeight = Math.max(label?.getBoundingClientRect().height || 0, 28);
        const pagerHeight = pager && !pager.hidden ? Math.max(pager.getBoundingClientRect().height || 0, 38) : 0;
        const groveGap = Number.parseFloat(groveStyle.rowGap) || 0;
        const grovePaddingY = (Number.parseFloat(groveStyle.paddingTop) || 0) + (Number.parseFloat(groveStyle.paddingBottom) || 0);
        const visibleRows = 1 + (pagerHeight ? 1 : 0) + 1;
        const groveMinHeight = minHeight + labelHeight + pagerHeight + Math.max(0, visibleRows - 1) * groveGap + grovePaddingY;
        trees.style.setProperty("--grove-trees-min-height", `${Math.ceil(minHeight)}px`);
        grove.style.setProperty("--grove-min-height", `${Math.ceil(groveMinHeight)}px`);
      });
    };

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
      const topicIsFiltering = activeFilters.topic !== "all";
      const overflowAllowed = options.ignoreOverflow || Boolean(focusedGrove) || statusIsFiltering || topicIsFiltering;
      const overflowMatch = overflowAllowed || button.dataset.groveOverflow !== "true";
      return focusedMatch && overflowMatch && matchesTopicFilter(button) && matchesStatusFilter(button);
    };

    const filterOptionsForGroup = (group) => {
      const values = new Set(["all"]);
      filterSelects
        .filter((select) => select.dataset.forestFilterSelect === group)
        .forEach((select) => {
          Array.from(select.options).forEach((option) => values.add(option.value || "all"));
        });
      filters
        .filter((button) => buttonGroup(button) === group)
        .forEach((button) => values.add(button.dataset.forestFilter || "all"));
      return values;
    };

    const validFilterOptions = {
      topic: filterOptionsForGroup("topic"),
      status: filterOptionsForGroup("status"),
    };

    const normalizeFilterKey = (group, value) => {
      const key = String(value || "all");
      if (validFilterOptions[group]?.has(key)) {
        return key;
      }
      return "all";
    };

    const applyUrlFilterState = () => {
      const params = new URLSearchParams(window.location.search);
      activeFilters.topic = normalizeFilterKey("topic", params.get("topic"));
      activeFilters.status = normalizeFilterKey("status", params.get("status"));

      const legacyFilter = params.get("filter");
      if (legacyFilter && activeFilters.topic === "all" && activeFilters.status === "all") {
        if (validFilterOptions.status.has(legacyFilter)) {
          activeFilters.status = legacyFilter;
        } else if (validFilterOptions.topic.has(legacyFilter)) {
          activeFilters.topic = legacyFilter;
        }
      }
    };

    const syncFilterStateToUrl = () => {
      const url = new URL(window.location.href);
      ["topic", "status"].forEach((group) => {
        const value = normalizeFilterKey(group, activeFilters[group]);
        if (value === "all") {
          url.searchParams.delete(group);
        } else {
          url.searchParams.set(group, value);
        }
      });
      url.searchParams.delete("filter");
      url.searchParams.delete("_refresh");
      window.history.replaceState(
        {
          forestFilters: { ...activeFilters },
        },
        "",
        url.toString()
      );
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

    const updateFilterSelects = () => {
      filterSelects.forEach((select) => {
        const group = select.dataset.forestFilterSelect;
        if (!group) return;
        select.value = activeFilters[group] || "all";
      });
    };

    const keepActiveFiltersInView = () => {
      filters.forEach((button) => {
        if (!button.classList.contains("is-active")) return;
        const list = button.closest("[data-forest-filters]");
        if (!list) return;
        const buttonRect = button.getBoundingClientRect();
        const listRect = list.getBoundingClientRect();
        const outside = buttonRect.left < listRect.left || buttonRect.right > listRect.right;
        if (outside) {
          button.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
        }
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
        const totalMatched = grove
          ? groveTiles(grove).filter((tileButton) => matchesActiveFilters(tileButton, { ignoreOverflow: true })).length
          : 0;
        const paged = shouldPageGrove(grove, totalMatched);
        button.hidden = Boolean(focusedGrove) || statusIsFiltering || paged || !grove || grove.hidden || overflowVisible === 0;
        button.dataset.groveMoreCount = String(overflowVisible);
        const countNode = button.querySelector("strong");
        if (countNode) {
          countNode.textContent = `余 ${overflowVisible}`;
        }
      });
    };

    const shouldPageGrove = () => false;

    const updateGrovePagination = () => {
      groves.forEach((grove) => {
        const key = grove.dataset.groveKey || "";
        const tilesForGrove = groveTiles(grove);
        const matched = matchedGroveTiles(grove);
        const pager = grove.querySelector("[data-grove-pager]");
        const prev = grove.querySelector("[data-grove-page-prev]");
        const next = grove.querySelector("[data-grove-page-next]");
        const status = grove.querySelector("[data-grove-page-status]");
        const paged = shouldPageGrove(grove, matched.length);
        const pageSize = pageSizeForGrove(grove);
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
          pager.dataset.pagePosition = totalPages <= 1 ? "single" : page <= 0 ? "first" : page >= totalPages - 1 ? "last" : "middle";
        }
        if (prev) {
          prev.disabled = !paged || page <= 0;
          prev.title = page <= 0 ? "已经是第一页" : `上一页：${Math.max(1, start - pageSize + 1)}-${start}`;
        }
        if (next) {
          next.disabled = !paged || page >= totalPages - 1;
          next.title = page >= totalPages - 1 ? "已经是最后一页" : `下一页：${end + 1}-${Math.min(end + pageSize, matched.length)}`;
        }
        if (status) {
          const pageLabel = paged ? `${start + 1}-${end} / ${matched.length}` : `共 ${matched.length}`;
          status.textContent = `第 ${page + 1}/${totalPages} 页 · ${pageLabel}`;
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
      const pageSize = pageSizeForGrove(grove);
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
      return `/static/forest/generated/${prefix}${tile.asset}.png?v=20260528-forest-frame`;
    };

    const growthStateLabel = (tile) => tile?.plant_tier_label || (tile?.summarized ? "已生成" : "树苗");

    const growthSpritePath = (tile, step) => {
      const prefix = step.plant_stage === "tree" ? "tree-" : "sapling-";
      return `/static/forest/generated/${prefix}${tile.asset}.png?v=20260528-forest-frame`;
    };

    const paperPath = (tile, hash = "") => `${tile.detail_url || `/papers/${tile.arxiv_id}`}${hash}`;

    const hasInsight = (tile, key) => {
      const status = tile?.summary_status || "";
      if (key === "translation") {
        return Boolean(tile?.has_translation_record) || status.includes("摘要翻译");
      }
      if (key === "summary") {
        return Boolean(tile?.has_summary_record) || status.includes("单篇总结");
      }
      if (key === "full_text") {
        return Boolean(tile?.has_full_text_record) || status.includes("全文总结");
      }
      return false;
    };

    const updateInsightLink = (link, tile, key, hash) => {
      if (!link) return;
      const ready = hasInsight(tile, key);
      link.href = paperPath(tile, hash);
      link.classList.toggle("is-ready", ready);
      link.classList.toggle("is-pending", !ready);
      link.setAttribute("aria-label", `${link.textContent.trim()}${ready ? "已生成" : "待生成"}`);
    };

    const fallbackGrowthSteps = (tile) => {
      const steps = [
        {
          key: "metadata",
          label: "树苗",
          detail: "元数据",
          rank: 0,
          plant_stage: "sapling",
          plant_tier: "sapling",
        },
      ];
      if (tile.summarized || Number(tile.generated_ai_count || 0) > 0) {
        const tier = tile.plant_tier || "young";
        steps.push({
          key: "grown",
          label: tile.plant_tier_label || "幼树",
          detail: tile.summary_status || "已生成智能内容",
          rank: Number(tile.generated_ai_count || 1),
          plant_stage: tier === "sapling" ? "sapling" : "tree",
          plant_tier: tier,
        });
      }
      return steps;
    };

    const normalizedGrowthSteps = (tile) => {
      const steps =
        Array.isArray(tile.growth_steps) && tile.growth_steps.length ? tile.growth_steps : fallbackGrowthSteps(tile);
      return steps.map((step) => ({
        key: step.key || "metadata",
        label: step.label || "树苗",
        detail: step.detail || "元数据",
        rank: Number(step.rank || 0),
        plant_stage:
          step.plant_stage === "tree" || ["ancient", "mature", "young", "tree"].includes(step.plant_tier)
            ? "tree"
            : "sapling",
        plant_tier: ["ancient", "mature", "young", "tree", "sapling"].includes(step.plant_tier)
          ? step.plant_tier
          : step.plant_stage === "tree" || Number(step.rank || 0) > 0
            ? "young"
            : "sapling",
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
      nodes.growthDiary.setAttribute("aria-label", `论文成长进度：${growthStateLabel(tile)}`);

      const label = document.createElement("span");
      label.className = "forest-growth-label";
      label.textContent = "成长";
      nodes.growthDiary.append(label);

      const rail = document.createElement("span");
      rail.className = "forest-growth-rail";
      rail.setAttribute("aria-hidden", "true");
      nodes.growthDiary.append(rail);

      steps.forEach((step, index) => {
        const item = document.createElement("span");
        item.className = `forest-growth-step is-complete ${index === steps.length - 1 ? "is-current" : ""} is-${step.plant_stage}-step is-${step.plant_tier}-tier`;
        item.dataset.growthStep = step.key;
        item.dataset.growthRank = String(step.rank);

        const icon = document.createElement("i");
        icon.className = "forest-growth-icon";
        icon.setAttribute("aria-hidden", "true");
        const image = document.createElement("img");
        image.src = growthSpritePath(tile, step);
        image.alt = "";
        icon.append(image);

        const stepLabel = document.createElement("b");
        stepLabel.textContent = step.label;
        const detail = document.createElement("small");
        detail.textContent = step.detail;

        item.append(icon, stepLabel, detail);
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
        inspector.classList.add(tile.plant_stage === "tree" || tile.has_generated_ai ? "is-tree-stage" : "is-sapling-stage");
        void inspector.offsetWidth;
        inspector.classList.add("is-updating");
        window.setTimeout(() => inspector.classList.remove("is-updating"), 380);
      }
      if (nodes.kindEn) {
        nodes.kindEn.textContent = tile.kind_label || tile.primary_category || "";
      } else if (nodes.kind) {
        nodes.kind.textContent = tile.kind_label || tile.primary_category || "";
      }
      if (nodes.kindZh) nodes.kindZh.textContent = tile.kind_label_zh || "";
      setRichText(nodes.title, tile.title_html, tile.title_display || tile.title || "");
      const translatedTitle = text(tile.translated_title);
      const translatedAbstract = text(tile.translated_abstract);
      if (nodes.titleTranslation) {
        setRichText(nodes.titleTranslation, tile.translated_title_html, translatedTitle);
        nodes.titleTranslation.hidden = !translatedTitle;
      }
      if (nodes.paper) nodes.paper.href = tile.detail_url || "#";
      if (nodes.favoriteForm && tile.arxiv_id) {
        nodes.favoriteForm.action = `/papers/${tile.arxiv_id}/favorite`;
        nodes.favoriteForm.dataset.arxivId = tile.arxiv_id;
        nodes.favoriteForm.dataset.favorite = tile.favorite ? "true" : "false";
      }
      setFavoriteButtonState(nodes.favoriteButton, Boolean(tile.favorite));
      if (nodes.score) nodes.score.textContent = `相关性 ${tile.score_display || tile.score || 0}`;
      if (nodes.rarity) nodes.rarity.textContent = tile.rarity_label || "";
      if (nodes.growth) nodes.growth.textContent = growthStateLabel(tile);
      if (nodes.category) nodes.category.textContent = tile.primary_category || "";
      if (nodes.authors) nodes.authors.textContent = text(tile.authors_display || tile.authors, "作者未记录");
      if (nodes.arxiv) {
        nodes.arxiv.href = tile.abs_url || "#";
        nodes.arxiv.textContent = tile.arxiv_id || "arXiv";
      }
      if (nodes.keywords) nodes.keywords.textContent = text(tile.matched_terms_display || tile.matched_keywords, "暂无关键词");
      if (nodes.categories) nodes.categories.textContent = text(tile.categories_display || tile.categories, tile.primary_category || "-");
      if (nodes.status) nodes.status.textContent = tile.summary_status || "只有元数据";
      setRichText(nodes.abstract, tile.abstract_html, tile.abstract || "");
      const hasTranslation = Boolean(translatedTitle || translatedAbstract);
      if (nodes.translationCard) {
        nodes.translationCard.hidden = !hasTranslation;
      }
      if (nodes.translatedTitle) {
        setRichText(nodes.translatedTitle, tile.translated_title_html, translatedTitle);
        nodes.translatedTitle.hidden = !translatedTitle;
      }
      if (nodes.translatedAbstract) {
        setRichText(nodes.translatedAbstract, tile.translated_abstract_html, translatedAbstract);
      }
      renderGrowthDiary(tile);
      if (nodes.sprite && tile.asset) {
        nodes.sprite.src = spritePath(tile);
      }
      if (nodes.aiStatus) nodes.aiStatus.textContent = tile.summary_status || "只有元数据";
      if (nodes.aiForm && tile.arxiv_id) {
        const refresh = tile.growth === "full_text";
        const submitLabel = refresh ? "刷新三项" : "生成三项";
        nodes.aiForm.action = `/papers/${tile.arxiv_id}/summarize-all`;
        nodes.aiForm.dataset.summaryJobUrl = `/summary-jobs/papers/${tile.arxiv_id}/all`;
        nodes.aiForm.dataset.runningLabel = refresh ? "刷新中" : "生成中";
        nodes.aiForm.dataset.completedLabel = refresh ? "已刷新" : "已生成";
        if (nodes.aiForce) nodes.aiForce.value = refresh ? "true" : "false";
        if (nodes.aiSubmit) {
          nodes.aiSubmit.textContent = submitLabel;
          nodes.aiSubmit.dataset.defaultLabel = submitLabel;
          nodes.aiSubmit.dataset.completedLabel = refresh ? "已刷新" : "已生成";
        }
        nodes.aiForm.dispatchEvent(new CustomEvent("summary-job-url-change"));
      }
      updateInsightLink(nodes.translationLink, tile, "translation", "#abstract-translation");
      updateInsightLink(nodes.translationLinkSecondary, tile, "translation", "#abstract-translation");
      updateInsightLink(nodes.summaryLink, tile, "summary", "#abstract-summary");
      updateInsightLink(nodes.fullLink, tile, "full_text", "#full-text-summary");
      if (nodes.plant) {
        const plantClasses = [
          "forest-inspector-plant",
          `tree-${tile.visual_kind || tile.kind || "other"}`,
          `land-${tile.land || "grass"}`,
          `is-${tile.plant_stage || "sapling"}-plant`,
          `is-${tile.plant_tier || tile.plant_stage || "sapling"}-tier`,
        ];
        if (tile.high_relevance) {
          plantClasses.push("is-high-relevance-plant");
        }
        if (tile.growth === "full_text") {
          plantClasses.push("is-full-text-plant");
        }
        nodes.plant.className = plantClasses.join(" ");
        nodes.plant.dataset.growth = tile.growth || "";
        nodes.plant.style.setProperty("--sprite-contact-shift", `${Number(tile.sprite_contact_shift || 0)}%`);
      }
    };

    const titleTooltip = document.createElement("div");
    titleTooltip.className = "forest-hover-title";
    titleTooltip.setAttribute("role", "tooltip");
    titleTooltip.hidden = true;
    const titleTooltipMeta = document.createElement("span");
    const titleTooltipText = document.createElement("strong");
    titleTooltip.append(titleTooltipMeta, titleTooltipText);
    document.body.append(titleTooltip);

    const positionTitleTooltip = (button) => {
      if (!button || titleTooltip.hidden) return;
      const rect = button.getBoundingClientRect();
      const gap = 14;
      const margin = 10;
      const width = titleTooltip.offsetWidth || 280;
      const height = titleTooltip.offsetHeight || 58;
      let placement = "right";
      let left = rect.right + gap;
      if (left + width > window.innerWidth - margin) {
        placement = "left";
        left = rect.left - gap - width;
      }
      if (left < margin) {
        placement = "bottom";
        const centerX = rect.left + rect.width / 2;
        left = Math.max(margin, Math.min(window.innerWidth - margin - width, centerX - width / 2));
      }
      const midY = rect.top + rect.height / 2 - height / 2;
      const top = Math.max(margin, Math.min(window.innerHeight - margin - height, midY));
      titleTooltip.dataset.placement = placement;
      titleTooltip.style.left = `${Math.round(left)}px`;
      titleTooltip.style.top = `${Math.round(top)}px`;
    };

    const showTitleTooltip = (button) => {
      const tile = tileById.get(button.dataset.arxivId);
      const paperTitle = tile?.title_display || button.dataset.forestTooltipTitle || tile?.title || button.getAttribute("aria-label") || "";
      if (!paperTitle) return;
      const topicLabel = [tile?.kind_label, tile?.kind_label_zh].filter(Boolean).join(" / ");
      titleTooltipMeta.textContent = [topicLabel, growthStateLabel(tile)].filter(Boolean).join(" · ");
      titleTooltipText.textContent = paperTitle;
      titleTooltip.hidden = false;
      titleTooltip.classList.add("is-visible");
      positionTitleTooltip(button);
    };

    const hideTitleTooltip = () => {
      titleTooltip.classList.remove("is-visible");
      titleTooltip.hidden = true;
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

    const groveLayoutTierForCount = (count) => {
      if (count <= 1) return "single";
      if (count <= 6) return "compact";
      if (count >= 12 && !isExpandedGroveLayout()) return "field";
      if (count < 28 && !isExpandedGroveLayout()) return "wide";
      return "field";
    };

    const clampNumber = (value, min, max) => Math.max(min, Math.min(max, value));

    const targetRowsForGrove = (count, tier) => {
      if (tier === "single") return 1;
      if (tier === "compact") return count <= 3 ? 1 : 2;
      if (tier === "wide") return count <= 10 ? 2 : 3;
      if (count >= 30) return 3;
      return 3;
    };

    const tileWidthForGrove = (count, tier) => {
      if (count >= 48) return 72;
      if (count >= 28) return 82;
      if (count >= 18) return 88;
      if (tier === "field") return 96;
      if (tier === "wide") return count >= 16 ? 98 : 106;
      if (tier === "compact") return count <= 3 ? 116 : 108;
      return 124;
    };

    const tileHeightForGrove = (count, tier) => {
      if (count >= 48) return 74;
      if (count >= 28) return 84;
      if (count >= 18) return 90;
      if (tier === "single") return 126;
      if (tier === "compact") return count <= 3 ? 124 : 112;
      if (tier === "wide") return count >= 12 ? 102 : 110;
      return 104;
    };

    const updateGroveArrangements = () => {
      groves.forEach((grove) => {
        const trees = grove.querySelector(".forest-grove-trees");
        if (!trees || grove.hidden) {
          if (trees) {
            delete trees.dataset.groveColumns;
            delete trees.dataset.groveRows;
            trees.style.removeProperty("--grove-tile-width");
            trees.style.removeProperty("--grove-tile-height");
            trees.style.removeProperty("grid-template-columns");
          }
          return;
        }

        const count =
          Number.parseInt(grove.dataset.layoutCount || "", 10) ||
          matchedGroveTiles(grove).filter((button) => button.dataset.pageHidden !== "true" && !button.hidden).length ||
          0;
        if (!count) return;

        const tier = grove.dataset.layoutTier || groveLayoutTierForCount(count);
        const tileWidth = tileWidthForGrove(count, tier);
        const tileHeight = tileHeightForGrove(count, tier);
        trees.style.setProperty("--grove-tile-width", `${tileWidth}px`);
        trees.style.setProperty("--grove-tile-height", `${tileHeight}px`);

        const style = window.getComputedStyle(trees);
        const columnGap = Number.parseFloat(style.columnGap) || 0;
        const paddingX = (Number.parseFloat(style.paddingLeft) || 0) + (Number.parseFloat(style.paddingRight) || 0);
        const availableWidth = Math.max(tileWidth, trees.clientWidth - paddingX);
        const maxColumns = Math.max(1, Math.floor((availableWidth + columnGap) / (tileWidth + columnGap)));
        const rows = targetRowsForGrove(count, tier);
        let columns = Math.ceil(count / rows);

        if (tier === "field" && count >= 28 && maxColumns >= 8) {
          columns = Math.max(columns, Math.ceil(count / 3));
        }
        if (tier === "compact") {
          columns = count <= 3 ? count : Math.ceil(count / 2);
        }
        if (tier === "single") {
          columns = 1;
        }

        columns = clampNumber(columns, 1, Math.min(maxColumns, count));
        const arrangedRows = Math.ceil(count / columns);
        trees.dataset.groveColumns = String(columns);
        trees.dataset.groveRows = String(arrangedRows);
        trees.style.gridTemplateColumns = `repeat(${columns}, minmax(var(--grove-tile-width), var(--grove-tile-width)))`;
        grove.style.setProperty("--grove-arranged-columns", String(columns));
        grove.style.setProperty("--grove-arranged-rows", String(arrangedRows));
      });
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
        const totalButtonsForGrove = groveTiles(grove).filter((button) =>
          matchesActiveFilters(button, { ignoreOverflow: true })
        );
        const previewButtonsForGrove = matchedGroveTiles(grove).filter(
          (button) => button.dataset.pageHidden !== "true" && !button.hidden
        );
        const total = totalButtonsForGrove.length;
        const visible = previewButtonsForGrove.length;
        const summarized = totalButtonsForGrove.filter((button) => button.dataset.summarized === "true").length;
        const size = groveSizeForCount(total);
        const tier = groveLayoutTierForCount(total);
        const countLabel = grove.querySelector("[data-grove-count-label]");
        const growthLabel = grove.querySelector("[data-grove-growth-label]");

        grove.hidden = total === 0;
        grove.classList.remove(
          "is-canopy-grove",
          "is-large-grove",
          "is-medium-grove",
          "is-small-grove",
          "is-major",
          "is-minor",
          "is-field-grove",
          "is-wide-grove",
          "is-compact-grove",
          "is-single-grove"
        );
        grove.classList.add(`is-${size}-grove`, total >= 48 ? "is-major" : "is-minor");
        grove.classList.add(`is-${tier}-grove`);
        grove.dataset.layoutTier = tier;
        grove.dataset.layoutCount = String(total);
        if (countLabel) {
          countLabel.textContent = visible < total ? `${visible}/${total}` : String(total);
        }
        if (growthLabel) {
          growthLabel.textContent = `${summarized} 成长 / ${Math.max(total - summarized, 0)} 树苗`;
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
      updateFilterSelects();
      keepActiveFiltersInView();
      updateActiveFilterLabels();
      if (nodes.filterVisible) {
        nodes.filterVisible.textContent = String(visible);
      }
      if (nodes.filterTotal) {
        nodes.filterTotal.textContent = String(buttons.length);
      }
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
      applyGroveLayout();
      updateGroveArrangements();
      applyDensity(visible);
      updateGrovePagination();
      firstVisible = firstVisibleTileInGrove("");
      updateMoreButtons();
      updateOverviewPreviewLimits();
      applyGroveLayout();
      updateGroveArrangements();
      updateGroveTreeHeights();
      if (empty) {
        empty.hidden = visible > 0;
      }
      if (selectFirst && firstVisible && !selectedVisibleButton()) {
        setSelected(firstVisible);
        renderDetails(tileById.get(firstVisible.dataset.arxivId));
      }
      if (grid && (focusedGrove || activeFilters.topic !== "all" || activeFilters.status !== "all")) {
        grid.scrollTo({ top: 0, behavior: "smooth" });
      }
    };

    buttons.forEach((button) => {
      button.addEventListener("mouseenter", () => showTitleTooltip(button));
      button.addEventListener("focus", () => showTitleTooltip(button));
      button.addEventListener("mouseleave", hideTitleTooltip);
      button.addEventListener("blur", hideTitleTooltip);
      button.addEventListener("click", () => {
        hideTitleTooltip();
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
        syncFilterStateToUrl();
        applyFilterState();
      });
    });

    filterSelects.forEach((select) => {
      select.addEventListener("change", () => {
        const group = select.dataset.forestFilterSelect;
        if (!group) return;
        activeFilters[group] = select.value || "all";
        grovePages.clear();
        if (group === "topic" && focusedGrove && (activeFilters.topic === "all" || activeFilters.topic !== focusedGrove)) {
          setFocusedGrove("");
        }
        syncFilterStateToUrl();
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

    document.addEventListener("paper-favorite-change", (event) => {
      const arxivId = event.detail?.arxivId || "";
      if (!arxivId || !tileById.has(arxivId)) return;
      const tile = tileById.get(arxivId);
      tile.favorite = Boolean(event.detail.favorite);
      const selected = buttons.find((button) => button.classList.contains("is-selected"));
      if (selected?.dataset.arxivId === arxivId) {
        renderDetails(tile);
      }
    });

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
      hideTitleTooltip();
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => applyFilterState(false), 120);
    });

    grid.addEventListener("scroll", hideTitleTooltip, { passive: true });

    applyUrlFilterState();
    syncFilterStateToUrl();
    const initialButton =
      buttons.find((button) => button.classList.contains("is-selected") && matchesActiveFilters(button, { ignoreOverflow: true })) ||
      buttons.find((button) => matchesActiveFilters(button, { ignoreOverflow: true })) ||
      buttons[0];
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
  setupFavoriteToggles();
  setupSettingsPresets();
  setupFigureLightbox();
  setupForest();
})();
