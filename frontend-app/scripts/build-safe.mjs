import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { copyFile, mkdir, readdir, rm } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, '..');
const tempOutDir = path.join(projectRoot, '.dist-build-temp');
const viteCliPath = path.join(projectRoot, 'node_modules', 'vite', 'bin', 'vite.js');

const passthroughArgs = process.argv.slice(2);
const resolveModeFromArgs = (args) => {
  for (let i = 0; i < args.length; i += 1) {
    const value = String(args[i] || '').trim();
    if (!value) {
      continue;
    }
    if (value === '--mode' && i + 1 < args.length) {
      const modeValue = String(args[i + 1] || '').trim();
      if (modeValue) {
        return modeValue;
      }
    }
    if (value.startsWith('--mode=')) {
      const modeValue = value.slice('--mode='.length).trim();
      if (modeValue) {
        return modeValue;
      }
    }
  }
  return 'production';
};
const buildMode = resolveModeFromArgs(passthroughArgs);
const defaultOutDir = buildMode === 'native' ? 'dist-native' : 'dist';
const finalOutDir = path.resolve(projectRoot, String(process.env.VITE_BUILD_OUT_DIR || defaultOutDir).trim() || defaultOutDir);
const isNativeBuild = buildMode === 'native';
const shouldCleanOutDir = buildMode === 'native' || String(process.env.VITE_FORCE_CLEAN_OUT_DIR || '').trim() === '1';

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

    // Native build must always overwrite to avoid stale hashed assets in APK.
    // Keep web build resilient on Windows lock contention (commonly dist/assets).
    if (!isNativeBuild) {
      const isAssetFile = relativePath.startsWith('assets/');
      if (isAssetFile && existsSync(targetPath)) {
        continue;
      }
    }

    await mkdir(path.dirname(targetPath), { recursive: true });
    await copyFile(sourcePath, targetPath);
  }
};

const main = async () => {
  await runViteBuildIntoTemp();
  if (shouldCleanOutDir) {
    await removeIfExists(finalOutDir);
  }
  await mkdir(finalOutDir, { recursive: true });
  await copyTree(tempOutDir, finalOutDir);
  await removeIfExists(tempOutDir);
};

main().catch(async (error) => {
  await removeIfExists(tempOutDir);
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
