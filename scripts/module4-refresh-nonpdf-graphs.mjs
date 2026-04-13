#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

const datasetsRoot = process.env.MODULE4_REFRESH_DATASETS_ROOT || path.join(projectRoot, "datasets");
const module2Base = String(process.env.MODULE2_API_BASE || "http://127.0.0.1:8010").trim().replace(/\/+$/, "");
const module4Base = String(process.env.MODULE4_API_BASE || "http://127.0.0.1:8100").trim().replace(/\/+$/, "");
const tenantId = String(process.env.MODULE4_REFRESH_TENANT_ID || "default").trim() || "default";
const batchSize = Math.max(1, Math.min(Number(process.env.MODULE4_REFRESH_BATCH_SIZE || 5), 5));
const pollIntervalMs = Math.max(1_500, Number(process.env.MODULE4_REFRESH_POLL_INTERVAL_MS || 3_000));
const pollTimeoutMs = Math.max(60_000, Number(process.env.MODULE4_REFRESH_POLL_TIMEOUT_MS || 900_000));
const requestTimeoutMs = Math.max(60_000, Number(process.env.MODULE4_REFRESH_REQUEST_TIMEOUT_MS || 900_000));
const outputRoot =
  process.env.MODULE4_REFRESH_OUTPUT_DIR ||
  path.join(
    projectRoot,
    ".runlogs",
    "module4-refresh-nonpdf-graphs",
    new Date().toISOString().replace(/[:.]/g, "-"),
  );

const supportedExtensions = new Set([".docx", ".xlsx", ".xls", ".csv", ".txt", ".md"]);
const preferredOrder = [".docx", ".xlsx", ".txt", ".md", ".xls", ".csv"];

function parseTargetArgs(argv) {
  const rawTargets = [];
  for (let index = 0; index < argv.length; index += 1) {
    const value = String(argv[index] || "").trim();
    if (!value) continue;
    if (value === "--targets" || value === "-t") {
      rawTargets.push(String(argv[index + 1] || ""));
      index += 1;
      continue;
    }
    if (value.startsWith("--targets=")) {
      rawTargets.push(value.slice("--targets=".length));
      continue;
    }
  }
  return rawTargets
    .flatMap((item) => String(item || "").split(","))
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeName(value) {
  return String(value || "")
    .normalize("NFKC")
    .replace(/\s+/g, "")
    .toLowerCase();
}

function safeSlug(value) {
  return String(value || "unknown")
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\u0000-\u001F]+/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 100);
}

function compareByPreferredExtension(left, right) {
  const leftExt = path.extname(left).toLowerCase();
  const rightExt = path.extname(right).toLowerCase();
  const leftIndex = preferredOrder.indexOf(leftExt);
  const rightIndex = preferredOrder.indexOf(rightExt);
  if (leftIndex !== rightIndex) {
    return (leftIndex === -1 ? 999 : leftIndex) - (rightIndex === -1 ? 999 : rightIndex);
  }
  return left.localeCompare(right, "zh-CN");
}

function chunk(values, size) {
  const items = Array.isArray(values) ? values : [];
  const chunks = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

function splitBatchGroup(group) {
  const files = Array.isArray(group?.files) ? group.files : [];
  const midpoint = Math.ceil(files.length / 2);
  return [
    {
      label: `${group.label}a`,
      files: files.slice(0, midpoint),
    },
    {
      label: `${group.label}b`,
      files: files.slice(midpoint),
    },
  ].filter((item) => item.files.length > 0);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function mkdirp(target) {
  await fs.mkdir(target, { recursive: true });
}

async function walkFiles(rootDir) {
  const output = [];
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    const entries = await fs.readdir(current, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      output.push(fullPath);
    }
  }
  return output;
}

async function discoverDatasetFiles(targetNames) {
  const allFiles = await walkFiles(datasetsRoot);
  const candidates = allFiles
    .filter((item) => {
      const ext = path.extname(item).toLowerCase();
      return supportedExtensions.has(ext);
    })
    .sort(compareByPreferredExtension);

  if (!targetNames.length) {
    return candidates;
  }

  const normalizedTargets = new Set(targetNames.map((item) => normalizeName(item)));
  return candidates.filter((item) => {
    const baseName = path.basename(item);
    const relativeName = path.relative(datasetsRoot, item);
    return normalizedTargets.has(normalizeName(baseName)) || normalizedTargets.has(normalizeName(relativeName));
  });
}

async function readFileWithHash(filePath) {
  const bytes = await fs.readFile(filePath);
  return {
    filePath,
    fileName: path.basename(filePath),
    extension: path.extname(filePath).toLowerCase(),
    bytes,
    fileHash: crypto.createHash("sha256").update(bytes).digest("hex"),
  };
}

function buildAbortSignal(timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error(`request_timeout_${timeoutMs}`)), timeoutMs);
  return {
    signal: controller.signal,
    cleanup() {
      clearTimeout(timer);
    },
  };
}

async function fetchJson(url, init = {}, timeoutMs = requestTimeoutMs) {
  const guard = buildAbortSignal(timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: guard.signal });
    const text = await response.text().catch(() => "");
    let payload = null;
    try {
      payload = text ? JSON.parse(text.replace(/^\uFEFF/, "")) : null;
    } catch {
      payload = null;
    }
    if (!response.ok) {
      throw new Error(`request_failed:${response.status}:${url}:${String(text || "").slice(0, 800)}`);
    }
    return payload;
  } finally {
    guard.cleanup();
  }
}

async function fetchGraphFileDetail(fileHash) {
  return await fetchJson(`${module4Base}/module4/graph/files/${encodeURIComponent(fileHash)}`);
}

async function fetchGraphView(fileHash) {
  return await fetchJson(
    `${module4Base}/module4/graph/files/${encodeURIComponent(fileHash)}/view?limit_nodes=1600&limit_edges=3200`,
  );
}

async function extractBatchFromModule2(fileEntries) {
  const form = new FormData();
  for (const entry of fileEntries) {
    form.append("files", new Blob([entry.bytes]), entry.fileName);
  }
  form.append("schema", "{}");
  form.append("tenant_id", tenantId);
  return await fetchJson(`${module2Base}/extract/batch`, {
    method: "POST",
    body: form,
  });
}

async function waitForGraphReady({ fileHash, beforeLastIndexedAt, startedAt }) {
  const started = Date.now();
  let lastSnapshot = null;

  while (Date.now() - started < pollTimeoutMs) {
    try {
      const detail = await fetchGraphFileDetail(fileHash);
      const item = detail?.item && typeof detail.item === "object" ? detail.item : null;
      if (item) {
        lastSnapshot = item;
        const lastIndexedAt = String(item.last_indexed_at || "").trim();
        const isReady = String(item.status || "").trim() === "ready";
        const changed =
          !beforeLastIndexedAt ||
          (lastIndexedAt && beforeLastIndexedAt && new Date(lastIndexedAt).getTime() > new Date(beforeLastIndexedAt).getTime()) ||
          (lastIndexedAt && startedAt && new Date(lastIndexedAt).getTime() >= new Date(startedAt).getTime() - 1000);
        if (isReady && Number(item.node_count || 0) > 0 && changed) {
          return item;
        }
      }
    } catch (error) {
      const message = String(error?.message || error || "");
      if (!message.includes("404")) {
        lastSnapshot = { error: message };
      }
    }
    await sleep(pollIntervalMs);
  }

  throw new Error(
    `graph_ready_timeout:${fileHash}:${JSON.stringify(lastSnapshot || {}, null, 2).slice(0, 1200)}`,
  );
}

function summarizeGraph(graph, detail, sourceFile) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];
  const typeCounts = nodes.reduce((acc, item) => {
    const key = String(item?.node_type || "Unknown").trim() || "Unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const relationCounts = edges.reduce((acc, item) => {
    const key = String(item?.relation_type || "unknown").trim() || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const documentNode = nodes.find((item) => String(item?.node_type || "") === "Document") || null;
  const artifactNodes = nodes.filter((item) =>
    ["Table", "Figure", "Image"].includes(String(item?.node_type || "").trim()),
  );

  const hasBusinessContext = Boolean(typeCounts.BusinessContext);
  const hasTopic = Boolean(typeCounts.Topic);
  const hasObservation = Boolean(typeCounts.Observation);
  const hasClaim = Boolean(typeCounts.Claim);
  const hasBusinessAlert = Boolean(typeCounts.BusinessAlert);
  const hasField = Boolean(typeCounts.Field);
  const hasArtifact = artifactNodes.length > 0;

  let score = 0;
  if (documentNode) score += 1;
  if (hasBusinessContext) score += 2;
  if (hasTopic) score += 2;
  if (hasObservation) score += 2;
  if (hasClaim) score += 1;
  if (hasBusinessAlert) score += 1;
  if (hasField) score += 1;
  if (hasArtifact) score += 1;
  if (nodes.length >= 20) score += 1;
  if (edges.length >= 24) score += 1;

  let quality = "poor";
  if (score >= 10) {
    quality = "excellent";
  } else if (score >= 7) {
    quality = "usable";
  } else if (score >= 5) {
    quality = "weak";
  }

  return {
    file_name: sourceFile.fileName,
    file_path: sourceFile.filePath,
    extension: sourceFile.extension,
    file_hash: sourceFile.fileHash,
    graph_file_status: String(detail?.status || "").trim(),
    graph_file_last_indexed_at: String(detail?.last_indexed_at || "").trim(),
    node_count: nodes.length,
    edge_count: edges.length,
    type_counts: typeCounts,
    relation_counts: relationCounts,
    quality,
    score,
    has_document: Boolean(documentNode),
    has_business_context: hasBusinessContext,
    has_topic: hasTopic,
    has_observation: hasObservation,
    has_claim: hasClaim,
    has_business_alert: hasBusinessAlert,
    has_field: hasField,
    has_artifact: hasArtifact,
    sample_nodes: nodes.slice(0, 12).map((item) => ({
      node_type: String(item?.node_type || "").trim(),
      display_name: String(item?.display_name || "").trim(),
    })),
    sample_edges: edges.slice(0, 12).map((item) => ({
      relation_type: String(item?.relation_type || "").trim(),
      source_node_id: String(item?.source_node_id || "").trim(),
      target_node_id: String(item?.target_node_id || "").trim(),
    })),
  };
}

function buildAssessmentMarkdown(report) {
  const lines = [
    "# Module 4 Non-PDF Refresh Assessment",
    "",
    `- Generated at: ${report.generated_at}`,
    `- Datasets root: ${report.datasets_root}`,
    `- Module2 base: ${report.module2_base}`,
    `- Module4 base: ${report.module4_base}`,
    `- Tenant: ${report.tenant_id}`,
    `- Target file count: ${report.target_file_count}`,
    `- Refreshed file count: ${report.results.length}`,
    "",
    "## Quality Summary",
    "",
  ];

  for (const [extension, summary] of Object.entries(report.quality_summary.by_extension)) {
    lines.push(
      `- ${extension}: excellent=${summary.excellent}, usable=${summary.usable}, weak=${summary.weak}, poor=${summary.poor}`,
    );
  }

  lines.push("");
  lines.push("## File Results");
  lines.push("");

  for (const item of report.results) {
    lines.push(`### ${item.file_name}`);
    lines.push("");
    if (item.error) {
      lines.push(`- Error: ${item.error}`);
      lines.push(`- File path: ${item.file_path}`);
      lines.push("");
      continue;
    }
    lines.push(`- File path: ${item.file_path}`);
    lines.push(`- Hash: ${item.file_hash}`);
    lines.push(`- Quality: ${item.quality} (score=${item.score})`);
    lines.push(`- Nodes / edges: ${item.node_count} / ${item.edge_count}`);
    lines.push(`- Types: ${JSON.stringify(item.type_counts)}`);
    lines.push(`- Relations: ${JSON.stringify(item.relation_counts)}`);
    lines.push(
      `- Semantic core: context=${item.has_business_context}, topic=${item.has_topic}, observation=${item.has_observation}, claim=${item.has_claim}, alert=${item.has_business_alert}`,
    );
    lines.push(`- Artifact support: field=${item.has_field}, artifact=${item.has_artifact}`);
    lines.push("");
  }

  return lines.join("\n");
}

function summarizeByExtension(results) {
  const output = {};
  for (const item of results) {
    const extension = String(item.extension || "unknown").toLowerCase() || "unknown";
    const bucket = output[extension] || { excellent: 0, usable: 0, weak: 0, poor: 0 };
    if (item.error) {
      bucket.poor += 1;
    } else {
      bucket[item.quality] = (bucket[item.quality] || 0) + 1;
    }
    output[extension] = bucket;
  }
  return output;
}

async function writeJson(filePath, data) {
  await fs.writeFile(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

async function main() {
  const targetArgs = parseTargetArgs(process.argv.slice(2));
  await mkdirp(outputRoot);
  const targetPaths = await discoverDatasetFiles(targetArgs);
  if (!targetPaths.length) {
    throw new Error(
      targetArgs.length
        ? `no_matching_nonpdf_targets:${targetArgs.join(",")}`
        : `no_nonpdf_files_found_under:${datasetsRoot}`,
    );
  }

  const sourceFiles = [];
  for (const targetPath of targetPaths) {
    sourceFiles.push(await readFileWithHash(targetPath));
  }

  const report = {
    ok: true,
    generated_at: new Date().toISOString(),
    datasets_root: datasetsRoot,
    module2_base: module2Base,
    module4_base: module4Base,
    tenant_id: tenantId,
    output_root: outputRoot,
    target_file_count: sourceFiles.length,
    target_files: sourceFiles.map((item) => ({
      file_name: item.fileName,
      file_path: item.filePath,
      file_hash: item.fileHash,
      extension: item.extension,
    })),
    batches: [],
    results: [],
    quality_summary: {
      by_extension: {},
    },
  };

  const beforeMap = new Map();
  for (const entry of sourceFiles) {
    try {
      const detail = await fetchGraphFileDetail(entry.fileHash);
      const item = detail?.item && typeof detail.item === "object" ? detail.item : null;
      beforeMap.set(entry.fileHash, item || null);
    } catch {
      beforeMap.set(entry.fileHash, null);
    }
  }

  const sourceByName = new Map(sourceFiles.map((item) => [item.fileName, item]));
  const pendingGroups = chunk(sourceFiles, batchSize).map((files, index) => ({
    label: `batch-${String(index + 1).padStart(2, "0")}`,
    files,
  }));
  while (pendingGroups.length > 0) {
    const currentGroup = pendingGroups.shift();
    const batchFiles = Array.isArray(currentGroup?.files) ? currentGroup.files : [];
    const batchLabel = String(currentGroup?.label || `batch-${String(report.batches.length + 1).padStart(2, "0")}`);
    const batchDir = path.join(outputRoot, batchLabel);
    await mkdirp(batchDir);

    const startedAt = new Date().toISOString();
    let extractResponse = null;
    try {
      extractResponse = await extractBatchFromModule2(batchFiles);
    } catch (error) {
      const message = String(error?.stack || error || "extract_batch_failed");
      await writeJson(path.join(batchDir, "extract-error.json"), {
        batch: batchLabel,
        file_count: batchFiles.length,
        files: batchFiles.map((item) => item.fileName),
        error: message,
      });

      if (batchFiles.length > 1) {
        const splitGroups = splitBatchGroup({ label: batchLabel, files: batchFiles });
        pendingGroups.unshift(...splitGroups.reverse());
        report.batches.push({
          batch: batchLabel,
          started_at: startedAt,
          finished_at: new Date().toISOString(),
          files: batchFiles.map((item) => item.fileName),
          split_retry: true,
          error: message,
        });
        continue;
      }

      const singleFile = batchFiles[0];
      report.batches.push({
        batch: batchLabel,
        started_at: startedAt,
        finished_at: new Date().toISOString(),
        files: batchFiles.map((item) => item.fileName),
        split_retry: false,
        error: message,
      });
      report.results.push({
        file_name: singleFile?.fileName || "(unknown)",
        file_hash: singleFile?.fileHash || "",
        file_path: singleFile?.filePath || "",
        extension: singleFile?.extension || "",
        error: message,
      });
      continue;
    }
    await writeJson(path.join(batchDir, "extract-response.json"), extractResponse);

    const docs = Array.isArray(extractResponse?.documents) ? extractResponse.documents : [];
    const batchRecord = {
      batch: batchLabel,
      started_at: startedAt,
      finished_at: "",
      files: batchFiles.map((item) => item.fileName),
      documents: docs.map((item) => ({
        file_name: String(item?.file_name || "").trim(),
        file_hash: String(item?.file_hash || "").trim(),
        cached: Boolean(item?.cached),
        track: String(item?.track || "").trim(),
        error_count: Array.isArray(item?.errors) ? item.errors.length : 0,
        warning_count: Array.isArray(item?.soft_warnings) ? item.soft_warnings.length : 0,
      })),
    };

    for (const doc of docs) {
      const fileName = String(doc?.file_name || "").trim();
      const fileHash = String(doc?.file_hash || "").trim();
      const sourceFile = sourceByName.get(fileName);
      if (!sourceFile || !fileHash) {
        report.results.push({
          file_name: fileName || "(unknown)",
          file_hash: fileHash,
          file_path: sourceFile?.filePath || "",
          extension: sourceFile?.extension || path.extname(fileName).toLowerCase(),
          error: "extract_response_missing_source_mapping",
        });
        continue;
      }

      const beforeDetail = beforeMap.get(fileHash);
      const readyDetail = await waitForGraphReady({
        fileHash,
        beforeLastIndexedAt: String(beforeDetail?.last_indexed_at || "").trim(),
        startedAt,
      });
      const graph = await fetchGraphView(fileHash);
      const summary = summarizeGraph(graph, readyDetail, sourceFile);

      await writeJson(path.join(batchDir, `${safeSlug(fileName)}.graph.json`), graph);
      await writeJson(path.join(batchDir, `${safeSlug(fileName)}.detail.json`), readyDetail);
      report.results.push(summary);
    }

    batchRecord.finished_at = new Date().toISOString();
    report.batches.push(batchRecord);
    await writeJson(path.join(batchDir, "batch-summary.json"), batchRecord);
  }

  report.quality_summary.by_extension = summarizeByExtension(report.results);

  await writeJson(path.join(outputRoot, "report.json"), report);
  await fs.writeFile(path.join(outputRoot, "assessment.md"), `${buildAssessmentMarkdown(report)}\n`, "utf8");

  console.log(
    JSON.stringify(
      {
        ok: true,
        output_root: outputRoot,
        report_json: path.join(outputRoot, "report.json"),
        assessment_md: path.join(outputRoot, "assessment.md"),
      },
      null,
      2,
    ),
  );
}

main().catch(async (error) => {
  await mkdirp(outputRoot).catch(() => {});
  await writeJson(path.join(outputRoot, "error.json"), {
    ok: false,
    error: String(error?.stack || error || "unknown_error"),
  }).catch(() => {});
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
