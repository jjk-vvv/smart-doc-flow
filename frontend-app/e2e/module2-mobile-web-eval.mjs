#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const datasetsRoot = path.join(projectRoot, "datasets");

const appUrl = String(process.env.MODULE2_APP_URL || "http://127.0.0.1:3002").trim();
const apiBase = String(process.env.MODULE2_API_BASE || "http://127.0.0.1:3001")
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/extract$/i, "");
const configuredExecutablePath = String(
  process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH || process.env.PLAYWRIGHT_EXECUTABLE_PATH || "",
).trim();
const browserExecutableCandidates = [
  configuredExecutablePath,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.join(projectRoot, ".runlogs", "module2-mobile-web-eval", runTag);
const screenshotDir = path.join(outputDir, "screenshots");
const progressLogPath = path.join(outputDir, "progress.log");
const createTimeoutMs = Math.max(30_000, Number(process.env.MODULE2_CREATE_TIMEOUT_MS || 120_000));
const terminalTimeoutMs = Math.max(60_000, Number(process.env.MODULE2_TERMINAL_TIMEOUT_MS || 480_000));
const pollIntervalMs = Math.max(800, Number(process.env.MODULE2_TERMINAL_POLL_INTERVAL_MS || 2_000));
const scenarioIdsFilter = String(process.env.MODULE2_SCENARIO_IDS || "")
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);

const DESKTOP_VIEWPORT = { width: 1366, height: 900 };
const MOBILE_VIEWPORT = { width: 390, height: 844 };

const scenarios = [
  {
    id: "docx_single",
    description: "单文件 DOCX",
    files: [
      "word/2021年民政事业发展统计公报.docx",
    ],
  },
  {
    id: "xlsx_single",
    description: "单文件 XLSX",
    files: [
      "Excel/电商销售数据.xlsx",
    ],
  },
  {
    id: "md_single",
    description: "单文件 Markdown",
    files: [
      "md/2024年卫生健康事业发展统计公报.md",
    ],
  },
  {
    id: "txt_single",
    description: "single-file TXT",
    files: [
      "txt/2024年药品流通行业运行统计分析报告.txt",
    ],
  },
  {
    id: "pdf_single",
    description: "单文件 PDF",
    files: [
      "PDF/Choppin, Gregory, et al. Radiochemistry and nuclear chemistry. Academic Press, 2013/Appendix A Solvent Extraction Separations/A.4. Solvent Extraction Equipment.pdf",
    ],
  },
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const normalizePath = (value) => path.resolve(String(value || "")).replace(/\\/g, "/").toLowerCase();

function toDisplayValue(value) {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean).join("、");
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function getHitLocator(hit) {
  const locator = hit?.locator;
  if (!locator || typeof locator !== "object" || Array.isArray(locator)) return {};
  return locator;
}

function toDataframePayload(value) {
  let source = value;
  if (typeof source === "string") {
    const text = source.trim();
    if (!text) source = null;
    else {
      try {
        source = JSON.parse(text);
      } catch {
        source = value;
      }
    }
  }
  const payload =
    source && typeof source === "object" && !Array.isArray(source)
      ? source
      : {};
  const headers = Array.isArray(payload.headers)
    ? payload.headers.map((item) => String(item ?? "").trim())
    : [];
  const rows = Array.isArray(payload.rows)
    ? payload.rows.map((row) =>
        Array.isArray(row) ? row.map((cell) => String(cell ?? "").trim()) : [],
      )
    : [];
  return { headers, rows };
}

function pickBestDataframe(...values) {
  const candidates = values.map((item) => {
    const payload = toDataframePayload(item);
    const nonEmptyCellCount = payload.rows.reduce(
      (acc, row) => acc + row.filter((cell) => cell.trim().length > 0).length,
      0,
    );
    const score =
      payload.rows.length * 10000 +
      payload.headers.length * 100 +
      nonEmptyCellCount;
    return { payload, score };
  });
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0]?.payload || { headers: [], rows: [] };
}

function isTableLikeFigureTrace(hit) {
  const locator = getHitLocator(hit);
  const figureType = String(locator.figure_type || "").trim().toLowerCase();
  if (figureType === "table" || figureType === "spreadsheet") return true;
  const dataframe = pickBestDataframe(
    locator.dataframe,
    locator.table_preview,
    locator.dataframe_json,
  );
  return dataframe.headers.length > 0 || dataframe.rows.length > 0;
}

function getTraceKind(hit) {
  const objectType = String(hit?.object_type || "").trim().toLowerCase();
  if (objectType === "field") return "field";
  if (objectType === "table") return "table";
  if (objectType === "figure" || objectType === "image") {
    return isTableLikeFigureTrace(hit) ? "table" : "image";
  }
  return "other";
}

function computeExpectedFieldCount(doc) {
  const result = doc?.result && typeof doc.result === "object" ? doc.result : {};
  return Object.values(result).reduce((count, entity) => {
    const value = toDisplayValue(entity?.value);
    return value.length > 0 ? count + 1 : count;
  }, 0);
}

async function resolveScenarioFiles() {
  const resolved = [];
  for (const scenario of scenarios) {
    const files = [];
    for (const relPath of scenario.files) {
      const full = path.resolve(datasetsRoot, relPath);
      try {
        await fs.access(full);
      } catch {
        throw new Error(`missing_fixture_file:${full}`);
      }
      files.push(full);
    }
    resolved.push({
      ...scenario,
      files,
    });
  }
  if (scenarioIdsFilter.length === 0) return resolved;
  return resolved.filter((item) => scenarioIdsFilter.includes(item.id));
}

async function ensureDirs() {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.mkdir(screenshotDir, { recursive: true });
}

async function mark(message) {
  const line = `[${new Date().toISOString()}] ${String(message || "").trim()}\n`;
  await fs.appendFile(progressLogPath, line, "utf8").catch(() => {});
}

async function resolveBrowserExecutablePath() {
  for (const candidate of browserExecutableCandidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      continue;
    }
  }
  return "";
}

async function clearFrontendState(page) {
  await page.evaluate((nextApiBase) => {
    window.localStorage.removeItem("module2_last_documents");
    window.localStorage.removeItem("module2_last_updated");
    window.localStorage.removeItem("module2_workbench_session_v1");
    window.localStorage.removeItem("module2_assistant_session_map_v1");
    window.localStorage.setItem("module2_api_base_override", String(nextApiBase || "").trim());
    window.dispatchEvent(new Event("module2-data-updated"));
  }, apiBase);
}

function parseJsonSafe(value, fallback = {}) {
  try {
    if (value == null) return fallback;
    if (typeof value === "object") return value;
    return JSON.parse(String(value || ""));
  } catch {
    return fallback;
  }
}

async function readDocumentsFromStorage(page) {
  return await page.evaluate(() => {
    try {
      const docsRaw = window.localStorage.getItem("module2_last_documents");
      const docs = docsRaw ? JSON.parse(docsRaw) : [];
      return Array.isArray(docs) ? docs : [];
    } catch {
      return [];
    }
  });
}

async function enterLegacyWorkbench(page) {
  await openProtectedTab(page, appUrl, "deepread_extraction");
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  if ((await fileInput.count().catch(() => 0)) > 0) {
    await fileInput.first().waitFor({ state: "attached", timeout: 30_000 });
    return;
  }

  const openLegacyBtn = page.getByRole("button", { name: /进入完整工作台/ }).first();
  if (await openLegacyBtn.isVisible().catch(() => false)) {
    await openLegacyBtn.click({ timeout: 20_000 });
  }

  await fileInput.first().waitFor({ state: "attached", timeout: 60_000 });
}

async function waitForExtractionTerminalByApi(jobId, cookieHeader, timeoutMs = terminalTimeoutMs) {
  const startedAt = Date.now();
  const timeline = [];
  while (Date.now() - startedAt < timeoutMs) {
    let responseStatus = 0;
    let payload = null;
    let error = "";
    try {
      const response = await fetch(`${apiBase}/extract/jobs/status/${encodeURIComponent(jobId)}`, {
        method: "GET",
        headers: {
          ...(cookieHeader ? { cookie: cookieHeader } : {}),
        },
      });
      responseStatus = response.status;
      const bodyText = await response.text();
      payload = parseJsonSafe(bodyText, {});
      const statusText = String(payload?.status || "").trim();
      const terminal =
        Boolean(payload?.terminal) ||
        ["completed", "failed", "cached", "cancelled"].includes(statusText.toLowerCase());
      timeline.push({
        ts: new Date().toISOString(),
        httpStatus: responseStatus,
        status: statusText,
        terminal,
        completedFiles: Number(payload?.progress?.completed_files || 0),
        failedFiles: Number(payload?.progress?.failed_files || 0),
      });
      if (responseStatus >= 400) {
        return {
          payload,
          terminal: true,
          timedOut: false,
          statusCode: responseStatus,
          timeline,
          error: `job_poll_http_${responseStatus}`,
          elapsedMs: Date.now() - startedAt,
        };
      }
      if (terminal) {
        return {
          payload,
          terminal: true,
          timedOut: false,
          statusCode: responseStatus,
          timeline,
          error: "",
          elapsedMs: Date.now() - startedAt,
        };
      }
    } catch (err) {
      error = String(err?.message || err || "job_poll_failed");
      timeline.push({
        ts: new Date().toISOString(),
        httpStatus: responseStatus,
        status: "",
        terminal: false,
        completedFiles: 0,
        failedFiles: 0,
        error,
      });
    }
    await sleep(pollIntervalMs);
  }
  return {
    payload: null,
    terminal: false,
    timedOut: true,
    statusCode: 0,
    timeline,
    error: "job_terminal_timeout",
    elapsedMs: Date.now() - startedAt,
  };
}

async function createTraceIndexForDocs(docs, cookieHeader) {
  const byFileHash = new Map();
  for (const doc of docs) {
    const fileHash = String(doc?.file_hash || "").trim();
    if (!fileHash) continue;
    let hits = [];
    let error = "";
    try {
      const response = await fetch(`${apiBase}/extract/trace/locate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(cookieHeader ? { cookie: cookieHeader } : {}),
        },
        body: JSON.stringify({
          document: doc,
          top_k: 80,
        }),
      });
      if (response.ok) {
        const payload = await response.json().catch(() => ({}));
        hits = Array.isArray(payload?.hits) ? payload.hits : [];
      } else {
        error = `trace_http_${response.status}`;
      }
    } catch (err) {
      error = String(err?.message || err || "trace_request_failed");
    }

    const effectiveHits = hits.length > 0 ? hits : Array.isArray(doc?.trace_hits) ? doc.trace_hits : [];
    const tableCount = effectiveHits.filter((hit) => getTraceKind(hit) === "table").length;
    const imageCount = effectiveHits.filter((hit) => getTraceKind(hit) === "image").length;
    const fieldCount = computeExpectedFieldCount(doc);
    byFileHash.set(fileHash, {
      fileName: String(doc?.file_name || ""),
      fileHash,
      fieldCount,
      tableCount,
      imageCount,
      traceError: error,
      traceHitCount: effectiveHits.length,
      backendDocErrors: Array.isArray(doc?.errors) ? doc.errors : [],
    });
  }
  return byFileHash;
}

async function ensureMobilePage(page) {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await openProtectedTab(page, appUrl, "deepread_extraction");
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  const backToMobileBtn = page.getByRole("button", { name: /返回移动版/ }).first();
  if (await backToMobileBtn.isVisible().catch(() => false)) {
    await backToMobileBtn.click({ timeout: 10_000 });
    await page.waitForTimeout(700);
  }
  await page.getByText("文件解析产物查看").first().waitFor({ state: "visible", timeout: 30_000 });
}

async function countMobileDetailArticles(page) {
  return await page.locator("section").nth(2).locator("article").count();
}

async function collectMobileCountsForDoc(page, fileName) {
  const docButton = page.locator("section").nth(1).getByRole("button", { name: new RegExp(fileName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }).first();
  await docButton.click({ timeout: 20_000 });
  await page.waitForTimeout(350);

  const selectTab = async (name) => {
    await page.getByRole("button", { name }).first().click({ timeout: 10_000 });
    await page.waitForTimeout(220);
  };

  await selectTab("字段");
  const fieldsCount = await countMobileDetailArticles(page);
  const fieldsEmpty = await page.getByText("暂无字段产物").count();

  await selectTab("表格");
  const tablesCount = await countMobileDetailArticles(page);
  const tablesEmpty = await page.getByText("暂无表格产物").count();

  await selectTab("图片");
  const imagesCount = await countMobileDetailArticles(page);
  const imagesEmpty = await page.getByText("暂无图片产物").count();

  return {
    fieldsCount: fieldsEmpty > 0 ? 0 : fieldsCount,
    tablesCount: tablesEmpty > 0 ? 0 : tablesCount,
    imagesCount: imagesEmpty > 0 ? 0 : imagesCount,
  };
}

async function ensureMobilePageRobust(page) {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await openProtectedTab(page, appUrl, "deepread_extraction");
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  await page.waitForFunction(
    () => document.querySelectorAll("section").length >= 2,
    null,
    { timeout: 30_000 },
  );
}

async function countMobileDetailArticlesRobust(page) {
  return await page.evaluate(() => {
    const section = document.querySelectorAll("section")[2];
    if (!section) return 0;
    return section.querySelectorAll("article").length;
  });
}

async function collectMobileCountsForDocRobust(page, fileName, fallbackIndex = 0) {
  const docClicked = await page.evaluate(({ targetName, index }) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const listSection = document.querySelectorAll("section")[1];
    if (!listSection) return false;
    const buttons = Array.from(listSection.querySelectorAll("button"));
    if (buttons.length === 0) return false;
    const target = normalize(targetName);
    const targetNoExt = target.includes(".") ? normalize(target.slice(0, target.lastIndexOf("."))) : target;
    const matched = buttons.find((btn) => {
      const text = normalize(btn.textContent || "");
      return text.includes(target) || (targetNoExt && text.includes(targetNoExt));
    });
    const fallback = Number.isFinite(index) ? buttons[Math.max(0, Math.min(buttons.length - 1, Number(index)))] : null;
    const targetButton = matched || fallback || null;
    if (!targetButton) return false;
    targetButton.click();
    return true;
  }, { targetName: fileName, index: fallbackIndex });
  if (!docClicked) {
    throw new Error(`mobile_doc_not_found:${fileName}`);
  }
  await page.waitForTimeout(350);

  const selectTab = async (index) => {
    const clicked = await page.evaluate((idx) => {
      const detailSection = document.querySelectorAll("section")[2];
      if (!detailSection) return false;
      const tabButtons = detailSection.querySelectorAll("div.grid.grid-cols-3 button");
      const target = tabButtons[idx];
      if (!(target instanceof HTMLButtonElement)) return false;
      target.click();
      return true;
    }, index);
    if (!clicked) {
      throw new Error(`mobile_tab_not_found:${index}`);
    }
    await page.waitForTimeout(220);
  };

  await selectTab(0);
  const fieldsCount = await countMobileDetailArticlesRobust(page);

  await selectTab(1);
  const tablesCount = await countMobileDetailArticlesRobust(page);

  await selectTab(2);
  const imagesCount = await countMobileDetailArticlesRobust(page);

  return {
    fieldsCount,
    tablesCount,
    imagesCount,
  };
}

async function runScenario(page, scenario, cookieHeader) {
  await mark(`scenario_start:${scenario.id}`);
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await mark(`scenario_${scenario.id}:desktop_viewport_set`);
  await openProtectedTab(page, appUrl, "deepread_extraction");
  await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
  await mark(`scenario_${scenario.id}:page_opened_for_reset`);
  await clearFrontendState(page);
  await mark(`scenario_${scenario.id}:frontend_state_cleared`);
  await page.reload({ waitUntil: "domcontentloaded", timeout: 60_000 });
  await mark(`scenario_${scenario.id}:page_reloaded_after_clear`);
  await enterLegacyWorkbench(page);
  await mark(`scenario_${scenario.id}:legacy_workbench_ready`);

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  const startBtn = page.locator('[data-testid="module2-start-extract"]');
  await fileInput.setInputFiles(scenario.files);
  await mark(`scenario_${scenario.id}:files_uploaded:${scenario.files.length}`);
  await page.waitForTimeout(900);
  const createResponsePromise = page
    .waitForResponse(
      (res) =>
        res.url().includes("/extract/jobs/create")
        && res.request().method() === "POST",
      { timeout: createTimeoutMs },
    )
    .catch((err) => err);
  await startBtn.click({ timeout: 20_000 });
  await mark(`scenario_${scenario.id}:start_extract_clicked`);
  const createResponse = await createResponsePromise;
  if (createResponse instanceof Error) {
    throw new Error(`create_response_timeout:${String(createResponse.message || createResponse)}`);
  }
  const createStatus = Number(createResponse.status() || 0);
  const createBodyText = await createResponse.text().catch(() => "");
  const createPayload = parseJsonSafe(createBodyText, {});
  await mark(`scenario_${scenario.id}:create_response:http=${createStatus}`);
  if (createStatus >= 400) {
    throw new Error(`create_http_${createStatus}:${String(createBodyText || "").slice(0, 300)}`);
  }
  const jobId = String(createPayload?.job_id || "").trim();
  if (!jobId) {
    throw new Error("create_payload_missing_job_id");
  }
  await mark(`scenario_${scenario.id}:job_created:${jobId}`);

  const terminalState = await waitForExtractionTerminalByApi(jobId, cookieHeader, terminalTimeoutMs);
  await mark(
    `scenario_${scenario.id}:job_terminal_checked:terminal=${terminalState.terminal}:timedOut=${terminalState.timedOut}:statusCode=${terminalState.statusCode}`,
  );
  if (terminalState.timedOut) {
    throw new Error(`job_terminal_timeout:${jobId}`);
  }

  const terminalPayload = terminalState.payload && typeof terminalState.payload === "object"
    ? terminalState.payload
    : {};
  const terminalJobErrors = Array.isArray(terminalPayload?.errors)
    ? terminalPayload.errors
    : [];
  let docs = Array.isArray(terminalPayload?.documents)
    ? terminalPayload.documents
    : Array.isArray(createPayload?.documents)
      ? createPayload.documents
      : [];
  if (docs.length === 0) {
    const docsFromStorage = await readDocumentsFromStorage(page);
    docs = Array.isArray(docsFromStorage) ? docsFromStorage : [];
    await mark(`scenario_${scenario.id}:docs_loaded_from_storage:${docs.length}`);
  }
  const traceIndex = await createTraceIndexForDocs(docs, cookieHeader);
  await mark(`scenario_${scenario.id}:trace_index_ready:docs=${docs.length}`);

  await ensureMobilePageRobust(page);
  await mark(`scenario_${scenario.id}:mobile_page_ready`);
  const mobileChecks = [];

  for (const [docIndex, doc] of docs.entries()) {
    const fileHash = String(doc?.file_hash || "").trim();
    const expected = traceIndex.get(fileHash) || {
      fileName: String(doc?.file_name || ""),
      fileHash,
      fieldCount: 0,
      tableCount: 0,
      imageCount: 0,
      traceError: "trace_missing",
      traceHitCount: 0,
      backendDocErrors: [],
    };
    const mobile = await collectMobileCountsForDocRobust(page, expected.fileName, docIndex);
    await mark(`scenario_${scenario.id}:mobile_counts:${expected.fileName}:f=${mobile.fieldsCount}:t=${mobile.tablesCount}:i=${mobile.imagesCount}`);

    await page.screenshot({
      path: path.join(
        screenshotDir,
        `${scenario.id}__${expected.fileName.replace(/[<>:"/\\|?*]+/g, "_").slice(0, 80)}.png`,
      ),
      fullPage: true,
    });

    mobileChecks.push({
      fileName: expected.fileName,
      fileHash: expected.fileHash,
      expected: {
        fields: expected.fieldCount,
        tables: expected.tableCount,
        images: expected.imageCount,
      },
      mobile,
      match: {
        fields: mobile.fieldsCount === expected.fieldCount,
        tables: mobile.tablesCount === expected.tableCount,
        images: mobile.imagesCount === expected.imageCount,
      },
      traceHitCount: expected.traceHitCount,
      traceError: expected.traceError,
      backendDocErrors: expected.backendDocErrors,
    });
  }

  await page.setViewportSize(DESKTOP_VIEWPORT);
  await mark(`scenario_done:${scenario.id}`);

  return {
    scenarioId: scenario.id,
    scenarioDescription: scenario.description,
    files: scenario.files.map((item) => path.relative(projectRoot, item).replace(/\\/g, "/")),
    terminal: Boolean(terminalState.terminal),
    terminalStatus: String(terminalPayload?.status || ""),
    terminalJobErrors,
    jobId,
    jobPollElapsedMs: Number(terminalState.elapsedMs || 0),
    jobPollTimeline: Array.isArray(terminalState.timeline) ? terminalState.timeline : [],
    jobPollError: String(terminalState.error || ""),
    docsCount: docs.length,
    docsExpectedMin: scenario.files.length,
    mobileChecks,
  };
}

function summarize(results) {
  const summary = {
    scenarios: results.length,
    scenarioFailures: 0,
    scenarioErrors: 0,
    mobileFieldMismatchDocs: 0,
    mobileTableMismatchDocs: 0,
    mobileImageMismatchDocs: 0,
    backendDocErrorDocs: 0,
    traceErrorDocs: 0,
  };

  for (const result of results) {
    const scenarioFailed =
      Boolean(result.error) ||
      !result.terminal ||
      result.docsCount < result.docsExpectedMin ||
      (Array.isArray(result.terminalJobErrors) && result.terminalJobErrors.length > 0);
    if (scenarioFailed) summary.scenarioFailures += 1;
    if (result.error) summary.scenarioErrors += 1;

    for (const row of result.mobileChecks) {
      if (!row.match.fields) summary.mobileFieldMismatchDocs += 1;
      if (!row.match.tables) summary.mobileTableMismatchDocs += 1;
      if (!row.match.images) summary.mobileImageMismatchDocs += 1;
      if (Array.isArray(row.backendDocErrors) && row.backendDocErrors.length > 0) {
        summary.backendDocErrorDocs += 1;
      }
      if (row.traceError) summary.traceErrorDocs += 1;
    }
  }

  return summary;
}

async function main() {
  await ensureDirs();
  await mark("main_start");
  const resolvedScenarios = await resolveScenarioFiles();
  await mark(`fixtures_resolved:count=${resolvedScenarios.length}`);
  const executablePath = await resolveBrowserExecutablePath();
  await mark(`browser_executable:${executablePath || "builtin"}`);
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  await mark("browser_launched");
  const context = await browser.newContext({ viewport: DESKTOP_VIEWPORT });
  await mark("context_created");
  const page = await context.newPage();
  await mark("page_created");

  const authInfo = await loginForProtectedApp(context, appUrl);
  await mark("auth_ready");
  const cookieHeader = String(authInfo?.cookieHeader || "").trim();

  const results = [];
  for (const scenario of resolvedScenarios) {
    // eslint-disable-next-line no-console
    console.log(`[module2-mobile-web-eval] running ${scenario.id} with ${scenario.files.length} files`);
    try {
      // eslint-disable-next-line no-await-in-loop
      const result = await runScenario(page, scenario, cookieHeader);
      results.push(result);
      await mark(`scenario_report_pushed:${scenario.id}`);
    } catch (error) {
      const errorMessage = String(error?.message || error || "scenario_failed");
      await mark(`scenario_failed:${scenario.id}:${errorMessage}`);
      results.push({
        scenarioId: scenario.id,
        scenarioDescription: scenario.description,
        files: scenario.files.map((item) => path.relative(projectRoot, item).replace(/\\/g, "/")),
        terminal: false,
        terminalStatus: "",
        terminalJobErrors: [],
        jobId: "",
        jobPollElapsedMs: 0,
        jobPollTimeline: [],
        jobPollError: "",
        docsCount: 0,
        docsExpectedMin: scenario.files.length,
        mobileChecks: [],
        error: errorMessage,
      });
    }
  }

  const summary = summarize(results);
  const report = {
    generatedAt: new Date().toISOString(),
    appUrl,
    apiBase,
    outputDir,
    summary,
    results,
  };
  const reportPath = path.join(outputDir, "report.json");
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  await mark(`report_written:${reportPath}`);

  // eslint-disable-next-line no-console
  console.log(JSON.stringify({ reportPath, summary }, null, 2));

  await browser.close();
  await mark("browser_closed");
}

main().catch((error) => {
  // eslint-disable-next-line no-console
  console.error(`[module2-mobile-web-eval] failed: ${String(error?.message || error)}`);
  process.exitCode = 1;
});
