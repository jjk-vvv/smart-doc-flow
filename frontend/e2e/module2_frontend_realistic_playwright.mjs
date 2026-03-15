#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const datasetRoot = path.join(projectRoot, "datasets");
const outputRoot = path.join(projectRoot, "backend", "module2", "tools", "generated_tests");
const screenshotRoot = path.join(outputRoot, "screenshots");

const appUrl = process.env.MODULE2_APP_URL || "http://127.0.0.1:3000";
const cacheClearUrl = process.env.MODULE2_CACHE_CLEAR_URL || "http://127.0.0.1:8000/extract/cache/clear";
const rounds = Math.max(5, Number.parseInt(process.env.MODULE2_FRONTEND_ROUNDS || "5", 10) || 5);
const seed = Number(process.env.MODULE2_FRONTEND_SEED || Date.now()) >>> 0;
const singleNonPdfSlaMs = 90_000;
const scenarioMultiCounts = [2, 3, 4, 5, 6];

const ALLOWED_EXT = new Set([
  ".pdf",
  ".doc",
  ".docx",
  ".xlsx",
  ".txt",
  ".md",
  ".png",
  ".jpg",
  ".jpeg",
  ".bmp",
  ".webp",
  ".tif",
  ".tiff",
]);
const NON_PDF_EXT = new Set([
  ".doc",
  ".docx",
  ".xlsx",
  ".txt",
  ".md",
  ".png",
  ".jpg",
  ".jpeg",
  ".bmp",
  ".webp",
  ".tif",
  ".tiff",
]);

function tsTag() {
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${hh}${mi}${ss}`;
}

function mulberry32(v) {
  let t = v >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function randInt(rng, n) {
  return Math.floor(rng() * n);
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function withRetry(label, attempts, fn) {
  let lastErr = null;
  for (let i = 1; i <= attempts; i += 1) {
    try {
      return await fn(i);
    } catch (err) {
      lastErr = err;
      if (i >= attempts) break;
      // eslint-disable-next-line no-console
      console.warn(`[retry ${i}/${attempts}] ${label}: ${String(err?.message || err || "unknown_error")}`);
      // eslint-disable-next-line no-await-in-loop
      await sleep(800 * i);
    }
  }
  throw lastErr;
}

async function collectFiles(root) {
  const out = [];
  async function walk(dir) {
    let entries = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        // eslint-disable-next-line no-await-in-loop
        await walk(fullPath);
      } else {
        const ext = path.extname(entry.name).toLowerCase();
        if (!ALLOWED_EXT.has(ext)) continue;
        let size = 0;
        try {
          const st = await fs.stat(fullPath);
          size = Number(st.size || 0);
        } catch {
          size = 0;
        }
        out.push({
          path: fullPath,
          name: entry.name,
          ext,
          size,
        });
      }
    }
  }
  await walk(root);
  return out;
}

function pickRandomFiles(rng, files, count) {
  if (count <= 0) return [];
  if (files.length <= count) return [...files];
  const out = [];
  const used = new Set();
  while (out.length < count && used.size < files.length) {
    const idx = randInt(rng, files.length);
    if (used.has(idx)) continue;
    used.add(idx);
    out.push(files[idx]);
  }
  return out;
}

function pickRandomMultiFiles(rng, files, count) {
  const smallPool = files.filter((x) => Number(x.size || 0) > 0 && Number(x.size || 0) <= 2.2 * 1024 * 1024);
  const mediumPool = files.filter((x) => Number(x.size || 0) > 0 && Number(x.size || 0) <= 3.0 * 1024 * 1024);
  const basePool =
    smallPool.length >= count ? smallPool : mediumPool.length >= count ? mediumPool : files;

  const pdfPool = basePool.filter((x) => x.ext === ".pdf");
  const others = basePool.filter((x) => x.ext !== ".pdf");
  const out = [];
  if (pdfPool.length > 0) {
    out.push(...pickRandomFiles(rng, pdfPool, 1));
  }
  if (out.length < count) {
    out.push(...pickRandomFiles(rng, others, count - out.length));
  }
  if (out.length < count) {
    out.push(...pickRandomFiles(rng, basePool, count - out.length));
  }
  return out.slice(0, count);
}

function pickSingleNonPdf(rng, files) {
  const nonPdf = files.filter((x) => NON_PDF_EXT.has(x.ext));
  if (nonPdf.length === 0) return null;
  return nonPdf[randInt(rng, nonPdf.length)] || null;
}

async function clearBackendCache() {
  try {
    const response = await fetch(cacheClearUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!response.ok) {
      return { ok: false, status: response.status, body: await response.text().catch(() => "") };
    }
    const payload = await response.json().catch(() => ({}));
    return { ok: true, status: 200, payload };
  } catch (err) {
    return { ok: false, status: 0, body: String(err || "") };
  }
}

async function openModulePage(page) {
  await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  const alreadyReady = (await fileInput.count().catch(() => 0)) > 0;
  if (alreadyReady) return;

  const deepreadBtn = page.getByRole("button", { name: /\u667a\u80fd\u6587\u6863\u89e3\u6790/ }).first();
  await deepreadBtn.click({ timeout: 20_000 });

  const extractionBtn = page.getByRole("button", { name: /\u975e\u7ed3\u6784\u5316\u6587\u6863\u4fe1\u606f\u9700\u6c42\u6a21\u5757/ }).first();
  await extractionBtn.click({ timeout: 20_000 });
  await fileInput.waitFor({ state: "attached", timeout: 90_000 });
}

async function isModuleReady(page) {
  const fileInput = page.locator('[data-testid="module2-file-input"]');
  const attached = (await fileInput.count().catch(() => 0)) > 0;
  return Boolean(attached);
}

async function pageLooksBlank(page) {
  try {
    return await page.evaluate(() => {
      const body = document.body;
      if (!body) return true;
      const text = (body.innerText || "").trim();
      const childCount = body.querySelectorAll("*").length;
      return childCount < 3 && text.length < 12;
    });
  } catch {
    return true;
  }
}

async function ensureModuleReady(page, attempts = 2) {
  for (let i = 1; i <= attempts; i += 1) {
    if (await isModuleReady(page)) return;
    const blank = await pageLooksBlank(page);
    if (blank) {
      await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
      await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
    }
    await openModulePage(page);
    if (await isModuleReady(page)) return;
    // eslint-disable-next-line no-await-in-loop
    await sleep(500 * i);
  }
  throw new Error("模块页面未就绪，无法定位上传与抽取按钮");
}

async function uploadFiles(page, filePaths) {
  await page.locator('[data-testid="module2-file-input"]').waitFor({ state: "attached", timeout: 15_000 });
  await page.setInputFiles('[data-testid="module2-file-input"]', filePaths);
  await page.waitForTimeout(500);
}

async function parseCountBadge(page) {
  const badge = page.getByTestId("module2-file-count");
  const visible = await badge.isVisible().catch(() => false);
  if (!visible) return 0;
  const raw = (await page.getByTestId("module2-file-count").textContent()) || "";
  const m = raw.match(/(\d+)\s*\/\s*5/);
  return m ? Number(m[1]) : 0;
}

async function readUploadLayoutState(page) {
  try {
    return await page.evaluate(() => {
      const isVisible = (el) => {
        if (!(el instanceof HTMLElement)) return false;
        const style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") <= 0.01) {
          return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 4 && rect.height > 4;
      };
      const leftPanel = document.querySelector('[data-testid="module2-left-panel"]');
      const centerUploader = document.querySelector('[data-testid="module2-center-uploader"]');
      const countRaw = (document.querySelector('[data-testid="module2-file-count"]')?.textContent || "").trim();
      return {
        left_panel_visible: isVisible(leftPanel),
        center_uploader_visible: isVisible(centerUploader),
        count_raw: countRaw,
      };
    });
  } catch (err) {
    return {
      left_panel_visible: false,
      center_uploader_visible: false,
      count_raw: "",
      eval_error: String(err?.message || err || ""),
    };
  }
}

async function readUiState(page) {
  try {
    return await page.evaluate(() => {
      const startBtn = document.querySelector('[data-testid="module2-start-extract"]');
      const addBtn = document.querySelector('[data-testid="module2-add-files"]');
      const countRaw = (document.querySelector('[data-testid="module2-file-count"]')?.textContent || "").trim();
      const info = (document.querySelector('[data-testid="module2-info-message"]')?.textContent || "").trim();
      return {
        href: window.location.href,
        readyState: document.readyState,
        hasStartBtn: Boolean(startBtn),
        hasAddBtn: Boolean(addBtn),
        countRaw,
        info,
      };
    });
  } catch (err) {
    return {
      href: "",
      readyState: "unknown",
      hasStartBtn: false,
      hasAddBtn: false,
      countRaw: "",
      info: "",
      evalError: String(err?.message || err || ""),
    };
  }
}

async function waitStartButtonReady(page) {
  const startBtn = page.getByTestId("module2-start-extract");
  await startBtn.waitFor({ state: "visible", timeout: 35_000 });
  await page.waitForFunction(
    () => {
      const btn = document.querySelector('[data-testid="module2-start-extract"]');
      if (!(btn instanceof HTMLButtonElement)) return false;
      const raw = (document.querySelector('[data-testid="module2-file-count"]')?.textContent || "").trim();
      const m = raw.match(/(\d+)\s*\/\s*5/);
      const selected = Number(m?.[1] || 0);
      return selected > 0 && !btn.disabled;
    },
    null,
    { timeout: 20_000 }
  );
}

async function runExtraction(page) {
  await waitStartButtonReady(page);
  const startTs = Date.now();
  let summarySeenTs = null;
  let batchSeenTs = null;
  let summaryUiSeenTs = null;
  const summaryUiPromise = page
    .waitForFunction(
      () => {
        const text = (document.querySelector('[data-testid="module2-summary-text"]')?.textContent || "").trim();
        if (!text) return false;
        return text !== "暂无摘要。";
      },
      null,
      { timeout: 8_000 }
    )
    .then(() => {
      summaryUiSeenTs = Date.now();
      return true;
    })
    .catch(() => false);
  const summaryPromise = page
    .waitForResponse(
      (res) => res.url().includes("/extract/summarize") && res.request().method() === "POST",
      { timeout: 620_000 }
    )
    .then((res) => {
      summarySeenTs = Date.now();
      return res;
    })
    .catch(() => null);
  const batchPromise = page
    .waitForResponse(
      (res) => res.url().includes("/extract/batch") && res.request().method() === "POST",
      { timeout: 540_000 }
    )
    .then((res) => {
      batchSeenTs = Date.now();
      return res;
    })
    .catch((err) => err);
  await page.getByTestId("module2-start-extract").click({ timeout: 20_000 });
  const batchResp = await batchPromise;
  if (batchResp instanceof Error) {
    const uiState = await readUiState(page);
    throw new Error(
      `batch_request_failed:${String(batchResp.message || batchResp)};ui_state=${JSON.stringify(uiState)}`
    );
  }
  const batchStatus = batchResp.status();
  let batchPayload = null;
  try {
    batchPayload = await batchResp.json();
  } catch {
    batchPayload = null;
  }

  await page.waitForFunction(
    () => {
      const btn = document.querySelector('[data-testid="module2-start-extract"]');
      return !!btn && !(btn instanceof HTMLButtonElement && btn.disabled);
    },
    null,
    { timeout: 540_000 }
  );

  const summaryResp = await summaryPromise;
  const summaryUiImmediateOk = await summaryUiPromise;

  const elapsedMs = Date.now() - startTs;
  const summaryLatencyMs = summarySeenTs == null ? -1 : Math.max(0, summarySeenTs - startTs);
  const summaryUiLatencyMs = summaryUiSeenTs == null ? -1 : Math.max(0, summaryUiSeenTs - startTs);
  const infoMessage = ((await page.getByTestId("module2-info-message").textContent()) || "").trim();
  const traceStatus = ((await page.getByTestId("module2-trace-status").textContent()) || "").trim();
  const summaryText = ((await page.getByTestId("module2-summary-text").textContent()) || "").trim();
  return {
    elapsed_ms: elapsedMs,
    status_code: batchStatus,
    payload: batchPayload,
    info_message: infoMessage,
    trace_status: traceStatus,
    summary_text: summaryText,
    summary_request_seen: Boolean(summaryResp),
    summary_latency_ms: summaryLatencyMs,
    summary_ui_immediate_ok: summaryUiImmediateOk,
    summary_ui_latency_ms: summaryUiLatencyMs,
    summary_before_batch: summarySeenTs != null && batchSeenTs != null ? summarySeenTs <= batchSeenTs : false,
  };
}

async function runAssistant(page, instruction) {
  await page.getByTestId("module2-assistant-input").fill(instruction);
  const assistantPromise = page
    .waitForResponse(
      (res) => res.url().includes("/extract/assistant/query") && res.request().method() === "POST",
      { timeout: 120_000 }
    )
    .catch((err) => err);
  await page.getByTestId("module2-assistant-send").click();
  const response = await assistantPromise;
  if (response instanceof Error) {
    throw response;
  }
  const status = response.status();
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  let answerText = "";
  try {
    answerText = ((await page.getByTestId("module2-assistant-answer").textContent()) || "").trim();
  } catch {
    answerText = "";
  }
  return { status_code: status, payload, answer_text: answerText };
}

async function clearUiCache(page) {
  await page.evaluate(() => {
    try {
      window.localStorage.clear();
      window.sessionStorage.clear();
    } catch {
      // ignore
    }
  });
}

async function runScenario({
  page,
  rng,
  files,
  round,
  kind,
  multiCount,
  screenshotPrefix,
}) {
  await ensureModuleReady(page, 2);

  const selected =
    kind === "single"
      ? [pickSingleNonPdf(rng, files)].filter(Boolean)
      : pickRandomMultiFiles(rng, files, multiCount);
  if (selected.length === 0) {
    throw new Error(`\u573a\u666f ${kind} \u65e0\u53ef\u7528\u6d4b\u8bd5\u6587\u4ef6`);
  }

  const uploadLayoutBefore = await readUploadLayoutState(page);
  const filePaths = selected.map((x) => x.path);
  await uploadFiles(page, filePaths);
  const uploadLayoutAfter = await readUploadLayoutState(page);
  let countBadge = await parseCountBadge(page);
  if (countBadge <= 0) {
    await ensureModuleReady(page, 2);
    await uploadFiles(page, filePaths);
    const uploadLayoutRetry = await readUploadLayoutState(page);
    uploadLayoutAfter.left_panel_visible = uploadLayoutRetry.left_panel_visible;
    uploadLayoutAfter.center_uploader_visible = uploadLayoutRetry.center_uploader_visible;
    uploadLayoutAfter.count_raw = uploadLayoutRetry.count_raw;
    countBadge = await parseCountBadge(page);
  }

  let extraction = null;
  let assistant = null;
  let scenarioError = "";
  const uploadPanelTransitionOk =
    Boolean(uploadLayoutBefore?.center_uploader_visible) &&
    !Boolean(uploadLayoutBefore?.left_panel_visible) &&
    Boolean(uploadLayoutAfter?.left_panel_visible);
  if (countBadge <= 0) {
    const uiState = await readUiState(page);
    scenarioError = `upload_count_badge_missing;ui_state=${JSON.stringify(uiState)}`;
  }
  if (!scenarioError) {
    let extractionErr = null;
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      try {
        extraction = await runExtraction(page);
        extractionErr = null;
        break;
      } catch (err) {
        extractionErr = err;
        const errText = String(err?.message || err || "extract_timeout");
        if (attempt >= 2 || !errText.includes("batch_request_failed")) {
          break;
        }
        await ensureModuleReady(page, 2);
        await uploadFiles(page, filePaths);
      }
    }
    if (extractionErr) {
      const uiState = await readUiState(page);
      scenarioError = `${String(extractionErr?.message || extractionErr || "extract_timeout")};ui_state=${JSON.stringify(uiState)}`;
    }
  }

  if (!scenarioError) {
    const assistantInstruction =
      kind === "single"
        ? "\u8bf7\u63d0\u53d6\u8be5\u6587\u4ef6\u4e2d\u7684\u6838\u5fc3\u7ed3\u8bba\u3001\u5173\u952e\u5b9e\u4f53\u3001\u65f6\u95f4\u4e0e\u6570\u5b57\u6307\u6807\uff0c\u5e76\u7ed9\u51fa\u53ef\u5165\u5e93\u7684\u7ed3\u6784\u5316\u5b57\u6bb5\u3002"
        : "\u8bf7\u6309\u6587\u6863\u5206\u522b\u603b\u7ed3\u91cd\u70b9\uff0c\u5e76\u6c47\u603b\u8de8\u6587\u6863\u5171\u540c\u4e3b\u9898\u3001\u51b2\u7a81\u4fe1\u606f\u548c\u53ef\u843d\u5e93\u5b57\u6bb5\u3002";
    try {
      assistant = await runAssistant(page, assistantInstruction);
    } catch (err) {
      scenarioError = String(err?.message || err || "assistant_timeout");
    }
  }

  const screenshotPath = path.join(
    screenshotRoot,
    `${screenshotPrefix}_round${round}_${kind}.png`
  );
  await page.screenshot({ path: screenshotPath, fullPage: true });

  const documents = Array.isArray(extraction?.payload?.documents) ? extraction.payload.documents : [];
  const docErrors = documents.reduce(
    (acc, doc) => acc + (Array.isArray(doc?.errors) ? doc.errors.length : 0),
    0
  );
  const singleNonPdfSlaOk =
    kind !== "single" || !NON_PDF_EXT.has(path.extname(selected[0].name).toLowerCase())
      ? true
      : Number(extraction?.elapsed_ms || Number.MAX_SAFE_INTEGER) < singleNonPdfSlaMs;
  const elapsedMs = Number(extraction?.elapsed_ms || 0);

  return {
    kind,
    files: selected.map((x) => x.name),
    uploaded_file_count: filePaths.length,
    badge_selected_count: countBadge,
    extract_elapsed_ms: elapsedMs,
    extract_status_code: Number(extraction?.status_code || 0),
    extract_doc_count: documents.length,
    extract_error_count: docErrors,
    summary_text: String(extraction?.summary_text || ""),
    info_message: String(extraction?.info_message || ""),
    trace_status: String(extraction?.trace_status || ""),
    summary_request_seen: Boolean(extraction?.summary_request_seen),
    summary_latency_ms: Number(extraction?.summary_latency_ms ?? -1),
    summary_ui_immediate_ok: Boolean(extraction?.summary_ui_immediate_ok),
    summary_ui_latency_ms: Number(extraction?.summary_ui_latency_ms ?? -1),
    summary_before_batch: Boolean(extraction?.summary_before_batch),
    summary_fast_response_ok:
      Number(extraction?.summary_latency_ms ?? -1) >= 0 &&
      Number(extraction?.summary_latency_ms ?? -1) <= 8_000,
    assistant_status_code: Number(assistant?.status_code || 0),
    assistant_answer: String(assistant?.answer_text || assistant?.payload?.answer || ""),
    assistant_persisted: Boolean(assistant?.payload?.persisted),
    assistant_persisted_rows: Number(assistant?.payload?.persisted_rows || 0),
    single_nonpdf_under_90s: singleNonPdfSlaOk,
    screenshot_path: screenshotPath,
    over_limit_guard_ok: kind !== "multi" || multiCount <= 5 ? true : countBadge <= 5,
    upload_panel_transition_ok: uploadPanelTransitionOk,
    upload_layout_before: uploadLayoutBefore,
    upload_layout_after: uploadLayoutAfter,
    scenario_error: scenarioError,
  };
}

async function main() {
  const files = await collectFiles(datasetRoot);
  if (files.length < 6) {
    throw new Error("\u6d4b\u8bd5\u96c6\u4e2d\u53ef\u7528\u6587\u4ef6\u4e0d\u8db3\uff0c\u81f3\u5c11\u9700\u8981 6 \u4e2a\u53ef\u6d4b\u6587\u4ef6\u3002");
  }

  await fs.mkdir(outputRoot, { recursive: true });
  await fs.mkdir(screenshotRoot, { recursive: true });

  const rng = mulberry32(seed);
  const roundReports = [];
  let browser = null;
  let context = null;
  let page = null;
  const consoleErrors = [];
  const pageErrors = [];
  const serverErrors = [];
  try {
    browser = await chromium.launch({
      headless: process.env.MODULE2_HEADLESS !== "0",
    });
    context = await browser.newContext({
      viewport: { width: 1560, height: 980 },
    });
    page = await context.newPage();
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      consoleErrors.push({
        time: new Date().toISOString(),
        text: msg.text(),
      });
      if (consoleErrors.length > 120) consoleErrors.shift();
    });
    page.on("pageerror", (error) => {
      pageErrors.push({
        time: new Date().toISOString(),
        text: String(error?.message || error || ""),
      });
      if (pageErrors.length > 120) pageErrors.shift();
    });
    page.on("response", (res) => {
      const status = Number(res.status() || 0);
      if (status < 500) return;
      const req = res.request();
      serverErrors.push({
        time: new Date().toISOString(),
        status,
        method: req.method(),
        url: res.url(),
      });
      if (serverErrors.length > 200) serverErrors.shift();
    });

    for (let round = 1; round <= rounds; round += 1) {
      const multiCount = scenarioMultiCounts[(round - 1) % scenarioMultiCounts.length];
      const roundReport = {
        round,
        multi_target_count: multiCount,
      };
      // eslint-disable-next-line no-console
      console.log(`[round ${round}/${rounds}] target multi upload count=${multiCount}`);
      try {
        // round start: clear backend cache + open module
        roundReport.cache_clear_before = await clearBackendCache();
        await withRetry(`round-${round}-open-start`, 3, async () => openModulePage(page));
        await clearUiCache(page);
        await withRetry(`round-${round}-open-after-ui-clear`, 3, async () => openModulePage(page));

        // single
        roundReport.single = await withRetry(`round-${round}-single`, 2, async () =>
          runScenario({
            page,
            rng,
            files,
            round,
            kind: "single",
            multiCount: 1,
            screenshotPrefix: tsTag(),
          })
        );

        // clear caches after single
        roundReport.cache_clear_after_single = await clearBackendCache();
        await clearUiCache(page);
        await withRetry(`round-${round}-open-before-multi`, 3, async () => openModulePage(page));

        // multi
        roundReport.multi = await withRetry(`round-${round}-multi`, 2, async () =>
          runScenario({
            page,
            rng,
            files,
            round,
            kind: "multi",
            multiCount,
            screenshotPrefix: tsTag(),
          })
        );

        // clear caches after multi
        roundReport.cache_clear_after_multi = await clearBackendCache();
        await clearUiCache(page);
      } catch (err) {
        roundReport.round_error = String(err?.message || err || "unknown_round_error");
        // eslint-disable-next-line no-console
        console.error(`[round ${round}] failed: ${roundReport.round_error}`);
        roundReport.cache_clear_on_error = await clearBackendCache().catch((error) => ({
          ok: false,
          status: 0,
          body: String(error?.message || error || ""),
        }));
        await clearUiCache(page).catch(() => {});
      }
      roundReports.push(roundReport);
    }
  } finally {
    if (context) await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }

  const summary = {
    rounds,
    round_error_count: roundReports.filter((r) => Boolean(r.round_error)).length,
    single_nonpdf_sla_failures: roundReports.filter((r) => r.single && !r.single.single_nonpdf_under_90s).length,
    extraction_fail_rounds: roundReports.filter(
      (r) =>
        Boolean(r.round_error) ||
        !r.single ||
        !r.multi ||
        r.single.extract_status_code !== 200 ||
        r.multi.extract_status_code !== 200 ||
        Boolean(r.single.scenario_error) ||
        Boolean(r.multi.scenario_error)
    ).length,
    summary_response_anomaly_rounds: roundReports.filter(
      (r) =>
        Boolean(r.single && (!r.single.summary_request_seen || !r.single.summary_ui_immediate_ok)) ||
        Boolean(r.multi && (!r.multi.summary_request_seen || !r.multi.summary_ui_immediate_ok))
    ).length,
    upload_panel_transition_failures: roundReports.filter(
      (r) => Boolean(r.single && !r.single.upload_panel_transition_ok) || Boolean(r.multi && !r.multi.upload_panel_transition_ok)
    ).length,
    over_limit_guard_failures: roundReports.filter((r) => r.multi && !r.multi.over_limit_guard_ok).length,
    assistant_persist_success_rounds: roundReports.filter(
      (r) => Boolean(r.single?.assistant_persisted || r.multi?.assistant_persisted)
    ).length,
  };

  const output = {
    generated_at: new Date().toISOString(),
    seed,
    app_url: appUrl,
    cache_clear_url: cacheClearUrl,
    dataset_root: datasetRoot,
    rounds,
    single_nonpdf_sla_ms: singleNonPdfSlaMs,
    summary,
    diagnostics: {
      console_error_count: consoleErrors.length,
      page_error_count: pageErrors.length,
      server_error_count: serverErrors.length,
      server_errors: serverErrors.slice(-60),
      console_errors: consoleErrors.slice(-40),
      page_errors: pageErrors.slice(-40),
    },
    rounds_report: roundReports,
  };

  const outputPath = path.join(outputRoot, `frontend_playwright_realistic_${tsTag()}.json`);
  await fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf-8");

  // eslint-disable-next-line no-console
  console.log(
    JSON.stringify(
      {
        output_path: outputPath,
        summary,
      },
      null,
      2
    )
  );
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});
