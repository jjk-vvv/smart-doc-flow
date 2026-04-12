import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const baseUrl = String(
  process.env.WORKFLOW_SMOKE_BASE_URL ||
    process.env.SMART_DOC_FLOW_APP_URL ||
    "http://127.0.0.1:3000",
).trim();
const runTag = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.join(projectRoot, ".runlogs", "workflow-smoke-debug", runTag);

async function ensureOutputDir() {
  await fs.mkdir(outputDir, { recursive: true });
}

function screenshotPath(name) {
  return path.join(outputDir, `${name}.png`);
}

async function writeTestPdf() {
  const pdfPath = path.join(outputDir, "smoke-upload.pdf");
  const minimalPdf = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 45>>stream
BT /F1 12 Tf 100 700 Td (Workflow Smoke Test PDF) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000361 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
442
%%EOF`;
  await fs.writeFile(pdfPath, minimalPdf, "utf8");
  return pdfPath;
}

async function main() {
  await ensureOutputDir();
  const smokePdfPath = await writeTestPdf();
  const browser = await chromium.launch({
    headless: process.env.WORKFLOW_SMOKE_HEADLESS !== "0",
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
  });
  const page = await context.newPage();
  const issues = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      issues.push(`console:${msg.text()}`);
    }
  });
  page.on("pageerror", (error) => {
    issues.push(`pageerror:${String(error.message || error)}`);
  });

  try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
    await page.screenshot({ path: screenshotPath("home"), fullPage: true });

    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.count()) {
      await fileInput.setInputFiles(smokePdfPath);
      await page.waitForTimeout(1200);
      await page.screenshot({ path: screenshotPath("after-upload"), fullPage: true });
    } else {
      issues.push("upload:file-input-missing");
    }

    const healthPayload = await page.evaluate(async () => {
      try {
        const response = await fetch("/gateway/ready", { credentials: "include" });
        return {
          status: response.status,
          body: await response.text(),
        };
      } catch (error) {
        return {
          status: 0,
          body: String(error instanceof Error ? error.message : error),
        };
      }
    });

    await page.screenshot({ path: screenshotPath("final"), fullPage: true });

    console.log(
      JSON.stringify(
        {
          ok: issues.length === 0 && healthPayload.status > 0 && healthPayload.status < 500,
          baseUrl,
          outputDir,
          smokePdfPath,
          gatewayReady: healthPayload,
          issues,
        },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(
    JSON.stringify(
      {
        ok: false,
        baseUrl,
        outputDir,
        error: String(error instanceof Error ? error.stack || error.message : error),
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
});
