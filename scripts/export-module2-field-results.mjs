#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

const datasetRoot = path.resolve(
  projectRoot,
  String(process.env.MODULE2_DATASET_ROOT || "datasets").trim(),
);
const apiBase = String(process.env.MODULE2_API_BASE || "http://127.0.0.1:8000")
  .trim()
  .replace(/\/+$/, "");
const pollIntervalMs = Math.max(
  1000,
  Number.parseInt(process.env.MODULE2_EXPORT_POLL_INTERVAL_MS || "2000", 10) || 2000,
);
const jobTimeoutMs = Math.max(
  300_000,
  Number.parseInt(process.env.MODULE2_EXPORT_JOB_TIMEOUT_MS || "2700000", 10) || 2_700_000,
);
const shouldClearCache = ["1", "true", "yes"].includes(
  String(process.env.MODULE2_EXPORT_CLEAR_CACHE || "").trim().toLowerCase(),
);

const allowedExt = new Set([".doc", ".docx", ".xlsx", ".xls", ".md", ".markdown", ".txt"]);

const reportRoot = path.join(
  projectRoot,
  "runtime-data",
  "module2",
  "reports",
  "nonpdf-field-results",
  timestampTag(),
);

function timestampTag() {
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${hh}${mi}${ss}`;
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function safeJson(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function escapeMarkdownCell(value) {
  return String(value ?? "")
    .replace(/\|/g, "\\|")
    .replace(/\r?\n/g, "<br/>")
    .trim();
}

function shortHash(value) {
  return crypto.createHash("sha1").update(String(value || "")).digest("hex").slice(0, 8);
}

function buildAsciiSlug(filePath, index) {
  const parsed = path.parse(filePath);
  const rawBase = parsed.name.normalize("NFKC").replace(/[^\p{L}\p{N}._-]+/gu, "-");
  const compactBase = rawBase.replace(/-+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  const readableBase = compactBase || "file";
  return `${String(index + 1).padStart(2, "0")}-${readableBase}-${shortHash(filePath)}`;
}

function toRelativeProjectPath(targetPath) {
  return path.relative(projectRoot, targetPath).replace(/\\/g, "/");
}

function isNonPdfDatasetFile(filePath) {
  const normalized = String(filePath || "").replace(/\\/g, "/");
  if (/\/pdf\//i.test(normalized)) return false;
  const ext = path.extname(filePath).toLowerCase();
  return allowedExt.has(ext);
}

function guessMimeType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case ".doc":
      return "application/msword";
    case ".docx":
      return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    case ".xls":
      return "application/vnd.ms-excel";
    case ".xlsx":
      return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    case ".md":
    case ".markdown":
      return "text/markdown";
    case ".txt":
      return "text/plain";
    default:
      return "application/octet-stream";
  }
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function walkFiles(dirPath) {
  const entries = await fs.readdir(dirPath, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await walkFiles(fullPath)));
      continue;
    }
    if (entry.isFile()) {
      out.push(fullPath);
    }
  }
  return out;
}

async function fetchText(url, init = {}) {
  const response = await fetch(url, init);
  const text = await response.text();
  return { response, text };
}

async function clearBackendCacheIfNeeded() {
  if (!shouldClearCache) return null;
  const { response, text } = await fetchText(`${apiBase}/extract/cache/clear?scope=all`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`clear_cache_failed:${response.status}:${text.slice(0, 400)}`);
  }
  return tryParseJson(text);
}

function tryParseJson(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function createExtractionJob(filePath) {
  const bytes = await fs.readFile(filePath);
  const fileName = path.basename(filePath);
  const formData = new FormData();
  formData.append("files", new Blob([bytes], { type: guessMimeType(filePath) }), fileName);
  formData.append("schema", "{}");

  const { response, text } = await fetchText(`${apiBase}/extract/jobs/create`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`create_job_failed:${fileName}:${response.status}:${text.slice(0, 400)}`);
  }
  const payload = tryParseJson(text);
  const jobId = String(payload?.job_id || "").trim();
  if (!jobId) {
    throw new Error(`create_job_missing_job_id:${fileName}`);
  }
  return payload;
}

async function waitForTerminalJob(jobId) {
  const startedAt = Date.now();
  let lastPayload = null;
  let lastStatus = 0;

  while (Date.now() - startedAt < jobTimeoutMs) {
    const { response, text } = await fetchText(
      `${apiBase}/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`,
      { method: "GET" },
    );
    lastStatus = response.status;
    lastPayload = tryParseJson(text);

    if (!response.ok) {
      throw new Error(`job_status_failed:${jobId}:${response.status}:${text.slice(0, 400)}`);
    }
    if (lastPayload?.terminal) {
      return {
        status: lastStatus,
        payload: lastPayload,
        elapsedMs: Date.now() - startedAt,
      };
    }

    await sleep(pollIntervalMs);
  }

  throw new Error(
    `job_terminal_timeout:${jobId}:status=${lastStatus}:elapsed_ms=${Date.now() - startedAt}`,
  );
}

function toFieldRows(documentPayload) {
  const result = documentPayload && typeof documentPayload.result === "object" ? documentPayload.result : {};
  return Object.entries(result).map(([fieldName, entity]) => {
    const obj = entity && typeof entity === "object" ? entity : {};
    return {
      field_name: fieldName,
      value: obj.value ?? null,
      confidence: Number(obj.confidence || 0) || 0,
      source_ref_id: obj.source_ref_id ?? null,
      bbox: Array.isArray(obj.bbox) ? obj.bbox : [],
    };
  });
}

function normalizeArtifactLinks(diagnostics) {
  const out = {};
  for (const [key, value] of Object.entries(diagnostics || {})) {
    if (!/_artifact_path$|_artifact_url$|_preview_path$|_preview_url$/.test(key)) continue;
    if (value == null || value === "") continue;
    out[key] = value;
  }
  return out;
}

function summarizeDocument(sourceFile, jobId, terminalPayload) {
  const documentPayload = Array.isArray(terminalPayload?.documents) ? terminalPayload.documents[0] : null;
  const fieldRows = documentPayload ? toFieldRows(documentPayload) : [];
  const filledFieldRows = fieldRows.filter((row) => {
    const value = row.value;
    if (value == null) return false;
    if (typeof value === "string") return value.trim().length > 0;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "object") return Object.keys(value).length > 0;
    return true;
  });
  const diagnostics = documentPayload?.diagnostics && typeof documentPayload.diagnostics === "object"
    ? documentPayload.diagnostics
    : {};
  const traceStats = documentPayload?.trace_stats && typeof documentPayload.trace_stats === "object"
    ? documentPayload.trace_stats
    : {};

  return {
    source_file: toRelativeProjectPath(sourceFile),
    file_name: path.basename(sourceFile),
    extension: path.extname(sourceFile).toLowerCase(),
    job_id: jobId,
    terminal_status: String(terminalPayload?.status || "").trim() || "unknown",
    document_found: Boolean(documentPayload),
    cached: Boolean(documentPayload?.cached),
    field_count: fieldRows.length,
    filled_field_count: filledFieldRows.length,
    trace_hit_count: Number(traceStats.trace_hit_count || 0) || 0,
    trace_object_counts: traceStats.trace_object_counts || {},
    parse_ms: Number(diagnostics.parse_ms || 0) || 0,
    extract_ms: Number(diagnostics.extract_ms || 0) || 0,
    total_ms: Number(diagnostics.total_ms || 0) || 0,
    errors: Array.isArray(documentPayload?.errors) ? documentPayload.errors : [],
    soft_warnings: Array.isArray(documentPayload?.soft_warnings) ? documentPayload.soft_warnings : [],
    diagnostics: {
      schema_mode: diagnostics.schema_mode || "",
      schema_source: diagnostics.schema_source || "",
      quality_status: diagnostics.quality_status || "",
      business_extraction_status: diagnostics.business_extraction_status || "",
      field_naming_version: diagnostics.field_naming_version || "",
      nonpdf_profile: diagnostics.nonpdf_profile || "",
      office_pdf_converter: diagnostics.office_pdf_converter || "",
      office_pdf_elapsed_ms: Number(diagnostics.office_pdf_elapsed_ms || 0) || 0,
      trace_pages: Array.isArray(diagnostics.trace_pages) ? diagnostics.trace_pages : [],
    },
    artifact_links: normalizeArtifactLinks(diagnostics),
  };
}

function buildFieldsMarkdown({ sourceFile, jobId, terminalPayload, documentPayload, fieldRows }) {
  const diagnostics = documentPayload?.diagnostics && typeof documentPayload.diagnostics === "object"
    ? documentPayload.diagnostics
    : {};
  const traceStats = documentPayload?.trace_stats && typeof documentPayload.trace_stats === "object"
    ? documentPayload.trace_stats
    : {};
  const artifactLinks = normalizeArtifactLinks(diagnostics);
  const lines = [];
  lines.push(`# ${path.basename(sourceFile)}`);
  lines.push("");
  lines.push("## 基本信息");
  lines.push("");
  lines.push(`- 源文件: \`${toRelativeProjectPath(sourceFile)}\``);
  lines.push(`- Job ID: \`${jobId}\``);
  lines.push(`- 文档哈希: \`${String(documentPayload?.file_hash || "").trim()}\``);
  lines.push(`- Track: \`${String(documentPayload?.track || "").trim()}\``);
  lines.push(`- 缓存命中: \`${Boolean(documentPayload?.cached)}\``);
  lines.push(`- 字段总数: \`${fieldRows.length}\``);
  lines.push(
    `- Trace 命中: \`${Number(traceStats.trace_hit_count || 0) || 0}\``,
  );
  lines.push("");
  lines.push("## 诊断摘要");
  lines.push("");
  lines.push(`- parse_ms: \`${Number(diagnostics.parse_ms || 0) || 0}\``);
  lines.push(`- extract_ms: \`${Number(diagnostics.extract_ms || 0) || 0}\``);
  lines.push(`- total_ms: \`${Number(diagnostics.total_ms || 0) || 0}\``);
  lines.push(`- schema_mode: \`${String(diagnostics.schema_mode || "").trim()}\``);
  lines.push(`- schema_source: \`${String(diagnostics.schema_source || "").trim()}\``);
  lines.push(`- quality_status: \`${String(diagnostics.quality_status || "").trim()}\``);
  lines.push(`- business_extraction_status: \`${String(diagnostics.business_extraction_status || "").trim()}\``);
  if (Object.keys(artifactLinks).length > 0) {
    lines.push("");
    lines.push("## 相关产物路径");
    lines.push("");
    for (const [key, value] of Object.entries(artifactLinks)) {
      lines.push(`- ${key}: \`${String(value || "").trim()}\``);
    }
  }
  if (Array.isArray(documentPayload?.errors) && documentPayload.errors.length > 0) {
    lines.push("");
    lines.push("## Errors");
    lines.push("");
    for (const error of documentPayload.errors) {
      lines.push(`- ${escapeMarkdownCell(error)}`);
    }
  }
  if (Array.isArray(documentPayload?.soft_warnings) && documentPayload.soft_warnings.length > 0) {
    lines.push("");
    lines.push("## Soft Warnings");
    lines.push("");
    for (const warning of documentPayload.soft_warnings) {
      lines.push(`- ${escapeMarkdownCell(warning)}`);
    }
  }
  lines.push("");
  lines.push("## 字段结果");
  lines.push("");
  lines.push("| 字段 | 值 | 置信度 | source_ref_id | bbox |");
  lines.push("| --- | --- | ---: | --- | --- |");
  for (const row of fieldRows) {
    const valueText =
      row.value == null ? "" : typeof row.value === "string" ? row.value : JSON.stringify(row.value, null, 0);
    lines.push(
      `| ${escapeMarkdownCell(row.field_name)} | ${escapeMarkdownCell(valueText)} | ${row.confidence.toFixed(3)} | ${escapeMarkdownCell(row.source_ref_id || "")} | ${escapeMarkdownCell(JSON.stringify(row.bbox || []))} |`,
    );
  }
  if (fieldRows.length === 0) {
    lines.push("| _(无字段)_ |  |  |  |  |");
  }
  lines.push("");
  lines.push("## Trace 统计");
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(traceStats || {}, null, 2));
  lines.push("```");
  lines.push("");
  lines.push("## Job 终态");
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(terminalPayload || {}, null, 2));
  lines.push("```");
  lines.push("");
  return `${lines.join("\n")}\n`;
}

function buildRunIndexMarkdown(runSummary) {
  const lines = [];
  lines.push("# Module2 Non-PDF 字段抽取导出");
  lines.push("");
  lines.push(`- 生成时间: \`${runSummary.generated_at}\``);
  lines.push(`- API: \`${runSummary.api_base}\``);
  lines.push(`- 数据集目录: \`${runSummary.dataset_root}\``);
  lines.push(`- 文件数量: \`${runSummary.file_count}\``);
  lines.push("");
  lines.push("| 文件 | 类型 | 字段数 | 已填字段 | Trace 命中 | total_ms | 导出目录 |");
  lines.push("| --- | --- | ---: | ---: | ---: | ---: | --- |");
  for (const item of runSummary.files) {
    lines.push(
      `| ${escapeMarkdownCell(item.file_name)} | ${escapeMarkdownCell(item.extension)} | ${item.field_count} | ${item.filled_field_count} | ${item.trace_hit_count} | ${item.total_ms} | ${escapeMarkdownCell(item.output_dir)} |`,
    );
  }
  lines.push("");
  return `${lines.join("\n")}\n`;
}

async function main() {
  await ensureDir(reportRoot);

  const cacheClearPayload = await clearBackendCacheIfNeeded();
  const datasetFiles = (await walkFiles(datasetRoot))
    .filter(isNonPdfDatasetFile)
    .sort((left, right) => left.localeCompare(right, "zh-CN"));

  if (datasetFiles.length === 0) {
    throw new Error(`no_nonpdf_dataset_files_found:${datasetRoot}`);
  }

  const runFiles = [];

  for (let index = 0; index < datasetFiles.length; index += 1) {
    const sourceFile = datasetFiles[index];
    const outputDirName = buildAsciiSlug(sourceFile, index);
    const outputDir = path.join(reportRoot, outputDirName);
    await ensureDir(outputDir);

    const createPayload = await createExtractionJob(sourceFile);
    const jobId = String(createPayload.job_id || "").trim();
    const terminalState = await waitForTerminalJob(jobId);
    const terminalPayload = terminalState.payload || {};
    const documentPayload = Array.isArray(terminalPayload.documents) ? terminalPayload.documents[0] || null : null;
    const fieldRows = documentPayload ? toFieldRows(documentPayload) : [];
    const summary = summarizeDocument(sourceFile, jobId, terminalPayload);

    await fs.writeFile(path.join(outputDir, "job-create.json"), safeJson(createPayload), "utf8");
    await fs.writeFile(path.join(outputDir, "job-terminal.json"), safeJson(terminalPayload), "utf8");
    await fs.writeFile(path.join(outputDir, "summary.json"), safeJson(summary), "utf8");
    await fs.writeFile(path.join(outputDir, "fields.json"), safeJson(fieldRows), "utf8");

    if (documentPayload) {
      await fs.writeFile(path.join(outputDir, "document.json"), safeJson(documentPayload), "utf8");
      await fs.writeFile(
        path.join(outputDir, "trace-hits.json"),
        safeJson(Array.isArray(documentPayload.trace_hits) ? documentPayload.trace_hits : []),
        "utf8",
      );
      await fs.writeFile(
        path.join(outputDir, "diagnostics.json"),
        safeJson(documentPayload.diagnostics && typeof documentPayload.diagnostics === "object" ? documentPayload.diagnostics : {}),
        "utf8",
      );
      await fs.writeFile(
        path.join(outputDir, "fields.md"),
        buildFieldsMarkdown({
          sourceFile,
          jobId,
          terminalPayload,
          documentPayload,
          fieldRows,
        }),
        "utf8",
      );
    }

    runFiles.push({
      ...summary,
      output_dir: toRelativeProjectPath(outputDir),
      poll_elapsed_ms: terminalState.elapsedMs,
    });

    console.log(
      `[export ${index + 1}/${datasetFiles.length}] ${path.basename(sourceFile)} -> ${toRelativeProjectPath(outputDir)}`,
    );
  }

  const runSummary = {
    generated_at: new Date().toISOString(),
    api_base: apiBase,
    dataset_root: toRelativeProjectPath(datasetRoot),
    clear_cache_requested: shouldClearCache,
    clear_cache_result: cacheClearPayload,
    file_count: runFiles.length,
    files: runFiles,
  };

  await fs.writeFile(path.join(reportRoot, "index.json"), safeJson(runSummary), "utf8");
  await fs.writeFile(path.join(reportRoot, "README.md"), buildRunIndexMarkdown(runSummary), "utf8");
  await fs.writeFile(
    path.join(projectRoot, "runtime-data", "module2", "reports", "nonpdf-field-results", "latest-run.json"),
    safeJson({
      generated_at: runSummary.generated_at,
      output_dir: toRelativeProjectPath(reportRoot),
      file_count: runSummary.file_count,
    }),
    "utf8",
  );

  console.log(`Export finished: ${toRelativeProjectPath(reportRoot)}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
