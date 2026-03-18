#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const appUrl = process.env.MODULE2_APP_URL || "http://127.0.0.1:3000";
const apiBase = String(process.env.MODULE2_API_BASE_OVERRIDE || "http://127.0.0.1:8001").trim().replace(/\/+$/, "");
const configuredExecutablePath = String(
  process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH || process.env.PLAYWRIGHT_EXECUTABLE_PATH || "",
).trim();
const outputDir =
  process.env.MODULE2_ASSISTANT_CHECK_OUTPUT_DIR ||
  path.join(projectRoot, ".runlogs", "module2-frontend-assistant-check", new Date().toISOString().replace(/[:.]/g, "-"));
const browserExecutableCandidates = [
  configuredExecutablePath,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);

const defaultScenarios = [
  {
    key: "excel_blocked_preview",
    filePath: path.join(projectRoot, "datasets", "Excel", "2025\u5c71\u4e1c\u7701\u73af\u5883\u7a7a\u6c14\u8d28\u91cf\u76d1\u6d4b\u6570\u636e\u4fe1\u606f.xlsx"),
    questions: [
      "\u8bf7\u76f4\u63a5\u67e5\u770b xlsx_t1 \u8868\u683c\uff0c\u7ad9\u70b9\u540d\u79f0\u4e3a\u6ec1\u5dde\u65b0\u4e8c\u4e2d\u7684 PM10 \u76d1\u6d4b\u503c\u662f\u591a\u5c11\uff1f\u8bf7\u5199\u660e\u8868\u683c\u3001\u9875\u7801\u3001\u8868\u5185\u884c\u53f7\u3001\u539f\u59cb\u884c\u53f7\u548c ref_id\u3002",
      "\u628a\u521a\u624d\u90a3\u4e00\u884c\u91cc\u5df2\u7ecf\u8bc6\u522b\u5230\u7684\u5173\u952e\u5b57\u6bb5\u51c6\u5907\u5165\u5e93\uff0c\u5148\u7ed9\u6211\u770b\u52a8\u4f5c\u9884\u89c8\uff0c\u4e0d\u8981\u76f4\u63a5\u6267\u884c\u3002",
      "\u91cd\u65b0\u5224\u65ad\u4e00\u4e0b\uff1a\u8fd9\u4efd\u6587\u6863\u73b0\u5728\u5927\u81f4\u8bb2\u4e86\u4ec0\u4e48\uff1f\u8bf7\u5148\u5355\u72ec\u8bf4\u660e\u5f53\u524d\u9501\u5b9a\u5bf9\u8c61\uff0c\u518d\u8bf4\u660e\u5168\u5c40\u6982\u89c8\uff0c\u5e76\u533a\u5206\u54ea\u4e9b\u4fe1\u606f\u6bd4\u8f83\u7a33\u5b9a\u3001\u54ea\u4e9b\u8fd8\u9700\u8981\u8c28\u614e\u6838\u5bf9\u3002",
    ],
  },
  {
    key: "image_general_read",
    filePath: path.join(projectRoot, ".runlogs", "module2-assistant-eval", "page4_from_pdf.png"),
    questions: [
      "\u8bf7\u6982\u8ff0\u8fd9\u5f20\u56fe\u7247\u4e2d\u7684\u56fe\u8868\uff0c\u5e76\u5217\u51fa figure_id\u3001\u9875\u7801\u3001\u5173\u952e\u8981\u70b9\uff0c\u4ee5\u53ca\u662f\u5426\u8bc6\u522b\u51fa\u4e86 dataframe \u6216\u53ef\u5f15\u7528\u7684\u6570\u503c\u3002",
      "\u5982\u679c\u73b0\u5728\u8fd8\u6ca1\u6709\u7a33\u5b9a\u7684\u56fe\u8868\u5bf9\u8c61\uff0c\u8bf7\u76f4\u63a5\u5217\u51fa\u4f60\u80fd\u7a33\u5b9a\u786e\u8ba4\u7684\u5b57\u6bb5\u7ea7\u4e8b\u5b9e\uff0c\u5199\u660e\u5b57\u6bb5\u540d\u3001\u503c\u3001ref_id \u548c\u9875\u7801\u3002",
    ],
  },
];

const scenarios = (() => {
  const raw = String(process.env.MODULE2_ASSISTANT_SCENARIOS_JSON || "").trim();
  if (!raw) return defaultScenarios;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : defaultScenarios;
  } catch {
    return defaultScenarios;
  }
})();

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

async function setApiOverride(page) {
  await page.evaluate((base) => {
    try {
      window.localStorage.setItem("module2_api_base_override", String(base || "").trim());
    } catch {
      // ignore
    }
  }, apiBase);
}

async function clearUiState(page) {
  await page.evaluate((base) => {
    try {
      window.localStorage.clear();
      window.sessionStorage.clear();
      window.localStorage.setItem("module2_api_base_override", String(base || "").trim());
    } catch {
      // ignore
    }
  }, apiBase);
}

async function openModulePage(page) {
  await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  await setApiOverride(page);
  await page.reload({ waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  const alreadyReady = (await fileInput.count().catch(() => 0)) > 0;
  if (alreadyReady) return;

  await page.getByRole("button", { name: /\u667a\u80fd\u6587\u6863\u89e3\u6790/ }).first().click({ timeout: 20_000 });
  await page.getByRole("button", { name: /\u975e\u7ed3\u6784\u5316\u6587\u6863\u4fe1\u606f\u9700\u6c42\u6a21\u5757/ }).first().click({ timeout: 20_000 });
  await fileInput.waitFor({ state: "attached", timeout: 90_000 });
}

async function waitStartButtonReady(page) {
  const startBtn = page.getByTestId("module2-start-extract");
  await startBtn.waitFor({ state: "visible", timeout: 35_000 });
  await page.waitForFunction(
    () => {
      const btn = document.querySelector('[data-testid="module2-start-extract"]');
      const fileInput = document.querySelector('[data-testid="module2-file-input"]');
      if (!(btn instanceof HTMLButtonElement)) return false;
      const selectedFromInput = fileInput instanceof HTMLInputElement ? Number(fileInput.files?.length || 0) : 0;
      const countRaw = (document.querySelector('[data-testid="module2-file-count"]')?.textContent || "").trim();
      const countMatch = countRaw.match(/(\d+)\s*\/\s*5/);
      const infoRaw = (document.querySelector('[data-testid="module2-info-message"]')?.textContent || "").trim();
      const infoMatch = infoRaw.match(/\u5df2\u9009\u62e9\s*(\d+)\s*\u4e2a\u6587\u4ef6/);
      const selected = Number(countMatch?.[1] || infoMatch?.[1] || selectedFromInput || 0);
      return selected > 0 && !btn.disabled;
    },
    null,
    { timeout: 30_000 },
  );
}

async function waitAssistantReady(page) {
  const assistantTab = page.getByRole("tab", { name: /\u667a\u80fd\u52a9\u624b/ }).first();
  if ((await assistantTab.count().catch(() => 0)) > 0) {
    await assistantTab.click({ timeout: 20_000 });
  }
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('[aria-label="任务助手视图"][aria-hidden="false"]');
      const input = panel?.querySelector('[data-testid="module2-assistant-input"]');
      return input instanceof HTMLTextAreaElement && !String(input.placeholder || "").includes("\u8bf7\u5148\u62bd\u53d6\u6587\u6863");
    },
    null,
    { timeout: 120_000 },
  );
}

async function runExtraction(page) {
  await waitStartButtonReady(page);
  const createPromise = page.waitForResponse(
    (res) => res.url().includes("/extract/jobs/create") && res.request().method() === "POST",
    { timeout: 600_000 },
  );
  await page.getByTestId("module2-start-extract").click();
  const createResp = await createPromise;
  const createPayload = await createResp.json();
  const jobId = String(createPayload?.job_id || "");
  if (!jobId) {
    throw new Error(`missing_job_id:${JSON.stringify(createPayload)}`);
  }

  const startedAt = Date.now();
  while (Date.now() - startedAt < 600_000) {
    const resp = await fetch(`${apiBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`);
    const payload = await resp.json();
    if (resp.ok && payload?.terminal) {
      await waitAssistantReady(page);
      await page.waitForTimeout(1200);
      return payload;
    }
    await page.waitForTimeout(1500);
  }

  throw new Error(`extract_timeout:${jobId}`);
}

async function askAssistant(page, question, screenshotPath) {
  const assistantTab = page.getByRole("tab", { name: /\u667a\u80fd\u52a9\u624b/ }).first();
  if ((await assistantTab.count().catch(() => 0)) > 0) {
    await assistantTab.click({ timeout: 20_000 });
  }
  const activePanel = page.locator('[aria-label="任务助手视图"][aria-hidden="false"]').first();
  const input = activePanel.getByTestId("module2-assistant-input");
  const sendBtn = activePanel.getByTestId("module2-assistant-send");
  await input.fill(question);
  await sendBtn.click();
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('[aria-label="任务助手视图"][aria-hidden="false"]');
      const btn = panel?.querySelector('[data-testid="module2-assistant-send"]');
      return btn instanceof HTMLButtonElement && String(btn.title || "").includes("\u505c\u6b62");
    },
    null,
    { timeout: 30_000 },
  ).catch(() => false);
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('[aria-label="任务助手视图"][aria-hidden="false"]');
      const btn = panel?.querySelector('[data-testid="module2-assistant-send"]');
      return btn instanceof HTMLButtonElement && String(btn.title || "") === "\u53d1\u9001";
    },
    null,
    { timeout: 240_000 },
  );
  await page.waitForTimeout(1200);

  const snapshot = await page.evaluate(() => {
    const dialog = document.querySelector('[data-testid="module2-assistant-dialog"]');
    const dialogItems = dialog
      ? Array.from(dialog.children).map((node) => (node.textContent || "").trim()).filter(Boolean)
      : [];
    const bodyText = (document.body.innerText || "").trim();
    const semanticHits = Array.from(document.querySelectorAll("*"))
      .map((node) => (node.textContent || "").trim())
      .filter(
        (text) =>
          text.includes("\u72b6\u6001\uff1a\u5df2\u963b\u585e") ||
          text.includes("\u5f53\u524d\u5019\u9009\u6570\uff1a") ||
          text.includes("OCR \u4e8b\u5b9e\u7ec4") ||
          text.includes("\u4e0a\u4e0b\u6587\u9501\u5b9a") ||
          text.includes("\u9501\u5b9a\u5f3a\u5ea6:") ||
          text.includes("\u8bc6\u522b\u5c42\u7ea7:"),
      );
    return {
      dialog_tail: dialogItems.slice(-6),
      body_excerpt: bodyText.slice(Math.max(0, bodyText.length - 2500)),
      semantic_hits: Array.from(new Set(semanticHits)).slice(0, 20),
    };
  });

  await page.screenshot({ path: screenshotPath, fullPage: true });
  return snapshot;
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const executablePath = await resolveBrowserExecutablePath();
  const browser = await chromium.launch({
    headless: process.env.MODULE2_HEADLESS !== "0",
    executablePath: executablePath || undefined,
  });
  const context = await browser.newContext({ viewport: { width: 1560, height: 980 } });
  const page = await context.newPage();
  const report = [];
  const consoleErrors = [];
  const pageErrors = [];
  const serverErrors = [];
  let fatalError = "";

  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    consoleErrors.push({
      time: new Date().toISOString(),
      text: msg.text(),
    });
  });
  page.on("pageerror", (error) => {
    pageErrors.push({
      time: new Date().toISOString(),
      text: String(error?.message || error || ""),
    });
  });
  page.on("response", (res) => {
    const status = Number(res.status() || 0);
    if (status < 500) return;
    const request = res.request();
    serverErrors.push({
      time: new Date().toISOString(),
      status,
      method: request.method(),
      url: res.url(),
    });
  });

  try {
    for (const scenario of scenarios) {
      const scenarioReport = {
        scenario: scenario.key,
        file_path: scenario.filePath,
        extraction_status: "",
        extraction_terminal: false,
        questions: [],
        error: "",
      };
      try {
        await clearUiState(page);
        await openModulePage(page);
        await page.setInputFiles('[data-testid="module2-file-input"]', scenario.filePath);
        await page.waitForTimeout(500);
        const extraction = await runExtraction(page);
        scenarioReport.extraction_status = String(extraction?.status || "");
        scenarioReport.extraction_terminal = Boolean(extraction?.terminal);
        for (let index = 0; index < scenario.questions.length; index += 1) {
          const question = String(scenario.questions[index] || "").trim();
          const screenshotPath = path.join(outputDir, `${scenario.key}_q${index + 1}.png`);
          const snapshot = await askAssistant(page, question, screenshotPath);
          scenarioReport.questions.push({
            question,
            screenshot_path: screenshotPath,
            snapshot,
          });
        }
      } catch (error) {
        scenarioReport.error = String(error?.message || error || "scenario_failed");
        try {
          await page.screenshot({ path: path.join(outputDir, `${scenario.key}_error.png`), fullPage: true });
        } catch {
          // ignore
        }
      }
      report.push(scenarioReport);
      if (scenarioReport.error) {
        fatalError = scenarioReport.error;
        break;
      }
    }
  } catch (error) {
    fatalError = String(error?.message || error || "frontend_check_failed");
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }

  const outputPath = path.join(outputDir, "report.json");
  await fs.writeFile(
    outputPath,
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        app_url: appUrl,
        api_base: apiBase,
        browser_executable_path: executablePath,
        output_dir: outputDir,
        fatal_error: fatalError,
        diagnostics: {
          console_errors: consoleErrors,
          page_errors: pageErrors,
          server_errors: serverErrors,
        },
        report,
      },
      null,
      2,
    ),
    "utf-8",
  );

  console.log(JSON.stringify({ output_path: outputPath, report }, null, 2));
  if (fatalError) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
