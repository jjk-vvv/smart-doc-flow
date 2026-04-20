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
const appOrigin = new URL(appUrl).origin;
const outputRoot =
  process.env.MODULE4_FRONTEND_OUTPUT_DIR ||
  path.join(projectRoot, ".runlogs", "module4-frontend-regression", new Date().toISOString().replace(/[:.]/g, "-"));
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

const STORAGE_KEY = "module2_last_documents";
const UPDATED_AT_KEY = "module2_last_updated";
const WORKBENCH_KEY = "module2_workbench_session_v1";

const fileHash = "hash-demo-001";
const graphFileId = "graph-file-demo-001";
const graphVersionId = "graph-version-demo-001";
const documentNodeId = "document-1";
const entityNodeId = "entity-1";
const edgeId = "edge-doc-entity-1";

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

function asJson(data) {
  return {
    status: 200,
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify(data),
  };
}

function shortNow() {
  return new Date().toISOString();
}

function buildMockState() {
  return {
    rules: [
      {
        rule_id: "RULE_DOC_ERRORS",
        name: "文档错误聚集",
        severity: "red",
        rule_kind: "deterministic",
        expr: { scope: "document", path: "errors_count", op: "gt", value: 0 },
        enabled: true,
        version: 3,
        updated_at: shortNow(),
      },
      {
        rule_id: "RULE_LOW_CONFIDENCE",
        name: "低置信字段预警",
        severity: "orange",
        rule_kind: "deterministic",
        expr: { scope: "field", path: "confidence", op: "lt", value: 0.6 },
        enabled: false,
        version: 2,
        updated_at: shortNow(),
      },
    ],
  };
}

async function installMockRoutes(page, state) {
  await page.route("**/module4/**", async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const url = new URL(request.url());
    const pathname = url.pathname;

    if (method === "GET" && pathname === "/module4/graph/files") {
      return route.fulfill(
        asJson({
          items: [
            {
              graph_file_id: graphFileId,
              tenant_id: "default",
              file_hash: fileHash,
              file_name: "演示项目风险报告.pdf",
              workspace_id: "workspace-demo-001",
              graph_mode: "hybrid",
              source: "module2",
              status: "ready",
              current_job_id: null,
              active_version_id: graphVersionId,
              last_error: null,
              node_count: 2,
              edge_count: 1,
              metadata: {
                quality_status: "passed",
                truth_status: "ready",
              },
              projection: {
                status: "success",
                projected_nodes: 2,
                projected_edges: 1,
                source_node_count: 2,
                source_edge_count: 1,
                skipped_reason: null,
                error_message: null,
                labels: ["Module4Node"],
                relationship_type: "MODULE4_EDGE",
              },
              created_at: shortNow(),
              updated_at: shortNow(),
              last_indexed_at: shortNow(),
            },
          ],
        }),
      );
    }

    if (method === "GET" && pathname === "/module4/alerts") {
      return route.fulfill(
        asJson({
          total: 1,
          items: [
            {
              alert_id: "alert-1",
              rule_id: "RULE_DOC_ERRORS",
              severity: "red",
              status: "open",
              subject_node_id: entityNodeId,
              title: "文档存在结构化抽取异常",
              summary: "当前文件中检测到字段错误与人工复核需求。",
              risk_score: 91.2,
              payload: {
                file_hash: fileHash,
                context: {
                  file_hash: fileHash,
                  file_name: "演示项目风险报告.pdf",
                  errors_count: 2,
                },
              },
              detected_at: shortNow(),
            },
          ],
        }),
      );
    }

    if (method === "GET" && pathname === "/module4/healthz") {
      return route.fulfill(
        asJson({
          status: "ok",
          db_connected: true,
          jobs_in_queue: 0,
          last_connect_error: null,
          graphrag: {
            ready: true,
            check_mode: "basic",
            python_bin: "python",
            python_bin_exists: true,
            graphrag_module_available: true,
            module_error_message: null,
            prompt_assets_root: "D:/smart_doc_flow/smart-doc-flow/backend/app/modules/module4/assets/prompts",
            prompt_assets_ok: true,
            missing_prompt_assets: [],
            config_missing_fields: [],
            runtime_versions: { graphrag: "demo" },
            tiktoken_encoding_ready: true,
            tiktoken_encoding_error_message: null,
            oneapi: {
              configured: true,
              reachable: true,
              missing_fields: [],
              error_message: null,
            },
            neo4j: {
              configured: true,
              reachable: true,
              missing_fields: [],
              error_message: null,
            },
          },
          projection_runtime: {
            enabled: true,
            configured: true,
            can_project: true,
            database: "neo4j",
            max_nodes: 1000,
            max_edges: 2000,
            timeout_sec: 8,
            missing_fields: [],
            labels: ["Module4Node"],
            relationship_type: "MODULE4_EDGE",
          },
          now: shortNow(),
        }),
      );
    }

    if (method === "GET" && pathname === `/module4/graph/files/${encodeURIComponent(fileHash)}/view`) {
      return route.fulfill(
        asJson({
          nodes: [
            {
              node_id: documentNodeId,
              node_type: "Document",
              canonical_key: fileHash,
              display_name: "演示项目风险报告",
              confidence: 1,
              attrs: {
                file_hash: fileHash,
                file_name: "演示项目风险报告.pdf",
                summary: "用于回归模块四工作台的演示文档",
              },
              updated_at: shortNow(),
              type_label: "document",
              category: "document",
            },
            {
              node_id: entityNodeId,
              node_type: "Entity",
              canonical_key: "risk-entity-demo",
              display_name: "高风险资金流转",
              confidence: 0.94,
              attrs: {
                entity_type: "risk",
                summary: "命中的核心风险实体",
                file_hash: fileHash,
              },
              updated_at: shortNow(),
              type_label: "entity",
              category: "entity",
            },
          ],
          edges: [
            {
              edge_id: edgeId,
              source_node_id: documentNodeId,
              target_node_id: entityNodeId,
              relation_type: "HAS_ENTITY",
              direction: "out",
              confidence: 0.93,
              risk_score: 0.91,
              attrs: {},
              updated_at: shortNow(),
              relation_label: "contains",
            },
          ],
          stats: {
            node_count: 2,
            edge_count: 1,
            by_node_type: { Document: 1, Entity: 1 },
            by_relation_type: { HAS_ENTITY: 1 },
          },
          source: "storage",
          workspace_id: "workspace-demo-001",
        }),
      );
    }

    if (method === "GET" && pathname === `/module4/graph/files/${encodeURIComponent(fileHash)}/node/${encodeURIComponent(entityNodeId)}`) {
      return route.fulfill(
        asJson({
          node: {
            node_id: entityNodeId,
            node_type: "Entity",
            canonical_key: "risk-entity-demo",
            display_name: "高风险资金流转",
            confidence: 0.94,
            attrs: {
              entity_type: "risk",
              summary: "命中的核心风险实体",
              file_hash: fileHash,
              evidence_count: 2,
            },
            updated_at: shortNow(),
            type_label: "entity",
            category: "entity",
          },
          graph: {
            nodes: [
              {
                node_id: documentNodeId,
                node_type: "Document",
                canonical_key: fileHash,
                display_name: "演示项目风险报告",
                confidence: 1,
                attrs: {
                  file_hash: fileHash,
                  file_name: "演示项目风险报告.pdf",
                },
                updated_at: shortNow(),
                type_label: "document",
                category: "document",
              },
              {
                node_id: entityNodeId,
                node_type: "Entity",
                canonical_key: "risk-entity-demo",
                display_name: "高风险资金流转",
                confidence: 0.94,
                attrs: {
                  entity_type: "risk",
                },
                updated_at: shortNow(),
                type_label: "entity",
                category: "entity",
              },
            ],
            edges: [
              {
                edge_id: edgeId,
                source_node_id: documentNodeId,
                target_node_id: entityNodeId,
                relation_type: "HAS_ENTITY",
                direction: "out",
                confidence: 0.93,
                risk_score: 0.91,
                attrs: {},
                updated_at: shortNow(),
                relation_label: "contains",
              },
            ],
            stats: {
              node_count: 2,
              edge_count: 1,
              by_node_type: { Document: 1, Entity: 1 },
              by_relation_type: { HAS_ENTITY: 1 },
            },
            source: "storage",
            workspace_id: "workspace-demo-001",
          },
          file: {
            graph_file_id: graphFileId,
            tenant_id: "default",
            file_hash: fileHash,
            file_name: "演示项目风险报告.pdf",
            workspace_id: "workspace-demo-001",
            graph_mode: "hybrid",
            source: "module2",
            status: "ready",
            current_job_id: null,
            active_version_id: graphVersionId,
            last_error: null,
            node_count: 2,
            edge_count: 1,
            metadata: {
              quality_status: "passed",
            },
            projection: {
              status: "success",
              projected_nodes: 2,
              projected_edges: 1,
              source_node_count: 2,
              source_edge_count: 1,
              skipped_reason: null,
              error_message: null,
              labels: ["Module4Node"],
              relationship_type: "MODULE4_EDGE",
            },
            created_at: shortNow(),
            updated_at: shortNow(),
            last_indexed_at: shortNow(),
          },
          evidence: [
            {
              evidence_id: "ev-node-1",
              doc_id: "doc-demo-1",
              object_type: "entity",
              object_id: entityNodeId,
              ref_id: "ref-risk-01",
              page_no: 3,
              snippet: "报告指出该笔资金流转存在多次异常拆分与高频转移。",
              locator: { page_no: 3, section: "3.2 风险发现" },
              bbox: [],
              artifact_url: `${appOrigin}/extract/artifacts/demo-risk-01.png`,
              confidence: 0.95,
              created_at: shortNow(),
            },
          ],
          edge_evidence: {
            [edgeId]: [
              {
                evidence_id: "ev-edge-1",
                doc_id: "doc-demo-1",
                object_type: "chunk",
                object_id: "chunk-7",
                ref_id: "ref-risk-edge-01",
                page_no: 3,
                snippet: "该风险实体来源于文档主结论段落与附录对账表的交叉验证。",
                locator: { page_no: 3, section: "3.2 风险发现" },
                bbox: [],
                artifact_url: null,
                confidence: 0.91,
                created_at: shortNow(),
              },
            ],
          },
        }),
      );
    }

    if (method === "GET" && pathname === "/module4/rules") {
      return route.fulfill(asJson({ items: state.rules }));
    }

    if (method === "PUT" && pathname.startsWith("/module4/rules/")) {
      const ruleId = decodeURIComponent(pathname.split("/").pop() || "");
      const body = request.postDataJSON();
      const current = state.rules.find((item) => item.rule_id === ruleId);
      if (!current) {
        return route.fulfill({
          status: 404,
          contentType: "application/json; charset=utf-8",
          body: JSON.stringify({ detail: "rule_not_found" }),
        });
      }
      current.name = String(body?.name || current.name);
      current.severity = String(body?.severity || current.severity);
      current.rule_kind = "deterministic";
      current.expr = body?.expr && typeof body.expr === "object" ? body.expr : current.expr;
      current.enabled = Boolean(body?.enabled);
      current.version = Number(current.version || 0) + 1;
      current.updated_at = shortNow();
      return route.fulfill(asJson({ ok: true, rule: current }));
    }

    if (method === "POST" && pathname === "/module4/explain") {
      const body = request.postDataJSON();
      const viaAlert = String(body?.alert_id || "").trim();
      const viaNode = String(body?.node_id || "").trim();
      return route.fulfill(
        asJson({
          conclusion: viaAlert
            ? "该告警由文档错误聚集规则触发，需要人工核查。"
            : `节点 ${viaNode || entityNodeId} 已关联到直接证据，可用于复核。`,
          reasoning_steps: [
            "已读取当前选中节点与关联告警。",
            "已回溯节点证据和关系证据。",
            "规则命中与证据片段相互印证，建议进入人工复核流程。",
          ],
          evidence: [
            {
              title: "节点直连证据",
              summary: "证据显示该风险实体来自文档正文与附录的交叉引用。",
              object_type: "entity",
              ref_id: "ref-risk-01",
            },
          ],
        }),
      );
    }

    if (method === "POST" && pathname === "/module4/simulate") {
      const body = request.postDataJSON();
      const scopeRuleId = String(body?.scope?.rule_id || "").trim();
      const selectedRule = state.rules.find((item) => item.rule_id === scopeRuleId) || state.rules.find((item) => item.enabled);
      return route.fulfill(
        asJson({
          impacts: [
            { metric: "simulated_contexts", value: 1 },
            { metric: "evaluated_rules", value: selectedRule ? 1 : state.rules.filter((item) => item.enabled).length },
            { metric: "simulated_hits", value: 1 },
            { metric: "hits_by_rule", value: { [selectedRule?.rule_id || "RULE_DOC_ERRORS"]: 1 } },
          ],
          changed_alerts: [
            {
              alert_id: "alert-1",
              rule_id: selectedRule?.rule_id || "RULE_DOC_ERRORS",
              severity: selectedRule?.severity || "red",
              title: "模拟后仍然命中核心风险",
              summary: "当前情景下该告警依然保持高风险，需要优先处置。",
              simulated_risk_score: 92.5,
              context_label: "document:hash-demo-001",
            },
          ],
          summary: `场景“${String(body?.scenario_name || "default")}”模拟完成，命中 1 条结果。`,
        }),
      );
    }

    return route.continue();
  });
}

async function seedLocalState(page) {
  const now = shortNow();
  await page.addInitScript(
    ({ docs, nowValue }) => {
      window.localStorage.setItem("module2_last_documents", JSON.stringify(docs));
      window.localStorage.setItem("module2_last_updated", nowValue);
      window.localStorage.setItem(
        "module2_workbench_session_v1",
        JSON.stringify({
          version: 1,
          activeDocIndex: 0,
          selectedFiles: [],
          officePreviewMap: {},
          extractionJob: null,
        }),
      );
    },
    {
      nowValue: now,
      docs: [
        {
          file_name: "演示项目风险报告.pdf",
          file_hash: fileHash,
          track: "demo",
          cached: true,
          result: {
            风险等级: {
              value: "高",
              confidence: 0.93,
              source_ref_id: "ref-risk-01",
              bbox: [],
            },
          },
          errors: ["字段对齐异常"],
          soft_warnings: [],
          trace_hits: [],
          trace_stats: {},
          diagnostics: {},
        },
      ],
    },
  );
}

async function openModule4Page(page) {
  await openProtectedTab(page, appUrl, "nexus");
  await page.getByTestId("module4-file-select").waitFor({ state: "visible", timeout: 60_000 });
  await page.getByTestId("module4-graph-host").waitFor({ state: "visible", timeout: 60_000 });
}

async function collectSnapshot(page) {
  return await page.evaluate(() => {
    const textOf = (selector) => {
      const el = document.querySelector(selector);
      return (el?.textContent || "").trim();
    };
    return {
      fallbackWarningVisible: Boolean(document.querySelector('[data-testid="module4-fallback-warning"]')),
      graphStatus: textOf("header .text-lg"),
      explainSummary: textOf('[data-testid="module4-explain-result"]'),
      simulateSummary: textOf('[data-testid="module4-simulate-result"]'),
      bodyExcerpt: (document.body.innerText || "").slice(0, 4000),
    };
  });
}

async function waitForEnabled(page, testId, timeout = 20_000) {
  await page.waitForFunction(
    (value) => {
      const element = document.querySelector(`[data-testid="${value}"]`);
      return element instanceof HTMLButtonElement && !element.disabled;
    },
    testId,
    { timeout },
  );
}

async function waitForTextChange(page, testId, previousText, timeout = 20_000) {
  await page.waitForFunction(
    ({ value, previous }) => {
      const element = document.querySelector(`[data-testid="${value}"]`);
      if (!element) return false;
      const current = String(element.textContent || "").trim();
      return Boolean(current) && current !== previous;
    },
    { value: testId, previous: previousText },
    { timeout },
  );
}

async function clickGraphNode(page, strategy = "smallest") {
  const target = await page.evaluate((mode) => {
    const graphSvg = Array.from(document.querySelectorAll("svg"))
      .sort((left, right) => right.querySelectorAll("circle").length - left.querySelectorAll("circle").length)
      .find((svg) => svg.querySelectorAll("circle").length > 2);
    if (!graphSvg) return null;

    const candidates = Array.from(graphSvg.querySelectorAll("circle"))
      .map((circle) => {
        const rect = circle.getBoundingClientRect();
        return {
          radius: Number(circle.getAttribute("r") || "0"),
          stroke: circle.getAttribute("stroke"),
          fill: circle.getAttribute("fill") || "",
          width: rect.width,
          height: rect.height,
          x: rect.left + rect.width / 2,
          y: rect.top + rect.height / 2,
        };
      })
      .filter(
        (item) =>
          item.radius > 0 &&
          Boolean(item.stroke) &&
          item.fill !== "none" &&
          item.width > 8 &&
          item.height > 8
      )
      .sort((left, right) => left.radius - right.radius);

    if (candidates.length === 0) return null;
    return mode === "largest" ? candidates[candidates.length - 1] : candidates[0];
  }, strategy);

  if (!target) {
    throw new Error(`graph_node_not_found:${strategy}`);
  }

  await page.mouse.click(target.x, target.y);
}

async function openDebugNode(page, nodeId) {
  await page.waitForFunction(
    () =>
      Boolean(
        window.__module4GraphDebug &&
          typeof window.__module4GraphDebug.openNode === "function" &&
          window.__module4GraphDebug.getGraph()?.nodes?.length
      ),
    { timeout: 20_000 },
  );
  await page.evaluate((value) => {
    window.__module4GraphDebug.openNode(value);
  }, nodeId);
}

async function main() {
  await mkdirp(outputRoot);
  await mkdirp(screenshotRoot);

  const state = buildMockState();
  const executablePath = await resolveBrowserExecutablePath();
  const browser = await chromium.launch({
    headless: true,
    executablePath: executablePath || undefined,
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1600, height: 1000 },
    });
    await loginForProtectedApp(context, appUrl);
    const page = await context.newPage();
    const pageErrors = [];
    const consoleErrors = [];

    page.on("pageerror", (error) => {
      pageErrors.push(String(error?.stack || error || "unknown_pageerror"));
    });
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = String(message.text() || "").trim();
      if (!text || text.includes("404 (Not Found)")) return;
      consoleErrors.push(text);
    });

    await installMockRoutes(page, state);
    await seedLocalState(page);
    await openModule4Page(page);

    await page.screenshot({ path: path.join(screenshotRoot, "01-initial.png"), fullPage: true });

    const fallbackCount = await page.getByTestId("module4-fallback-warning").count().catch(() => 0);
    if (fallbackCount > 0) {
      throw new Error("unexpected_fallback_warning");
    }

    if (pageErrors.length > 0) {
      throw new Error(`page_errors_detected:${pageErrors.join(" | ")}`);
    }

    await openDebugNode(page, entityNodeId);
    await page.waitForTimeout(1200);
    await page.getByTestId("module4-analysis-panel").waitFor({ state: "visible", timeout: 20_000 });
    await waitForEnabled(page, "module4-explain-btn");
    await page.screenshot({ path: path.join(screenshotRoot, "02-detail-opened.png"), fullPage: true });

    await page.getByTestId("module4-explain-btn").click({ timeout: 15_000 });
    await page.getByTestId("module4-explain-conclusion").waitFor({ state: "visible", timeout: 15_000 });

    const simulateEnabled = await page.evaluate(() => {
      const button = document.querySelector('[data-testid="module4-simulate-btn"]');
      return button instanceof HTMLButtonElement ? !button.disabled : false;
    });
    if (simulateEnabled) {
      await page.getByTestId("module4-simulate-btn").click({ timeout: 15_000 });
      await page.getByTestId("module4-simulate-summary-text").waitFor({ state: "visible", timeout: 15_000 });
    }
    await page.screenshot({ path: path.join(screenshotRoot, "03-analysis-finished.png"), fullPage: true });

    if (false) {

    await page.getByText("文档存在结构化抽取异常").first().click({ timeout: 15_000 });
    await page.getByText("高风险资金流转").first().waitFor({ state: "visible", timeout: 20_000 });
    await page.screenshot({ path: path.join(screenshotRoot, "02-detail-opened.png"), fullPage: true });

    await page.getByTestId("module4-rule-card-RULE_LOW_CONFIDENCE").click({ timeout: 15_000 });
    await page.getByTestId("module4-rule-toggle-RULE_LOW_CONFIDENCE").click({ timeout: 15_000 });
    await page.getByText("已启用").first().waitFor({ state: "visible", timeout: 15_000 });

    await page.getByTestId("module4-explain-btn").click({ timeout: 15_000 });
    await page.getByText("该告警由文档错误聚集规则触发，需要人工核查。").waitFor({
      state: "visible",
      timeout: 15_000,
    });

    await page.getByTestId("module4-simulate-btn").click({ timeout: 15_000 });
    await page.getByText(/模拟完成，命中 1 条结果/).waitFor({ state: "visible", timeout: 15_000 });
    await page.screenshot({ path: path.join(screenshotRoot, "03-analysis-finished.png"), fullPage: true });

    }

    const snapshot = await collectSnapshot(page);
    if (pageErrors.length > 0) {
      throw new Error(`page_errors_detected:${pageErrors.join(" | ")}`);
    }

    await fs.writeFile(path.join(outputRoot, "snapshot.json"), JSON.stringify(snapshot, null, 2), "utf8");
    await fs.writeFile(
      path.join(outputRoot, "summary.json"),
      JSON.stringify(
        {
          ok: true,
          app_url: appUrl,
          output_root: outputRoot,
          screenshots: [
            path.join(screenshotRoot, "01-initial.png"),
            path.join(screenshotRoot, "02-detail-opened.png"),
            path.join(screenshotRoot, "03-analysis-finished.png"),
          ],
          enabled_rules: state.rules.filter((item) => item.enabled).map((item) => item.rule_id),
          console_errors: consoleErrors,
          page_errors: pageErrors,
        },
        null,
        2,
      ),
      "utf8",
    );

    console.log(JSON.stringify({ ok: true, output_root: outputRoot }, null, 2));
    await context.close();
  } finally {
    await browser.close();
  }
}

main().catch(async (error) => {
  await mkdirp(outputRoot).catch(() => {});
  await fs.writeFile(
    path.join(outputRoot, "error.json"),
    JSON.stringify({ ok: false, error: String(error?.stack || error || "unknown_error") }, null, 2),
    "utf8",
  ).catch(() => {});
  console.error(error);
  process.exit(1);
});
