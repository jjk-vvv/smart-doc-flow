import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const appUrl = "http://127.0.0.1:3001";
const gatewayUrl = "http://127.0.0.1:3001";
const outputDir = path.join(projectRoot, ".runlogs", "module2-frontend-text-regression");
const playwrightExecutablePath = String(process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH || "").trim();
const browserExecutableCandidates = [
  playwrightExecutablePath,
  String(process.env.PLAYWRIGHT_EXECUTABLE_PATH || "").trim(),
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);

const SUMMARY_PLACEHOLDER = "上传文件并执行抽取后，摘要会自动展示。";
const SUMMARY_LOADING = "正在生成文档摘要...";

const allScenarios = [
  {
    name: "single-txt",
    files: [
      path.join(projectRoot, "datasets", "txt", "2024年国民经济和社会发展统计公报（节选）.txt"),
    ],
  },
  {
    name: "multi-txt-md",
    files: [
      path.join(projectRoot, "datasets", "txt", "2024年国民经济和社会发展统计公报（节选）.txt"),
      path.join(projectRoot, "datasets", "md", "2024年卫生健康事业发展统计公报.md"),
    ],
  },
];
const scenarioFilter = String(process.env.MODULE2_TEXT_SCENARIO || "").trim();
const scenarios = scenarioFilter
  ? allScenarios.filter((item) => item.name === scenarioFilter)
  : allScenarios;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseJsonSafe(raw) {
  const text = String(raw || "").trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
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

async function clearBackendCache(request) {
  await request
    .post(`${gatewayUrl}/extract/cache/clear?scope=all`, {
      timeout: 180_000,
    })
    .catch(() => null);
}

async function clickIfVisible(locator) {
  if (await locator.isVisible().catch(() => false)) {
    await locator.click({ timeout: 10_000 }).catch(() => null);
    return true;
  }
  return false;
}

async function textContent(locator) {
  return String((await locator.textContent().catch(() => "")) || "").trim();
}

async function openResultsTab(page) {
  const button = page.getByTestId("module2-smart-tab-results");
  if ((await button.count().catch(() => 0)) > 0) {
    await button.scrollIntoViewIfNeeded().catch(() => null);
    await button.click({ timeout: 10_000, force: true }).catch(() => null);
    await page
      .getByTestId("module2-start-extract")
      .waitFor({ state: "visible", timeout: 10_000 })
      .catch(() => null);
  }
}

async function openAssistantTab(page) {
  const button = page.getByTestId("module2-smart-tab-assistant");
  if ((await button.count().catch(() => 0)) > 0) {
    await button.scrollIntoViewIfNeeded().catch(() => null);
    await button.click({ timeout: 10_000, force: true }).catch(() => null);
    await page
      .getByTestId("module2-assistant-input")
      .waitFor({ state: "visible", timeout: 10_000 })
      .catch(() => null);
  }
}

async function openAssistantCompanion(page) {
  const panel = page.locator('#module2-assistant-companion');
  if (await panel.isVisible().catch(() => false)) {
    return;
  }
  const button = page.locator('[aria-controls="module2-assistant-companion"]').first();
  if ((await button.count().catch(() => 0)) > 0) {
    await button.scrollIntoViewIfNeeded().catch(() => null);
    await button.click({ timeout: 10_000, force: true }).catch(() => null);
    await panel.waitFor({ state: "visible", timeout: 10_000 }).catch(() => null);
  }
}

async function collectScenarioState(page) {
  const infoMessage = await textContent(page.getByTestId("module2-info-message"));
  const summaryText = await textContent(page.locator('[data-testid="module2-summary-text"]:visible').first());
  const fieldChipCount = await page.getByTestId("module2-field-chip").count().catch(() => 0);
  const switcherButtons = page.getByTestId("module2-document-switcher-button");
  const switcherCount = await switcherButtons.count().catch(() => 0);
  const switcherVisible = switcherCount > 0
    ? await switcherButtons.first().isVisible().catch(() => false)
    : false;
  const fileCountText = await textContent(page.getByTestId("module2-file-count"));
  return {
    infoMessage,
    summaryText,
    fieldChipCount,
    switcherCount,
    switcherVisible,
    fileCountText,
    currentUrl: page.url(),
  };
}

function isSummaryReady(summaryText) {
  const text = String(summaryText || "").trim();
  if (!text) return false;
  if (text === SUMMARY_PLACEHOLDER) return false;
  if (text === SUMMARY_LOADING) return false;
  return true;
}

function buildCompactResult(result) {
  return {
    scenario: result.scenario,
    ok: result.ok,
    uiOutcomeOk: result.uiOutcomeOk,
    summaryReadyOk: result.summaryReadyOk,
    createJob: {
      ok: result.createJob?.ok || false,
      status: result.createJob?.status || 0,
      jobId: result.createJob?.jobId || "",
    },
    jobTerminal: {
      ok: result.jobTerminal?.ok || false,
      status: result.jobTerminal?.payload?.status || "",
      completed: result.jobTerminal?.payload?.progress?.completed_files || 0,
      total: result.jobTerminal?.payload?.progress?.total_files || 0,
      docs: Array.isArray(result.jobTerminal?.payload?.documents) ? result.jobTerminal.payload.documents.length : 0,
      elapsedMs: result.jobTerminal?.elapsedMs || 0,
    },
    summaryOutcome: {
      ok: result.summaryOutcome?.ok || false,
      elapsedMs: result.summaryOutcome?.elapsedMs || 0,
      preview: String(result.summaryOutcome?.summaryText || "").slice(0, 120),
    },
    summaryNodeCount: Array.isArray(result.summaryDomNodes) ? result.summaryDomNodes.length : 0,
    errorResponses: Array.isArray(result.errorResponses) ? result.errorResponses : [],
    failedRequests: Array.isArray(result.failedRequests) ? result.failedRequests : [],
    consoleErrors: Array.isArray(result.consoleErrors) ? result.consoleErrors : [],
    pageErrors: Array.isArray(result.pageErrors) ? result.pageErrors : [],
    fieldChipCount: Number(result.fieldChipCount || 0),
    switcherCount: Number(result.switcherCount || 0),
    switcherVisible: Boolean(result.switcherVisible),
    infoMessage: String(result.infoMessage || ""),
  };
}

function buildCompactReport(results) {
  return {
    generatedAt: new Date().toISOString(),
    scenarios: results.map(buildCompactResult),
  };
}

async function waitForExtractionOutcome(page, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const state = await collectScenarioState(page);
    if (state.fieldChipCount > 0 || state.switcherVisible || isSummaryReady(state.summaryText)) {
      return {
        ok: true,
        elapsedMs: Date.now() - startedAt,
        ...state,
      };
    }
    await sleep(1500);
  }

  return {
    ok: false,
    elapsedMs: timeoutMs,
    ...(await collectScenarioState(page)),
  };
}

async function waitForCreateJobResponse(page) {
  const response = await page
    .waitForResponse(
      (item) => item.url().includes("/extract/jobs/create") && item.request().method() === "POST",
      { timeout: 60_000 }
    )
    .catch(() => null);

  if (!response) {
    return {
      seen: false,
      ok: false,
      status: 0,
      jobId: "",
      payload: null,
      bodyPreview: "",
    };
  }

  const bodyText = String((await response.text().catch(() => "")) || "");
  const payload = parseJsonSafe(bodyText);
  return {
    seen: true,
    ok: response.ok(),
    status: response.status(),
    jobId: String(payload?.job_id || "").trim(),
    payload,
    bodyPreview: bodyText.slice(0, 1000),
  };
}

async function waitForJobTerminal(context, jobId, timeoutMs = 300_000) {
  const startedAt = Date.now();
  let lastStatus = 0;
  let lastPayload = null;

  while (Date.now() - startedAt < timeoutMs) {
    const response = await context.request
      .get(`${appUrl}/extract/jobs/status/${jobId}?include_documents=true`, {
        timeout: 60_000,
      })
      .catch(() => null);

    if (response) {
      lastStatus = response.status();
      lastPayload = parseJsonSafe(await response.text().catch(() => "")) || null;
      if (response.ok() && lastPayload?.terminal) {
        return {
          ok: true,
          timedOut: false,
          status: lastStatus,
          elapsedMs: Date.now() - startedAt,
          payload: lastPayload,
        };
      }
    }

    await sleep(2000);
  }

  return {
    ok: false,
    timedOut: true,
    status: lastStatus,
    elapsedMs: Date.now() - startedAt,
    payload: lastPayload,
  };
}

async function waitForSummaryReady(page, timeoutMs = 60_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    await openAssistantTab(page);
    await openAssistantCompanion(page);
    const summaryText = await textContent(page.locator('[data-testid="module2-summary-text"]:visible').first());
    if (isSummaryReady(summaryText)) {
      return {
        ok: true,
        elapsedMs: Date.now() - startedAt,
        summaryText,
      };
    }
    await sleep(1500);
  }

  await openAssistantTab(page);
  await openAssistantCompanion(page);
  return {
    ok: false,
    elapsedMs: timeoutMs,
    summaryText: await textContent(page.locator('[data-testid="module2-summary-text"]:visible').first()),
  };
}

async function collectSummaryDomNodes(page) {
  await openAssistantTab(page);
  await openAssistantCompanion(page);
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-testid="module2-summary-text"]')).map((node, index) => {
      const el = node;
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return {
        index,
        text: (el.textContent || "").trim(),
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        width: rect.width,
        height: rect.height,
      };
    })
  ).catch(() => []);
}

async function runScenario(context, scenario) {
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const errorResponses = [];
  const summaryResponses = [];
  const statusResponses = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });
  page.on("requestfailed", (req) => {
    failedRequests.push({
      url: req.url(),
      method: req.method(),
      failure: req.failure()?.errorText || "",
    });
  });
  page.on("response", (res) => {
    if (res.url().includes("/extract/jobs/status/")) {
      const target = res;
      target
        .text()
        .then((text) => {
          const payload = parseJsonSafe(text) || null;
          statusResponses.push({
            url: target.url(),
            method: target.request().method(),
            status: target.status(),
            terminal: Boolean(payload?.terminal),
            jobStatus: String(payload?.status || ""),
            completedFiles: Number(payload?.progress?.completed_files || 0),
            totalFiles: Number(payload?.progress?.total_files || 0),
            docs: Array.isArray(payload?.documents) ? payload.documents.length : 0,
          });
        })
        .catch(() => {
          statusResponses.push({
            url: target.url(),
            method: target.request().method(),
            status: target.status(),
            terminal: false,
            jobStatus: "",
            completedFiles: 0,
            totalFiles: 0,
            docs: 0,
          });
        });
    }
    if (res.url().includes("/extract/summarize")) {
      summaryResponses.push({
        url: res.url(),
        method: res.request().method(),
        status: res.status(),
      });
    }
    if (res.status() >= 400) {
      errorResponses.push({
        url: res.url(),
        method: res.request().method(),
        status: res.status(),
      });
    }
  });

  await clearBackendCache(context.request);
  await openProtectedTab(page, appUrl, "deepread_extraction", {
    timeout: 90_000,
    networkIdleTimeout: 30_000,
  });

  const fileInput = page.getByTestId("module2-file-input");
  const startButton = page.getByTestId("module2-start-extract");
  const clearButton = page.getByTestId("module2-clear-data");

  await fileInput.waitFor({ state: "attached", timeout: 60_000 });
  await startButton.waitFor({ state: "visible", timeout: 60_000 });

  await clickIfVisible(clearButton);
  await sleep(1000);
  await page.setInputFiles('[data-testid="module2-file-input"]', scenario.files);
  await sleep(1500);

  const jobCreatePromise = waitForCreateJobResponse(page);
  await startButton.click({ timeout: 20_000 });
  const createJob = await jobCreatePromise;
  const jobTerminal = createJob.jobId
    ? await waitForJobTerminal(context, createJob.jobId, 300_000)
    : {
        ok: false,
        timedOut: false,
        status: 0,
        elapsedMs: 0,
        payload: null,
      };

  await openResultsTab(page);
  if (scenario.files.length > 1) {
    await page
      .getByTestId("module2-document-switcher-button")
      .first()
      .waitFor({ state: "visible", timeout: 45_000 })
      .catch(() => null);
  }
  const outcome = await waitForExtractionOutcome(page, 45_000);
  const summaryOutcome = await waitForSummaryReady(page, 60_000);
  const summaryDomNodes = await collectSummaryDomNodes(page);
  const finalState = await collectScenarioState(page);
  const summaryReadyOk = Boolean(
    summaryOutcome.ok
    && Array.isArray(summaryDomNodes)
    && summaryDomNodes.some((item) => isSummaryReady(item?.text))
  );
  const noBrowserErrors =
    consoleErrors.length === 0
    && pageErrors.length === 0
    && failedRequests.length === 0
    && errorResponses.length === 0;

  const screenshotPath = path.join(outputDir, `${scenario.name}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.close();

  return {
    scenario: scenario.name,
    files: scenario.files,
    screenshotPath,
    consoleErrors,
    pageErrors,
    failedRequests,
    errorResponses,
    summaryResponses,
    statusResponses,
    createJob,
    jobTerminal,
    summaryOutcome,
    summaryDomNodes,
    summaryReadyOk,
    ...finalState,
    uiOutcomeOk: outcome.ok,
    ok: Boolean(createJob.ok && jobTerminal.ok && outcome.ok && summaryReadyOk && noBrowserErrors),
  };
}

async function main() {
  await ensureDir(outputDir);
  const resolvedBrowserExecutablePath = await resolveBrowserExecutablePath();
  const browser = await chromium.launch({
    headless: true,
    executablePath: resolvedBrowserExecutablePath || undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
  });
  await context.addInitScript(() => {
    try {
      window.localStorage.clear();
    } catch {
      // ignore
    }
    try {
      window.sessionStorage.clear();
    } catch {
      // ignore
    }
  });

  try {
    await loginForProtectedApp(context, appUrl, {
      account: "regression.local+ui@example.com",
      password: "Regression@123",
    });

    const results = [];
    for (const scenario of scenarios) {
      results.push(await runScenario(context, scenario));
    }

    const fullReportPath = path.join(outputDir, "report.json");
    const compactReportPath = path.join(outputDir, "report.summary.json");
    const compactReport = buildCompactReport(results);
    await fs.writeFile(fullReportPath, JSON.stringify({ results }, null, 2), "utf-8");
    await fs.writeFile(compactReportPath, JSON.stringify(compactReport, null, 2), "utf-8");
    console.log(JSON.stringify({ fullReportPath, compactReportPath, ...compactReport }, null, 2));
  } finally {
    await context.close();
    await browser.close();
  }
}

await main();
