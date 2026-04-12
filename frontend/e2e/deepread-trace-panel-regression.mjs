#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const datasetRoot = path.join(projectRoot, "datasets");
const frontendUrl = process.env.MODULE2_APP_URL || "http://127.0.0.1:3001";
const extractBase = String(process.env.MODULE2_API_BASE || "http://127.0.0.1:3001")
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/extract$/i, "");
const todayTag = new Date().toISOString().slice(0, 10);
const outputDir = path.join(projectRoot, ".runlogs", "module2-trace-checks", todayTag, "validation");
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
const traceWordFixtureName = "2024年杭州市生态环境状况公报（节选）.docx";
const tracePdfFixtureName = "2024年杭州市生态环境状况公报（节选）-native.pdf";
const traceWordFixturePath = path.join(datasetRoot, "word", traceWordFixtureName);
const traceSchema = {
  auto_infer: true,
  prefer_llm: true,
  max_auto_fields: 12,
};
const traceJobTimeoutMs = 900_000;
const createJobMaxAttempts = Number(process.env.MODULE2_TRACE_CREATE_RETRY_MAX || 4);
const createJobBaseDelayMs = Number(process.env.MODULE2_TRACE_CREATE_RETRY_DELAY_MS || 2500);
const createJobDelayCapMs = Number(process.env.MODULE2_TRACE_CREATE_RETRY_DELAY_CAP_MS || 15000);
let authCookieHeader = "";

const clone = (value) => JSON.parse(JSON.stringify(value));

const ensureAbsoluteUrl = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw;
  if (raw.startsWith("/")) return `${extractBase}${raw}`;
  return `${extractBase}/${raw.replace(/^\/+/, "")}`;
};

const normalizeTraceHit = (traceHit, friendlyName) => {
  const next = clone(traceHit || {});
  next.file_name = friendlyName;
  if (next.artifact_url) {
    next.artifact_url = ensureAbsoluteUrl(next.artifact_url);
  }
  if (next.locator && typeof next.locator === "object" && next.locator.artifact_url) {
    next.locator.artifact_url = ensureAbsoluteUrl(next.locator.artifact_url);
  }
  return next;
};

const normalizeDocument = (document, friendlyName) => {
  const next = clone(document || {});
  next.file_name = friendlyName;
  if (Array.isArray(next.trace_hits)) {
    next.trace_hits = next.trace_hits.map((item) => normalizeTraceHit(item, friendlyName));
  }
  if (next.diagnostics && typeof next.diagnostics === "object" && next.diagnostics.office_pdf_preview_url) {
    next.diagnostics.office_pdf_preview_url = ensureAbsoluteUrl(next.diagnostics.office_pdf_preview_url);
  }
  return next;
};

const screenshotPath = (name) => path.join(outputDir, name);

function parseIndicatorTotal(indicator) {
  const match = String(indicator || "").match(/(\d+)\s*\/\s*(\d+)/);
  return match ? Number(match[2]) : 0;
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryableCreateError(error) {
  const message = String(error?.message || error || "");
  const lowered = message.toLowerCase();
  if (!message.includes("/extract/jobs/create")) return false;
  if (message.includes("request_failed:429:")) return true;
  if (message.includes("request_failed:503:")) return true;
  return (
    lowered.includes("fetch failed") ||
    lowered.includes("networkerror") ||
    lowered.includes("econnreset") ||
    lowered.includes("etimedout")
  );
}

function isRetryableTerminalFailure(payload) {
  if (String(payload?.status || "").toLowerCase() !== "failed") return false;
  const serialized = JSON.stringify(payload || {}).toLowerCase();
  return (
    serialized.includes("429") ||
    serialized.includes("503") ||
    serialized.includes("read timed out") ||
    serialized.includes("timed out") ||
    serialized.includes("timeout") ||
    serialized.includes("upstream") ||
    serialized.includes("connection error") ||
    serialized.includes("temporarily unavailable")
  );
}

async function fetchJson(url, init = {}) {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(authCookieHeader ? { cookie: authCookieHeader } : {}),
    },
  });
  const text = await response.text().catch(() => "");
  let payload = null;
  try {
    payload = text ? JSON.parse(text.replace(/^\uFEFF/, "")) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(`request_failed:${response.status}:${url}:${text.slice(0, 320)}`);
  }
  return payload;
}

async function fetchBuffer(url, init = {}) {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(authCookieHeader ? { cookie: authCookieHeader } : {}),
    },
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`request_failed:${response.status}:${url}:${text.slice(0, 320)}`);
  }
  const arrayBuffer = await response.arrayBuffer();
  return Buffer.from(arrayBuffer);
}

async function waitForExtractionTerminal(jobId) {
  const startedAt = Date.now();
  const jobUrl = `${extractBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`;
  let latestPayload = null;
  let latestStatus = 0;

  while (Date.now() - startedAt < traceJobTimeoutMs) {
    try {
      const response = await fetch(jobUrl, {
        headers: authCookieHeader ? { cookie: authCookieHeader } : {},
      });
      latestStatus = Number(response.status || 0);
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      latestPayload = payload;
      if (response.ok && payload?.terminal) {
        return payload;
      }
    } catch {
      latestStatus = 0;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }

  throw new Error(
    `trace_job_timeout:${jobId}:status=${latestStatus}:payload=${JSON.stringify(latestPayload || {}).slice(0, 320)}`,
  );
}

async function createExtractionJobFromBuffer({ fileName, contentType, buffer }) {
  let lastError = null;
  for (let attempt = 0; attempt < createJobMaxAttempts; attempt += 1) {
    const form = new FormData();
    form.append("files", new Blob([buffer], { type: contentType }), fileName);
    form.append("schema", JSON.stringify(traceSchema));
    form.append("tenant_id", "");

    try {
      const created = await fetchJson(`${extractBase}/extract/jobs/create`, {
        method: "POST",
        body: form,
      });
      const jobId = String(created?.job_id || "").trim();
      if (!jobId) {
        throw new Error(`trace_job_create_missing_id:${JSON.stringify(created || {}).slice(0, 320)}`);
      }
      const terminal = await waitForExtractionTerminal(jobId);
      if (String(terminal?.status || "").toLowerCase() !== "failed") {
        return terminal;
      }

      const failure = new Error(`trace_job_terminal_failed:${jobId}:${JSON.stringify(terminal || {}).slice(0, 320)}`);
      const canRetry = attempt < createJobMaxAttempts - 1 && isRetryableTerminalFailure(terminal);
      if (!canRetry) {
        throw failure;
      }
      const delayMs = Math.min(createJobBaseDelayMs * 2 ** attempt, createJobDelayCapMs);
      console.warn(
        `[module2-trace] terminal failed, recreating extraction job file=${fileName} attempt=${attempt + 1}/${createJobMaxAttempts} delay_ms=${delayMs} reason=${String(failure.message || "unknown_error").slice(0, 240)}`,
      );
      await sleep(delayMs);
    } catch (error) {
      lastError = error;
      const canRetry = attempt < createJobMaxAttempts - 1 && isRetryableCreateError(error);
      if (!canRetry) {
        throw error;
      }
      const delayMs = Math.min(createJobBaseDelayMs * 2 ** attempt, createJobDelayCapMs);
      console.warn(
        `[module2-trace] create extraction job retrying file=${fileName} attempt=${attempt + 1}/${createJobMaxAttempts} delay_ms=${delayMs} reason=${String(error?.message || error || "unknown_error").slice(0, 240)}`,
      );
      await sleep(delayMs);
    }
  }

  throw lastError || new Error(`trace_job_create_failed:${fileName}`);
}

function buildSelectedFilePayload({ name, ext, size, artifactUrl, artifactPath, lastModified }) {
  return {
    key: `${name}:${size}:${lastModified}`,
    name,
    size,
    lastModified,
    ext,
    artifactUrl: ensureAbsoluteUrl(artifactUrl),
    artifactPath: String(artifactPath || "").trim(),
  };
}

async function buildLiveTraceFixtures() {
  const wordBuffer = await fs.readFile(traceWordFixturePath);
  const wordStatus = await createExtractionJobFromBuffer({
    fileName: traceWordFixtureName,
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: wordBuffer,
  });
  const wordDocRaw = Array.isArray(wordStatus?.documents) ? wordStatus.documents[0] : null;
  const wordJobFile = Array.isArray(wordStatus?.files) ? wordStatus.files[0] : null;
  if (!wordDocRaw || !wordJobFile) {
    throw new Error(`trace_word_fixture_missing_document:${JSON.stringify(wordStatus || {}).slice(0, 320)}`);
  }

  const officePreviewUrl = ensureAbsoluteUrl(
    wordDocRaw?.diagnostics?.office_pdf_preview_url || wordDocRaw?.diagnostics?.office_pdf_preview_path || "",
  );
  if (!officePreviewUrl) {
    throw new Error(`trace_word_fixture_missing_preview:${JSON.stringify(wordDocRaw?.diagnostics || {}).slice(0, 320)}`);
  }

  const pdfBuffer = await fetchBuffer(officePreviewUrl);
  const pdfStatus = await createExtractionJobFromBuffer({
    fileName: tracePdfFixtureName,
    contentType: "application/pdf",
    buffer: pdfBuffer,
  });
  const pdfDocRaw = Array.isArray(pdfStatus?.documents) ? pdfStatus.documents[0] : null;
  const pdfJobFile = Array.isArray(pdfStatus?.files) ? pdfStatus.files[0] : null;
  if (!pdfDocRaw || !pdfJobFile) {
    throw new Error(`trace_pdf_fixture_missing_document:${JSON.stringify(pdfStatus || {}).slice(0, 320)}`);
  }

  const now = Date.now();
  return {
    wordDoc: normalizeDocument(wordDocRaw, traceWordFixtureName),
    pdfDoc: normalizeDocument(pdfDocRaw, tracePdfFixtureName),
    wordSelected: buildSelectedFilePayload({
      name: traceWordFixtureName,
      ext: "docx",
      size: wordBuffer.length,
      artifactUrl: wordJobFile.artifact_url,
      artifactPath: wordJobFile.artifact_path,
      lastModified: now,
    }),
    pdfSelected: buildSelectedFilePayload({
      name: tracePdfFixtureName,
      ext: "pdf",
      size: pdfBuffer.length,
      artifactUrl: pdfJobFile.artifact_url,
      artifactPath: pdfJobFile.artifact_path,
      lastModified: now + 1,
    }),
    wordStatus,
    pdfStatus,
  };
}

async function openModulePage(page) {
  await openProtectedTab(page, frontendUrl, "deepread_extraction");
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
  await page.getByRole("button", { name: /智能文档解析/ }).first().click();
  await page
    .getByRole("button", { name: /非结构化文档信息需求模块/ })
    .first()
    .click();
  await fileInput.waitFor({ state: "attached", timeout: 90_000 });
}

async function collectCardState(card) {
  return await card.evaluate((node) => ({
    traceKind: node.getAttribute("data-trace-kind") || "",
    traceActive: node.getAttribute("data-trace-active") || "",
    traceExpanded: node.getAttribute("data-trace-expanded") || "",
    ariaPressed: node.getAttribute("aria-pressed") || "",
    ariaExpanded: node.getAttribute("aria-expanded") || "",
  }));
}

async function readPageIndicator(page) {
  const indicator = page.getByTestId("module2-preview-page-indicator");
  return ((await indicator.textContent().catch(() => "")) || "").trim();
}

async function main() {
  await ensureDir(outputDir);
  const executablePath = await resolveBrowserExecutablePath();
  const browser = await chromium.launch({
    headless: true,
    executablePath: executablePath || undefined,
  });

  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    const authSession = await loginForProtectedApp(page.context(), frontendUrl);
    authCookieHeader = authSession.cookieHeader || "";
    const fixtureBundle = await buildLiveTraceFixtures();
    const {
      wordDoc,
      pdfDoc,
      wordSelected,
      pdfSelected,
      wordStatus,
      pdfStatus,
    } = fixtureBundle;

    await fs.writeFile(
      path.join(outputDir, "trace-word-status.json"),
      `${JSON.stringify(wordStatus, null, 2)}\n`,
      "utf8",
    );
    await fs.writeFile(
      path.join(outputDir, "trace-pdf-status.json"),
      `${JSON.stringify(pdfStatus, null, 2)}\n`,
      "utf8",
    );

    await page.addInitScript(
      ({ docs, session, base }) => {
        window.localStorage.clear();
        window.sessionStorage.clear();
        window.localStorage.setItem("module2_last_documents", JSON.stringify(docs));
        window.localStorage.setItem("module2_last_updated", new Date().toISOString());
        window.localStorage.setItem("module2_workbench_session_v1", JSON.stringify(session));
        window.localStorage.setItem("module2_api_base_override", String(base || "").trim());
      },
      {
        docs: [wordDoc, pdfDoc],
        session: {
          version: 1,
          activeDocIndex: 0,
          activeDocFileHash: wordDoc.file_hash,
          selectedFiles: [wordSelected, pdfSelected],
          officePreviewMap: {},
          extractionJob: null,
        },
        base: extractBase,
      },
    );

    await openModulePage(page);

    const tableGroup = page.locator('[data-testid="module2-trace-group-table"]');
    await tableGroup.waitFor({ state: "visible", timeout: 30_000 });
    const wordTraceCards = page.locator('[data-testid="module2-trace-card"]');
    await wordTraceCards.first().waitFor({ state: "visible", timeout: 30_000 });
    const wordInitialTraceCards = await wordTraceCards.count();
    await page.waitForFunction(
      () => document.querySelectorAll('[data-testid="module2-trace-expand-button"]').length > 0,
      null,
      { timeout: 30_000 },
    );
    const expandableCard = page
      .locator('[data-testid="module2-trace-card"]')
      .filter({ has: page.locator('[data-testid="module2-trace-expand-button"]') })
      .first();
    await expandableCard.waitFor({ state: "visible", timeout: 30_000 });

    const initialIndicator = await readPageIndicator(page);
    const expandButton = expandableCard.getByTestId("module2-trace-expand-button").first();
    const jumpButton = expandableCard.getByTestId("module2-trace-jump-button").first();
    const initialCardState = await collectCardState(expandableCard);
    const expandableTraceKind = String((await expandableCard.getAttribute("data-trace-kind")) || "").trim();

    await page.screenshot({ path: screenshotPath("module2-trace-regression-initial.png"), fullPage: true });

    await expandButton.scrollIntoViewIfNeeded();
    await expandButton.click({ force: true });
    await page.waitForTimeout(1000);

    const expandedCardState = await collectCardState(expandableCard);
    const expandedButtonText = ((await expandButton.textContent()) || "").trim();
    const tablePreviewCount = await expandableCard.locator('[data-testid="module2-trace-table-preview"]').count();
    const figureDataframeCount = await expandableCard.locator('[data-testid="module2-trace-figure-dataframe"]').count();
    const expandedPreviewCount = tablePreviewCount + figureDataframeCount;

    await jumpButton.scrollIntoViewIfNeeded();
    await jumpButton.click({ force: true });
    await page.waitForTimeout(1200);
    const indicatorAfterJump = await readPageIndicator(page);

    const wordFieldChips = page.locator('[data-testid="module2-field-chip"]');
    const wordFieldChipCount = await wordFieldChips.count();
    let wordTraceCardsAfterFieldClick = null;
    if (wordFieldChipCount > 0) {
      const fieldButton = wordFieldChips.first();
      await fieldButton.scrollIntoViewIfNeeded();
      await fieldButton.click({ force: true });
      await page.waitForTimeout(800);
      wordTraceCardsAfterFieldClick = await page.locator('[data-testid="module2-trace-card"]').count();
    }

    const docButtons = page.locator('[data-testid="module2-document-switcher-button"]');
    await docButtons.nth(1).scrollIntoViewIfNeeded();
    await docButtons.nth(1).click({ force: true });
    await page.waitForTimeout(1200);
    const pdfTraceCardsAfterSwitch = await page.locator('[data-testid="module2-trace-card"]').count();
    const pdfIndicatorAfterSwitch = await readPageIndicator(page);
    const pdfFieldChips = page.locator('[data-testid="module2-field-chip"]');
    const pdfFieldChipCount = await pdfFieldChips.count();
    let pdfTraceCardsAfterFieldClick = null;
    if (pdfFieldChipCount > 0) {
      const pdfFieldButton = pdfFieldChips.first();
      await pdfFieldButton.scrollIntoViewIfNeeded();
      await pdfFieldButton.click({ force: true });
      await page.waitForTimeout(800);
      pdfTraceCardsAfterFieldClick = await page.locator('[data-testid="module2-trace-card"]').count();
    }
    const pdfEmptyStateVisible = await page
      .getByText(/暂无相关定位信息/)
      .first()
      .isVisible()
      .catch(() => false);

    await page.screenshot({ path: screenshotPath("module2-trace-regression-after-switch.png"), fullPage: true });

    await docButtons.nth(0).scrollIntoViewIfNeeded();
    await docButtons.nth(0).click({ force: true });
    await page.waitForTimeout(1200);
    const wordTraceCardsAfterReturn = await page.locator('[data-testid="module2-trace-card"]').count();
    const wordIndicatorAfterReturn = await readPageIndicator(page);
    const returnedExpandableCard = page
      .locator('[data-testid="module2-trace-card"]')
      .filter({ has: page.locator('[data-testid="module2-trace-expand-button"]') })
      .first();
    await returnedExpandableCard.waitFor({ state: "visible", timeout: 30_000 });
    const returnedExpandState = await collectCardState(returnedExpandableCard);
    const returnedExpandedPreviewCount =
      (await returnedExpandableCard.locator('[data-testid="module2-trace-table-preview"]').count()) +
      (await returnedExpandableCard.locator('[data-testid="module2-trace-figure-dataframe"]').count());

    await page.screenshot({ path: screenshotPath("module2-trace-regression-word.png"), fullPage: true });

    const report = {
      generated_at: new Date().toISOString(),
      fixtures: {
        word_file: traceWordFixtureName,
        pdf_file: tracePdfFixtureName,
        word_job_id: wordStatus.job_id,
        pdf_job_id: pdfStatus.job_id,
      },
      checks: {
        word_initial_indicator: initialIndicator,
        word_initial_trace_cards: wordInitialTraceCards,
        expandable_trace_kind: expandableTraceKind,
        jump_button_visible: await jumpButton.isVisible(),
        expand_button_visible: await expandButton.isVisible(),
        initial_card_state: initialCardState,
        expanded_card_state: expandedCardState,
        expanded_button_text: expandedButtonText,
        word_expand_full_table: tablePreviewCount > 0 && expandedCardState.traceExpanded === "true",
        word_expand_detail_preview:
          expandedPreviewCount > 0 && expandedCardState.traceExpanded === "true",
        word_expand_table_preview_count: tablePreviewCount,
        word_expand_figure_dataframe_count: figureDataframeCount,
        word_after_jump_indicator: indicatorAfterJump,
        word_indicator_total_stable_after_jump:
          parseIndicatorTotal(initialIndicator) > 0 &&
          parseIndicatorTotal(initialIndicator) === parseIndicatorTotal(indicatorAfterJump),
        word_field_chip_count: wordFieldChipCount,
        word_after_field_click_trace_cards: wordTraceCardsAfterFieldClick,
        pdf_trace_cards_after_switch: pdfTraceCardsAfterSwitch,
        pdf_indicator_after_switch: pdfIndicatorAfterSwitch,
        pdf_field_chip_count: pdfFieldChipCount,
        pdf_after_field_click_trace_cards: pdfTraceCardsAfterFieldClick,
        pdf_empty_state_visible: pdfEmptyStateVisible,
        word_trace_cards_after_return: wordTraceCardsAfterReturn,
        word_indicator_after_return: wordIndicatorAfterReturn,
        word_expand_reset_after_return:
          returnedExpandedPreviewCount === 0 && returnedExpandState.traceExpanded !== "true",
      },
      screenshots: {
        initial: screenshotPath("module2-trace-regression-initial.png"),
        after_switch: screenshotPath("module2-trace-regression-after-switch.png"),
        word_return: screenshotPath("module2-trace-regression-word.png"),
      },
    };

    await fs.writeFile(
      path.join(outputDir, "module2-trace-regression.json"),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
