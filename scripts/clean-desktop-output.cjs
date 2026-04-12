const fs = require('fs');
const path = require('path');

const { sourceRootDir } = require('./python-service-utils.cjs');

const argv = process.argv.slice(2);
const dryRun = argv.includes('--dry-run');
const outputOnly = argv.includes('--output-only');
const outputArgs = argv.filter((item) => !String(item || '').startsWith('-'));
const defaultOutputDirs = ['dist-electron', 'dist-electron-final'];
const workspaceRoot = path.resolve(sourceRootDir);
const rawOutputDirs = outputArgs.length > 0
  ? outputArgs
  : (process.env.DESKTOP_OUTPUT_DIR ? [process.env.DESKTOP_OUTPUT_DIR] : defaultOutputDirs);
const sourceCacheRoots = [
  'backend/app',
  'backend/module2/app',
  'backend/module2/tests',
  'backend/module4/app',
  'backend/tests',
  'frontend',
  'backend/auth',
  'auth',
];
const extraCacheDirs = ['.pytest_cache'];
const ignoredWalkDirNames = new Set(['node_modules', '.git', '.venv-module2-py311']);
const cacheDirNames = new Set(['__pycache__']);
const cacheFileExts = new Set(['.pyc', '.pyo']);

const isWithinWorkspace = (candidatePath) => {
  const normalizedWorkspace = path.resolve(workspaceRoot);
  const normalizedCandidate = path.resolve(candidatePath);
  return (
    normalizedCandidate === normalizedWorkspace
    || normalizedCandidate.startsWith(`${normalizedWorkspace}${path.sep}`)
  );
};

const ensureSafeTarget = (targetPath) => {
  if (!isWithinWorkspace(targetPath) || targetPath === workspaceRoot) {
    console.error(JSON.stringify({
      ok: false,
      error: `Refusing to remove unsafe path: ${targetPath}`,
      workspace_root: workspaceRoot,
    }, null, 2));
    process.exit(1);
  }
};

const walkDir = (rootPath, visitor) => {
  const stack = [rootPath];
  while (stack.length > 0) {
    const currentPath = stack.pop();
    if (!currentPath || !fs.existsSync(currentPath) || !fs.statSync(currentPath).isDirectory()) {
      continue;
    }

    for (const entry of fs.readdirSync(currentPath, { withFileTypes: true })) {
      const entryPath = path.join(currentPath, entry.name);
      const action = visitor(entryPath, entry);
      if (entry.isDirectory() && action !== 'skip') {
        stack.push(entryPath);
      }
    }
  }
};

const collectSourceCacheTargets = () => {
  const dirTargets = new Set();
  const fileTargets = new Set();

  for (const relDir of extraCacheDirs) {
    const absDir = path.resolve(workspaceRoot, relDir);
    if (fs.existsSync(absDir)) {
      dirTargets.add(absDir);
    }
  }

  for (const relRoot of sourceCacheRoots) {
    const absRoot = path.resolve(workspaceRoot, relRoot);
    if (!fs.existsSync(absRoot) || !fs.statSync(absRoot).isDirectory()) {
      continue;
    }

    walkDir(absRoot, (entryPath, entry) => {
      if (entry.isDirectory()) {
        if (ignoredWalkDirNames.has(entry.name)) {
          return 'skip';
        }
        if (cacheDirNames.has(entry.name)) {
          dirTargets.add(entryPath);
          return 'skip';
        }
        return undefined;
      }

      if (entry.isFile() && cacheFileExts.has(path.extname(entry.name).toLowerCase())) {
        fileTargets.add(entryPath);
      }
      return undefined;
    });
  }

  const normalizedDirTargets = Array.from(dirTargets).map((item) => path.resolve(item));
  const filteredFileTargets = Array.from(fileTargets)
    .map((item) => path.resolve(item))
    .filter((filePath) => !normalizedDirTargets.some((dirPath) => filePath.startsWith(`${dirPath}${path.sep}`)));

  return [
    ...normalizedDirTargets.map((targetPath) => ({
      category: 'source_cache',
      type: 'dir',
      path: targetPath,
      label: path.relative(workspaceRoot, targetPath) || '.',
    })),
    ...filteredFileTargets.map((targetPath) => ({
      category: 'source_cache',
      type: 'file',
      path: targetPath,
      label: path.relative(workspaceRoot, targetPath) || '.',
    })),
  ];
};

const outputTargets = rawOutputDirs.map((rawOutputDir) => {
  const targetPath = path.resolve(workspaceRoot, rawOutputDir);
  return {
    category: 'desktop_output',
    type: 'dir',
    path: targetPath,
    label: rawOutputDir,
  };
});

const targets = [
  ...outputTargets,
  ...(outputOnly ? [] : collectSourceCacheTargets()),
];

const results = [];
for (const target of targets) {
  ensureSafeTarget(target.path);
  const exists = fs.existsSync(target.path);
  if (exists && !dryRun) {
    fs.rmSync(target.path, { recursive: true, force: true });
  }
  results.push({
    category: target.category,
    type: target.type,
    label: target.label,
    target_path: target.path,
    existed: exists,
    removed: exists && !dryRun,
  });
}

console.log(JSON.stringify({
  ok: true,
  dry_run: dryRun,
  output_only: outputOnly,
  workspace_root: workspaceRoot,
  removed_count: results.filter((item) => item.removed).length,
  targets: results,
}, null, 2));
