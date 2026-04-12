#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const datasetRoot = path.join(projectRoot, "datasets");
const outputRoot = path.join(projectRoot, "backend", "module2", "tools", "generated_tests");

const batchApiUrl = process.env.MODULE2_EXTRACT_URL || "http://localhost:3001/extract/batch";
const traceApiUrl = process.env.MODULE2_TRACE_URL || "http://localhost:3001/extract/trace/locate";
const rounds = Math.max(1, Number.parseInt(process.env.MODULE2_REALISTIC_ROUNDS || "5", 10) || 5);
const singleNonPdfSlaMs = 90_000;
const maxMultiFiles = 3;

const DEFAULT_SCHEMA = {
  fields: {
    contract_amount: "number",
    start_date: "string",
    end_date: "string",
    tax_rate: "number",
    region: "string",
  },
  dependencies: {
    tax_rate: ["region"],
  },
};

const ALLOWED_EXT = new Set([
  ".pdf",
  ".docx",
  ".xlsx",
  ".txt",
  ".md",
  ".png",
  ".jpg",
  ".jpeg",
  ".bmp",
  ".webp",
  ".tif",
  ".tiff",
]);

const NON_PDF_EXT = new Set([
  ".docx",
  ".xlsx",
  ".txt",
  ".md",
  ".png",
  ".jpg",
  ".jpeg",
  ".bmp",
  ".webp",
  ".tif",
  ".tiff",
]);

function tsTag() {
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}_${hh}${mi}${ss}`;
}

function mulberry32(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function randomInt(rng, maxExclusive) {
  return Math.floor(rng() * maxExclusive);
}

async function collectFiles(root) {
  const out = [];
  async function walk(dir) {
    let entries = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        // eslint-disable-next-line no-await-in-loop
        await walk(fullPath);
        continue;
      }
      const ext = path.extname(entry.name).toLowerCase();
      if (!ALLOWED_EXT.has(ext)) continue;
      let size = 0;
      try {
        const stat = await fs.stat(fullPath);
        size = Number(stat.size || 0);
      } catch {
        size = 0;
      }
      out.push({ path: fullPath, ext, size });
    }
  }
  await walk(root);
  out.sort((a, b) => a.path.localeCompare(b.path));
  return out;
}

function pickOne(rng, files, usedSet, hardCapBytes = Number.POSITIVE_INFINITY) {
  const candidates = files.filter((f) => !usedSet.has(f.path) && f.size <= hardCapBytes);
  if (candidates.length === 0) return null;
  return candidates[randomInt(rng, candidates.length)] || null;
}

function pickMany(rng, files, count, usedSet) {
  const pool = files.filter((f) => !usedSet.has(f.path));
  if (pool.length <= count) return pool.slice();
  const out = [];
  const seen = new Set();
  while (out.length < count && seen.size < pool.length) {
    const idx = randomInt(rng, pool.length);
    if (seen.has(idx)) continue;
    seen.add(idx);
    out.push(pool[idx]);
  }
  return out;
}

function nonNullFieldNames(doc) {
  const result = doc?.result || {};
  return Object.entries(result)
    .filter(([, entity]) => entity && typeof entity === "object" && entity.value != null)
    .map(([field]) => field);
}

function calcTraceRatio(doc) {
  const result = doc?.result || {};
  const entities = Object.values(result).filter((item) => item && typeof item === "object" && item.value != null);
  if (entities.length === 0) return 1;
  const grounded = entities.filter((entity) => String(entity.source_ref_id || "").trim()).length;
  return Number((grounded / entities.length).toFixed(4));
}

function calcFigureCompletenessLike(doc) {
  const figureCount = Number(doc?.diagnostics?.figure_count || 0);
  if (figureCount <= 0) return 1;
  const traceHits = Array.isArray(doc?.trace_hits) ? doc.trace_hits : [];
  const figureHits = traceHits.filter((hit) => String(hit?.object_type || "").toLowerCase() === "figure").length;
  return Number(Math.min(1, figureHits / Math.max(1, figureCount)).toFixed(4));
}

function calcTablePrecisionLike(doc) {
  const tableCount = Number(doc?.diagnostics?.table_count || 0);
  if (!Number.isFinite(tableCount) || tableCount <= 0) return 1;
  const raw = Number(doc?.diagnostics?.table_quality_avg || 0);
  if (!Number.isFinite(raw)) return 0;
  return Number(Math.max(0, Math.min(1, raw)).toFixed(4));
}

async function locateTraceForDoc(doc, fieldName) {
  const response = await fetch(traceApiUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document: doc,
      field_name: fieldName,
      top_k: 6,
    }),
  });
  if (!response.ok) return 0;
  const payload = await response.json().catch(() => ({}));
  return Number(payload?.hit_count || 0);
}

async function runBatchWithFiles(files) {
  const form = new FormData();
  form.append("schema", JSON.stringify(DEFAULT_SCHEMA));
  for (const file of files) {
    // eslint-disable-next-line no-await-in-loop
    const buf = await fs.readFile(file.path);
    const blob = new Blob([buf], { type: "application/octet-stream" });
    form.append("files", blob, path.basename(file.path));
  }

  const t0 = Date.now();
  const response = await fetch(batchApiUrl, { method: "POST", body: form });
  const elapsedMs = Date.now() - t0;
  if (!response.ok) {
    const errText = await response.text().catch(() => "");
    return {
      ok: false,
      elapsed_ms: elapsedMs,
      status_code: response.status,
      error_text: errText || "请求失败",
      documents: [],
    };
  }
  const payload = await response.json().catch(() => ({}));
  const documents = Array.isArray(payload?.documents) ? payload.documents : [];
  return {
    ok: true,
    elapsed_ms: elapsedMs,
    status_code: 200,
    error_text: "",
    documents,
  };
}

async function evaluateDocuments(documents) {
  if (!Array.isArray(documents) || documents.length === 0) {
    return {
      failed: 0,
      trace_locator_ratio: 1,
      figure_completeness_like: 1,
      table_precision_like: 0,
      trace_api_hit_ratio: 1,
    };
  }

  let failed = 0;
  let traceRatioSum = 0;
  let figSum = 0;
  let tableSum = 0;
  let traceApiHit = 0;
  let traceApiTotal = 0;

  for (const doc of documents) {
    if (Array.isArray(doc?.errors) && doc.errors.length > 0) failed += 1;
    traceRatioSum += calcTraceRatio(doc);
    figSum += calcFigureCompletenessLike(doc);
    tableSum += calcTablePrecisionLike(doc);

    const fields = nonNullFieldNames(doc).slice(0, 2);
    for (const field of fields) {
      traceApiTotal += 1;
      // eslint-disable-next-line no-await-in-loop
      const hitCount = await locateTraceForDoc(doc, field);
      if (hitCount > 0) traceApiHit += 1;
    }
  }

  return {
    failed,
    trace_locator_ratio: Number((traceRatioSum / documents.length).toFixed(4)),
    figure_completeness_like: Number((figSum / documents.length).toFixed(4)),
    table_precision_like: Number((tableSum / documents.length).toFixed(4)),
    trace_api_hit_ratio: traceApiTotal > 0 ? Number((traceApiHit / traceApiTotal).toFixed(4)) : 1,
  };
}

function buildRoundFiles(rng, allFiles, usedSet) {
  const nonPdfFiles = allFiles.filter((f) => NON_PDF_EXT.has(f.ext));
  const pdfFiles = allFiles.filter((f) => f.ext === ".pdf");

  const singleNonPdf =
    pickOne(rng, nonPdfFiles, usedSet, 12 * 1024 * 1024) ||
    pickOne(rng, nonPdfFiles, usedSet) ||
    null;

  const multi = [];
  if (pdfFiles.length > 0) {
    const onePdf = pickOne(rng, pdfFiles, usedSet, 18 * 1024 * 1024) || pickOne(rng, pdfFiles, usedSet);
    if (onePdf) multi.push(onePdf);
  }
  if (nonPdfFiles.length > 0) {
    const oneNonPdf =
      pickOne(rng, nonPdfFiles, new Set([...usedSet, ...multi.map((x) => x.path)]), 12 * 1024 * 1024) ||
      pickOne(rng, nonPdfFiles, new Set([...usedSet, ...multi.map((x) => x.path)]));
    if (oneNonPdf) multi.push(oneNonPdf);
  }
  const needed = Math.max(0, maxMultiFiles - multi.length);
  if (needed > 0) {
    const multiPool = allFiles.filter((f) => f.size <= 15 * 1024 * 1024);
    const picks = pickMany(rng, multiPool, needed, new Set([...usedSet, ...multi.map((x) => x.path)]));
    multi.push(...picks);
  }
  if (multi.length < 2) {
    const fallback = pickMany(rng, allFiles, Math.max(2, maxMultiFiles), usedSet);
    multi.splice(0, multi.length, ...fallback.slice(0, maxMultiFiles));
  }

  return { singleNonPdf, multi: multi.slice(0, maxMultiFiles) };
}

async function runRound(roundIndex, files, rng, usedSet) {
  const picked = buildRoundFiles(rng, files, usedSet);
  if (!picked.singleNonPdf || picked.multi.length < 2) {
    throw new Error("测试集可用文件不足，无法构造单文件+多文件场景。");
  }

  usedSet.add(picked.singleNonPdf.path);
  for (const f of picked.multi) usedSet.add(f.path);

  const singleRun = await runBatchWithFiles([picked.singleNonPdf]);
  const multiRun = await runBatchWithFiles(picked.multi);
  const singleEval = await evaluateDocuments(singleRun.documents);
  const multiEval = await evaluateDocuments(multiRun.documents);

  const singleSlaOk = singleRun.elapsed_ms < singleNonPdfSlaMs;
  return {
    round: roundIndex,
    single_nonpdf: {
      file: path.basename(picked.singleNonPdf.path),
      ext: picked.singleNonPdf.ext,
      elapsed_ms: singleRun.elapsed_ms,
      under_90s: singleSlaOk,
      ok: singleRun.ok,
      failed_docs: singleEval.failed,
      trace_locator_ratio: singleEval.trace_locator_ratio,
      trace_api_hit_ratio: singleEval.trace_api_hit_ratio,
      figure_completeness_like: singleEval.figure_completeness_like,
      table_precision_like: singleEval.table_precision_like,
      status_code: singleRun.status_code,
      error_text: singleRun.error_text,
    },
    multi_mixed: {
      files: picked.multi.map((x) => path.basename(x.path)),
      elapsed_ms: multiRun.elapsed_ms,
      ok: multiRun.ok,
      failed_docs: multiEval.failed,
      trace_locator_ratio: multiEval.trace_locator_ratio,
      trace_api_hit_ratio: multiEval.trace_api_hit_ratio,
      figure_completeness_like: multiEval.figure_completeness_like,
      table_precision_like: multiEval.table_precision_like,
      status_code: multiRun.status_code,
      error_text: multiRun.error_text,
    },
  };
}

function summarize(roundReports) {
  const totalRounds = roundReports.length;
  const singleSlaFailures = roundReports.filter((r) => !r.single_nonpdf.under_90s).length;
  const scenarioFailures = roundReports.filter((r) => !r.single_nonpdf.ok || !r.multi_mixed.ok).length;

  const singleTraceAvg =
    totalRounds > 0
      ? Number((roundReports.reduce((acc, r) => acc + Number(r.single_nonpdf.trace_locator_ratio || 0), 0) / totalRounds).toFixed(4))
      : 0;
  const multiTraceAvg =
    totalRounds > 0
      ? Number((roundReports.reduce((acc, r) => acc + Number(r.multi_mixed.trace_locator_ratio || 0), 0) / totalRounds).toFixed(4))
      : 0;
  const figAvg =
    totalRounds > 0
      ? Number((roundReports.reduce((acc, r) => acc + Number(r.multi_mixed.figure_completeness_like || 0), 0) / totalRounds).toFixed(4))
      : 0;
  const tableAvg =
    totalRounds > 0
      ? Number((roundReports.reduce((acc, r) => acc + Number(r.multi_mixed.table_precision_like || 0), 0) / totalRounds).toFixed(4))
      : 0;

  return {
    total_rounds: totalRounds,
    scenario_failures: scenarioFailures,
    single_nonpdf_sla_failures: singleSlaFailures,
    avg_single_trace_locator_ratio: singleTraceAvg,
    avg_multi_trace_locator_ratio: multiTraceAvg,
    avg_multi_figure_completeness_like: figAvg,
    avg_multi_table_precision_like: tableAvg,
  };
}

async function main() {
  const seed = Number(process.env.MODULE2_REALISTIC_SEED || Date.now()) >>> 0;
  const rng = mulberry32(seed);
  const files = await collectFiles(datasetRoot);
  if (files.length < 3) {
    throw new Error(`测试集文件数量不足: ${datasetRoot}`);
  }

  const usedSet = new Set();
  const roundReports = [];
  for (let i = 1; i <= rounds; i += 1) {
    // eslint-disable-next-line no-console
    console.log(`[round ${i}/${rounds}] running single+multi`);
    // eslint-disable-next-line no-await-in-loop
    const report = await runRound(i, files, rng, usedSet);
    roundReports.push(report);
  }

  const summary = summarize(roundReports);
  const output = {
    generated_at: new Date().toISOString(),
    seed,
    batch_api_url: batchApiUrl,
    trace_api_url: traceApiUrl,
    dataset_root: datasetRoot,
    rounds,
    single_nonpdf_sla_ms: singleNonPdfSlaMs,
    summary,
    rounds_report: roundReports,
  };

  await fs.mkdir(outputRoot, { recursive: true });
  const outputPath = path.join(outputRoot, `frontend_realistic_${tsTag()}.json`);
  await fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf-8");

  // eslint-disable-next-line no-console
  console.log(
    JSON.stringify(
      {
        output_path: outputPath,
        summary,
      },
      null,
      2
    )
  );
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});
