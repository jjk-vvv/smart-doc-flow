import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, "..");
const projectRoot = path.resolve(frontendRoot, "..");
const singleRunScript = path.join(frontendRoot, "e2e", "module3-live-check.mjs");
const datasetRoot = path.join(
  projectRoot,
  "datasets",
  process.env.MODULE3_BATCH_DATASET_DIR || "模块三测试文件",
);
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const batchOutputRoot = path.join(projectRoot, ".runlogs", "module3-live-batch", runTag);
const singleRunRoot = path.join(projectRoot, ".runlogs", "module3-live-check");
const singleRunTimeoutMs = Math.max(
  15 * 60_000,
  Number(process.env.MODULE3_BATCH_SINGLE_TIMEOUT_MS || 45 * 60_000),
);

function nowIso() {
  return new Date().toISOString();
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function writeJson(filePath, payload) {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf8");
}

function relativePath(filePath) {
  return path.relative(projectRoot, filePath).replace(/\\/g, "/");
}

async function readDirNamesSafe(dirPath) {
  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort((a, b) => String(a).localeCompare(String(b), "en-US"));
  } catch {
    return [];
  }
}

async function discoverCaseDirs() {
  const entries = await fs.readdir(datasetRoot, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory() && /^case_repo\d+$/i.test(entry.name))
    .map((entry) => path.join(datasetRoot, entry.name))
    .sort((a, b) => String(a).localeCompare(String(b), "en-US"));
}

function execNodeScript(scriptPath, env = {}) {
  return new Promise((resolve) => {
    let timedOut = false;
    const child = spawn(process.execPath, [scriptPath], {
      cwd: frontendRoot,
      env: {
        ...process.env,
        ...env,
      },
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      const text = String(chunk || "");
      stdout += text;
      process.stdout.write(text);
    });
    child.stderr.on("data", (chunk) => {
      const text = String(chunk || "");
      stderr += text;
      process.stderr.write(text);
    });

    const timeoutHandle = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, singleRunTimeoutMs);

    child.on("close", (code) => {
      clearTimeout(timeoutHandle);
      resolve({
        code: Number(code || 0),
        stdout,
        stderr,
        timed_out: timedOut,
      });
    });
  });
}

async function loadSingleRunResult(runDirPath) {
  const summaryPath = path.join(runDirPath, "summary.json");
  const failurePath = path.join(runDirPath, "failure.json");
  try {
    const summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));
    return {
      ok: true,
      summary,
      failure: null,
    };
  } catch {
    // ignore
  }
  try {
    const failure = JSON.parse(await fs.readFile(failurePath, "utf8"));
    return {
      ok: false,
      summary: null,
      failure,
    };
  } catch {
    return {
      ok: false,
      summary: null,
      failure: {
        ok: false,
        error: "missing_summary_and_failure_json",
      },
    };
  }
}

async function resolveNewRunDirectory(beforeNames, afterNames) {
  const before = new Set(beforeNames);
  const created = afterNames.filter((name) => !before.has(name));
  if (created.length > 0) {
    const newest = created[created.length - 1];
    return path.join(singleRunRoot, newest);
  }
  if (afterNames.length > 0) {
    const fallbackNewest = afterNames[afterNames.length - 1];
    return path.join(singleRunRoot, fallbackNewest);
  }
  return "";
}

async function runCase(caseRoot, index, total) {
  const caseName = path.basename(caseRoot);
  const startedAt = nowIso();
  console.log(`\n[module3-batch] (${index}/${total}) start ${caseName}`);

  const beforeNames = await readDirNamesSafe(singleRunRoot);
  const execResult = await execNodeScript(singleRunScript, {
    MODULE3_DATASET_CASE_ROOT: caseRoot,
    MODULE3_RUN_TIMEOUT_MS: String(process.env.MODULE3_RUN_TIMEOUT_MS || 2_100_000),
    MODULE3_RUN_POLL_MS: String(process.env.MODULE3_RUN_POLL_MS || 5_000),
  });
  const afterNames = await readDirNamesSafe(singleRunRoot);
  const runDirPath = await resolveNewRunDirectory(beforeNames, afterNames);
  const runData = runDirPath ? await loadSingleRunResult(runDirPath) : null;

  const compare = runData?.summary?.compare || null;
  const accuracy = Number(compare?.accuracy_vs_expected_non_empty || 0);
  const expectedCount = Number(compare?.expected_non_empty || 0);

  const caseResult = {
    case_name: caseName,
    case_root: relativePath(caseRoot),
    started_at: startedAt,
    finished_at: nowIso(),
    process_exit_code: execResult.code,
    process_timed_out: Boolean(execResult.timed_out),
    output_root: runData?.summary?.output_root || runData?.failure?.output_root || relativePath(runDirPath || ""),
    ok: Boolean(runData?.summary?.ok) && execResult.code === 0,
    web_status: String(runData?.summary?.web?.run_status?.final?.status || ""),
    mobile_status: String(runData?.summary?.mobile?.run_status?.final?.status || ""),
    compare_kind: String(compare?.compare_kind || ""),
    accuracy_vs_expected_non_empty: accuracy,
    expected_non_empty: expectedCount,
    compare: compare || null,
    summary: runData?.summary || null,
    failure: runData?.failure || (execResult.code !== 0 ? { error: "process_failed_without_failure_json" } : null),
    stderr_tail: String(execResult.stderr || "").slice(-4000),
  };

  console.log(
    `[module3-batch] (${index}/${total}) finish ${caseName} ok=${caseResult.ok} web=${caseResult.web_status || "-"} mobile=${caseResult.mobile_status || "-"} acc=${accuracy}`,
  );
  return caseResult;
}

function summarizeResults(caseResults) {
  const finished = caseResults.length;
  const passed = caseResults.filter((item) => item.ok).length;
  const failed = finished - passed;
  const withCompare = caseResults.filter(
    (item) => Number(item.expected_non_empty || 0) > 0,
  );
  const weightedDenominator = withCompare.reduce(
    (sum, item) => sum + Number(item.expected_non_empty || 0),
    0,
  );
  const weightedNumerator = withCompare.reduce(
    (sum, item) =>
      sum +
      Number(item.accuracy_vs_expected_non_empty || 0) *
        Number(item.expected_non_empty || 0),
    0,
  );
  const weightedAccuracy =
    weightedDenominator > 0
      ? Number((weightedNumerator / weightedDenominator).toFixed(4))
      : 0;
  const averageAccuracy =
    withCompare.length > 0
      ? Number(
          (
            withCompare.reduce(
              (sum, item) => sum + Number(item.accuracy_vs_expected_non_empty || 0),
              0,
            ) / withCompare.length
          ).toFixed(4),
        )
      : 0;

  return {
    total_cases: finished,
    passed_cases: passed,
    failed_cases: failed,
    compared_cases: withCompare.length,
    weighted_accuracy_vs_expected_non_empty: weightedAccuracy,
    average_accuracy_vs_expected_non_empty: averageAccuracy,
  };
}

async function main() {
  await ensureDir(batchOutputRoot);
  const caseDirs = await discoverCaseDirs();
  if (caseDirs.length === 0) {
    throw new Error(`module3_batch_cases_not_found:${datasetRoot}`);
  }

  const report = {
    started_at: nowIso(),
    batch_output_root: relativePath(batchOutputRoot),
    dataset_root: relativePath(datasetRoot),
    case_count: caseDirs.length,
    cases: [],
    summary: null,
    ok: false,
  };

  for (let i = 0; i < caseDirs.length; i += 1) {
    const caseResult = await runCase(caseDirs[i], i + 1, caseDirs.length);
    report.cases.push(caseResult);
    await writeJson(path.join(batchOutputRoot, "batch-progress.json"), report);
  }

  report.summary = summarizeResults(report.cases);
  report.ok = report.summary.failed_cases === 0;
  report.finished_at = nowIso();

  await writeJson(path.join(batchOutputRoot, "batch-summary.json"), report);
  console.log(JSON.stringify(report, null, 2));
}

main().catch(async (error) => {
  const failure = {
    ok: false,
    dataset_root: relativePath(datasetRoot),
    batch_output_root: relativePath(batchOutputRoot),
    failed_at: nowIso(),
    error: String(error?.stack || error?.message || error),
  };
  await writeJson(path.join(batchOutputRoot, "batch-failure.json"), failure);
  console.error(JSON.stringify(failure, null, 2));
  process.exitCode = 1;
});

