(() => {
  const numberText = (value) => String(value || 0);

  const setProgress = (panel, nodes, job) => {
    const percent = Math.max(0, Math.min(100, Number(job.percent || 0)));
    panel.hidden = false;
    document.querySelectorAll(`[data-progress-nav='${panel.id}']`).forEach((link) => {
      link.hidden = false;
    });
    panel.dataset.status = job.status || "running";
    nodes.fill.style.width = `${percent}%`;
    nodes.percent.textContent = job.status === "failed" ? "失败" : `${Math.round(percent)}%`;
    nodes.message.textContent = job.message || "任务正在执行。";
    nodes.stage.textContent = job.stage_label || "正在处理";
  };

  const setupFetchProgress = () => {
    const form = document.querySelector("[data-progress-fetch='true']");
    if (!form) {
      return;
    }

    const panel = document.getElementById("fetch-progress");
    const button = document.getElementById("fetch-button");
    const nodes = {
      fill: document.getElementById("fetch-progress-fill"),
      percent: document.getElementById("fetch-progress-percent"),
      message: document.getElementById("fetch-progress-message"),
      stage: document.getElementById("fetch-progress-stage"),
      fetched: document.getElementById("fetch-progress-fetched"),
      saved: document.getElementById("fetch-progress-saved"),
      skipped: document.getElementById("fetch-progress-skipped"),
    };

    const applyFetchProgress = (job) => {
      setProgress(panel, nodes, job);
      nodes.fetched.textContent = numberText(job.fetched);
      nodes.saved.textContent = numberText(job.saved);
      nodes.skipped.textContent = numberText((job.skipped_no_keyword || 0) + (job.skipped_excluded || 0));
    };

    const handleError = (error) => {
      applyFetchProgress({
        status: "failed",
        stage_label: "抓取失败",
        message: error.message || "抓取失败。",
        percent: 100,
      });
      button.disabled = false;
      button.textContent = "重新抓取";
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
          const url = `/?day=${encodeURIComponent(day)}&message=${encodeURIComponent("抓取完成，论文列表已刷新。")}`;
          window.location.assign(url);
        }, 900);
        return;
      }

      if (job.status === "failed" || job.status === "not_found") {
        button.disabled = false;
        button.textContent = "重新抓取";
        nodes.message.textContent = job.error || job.message || "抓取失败。";
        return;
      }

      window.setTimeout(() => poll(jobId, day).catch(handleError), 800);
    };

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const day = data.get("day") || "";
      button.disabled = true;
      button.textContent = "抓取中...";
      applyFetchProgress({
        status: "queued",
        stage_label: "等待开始",
        message: "任务已创建，正在连接 arXiv。",
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
  };

  const setupSummaryProgress = () => {
    const forms = document.querySelectorAll("[data-progress-summary='true']");
    if (!forms.length) {
      return;
    }

    forms.forEach((form) => {
      const panel = document.getElementById(form.dataset.progressPanel || "summary-progress");
      if (!panel) {
        return;
      }
      const button = form.querySelector("button[type='submit']");
      const nodes = {
        fill: panel.querySelector("[data-progress-fill]") || document.getElementById("summary-progress-fill"),
        percent: panel.querySelector("[data-progress-percent]") || document.getElementById("summary-progress-percent"),
        message: panel.querySelector("[data-progress-message]") || document.getElementById("summary-progress-message"),
        stage: panel.querySelector("[data-progress-stage]") || document.getElementById("summary-progress-stage"),
        kind: panel.querySelector("[data-progress-kind]") || document.getElementById("summary-progress-kind"),
        model: panel.querySelector("[data-progress-model]") || document.getElementById("summary-progress-model"),
        title: panel.querySelector("[data-progress-title]") || document.getElementById("summary-progress-title"),
      };

      const applySummaryProgress = (job) => {
        setProgress(panel, nodes, job);
        if (job.label && nodes.title) {
          nodes.title.textContent = `正在生成${job.label}`;
        }
        if (job.label && nodes.kind) {
          nodes.kind.textContent = job.label;
        }
        if (job.model && nodes.model) {
          nodes.model.textContent = job.model;
        }
      };

      const handleError = (error) => {
        applySummaryProgress({
          status: "failed",
          stage_label: "生成失败",
          message: error.message || "生成失败。",
          percent: 100,
        });
        button.disabled = false;
        button.textContent = "重新生成";
      };

      const poll = async (jobId) => {
        const response = await fetch(`/summary-jobs/${jobId}`, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error("无法读取生成进度。");
        }
        const job = await response.json();
        applySummaryProgress(job);

        if (job.status === "completed") {
          window.setTimeout(() => {
            const target = job.redirect_url || window.location.pathname;
            const joiner = target.includes("?") ? "&" : "?";
            window.location.assign(`${target}${joiner}message=${encodeURIComponent("总结已生成，页面已刷新。")}`);
          }, 900);
          return;
        }

        if (job.status === "failed" || job.status === "not_found") {
          button.disabled = false;
          button.textContent = "重新生成";
          nodes.message.textContent = job.error || job.message || "生成失败。";
          return;
        }

        window.setTimeout(() => poll(jobId).catch(handleError), 850);
      };

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(form);
        const jobUrl = form.dataset.summaryJobUrl;
        button.disabled = true;
        button.textContent = form.dataset.runningLabel || "生成中...";
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
          await poll(payload.job_id);
        } catch (error) {
          handleError(error);
        }
      });
    });
  };

  setupFetchProgress();
  setupSummaryProgress();
})();
