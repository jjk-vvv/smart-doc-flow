#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");

const rerunRoot = path.resolve(
  process.env.MODULE2_XLSX_RERUN_ROOT
    || path.join(projectRoot, "runtime-data-rerun", "20260411_165004", "xlsx_rerun_forced_fresh"),
);
const appUrl = String(process.env.MODULE2_APP_URL || "http://127.0.0.1:3002").trim().replace(/\/+$/, "");
const gatewayPort = String(process.env.GATEWAY_PORT || "3001").trim() || "3001";
const apiBase = String(process.env.MODULE2_API_BASE_OVERRIDE || `http://127.0.0.1:${gatewayPort}`).trim().replace(/\/+$/, "");
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.join(projectRoot, ".runlogs", "xlsx-web-monitor", runTag);
const docSwitchWaitMs = Math.max(0, Number.parseInt(process.env.MODULE2_XLSX_DOC_WAIT_MS || "2500", 10) || 2500);
const docLimit = Math.max(1, Number.parseInt(process.env.MODULE2_XLSX_DOC_LIMIT || "999", 10) || 999);
const browserExecutablePath = String(
  process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH
  || process.env.PLAYWRIGHT_EXECUTABLE_PATH
  || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
).trim();

const normalizeArtifactUrl = (rawUrl) => {
  const value = String(rawUrl || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("/")) return `${apiBase}${value}`;
  return `${apiBase}/${value.replace(/^\/+/, "")}`;
};

const toSelectedFile = ({ finalPayload, summary }, index) => {
  const doc = finalPayload.documents[0] || {};
  const jobFile = finalPayload.files[0] || {};
  const fileName = String(doc.file_name || `xlsx-${index + 1}.xlsx`).trim() || `xlsx-${index + 1}.xlsx`;
  const ext = path.extname(fileName).replace(/^\./, "").toLowerCase() || "xlsx";

  return {
    key: `xlsx-monitor-${index + 1}-${String(doc.file_hash || "").slice(0, 12) || "unknown"}`,
    name: fileName,
    size: Math.max(
      1024,
      Number(summary.xlsx_source_total_rows || 0) * Math.max(1, Number(summary.xlsx_source_total_cols || 1)),
    ),
    lastModified: 1712810000000 + index,
    ext,
    artifactUrl: normalizeArtifactUrl(jobFile.artifact_url),
    artifactPath: String(jobFile.artifact_path || "").trim(),
  };
};

const readPayloads = async () => {
  const entries = await fs.readdir(rerunRoot, { withFileTypes: true });
  const folders = entries
    .filter((item) => item.isDirectory())
    .map((item) => item.name)
    .sort()
    .slice(0, docLimit);
  const out = [];
  for (const folder of folders) {
    const base = path.join(rerunRoot, folder);
    const finalPayload = JSON.parse(await fs.readFile(path.join(base, "final_payload.json"), "utf8"));
    const summary = JSON.parse(await fs.readFile(path.join(base, "summary.json"), "utf8"));
    out.push({ folder, base, finalPayload, summary });
  }
  return out;
};

const collectPageMetrics = async (page) => {
  return await page.evaluate(() => {
    const allText = String(document.body?.innerText || "");
    const activeButton = document.querySelector('[data-testid="module2-document-switcher-button"][aria-current="true"]');
    const traceGroupIds = Array.from(document.querySelectorAll('[data-testid^="module2-trace-group-"]'))
      .map((element) => element.getAttribute("data-testid"))
      .filter(Boolean);

    const runtime = window.luckysheet;
    let luckysheetInfo = null;
    if (runtime && typeof runtime.getluckysheetfile === "function") {
      try {
        luckysheetInfo = runtime.getluckysheetfile().map((sheet) => ({
          name: String(sheet?.name || ""),
          row: Number(sheet?.row || 0),
          column: Number(sheet?.column || 0),
          dataRows: Array.isArray(sheet?.data) ? sheet.data.length : 0,
          hasData: Array.isArray(sheet?.data) && sheet.data.some(
            (row) => Array.isArray(row) && row.some((cell) => {
              if (cell == null) return false;
              if (typeof cell === "string") return cell.trim().length > 0;
              if (typeof cell === "number" || typeof cell === "boolean") return true;
              if (typeof cell === "object") {
                const raw = cell?.v ?? cell?.m ?? cell?.f;
                return raw != null && String(raw).trim().length > 0;
              }
              return false;
            }),
          ),
        }));
      } catch {
        luckysheetInfo = null;
      }
    }

    return {
      href: window.location.href,
      title: document.title,
      activeButtonText: activeButton?.textContent?.replace(/\s+/g, " ").trim() || "",
      fieldChipCount: document.querySelectorAll('[data-testid="module2-field-chip"]').length,
      traceCardCount: document.querySelectorAll('[data-testid="module2-trace-card"]').length,
      traceGroupIds,
      summaryText: Array.from(document.querySelectorAll('[data-testid="module2-summary-text"]'))
        .map((element) => String(element.textContent || "").trim())
        .find(Boolean) || "",
      hasResultPromptText: allText.includes("结果提示"),
      warningTexts: allText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .filter((text) =>
          text.includes("上游解析")
          || text.includes("限流")
          || text.includes("质量")
          || text.includes("自动过滤"),
        )
        .slice(0, 8),
      hasTraceTitle: allText.includes("原文定位"),
      hasLuckysheetRoot: Boolean(document.querySelector(".luckysheet")),
      luckysheetSheetTabCount: document.querySelectorAll(".luckysheet-sheets-menu li").length,
      luckysheetInfo,
    };
  });
};

const seedWorkbenchStorage = async (page, documents, session) => {
  await page.evaluate(
    ({ docs, sessionData, apiBaseOverride }) => {
      window.localStorage.setItem("smart_doc_flow.has_seen_onboarding", "true");
      window.localStorage.setItem("smart_doc_flow.frontend_app.active_tab", "deepread_extraction");
      window.localStorage.setItem("module2_api_base_override", apiBaseOverride);
      window.localStorage.setItem("module2_last_documents", JSON.stringify(docs));
      window.localStorage.setItem("module2_last_updated", new Date().toISOString());
      window.localStorage.setItem("module2_workbench_session_v1", JSON.stringify(sessionData));
    },
    {
      docs: documents,
      sessionData: session,
      apiBaseOverride: apiBase,
    },
  );
};

const clickDocumentByIndex = async (page, index, fileName) => {
  const clicked = await page.evaluate(
    ({ idx, expectedName }) => {
      const byTestId = Array.from(
        document.querySelectorAll('[data-testid="module2-document-switcher-button"]'),
      );
      if (byTestId[idx] instanceof HTMLButtonElement) {
        byTestId[idx].click();
        return true;
      }

      const normalizedName = String(expectedName || "").trim();
      const allButtons = Array.from(document.querySelectorAll("button"));
      const byName = allButtons.find((button) => {
        const text = String(button.textContent || "").replace(/\s+/g, " ").trim();
        return normalizedName && text.includes(normalizedName);
      });
      if (byName instanceof HTMLButtonElement) {
        byName.click();
        return true;
      }

      const queueHost = Array.from(document.querySelectorAll("section,div,aside")).find((el) => {
        const text = String(el.textContent || "");
        return text.includes("文档队列") || text.includes("解析文档列表");
      });
      if (queueHost) {
        const queueButtons = Array.from(queueHost.querySelectorAll("button")).filter((button) => {
          const text = String(button.textContent || "");
          return text.includes(".xlsx") || text.includes(".xls");
        });
        if (queueButtons[idx] instanceof HTMLButtonElement) {
          queueButtons[idx].click();
          return true;
        }
      }
      return false;
    },
    { idx: index, expectedName: fileName },
  );
  return Boolean(clicked);
};

const ensureExtractionWorkbench = async (page) => {
  const isReady = await page.evaluate(() => {
    const bodyText = String(document.body?.innerText || "");
    return bodyText.includes("文档队列") || bodyText.includes("解析文档列表");
  });
  if (isReady) return;

  const deepreadMenu = page.getByRole("button", { name: /智能文档解析/ }).first();
  if (await deepreadMenu.isVisible().catch(() => false)) {
    await deepreadMenu.click({ timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(500);
  }

  const extractionButton = page.getByRole("button", { name: /AI信息提取|非结构化文档/ }).first();
  if (await extractionButton.isVisible().catch(() => false)) {
    await extractionButton.click({ timeout: 15_000 }).catch(() => {});
  }

  await page.evaluate(() => {
    const clickByText = (patterns) => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const target = buttons.find((button) => {
        const text = String(button.textContent || "").replace(/\s+/g, " ").trim();
        return patterns.some((pattern) => text.includes(pattern));
      });
      if (target instanceof HTMLButtonElement) {
        target.click();
        return true;
      }
      return false;
    };
    clickByText(["智能文档解析"]);
    clickByText(["AI信息提取", "非结构化文档"]);
  });
  await page.waitForTimeout(800);

  await page.waitForFunction(
    () => {
      const bodyText = String(document.body?.innerText || "");
      return bodyText.includes("文档队列") || bodyText.includes("解析文档列表");
    },
    undefined,
    { timeout: 60_000 },
  );
};

const main = async () => {
  await fs.mkdir(outputDir, { recursive: true });
  const payloads = await readPayloads();
  const documents = payloads.map(({ finalPayload }) => finalPayload.documents[0]).filter(Boolean);
  if (documents.length === 0) {
    throw new Error(`no_xlsx_payloads_found:${rerunRoot}`);
  }

  const selectedFiles = payloads.map(toSelectedFile);
  const session = {
    version: 1,
    activeDocIndex: 0,
    activeDocFileHash: String(documents[0]?.file_hash || ""),
    smartUnitTab: "results",
    selectedFiles,
    officePreviewMap: {},
    extractionJob: null,
  };

  const browser = await chromium.launch({
    headless: true,
    executablePath: browserExecutablePath || undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1100 },
  });
  await loginForProtectedApp(context, appUrl);
  const page = await context.newPage();

  const consoleLogs = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on("console", (message) => {
    const location = message.location ? message.location() : null;
    consoleLogs.push({
      type: message.type(),
      text: message.text(),
      location,
    });
  });
  page.on("pageerror", (error) => {
    pageErrors.push(String(error?.message || error));
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status >= 400) {
      failedResponses.push({
        status,
        url: response.url(),
        method: response.request().method(),
      });
    }
  });

  await openProtectedTab(page, appUrl, "deepread_extraction");
  await seedWorkbenchStorage(page, documents, session);
  await openProtectedTab(page, appUrl, "deepread_extraction");
  await ensureExtractionWorkbench(page);
  await page.waitForLoadState("networkidle", { timeout: 45_000 }).catch(() => {});
  await page.waitForFunction(
    () => {
      const hasLegacyDocSwitcher =
        document.querySelectorAll('[data-testid="module2-document-switcher-button"]').length >= 1;
      const bodyText = String(document.body?.innerText || "");
      const hasDesktopQueue = bodyText.includes("文档队列");
      const hasMobileQueue = bodyText.includes("解析文档列表");
      return hasLegacyDocSwitcher || hasDesktopQueue || hasMobileQueue;
    },
    undefined,
    { timeout: 120_000 },
  );
  await page.waitForTimeout(4_000);

  const inferredDocButtonCount = await page.evaluate(() => {
    const legacyCount = document.querySelectorAll('[data-testid="module2-document-switcher-button"]').length;
    if (legacyCount > 0) return legacyCount;
    const queueHost = Array.from(document.querySelectorAll("section,div,aside")).find((el) => {
      const text = String(el.textContent || "");
      return text.includes("文档队列") || text.includes("解析文档列表");
    });
    if (!queueHost) return 0;
    return Array.from(queueHost.querySelectorAll("button")).filter((button) => {
      const text = String(button.textContent || "");
      return text.includes(".xlsx") || text.includes(".xls");
    }).length;
  });

  const overall = {
    rerunRoot,
    appUrl,
    apiBase,
    outputDir,
    selectedFileCount: selectedFiles.length,
    leftPanelVisible: await page.locator('[data-testid="module2-left-panel"]').isVisible().catch(() => false),
    docButtonCount: inferredDocButtonCount,
    tracePanelVisible: await page.locator('[data-testid="module2-trace-panel"]').isVisible().catch(() => false),
    docSwitchWaitMs,
  };

  const results = [];
  for (let index = 0; index < selectedFiles.length; index += 1) {
    const switched = await clickDocumentByIndex(page, index, selectedFiles[index]?.name || "");
    if (!switched && index > 0) {
      results.push({
        index,
        fileName: selectedFiles[index].name,
        expectedFieldCount: Object.keys(documents[index]?.result || {}).length,
        rawSoftWarnings: Array.isArray(documents[index]?.soft_warnings) ? documents[index].soft_warnings : [],
        screenshotPath: "",
        metrics: { switchError: "doc_switch_button_not_found" },
      });
      continue;
    }
    await page.waitForTimeout(docSwitchWaitMs);
    await page.waitForLoadState("networkidle", { timeout: 12_000 }).catch(() => {});

    const metrics = await collectPageMetrics(page);
    const screenshotPath = path.join(outputDir, `${String(index + 1).padStart(2, "0")}.png`);
    await page.screenshot({ path: screenshotPath, timeout: 60_000 }).catch(() => {});

    results.push({
      index,
      fileName: selectedFiles[index].name,
      expectedFieldCount: Object.keys(documents[index]?.result || {}).length,
      rawSoftWarnings: Array.isArray(documents[index]?.soft_warnings) ? documents[index].soft_warnings : [],
      screenshotPath,
      metrics,
    });
  }

  const report = {
    generatedAt: new Date().toISOString(),
    overall,
    results,
    consoleLogs: consoleLogs.slice(-200),
    pageErrors,
    failedResponses,
  };
  await fs.writeFile(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2), "utf8");
  await browser.close();

  console.log(JSON.stringify(report, null, 2));
};

main().catch((error) => {
  const text = error && error.stack ? error.stack : String(error || "unknown_error");
  console.error(text);
  process.exit(1);
});
