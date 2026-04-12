const fs = require('fs');
const path = require('path');

const {
  parseEnvFile,
  resolveDataRootDir,
  resolveRuntimeRootDir,
  rootDir,
} = require('./python-service-utils.cjs');

const envFileValues = parseEnvFile(path.join(rootDir, 'backend', '.env'));
const managedBaseEnv = { ...envFileValues, ...process.env };
const runtimeRoot = path.resolve(resolveRuntimeRootDir({ baseEnv: managedBaseEnv }) || rootDir);
const dataRoot = path.resolve(resolveDataRootDir({ baseEnv: managedBaseEnv, runtimeRoot }) || runtimeRoot);

const ensureDir = (target) => {
  fs.mkdirSync(target, { recursive: true });
};

const pathExists = (target) => {
  try {
    return fs.existsSync(target);
  } catch {
    return false;
  }
};

const isDirectory = (target) => {
  try {
    return fs.statSync(target).isDirectory();
  } catch {
    return false;
  }
};

const isFile = (target) => {
  try {
    return fs.statSync(target).isFile();
  } catch {
    return false;
  }
};

const removeIfEmpty = (target) => {
  if (!pathExists(target) || !isDirectory(target)) {
    return;
  }
  const children = fs.readdirSync(target);
  if (children.length === 0) {
    fs.rmSync(target, { recursive: true, force: true });
  }
};

const copyPath = (src, dest) => {
  ensureDir(path.dirname(dest));
  if (isDirectory(src)) {
    fs.cpSync(src, dest, { recursive: true, force: true });
    return;
  }
  fs.copyFileSync(src, dest);
};

const removePathBestEffort = (target) => {
  try {
    fs.rmSync(target, { recursive: true, force: true });
  } catch {
    // Keep the source path when another process still holds a file handle.
  }
};

const movePath = (src, dest, stats) => {
  if (!pathExists(src)) {
    return;
  }
  if (path.resolve(src) === path.resolve(dest)) {
    return;
  }

  if (!pathExists(dest)) {
    ensureDir(path.dirname(dest));
    try {
      fs.renameSync(src, dest);
      stats.moved += 1;
    } catch (error) {
      if (!['EPERM', 'EXDEV', 'EACCES'].includes(String(error && error.code || ''))) {
        throw error;
      }
      copyPath(src, dest);
      removePathBestEffort(src);
      stats.copied += 1;
    }
    return;
  }

  if (isDirectory(src) && isDirectory(dest)) {
    ensureDir(dest);
    for (const entry of fs.readdirSync(src)) {
      movePath(path.join(src, entry), path.join(dest, entry), stats);
    }
    removeIfEmpty(src);
    return;
  }

  if (isFile(src) && isFile(dest)) {
    const srcBuffer = fs.readFileSync(src);
    const destBuffer = fs.readFileSync(dest);
    if (Buffer.compare(srcBuffer, destBuffer) === 0) {
      removePathBestEffort(src);
      stats.deduped += 1;
      return;
    }
    const backupDest = `${dest}.migrated-${Date.now()}`;
    ensureDir(path.dirname(backupDest));
    fs.renameSync(src, backupDest);
    stats.conflicts += 1;
    return;
  }

  if (isFile(src) && isDirectory(dest)) {
    movePath(src, path.join(dest, path.basename(src)), stats);
    return;
  }

  if (isDirectory(src) && isFile(dest)) {
    const backupDest = `${dest}.backup-${Date.now()}`;
    fs.renameSync(dest, backupDest);
    stats.conflicts += 1;
    movePath(src, dest, stats);
  }
};

const visitJson = (value, mapper) => {
  if (typeof value === 'string') {
    return mapper(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => visitJson(item, mapper));
  }
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = visitJson(item, mapper);
    }
    return out;
  }
  return value;
};

const buildPrefixMapper = () => {
  const prefixes = [
    [path.join(runtimeRoot, 'backend', 'module2', 'artifacts'), path.join(dataRoot, 'module2', 'artifacts')],
    [path.join(runtimeRoot, 'backend', 'module4', 'workspaces'), path.join(dataRoot, 'module4', 'workspaces')],
    [path.join(runtimeRoot, 'module2'), path.join(dataRoot, 'module2')],
    [path.join(runtimeRoot, 'auth'), path.join(dataRoot, 'auth')],
  ]
    .map(([from, to]) => [path.resolve(from), path.resolve(to)])
    .sort((a, b) => b[0].length - a[0].length);

  return (raw) => {
    const text = String(raw || '').trim();
    if (!text) return text;
    const normalized = path.normalize(text);
    const normalizedLower = normalized.toLowerCase();
    for (const [from, to] of prefixes) {
      const fromLower = from.toLowerCase();
      if (normalizedLower === fromLower) {
        return to;
      }
      const prefix = `${fromLower}${path.sep}`;
      if (normalizedLower.startsWith(prefix)) {
        const suffix = normalized.slice(from.length + 1);
        return path.join(to, suffix);
      }
    }
    return raw;
  };
};

const rewriteJsonTree = (root) => {
  if (!pathExists(root) || !isDirectory(root)) {
    return 0;
  }
  const mapPrefix = buildPrefixMapper();
  let updated = 0;
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (!entry.isFile() || path.extname(entry.name).toLowerCase() !== '.json') {
        continue;
      }
      try {
        const raw = fs.readFileSync(fullPath, 'utf8');
        const parsed = JSON.parse(raw);
        const next = visitJson(parsed, mapPrefix);
        const nextText = JSON.stringify(next, null, 2);
        if (nextText !== raw) {
          fs.writeFileSync(fullPath, `${nextText}\n`, 'utf8');
          updated += 1;
        }
      } catch {
        // Ignore non-JSON or malformed runtime files.
      }
    }
  }
  return updated;
};

const stats = {
  moved: 0,
  copied: 0,
  deduped: 0,
  conflicts: 0,
  rewrittenJson: 0,
};

ensureDir(dataRoot);
ensureDir(path.join(dataRoot, 'auth'));
ensureDir(path.join(dataRoot, 'module2'));
ensureDir(path.join(dataRoot, 'module4'));

movePath(path.join(runtimeRoot, 'auth'), path.join(dataRoot, 'auth'), stats);
movePath(path.join(runtimeRoot, 'module2'), path.join(dataRoot, 'module2'), stats);
movePath(path.join(runtimeRoot, 'module4'), path.join(dataRoot, 'module4'), stats);
movePath(path.join(runtimeRoot, 'backend', 'module2', 'artifacts'), path.join(dataRoot, 'module2', 'artifacts'), stats);
movePath(path.join(runtimeRoot, 'backend', 'module4', 'workspaces'), path.join(dataRoot, 'module4', 'workspaces'), stats);
movePath(path.join(runtimeRoot, 'legacy'), path.join(dataRoot, 'legacy'), stats);
movePath(path.join(runtimeRoot, 'backend', 'backend'), path.join(dataRoot, 'legacy', 'backend-backend'), stats);
movePath(path.join(runtimeRoot, 'backend', 'module2', 'backend'), path.join(dataRoot, 'legacy', 'backend-module2-backend'), stats);

stats.rewrittenJson += rewriteJsonTree(path.join(dataRoot, 'module2'));
stats.rewrittenJson += rewriteJsonTree(path.join(dataRoot, 'module4'));

console.log('[normalize-runtime-layout] runtimeRoot=', runtimeRoot);
console.log('[normalize-runtime-layout] dataRoot=', dataRoot);
console.log('[normalize-runtime-layout] stats=', JSON.stringify(stats, null, 2));
