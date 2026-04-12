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
const apiBase = String(process.env.MODULE2_API_BASE_OVERRIDE || "http://127.0.0.1:3001")
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/extract$/i, "");
const configuredTargetFilePath = String(process.env.MODULE2_LOCKED_ROW_FILE || "").trim();
const question1 =
  process.env.MODULE2_LOCKED_ROW_Q1 ||
  "请在 xlsx_t1 表格中定位“站点名称=滕州北辛中学”这一行，返回 PM10 数值和 ref_id。";
const question2 =
  process.env.MODULE2_LOCKED_ROW_Q2 ||
  "继续同一行，返回污染类型的值和 ref_id。";
const outputDir =
  process.env.MODULE2_LOCKED_ROW_OUTPUT_DIR ||
  path.join(projectRoot, ".runlogs", "module2-locked-row-followup", new Date().toISOString().replace(/[:.]/g, "-"));
const maxPostDataChars = Math.max(20_000, Number(process.env.MODULE2_CAPTURE_POST_DATA_CHARS || 120_000));
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

async function resolveTargetFilePath() {
  if (configuredTargetFilePath) {
    const explicit = path.isAbsolute(configuredTargetFilePath)
      ? configuredTargetFilePath
      : path.resolve(projectRoot, configuredTargetFilePath);
    await fs.access(explicit);
    return explicit;
  }

  const excelDir = path.join(projectRoot, "datasets", "Excel");
  const entries = await fs.readdir(excelDir, { withFileTypes: true });
  const candidates = entries
    .filter((entry) => entry.isFile() && /\.xlsx$/i.test(entry.name))
    .map((entry) => path.join(excelDir, entry.name))
    .sort((a, b) => a.localeCompare(b, "zh-CN"));

  if (candidates.length > 0) {
    return candidates[0];
  }

  throw new Error(`no_xlsx_input_found:${excelDir}`);
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

async function openModulePage(page) {
  await openProtectedTab(page, appUrl, "deepread_extraction", {
    waitUntil: "domcontentloaded",
    timeout: 90_000,
    networkIdleTimeout: 30_000,
  });
  await setApiOverride(page);
  await page.reload({ waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  if ((await fileInput.count().catch(() => 0)) > 0) return;

  const menu = page.getByTestId("sidebar-menu-deepread");
  const submenu = page.getByTestId("sidebar-submenu-deepread_extraction");
  if (await menu.isVisible().catch(() => false)) {
    await menu.click({ timeout: 15_000 }).catch(() => {});
  }
  if (await submenu.isVisible().catch(() => false)) {
    await submenu.click({ timeout: 15_000 }).catch(() => {});
  }

  await fileInput.first().waitFor({ state: "attached", timeout: 90_000 });
}

async function waitStartButtonReady(page) {
  await page.waitForFunction(() => {
    const button = document.querySelector('[data-testid="module2-start-extract"]');
    if (!(button instanceof HTMLButtonElement)) return false;
    const style = window.getComputedStyle(button);
    if (style.visibility === "hidden" || style.display === "none") return false;
    const selected = document.querySelectorAll('[data-testid="module2-document-switcher-button"]').length;
    return selected > 0 && !button.disabled;
  }, { timeout: 120_000 });
}

async function waitJobTerminal(jobId, cookieHeader) {
  const startedAt = Date.now();
  const timeline = [];
  while (Date.now() - startedAt < 600_000) {
    const response = await fetch(`${apiBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
    });
    const payload = await response.json().catch(() => ({}));
    timeline.push({
      ts: new Date().toISOString(),
      status_code: Number(response.status || 0),
      status: String(payload?.status || ""),
      terminal: Boolean(payload?.terminal),
      completed_files: Number(payload?.progress?.completed_files || 0),
      failed_files: Number(payload?.progress?.failed_files || 0),
    });
    if (response.ok && payload?.terminal) {
      return {
        timed_out: false,
        elapsed_ms: Date.now() - startedAt,
        payload,
        timeline,
      };
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  return {
    timed_out: true,
    elapsed_ms: Date.now() - startedAt,
    payload: null,
    timeline,
  };
}

async function ensureAssistantReady(page) {
  const visibleInput = page.locator('[data-testid="module2-assistant-input"]:visible').first();
  if ((await visibleInput.count().catch(() => 0)) === 0) {
    const tab = page.getByTestId("module2-smart-tab-assistant").first();
    if ((await tab.count().catch(() => 0)) > 0) {
      await tab.scrollIntoViewIfNeeded().catch(() => {});
      await tab.click({ timeout: 15_000, force: true }).catch(() => {});
    }
  }
  await visibleInput.waitFor({ state: "visible", timeout: 90_000 });
  await page.waitForFunction(() => {
    const inputs = Array.from(document.querySelectorAll('[data-testid="module2-assistant-input"]'));
    const input = inputs.find((node) => node instanceof HTMLTextAreaElement && node.offsetParent !== null);
    return input instanceof HTMLTextAreaElement && !input.disabled;
  }, { timeout: 90_000 });
}

async function ask(page, question, screenshotPath) {
  await ensureAssistantReady(page);
  const input = page.locator('[data-testid="module2-assistant-input"]:visible').first();
  await input.fill(question);
  await input.press("Control+Enter");

  await page.waitForFunction(() => {
    const buttons = Array.from(document.querySelectorAll('[data-testid="module2-assistant-send"]'));
    const visibleButton = buttons.find((node) => node instanceof HTMLButtonElement && node.offsetParent !== null);
    return visibleButton instanceof HTMLButtonElement && visibleButton.disabled;
  }, { timeout: 30_000 }).catch(() => {});

  await page.waitForFunction(() => {
    const buttons = Array.from(document.querySelectorAll('[data-testid="module2-assistant-send"]'));
    const visibleButton = buttons.find((node) => node instanceof HTMLButtonElement && node.offsetParent !== null);
    return visibleButton instanceof HTMLButtonElement && !visibleButton.disabled;
  }, { timeout: 240_000 }).catch(() => {});

  await page.waitForTimeout(1200);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  return await page.evaluate(() => {
    const container = document.querySelector('[data-testid="module2-assistant-dialog"]');
    const lines = container
      ? Array.from(container.children).map((node) => (node.textContent || "").trim()).filter(Boolean)
      : [];
    const latest = lines.slice(-2);
    return {
      dialog_tail: lines.slice(-8),
      latest_answer: latest.length > 0 ? latest[latest.length - 1] : "",
      body_excerpt: (document.body?.innerText || "").trim().slice(-2600),
    };
  });
}

function summarizeAssistantPostData(postDataRaw) {
  const postData = String(postDataRaw || "");
  const fallback = {
    parse_ok: false,
    has_extra_context: /"extra_context"\s*:/.test(postData),
    has_current_document: /"current_document"\s*:/.test(postData),
    has_diagnostics: /"diagnostics"\s*:/.test(postData),
    has_table_row_samples: /"table_row_samples"\s*:/.test(postData),
    has_current_locked_object: /"current_locked_object"\s*:/.test(postData),
    parse_error: "",
  };

  try {
    const payload = JSON.parse(postData);
    const extraContext =
      payload && typeof payload.extra_context === "object" && payload.extra_context
        ? payload.extra_context
        : {};
    const currentDocument =
      extraContext && typeof extraContext.current_document === "object" && extraContext.current_document
        ? extraContext.current_document
        : {};
    const diagnostics =
      currentDocument && typeof currentDocument.diagnostics === "object" && currentDocument.diagnostics
        ? currentDocument.diagnostics
        : {};
    const tableRowSamples = Array.isArray(currentDocument.table_row_samples)
      ? currentDocument.table_row_samples
      : [];
    const tracePreview = Array.isArray(currentDocument.trace_preview) ? currentDocument.trace_preview : [];
    const traceTypeCounts = {};

    for (const item of tracePreview) {
      const type = String(item?.object_type || "unknown").trim() || "unknown";
      traceTypeCounts[type] = Number(traceTypeCounts[type] || 0) + 1;
    }

    return {
      parse_ok: true,
      has_extra_context: Boolean(payload.extra_context),
      has_current_document: Boolean(extraContext.current_document),
      has_diagnostics: Boolean(currentDocument.diagnostics),
      has_table_row_samples: tableRowSamples.length > 0,
      has_current_locked_object: Boolean(currentDocument.current_locked_object),
      diagnostics_keys: Object.keys(diagnostics),
      workbook_manifest_path: String(diagnostics.xlsx_workbook_manifest_path || "").trim(),
      workbook_manifest_url: String(diagnostics.xlsx_workbook_manifest_url || "").trim(),
      sheet_rows_artifact_version: String(diagnostics.xlsx_sheet_rows_artifact_version || "").trim(),
      table_row_sample_count: tableRowSamples.length,
      trace_preview_count: tracePreview.length,
      trace_preview_object_types: traceTypeCounts,
      trace_hit_count: Number(currentDocument.trace_hit_count || 0),
      field_count: Number(currentDocument.field_count || 0),
      parse_error: "",
    };
  } catch (error) {
    return {
      ...fallback,
      parse_error: String(error?.message || error || "parse_failed"),
    };
  }
}

async function captureFrontendDocumentDebug(page) {
  return await page.evaluate(() => {
    const safeReadJson = (key) => {
      try {
        const raw = window.localStorage.getItem(key);
        if (!raw) return null;
        return JSON.parse(raw);
      } catch {
        return null;
      }
    };

    const docsRaw = safeReadJson("module2_last_documents");
    const docs = Array.isArray(docsRaw) ? docsRaw : [];
    const firstDoc = docs[0] && typeof docs[0] === "object" ? docs[0] : {};
    const diagnostics = firstDoc?.diagnostics && typeof firstDoc.diagnostics === "object"
      ? firstDoc.diagnostics
      : {};
    const traceHits = Array.isArray(firstDoc?.trace_hits) ? firstDoc.trace_hits : [];
    const typeCounts = {};

    for (const hit of traceHits) {
      const type = String(hit?.object_type || "unknown").trim() || "unknown";
      typeCounts[type] = Number(typeCounts[type] || 0) + 1;
    }

    return {
      doc_count: docs.length,
      first_doc_file_name: String(firstDoc?.file_name || "").trim(),
      first_doc_file_hash: String(firstDoc?.file_hash || "").trim(),
      diagnostics_keys: Object.keys(diagnostics || {}),
      workbook_manifest_path: String(diagnostics.xlsx_workbook_manifest_path || "").trim(),
      workbook_manifest_url: String(diagnostics.xlsx_workbook_manifest_url || "").trim(),
      sheet_rows_artifact_version: String(diagnostics.xlsx_sheet_rows_artifact_version || "").trim(),
      trace_hit_count: traceHits.length,
      trace_object_type_counts: typeCounts,
      has_table_trace: Number(typeCounts.table || 0) > 0,
      has_figure_trace: Number(typeCounts.figure || 0) > 0,
    };
  });
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const targetFilePath = await resolveTargetFilePath();

  const executablePath = await resolveBrowserExecutablePath();
  const browser = await chromium.launch({
    headless: process.env.MODULE2_HEADLESS !== "0",
    executablePath: executablePath || undefined,
  });
  const context = await browser.newContext({ viewport: { width: 1560, height: 980 } });
  const authSession = await loginForProtectedApp(context, appUrl, {
    account: process.env.PLAYWRIGHT_AUTH_ACCOUNT || "default.tenant@example.com",
    password: process.env.PLAYWRIGHT_AUTH_PASSWORD || "Test@123456",
  });
  const cookieHeader = authSession.cookieHeader || "";
  const page = await context.newPage();

  let fatalError = "";
  let report = {};
  const consoleErrors = [];
  const pageErrors = [];
  const assistantRequests = [];

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
  page.on("request", (request) => {
    if (!request.url().includes("/extract/assistant1/chat/stream")) return;
    const rawPostData = String(request.postData() || "");
    const clippedPostData =
      rawPostData.length > maxPostDataChars
        ? `${rawPostData.slice(0, maxPostDataChars)}\n...[truncated:${rawPostData.length - maxPostDataChars} chars]`
        : rawPostData;
    assistantRequests.push({
      time: new Date().toISOString(),
      url: request.url(),
      method: request.method(),
      post_data_chars: rawPostData.length,
      post_data_summary: summarizeAssistantPostData(rawPostData),
      post_data: clippedPostData,
    });
  });

  try {
    await openModulePage(page);
    await page.setInputFiles('[data-testid="module2-file-input"]', targetFilePath);
    await waitStartButtonReady(page);

    const createPromise = page.waitForResponse(
      (res) => res.url().includes("/extract/jobs/create") && res.request().method() === "POST",
      { timeout: 180_000 },
    );
    await page.getByTestId("module2-start-extract").click();
    const createResp = await createPromise;
    const createPayload = await createResp.json();
    const jobId = String(createPayload?.job_id || "");
    if (!jobId) throw new Error(`missing_job_id:${JSON.stringify(createPayload)}`);

    const terminal = await waitJobTerminal(jobId, cookieHeader);
    if (terminal.timed_out) {
      throw new Error(`extract_job_terminal_timeout:${jobId}`);
    }

    const shot1 = path.join(outputDir, "q1.png");
    const shot2 = path.join(outputDir, "q2.png");
    const q1 = await ask(page, question1, shot1);
    const q2 = await ask(page, question2, shot2);
    const frontendDocDebug = await captureFrontendDocumentDebug(page);

    report = {
      ok: true,
      app_url: appUrl,
      api_base: apiBase,
      file_path: targetFilePath,
      extract_job_id: jobId,
      extract_status: String(terminal?.payload?.status || ""),
      extract_terminal: Boolean(terminal?.payload?.terminal),
      extract_elapsed_ms: Number(terminal?.elapsed_ms || 0),
      q1: {
        question: question1,
        answer: q1.latest_answer,
        dialog_tail: q1.dialog_tail,
        screenshot: shot1,
      },
      q2: {
        question: question2,
        answer: q2.latest_answer,
        dialog_tail: q2.dialog_tail,
        screenshot: shot2,
      },
      diagnostics: {
        frontend_doc_debug: frontendDocDebug,
        console_errors: consoleErrors,
        page_errors: pageErrors,
        assistant_requests: assistantRequests,
      },
    };
  } catch (error) {
    fatalError = String(error?.message || error || "locked_row_followup_failed");
    report = {
      ok: false,
      error: fatalError,
      diagnostics: {
        console_errors: consoleErrors,
        page_errors: pageErrors,
        assistant_requests: assistantRequests,
      },
    };
    await page.screenshot({ path: path.join(outputDir, "error.png"), fullPage: true }).catch(() => {});
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }

  const outputPath = path.join(outputDir, "report.json");
  await fs.writeFile(outputPath, JSON.stringify(report, null, 2), "utf-8");
  console.log(JSON.stringify({ output_path: outputPath, report }, null, 2));
  if (fatalError) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

