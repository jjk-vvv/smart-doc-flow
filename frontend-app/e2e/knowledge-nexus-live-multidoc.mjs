#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { loginForProtectedApp, openProtectedTab } from "./auth-session.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const appUrl = process.env.MODULE4_APP_URL || "http://127.0.0.1:3002";
const module4ApiBase = String(process.env.MODULE4_API_BASE || appUrl).trim().replace(/\/+$/, "");
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

async function fetchJson(url, init = {}) {
  const response = await fetch(url, init);
  const text = await response.text().catch(() => "");
  let payload = null;
  try {
    payload = text ? JSON.parse(text.replace(/^\uFEFF/, "")) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(`request_failed:${response.status}:${url}:${text.slice(0, 400)}`);
  }
  return payload;
}

async function fetchFileGraph(fileHash) {
  return await fetchJson(
    `${module4ApiBase}/module4/graph/files/${encodeURIComponent(fileHash)}/view?limit_nodes=1200&limit_edges=2400`,
  );
}

async function fetchNodeDetail(fileHash, nodeId) {
  return await fetchJson(
    `${module4ApiBase}/module4/graph/files/${encodeURIComponent(fileHash)}/node/${encodeURIComponent(nodeId)}?depth=1&limit=180`,
  );
}

function summarizeGraph(graph) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];
  const typeCounts = nodes.reduce((acc, item) => {
    const key = String(item?.node_type || "Unknown");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const documentNode =
    nodes.find((item) => String(item?.node_type || "").toLowerCase() === "document") || null;
  const artifactNode =
    nodes.find((item) => ["table", "figure", "image"].includes(String(item?.node_type || "").toLowerCase())) || null;

  return {
    ok: nodes.length > 0,
    nodeCount: nodes.length,
    edgeCount: edges.length,
    typeCounts,
    documentNode: documentNode
      ? {
          id: String(documentNode.node_id || "").trim(),
          name: String(documentNode.display_name || "").trim(),
          type: String(documentNode.node_type || "").trim(),
        }
      : null,
    artifactNode: artifactNode
      ? {
          id: String(artifactNode.node_id || "").trim(),
          name: String(artifactNode.display_name || "").trim(),
          type: String(artifactNode.node_type || "").trim(),
        }
      : null,
  };
}

function summarizeNodeDetail(detail) {
  const node = detail?.node && typeof detail.node === "object" ? detail.node : null;
  const attrs = node?.attrs && typeof node.attrs === "object" ? node.attrs : {};
  const evidence = Array.isArray(detail?.evidence) ? detail.evidence : [];
  const edgeEvidence =
    detail?.edge_evidence && typeof detail.edge_evidence === "object" ? detail.edge_evidence : {};
  const relatedNodes = Array.isArray(detail?.graph?.nodes) ? detail.graph.nodes : [];
  const relatedEdges = Array.isArray(detail?.graph?.edges) ? detail.graph.edges : [];

  return {
    ok: Boolean(node),
    title: String(node?.display_name || "").trim(),
    hasCoreInfo: Object.keys(attrs).length > 0,
    hasAnalysisPanel: Boolean(node),
    hasNodeEvidence: evidence.length > 0,
    hasEdgeEvidence: Object.keys(edgeEvidence).length > 0,
    hasAttributes: Object.keys(attrs).length > 0,
    hasRelations: relatedEdges.length > 0,
    hasRelatedNodes: relatedNodes.length > 1,
    evidenceCount: evidence.length,
    edgeEvidenceCount: Object.keys(edgeEvidence).length,
    relatedNodeCount: Math.max(relatedNodes.length - 1, 0),
    relatedEdgeCount: relatedEdges.length,
    textSample: JSON.stringify(
      {
        title: String(node?.display_name || "").trim(),
        evidencePreview: evidence.slice(0, 2),
        edgeEvidenceKeys: Object.keys(edgeEvidence).slice(0, 6),
      },
      null,
      2,
    ).slice(0, 600),
  };
}

async function openModule4Page(page) {
  await openProtectedTab(page, appUrl, "nexus", { waitUntil: "networkidle" });
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

async function waitForSelectValue(page, expectedValue, timeoutMs = 12_000) {
  await page.waitForFunction(
    (value) => {
      const select = document.querySelector('[data-testid="module4-file-select"]');
      return select instanceof HTMLSelectElement && select.value === value;
    },
    expectedValue,
    { timeout: timeoutMs },
  );
}

async function setGraphFileValue(page, expectedValue) {
  const applied = await page.evaluate((value) => {
    const select = document.querySelector('[data-testid="module4-file-select"]');
    if (!(select instanceof HTMLSelectElement)) return false;
    const optionExists = Array.from(select.options).some((option) => option.value === value);
    if (!optionExists) return false;
    select.value = value;
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }, expectedValue);
  if (!applied) {
    throw new Error(`module4_file_select_option_missing:${expectedValue}`);
  }
}

async function clickRefreshGraph(page) {
  const refreshButton = page.getByTestId("module4-refresh-graph");
  if (await refreshButton.isVisible().catch(() => false)) {
    await refreshButton.click();
  }
}

async function readGraphCanvasState(page) {
  return page.evaluate(() => {
    const host = document.querySelector('[data-testid="module4-graph-host"]');
    const select = document.querySelector('[data-testid="module4-file-select"]');
    const spanTexts = Array.from(document.querySelectorAll("span"))
      .map((item) => (item.textContent || "").trim())
      .filter(Boolean);
    const nodeMetricText = spanTexts.find((text) => text.includes("节点数")) || "";
    const nodeMetricMatch = nodeMetricText.match(/(\d+)/);

    return {
      selectValue: select instanceof HTMLSelectElement ? select.value : "",
      selectedLabel:
        select instanceof HTMLSelectElement ? select.selectedOptions?.[0]?.textContent?.trim() || "" : "",
      emptyState: Boolean(host?.querySelector(".module4-empty-state")),
      svgCount: host?.querySelectorAll("svg").length || 0,
      circleCount: host?.querySelectorAll("circle").length || 0,
      displayedNodeCount: nodeMetricMatch ? Number(nodeMetricMatch[1]) : 0,
      nodeMetricText,
    };
  });
}

function canvasMatchesExpected(state, option, graphSummary) {
  if (!state) return false;
  if (state.selectValue !== option.value) return false;
  if (state.emptyState) return false;
  if (!state.svgCount && !state.circleCount) return false;
  return state.displayedNodeCount === graphSummary.nodeCount;
}

function formatCanvasState(state) {
  if (!state) return "state=unavailable";
  return JSON.stringify(state, null, 2);
}

async function waitForRenderedGraph(page, option, graphSummary, timeoutMs) {
  const startedAt = Date.now();
  let lastState = await readGraphCanvasState(page).catch(() => null);

  while (Date.now() - startedAt < timeoutMs) {
    lastState = await readGraphCanvasState(page).catch(() => null);
    if (canvasMatchesExpected(lastState, option, graphSummary)) {
      return lastState;
    }
    await sleep(900);
  }

  throw new Error(
    `module4_graph_not_rendered:${option.label}:expected_nodes=${graphSummary.nodeCount}:${formatCanvasState(lastState)}`,
  );
}

async function selectGraphFile(page, option, graphSummary) {
  const phases = [
    { timeoutMs: 12_000, refresh: false },
    { timeoutMs: 18_000, refresh: true },
    { timeoutMs: 24_000, refresh: true },
  ];
  let lastError = null;

  for (let index = 0; index < phases.length; index += 1) {
    const phase = phases[index];
    try {
      try {
        await page.getByTestId("module4-file-select").selectOption(option.value, { timeout: 6_000 });
      } catch {
        await setGraphFileValue(page, option.value);
      }
      await waitForSelectValue(page, option.value);
      if (phase.refresh) {
        await clickRefreshGraph(page);
        await sleep(1200);
      }
      return await waitForRenderedGraph(page, option, graphSummary, phase.timeoutMs);
    } catch (error) {
      lastError = error;
      console.warn(
        `[module4-live-regression] selectGraphFile retry label=${option.label} attempt=${index + 1}/${phases.length} reason=${String(error?.message || error || "unknown_error").slice(0, 260)}`,
      );
    }
  }

  throw lastError || new Error(`module4_select_graph_file_failed:${option.label}`);
}

function toMarkdown(report) {
  const lines = [
    "# Module 4 Live Multi-Document Regression",
    "",
    `- App URL: ${report.appUrl}`,
    `- API Base: ${report.apiBase}`,
    `- Checked at: ${report.generatedAt}`,
    `- Documents checked: ${report.results.length}`,
    "",
  ];

  for (const item of report.results) {
    lines.push(`## ${item.label}`);
    lines.push("");
    lines.push(`- File hash: ${item.fileHash}`);
    if (item.error) {
      lines.push(`- Error: ${item.error}`);
      lines.push("");
      continue;
    }
    lines.push(`- API graph nodes / edges: ${item.graph.nodeCount} / ${item.graph.edgeCount}`);
    lines.push(`- API graph type counts: ${JSON.stringify(item.graph.typeCounts)}`);
    lines.push(
      `- Canvas state: selected=${item.canvas.selectedLabel}, displayedNodes=${item.canvas.displayedNodeCount}, svg=${item.canvas.svgCount}, circles=${item.canvas.circleCount}, empty=${item.canvas.emptyState}`,
    );
    lines.push(
      `- Document detail: title=${item.documentDetail.title || "(none)"}, nodeEvidence=${item.documentDetail.hasNodeEvidence}, edgeEvidence=${item.documentDetail.hasEdgeEvidence}, relatedNodes=${item.documentDetail.relatedNodeCount}`,
    );
    if (item.artifactDetail) {
      lines.push(
        `- Artifact detail: title=${item.artifactDetail.title || "(none)"}, nodeEvidence=${item.artifactDetail.hasNodeEvidence}, edgeEvidence=${item.artifactDetail.hasEdgeEvidence}, relatedNodes=${item.artifactDetail.relatedNodeCount}`,
      );
    } else {
      lines.push("- Artifact detail: none");
    }
    lines.push(`- Screenshot: ${item.screenshots.graph}`);
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
    apiBase: module4ApiBase,
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
    await loginForProtectedApp(context, appUrl);
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

      try {
        report.eventLog.push({ label, step: "fetchFileGraph", at: new Date().toISOString() });
        const graphRaw = await fetchFileGraph(option.value);
        const graph = summarizeGraph(graphRaw);
        if (!graph.ok || !graph.documentNode) {
          report.results.push({
            label,
            fileHash: option.value,
            graph,
            error: "document_node_missing",
          });
          continue;
        }

        report.eventLog.push({ label, step: "selectGraphFile", at: new Date().toISOString() });
        const canvas = await selectGraphFile(page, option, graph);
        const graphShot = path.join(screenshotRoot, `${safeSlug(label)}__graph.png`);
        await page.screenshot({ path: graphShot, fullPage: true });

        report.eventLog.push({ label, step: "fetchDocumentDetail", at: new Date().toISOString() });
        const documentDetailRaw = await fetchNodeDetail(option.value, graph.documentNode.id);
        const documentDetail = summarizeNodeDetail(documentDetailRaw);

        let artifact = graph.artifactNode;
        let artifactDetail = null;
        if (artifact?.id) {
          report.eventLog.push({ label, step: "fetchArtifactDetail", at: new Date().toISOString() });
          artifactDetail = summarizeNodeDetail(await fetchNodeDetail(option.value, artifact.id));
        }

        report.results.push({
          label,
          fileHash: option.value,
          graph,
          canvas,
          artifact,
          documentDetail,
          artifactDetail,
          screenshots: {
            graph: graphShot,
          },
        });
      } catch (error) {
        report.results.push({
          label,
          fileHash: option.value,
          error: String(error?.stack || error || "unknown_module4_live_error"),
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
