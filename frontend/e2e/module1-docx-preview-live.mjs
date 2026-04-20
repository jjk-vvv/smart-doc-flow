import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../node_modules/playwright/index.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const appUrl = String(process.env.SMART_DOC_FLOW_APP_URL || "http://127.0.0.1:3000").trim();
const authBase = String(process.env.SMART_DOC_FLOW_AUTH_API_BASE || "http://127.0.0.1:3001").trim();
const authAccount = String(
  process.env.PLAYWRIGHT_AUTH_ACCOUNT ||
    process.env.SMART_DOC_FLOW_E2E_ACCOUNT ||
    "codex_1776252886_183@example.com",
).trim();
const authPassword = String(
  process.env.PLAYWRIGHT_AUTH_PASSWORD ||
    process.env.SMART_DOC_FLOW_E2E_PASSWORD ||
    "Codex123!",
).trim();
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.join(projectRoot, ".runlogs", "module1-docx-preview-web", runTag);

function parseJsonSafe(raw = "") {
  const text = String(raw || "").trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function resolveSampleDocx() {
  const candidateDir = path.join(projectRoot, "datasets", "word");
  const entries = await fs.readdir(candidateDir, { withFileTypes: true });
  const docxFiles = entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".docx"))
    .map((entry) => path.join(candidateDir, entry.name))
    .sort((a, b) => a.localeCompare(b, "zh-CN"));
  if (!docxFiles.length) {
    throw new Error(`docx_sample_not_found:${candidateDir}`);
  }
  return docxFiles[0];
}

async function login(context) {
  const response = await context.request.post(`${authBase}/api/login`, {
    headers: { "content-type": "application/json" },
    data: {
      account: authAccount,
      password: authPassword,
    },
  });
  const raw = await response.text();
  const payload = parseJsonSafe(raw);
  if (!response.ok()) {
    throw new Error(`login_failed:${response.status()}:${String(raw || "").slice(0, 300)}`);
  }
  return payload;
}

async function waitForPreviewResult(page) {
  const deadline = Date.now() + 120_000;

  while (Date.now() < deadline) {
    const canvasCount = await page.locator("canvas").count().catch(() => 0);
    const bodyText = await page.locator("body").innerText().catch(() => "");

    if (canvasCount > 0) {
      return {
        ok: true,
        canvasCount,
        bodyText,
      };
    }

    if (
      bodyText.includes("Word 转 PDF 失败") ||
      bodyText.includes("PDF 预览加载失败") ||
      bodyText.includes("需要登录后访问")
    ) {
      return {
        ok: false,
        canvasCount,
        bodyText,
      };
    }

    await page.waitForTimeout(1500);
  }

  const bodyText = await page.locator("body").innerText().catch(() => "");
  return {
    ok: false,
    canvasCount: await page.locator("canvas").count().catch(() => 0),
    bodyText,
    timeout: true,
  };
}

async function writeResult(result) {
  await fs.writeFile(
    path.join(outputDir, "result.json"),
    JSON.stringify(result, null, 2),
    "utf8",
  );
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const filePath = await resolveSampleDocx();
  const result = {
    ok: false,
    appUrl,
    authBase,
    outputDir,
    filePath,
    auth: null,
    currentUrl: "",
    fileNameVisible: false,
    previewCanvasCount: 0,
    convertResponses: [],
    consoleErrors: [],
    pageErrors: [],
    bodyHints: {},
  };

  const browser = await chromium.launch({
    headless: String(process.env.PLAYWRIGHT_HEADLESS || "1").trim() !== "0",
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 960 },
    locale: "zh-CN",
  });
  const page = await context.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      result.consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    result.pageErrors.push(String(err?.message || err));
  });
  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/module1/convert/docx-to-pdf")) return;
    let textSnippet = "";
    if (!response.ok()) {
      try {
        textSnippet = String(await response.text()).slice(0, 300);
      } catch {
        textSnippet = "";
      }
    }
    result.convertResponses.push({
      url,
      status: response.status(),
      ok: response.ok(),
      contentType: response.headers()["content-type"] || "",
      textSnippet,
    });
  });

  try {
    result.auth = await login(context);

    await page.goto(`${appUrl}/?tab=doc-processing`, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
    await page.waitForTimeout(3000);
    result.currentUrl = page.url();

    await page.screenshot({
      path: path.join(outputDir, "01-doc-processing-open.png"),
      fullPage: true,
    });

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.waitFor({ state: "attached", timeout: 30_000 });
    await fileInput.setInputFiles(filePath);
    await page.waitForTimeout(1500);

    const previewToggle = page.locator("button").filter({
      has: page.locator("svg.lucide-eye"),
    }).first();
    if (await previewToggle.count()) {
      await previewToggle.click({ timeout: 10_000 }).catch(() => {});
      await page.waitForTimeout(1200);
    }

    const fileName = path.basename(filePath);
    try {
      await page.getByText(fileName, { exact: false }).first().waitFor({
        state: "visible",
        timeout: 15_000,
      });
      result.fileNameVisible = true;
    } catch {
      result.fileNameVisible = false;
    }

    await page.screenshot({
      path: path.join(outputDir, "02-after-upload.png"),
      fullPage: true,
    });

    const previewState = await waitForPreviewResult(page);
    result.previewCanvasCount = Number(previewState.canvasCount || 0);
    result.bodyHints = {
      hasConverting: String(previewState.bodyText || "").includes("正在将 Word 转为 PDF 预览"),
      hasPreviewLoadError: String(previewState.bodyText || "").includes("PDF 预览加载失败"),
      hasWordConvertError: String(previewState.bodyText || "").includes("Word 转 PDF 失败"),
      hasNeedLogin: String(previewState.bodyText || "").includes("需要登录后访问"),
      timeout: Boolean(previewState.timeout),
      textLength: String(previewState.bodyText || "").length,
    };

    await page.screenshot({
      path: path.join(outputDir, previewState.ok ? "03-preview-success.png" : "03-preview-failed.png"),
      fullPage: true,
    });

    result.ok =
      previewState.ok &&
      result.previewCanvasCount > 0 &&
      !result.bodyHints.hasNeedLogin &&
      !result.bodyHints.hasWordConvertError &&
      !result.bodyHints.hasPreviewLoadError;

    await writeResult(result);
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    result.ok = false;
    result.error = String(error?.stack || error?.message || error);
    try {
      await page.screenshot({
        path: path.join(outputDir, "99-script-error.png"),
        fullPage: true,
      });
    } catch {
      // Ignore screenshot failures during teardown.
    }
    await writeResult(result);
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = 1;
  } finally {
    await context.request.dispose().catch(() => {});
    await context.close().catch(() => {});
    await browser.close();
  }
}

main().catch((error) => {
  console.error(
    JSON.stringify(
      {
        ok: false,
        outputDir,
        error: String(error?.stack || error?.message || error),
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
});
