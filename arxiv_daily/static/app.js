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
        const fetched = numberText(job.fetched);
        const network = numberText(job.network_requests);
        const cached = numberText(job.cached_pages);
        renderInlineStatus(statusNode, `${job.stage_label || "正在抓取"} · 读取 ${fetched} · 保存 ${saved} · API ${network} · 缓存 ${cached}`, job);
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
      daily: document.querySelector("[name='max_tokens_daily']"),
      topN: document.querySelector("[name='daily_top_n']"),
      abstractChars: document.querySelector("[name='daily_abstract_chars']"),
      fullTextChars: document.querySelector("[name='full_text_max_chars']"),
      figureLimit: document.querySelector("[name='full_text_figure_limit']"),
    };

    presetButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (fields.single) fields.single.value = button.dataset.single || fields.single.value;
        if (fields.fullText) fields.fullText.value = button.dataset.fullText || fields.fullText.value;
        if (fields.daily) fields.daily.value = button.dataset.daily || fields.daily.value;
        if (fields.topN) fields.topN.value = button.dataset.topN || fields.topN.value;
        if (fields.abstractChars) fields.abstractChars.value = button.dataset.abstractChars || fields.abstractChars.value;
        if (fields.fullTextChars) fields.fullTextChars.value = button.dataset.fullTextChars || fields.fullTextChars.value;
        if (fields.figureLimit) fields.figureLimit.value = button.dataset.figureLimit || fields.figureLimit.value;

        presetButtons.forEach((item) => item.classList.remove("is-applied"));
        button.classList.add("is-applied");
      });
    });
  };

  const setupDailyForest = () => {
    const board = document.querySelector("[data-daily-forest]");
    if (!board) {
      return;
    }

    const buttons = Array.from(board.querySelectorAll("[data-forest-branch]"));
    const panels = Array.from(board.querySelectorAll("[data-forest-panel]"));
    const groves = Array.from(board.querySelectorAll("[data-forest-grove]"));
    const trees = Array.from(board.querySelectorAll("[data-forest-tree]"));
    const plotTriggers = Array.from(board.querySelectorAll("[data-forest-plot-trigger]"));
    const unifiedField = board.querySelector("[data-unified-field]");
    const unifiedGrid = board.querySelector("[data-unified-grid]");
    const fieldSizeButtons = Array.from(board.querySelectorAll("[data-field-size-control]"));
    const fieldSizeLabel = board.querySelector("[data-field-size-label]");
    const inspector = board.querySelector("[data-forest-inspector]");
    const inspectorFields = inspector ? {
      eyebrow: inspector.querySelector("[data-inspector-eyebrow]"),
      title: inspector.querySelector("[data-inspector-title]"),
      reason: inspector.querySelector("[data-inspector-reason]"),
      score: inspector.querySelector("[data-inspector-score]"),
      meta: inspector.querySelector("[data-inspector-meta]"),
      land: inspector.querySelector("[data-inspector-land]"),
      link: inspector.querySelector("[data-inspector-link]"),
    } : {};
    if (!buttons.length || !panels.length) {
      return;
    }

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const clusterGridPositions = (count, size) => {
      if (count <= 0) {
        return [];
      }
      if (count === 1) {
        const center = Math.floor((size + 1) / 2);
        return [{ row: center, column: center }];
      }

      const center = (size + 1) / 2;
      const candidates = [];
      for (let row = 1; row <= size; row += 1) {
        for (let column = 1; column <= size; column += 1) {
          const vertical = Math.abs(row - center);
          const horizontal = Math.abs(column - center);
          const organicOffset = ((row * 17 + column * 31) % 11) / 100;
          const lowerCanopyBias = (row - center) * -0.02;
          const score = (
            Math.max(vertical * 1.02, horizontal * 0.9)
            + vertical * 0.18
            + horizontal * 0.08
            + organicOffset
            + lowerCanopyBias
          );
          candidates.push({ row, column, score });
        }
      }

      return candidates
        .sort((a, b) => a.score - b.score || a.row - b.row || a.column - b.column)
        .slice(0, count)
        .sort((a, b) => a.row - b.row || a.column - b.column);
    };

    const layoutUnifiedTrees = (size) => {
      if (!trees.length) {
        return;
      }
      const positions = clusterGridPositions(trees.length, size);
      const center = (size + 1) / 2;
      trees.forEach((tree, index) => {
        const position = positions[index];
        if (!position) {
          return;
        }
        const depth = 0.82 + (position.row / Math.max(1, size)) * 0.24;
        const baseShiftY = Number(tree.dataset.treeBaseY || 0);
        tree.style.gridRow = String(position.row);
        tree.style.gridColumn = String(position.column);
        tree.style.setProperty("--scene-scale", depth.toFixed(3));
        tree.style.setProperty("--scene-z", String(20 + position.row));
        tree.style.setProperty("--tile-z", String(30 + position.row * 4));
        tree.style.setProperty("--tree-z", String(120 + position.row * 4));
        tree.style.setProperty("--tree-shift-y", `${baseShiftY + Math.round((position.row - center) * 1.4)}px`);
      });
    };

    const setFieldSize = (value) => {
      const size = Math.max(4, Math.min(18, Number(value) || 6));
      if (unifiedField) {
        unifiedField.style.setProperty("--field-size", String(size));
        unifiedField.dataset.fieldSize = String(size);
      }
      if (unifiedGrid) {
        unifiedGrid.style.setProperty("--field-size", String(size));
      }
      if (fieldSizeLabel) {
        fieldSizeLabel.textContent = `${size}x${size}`;
      }
      fieldSizeButtons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.fieldSizeControl === String(value));
      });
      layoutUnifiedTrees(size);
    };

    const renderInspector = (tree) => {
      if (!inspector) {
        return;
      }
      const title = tree.dataset.paperTitle || "未命名论文";
      const meta = tree.dataset.paperMeta || "";
      const score = tree.dataset.paperScore || "";
      const rank = tree.dataset.paperRank || "";
      const reason = tree.dataset.paperReason || "";
      const plot = tree.dataset.paperPlot || "";
      const shape = tree.dataset.paperShapeLabel || tree.dataset.paperShape || "";
      const land = tree.dataset.paperLandLabel || tree.dataset.paperLand || "";
      const url = tree.dataset.paperUrl || "#";

      trees.forEach((item) => item.classList.toggle("is-paper-active", item === tree));
      inspector.dataset.state = "paper";
      if (inspectorFields.eyebrow) {
        inspectorFields.eyebrow.textContent = [plot, rank].filter(Boolean).join(" · ");
      }
      if (inspectorFields.title) {
        inspectorFields.title.textContent = title;
      }
      if (inspectorFields.reason) {
        inspectorFields.reason.textContent = reason;
      }
      if (inspectorFields.score) {
        inspectorFields.score.textContent = score;
      }
      if (inspectorFields.meta) {
        inspectorFields.meta.textContent = meta;
      }
      if (inspectorFields.land) {
        inspectorFields.land.textContent = [shape, land].filter(Boolean).join(" · ") || "树种/地块 -";
      }
      if (inspectorFields.link) {
        inspectorFields.link.href = url;
        inspectorFields.link.textContent = "进入论文详情";
        inspectorFields.link.removeAttribute("aria-disabled");
      }
    };

    const activateBranch = (branchId, focusButton = false, shouldScroll = false) => {
      const allActive = branchId === "all";
      let activeGrove = null;
      buttons.forEach((button) => {
        const active = button.dataset.forestBranch === branchId;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-expanded", active ? "true" : "false");
        button.tabIndex = active ? 0 : -1;
        if (active && focusButton) {
          button.focus();
        }
      });

      plotTriggers.forEach((trigger) => {
        const active = trigger.dataset.forestPlotTrigger === branchId;
        trigger.classList.toggle("is-active", active);
        trigger.setAttribute("aria-expanded", active ? "true" : "false");
      });

      panels.forEach((panel) => {
        const active = panel.dataset.forestPanel === branchId;
        panel.hidden = !active;
        panel.classList.toggle("is-active", active);
      });

      groves.forEach((grove) => {
        const active = allActive || grove.dataset.forestGrove === branchId;
        grove.classList.toggle("is-muted", !active);
        grove.classList.toggle("is-spotlight", !allActive && active);
        if (!allActive && active) {
          activeGrove = grove;
        }
      });

      trees.forEach((tree) => {
        const active = allActive || tree.dataset.forestTree === branchId;
        tree.classList.toggle("is-muted", !active);
      });

      board.dataset.activeBranch = branchId;
      board.classList.remove("is-leaf-sweep");
      void board.offsetWidth;
      board.classList.add("is-leaf-sweep");
      window.setTimeout(() => {
        board.classList.remove("is-leaf-sweep");
      }, 900);

      if (shouldScroll && activeGrove) {
        window.setTimeout(() => {
          activeGrove.scrollIntoView({
            behavior: prefersReducedMotion ? "auto" : "smooth",
            block: "center",
          });
        }, 80);
      }
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        activateBranch(button.dataset.forestBranch || "", false, true);
      });
      button.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
          return;
        }
        event.preventDefault();
        const currentIndex = buttons.indexOf(button);
        let nextIndex = currentIndex;
        if (event.key === "Home") {
          nextIndex = 0;
        } else if (event.key === "End") {
          nextIndex = buttons.length - 1;
        } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;
        } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          nextIndex = (currentIndex + 1) % buttons.length;
        }
        activateBranch(buttons[nextIndex]?.dataset.forestBranch || "", true, true);
      });
    });

    plotTriggers.forEach((trigger) => {
      trigger.addEventListener("click", () => {
        activateBranch(trigger.dataset.forestPlotTrigger || "", false, false);
      });
    });

    fieldSizeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setFieldSize(button.dataset.fieldSizeControl);
      });
    });

    if (fieldSizeButtons.length) {
      const activeSizeButton = fieldSizeButtons.find((button) => button.classList.contains("is-active")) || fieldSizeButtons[0];
      setFieldSize(activeSizeButton.dataset.fieldSizeControl);
    }

    const activeButton = buttons.find((button) => button.classList.contains("is-active")) || buttons[0];
    activateBranch(activeButton.dataset.forestBranch || "");

    trees.forEach((tree) => {
      tree.addEventListener("pointerenter", () => {
        tree.classList.add("is-rustling");
        renderInspector(tree);
      });
      tree.addEventListener("focusin", () => {
        renderInspector(tree);
      });
      tree.addEventListener("animationend", (event) => {
        if (event.animationName === "cartoonRustle" || event.animationName === "assetTreeRustle" || event.animationName === "unifiedTreeRustle") {
          tree.classList.remove("is-rustling");
        }
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

  setupFetchProgress();
  setupSummaryProgress();
  setupPaperFilter();
  setupSettingsPresets();
  setupDailyForest();
  setupFigureLightbox();
})();
