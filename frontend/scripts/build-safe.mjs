import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { copyFile, mkdir, readdir, rm } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, '..');
const tempOutDir = path.join(projectRoot, '.dist-build-temp');
const distDir = path.join(projectRoot, 'dist');
const viteCliPath = path.join(projectRoot, 'node_modules', 'vite', 'bin', 'vite.js');

const passthroughArgs = process.argv.slice(2);

const removeIfExists = async (targetPath) => {
  await rm(targetPath, {
    recursive: true,
    force: true,
    maxRetries: 3,
    retryDelay: 200,
  }).catch(() => {});
};

const runViteBuildIntoTemp = async () => {
  await removeIfExists(tempOutDir);

  await new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        viteCliPath,
        'build',
        '--outDir',
        tempOutDir,
        '--emptyOutDir',
        ...passthroughArgs,
      ],
      {
        cwd: projectRoot,
        stdio: 'inherit',
        shell: false,
      },
    );

    child.once('error', reject);
    child.once('exit', (code, signal) => {
      if (code === 0) {
        resolve(undefined);
        return;
      }
      reject(new Error(`vite build failed with ${signal ? `signal ${signal}` : `code ${code}`}`));
    });
  });
};

const copyTree = async (sourceDir, targetDir, sourceRoot = sourceDir) => {
  await mkdir(targetDir, { recursive: true });
  const entries = await readdir(sourceDir, { withFileTypes: true });

  for (const entry of entries) {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);
    const relativePath = path.relative(sourceRoot, sourcePath).replace(/\\/g, '/');

    if (entry.isDirectory()) {
      await copyTree(sourcePath, targetPath, sourceRoot);
      continue;
    }

    const isAssetFile = relativePath.startsWith('assets/');
    const shouldOverwrite = !isAssetFile || !existsSync(targetPath);

    if (!shouldOverwrite) {
      continue;
    }

    await mkdir(path.dirname(targetPath), { recursive: true });
    await copyFile(sourcePath, targetPath);
  }
};

const main = async () => {
  await runViteBuildIntoTemp();
  await mkdir(distDir, { recursive: true });
  await copyTree(tempOutDir, distDir);
  await removeIfExists(tempOutDir);
};

main().catch(async (error) => {
  await removeIfExists(tempOutDir);
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
