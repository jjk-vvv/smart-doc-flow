#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const appUrl = process.env.MODULE2_APP_URL || "http://127.0.0.1:3001";
const apiBase = String(process.env.MODULE2_API_BASE_OVERRIDE || "http://127.0.0.1:3001").trim().replace(/\/+$/, "").replace(/\/extract$/i, "");
const configuredExecutablePath = String(
  process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH || process.env.PLAYWRIGHT_EXECUTABLE_PATH || "",
).trim();
const outputDir =
  process.env.MODULE2_ASSISTANT1_CHECK_OUTPUT_DIR ||
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
    filePath: path.join(projectRoot, "datasets", "Excel", "2025山东省环境空气质量监测数据信息.xlsx"),
    questions: [
      "请直接查看 xlsx_t1 表格，站点名称为滁州新二中的 PM10 监测值是多少？请写明表格、页码、表内行号、原始行号和 ref_id。",
      "把刚才那\u4e00行里已经识别到的关键字段准备入库，先给我看动作预览，不要直接执行。",
      "重新判断\u4e00下：这份文档现在大致讲了什么？请先单独说明当前锁定对象，再说明全局概览，并区分哪些信息比较稳定、哪些还需要谨慎核对。",
    ],
  },
  {
    key: "image_general_read",
    filePath: path.join(projectRoot, ".runlogs", "module2-assistant-eval", "page4_from_pdf.png"),
    questions: [
      "请概述这张图片中的图表，并列出 figure_id、页码、关键要点，以及是否识别出了 dataframe 或可引用的数值。",
      "如果现在还没有稳定的图表对象，请直接列出你能稳定确认的字段级事实，写明字段名、值、ref_id 和页码。",
    ],
  },
];

const scenarios = (() => {
  const raw = String(process.env.MODULE2_ASSISTANT1_SCENARIOS_JSON || "").trim();
  if (!raw) return defaultScenarios;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : defaultScenarios;
  } catch {
    return defaultScenarios;
  }
})();

let authCookieHeader = "";

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

async function fileExists(targetPath) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
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
  await openProtectedTab(page, appUrl, "deepread_extraction");
  await setApiOverride(page);
  await page.reload({ waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  const deepreadMenu = page.getByTestId("sidebar-menu-deepread");
  const extractionMenu = page.getByTestId("sidebar-submenu-deepread_extraction");
  const alreadyReady = (await fileInput.count().catch(() => 0)) > 0;
  if (alreadyReady) return;
  if (await deepreadMenu.isVisible().catch(() => false)) {
    await deepreadMenu.click({ timeout: 20_000 });
  }
  if (await extractionMenu.isVisible().catch(() => false)) {
    await extractionMenu.click({ timeout: 20_000 });
  }
  if ((await fileInput.count().catch(() => 0)) > 0) return;

  await page.getByRole("button", { name: /智能文档解析/ }).first().click({ timeout: 20_000 });
  await page.getByRole("button", { name: /非结构化文档信息需求模块/ }).first().click({ timeout: 20_000 });
  await fileInput.waitFor({ state: "attached", timeout: 90_000 });
}

async function waitStartButtonReady(page) {
  const startBtn = page.getByTestId("module2-start-extract");
  await page.waitForFunction(() => {
    const btn = document.querySelector('[data-testid="module2-start-extract"]');
    if (!(btn instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(btn);
    return (
      btn.offsetWidth > 0 &&
      btn.offsetHeight > 0 &&
      style.visibility !== "hidden" &&
      style.display !== "none"
    );
  }, { timeout: 35_000 });
  await page.waitForFunction(
    () => {
      const btn = document.querySelector('[data-testid="module2-start-extract"]');
      const fileInput = document.querySelector('[data-testid="module2-file-input"]');
      if (!(btn instanceof HTMLButtonElement)) return false;
      const selectedFromInput = fileInput instanceof HTMLInputElement ? Number(fileInput.files?.length || 0) : 0;
      const countRaw = (document.querySelector('[data-testid="module2-file-count"]')?.textContent || "").trim();
      const countMatch = countRaw.match(/(\d+)\s*\/\s*5/);
      const infoRaw = (document.querySelector('[data-testid="module2-info-message"]')?.textContent || "").trim();
      const infoMatch = infoRaw.match(/已选择\s*(\d+)\s*个文件/);
      const selected = Number(countMatch?.[1] || infoMatch?.[1] || selectedFromInput || 0);
      return selected > 0 && !btn.disabled;
    },
    null,
    { timeout: 30_000 },
  );
}

async function waitAssistantReady(page) {
  const assistantTabV2 = page.getByTestId("module2-smart-tab-assistant");
  if ((await assistantTabV2.count().catch(() => 0)) > 0) {
    await assistantTabV2.scrollIntoViewIfNeeded().catch(() => {});
    await assistantTabV2.click({ timeout: 20_000, force: true });
    await page.locator('[data-testid="module2-assistant-input"]:visible').first().waitFor({
      state: "visible",
      timeout: 120_000,
    });
    await page.waitForFunction(() => {
      const input = document.querySelector('[data-testid="module2-assistant-input"]:not([disabled])');
      return input instanceof HTMLTextAreaElement;
    }, { timeout: 30_000 });
    return;
  }
  const assistantTab = page.getByRole("tab", { name: /智能助手/ }).first();
  if ((await assistantTab.count().catch(() => 0)) > 0) {
    await assistantTab.click({ timeout: 20_000 });
  }
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('[aria-label="任务助手视图"][aria-hidden="false"]');
      const input = panel?.querySelector('[data-testid="module2-assistant-input"]');
      return input instanceof HTMLTextAreaElement && !String(input.placeholder || "").includes("请先抽取文档");
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
    const resp = await fetch(`${apiBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`, {
      headers: authCookieHeader ? { cookie: authCookieHeader } : {},
    });
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
  const assistantTabV2 = page.getByTestId("module2-smart-tab-assistant");
  if ((await assistantTabV2.count().catch(() => 0)) > 0) {
    await assistantTabV2.scrollIntoViewIfNeeded().catch(() => {});
    await assistantTabV2.click({ timeout: 20_000, force: true });
    const input = page.locator('[data-testid="module2-assistant-input"]:visible').first();
    const sendBtn = page.locator('[data-testid="module2-assistant-send"]:visible').first();
    await input.fill(question);
    await sendBtn.click();
    await page.waitForFunction(() => {
      const buttons = Array.from(document.querySelectorAll('[data-testid="module2-assistant-send"]'));
      const visibleButton = buttons.find((node) => {
        if (!(node instanceof HTMLElement)) return false;
        return node.offsetParent !== null;
      });
      return visibleButton instanceof HTMLButtonElement && visibleButton.disabled;
    }, { timeout: 240_000 }).catch(() => false);
    await page.waitForTimeout(1200);

    const snapshot = await page.evaluate(() => {
      const dialog = document.querySelector('[data-testid="module2-assistant-dialog"]');
      const dialogItems = dialog
        ? Array.from(dialog.children).map((node) => (node.textContent || "").trim()).filter(Boolean)
        : [];
      const bodyText = (document.body.innerText || "").trim();
      return {
        dialog_tail: dialogItems.slice(-6),
        body_excerpt: bodyText.slice(Math.max(0, bodyText.length - 2500)),
        semantic_hits: [],
      };
    });

    await page.screenshot({ path: screenshotPath, fullPage: true });
    return snapshot;
  }
  const assistantTab = page.getByRole("tab", { name: /智能助手/ }).first();
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
      return btn instanceof HTMLButtonElement && String(btn.title || "").includes("停止");
    },
    null,
    { timeout: 30_000 },
  ).catch(() => false);
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('[aria-label="任务助手视图"][aria-hidden="false"]');
      const btn = panel?.querySelector('[data-testid="module2-assistant-send"]');
      return btn instanceof HTMLButtonElement && String(btn.title || "") === "发送";
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
          text.includes("状态：已阻塞") ||
          text.includes("当前候选数：") ||
          text.includes("OCR 事实组") ||
          text.includes("上下文锁定") ||
          text.includes("锁定强度:") ||
          text.includes("识别层级:"),
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
  const authSession = await loginForProtectedApp(context, appUrl);
  authCookieHeader = authSession.cookieHeader || "";
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
        skipped: "",
      };
      if (!(await fileExists(scenario.filePath))) {
        scenarioReport.skipped = "missing_fixture";
        report.push(scenarioReport);
        continue;
      }
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
        auth_account: authSession.account,
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
