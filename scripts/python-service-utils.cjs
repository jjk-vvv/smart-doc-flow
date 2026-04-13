const fs = require('fs');
const path = require('path');

const trim = (value) => String(value || '').trim();
const sourceRootDir = path.resolve(__dirname, '..');
const nodeExec = process.execPath;
const defaultPythonExec = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const isElectronRuntime = Boolean(process.versions && process.versions.electron);
const packagedRuntimeRootDir = process.resourcesPath
  ? path.join(process.resourcesPath, 'app-runtime')
  : '';

const resolveRuntimeRootDir = ({ baseEnv = process.env } = {}) => {
  const overrideRootDir = trim(baseEnv.SMART_DOC_FLOW_RUNTIME_ROOT);
  if (overrideRootDir) {
    return path.resolve(overrideRootDir);
  }
  if (packagedRuntimeRootDir && fs.existsSync(packagedRuntimeRootDir)) {
    return path.resolve(packagedRuntimeRootDir);
  }
  return sourceRootDir;
};

const rootDir = resolveRuntimeRootDir();
const resolveConfigRootDir = ({ baseEnv = process.env, runtimeRoot = rootDir } = {}) => {
  const overrideConfigDir = trim(baseEnv.SMART_DOC_FLOW_CONFIG_ROOT);
  if (overrideConfigDir) {
    return path.resolve(overrideConfigDir);
  }
  return path.resolve(runtimeRoot);
};

const resolveDataRootDir = ({ baseEnv = process.env, runtimeRoot = rootDir } = {}) => {
  const overrideDataDir = trim(baseEnv.SMART_DOC_FLOW_DATA_ROOT);
  if (overrideDataDir) {
    return path.resolve(overrideDataDir);
  }
  return path.resolve(runtimeRoot);
};

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
  env.PYTHONDONTWRITEBYTECODE = env.PYTHONDONTWRITEBYTECODE || '1';
  return env;
};

const buildNodeRuntimeEnv = ({ baseEnv = process.env } = {}) => {
  const env = { ...baseEnv };
  if (isElectronRuntime) {
    env.ELECTRON_RUN_AS_NODE = '1';
    env.ELECTRON_NO_ATTACH_CONSOLE = env.ELECTRON_NO_ATTACH_CONSOLE || '1';
  }
  return env;
};

const parseEnvFile = (filePath, { allowedKeys = null } = {}) => {
  if (!filePath || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return {};
  }

  const allowSet = Array.isArray(allowedKeys) && allowedKeys.length > 0
    ? new Set(allowedKeys.map((item) => String(item || '').trim()).filter(Boolean))
    : null;
  const values = {};
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  for (const rawLine of lines) {
    const line = String(rawLine || '').trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const separatorIndex = line.indexOf('=');
    if (separatorIndex <= 0) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    if (!key) {
      continue;
    }
    if (allowSet && !allowSet.has(key)) {
      continue;
    }

    let value = line.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith('\'') && value.endsWith('\''))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }

  return values;
};

const AUTH_CORE_FALLBACK_KEYS = [
  'AUTH_SECRET_KEY',
  'AUTH_TOKEN_EXPIRES_IN',
  'AUTH_COOKIE_NAME',
  'AUTH_COOKIE_MAX_AGE_DAYS',
  'AUTH_PASSWORD_SALT_ROUNDS',
  'AUTH_VERIFY_CODE_EXPIRES_MS',
  'AUTH_SEND_CODE_WINDOW_MS',
  'AUTH_SEND_CODE_MAX_PER_CONTACT',
  'AUTH_SEND_CODE_MAX_PER_IP',
  'AUTH_SEND_CODE_COOLDOWN_MS',
  'AUTH_SMS_PROVIDER',
  'AUTH_IHUYI_API_ID',
  'AUTH_IHUYI_API_KEY',
  'AUTH_SMTP_HOST',
  'AUTH_SMTP_PORT',
  'AUTH_SMTP_SECURE',
  'AUTH_SMTP_USER',
  'AUTH_SMTP_PASS',
  'AUTH_SMTP_FROM',
  'AUTH_USERS_FILE',
];

const DEFAULT_MANAGED_ENV_SCOPES = ['backend', 'module2', 'module4'];

const MANAGED_ENV_SCOPE_SPECS = {
  backend: {
    relPath: path.join('backend', '.env'),
  },
  module2: {
    relPath: path.join('backend', 'module2', '.env'),
  },
  module4: {
    relPath: path.join('backend', 'module4', '.env'),
  },
  module3: {
    relPath: path.join('backend', 'module3', '.env'),
  },
};

const resolveScopedEnvFileSpecs = ({
  runtimeRoot = rootDir,
  configRoot = resolveConfigRootDir({ runtimeRoot }),
  scopes = DEFAULT_MANAGED_ENV_SCOPES,
} = {}) => {
  const seen = new Set();
  const out = [];
  const normalizedScopes = Array.isArray(scopes) && scopes.length > 0
    ? scopes
    : DEFAULT_MANAGED_ENV_SCOPES;

  const appendRoot = (baseDir) => {
    if (!baseDir) return;
    for (const scope of normalizedScopes) {
      const spec = MANAGED_ENV_SCOPE_SPECS[scope];
      if (!spec || !spec.relPath) continue;
      const fullPath = path.resolve(baseDir, spec.relPath);
      const scopeKey = JSON.stringify([fullPath, spec.allowedKeys || null]);
      if (seen.has(scopeKey)) continue;
      seen.add(scopeKey);
      out.push({
        path: fullPath,
        allowedKeys: Array.isArray(spec.allowedKeys) ? [...spec.allowedKeys] : null,
        scope,
      });
    }
  };

  appendRoot(runtimeRoot);
  appendRoot(configRoot);
  return out;
};

const ensureEnvValue = (env, key, value) => {
  if (trim(env[key])) {
    return;
  }
  env[key] = value;
};

const assignManagedDataPath = (env, key, value, { force } = {}) => {
  if (force) {
    env[key] = value;
    return;
  }
  ensureEnvValue(env, key, value);
};

const buildManagedRuntimeEnv = ({ baseEnv = process.env, scopes = DEFAULT_MANAGED_ENV_SCOPES } = {}) => {
  const initialRuntimeRoot = resolveRuntimeRootDir({ baseEnv });
  const initialConfigRoot = resolveConfigRootDir({ baseEnv, runtimeRoot: initialRuntimeRoot });
  const rootScopedEnvValues = {};
  for (const envSpec of resolveScopedEnvFileSpecs({
    runtimeRoot: initialRuntimeRoot,
    configRoot: initialConfigRoot,
    scopes: ['backend'],
  })) {
    Object.assign(rootScopedEnvValues, parseEnvFile(envSpec.path, { allowedKeys: envSpec.allowedKeys }));
  }
  const seededBaseEnv = { ...rootScopedEnvValues, ...baseEnv };
  const runtimeRoot = resolveRuntimeRootDir({ baseEnv: seededBaseEnv });
  const configRoot = resolveConfigRootDir({ baseEnv: seededBaseEnv, runtimeRoot });
  const dataRoot = resolveDataRootDir({ baseEnv: seededBaseEnv, runtimeRoot });

  const envFileValues = {};
  for (const envSpec of resolveScopedEnvFileSpecs({ runtimeRoot, configRoot, scopes })) {
    Object.assign(envFileValues, parseEnvFile(envSpec.path, { allowedKeys: envSpec.allowedKeys }));
  }
  const env = { ...envFileValues, ...baseEnv };

  env.SMART_DOC_FLOW_RUNTIME_ROOT = runtimeRoot;
  env.SMART_DOC_FLOW_CONFIG_ROOT = configRoot;
  env.SMART_DOC_FLOW_DATA_ROOT = dataRoot;
  env.SMART_DOC_FLOW_GATEWAY_ENV_FILE = path.join(configRoot, 'backend', '.env');
  env.MODULE2_ENV_FILE = path.join(configRoot, 'backend', 'module2', '.env');
  env.MODULE3_ENV_FILE = path.join(configRoot, 'backend', 'module3', '.env');
  env.SMART_DOC_FLOW_MODULE4_ENV_FILE = path.join(configRoot, 'backend', 'module4', '.env');

  const forceManagedDataPaths = path.resolve(dataRoot) !== path.resolve(runtimeRoot);

  ensureEnvValue(env, 'GATEWAY_FRONTEND_DIST_DIR', path.join(runtimeRoot, 'frontend', 'dist'));
  assignManagedDataPath(env, 'AUTH_USERS_FILE', path.join(dataRoot, 'auth', 'users.json'), {
    force: forceManagedDataPaths,
  });
  assignManagedDataPath(env, 'MODULE2_ARTIFACT_ROOT_DIR', path.join(dataRoot, 'module2', 'artifacts'), {
    force: forceManagedDataPaths,
  });
  assignManagedDataPath(env, 'MODULE2_MINERU_CACHE_DIR', path.join(dataRoot, 'module2', 'cache', 'mineru'), {
    force: forceManagedDataPaths,
  });
  assignManagedDataPath(env, 'MODULE2_GEMINI_CACHE_DIR', path.join(dataRoot, 'module2', 'cache', 'gemini'), {
    force: forceManagedDataPaths,
  });
  assignManagedDataPath(env, 'MODULE2_MINERU_WORK_ROOT_DIR', path.join(dataRoot, 'module2', 'work', 'mineru'), {
    force: forceManagedDataPaths,
  });
  assignManagedDataPath(
    env,
    'MODULE2_EXTRACT_JOB_STATE_DIR',
    path.join(dataRoot, 'module2', 'runlogs', 'extraction_jobs'),
    { force: forceManagedDataPaths },
  );
  assignManagedDataPath(
    env,
    'MODULE2_LLM_DEBUG_DIR',
    path.join(dataRoot, 'module2', 'runlogs', 'module2-llm-debug'),
    { force: forceManagedDataPaths },
  );

  const bundledMineruRuntimeModelsDir = path.join(
    runtimeRoot,
    'backend',
    'module2',
    '.cache',
    'mineru_runtime_models',
  );
  assignManagedDataPath(
    env,
    'MODULE2_MINERU_RUNTIME_MODELS_DIR',
    fs.existsSync(bundledMineruRuntimeModelsDir)
      ? bundledMineruRuntimeModelsDir
      : path.join(dataRoot, 'module2', 'cache', 'mineru_runtime_models'),
    { force: forceManagedDataPaths },
  );
  assignManagedDataPath(
    env,
    'MODULE4_GRAPHRAG_WORKSPACES_ROOT',
    path.join(dataRoot, 'module4', 'workspaces'),
    { force: forceManagedDataPaths },
  );
  ensureEnvValue(
    env,
    'MODULE4_GRAPHRAG_PROMPTS_ROOT',
    path.join(runtimeRoot, 'backend', 'module4', 'assets', 'prompts'),
  );

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
  // Uvicorn's Click-based CLI on Windows may expand wildcard option values
  // like `artifacts/*` into a long argv list, which then breaks startup.
  // Keeping reload enabled but skipping exclude globs is the most stable path.
  if (process.platform === 'win32') {
    return args;
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
  buildManagedRuntimeEnv,
  buildNodeRuntimeEnv,
  buildPythonRuntimeEnv,
  buildReloadArgs,
  DEFAULT_MANAGED_ENV_SCOPES,
  defaultPythonExec,
  detectVenvRootFromPythonExec,
  formatCommand,
  MANAGED_ENV_SCOPE_SPECS,
  nodeExec,
  parseEnvFile,
  reloadEnabled,
  resolveConfigRootDir,
  resolvePythonExec,
  resolveRuntimeRootDir,
  resolveDataRootDir,
  resolveScopedEnvFileSpecs,
  rootDir,
  sourceRootDir,
  venvBinDir,
  venvPythonPath,
};
