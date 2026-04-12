const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');

const explicitRuntimeDirs = [
  path.join(rootDir, 'backend', 'module2', '.codex-temp'),
  path.join(rootDir, 'backend', 'module2', '.mcache'),
  path.join(rootDir, 'backend', 'module2', '.runlogs'),
  path.join(rootDir, 'backend', 'module2', '.runtime'),
  path.join(rootDir, 'backend', 'module4', '.runlogs'),
  path.join(rootDir, 'backend', 'module4', '.runtime'),
];

const pycacheRoots = [
  path.join(rootDir, 'backend', 'module2'),
  path.join(rootDir, 'backend', 'module4'),
];

const pycacheExcludedDirNames = new Set([
  '.venv',
  '.venv-module2-py311',
  '.venv-module4-py311',
  'node_modules',
  '.git',
]);

const normalize = (targetPath) => path.resolve(String(targetPath || ''));

const isUnderRoot = (targetPath) => {
  const normalizedRoot = normalize(rootDir);
  const normalizedTarget = normalize(targetPath);
  return (
    normalizedTarget === normalizedRoot
    || normalizedTarget.startsWith(`${normalizedRoot}${path.sep}`)
  );
};

const removeDirIfExists = (targetPath, removed, skipped) => {
  const normalizedTarget = normalize(targetPath);
  if (!isUnderRoot(normalizedTarget)) {
    skipped.push({ path: normalizedTarget, reason: 'outside_workspace' });
    return;
  }
  if (!fs.existsSync(normalizedTarget)) {
    return;
  }
  try {
    fs.rmSync(normalizedTarget, { recursive: true, force: true });
    removed.push(normalizedTarget);
  } catch (error) {
    skipped.push({ path: normalizedTarget, reason: `${error.name}: ${error.message}` });
  }
};

const collectPycacheDirs = (startDir) => {
  const out = [];
  const normalizedStart = normalize(startDir);
  if (!isUnderRoot(normalizedStart) || !fs.existsSync(normalizedStart)) {
    return out;
  }

  const stack = [normalizedStart];
  while (stack.length > 0) {
    const current = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (!isUnderRoot(fullPath)) {
        continue;
      }
      if (!entry.isDirectory()) {
        continue;
      }
      if (pycacheExcludedDirNames.has(entry.name)) {
        continue;
      }
      if (entry.name === '__pycache__') {
        out.push(fullPath);
        continue;
      }
      stack.push(fullPath);
    }
  }
  return out;
};

const removed = [];
const skipped = [];

for (const dir of explicitRuntimeDirs) {
  removeDirIfExists(dir, removed, skipped);
}

for (const root of pycacheRoots) {
  for (const pycacheDir of collectPycacheDirs(root)) {
    removeDirIfExists(pycacheDir, removed, skipped);
  }
}

console.log('[ops:clean-backend-runtime-dirs] removed:');
if (removed.length === 0) {
  console.log('  (none)');
} else {
  for (const item of removed) {
    console.log(`  - ${item}`);
  }
}

if (skipped.length > 0) {
  console.log('[ops:clean-backend-runtime-dirs] skipped:');
  for (const item of skipped) {
    console.log(`  - ${item.path} (${item.reason})`);
  }
}
