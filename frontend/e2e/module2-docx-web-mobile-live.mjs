#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");

const docxPath = path.resolve(
  String(process.env.MODULE2_DOCX_PATH || "").trim() ||
    path.join(projectRoot, "datasets", "word", "2024年杭州市生态环境状况公报（节选）.docx"),
);
const webAppUrl = String(process.env.MODULE2_WEB_APP_URL || "http://127.0.0.1:3000").trim();
const mobileAppUrl = String(process.env.MODULE2_MOBILE_APP_URL || "http://127.0.0.1:3002").trim();
const apiBase = String(process.env.MODULE2_API_BASE || "http://127.0.0.1:3001").trim();
const playwrightExecutablePath = String(
  process.env.MODULE2_PLAYWRIGHT_EXECUTABLE_PATH ||
    process.env.PLAYWRIGHT_EXECUTABLE_PATH ||
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
).trim();
const headless = String(process.env.MODULE2_HEADLESS || "1").trim() !== "0";

const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputRoot = path.join(projectRoot, ".runlogs", "live-e2e", `module2-docx-web-mobile-${runTag}`);
const webShotDir = path.join(outputRoot, "web");
const mobileShotDir = path.join(outputRoot, "mobile");
const graphShotDir = path.join(outputRoot, "graph-monitor");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseJsonSafe(text, fallback = {}) {
  try {
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
}

function cookieHeaderFrom(cookies = []) {
  return cookies
    .map((item) => `${String(item.name || "").trim()}=${String(item.value || "").trim()}`)
    .filter(Boolean)
    .join("; ");
}

async function ensureDirs() {
  await fs.mkdir(webShotDir, { recursive: true });
  await fs.mkdir(mobileShotDir, { recursive: true });
  await fs.mkdir(graphShotDir, { recursive: true });
}

async function ensureModule2Workbench(page, appUrl) {
  await openProtectedTab(page, appUrl, "deepread_extraction", { waitUntil: "domcontentloaded", attempts: 5 });
  await page.waitForLoadState("networkidle", { timeout: 35_000 }).catch(() => {});

  await page.evaluate((base) => {
    localStorage.setItem("smart_doc_flow.has_seen_onboarding", "true");
    localStorage.setItem("module2_api_base_override", String(base || "").trim());
    window.dispatchEvent(new Event("module2-data-updated"));
  }, apiBase);
  await page.reload({ waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.waitForLoadState("networkidle", { timeout: 35_000 }).catch(() => {});

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  if ((await fileInput.count().catch(() => 0)) > 0) {
    await fileInput.first().waitFor({ state: "attached", timeout: 60_000 });
    return;
  }

  const deepreadMenu = page.getByTestId("sidebar-menu-deepread");
  if (await deepreadMenu.isVisible().catch(() => false)) {
    await deepreadMenu.click({ timeout: 10_000 }).catch(() => {});
  }
  const extractionMenu = page.getByTestId("sidebar-submenu-deepread_extraction");
  if (await extractionMenu.isVisible().catch(() => false)) {
    await extractionMenu.click({ timeout: 10_000 }).catch(() => {});
  }

  if ((await fileInput.count().catch(() => 0)) > 0) {
    await fileInput.first().waitFor({ state: "attached", timeout: 60_000 });
    return;
  }

  await page.locator('input[type="file"]').first().waitFor({ state: "attached", timeout: 60_000 });
}

async function pollExtraction(jobId, cookieHeader, timeoutMs = 1_200_000) {
  const startedAt = Date.now();
  const timeline = [];
  while (Date.now() - startedAt < timeoutMs) {
    let statusCode = 0;
    try {
      const response = await fetch(`${apiBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`, {
        headers: cookieHeader ? { cookie: cookieHeader } : {},
      });
      statusCode = response.status;
      const payload = parseJsonSafe(await response.text(), {});
      const status = String(payload?.status || "").toLowerCase();
      const terminal = Boolean(payload?.terminal) || ["completed", "failed", "cached", "cancelled"].includes(status);
      timeline.push({
        ts: new Date().toISOString(),
        statusCode,
        status,
        terminal,
        completed: Number(payload?.progress?.completed_files || 0),
        failed: Number(payload?.progress?.failed_files || 0),
      });
      if (terminal) {
        return {
          timedOut: false,
          statusCode,
          payload,
          timeline,
          elapsedMs: Date.now() - startedAt,
        };
      }
    } catch (error) {
      timeline.push({
        ts: new Date().toISOString(),
        statusCode,
        error: String(error?.message || error || "poll_error"),
      });
    }
    await sleep(2000);
  }
  return {
    timedOut: true,
    statusCode: 0,
    payload: null,
    timeline,
    elapsedMs: Date.now() - startedAt,
  };
}

async function runModule2Extraction(page, appUrl, scenarioName, screenshotDir, cookieHeader) {
  await ensureModule2Workbench(page, appUrl);

  const fileInput = page.locator('[data-testid="module2-file-input"]');
  const inputTarget = (await fileInput.count().catch(() => 0)) > 0 ? fileInput.first() : page.locator('input[type="file"]').first();
  await inputTarget.setInputFiles(docxPath);
  await page.waitForTimeout(900);

  const startExtractButton = await resolveStartExtractButton(page);
  await startExtractButton.scrollIntoViewIfNeeded().catch(() => {});

  const createResponse = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes("/extract/jobs/create") && res.request().method() === "POST",
      { timeout: 180_000 },
    ),
    startExtractButton.click({ timeout: 25_000 }),
  ]).then((all) => all[0]);
  const createStatus = createResponse.status();
  const createPayload = parseJsonSafe(await createResponse.text(), {});
  const jobId = String(createPayload?.job_id || "").trim();
  if (!jobId) {
    throw new Error(`${scenarioName}:missing_job_id`);
  }

  const terminal = await pollExtraction(jobId, cookieHeader, 1_200_000);
  await page.waitForTimeout(1800);
  await page.screenshot({ path: path.join(screenshotDir, `${scenarioName}-after-extract.png`), fullPage: true });

  const uiTrace = await page.evaluate(() => {
    const textOf = (el) => String(el?.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
    const cards = Array.from(document.querySelectorAll('[data-testid="module2-trace-card"]'));
    const tableLikeCards = cards.filter((card) => {
      const t = textOf(card);
      return t.includes("table") || t.includes("表") || Boolean(card.querySelector("table"));
    }).length;
    const imageLikeCards = cards.filter((card) => {
      const t = textOf(card);
      return t.includes("image") || t.includes("图") || Boolean(card.querySelector('[data-testid="module2-trace-artifact-image"]'));
    }).length;
    return {
      tracePanelVisible: Boolean(document.querySelector('[data-testid="module2-trace-panel"]')),
      traceCardCount: cards.length,
      traceArtifactImageCount: document.querySelectorAll('[data-testid="module2-trace-artifact-image"]').length,
      traceTableDomCount: document.querySelectorAll('[data-testid="module2-trace-card"] table').length,
      tableLikeCards,
      imageLikeCards,
      traceGroupLabels: Array.from(document.querySelectorAll('[data-testid="module2-trace-group-label"]'))
        .map((el) => String(el.textContent || "").replace(/\s+/g, " ").trim())
        .filter(Boolean),
    };
  });

  return {
    createStatus,
    createPayload,
    jobId,
    terminal,
    documents: Array.isArray(terminal?.payload?.documents) ? terminal.payload.documents : [],
    uiTrace,
  };
}

async function resolveStartExtractButton(page) {
  const primary = page.locator('[data-testid="module2-start-extract"]').first();
  if ((await primary.count().catch(() => 0)) > 0) {
    return primary;
  }

  const roleMatch = page.getByRole("button", { name: /开始解析|解析当前文件|开始提取/i }).first();
  if ((await roleMatch.count().catch(() => 0)) > 0) {
    return roleMatch;
  }

  const textMatch = page.locator("button").filter({ hasText: /开始解析|解析当前文件|开始提取/i }).first();
  if ((await textMatch.count().catch(() => 0)) > 0) {
    return textMatch;
  }

  throw new Error("start_extract_button_not_found");
}

function getTraceKind(hit) {
  const objectType = String(hit?.object_type || "").trim().toLowerCase();
  if (objectType === "table") return "table";
  if (objectType === "figure" || objectType === "image") {
    const locator = hit?.locator && typeof hit.locator === "object" ? hit.locator : {};
    const figureType = String(locator.figure_type || "").trim().toLowerCase();
    if (figureType === "table" || figureType === "spreadsheet") return "table";
    const dataframe = locator?.dataframe && typeof locator.dataframe === "object" ? locator.dataframe : {};
    const rows = Array.isArray(dataframe?.rows) ? dataframe.rows : [];
    return rows.length > 0 ? "table" : "image";
  }
  return "other";
}

async function getTraceStats(doc, cookieHeader) {
  const payload = await fetch(`${apiBase}/extract/trace/locate`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
    },
    body: JSON.stringify({ document: doc, top_k: 160 }),
  })
    .then(async (res) => parseJsonSafe(await res.text(), {}))
    .catch(() => ({}));

  const hits = Array.isArray(payload?.hits) ? payload.hits : Array.isArray(doc?.trace_hits) ? doc.trace_hits : [];
  return {
    totalHits: hits.length,
    tableHits: hits.filter((hit) => getTraceKind(hit) === "table").length,
    imageHits: hits.filter((hit) => getTraceKind(hit) === "image").length,
  };
}

async function readMobileArtifactPanel(page, targetFileName) {
  await page.setViewportSize({ width: 390, height: 844 });
  await openProtectedTab(page, mobileAppUrl, "deepread_extraction", { waitUntil: "domcontentloaded", attempts: 5 });
  await page.waitForLoadState("networkidle", { timeout: 35_000 }).catch(() => {});
  await page.waitForTimeout(1200);
  await page.locator('[data-testid="mobile-extraction-document-card"]').first().waitFor({
    state: "visible",
    timeout: 45_000,
  }).catch(() => {});

  const selected = await page.evaluate((fileName) => {
    const norm = (v) => String(v || "").replace(/\s+/g, " ").trim();
    const target = norm(fileName || "");
    const targetNoExt = target.includes(".") ? target.slice(0, target.lastIndexOf(".")) : target;
    const cards = Array.from(document.querySelectorAll('[data-testid="mobile-extraction-document-card"]'));
    const matchedCard = cards.find((card) => {
      const cardName = norm(card.getAttribute("data-file-name"));
      const cardText = norm(card.textContent);
      return (
        (target && (cardName.includes(target) || cardText.includes(target))) ||
        (targetNoExt && (cardName.includes(targetNoExt) || cardText.includes(targetNoExt)))
      );
    });
    const pickedCard = matchedCard || cards[0] || null;
    const picked = pickedCard?.querySelector('[data-testid="mobile-document-artifacts-button"]') || null;
    if (!(picked instanceof HTMLButtonElement)) return false;
    picked.click();
    return true;
  }, targetFileName);
  await page.locator("#mobile-artifact-detail").waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});
  await page.waitForFunction(
    () => {
      const detail = document.getElementById("mobile-artifact-detail");
      if (!detail) return false;
      const counts = ["field", "table", "chart", "image"].map((name) =>
        Number(detail.getAttribute(`data-${name}-count`) || 0),
      );
      return counts.some((count) => count > 0) || !detail.textContent?.includes("正在恢复并定位产物");
    },
    { timeout: 45_000 },
  ).catch(() => {});

  const tabLabels = await page.evaluate(() => {
    const detail = document.getElementById("mobile-artifact-detail");
    if (!detail) return [];
    return Array.from(detail.querySelectorAll('[data-testid^="mobile-artifact-tab-"]'))
      .map((btn) => String(btn.textContent || "").replace(/\s+/g, " ").trim())
      .filter(Boolean);
  });

  async function clickAndCount(tabName) {
    const clicked = await page.evaluate((idx) => {
      const detail = document.getElementById("mobile-artifact-detail");
      if (!detail) return false;
      const target = detail.querySelector(`[data-testid="mobile-artifact-tab-${idx}"]`);
      if (!(target instanceof HTMLButtonElement)) return false;
      target.click();
      return true;
    }, tabName);
    await page.waitForTimeout(280);
    const count = await page.evaluate((idx) => {
      const detail = document.getElementById("mobile-artifact-detail");
      if (!detail) return 0;
      const attrName = idx === "fields" ? "field" : idx === "tables" ? "table" : idx === "charts" ? "chart" : "image";
      const attrCount = Number(detail.getAttribute(`data-${attrName}-count`) || 0);
      if (Number.isFinite(attrCount) && attrCount > 0) return attrCount;
      return detail.querySelectorAll(`[data-testid="mobile-artifact-${attrName}-card"]`).length;
    }, tabName);
    return { clicked, count };
  }

  const field = await clickAndCount("fields");
  const table = await clickAndCount("tables");
  const chart = await clickAndCount("charts");
  const image = await clickAndCount("images");

  return {
    selected,
    tabLabels,
    fieldCount: field.count,
    tableCount: table.count,
    chartCount: chart.count,
    imageCount: image.count,
  };
}

async function waitGraphReady(fileHash, cookieHeader, timeoutMs = 240_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(
        `${apiBase}/module4/graph/files/${encodeURIComponent(fileHash)}/view?limit_nodes=1200&limit_edges=2400`,
        { headers: cookieHeader ? { cookie: cookieHeader } : {} },
      );
      const payload = parseJsonSafe(await response.text(), {});
      const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
      const edges = Array.isArray(payload?.edges) ? payload.edges : [];
      if (nodes.length > 0) {
        return { ready: true, nodes: nodes.length, edges: edges.length, payload };
      }
    } catch {
      // continue polling
    }
    await sleep(3000);
  }
  return { ready: false, nodes: 0, edges: 0, payload: null };
}

async function monitorWebGraph(page, fileHash, fileName) {
  await openProtectedTab(page, webAppUrl, "nexus", { waitUntil: "domcontentloaded", attempts: 6 });
  await page.waitForLoadState("networkidle", { timeout: 40_000 }).catch(() => {});
  await page.waitForFunction(() => {
    const legacy = document.querySelector('[data-testid="module4-file-select"]');
    if (legacy) return true;
    const hasHeader = Boolean(document.querySelector("header"));
    const hasMain = Boolean(document.querySelector("main"));
    return hasHeader && hasMain;
  }, { timeout: 90_000 });

  const selectResult = await page.evaluate(({ hash, name }) => {
    const norm = (v) => String(v || "").replace(/\s+/g, " ").trim();
    const target = norm(name || "");
    const targetNoExt = target.includes(".") ? target.slice(0, target.lastIndexOf(".")) : target;

    const legacy = document.querySelector('[data-testid="module4-file-select"]');
    if (legacy instanceof HTMLSelectElement) {
      let option = Array.from(legacy.options).find((opt) => opt.value === hash);
      if (!option) {
        option = Array.from(legacy.options).find((opt) => {
          const text = norm(opt.textContent);
          return (target && text.includes(target)) || (targetNoExt && text.includes(targetNoExt));
        });
      }
      if (!option) {
        return {
          ok: false,
          reason: "legacy_option_not_found",
          options: Array.from(legacy.options).slice(0, 20).map((opt) => ({
            value: opt.value,
            label: norm(opt.textContent),
          })),
        };
      }
      legacy.value = String(option.value || "");
      legacy.dispatchEvent(new Event("input", { bubbles: true }));
      legacy.dispatchEvent(new Event("change", { bubbles: true }));
      return { ok: true, mode: "legacy_select", value: legacy.value, label: norm(option.textContent) };
    }

    const header = document.querySelector("header");
    if (!header) return { ok: false, reason: "header_missing" };

    const headerButtons = Array.from(header.querySelectorAll("button"));
    if (headerButtons.length === 0) return { ok: false, reason: "header_buttons_missing" };
    const trigger =
      headerButtons.find((btn) => {
        const text = norm(btn.textContent);
        return text.includes("租户总图") || (targetNoExt && text.includes(targetNoExt));
      }) || headerButtons[0];
    if (!(trigger instanceof HTMLButtonElement)) return { ok: false, reason: "dropdown_trigger_missing" };

    trigger.click();
    const allButtons = Array.from(document.querySelectorAll("button"));
    const option =
      allButtons.find((btn) => {
        const text = norm(btn.textContent);
        return (target && text.includes(target)) || (targetNoExt && text.includes(targetNoExt));
      }) ||
      allButtons.find((btn) => {
        const text = norm(btn.textContent);
        return hash && text.includes(String(hash).slice(0, 8));
      }) ||
      null;

    if (!(option instanceof HTMLButtonElement)) {
      return {
        ok: false,
        reason: "dropdown_option_not_found",
        observed: allButtons.slice(0, 20).map((btn) => norm(btn.textContent)).filter(Boolean),
      };
    }
    option.click();
    return { ok: true, mode: "graphrag_dropdown", label: norm(option.textContent) };
  }, { hash: fileHash, name: fileName });

  await page.waitForTimeout(1400);
  const refreshClicked = await page.evaluate(() => {
    const norm = (v) => String(v || "").replace(/\s+/g, " ").trim();
    const byTestId = document.querySelector('[data-testid="module4-refresh-graph"]');
    if (byTestId instanceof HTMLButtonElement) {
      byTestId.click();
      return true;
    }
    const btn = Array.from(document.querySelectorAll("button")).find((button) => norm(button.textContent).includes("刷新"));
    if (btn instanceof HTMLButtonElement) {
      btn.click();
      return true;
    }
    return false;
  });
  if (refreshClicked) await page.waitForTimeout(1400);

  const samples = [];
  for (let i = 0; i < 12; i += 1) {
    const state = await page.evaluate(() => {
      const main = document.querySelector("main");
      const host = document.querySelector('[data-testid="module4-graph-host"]') || main;
      const spans = Array.from(document.querySelectorAll("span,div,p")).map((el) => String(el.textContent || "").trim());
      const metric = spans.find((text) => text.includes("节点") || text.toLowerCase().includes("node")) || "";
      const metricMatch = metric.match(/(\d+)/);
      const emptyHint = spans.some((text) => text.includes("当前图谱没有可渲染节点"));
      const headerButtons = Array.from(document.querySelectorAll("header button")).map((button) =>
        String(button.textContent || "").replace(/\s+/g, " ").trim(),
      );
      return {
        ts: new Date().toISOString(),
        selectedLabel: headerButtons[0] || "",
        emptyState: Boolean(host?.querySelector(".module4-empty-state")) || emptyHint,
        svgCount: host?.querySelectorAll("svg").length || 0,
        canvasCount: host?.querySelectorAll("canvas").length || 0,
        circleCount: host?.querySelectorAll("circle").length || 0,
        displayedNodeCount: metricMatch ? Number(metricMatch[1]) : 0,
        metricText: metric,
      };
    });
    samples.push(state);
    await page.screenshot({
      path: path.join(graphShotDir, `graph-sample-${String(i + 1).padStart(2, "0")}.png`),
      fullPage: true,
    });
    if (i < 11) await page.waitForTimeout(5000);
  }

  const firstVisibleIndex = samples.findIndex(
    (s) => (s.svgCount > 0 || s.canvasCount > 0 || s.circleCount > 0 || s.displayedNodeCount > 0) && !s.emptyState,
  );
  const disappearAfterVisible =
    firstVisibleIndex >= 0 &&
    samples
      .slice(firstVisibleIndex + 1)
      .some((s) => (s.svgCount === 0 && s.canvasCount === 0 && s.circleCount === 0 && s.displayedNodeCount === 0) || s.emptyState);

  return {
    selectResult,
    samples,
    firstVisibleIndex,
    disappearAfterVisible,
  };
}

async function main() {
  await ensureDirs();
  await fs.access(docxPath);

  const report = {
    generatedAt: new Date().toISOString(),
    outputRoot,
    docxPath,
    webAppUrl,
    mobileAppUrl,
    apiBase,
  };

  const browser = await chromium.launch({
    headless,
    executablePath: playwrightExecutablePath || undefined,
  });

  try {
    const webContext = await browser.newContext({ viewport: { width: 1560, height: 980 } });
    const webAuth = await loginForProtectedApp(webContext, webAppUrl);
    const webCookies = await webContext.cookies(webAppUrl);
    const webCookieHeader = cookieHeaderFrom(webCookies) || String(webAuth?.cookieHeader || "");
    const webPage = await webContext.newPage();

    const webFlow = await runModule2Extraction(webPage, webAppUrl, "web-docx", webShotDir, webCookieHeader);
    report.webFlow = {
      createStatus: webFlow.createStatus,
      jobId: webFlow.jobId,
      terminal: !webFlow.terminal?.timedOut,
      terminalStatus: String(webFlow.terminal?.payload?.status || ""),
      elapsedMs: Number(webFlow.terminal?.elapsedMs || 0),
      docsCount: webFlow.documents.length,
      uiTrace: webFlow.uiTrace,
    };

    const firstWebDoc = webFlow.documents[0] || null;
    if (firstWebDoc) {
      report.webFlow.document = {
        fileName: String(firstWebDoc?.file_name || ""),
        fileHash: String(firstWebDoc?.file_hash || ""),
        errors: Array.isArray(firstWebDoc?.errors) ? firstWebDoc.errors : [],
      };
      report.webFlow.traceStats = await getTraceStats(firstWebDoc, webCookieHeader);

      const graphApi = await waitGraphReady(String(firstWebDoc?.file_hash || ""), webCookieHeader, 240_000);
      report.graphApi = graphApi;
      report.graphMonitor = await monitorWebGraph(webPage, String(firstWebDoc?.file_hash || ""), String(firstWebDoc?.file_name || ""));
    }

    await webPage.screenshot({ path: path.join(webShotDir, "web-final.png"), fullPage: true });

    const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const mobileAuth = await loginForProtectedApp(mobileContext, mobileAppUrl);
    const mobileCookies = await mobileContext.cookies(mobileAppUrl);
    const mobileCookieHeader = cookieHeaderFrom(mobileCookies) || String(mobileAuth?.cookieHeader || "");
    const mobilePage = await mobileContext.newPage();

    const mobileFlow = await runModule2Extraction(mobilePage, mobileAppUrl, "mobile-docx", mobileShotDir, mobileCookieHeader);
    report.mobileFlow = {
      createStatus: mobileFlow.createStatus,
      jobId: mobileFlow.jobId,
      terminal: !mobileFlow.terminal?.timedOut,
      terminalStatus: String(mobileFlow.terminal?.payload?.status || ""),
      elapsedMs: Number(mobileFlow.terminal?.elapsedMs || 0),
      docsCount: mobileFlow.documents.length,
      uiTrace: mobileFlow.uiTrace,
    };

    const firstMobileDoc = mobileFlow.documents[0] || null;
    if (firstMobileDoc) {
      report.mobileFlow.document = {
        fileName: String(firstMobileDoc?.file_name || ""),
        fileHash: String(firstMobileDoc?.file_hash || ""),
        errors: Array.isArray(firstMobileDoc?.errors) ? firstMobileDoc.errors : [],
      };
      report.mobileFlow.traceStats = await getTraceStats(firstMobileDoc, mobileCookieHeader);
      report.mobileFlow.mobileArtifactPanel = await readMobileArtifactPanel(mobilePage, String(firstMobileDoc?.file_name || ""));
    }

    await mobilePage.screenshot({ path: path.join(mobileShotDir, "mobile-final.png"), fullPage: true });

    await webContext.close();
    await mobileContext.close();
  } finally {
    await browser.close();
  }

  const reportPath = path.join(outputRoot, "report.json");
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({ ok: true, reportPath, outputRoot }, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: String(error?.stack || error || "unknown_error") }, null, 2));
  process.exit(1);
});
