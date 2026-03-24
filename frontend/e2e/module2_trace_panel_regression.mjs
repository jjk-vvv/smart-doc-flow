#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const frontendUrl = process.env.MODULE2_APP_URL || "http://127.0.0.1:3000";
const extractBase = String(process.env.MODULE2_API_BASE || "http://127.0.0.1:8000").trim().replace(/\/+$/, "");
const todayTag = new Date().toISOString().slice(0, 10);
const outputDir = path.join(projectRoot, ".runlogs", "module2-trace-checks", todayTag, "validation");

const readJson = async (filePath) => {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw.replace(/^\uFEFF/, ""));
};

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

async function openModulePage(page) {
  await page.goto(frontendUrl, { waitUntil: "networkidle", timeout: 90_000 });
  await page.getByRole("button", { name: "智能文档解析" }).click();
  await page.getByRole("button", { name: "非结构化文档信息需求模块" }).click();
  await page.getByRole("heading", { name: "非结构化文档分析" }).waitFor({ timeout: 30_000 });
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

  const wordSession = await readJson(
    path.join(projectRoot, ".runlogs", "module2-trace-checks", "2026-03-22", "batch-word-check-01", "final_localstorage.json"),
  );
  const wordStatus = await readJson(
    path.join(projectRoot, ".runlogs", "module2-trace-checks", "2026-03-22", "batch-word-check-01", "final_status.json"),
  );
  const pdfStatus = await readJson(
    path.join(projectRoot, "backend", "module2", "backend", "module2", ".runlogs", "extraction_jobs", "extract_job_b35c10a59c884c14.json"),
  );

  const wordName = "2024杭州市生态环境状况公报（节选）.docx";
  const pdfName = "2024杭州市生态环境状况公报（节选）-native.pdf";

  const wordDoc = normalizeDocument(wordStatus.documents[0], wordName);
  const pdfDoc = normalizeDocument(pdfStatus.job.documents[0], pdfName);

  const wordSelected = {
    ...clone(wordSession.selectedFiles[0]),
    name: wordName,
    ext: "docx",
    artifactUrl: ensureAbsoluteUrl(wordSession.selectedFiles[0].artifactUrl),
  };

  const pdfJobFile = pdfStatus.job.files[0];
  const pdfSelected = {
    key: `${pdfName}:1101458:1774112154801`,
    name: pdfName,
    size: 1101458,
    lastModified: 1774112154801,
    ext: "pdf",
    artifactUrl: ensureAbsoluteUrl(pdfJobFile.artifact_url),
    artifactPath: pdfJobFile.artifact_path || "",
  };

  const browser = await chromium.launch({
    channel: "chrome",
    headless: true,
  });

  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

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
    const wordInitialTraceCards = await wordTraceCards.count();
    const tableCard = tableGroup.locator('[data-testid="module2-trace-card"]').first();
    await tableCard.waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForFunction(
      () => document.querySelectorAll('[data-testid="module2-trace-expand-button"]').length > 0,
      null,
      { timeout: 30_000 },
    );

    const initialIndicator = await readPageIndicator(page);
    const expandButton = tableCard.getByTestId("module2-trace-expand-button").first();
    const jumpButton = tableCard.getByTestId("module2-trace-jump-button").first();
    const initialCardState = await collectCardState(tableCard);

    await page.screenshot({ path: screenshotPath("module2-trace-regression-initial.png"), fullPage: true });

    await expandButton.scrollIntoViewIfNeeded();
    await expandButton.click({ force: true });
    await page.waitForTimeout(1000);

    const expandedCardState = await collectCardState(tableCard);
    const expandedButtonText = ((await expandButton.textContent()) || "").trim();
    const tablePreviewCount = await tableCard.locator('[data-testid="module2-trace-table-preview"]').count();

    await jumpButton.scrollIntoViewIfNeeded();
    await jumpButton.click({ force: true });
    await page.waitForTimeout(1200);
    const indicatorAfterJump = await readPageIndicator(page);

    const fieldButton = page.locator('[data-testid="module2-field-chip"]').first();
    await fieldButton.scrollIntoViewIfNeeded();
    await fieldButton.click({ force: true });
    await page.waitForTimeout(800);
    const wordTraceCardsAfterFieldClick = await page.locator('[data-testid="module2-trace-card"]').count();

    const docButtons = page.locator('[data-testid="module2-document-switcher-button"]');
    await docButtons.nth(1).scrollIntoViewIfNeeded();
    await docButtons.nth(1).click({ force: true });
    await page.waitForTimeout(1200);
    const pdfTraceCardsAfterSwitch = await page.locator('[data-testid="module2-trace-card"]').count();
    const pdfIndicatorAfterSwitch = await readPageIndicator(page);
    const pdfEmptyStateVisible = await page
      .locator('text=暂无相关定位信息')
      .first()
      .isVisible()
      .catch(() => false);

    await page.screenshot({ path: screenshotPath("module2-trace-regression-after-switch.png"), fullPage: true });

    await docButtons.nth(0).scrollIntoViewIfNeeded();
    await docButtons.nth(0).click({ force: true });
    await page.waitForTimeout(1200);
    const wordTraceCardsAfterReturn = await page.locator('[data-testid="module2-trace-card"]').count();
    const wordIndicatorAfterReturn = await readPageIndicator(page);
    const returnedTableCard = page.locator('[data-testid="module2-trace-group-table"] [data-testid="module2-trace-card"]').first();
    const returnedExpandState = await collectCardState(returnedTableCard);
    const returnedExpandedPreviewCount = await returnedTableCard.locator('[data-testid="module2-trace-table-preview"]').count();

    await page.screenshot({ path: screenshotPath("module2-trace-regression-word.png"), fullPage: true });

    const report = {
      generated_at: new Date().toISOString(),
      checks: {
        word_initial_indicator: initialIndicator,
        word_initial_trace_cards: wordInitialTraceCards,
        jump_button_visible: await jumpButton.isVisible(),
        expand_button_visible: await expandButton.isVisible(),
        initial_card_state: initialCardState,
        expanded_card_state: expandedCardState,
        expanded_button_text: expandedButtonText,
        word_expand_full_table: tablePreviewCount > 0 && expandedCardState.traceExpanded === "true",
        word_after_jump_indicator: indicatorAfterJump,
        word_indicator_total_stable_after_jump:
          parseIndicatorTotal(initialIndicator) > 0 &&
          parseIndicatorTotal(initialIndicator) === parseIndicatorTotal(indicatorAfterJump),
        word_after_field_click_trace_cards: wordTraceCardsAfterFieldClick,
        pdf_trace_cards_after_switch: pdfTraceCardsAfterSwitch,
        pdf_indicator_after_switch: pdfIndicatorAfterSwitch,
        pdf_empty_state_visible: pdfEmptyStateVisible,
        word_trace_cards_after_return: wordTraceCardsAfterReturn,
        word_indicator_after_return: wordIndicatorAfterReturn,
        word_expand_reset_after_return: returnedExpandedPreviewCount === 0 && returnedExpandState.traceExpanded !== "true",
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
