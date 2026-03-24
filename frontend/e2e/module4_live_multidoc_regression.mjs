#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const appUrl = process.env.MODULE4_APP_URL || "http://127.0.0.1:3000";
const outputRoot =
  process.env.MODULE4_MULTI_DOC_OUTPUT_DIR ||
  path.join(
    projectRoot,
    ".runlogs",
    "module4-live-multidoc-regression",
    new Date().toISOString().replace(/[:.]/g, "-"),
  );
const screenshotRoot = path.join(outputRoot, "screenshots");
const configuredExecutablePath = String(
  process.env.MODULE4_PLAYWRIGHT_EXECUTABLE_PATH || process.env.PLAYWRIGHT_EXECUTABLE_PATH || "",
).trim();
const browserExecutableCandidates = [
  configuredExecutablePath,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);

const defaultTargetLabels = [
  "2021年民政事业发展统计公报.docx",
  "2024年卫生健康事业发展统计公报.md",
  "第二节 溶解液的预处理（含后续子项）.pdf",
  "糖尿病患者数据.xlsx",
  "2025山东省环境空气质量监测数据信息.xlsx",
];

function parseRequestedLabels() {
  const raw = String(process.env.MODULE4_MULTI_DOC_LABELS || "").trim();
  if (!raw) return defaultTargetLabels;
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function safeSlug(value) {
  return String(value || "unknown")
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\u0000-\u001F]+/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 80);
}

async function mkdirp(target) {
  await fs.mkdir(target, { recursive: true });
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

async function openModule4Page(page) {
  await page.goto(appUrl, { waitUntil: "networkidle", timeout: 90_000 });
  const fileSelect = page.getByTestId("module4-file-select");
  if (await fileSelect.isVisible().catch(() => false)) {
    await page.waitForFunction(() => {
      const select = document.querySelector('[data-testid="module4-file-select"]');
      return select instanceof HTMLSelectElement && select.options.length > 1;
    }, { timeout: 60_000 });
    return;
  }

  const menu = page.getByTestId("sidebar-menu-nexus");
  await menu.waitFor({ state: "visible", timeout: 60_000 });
  await menu.click();
  await fileSelect.waitFor({ state: "visible", timeout: 60_000 });
  await page.waitForFunction(() => {
    const select = document.querySelector('[data-testid="module4-file-select"]');
    return select instanceof HTMLSelectElement && select.options.length > 1;
  }, { timeout: 60_000 });
}

async function waitForGraphReady(page, fileHash) {
  await page.waitForFunction(
    (expectedHash) => {
      const dbg = window.__module4GraphDebug;
      const graph = dbg?.getGraph?.();
      if (!graph?.nodes?.length) return false;
      const docNode = graph.nodes.find((item) => String(item.node_type).toLowerCase() === "document");
      return Boolean(docNode && docNode.canonical_key === expectedHash);
    },
    fileHash,
    { timeout: 60_000 },
  );
}

async function getFileOptions(page) {
  return page.evaluate(() => {
    const select = document.querySelector('[data-testid="module4-file-select"]');
    if (!(select instanceof HTMLSelectElement)) return [];
    return Array.from(select.options).map((option) => ({
      label: option.textContent?.trim() || "",
      value: option.value,
    }));
  });
}

async function selectGraphFile(page, option) {
  await page.evaluate(() => {
    window.__module4GraphDebug?.closeInspector?.();
  });
  await page.getByTestId("module4-file-select").selectOption(option.value);
  await waitForGraphReady(page, option.value);
  await page.waitForTimeout(1000);
}

async function inspectGraph(page) {
  return page.evaluate(() => {
    const dbg = window.__module4GraphDebug;
    const graph = dbg?.getGraph?.();
    if (!graph?.nodes?.length) {
      return { ok: false, reason: "graph_not_ready" };
    }
    const counts = graph.nodes.reduce((acc, item) => {
      const key = String(item.node_type || "Unknown");
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    const documentNode =
      graph.nodes.find((item) => String(item.node_type).toLowerCase() === "document") || null;
    const artifactNode =
      graph.nodes.find((item) =>
        ["table", "figure", "image"].includes(String(item.node_type).toLowerCase()),
      ) || null;
    return {
      ok: true,
      nodeCount: graph.nodes.length,
      edgeCount: graph.edges.length,
      typeCounts: counts,
      documentNode: documentNode
        ? {
            id: documentNode.node_id,
            name: documentNode.display_name,
            type: documentNode.node_type,
          }
        : null,
      artifactNode: artifactNode
        ? {
            id: artifactNode.node_id,
            name: artifactNode.display_name,
            type: artifactNode.node_type,
          }
        : null,
    };
  });
}

async function tryOpenDebugNode(page, nodeId, expectedTitle) {
  await page.waitForFunction(
    () =>
      Boolean(
        window.__module4GraphDebug &&
          typeof window.__module4GraphDebug.openNode === "function" &&
          window.__module4GraphDebug.getGraph()?.nodes?.length,
      ),
    { timeout: 20_000 },
  );
  await page.evaluate((value) => {
    window.__module4GraphDebug.openNode(value);
  }, nodeId);
  await page.waitForFunction(
    () => {
      const aside = document.querySelector('[data-testid="module4-detail-aside"]');
      return aside instanceof HTMLElement && aside.clientWidth > 0;
    },
    { timeout: 20_000 },
  );
  await page.waitForFunction(
    (expectedNodeId) => {
      return window.__module4GraphDebug?.getSelectedNodeId?.() === expectedNodeId;
    },
    nodeId,
    { timeout: 20_000 },
  );
  await page.getByTestId("module4-detail-title").waitFor({ state: "visible", timeout: 20_000 });
  await page.getByTestId("module4-analysis-panel").waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForTimeout(expectedTitle ? 900 : 600);
}

async function openDebugNode(page, nodeId, expectedTitle, contextLabel = "") {
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      if (attempt > 0) {
        await page.evaluate(() => {
          window.__module4GraphDebug?.openNode?.(window.__module4GraphDebug?.getSelectedNodeId?.() || "");
        });
      }
      await tryOpenDebugNode(page, nodeId, expectedTitle);
      return;
    } catch (error) {
      lastError = error;
      if (contextLabel) {
        // Best-effort log for debugging order-dependent flakiness.
        // eslint-disable-next-line no-console
        console.warn(`[module4-live-regression] openDebugNode retry: ${contextLabel} attempt=${attempt + 1}`);
      }
      await page.evaluate(() => {
        window.__module4GraphDebug?.closeInspector?.();
      });
      await page.waitForTimeout(800);
    }
  }
  throw lastError;
}

async function readDetailState(page) {
  return page.evaluate(() => {
    const aside = document.querySelector('[data-testid="module4-detail-aside"]');
    if (!(aside instanceof HTMLElement) || aside.clientWidth <= 0) {
      return { ok: false, reason: "detail_not_visible" };
    }
    const text = aside.innerText || "";
    const section = (testId) => aside.querySelector(`[data-testid="${testId}"]`);
    return {
      ok: true,
      title: aside.querySelector('[data-testid="module4-detail-title"]')?.textContent?.trim() || "",
      headings: Array.from(aside.querySelectorAll("h4"))
        .map((item) => item.textContent?.trim() || "")
        .filter(Boolean),
      hasCoreInfo: Boolean(section("module4-detail-core-info")),
      hasAnalysisPanel: Boolean(section("module4-analysis-panel")),
      hasNodeEvidence: Boolean(section("module4-detail-node-evidence")),
      hasEdgeEvidence: Boolean(section("module4-detail-edge-evidence")),
      hasAttributes: Boolean(section("module4-detail-attributes")),
      hasRelations: Boolean(section("module4-detail-relations")),
      hasRelatedNodes: Boolean(section("module4-detail-related-nodes")),
      hasExplainSummary: text.includes("解释结论"),
      hasExplainEvidence: text.includes("解释证据"),
      hasLegacyNodeAttrs: text.includes("节点属性"),
      hasEmptyAlert: text.includes("当前节点没有关联告警"),
      hasKeyEdgeEvidence: text.includes("关键证据关系"),
      hasSourceEvidence: text.includes("来源证据"),
      hasDataframePreview: text.includes("DataFrame 预览"),
      textSample: text.slice(0, 600),
    };
  });
}

function toMarkdown(report) {
  const joined = (value) => (Array.isArray(value) && value.length > 0 ? value.join(" | ") : "(none)");
  const lines = [
    "# Module 4 Live Multi-Document Regression",
    "",
    `- App URL: ${report.appUrl}`,
    `- Checked at: ${report.generatedAt}`,
    `- Documents checked: ${report.results.length}`,
    "",
  ];

  for (const item of report.results) {
    lines.push(`## ${item.label}`);
    lines.push("");
    lines.push(`- File hash: ${item.fileHash}`);
    lines.push(`- Graph nodes / edges: ${item.graph.nodeCount} / ${item.graph.edgeCount}`);
    lines.push(`- Type counts: ${JSON.stringify(item.graph.typeCounts)}`);
    if (item.error) {
      lines.push(`- Error: ${item.error}`);
      lines.push("");
      continue;
    }
    lines.push(`- Document detail headings: ${joined(item.documentDetail?.headings)}`);
    lines.push(
      `- Document detail cleanup: explainSummary=${Boolean(item.documentDetail?.hasExplainSummary)}, explainEvidence=${Boolean(item.documentDetail?.hasExplainEvidence)}, legacyNodeAttrs=${Boolean(item.documentDetail?.hasLegacyNodeAttrs)}, emptyAlert=${Boolean(item.documentDetail?.hasEmptyAlert)}`,
    );
    lines.push(
      `- Document evidence placement: keyEdgeEvidence=${Boolean(item.documentDetail?.hasKeyEdgeEvidence)}, sourceEvidence=${Boolean(item.documentDetail?.hasSourceEvidence)}`,
    );
    if (item.artifactDetail) {
      lines.push(`- Artifact node: ${item.artifact?.name || "(unknown)"}`);
      lines.push(`- Artifact detail headings: ${joined(item.artifactDetail?.headings)}`);
      lines.push(
        `- Artifact evidence placement: sourceEvidence=${Boolean(item.artifactDetail?.hasSourceEvidence)}, dataframe=${Boolean(item.artifactDetail?.hasDataframePreview)}`,
      );
    } else {
      lines.push("- Artifact node: none");
    }
    lines.push(`- Screenshots: ${item.screenshots.document}`);
    if (item.screenshots.artifact) {
      lines.push(`- Artifact screenshot: ${item.screenshots.artifact}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

async function main() {
  await mkdirp(outputRoot);
  await mkdirp(screenshotRoot);

  const executablePath = await resolveBrowserExecutablePath();
  const requestedLabels = parseRequestedLabels();
  const browser = await chromium.launch({
    headless: true,
    executablePath: executablePath || undefined,
  });

  const report = {
    ok: true,
    appUrl,
    generatedAt: new Date().toISOString(),
    requestedLabels,
    outputRoot,
    results: [],
    missingLabels: [],
    eventLog: [],
  };

  try {
    const context = await browser.newContext({
      viewport: { width: 1600, height: 1000 },
    });
    const page = await context.newPage();
    await openModule4Page(page);

    const options = await getFileOptions(page);
    report.availableLabels = options.map((item) => item.label);
    const optionMap = new Map(options.filter((item) => item.value).map((item) => [item.label, item]));

    for (const label of requestedLabels) {
      const option = optionMap.get(label);
      if (!option) {
        report.missingLabels.push(label);
        continue;
      }

      await selectGraphFile(page, option);
      const graph = await inspectGraph(page);
      if (!graph.ok || !graph.documentNode) {
        report.results.push({
          label,
          fileHash: option.value,
          graph,
          error: "document_node_missing",
        });
        continue;
      }

      const docSlug = safeSlug(label);
      try {
        report.eventLog.push({ label, step: "openDocumentNode", at: new Date().toISOString() });
        await openDebugNode(page, graph.documentNode.id, graph.documentNode.name, `doc:${label}`);
        const documentDetail = await readDetailState(page);
        const documentShot = path.join(screenshotRoot, `${docSlug}__document.png`);
        await page.screenshot({ path: documentShot, fullPage: true });

        let artifact = graph.artifactNode;
        let artifactDetail = null;
        let artifactShot = "";
        if (artifact) {
          report.eventLog.push({ label, step: "openArtifactNode", at: new Date().toISOString() });
          await openDebugNode(page, artifact.id, artifact.name, `artifact:${label}`);
          artifactDetail = await readDetailState(page);
          artifactShot = path.join(screenshotRoot, `${docSlug}__artifact.png`);
          await page.screenshot({ path: artifactShot, fullPage: true });
        }

        report.results.push({
          label,
          fileHash: option.value,
          graph,
          artifact,
          documentDetail,
          artifactDetail,
          screenshots: {
            document: documentShot,
            artifact: artifactShot || null,
          },
        });
      } catch (error) {
        report.results.push({
          label,
          fileHash: option.value,
          graph,
          error: String(error?.stack || error || "unknown_detail_error"),
        });
      }
    }

    await context.close();
  } finally {
    await browser.close();
  }

  const jsonPath = path.join(outputRoot, "report.json");
  const markdownPath = path.join(outputRoot, "summary.md");
  await fs.writeFile(jsonPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await fs.writeFile(markdownPath, `${toMarkdown(report)}\n`, "utf8");

  console.log(JSON.stringify({ ok: true, outputRoot, jsonPath, markdownPath }, null, 2));
}

main().catch((error) => {
  console.error(
    JSON.stringify(
      {
        ok: false,
        error: String(error?.stack || error || "unknown_error"),
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
});
