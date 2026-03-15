import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve("..", "..");
const datasetRoot = path.join(root, "datasets");

async function collectFiles(dir, out = []) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await collectFiles(full, out);
      continue;
    }
    if (/\.(pdf|docx|xlsx|txt|md|png|jpg|jpeg|bmp|webp|tif|tiff)$/i.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

const files = await collectFiles(datasetRoot, []);
console.log("files", files.length, files.slice(0, 3));

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1560, height: 980 } });
page.on("console", (msg) => {
  if (msg.type() === "error") {
    console.log("console_error", msg.text());
  }
});
page.on("pageerror", (err) => {
  console.log("page_error", String(err));
});

await page.goto("http://127.0.0.1:3000", { waitUntil: "domcontentloaded", timeout: 90000 });
await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});

const startExtractBtn = page.getByTestId("module2-start-extract");
const addFilesBtn = page.getByTestId("module2-add-files");
const alreadyReady = (await startExtractBtn.isVisible({ timeout: 2000 }).catch(() => false)) && (await addFilesBtn.isVisible({ timeout: 2000 }).catch(() => false));
console.log("alreadyReady", alreadyReady);
if (!alreadyReady) {
  await page.getByRole("button", { name: /\u667a\u80fd\u6587\u6863\u89e3\u6790/ }).first().click({ timeout: 20000 });
  await page.getByRole("button", { name: /\u975e\u7ed3\u6784\u5316\u6587\u6863\u4fe1\u606f\u9700\u6c42\u6a21\u5757/ }).first().click({ timeout: 20000 });
  await startExtractBtn.waitFor({ state: "visible", timeout: 45000 });
  await addFilesBtn.waitFor({ state: "visible", timeout: 45000 });
}

console.log("before upload start visible", await startExtractBtn.isVisible().catch(() => false));
await page.setInputFiles('[data-testid="module2-file-input"]', [files[0]]);
await page.waitForTimeout(1200);
console.log("after upload start visible", await startExtractBtn.isVisible().catch(() => false));
console.log("after upload add visible", await addFilesBtn.isVisible().catch(() => false));

await page.screenshot({ path: "../backend/module2/tools/generated_tests/screenshots/debug_upload_script.png", fullPage: true });

await browser.close();
