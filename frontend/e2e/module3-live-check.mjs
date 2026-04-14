import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, devices } from "playwright";
import mammoth from "mammoth";
import * as XLSX from "xlsx";

import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const XLSX_API =
  XLSX && typeof XLSX.read === "function"
    ? XLSX
    : XLSX && XLSX.default && typeof XLSX.default.read === "function"
      ? XLSX.default
      : XLSX;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputRoot = path.join(
  projectRoot,
  ".runlogs",
  "module3-live-check",
  runTag,
);

const defaultDatasetRoot = path.join(projectRoot, "datasets", "\u6a21\u5757\u4e09\u6d4b\u8bd5\u6587\u4ef6");
const fallbackDatasetRoot = path.join(
  projectRoot,
  ".codex-temp",
  "module3-test",
);

const desktopBaseUrl = String(
  process.env.MODULE3_WEB_BASE_URL ||
    process.env.SMART_DOC_FLOW_WEB_URL ||
    "http://127.0.0.1:3000",
).trim();

const mobileBaseUrl = String(
  process.env.MODULE3_MOBILE_BASE_URL ||
    process.env.SMART_DOC_FLOW_APP_URL ||
    "http://127.0.0.1:3002",
).trim();

const maxRunWaitMs = Math.max(
  120_000,
  Number(process.env.MODULE3_RUN_TIMEOUT_MS || 600_000),
);

const pollIntervalMs = Math.max(
  1_500,
  Number(process.env.MODULE3_RUN_POLL_MS || 3_000),
);

const useFetchCredentialsShim =
  String(process.env.MODULE3_FORCE_FETCH_SHIM || "").trim() === "1";

const defaultRequirements =
  "请基于资料文档精准填充模板，缺失信息保持空白，不要臆造；优先保留中文表述与原始统计口径。";

const browserExecutableCandidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
];

function nowIso() {
  return new Date().toISOString();
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function writeJson(filePath, payload) {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf8");
}

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function resolveBrowserExecutablePath() {
  const requested = String(process.env.PLAYWRIGHT_EXECUTABLE_PATH || "").trim();
  if (requested && (await exists(requested))) {
    return requested;
  }
  for (const candidate of browserExecutableCandidates) {
    if (await exists(candidate)) {
      return candidate;
    }
  }
  return null;
}

async function listFilesSafe(dirPath) {
  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isFile())
      .map((entry) => path.join(dirPath, entry.name))
      .sort((a, b) => String(a).localeCompare(String(b), "zh-CN"));
  } catch {
    return [];
  }
}

function looksLikeTemplate(filePath) {
  const lower = path.basename(filePath).toLowerCase();
  return (
    (lower.endsWith(".xlsx") || lower.endsWith(".docx")) &&
    (lower.includes("模板") || lower.includes("template"))
  );
}

function looksLikeExpected(filePath) {
  const lower = path.basename(filePath).toLowerCase();
  return (
    (lower.endsWith(".xlsx") || lower.endsWith(".docx")) &&
    (lower.includes("答案") || lower.includes("standard") || lower.includes("filled"))
  );
}

function looksLikeSource(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return [".docx", ".xlsx", ".txt", ".md"].includes(ext);
}

async function readRequestTextSafe(requestDirOrFile) {
  if (!requestDirOrFile) return defaultRequirements;

  let requestFile = "";
  try {
    const stat = await fs.stat(requestDirOrFile);
    if (stat.isFile()) {
      requestFile = requestDirOrFile;
    } else {
      const files = await listFilesSafe(requestDirOrFile);
      requestFile =
        files.find((file) => [".txt", ".md"].includes(path.extname(file).toLowerCase())) ||
        files[0] ||
        "";
    }
  } catch {
    requestFile = "";
  }

  if (!requestFile) return defaultRequirements;

  try {
    const text = String(await fs.readFile(requestFile, "utf8")).trim();
    return text || defaultRequirements;
  } catch {
    return defaultRequirements;
  }
}

async function resolveDatasetFromStructuredCase(caseRoot) {
  const sourceDir = path.join(caseRoot, "source_docs");
  const templateDir = path.join(caseRoot, "templates");
  const expectedDir = path.join(caseRoot, "standard_answers");
  const requestDir = path.join(caseRoot, "user_requests");

  const templateCandidates = (await listFilesSafe(templateDir)).filter((file) =>
    [".xlsx", ".docx"].includes(path.extname(file).toLowerCase()),
  );
  const templates = templateCandidates.filter((file) => !looksLikeExpected(file));
  const expectedFiles = (await listFilesSafe(expectedDir)).filter((file) =>
    [".xlsx", ".docx"].includes(path.extname(file).toLowerCase()),
  );
  const sources = (await listFilesSafe(sourceDir)).filter(looksLikeSource);
  const requirements = await readRequestTextSafe(requestDir);

  if (!templateCandidates.length || !expectedFiles.length || !sources.length) {
    throw new Error(
      `dataset_case_missing_files:${caseRoot}:template_candidates=${templateCandidates.length}:template=${templates.length}:expected=${expectedFiles.length}:sources=${sources.length}`,
    );
  }

  return {
    root: caseRoot,
    template: templates[0] || templateCandidates[0],
    expected: expectedFiles[0],
    sources,
    source: sources[0],
    requirements,
  };
}

async function resolveDatasetFromFlatCase(caseRoot) {
  const files = await listFilesSafe(caseRoot);
  const template =
    files.find(looksLikeTemplate) ||
    files.find((file) => [".xlsx", ".docx"].includes(path.extname(file).toLowerCase())) ||
    "";
  const expected =
    files.find(looksLikeExpected) ||
    "";
  const sources = files.filter((file) => {
    if (!looksLikeSource(file)) return false;
    return file !== template && file !== expected;
  });
  const requestFile =
    files.find((file) => [".txt", ".md"].includes(path.extname(file).toLowerCase()) && file.includes("用户")) ||
    files.find((file) => [".txt", ".md"].includes(path.extname(file).toLowerCase())) ||
    "";
  const requirements = await readRequestTextSafe(requestFile);

  if (!template || !expected || !sources.length) {
    throw new Error(
      `dataset_flat_missing_files:${caseRoot}:template=${Boolean(template)}:expected=${Boolean(expected)}:sources=${sources.length}`,
    );
  }

  return {
    root: caseRoot,
    template,
    expected,
    sources,
    source: sources[0],
    requirements,
  };
}

async function resolveDataset() {
  const requestedCaseRoot = String(process.env.MODULE3_DATASET_CASE_ROOT || "").trim();
  if (requestedCaseRoot) {
    const structuredSourceDir = path.join(requestedCaseRoot, "source_docs");
    if (await exists(structuredSourceDir)) {
      return await resolveDatasetFromStructuredCase(requestedCaseRoot);
    }
    return await resolveDatasetFromFlatCase(requestedCaseRoot);
  }

  const rootEntries = await fs.readdir(defaultDatasetRoot, { withFileTypes: true }).catch(() => []);
  const caseDirs = rootEntries
    .filter((entry) => entry.isDirectory() && /^case_repo\d+$/i.test(entry.name))
    .map((entry) => path.join(defaultDatasetRoot, entry.name))
    .sort((a, b) => String(a).localeCompare(String(b), "en-US"));
  if (caseDirs.length > 0) {
    const firstCaseRoot = caseDirs[0];
    const structuredSourceDir = path.join(firstCaseRoot, "source_docs");
    if (await exists(structuredSourceDir)) {
      return await resolveDatasetFromStructuredCase(firstCaseRoot);
    }
    return await resolveDatasetFromFlatCase(firstCaseRoot);
  }

  try {
    return await resolveDatasetFromFlatCase(defaultDatasetRoot);
  } catch {
    return await resolveDatasetFromFlatCase(fallbackDatasetRoot);
  }
}

function sanitizeFilename(value = "") {
  return String(value || "").replace(/[<>:"/\\|?*\u0000-\u001f]+/g, "_");
}

function relativePath(targetPath) {
  return path.relative(projectRoot, targetPath).replace(/\\/g, "/");
}

function pushIssue(issueBucket, scope, detail) {
  issueBucket.push({
    scope,
    detail: String(detail || "").slice(0, 4000),
    recorded_at: nowIso(),
  });
}

function installPageObservers(page, issues, label) {
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      pushIssue(issues, `${label}:console`, msg.text());
    }
  });
  page.on("pageerror", (error) => {
    pushIssue(issues, `${label}:pageerror`, error?.stack || error?.message || error);
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure();
    pushIssue(
      issues,
      `${label}:requestfailed`,
      `${request.method()} ${request.url()} :: ${failure?.errorText || "unknown_error"}`,
    );
  });
}

async function takeScreenshot(page, dirPath, name, summary) {
  const filePath = path.join(dirPath, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  summary.screenshots.push(relativePath(filePath));
  return filePath;
}

async function removeFusionStorage(context) {
  await context.addInitScript(() => {
    try {
      window.localStorage.removeItem("module3_fusion_grid_state");
      window.sessionStorage.removeItem("module3_fusion_grid_state");
    } catch {
      // Ignore storage cleanup failures in tests.
    }
  });
}

async function prepareMobileAppState(context) {
  await context.addInitScript(() => {
    try {
      window.localStorage.setItem("smart_doc_flow.has_seen_onboarding", "true");
      window.localStorage.setItem("smart_doc_flow.frontend_app.active_tab", "fusion");
    } catch {
      // Ignore localStorage write failures in restricted contexts.
    }
  });
}

async function patchModule3FetchCredentials(context) {
  await context.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? String(input)
            : String(input?.url || "");
      const needsModule3Credentials =
        /\/module3(\/|$|\?)/.test(url) || /:8001\/module3(\/|$|\?)/.test(url);
      if (!needsModule3Credentials) {
        return nativeFetch(input, init);
      }
      return nativeFetch(input, {
        ...(init || {}),
        credentials: "include",
      });
    };
  });
}

async function applyFetchCredentialsShimIfNeeded(context) {
  if (!useFetchCredentialsShim) return;
  await patchModule3FetchCredentials(context);
}

async function waitForEnabled(locator, timeoutMs = 30_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await locator.isVisible().catch(() => false)) {
      if (await locator.isEnabled().catch(() => false)) {
        return;
      }
    }
    await locator.page().waitForTimeout(250);
  }
  throw new Error(`wait_for_enabled_timeout:${locator.toString()}`);
}

async function waitForUploadResponse(page, matcher, trigger) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      matcher.test(response.url()),
    { timeout: 90_000 },
  );
  await trigger();
  const response = await responsePromise;
  const payload = await response.json().catch(() => ({}));
  return {
    ok: response.ok(),
    status: response.status(),
    url: response.url(),
    payload,
  };
}

async function waitForRunCreate(page, trigger) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/module3\/run$/.test(response.url()),
    { timeout: 90_000 },
  );
  await trigger();
  const response = await responsePromise;
  const payload = await response.json().catch(() => ({}));
  return {
    ok: response.ok(),
    status: response.status(),
    url: response.url(),
    payload,
  };
}

async function pollRunStatus(context, baseUrl, runId) {
  const history = [];
  const deadline = Date.now() + maxRunWaitMs;
  let lastPayload = null;
  let lastError = null;

  while (Date.now() <= deadline) {
    try {
      const response = await context.request.get(
        `${new URL(baseUrl).origin}/module3/run/${encodeURIComponent(runId)}`,
      );
      const text = await response.text();
      const payload = JSON.parse(text);
      history.push({
        recorded_at: nowIso(),
        http_status: response.status(),
        payload,
      });
      lastPayload = payload;
      lastError = null;
      if (["done", "failed", "cancelled", "cancel_requested"].includes(String(payload?.status || ""))) {
        return {
          final: payload,
          history,
          error: null,
        };
      }
    } catch (error) {
      lastError = String(error?.stack || error?.message || error);
      history.push({
        recorded_at: nowIso(),
        error: lastError,
      });
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  return {
    final: lastPayload,
    history,
    error: lastError || `run_status_timeout:${runId}`,
  };
}

async function readWorkbookCellMap(workbookPath) {
  const workbookBinary = await fs.readFile(workbookPath);
  const workbook = XLSX_API.read(workbookBinary, {
    type: "buffer",
    cellFormula: false,
    cellHTML: false,
    cellNF: false,
    cellText: true,
    raw: false,
  });
  const cellMap = new Map();

  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    if (!sheet || !sheet["!ref"]) continue;
    const range = XLSX_API.utils.decode_range(sheet["!ref"]);
    for (let row = range.s.r; row <= range.e.r; row += 1) {
      for (let col = range.s.c; col <= range.e.c; col += 1) {
        const address = XLSX_API.utils.encode_cell({ r: row, c: col });
        const cell = sheet[address];
        if (!cell) continue;
        const value =
          cell.w != null
            ? String(cell.w).trim()
            : cell.v == null
              ? ""
              : String(cell.v).trim();
        if (!value) continue;
        cellMap.set(`${sheetName}!${address}`, value);
      }
    }
  }

  return cellMap;
}

function normalizeComparableNumericText(value = "") {
  let text = String(value ?? "").trim().replace(/,/g, "");
  if (!text) return null;
  if (!/^[+-]?(?:(?:\d+\.?\d*)|(?:\.\d+))(?:[eE][+-]?\d+)?$/.test(text)) {
    return null;
  }

  let sign = "";
  if (text.startsWith("+") || text.startsWith("-")) {
    sign = text.startsWith("-") ? "-" : "";
    text = text.slice(1);
  }

  let exponent = 0;
  const exponentIndex = text.search(/[eE]/);
  if (exponentIndex >= 0) {
    exponent = Number(text.slice(exponentIndex + 1));
    if (!Number.isInteger(exponent)) return null;
    text = text.slice(0, exponentIndex);
  }

  let [integerPart, fractionalPart = ""] = text.split(".");
  integerPart = integerPart || "0";

  let digits = `${integerPart}${fractionalPart}`.replace(/^0+(?=\d)/, "");
  if (!digits || /^0+$/.test(digits)) {
    return "0";
  }

  let decimalIndex = integerPart.length + exponent;
  if (decimalIndex <= 0) {
    digits = `${"0".repeat(-decimalIndex)}${digits}`;
    decimalIndex = 0;
  } else if (decimalIndex >= digits.length) {
    digits = `${digits}${"0".repeat(decimalIndex - digits.length)}`;
  }

  integerPart = decimalIndex > 0 ? digits.slice(0, decimalIndex) : "0";
  fractionalPart = decimalIndex < digits.length ? digits.slice(decimalIndex) : "";
  integerPart = integerPart.replace(/^0+(?=\d)/, "") || "0";
  fractionalPart = fractionalPart.replace(/0+$/, "");

  const normalized = fractionalPart ? `${integerPart}.${fractionalPart}` : integerPart;
  return normalized === "0" ? "0" : `${sign}${normalized}`;
}

function workbookCellValuesEqual(actualValue, expectedValue) {
  if (actualValue === expectedValue) {
    return { equal: true, mode: "exact" };
  }

  const normalizedActual = normalizeComparableNumericText(actualValue);
  const normalizedExpected = normalizeComparableNumericText(expectedValue);
  if (
    normalizedActual != null &&
    normalizedExpected != null &&
    normalizedActual === normalizedExpected
  ) {
    return { equal: true, mode: "numeric_equivalent" };
  }

  return { equal: false, mode: "different" };
}

async function compareWorkbooks(actualPath, expectedPath) {
  const actual = await readWorkbookCellMap(actualPath);
  const expected = await readWorkbookCellMap(expectedPath);
  const mismatches = [];
  const missing = [];
  const extra = [];
  let matched = 0;
  let numericEquivalent = 0;

  for (const [key, expectedValue] of expected.entries()) {
    const actualValue = actual.get(key);
    if (actualValue == null) {
      missing.push({ cell: key, expected: expectedValue });
      continue;
    }
    const comparison = workbookCellValuesEqual(actualValue, expectedValue);
    if (comparison.equal) {
      matched += 1;
      if (comparison.mode === "numeric_equivalent") {
        numericEquivalent += 1;
      }
      continue;
    }
    mismatches.push({
      cell: key,
      expected: expectedValue,
      actual: actualValue,
    });
  }

  for (const [key, actualValue] of actual.entries()) {
    if (!expected.has(key)) {
      extra.push({ cell: key, actual: actualValue });
    }
  }

  return {
    expected_non_empty: expected.size,
    actual_non_empty: actual.size,
    matched,
    numeric_equivalent: numericEquivalent,
    mismatched: mismatches.length,
    missing: missing.length,
    extra: extra.length,
    accuracy_vs_expected_non_empty:
      expected.size > 0 ? Number((matched / expected.size).toFixed(4)) : 1,
    mismatch_samples: mismatches.slice(0, 30),
    missing_samples: missing.slice(0, 30),
    extra_samples: extra.slice(0, 30),
  };
}

function normalizeDocxText(text = "") {
  return String(text || "")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{2,}/g, "\n")
    .trim();
}

function tokenizeDocxLines(text = "") {
  return normalizeDocxText(text)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

async function extractDocxText(docxPath) {
  const buffer = await fs.readFile(docxPath);
  const extracted = await mammoth.extractRawText({ buffer });
  return normalizeDocxText(extracted?.value || "");
}

async function compareDocxDocuments(actualPath, expectedPath) {
  const [actualText, expectedText] = await Promise.all([
    extractDocxText(actualPath),
    extractDocxText(expectedPath),
  ]);

  const actualLines = tokenizeDocxLines(actualText);
  const expectedLines = tokenizeDocxLines(expectedText);
  const actualSet = new Set(actualLines);

  const missing = [];
  let matched = 0;
  for (const line of expectedLines) {
    if (actualSet.has(line)) {
      matched += 1;
    } else {
      missing.push({ expected: line });
    }
  }

  return {
    compare_kind: "docx_line_match",
    expected_non_empty: expectedLines.length,
    actual_non_empty: actualLines.length,
    matched,
    mismatched: missing.length,
    missing: missing.length,
    extra: Math.max(0, actualLines.length - matched),
    accuracy_vs_expected_non_empty:
      expectedLines.length > 0 ? Number((matched / expectedLines.length).toFixed(4)) : 1,
    missing_samples: missing.slice(0, 50),
    expected_text_length: expectedText.length,
    actual_text_length: actualText.length,
  };
}

async function compareOutputs(actualPath, expectedPath) {
  const actualExt = path.extname(actualPath).toLowerCase();
  const expectedExt = path.extname(expectedPath).toLowerCase();
  if (actualExt === ".xlsx" && expectedExt === ".xlsx") {
    return {
      compare_kind: "xlsx_cell_match",
      ...(await compareWorkbooks(actualPath, expectedPath)),
    };
  }
  if (actualExt === ".docx" && expectedExt === ".docx") {
    return await compareDocxDocuments(actualPath, expectedPath);
  }
  return {
    compare_kind: "unsupported",
    expected_non_empty: 0,
    actual_non_empty: 0,
    matched: 0,
    mismatched: 0,
    missing: 0,
    extra: 0,
    accuracy_vs_expected_non_empty: 0,
    warning: `unsupported_compare_ext:actual=${actualExt}:expected=${expectedExt}`,
  };
}

async function runDesktopFlow(browser, dataset, account) {
  const dirPath = path.join(outputRoot, "web");
  await ensureDir(dirPath);

  const summary = {
    channel: "web",
    base_url: desktopBaseUrl,
    account,
    fetch_credentials_shim: useFetchCredentialsShim,
    screenshots: [],
    upload: {},
    run_create: null,
    run_status: null,
    preview_opened: false,
    download: null,
    issues: [],
  };

  const context = await browser.newContext({
    viewport: { width: 1560, height: 980 },
    locale: "zh-CN",
    acceptDownloads: true,
  });
  await removeFusionStorage(context);
  await applyFetchCredentialsShimIfNeeded(context);

  const page = await context.newPage();
  installPageObservers(page, summary.issues, "web");

  try {
    await loginForProtectedApp(context, desktopBaseUrl, { account });
    await openProtectedTab(page, desktopBaseUrl, "fusion");
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
    await takeScreenshot(page, dirPath, "01-open-fusion", summary);

    const templateInput = page.locator('input[type="file"][accept=".xlsx,.docx"]').first();
    const docsetInput = page
      .locator('input[type="file"][accept=".xlsx,.docx,.txt,.md"]')
      .first();
    const startButton = page.getByRole("button", { name: /开始填充|创建中/ }).first();

    const templateUpload = await waitForUploadResponse(
      page,
      /\/module3\/template\/upload$/,
      async () => {
        await templateInput.setInputFiles(dataset.template);
      },
    );
    summary.upload.template = templateUpload;
    await page.waitForTimeout(1200);
    await takeScreenshot(page, dirPath, "02-template-uploaded", summary);

    const docsetUpload = await waitForUploadResponse(
      page,
      /\/module3\/docset\/upload$/,
      async () => {
        await docsetInput.setInputFiles(dataset.sources);
      },
    );
    summary.upload.docset = docsetUpload;
    await page.waitForTimeout(1200);
    await takeScreenshot(page, dirPath, "03-docset-uploaded", summary);

    await page
      .getByPlaceholder(/请输入你对这次填充的要求（选填）/)
      .fill(dataset.requirements || defaultRequirements);
    await waitForEnabled(startButton, 20_000);

    const runCreate = await waitForRunCreate(page, async () => {
      await startButton.click();
    });
    summary.run_create = runCreate;
    await page.waitForTimeout(1500);
    await takeScreenshot(page, dirPath, "04-run-started", summary);

    const runId = String(runCreate?.payload?.run_id || "").trim();
    if (!runId) {
      throw new Error("desktop_run_id_missing");
    }

    const runStatus = await pollRunStatus(context, desktopBaseUrl, runId);
    summary.run_status = runStatus;

    await page.waitForTimeout(3500);
    await takeScreenshot(page, dirPath, "05-run-finished", summary);

    const finalStatus = String(runStatus?.final?.status || "").trim();
    if (finalStatus !== "done") {
      summary.issues.push({
        at: nowIso(),
        type: "desktop_run_not_done",
        status: finalStatus,
        error: String(runStatus?.final?.error || ""),
      });
      return summary;
    }

    const previewButton = page.locator('button[title*="预览"]').first();
    await previewButton.click({ force: true });
    await page.waitForTimeout(2500);
    summary.preview_opened = true;
    await takeScreenshot(page, dirPath, "06-preview-opened", summary);

    const downloadButton = page.locator('button[title*="下载"]').first();
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 60_000 }),
      downloadButton.click({ force: true }),
    ]);
    const suggestedFilename = sanitizeFilename(download.suggestedFilename() || `${runId}.xlsx`);
    const savedPath = path.join(dirPath, suggestedFilename);
    await download.saveAs(savedPath);
    summary.download = {
      suggested_filename: suggestedFilename,
      saved_path: relativePath(savedPath),
    };
    await takeScreenshot(page, dirPath, "07-after-download", summary);

    return {
      ...summary,
      downloaded_file: savedPath,
    };
  } finally {
    await context.close();
  }
}

async function runMobileFlow(browser, dataset, account) {
  const dirPath = path.join(outputRoot, "mobile");
  await ensureDir(dirPath);

  const summary = {
    channel: "mobile",
    base_url: mobileBaseUrl,
    account,
    fetch_credentials_shim: useFetchCredentialsShim,
    screenshots: [],
    upload: {},
    run_create: null,
    run_status: null,
    preview_opened: false,
    download: null,
    issues: [],
  };

  const context = await browser.newContext({
    ...devices["iPhone 13 Pro"],
    locale: "zh-CN",
    acceptDownloads: true,
  });
  await removeFusionStorage(context);
  await prepareMobileAppState(context);
  await applyFetchCredentialsShimIfNeeded(context);

  const page = await context.newPage();
  installPageObservers(page, summary.issues, "mobile");

  try {
    await loginForProtectedApp(context, mobileBaseUrl, { account });
    await openProtectedTab(page, mobileBaseUrl, "fusion");
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
    const enterHomeButton = page.getByRole("button", { name: /直接进入首页|进入首页/ }).first();
    if (await enterHomeButton.isVisible({ timeout: 1200 }).catch(() => false)) {
      await enterHomeButton.click({ force: true });
      await page.waitForTimeout(1000);
      const fusionTab = page.getByRole("button", { name: /融合/ }).first();
      if (await fusionTab.isVisible({ timeout: 2000 }).catch(() => false)) {
        await fusionTab.click({ force: true });
      }
      await page.waitForTimeout(800);
    }
    await takeScreenshot(page, dirPath, "01-open-fusion", summary);

    await page.getByRole("button", { name: "模板管理" }).click({ force: true });
    const templateInput = page.locator('input[type="file"][accept=".xlsx,.docx"]').first();
    const templateUpload = await waitForUploadResponse(
      page,
      /\/module3\/template\/upload$/,
      async () => {
        await templateInput.setInputFiles(dataset.template);
      },
    );
    summary.upload.template = templateUpload;
    await page.waitForTimeout(1200);
    await takeScreenshot(page, dirPath, "02-template-uploaded", summary);
    await page.getByRole("button", { name: /关闭模板管理|关闭/ }).click().catch(() => {});
    const blockingOverlay = page.locator('div.fixed.inset-0.z-[55]').first();
    if (await blockingOverlay.isVisible({ timeout: 800 }).catch(() => false)) {
      await page.keyboard.press("Escape").catch(() => {});
      const fallbackClose = page.getByRole("button", { name: /关闭|取消|返回/ }).first();
      if (await fallbackClose.isVisible({ timeout: 800 }).catch(() => false)) {
        await fallbackClose.click({ force: true }).catch(() => {});
      }
      await page.waitForTimeout(300);
    }

    await page.getByRole("button", { name: "文档集管理" }).click({ force: true });
    const docsetInput = page
      .locator('input[type="file"][accept=".xlsx,.docx,.txt,.md"]')
      .first();
    const docsetUpload = await waitForUploadResponse(
      page,
      /\/module3\/docset\/upload$/,
      async () => {
        await docsetInput.setInputFiles(dataset.sources);
      },
    );
    summary.upload.docset = docsetUpload;
    await page.waitForTimeout(1200);
    await takeScreenshot(page, dirPath, "03-docset-uploaded", summary);
    await page.getByRole("button", { name: /关闭文档集管理|关闭/ }).click().catch(() => {});

    await page.getByRole("textbox", { name: "用户要求" }).fill(dataset.requirements || defaultRequirements);
    const startButton = page.getByRole("button", { name: /开始填充|创建中/ }).first();
    await waitForEnabled(startButton, 20_000);

    const runCreate = await waitForRunCreate(page, async () => {
      await startButton.click();
    });
    summary.run_create = runCreate;
    await page.waitForTimeout(1500);
    await takeScreenshot(page, dirPath, "04-run-started", summary);

    const runId = String(runCreate?.payload?.run_id || "").trim();
    if (!runId) {
      throw new Error("mobile_run_id_missing");
    }

    const runStatus = await pollRunStatus(context, mobileBaseUrl, runId);
    summary.run_status = runStatus;

    await page.waitForTimeout(3500);
    await takeScreenshot(page, dirPath, "05-run-finished", summary);

    const finalStatus = String(runStatus?.final?.status || "").trim();
    if (finalStatus !== "done") {
      summary.issues.push({
        at: nowIso(),
        type: "mobile_run_not_done",
        status: finalStatus,
        error: String(runStatus?.final?.error || ""),
      });
      return summary;
    }

    const openTaskCenterPanel = async () => {
      const taskCenterBtn = page.locator('button[aria-label="打开任务中心"]').first();
      await taskCenterBtn.waitFor({ state: "visible", timeout: 8_000 });
      await taskCenterBtn.evaluate((button) => {
        if (button instanceof HTMLElement) {
          button.click();
        }
      });
      await page.waitForTimeout(700);

      const settingsTitle = page.getByRole("heading", { name: /设置/ }).first();
      if (await settingsTitle.isVisible({ timeout: 700 }).catch(() => false)) {
        const closeSettingsBtn = page.getByRole("button", { name: /关闭/ }).first();
        if (await closeSettingsBtn.isVisible({ timeout: 1200 }).catch(() => false)) {
          await closeSettingsBtn.click({ force: true });
          await page.waitForTimeout(500);
          await taskCenterBtn.evaluate((button) => {
            if (button instanceof HTMLElement) {
              button.click();
            }
          });
          await page.waitForTimeout(700);
        }
      }

      await page.getByText("任务中心").first().waitFor({ state: "visible", timeout: 8_000 });
    };

    const collapseToast = page.getByRole("button", { name: /收起/ }).first();
    if (await collapseToast.isVisible({ timeout: 1800 }).catch(() => false)) {
      await collapseToast.click({ force: true });
      await page.waitForTimeout(500);
    } else {
      await page.waitForTimeout(2200);
    }

    await openTaskCenterPanel();
    await takeScreenshot(page, dirPath, "06-task-center", summary);

    const previewResultBtn = page.locator('button[aria-label="预览结果"]').first();
    await previewResultBtn.waitFor({ state: "visible", timeout: 12_000 });
    await previewResultBtn.click({ force: true });
    await page.waitForTimeout(2500);
    summary.preview_opened = true;
    await takeScreenshot(page, dirPath, "07-preview-opened", summary);

    await page.getByRole("button", { name: "返回" }).click().catch(() => {});
    await page.waitForTimeout(800);
    await openTaskCenterPanel();

    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 60_000 }),
      page.locator('button[aria-label="下载结果"]').first().click({ force: true }),
    ]);
    const suggestedFilename = sanitizeFilename(download.suggestedFilename() || `${runId}.xlsx`);
    const savedPath = path.join(dirPath, suggestedFilename);
    await download.saveAs(savedPath);
    summary.download = {
      suggested_filename: suggestedFilename,
      saved_path: relativePath(savedPath),
    };
    await takeScreenshot(page, dirPath, "08-after-download", summary);

    return {
      ...summary,
      downloaded_file: savedPath,
    };
  } finally {
    await context.close();
  }
}

async function main() {
  await ensureDir(outputRoot);
  const dataset = await resolveDataset();
  const account = String(
    process.env.PLAYWRIGHT_AUTH_ACCOUNT ||
      process.env.SMART_DOC_FLOW_E2E_ACCOUNT ||
      "regression.local+ui@example.com",
  ).trim();

  const summary = {
    started_at: nowIso(),
    output_root: relativePath(outputRoot),
    dataset: {
      root: relativePath(dataset.root),
      template: relativePath(dataset.template),
      sources: (Array.isArray(dataset.sources) ? dataset.sources : [dataset.source])
        .filter(Boolean)
        .map((item) => relativePath(item)),
      expected: relativePath(dataset.expected),
      requirements: String(dataset.requirements || ""),
    },
    account,
    web: null,
    mobile: null,
    compare: null,
    ok: false,
  };

  const executablePath = await resolveBrowserExecutablePath();
  const browser = await chromium.launch({
    headless: String(process.env.MODULE3_HEADED || "").trim() === "1" ? false : true,
    executablePath: executablePath || undefined,
  });

  try {
    let web = null;
    let mobile = null;

    try {
      web = await runDesktopFlow(browser, dataset, account);
      summary.web = web;
    } catch (error) {
      summary.web = {
        channel: "web",
        base_url: desktopBaseUrl,
        error: String(error?.stack || error?.message || error),
      };
    }

    try {
      mobile = await runMobileFlow(browser, dataset, account);
      summary.mobile = mobile;
    } catch (error) {
      summary.mobile = {
        channel: "mobile",
        base_url: mobileBaseUrl,
        error: String(error?.stack || error?.message || error),
      };
    }

    const compareCandidate =
      web?.downloaded_file && (await exists(web.downloaded_file))
        ? web.downloaded_file
        : mobile?.downloaded_file && (await exists(mobile.downloaded_file))
          ? mobile.downloaded_file
          : "";
    if (compareCandidate) {
      summary.compare = await compareOutputs(compareCandidate, dataset.expected);
      await writeJson(
        path.join(outputRoot, "compare_report.json"),
        summary.compare,
      );
    }

    summary.ok =
      String(web?.run_status?.final?.status || "") === "done" &&
      String(mobile?.run_status?.final?.status || "") === "done";
  } finally {
    await browser.close();
  }

  summary.finished_at = nowIso();
  await writeJson(path.join(outputRoot, "summary.json"), summary);
  console.log(JSON.stringify(summary, null, 2));
}

main().catch(async (error) => {
  const payload = {
    ok: false,
    output_root: relativePath(outputRoot),
    error: String(error?.stack || error?.message || error),
    failed_at: nowIso(),
  };
  await writeJson(path.join(outputRoot, "failure.json"), payload);
  console.error(JSON.stringify(payload, null, 2));
  process.exitCode = 1;
});



