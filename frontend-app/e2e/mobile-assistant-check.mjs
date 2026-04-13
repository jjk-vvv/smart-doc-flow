#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");

const appUrl = String(process.env.MODULE2_APP_URL || "http://127.0.0.1:3002").trim();
const edgePath = String(
  process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH ||
    process.env.PLAYWRIGHT_EXECUTABLE_PATH ||
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
).trim();
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.join(projectRoot, ".runlogs", "mobile-assistant-check", runTag);
const reportPath = path.join(outputDir, "report.json");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const ensureDir = async (target) => {
  await fs.mkdir(target, { recursive: true });
};

const dismissOverlayButtons = async (page) => {
  const labels = ["跳过", "稍后", "关闭", "知道了"];
  for (const label of labels) {
    const locator = page.getByRole("button", { name: new RegExp(label) }).first();
    if (await locator.isVisible().catch(() => false)) {
      await locator.click({ timeout: 1200 }).catch(() => {});
      await sleep(200);
    }
  }
};

const collectGeometry = async (page) =>
  await page.evaluate(() => {
    const dialog = document.querySelector("[data-testid='mobile-module2-assistant-dialog']");
    const textarea = document.querySelector("textarea");
    const sendBtn = textarea?.parentElement?.querySelector("button[aria-label], button[title]") || null;
    const bottomNav = document.querySelector("nav");
    const dialogRect = dialog?.getBoundingClientRect?.() || null;
    const textareaRect = textarea?.getBoundingClientRect?.() || null;
    const sendRect = sendBtn?.getBoundingClientRect?.() || null;
    const navRect = bottomNav?.getBoundingClientRect?.() || null;

    return {
      viewportHeight: window.innerHeight,
      hasDialog: Boolean(dialog),
      hasTextarea: Boolean(textarea),
      textareaDisabled:
        textarea && textarea instanceof HTMLTextAreaElement ? textarea.disabled : null,
      dialogRect: dialogRect
        ? { top: dialogRect.top, bottom: dialogRect.bottom, height: dialogRect.height }
        : null,
      textareaRect: textareaRect
        ? { top: textareaRect.top, bottom: textareaRect.bottom, height: textareaRect.height }
        : null,
      sendRect: sendRect
        ? { top: sendRect.top, bottom: sendRect.bottom, height: sendRect.height }
        : null,
      navRect: navRect ? { top: navRect.top, bottom: navRect.bottom, height: navRect.height } : null,
      overlapTextareaNav: Boolean(textareaRect && navRect && textareaRect.bottom > navRect.top),
      overlapSendNav: Boolean(sendRect && navRect && sendRect.bottom > navRect.top),
    };
  });

const collectAssistantState = async (page) =>
  await page.evaluate(() => {
    const panel = document.querySelector("[data-testid='mobile-module2-assistant-dialog']");
    if (!panel) {
      return {
        hasPanel: false,
        textLen: 0,
        hasCitation: false,
        citationCount: 0,
      };
    }
    const text = String(panel.textContent || "").trim();
    const citationEls = Array.from(panel.querySelectorAll("button, [role='button'], a")).filter(
      (el) => /定位|字段|表格|图表|图片|页|引用|证据/.test(String(el.textContent || "").trim()),
    );
    return {
      hasPanel: true,
      textLen: text.length,
      hasCitation: citationEls.length > 0,
      citationCount: citationEls.length,
    };
  });

const main = async () => {
  await ensureDir(outputDir);

  const report = {
    appUrl,
    edgePath,
    outputDir,
    checks: {},
    notes: [],
    screenshots: {},
    errors: [],
  };

  const browser = await chromium.launch({
    headless: true,
    executablePath: edgePath,
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    deviceScaleFactor: 3,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });
  const page = await context.newPage();

  try {
    const login = await loginForProtectedApp(context, appUrl);
    report.checks.authenticated = Boolean(login?.mePayload?.authenticated || login?.mePayload?.user);
    report.notes.push(`auth_account=${String(login?.account || "").trim()}`);

    await openProtectedTab(page, appUrl, "deepread_extraction");
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
    await sleep(1600);
    await dismissOverlayButtons(page);

    const beforeShot = path.join(outputDir, "before-assistant.png");
    await page.screenshot({ path: beforeShot, fullPage: true });
    report.screenshots.beforeAssistant = beforeShot;

    const assistantBtn = page
      .locator("button[aria-label*='助手'], button:has-text('智能助手'), button:has-text('助手')")
      .first();
    await assistantBtn.waitFor({ state: "visible", timeout: 25_000 });
    report.checks.assistantButtonVisible = true;
    report.checks.assistantButtonBox = await assistantBtn.boundingBox();

    await assistantBtn.click({ timeout: 10_000 });
    await sleep(900);

    const dialog = page.locator("[data-testid='mobile-module2-assistant-dialog']");
    await dialog.waitFor({ state: "visible", timeout: 20_000 });
    report.checks.dialogOpened = true;

    const openShot = path.join(outputDir, "assistant-open.png");
    await page.screenshot({ path: openShot, fullPage: true });
    report.screenshots.assistantOpen = openShot;

    const geometry = await collectGeometry(page);
    report.checks.geometry = geometry;

    if (geometry.hasTextarea && geometry.textareaDisabled === false) {
      const textarea = page.locator("textarea").first();
      await textarea.fill("请基于当前文档给出三个要点，并标注证据来源。");

      const sendBtn = page.locator("button[aria-label*='发送'], button[title*='发送']").first();
      if (await sendBtn.isVisible().catch(() => false)) {
        await sendBtn.click({ timeout: 5_000 });
      } else {
        await page.keyboard.press("Enter");
      }

      await sleep(4_500);
      report.checks.assistantInteraction = await collectAssistantState(page);

      const afterSendShot = path.join(outputDir, "assistant-after-send.png");
      await page.screenshot({ path: afterSendShot, fullPage: true });
      report.screenshots.afterSend = afterSendShot;
    } else {
      report.notes.push("assistant_unavailable_or_no_active_doc");
    }

    let closeWorked = false;
    const closeBtn = page
      .locator("div[class*='rounded-t'] button[class*='h-10'][class*='w-10'][class*='rounded-full']")
      .first();
    if (await closeBtn.isVisible().catch(() => false)) {
      await closeBtn.click({ timeout: 5_000, force: true }).catch(() => {});
      closeWorked = await dialog
        .waitFor({ state: "hidden", timeout: 5_000 })
        .then(() => true)
        .catch(() => false);
    }
    if (!closeWorked) {
      const backdrop = page.locator("button[class*='backdrop-blur']").first();
      if (await backdrop.isVisible().catch(() => false)) {
        await backdrop.click({ timeout: 4_000, force: true }).catch(() => {});
        closeWorked = await dialog
          .waitFor({ state: "hidden", timeout: 4_000 })
          .then(() => true)
          .catch(() => false);
      }
    }
    report.checks.closeButtonWorked = closeWorked;
  } catch (error) {
    report.errors.push(String(error?.stack || error?.message || error));
  } finally {
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    await browser.close();
  }

  process.stdout.write(`${reportPath}\n`);
};

await main();
