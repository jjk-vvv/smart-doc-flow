#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const datasetRoot = path.join(projectRoot, "datasets");
const runTag = tsTag();
const defaultOutputRoot = path.join(projectRoot, ".runlogs", "module2-frontend-regression", runTag);
const outputRoot = process.env.MODULE2_FRONTEND_OUTPUT_DIR || defaultOutputRoot;
const screenshotRoot = process.env.MODULE2_FRONTEND_SCREENSHOT_DIR || path.join(outputRoot, "screenshots");

const appUrl = process.env.MODULE2_APP_URL || "http://127.0.0.1:3000";
const apiBaseOverride = String(process.env.MODULE2_API_BASE_OVERRIDE || "").trim().replace(/\/+$/, "").replace(/\/extract$/i, "");
const module2ApiBase = apiBaseOverride || "http://127.0.0.1:8000";
const module4ApiBase = String(process.env.MODULE4_API_BASE || "http://127.0.0.1:8100").trim().replace(/\/+$/, "");
const module4Tenant = String(process.env.MODULE4_TENANT || "default").trim() || "default";
const cacheClearUrl =
  process.env.MODULE2_CACHE_CLEAR_URL ||
  `${module2ApiBase}/extract/cache/clear`;
const playwrightExecutablePath = String(process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH || "").trim();
const rounds = Math.max(1, Number.parseInt(process.env.MODULE2_FRONTEND_ROUNDS || "5", 10) || 5);
const seed = Number(process.env.MODULE2_FRONTEND_SEED || Date.now()) >>> 0;
const singleNonPdfSlaMs = 90_000;
const scenarioMultiCounts = [2, 3, 4, 5, 4];
const jobTerminalTimeoutMs = Math.max(
  300_000,
  Number.parseInt(process.env.MODULE2_FRONTEND_JOB_TIMEOUT_MS || "2700000", 10) || 2_700_000
);
const summaryRequestTimeoutMs = Math.max(620_000, jobTerminalTimeoutMs + 120_000);

const PREFERRED_SINGLE_TOKENS = [
  "2021年民政事业发展统计公报.docx",
  "电商销售数据.xlsx",
  "2024年卫生健康事业发展统计公报.md",
  "南京市2021~2024年国民经济和社会发展统计公报汇总.docx",
];

const PREFERRED_MULTI_TOKEN_GROUPS = [
  ["2021年民政事业发展统计公报.docx", "A.4. Solvent Extraction Equipment.pdf"],
  ["2021年民政事业发展统计公报.docx", "电商销售数据.xlsx", "2024年卫生健康事业发展统计公报.md"],
  ["南京市2021~2024年国民经济和社会发展统计公报汇总.docx", "A.4. Solvent Extraction Equipment.pdf", "电商销售数据.xlsx"],
  ["2024年杭州市生态环境状况公报（节选）.docx", "2025年国考职位表（节选）.xlsx", "2024年卫生健康事业发展统计公报.md", "A.4. Solvent Extraction Equipment.pdf"],
  ["2021年民政事业发展统计公报.docx", "电商销售数据.xlsx", "2024年卫生健康事业发展统计公报.md", "2025山东省环境空气质量监测数据信息.xlsx", "A.4. Solvent Extraction Equipment.pdf"],
];

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

function normalizeFsPath(inputPath) {
  return path.resolve(String(inputPath || "")).replace(/\\/g, "/").toLowerCase();
}

function parseJsonStringArrayEnv(envName) {
  const raw = String(process.env[envName] || "").trim();
  if (!raw) return [];
  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new Error(`${envName} must be a JSON array of file paths: ${String(err?.message || err || "invalid_json")}`);
  }
  if (!Array.isArray(parsed)) {
    throw new Error(`${envName} must be a JSON array of file paths.`);
  }
  return parsed
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function parseJsonNestedStringArrayEnv(envName) {
  const raw = String(process.env[envName] || "").trim();
  if (!raw) return [];
  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new Error(`${envName} must be a JSON array of file-path arrays: ${String(err?.message || err || "invalid_json")}`);
  }
  if (!Array.isArray(parsed)) {
    throw new Error(`${envName} must be a JSON array of file-path arrays.`);
  }
  return parsed
    .map((group) => (Array.isArray(group) ? group.map((item) => String(item || "").trim()).filter(Boolean) : []))
    .filter((group) => group.length > 0);
}

function resolveRepoPath(rawPath) {
  const value = String(rawPath || "").trim();
  if (!value) return "";
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(projectRoot, value);
}

function findFileByToken(files, token) {
  const raw = String(token || "").trim();
  if (!raw) return null;
  const normalizedResolved = normalizeFsPath(resolveRepoPath(raw));
  const normalizedRaw = raw.replace(/\\/g, "/").toLowerCase();

  return (
    files.find((file) => normalizeFsPath(file.path) === normalizedResolved) ||
    files.find((file) => normalizeFsPath(file.path).endsWith(normalizedRaw)) ||
    files.find((file) => file.name.toLowerCase() === normalizedRaw) ||
    files.find((file) => normalizeFsPath(file.path).includes(normalizedRaw)) ||
    files.find((file) => file.name.toLowerCase().includes(normalizedRaw)) ||
    null
  );
}

function dedupeFiles(files) {
  const out = [];
  const seen = new Set();
  for (const file of files) {
    if (!file) continue;
    const key = normalizeFsPath(file.path);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(file);
  }
  return out;
}

function buildSingleScenarioPool(files) {
  const configuredTokens = parseJsonStringArrayEnv("MODULE2_FRONTEND_SINGLE_FILES_JSON");
  const configuredFiles = dedupeFiles(configuredTokens.map((token) => findFileByToken(files, token)).filter(Boolean));
  if (configuredFiles.length > 0) {
    return {
      mode: "configured",
      items: configuredFiles,
    };
  }

  const preferredFiles = dedupeFiles(PREFERRED_SINGLE_TOKENS.map((token) => findFileByToken(files, token)).filter(Boolean));
  if (preferredFiles.length > 0) {
    return {
      mode: "preferred",
      items: preferredFiles,
    };
  }

  return {
    mode: "random",
    items: [],
  };
}

function buildMultiScenarioPool(files) {
  const configuredGroups = parseJsonNestedStringArrayEnv("MODULE2_FRONTEND_MULTI_FILES_JSON")
    .map((group) => dedupeFiles(group.map((token) => findFileByToken(files, token)).filter(Boolean)))
    .filter((group) => group.length >= 2);
  if (configuredGroups.length > 0) {
    return {
      mode: "configured",
      items: configuredGroups,
    };
  }

  const preferredGroups = PREFERRED_MULTI_TOKEN_GROUPS
    .map((group) => dedupeFiles(group.map((token) => findFileByToken(files, token)).filter(Boolean)))
    .filter((group) => group.length >= 2);
  if (preferredGroups.length > 0) {
    return {
      mode: "preferred",
      items: preferredGroups,
    };
  }

  return {
    mode: "random",
    items: [],
  };
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
  const usedPath = new Set();
  const addUnique = (items) => {
    for (const item of items) {
      if (!item || usedPath.has(item.path)) continue;
      usedPath.add(item.path);
      out.push(item);
      if (out.length >= count) break;
    }
  };
  if (pdfPool.length > 0) {
    addUnique(pickRandomFiles(rng, pdfPool, 1));
  }
  const extBuckets = new Map();
  for (const file of others) {
    const bucket = extBuckets.get(file.ext) || [];
    bucket.push(file);
    extBuckets.set(file.ext, bucket);
  }
  const extKeys = Array.from(extBuckets.keys());
  while (extKeys.length > 0 && out.length < count) {
    const idx = randInt(rng, extKeys.length);
    const ext = extKeys.splice(idx, 1)[0];
    addUnique(pickRandomFiles(rng, extBuckets.get(ext) || [], 1));
  }
  if (out.length < count) {
    addUnique(pickRandomFiles(rng, others, count - out.length));
  }
  if (out.length < count) {
    addUnique(pickRandomFiles(rng, basePool, count - out.length));
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

async function fetchJson(url) {
  const response = await fetch(url);
  const text = await response.text().catch(() => "");
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(`request_failed:${response.status}:${url}:${text.slice(0, 240)}`);
  }
  return payload;
}

async function readModule2Healthz() {
  return await fetchJson(`${module2ApiBase}/healthz`);
}

async function readModule4Job(jobId) {
  if (!jobId) return null;
  const suffix = module4Tenant ? `?tenant_id=${encodeURIComponent(module4Tenant)}` : "";
  return await fetchJson(`${module4ApiBase}/module4/jobs/${encodeURIComponent(jobId)}${suffix}`);
}

async function waitForExtractionJobTerminal(jobId) {
  const startedAt = Date.now();
  const timeline = [];
  let latestPayload = null;
  let latestStatusCode = 0;
  const finalUrl = `${module2ApiBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`;

  while (Date.now() - startedAt < jobTerminalTimeoutMs) {
    try {
      const response = await fetch(finalUrl);
      latestStatusCode = Number(response.status || 0);
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      latestPayload = payload;
      timeline.push({
        ts: new Date().toISOString(),
        status_code: latestStatusCode,
        status: String(payload?.status || ""),
        terminal: Boolean(payload?.terminal),
        completed_files: Number(payload?.progress?.completed_files || 0),
        failed_files: Number(payload?.progress?.failed_files || 0),
        current_file_name: String(payload?.progress?.current_file_name || ""),
        current_stage: String(payload?.progress?.current_stage || ""),
        document_count: Array.isArray(payload?.documents) ? payload.documents.length : 0,
      });
      if (response.ok && payload?.terminal) {
        return {
          timed_out: false,
          status_code: latestStatusCode,
          payload,
          timeline,
          elapsed_ms: Date.now() - startedAt,
        };
      }
    } catch (err) {
      timeline.push({
        ts: new Date().toISOString(),
        error: String(err?.message || err || "job_poll_failed"),
      });
    }
    await sleep(1500);
  }

  return {
    timed_out: true,
    status_code: latestStatusCode,
    payload: latestPayload,
    timeline,
    elapsed_ms: Date.now() - startedAt,
  };
}

async function waitForModule4Sync(previousHealthz) {
  const startedAt = Date.now();
  const prevAttempted = Number(previousHealthz?.module4_sync_attempted_batches || 0);
  const prevSucceeded = Number(previousHealthz?.module4_sync_succeeded_batches || 0);
  const prevFailed = Number(previousHealthz?.module4_sync_failed_batches || 0);
  const prevJobId = String(previousHealthz?.module4_sync_last_job_id || "");
  let latestHealthz = null;
  let latestJob = null;

  while (Date.now() - startedAt < 180_000) {
    latestHealthz = await readModule2Healthz().catch(() => null);
    const attempted = Number(latestHealthz?.module4_sync_attempted_batches || 0);
    const succeeded = Number(latestHealthz?.module4_sync_succeeded_batches || 0);
    const failed = Number(latestHealthz?.module4_sync_failed_batches || 0);
    const lastJobId = String(latestHealthz?.module4_sync_last_job_id || "");
    const syncAdvanced = attempted > prevAttempted || succeeded > prevSucceeded || failed > prevFailed || (lastJobId && lastJobId !== prevJobId);

    if (lastJobId) {
      latestJob = await readModule4Job(lastJobId).catch(() => null);
    }
    const jobStatus = String(latestJob?.status || "").toLowerCase();
    const jobTerminal = ["completed", "failed", "succeeded", "success"].includes(jobStatus);
    const jobFailed = ["failed", "error"].includes(jobStatus);

    if (syncAdvanced && (jobTerminal || !lastJobId)) {
      return {
        ok: failed <= prevFailed && !jobFailed,
        timed_out: false,
        healthz: latestHealthz,
        job: latestJob,
      };
    }
    await sleep(2000);
  }

  return {
    ok: false,
    timed_out: true,
    healthz: latestHealthz,
    job: latestJob,
  };
}

async function writeJson(filePath, payload) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}

async function applyApiBaseOverride(page) {
  if (!apiBaseOverride) return;
  await page.evaluate((base) => {
    try {
      window.localStorage.setItem("module2_api_base_override", String(base || "").trim());
    } catch {
      // ignore
    }
  }, apiBaseOverride);
}

async function openModulePage(page) {
  await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  await applyApiBaseOverride(page);

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
  if (visible) {
    const raw = (await page.getByTestId("module2-file-count").textContent()) || "";
    const m = raw.match(/(\d+)\s*\/\s*5/);
    if (m) return Number(m[1]);
  }
  const info = ((await page.getByTestId("module2-info-message").textContent().catch(() => "")) || "").trim();
  const infoMatch = info.match(/已选择\s*(\d+)\s*个文件/);
  return infoMatch ? Number(infoMatch[1]) : 0;
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

async function readTraceState(page) {
  try {
    return await page.evaluate(() => {
      const panel = document.querySelector('[data-testid="module2-trace-panel"]');
      const isVisible = (el) => {
        if (!(el instanceof HTMLElement)) return false;
        const style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") <= 0.01) {
          return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 4 && rect.height > 4;
      };
      const selectCount = (selector) => (panel ? panel.querySelectorAll(selector).length : 0);
      const groupLabels = panel
        ? Array.from(panel.querySelectorAll('[data-testid="module2-trace-group-label"]'))
            .map((el) => (el.textContent || "").trim())
            .filter(Boolean)
        : [];
      return {
        panel_visible: isVisible(panel),
        card_count: selectCount('[data-testid="module2-trace-card"]'),
        artifact_image_count: selectCount('[data-testid="module2-trace-artifact-image"]'),
        table_preview_count: selectCount('[data-testid="module2-trace-table-preview"]'),
        figure_dataframe_count: selectCount('[data-testid="module2-trace-figure-dataframe"]'),
        group_labels: groupLabels,
      };
    });
  } catch (err) {
    return {
      panel_visible: false,
      card_count: 0,
      artifact_image_count: 0,
      table_preview_count: 0,
      figure_dataframe_count: 0,
      group_labels: [],
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
      const countRaw = (document.querySelector('[data-testid="module2-file-count"]')?.textContent || "").trim();
      const countMatch = countRaw.match(/(\d+)\s*\/\s*5/);
      const infoRaw = (document.querySelector('[data-testid="module2-info-message"]')?.textContent || "").trim();
      const infoMatch = infoRaw.match(/已选择\s*(\d+)\s*个文件/);
      const selected = Number(countMatch?.[1] || infoMatch?.[1] || 0);
      return selected > 0 && !btn.disabled;
    },
    null,
    { timeout: 20_000 }
  );
}

async function waitAssistantContextReady(page) {
  await page.waitForFunction(
    () => {
      const input = document.querySelector('[data-testid="module2-assistant-input"]');
      return input instanceof HTMLTextAreaElement && !String(input.placeholder || "").includes("请先抽取文档");
    },
    null,
    { timeout: 120_000 }
  );
}

async function runExtraction(page) {
  await waitStartButtonReady(page);
  const startTs = Date.now();
  let summarySeenTs = null;
  let jobCreateSeenTs = null;
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
      { timeout: summaryRequestTimeoutMs }
    )
    .then((res) => {
      summarySeenTs = Date.now();
      return res;
    })
    .catch(() => null);
  const jobCreatePromise = page
    .waitForResponse(
      (res) => res.url().includes("/extract/jobs/create") && res.request().method() === "POST",
      { timeout: 540_000 }
    )
    .then((res) => {
      jobCreateSeenTs = Date.now();
      return res;
    })
    .catch((err) => err);
  await page.getByTestId("module2-start-extract").click({ timeout: 20_000 });
  const jobCreateResp = await jobCreatePromise;
  if (jobCreateResp instanceof Error) {
    const uiState = await readUiState(page);
    throw new Error(
      `job_create_failed:${String(jobCreateResp.message || jobCreateResp)};ui_state=${JSON.stringify(uiState)}`
    );
  }
  const createStatus = jobCreateResp.status();
  let createPayload = null;
  try {
    createPayload = await jobCreateResp.json();
  } catch {
    createPayload = null;
  }
  const jobId = String(createPayload?.job_id || "").trim();
  let finalPayload = createPayload;
  let finalStatusCode = createStatus;
  let jobTerminalState = null;
  if (jobId) {
    jobTerminalState = await waitForExtractionJobTerminal(jobId);
    finalStatusCode = Number(jobTerminalState?.status_code || createStatus);
    finalPayload = jobTerminalState?.payload || createPayload;
    if (jobTerminalState?.timed_out) {
      throw new Error(
        `job_terminal_timeout:${jobId};last_status=${String(finalPayload?.status || "")};completed=${Number(finalPayload?.progress?.completed_files || 0)};failed=${Number(finalPayload?.progress?.failed_files || 0)}`
      );
    }
  }

  const summaryResp = await Promise.race([summaryPromise, sleep(45_000).then(() => null)]);
  const summaryUiImmediateOk = await summaryUiPromise;
  if (jobId) {
    await waitAssistantContextReady(page);
  }

  const elapsedMs = Date.now() - startTs;
  const summaryLatencyMs = summarySeenTs == null ? -1 : Math.max(0, summarySeenTs - startTs);
  const summaryUiLatencyMs = summaryUiSeenTs == null ? -1 : Math.max(0, summaryUiSeenTs - startTs);
  const infoMessage = ((await page.getByTestId("module2-info-message").textContent()) || "").trim();
  let traceStatus = "";
  try {
    traceStatus = ((await page.getByTestId("module2-trace-status").textContent()) || "").trim();
  } catch {
    const traceState = await readTraceState(page).catch(() => null);
    traceStatus = traceState ? `cards=${Number(traceState.card_count || 0)}` : "";
  }
  const summaryText = ((await page.getByTestId("module2-summary-text").textContent()) || "").trim();
  return {
    elapsed_ms: elapsedMs,
    status_code: finalStatusCode,
    payload: finalPayload,
    info_message: infoMessage,
    trace_status: traceStatus,
    summary_text: summaryText,
    summary_request_seen: Boolean(summaryResp),
    summary_latency_ms: summaryLatencyMs,
    summary_ui_immediate_ok: summaryUiImmediateOk,
    summary_ui_latency_ms: summaryUiLatencyMs,
    summary_before_batch: summarySeenTs != null && jobCreateSeenTs != null ? summarySeenTs <= jobCreateSeenTs : false,
    job_id: jobId,
    job_terminal_wait_ms: Number(jobTerminalState?.elapsed_ms || 0),
    job_terminal_timed_out: Boolean(jobTerminalState?.timed_out),
    job_poll_timeline: Array.isArray(jobTerminalState?.timeline) ? jobTerminalState.timeline : [],
  };
}

async function runAssistant(page, instruction) {
  await page.getByTestId("module2-assistant-input").fill(instruction);
  const assistantPromise = page
    .waitForResponse(
      (res) => res.url().includes("/extract/assistant1/chat/stream") && res.request().method() === "POST",
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
    await page.waitForFunction(
      () => {
        const btn = document.querySelector('[data-testid="module2-assistant-send"]');
        return btn instanceof HTMLButtonElement && String(btn.title || "") === "发送";
      },
      null,
      { timeout: 240_000 }
    );
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

async function captureStep(page, scenarioDir, name) {
  await fs.mkdir(scenarioDir, { recursive: true });
  const screenshotPath = path.join(scenarioDir, name);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  return screenshotPath;
}

function summarizeDocuments(documents) {
  const traceHits = [];
  let officePdfConvertedDocs = 0;
  for (const doc of documents) {
    const diagnostics = doc?.diagnostics && typeof doc.diagnostics === "object" ? doc.diagnostics : {};
    if (diagnostics.office_pdf_converted === true) {
      officePdfConvertedDocs += 1;
    }
    if (Array.isArray(doc?.trace_hits)) {
      traceHits.push(...doc.trace_hits);
    }
  }
  const figureHits = traceHits.filter((hit) => String(hit?.object_type || "").toLowerCase() === "figure");
  const tableHits = traceHits.filter((hit) => String(hit?.object_type || "").toLowerCase() === "table");
  const figureHitsWithArtifact = figureHits.filter((hit) => Boolean(hit?.artifact_path || hit?.artifact_url));
  const tableHitsWithArtifact = tableHits.filter((hit) => Boolean(hit?.artifact_path || hit?.artifact_url));
  const figureHitsWithDataframe = figureHits.filter((hit) => {
    const locator = hit?.locator && typeof hit.locator === "object" ? hit.locator : {};
    const dataframe = locator?.dataframe && typeof locator.dataframe === "object" ? locator.dataframe : {};
    const rows = Array.isArray(dataframe?.rows) ? dataframe.rows : [];
    return rows.some((row) => Array.isArray(row) && row.some((cell) => String(cell || "").trim()));
  });
  return {
    document_count: documents.length,
    file_names: documents.map((doc) => String(doc?.file_name || "")),
    office_pdf_converted_docs: officePdfConvertedDocs,
    trace_hit_count: traceHits.length,
    figure_hit_count: figureHits.length,
    figure_hits_with_artifact: figureHitsWithArtifact.length,
    figure_hits_with_dataframe: figureHitsWithDataframe.length,
    table_hit_count: tableHits.length,
    table_hits_with_artifact: tableHitsWithArtifact.length,
  };
}

async function runScenario({
  page,
  rng,
  files,
  round,
  kind,
  multiCount,
  screenshotPrefix,
  singleScenarioPool,
  multiScenarioPool,
}) {
  await ensureModuleReady(page, 2);

  let selectionMode = "random";
  let selected = [];
  if (kind === "single") {
    if (Array.isArray(singleScenarioPool?.items) && singleScenarioPool.items.length > 0) {
      selectionMode = String(singleScenarioPool.mode || "preferred");
      selected = [singleScenarioPool.items[(round - 1) % singleScenarioPool.items.length]].filter(Boolean);
    } else {
      selected = [pickSingleNonPdf(rng, files)].filter(Boolean);
    }
  } else if (Array.isArray(multiScenarioPool?.items) && multiScenarioPool.items.length > 0) {
    selectionMode = String(multiScenarioPool.mode || "preferred");
    selected = [...multiScenarioPool.items[(round - 1) % multiScenarioPool.items.length]];
  } else {
    selected = pickRandomMultiFiles(rng, files, multiCount);
  }
  if (selected.length === 0) {
    throw new Error(`\u573a\u666f ${kind} \u65e0\u53ef\u7528\u6d4b\u8bd5\u6587\u4ef6`);
  }

  const scenarioDir = path.join(
    screenshotRoot,
    `round${String(round).padStart(2, "0")}_${kind}_${screenshotPrefix}`
  );
  await fs.mkdir(scenarioDir, { recursive: true });
  const module2HealthzBefore = await readModule2Healthz().catch((error) => ({
    read_error: String(error?.message || error || ""),
  }));
  const uploadLayoutBefore = await readUploadLayoutState(page);
  await captureStep(page, scenarioDir, "01_before_upload.png");
  const filePaths = selected.map((x) => x.path);
  await uploadFiles(page, filePaths);
  const uploadLayoutAfter = await readUploadLayoutState(page);
  await captureStep(page, scenarioDir, "02_after_upload.png");
  let countBadge = await parseCountBadge(page);
  if (countBadge <= 0) {
    await ensureModuleReady(page, 2);
    await uploadFiles(page, filePaths);
    const uploadLayoutRetry = await readUploadLayoutState(page);
    uploadLayoutAfter.left_panel_visible = uploadLayoutRetry.left_panel_visible;
    uploadLayoutAfter.center_uploader_visible = uploadLayoutRetry.center_uploader_visible;
    uploadLayoutAfter.count_raw = uploadLayoutRetry.count_raw;
    countBadge = await parseCountBadge(page);
    await captureStep(page, scenarioDir, "02b_after_upload_retry.png");
  }

  let extraction = null;
  let assistant = null;
  let scenarioError = "";
  if (countBadge <= 0) {
    const uiState = await readUiState(page);
    scenarioError = `upload_count_badge_missing;ui_state=${JSON.stringify(uiState)}`;
  }
  const uploadPanelTransitionOk =
    !Boolean(uploadLayoutAfter?.center_uploader_visible) &&
    countBadge > 0;
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
        if (attempt >= 2 || !errText.includes("job_create_failed")) {
          break;
        }
        await ensureModuleReady(page, 2);
        await uploadFiles(page, filePaths);
        await captureStep(page, scenarioDir, `03_retry_upload_attempt${attempt}.png`);
      }
    }
    if (extractionErr) {
      const uiState = await readUiState(page);
      scenarioError = `${String(extractionErr?.message || extractionErr || "extract_timeout")};ui_state=${JSON.stringify(uiState)}`;
    }
  }
  if (!scenarioError) {
    await captureStep(page, scenarioDir, "03_after_extract.png");
  }

  const traceState = await readTraceState(page).catch((error) => ({
    panel_visible: false,
    card_count: 0,
    artifact_image_count: 0,
    table_preview_count: 0,
    figure_dataframe_count: 0,
    group_labels: [],
    read_error: String(error?.message || error || ""),
  }));

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

  const screenshotPath = await captureStep(page, scenarioDir, "04_final.png");

  const documents = Array.isArray(extraction?.payload?.documents) ? extraction.payload.documents : [];
  const documentSummary = summarizeDocuments(documents);
  const docErrors = documents.reduce(
    (acc, doc) => acc + (Array.isArray(doc?.errors) ? doc.errors.length : 0),
    0
  );
  const module4Sync = await waitForModule4Sync(module2HealthzBefore).catch((error) => ({
    ok: false,
    timed_out: true,
    healthz: null,
    job: null,
    wait_error: String(error?.message || error || ""),
  }));
  const singleNonPdfSlaOk =
    kind !== "single" || !NON_PDF_EXT.has(path.extname(selected[0].name).toLowerCase())
      ? true
      : Number(extraction?.elapsed_ms || Number.MAX_SAFE_INTEGER) < singleNonPdfSlaMs;
  const elapsedMs = Number(extraction?.elapsed_ms || 0);

  await writeJson(path.join(scenarioDir, "module2_healthz_before.json"), module2HealthzBefore);
  await writeJson(path.join(scenarioDir, "module2_healthz_after.json"), module4Sync?.healthz || {});
  await writeJson(path.join(scenarioDir, "module4_sync.json"), module4Sync || {});
  await writeJson(path.join(scenarioDir, "trace_state.json"), traceState || {});
  await writeJson(path.join(scenarioDir, "documents_summary.json"), documentSummary);
  await writeJson(path.join(scenarioDir, "extract_payload.json"), extraction?.payload || {});
  await writeJson(path.join(scenarioDir, "extract_job_timeline.json"), extraction?.job_poll_timeline || []);
  await writeJson(path.join(scenarioDir, "assistant_payload.json"), assistant?.payload || {});

  return {
    kind,
    selection_mode: selectionMode,
    files: selected.map((x) => x.name),
    uploaded_file_count: filePaths.length,
    badge_selected_count: countBadge,
    extract_elapsed_ms: elapsedMs,
    extract_status_code: Number(extraction?.status_code || 0),
    extract_job_id: String(extraction?.job_id || ""),
    extract_job_status: String(extraction?.payload?.status || ""),
    extract_terminal: Boolean(extraction?.payload?.terminal),
    extract_terminal_wait_ms: Number(extraction?.job_terminal_wait_ms || 0),
    extract_terminal_timed_out: Boolean(extraction?.job_terminal_timed_out),
    extract_completed_files: Number(extraction?.payload?.progress?.completed_files || 0),
    extract_failed_files: Number(extraction?.payload?.progress?.failed_files || 0),
    extract_doc_count: documents.length,
    extract_doc_count_matches_upload: documents.length === filePaths.length,
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
    module4_sync_ok: Boolean(module4Sync?.ok),
    module4_sync_timed_out: Boolean(module4Sync?.timed_out),
    module4_job_id: String(module4Sync?.healthz?.module4_sync_last_job_id || ""),
    module4_job_status: String(module4Sync?.job?.status || ""),
    module4_sync_endpoint: String(module4Sync?.healthz?.module4_sync_last_endpoint || ""),
    trace_panel_visible: Boolean(traceState?.panel_visible),
    trace_card_count: Number(traceState?.card_count || 0),
    trace_artifact_image_count: Number(traceState?.artifact_image_count || 0),
    trace_table_preview_count: Number(traceState?.table_preview_count || 0),
    trace_figure_dataframe_count: Number(traceState?.figure_dataframe_count || 0),
    trace_group_labels: Array.isArray(traceState?.group_labels) ? traceState.group_labels : [],
    documents_summary: documentSummary,
    single_nonpdf_under_90s: singleNonPdfSlaOk,
    screenshot_dir: scenarioDir,
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
  const singleScenarioPool = buildSingleScenarioPool(files);
  const multiScenarioPool = buildMultiScenarioPool(files);

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
      executablePath: playwrightExecutablePath || undefined,
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
            singleScenarioPool,
            multiScenarioPool,
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
            singleScenarioPool,
            multiScenarioPool,
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
        !r.single.extract_terminal ||
        !r.multi.extract_terminal ||
        Boolean(r.single.scenario_error) ||
        Boolean(r.multi.scenario_error)
    ).length,
    doc_count_mismatch_rounds: roundReports.filter(
      (r) =>
        Boolean(r.single && !r.single.extract_doc_count_matches_upload) ||
        Boolean(r.multi && !r.multi.extract_doc_count_matches_upload)
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
    module4_sync_fail_rounds: roundReports.filter(
      (r) => Boolean(r.single && !r.single.module4_sync_ok) || Boolean(r.multi && !r.multi.module4_sync_ok)
    ).length,
    trace_artifact_gap_rounds: roundReports.filter(
      (r) => Boolean(r.single && Number(r.single.trace_artifact_image_count || 0) <= 0) || Boolean(r.multi && Number(r.multi.trace_artifact_image_count || 0) <= 0)
    ).length,
    trace_dataframe_gap_rounds: roundReports.filter(
      (r) => Boolean(r.single && Number(r.single.documents_summary?.figure_hits_with_dataframe || 0) <= 0) || Boolean(r.multi && Number(r.multi.documents_summary?.figure_hits_with_dataframe || 0) <= 0)
    ).length,
    assistant_persist_success_rounds: roundReports.filter(
      (r) => Boolean(r.single?.assistant_persisted || r.multi?.assistant_persisted)
    ).length,
  };

  const output = {
    generated_at: new Date().toISOString(),
    run_tag: runTag,
    seed,
    app_url: appUrl,
    api_base_override: apiBaseOverride,
    module2_api_base: module2ApiBase,
    module4_api_base: module4ApiBase,
    cache_clear_url: cacheClearUrl,
    playwright_executable_path: playwrightExecutablePath,
    dataset_root: datasetRoot,
    output_root: outputRoot,
    screenshot_root: screenshotRoot,
    rounds,
    single_nonpdf_sla_ms: singleNonPdfSlaMs,
    job_terminal_timeout_ms: jobTerminalTimeoutMs,
    scenario_pools: {
      single_mode: String(singleScenarioPool.mode || "random"),
      single_files: Array.isArray(singleScenarioPool.items) ? singleScenarioPool.items.map((item) => item.name) : [],
      multi_mode: String(multiScenarioPool.mode || "random"),
      multi_files: Array.isArray(multiScenarioPool.items)
        ? multiScenarioPool.items.map((group) => group.map((item) => item.name))
        : [],
    },
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

  const outputPath = path.join(outputRoot, "report.json");
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
