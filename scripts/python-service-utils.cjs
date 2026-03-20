const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const nodeExec = process.execPath;
const defaultPythonExec = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

const venvPythonPath = (venvDir) =>
  process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

const venvBinDir = (venvDir) =>
  process.platform === 'win32'
    ? path.join(venvDir, 'Scripts')
    : path.join(venvDir, 'bin');

const resolvePythonExec = ({ overrideExec, preferredVenvDirs = [], fallbackExec = defaultPythonExec } = {}) => {
  if (overrideExec) return overrideExec;

  for (const venvDir of preferredVenvDirs.filter(Boolean)) {
    const candidate = venvPythonPath(venvDir);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return fallbackExec;
};

const detectVenvRootFromPythonExec = (pythonExec) => {
  const normalizedExec = path.resolve(String(pythonExec || ''));
  const candidateDir = path.dirname(normalizedExec);
  const parentDir = path.dirname(candidateDir);
  const venvRoot = ['Scripts', 'bin'].includes(path.basename(candidateDir)) ? parentDir : candidateDir;
  const cfgPath = path.join(venvRoot, 'pyvenv.cfg');
  return fs.existsSync(cfgPath) ? venvRoot : null;
};

const buildPythonRuntimeEnv = ({ baseEnv = process.env, pythonExec } = {}) => {
  const env = { ...baseEnv };
  const venvRoot = detectVenvRootFromPythonExec(pythonExec);
  if (!venvRoot) {
    return env;
  }

  const binDir = venvBinDir(venvRoot);
  const pathKey = Object.keys(env).find((key) => key.toUpperCase() === 'PATH') || 'PATH';
  const currentPath = String(env[pathKey] || '');
  const pathParts = currentPath
    .split(path.delimiter)
    .map((part) => String(part || '').trim())
    .filter(Boolean);
  const normalizedBinDir = path.resolve(binDir);
  const filteredParts = pathParts.filter((part) => path.resolve(part) !== normalizedBinDir);

  env[pathKey] = [normalizedBinDir, ...filteredParts].join(path.delimiter);
  env.VIRTUAL_ENV = venvRoot;
  env.PYTHONNOUSERSITE = env.PYTHONNOUSERSITE || '1';
  return env;
};

const reloadEnabled = (name, defaultValue = true) => {
  const raw = process.env[name];
  if (raw == null || raw === '') return defaultValue;
  return !['0', 'false', 'no', 'off'].includes(String(raw).trim().toLowerCase());
};

const buildReloadArgs = ({
  sourceDirs = [],
  excludeGlobs = [],
} = {}) => {
  const args = ['--reload'];
  for (const dir of sourceDirs) {
    args.push('--reload-dir', dir);
  }
  for (const pattern of excludeGlobs) {
    args.push('--reload-exclude', pattern);
  }
  return args;
};

const formatCommand = (command, args = []) =>
  [command, ...args]
    .map((part) => {
      const text = String(part);
      return /\s/.test(text) ? `"${text}"` : text;
    })
    .join(' ');

module.exports = {
  buildPythonRuntimeEnv,
  buildReloadArgs,
  defaultPythonExec,
  detectVenvRootFromPythonExec,
  formatCommand,
  nodeExec,
  reloadEnabled,
  resolvePythonExec,
  rootDir,
  venvBinDir,
  venvPythonPath,
};
