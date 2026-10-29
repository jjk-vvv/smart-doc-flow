const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const baseConfigPath = path.join(rootDir, 'electron-builder.json');
const outputConfigPath = path.join(rootDir, 'electron-builder.generated.json');

const args = new Set(process.argv.slice(2).map((item) => String(item || '').trim()));
const envFlag = String(process.env.SMART_DOC_FLOW_DESKTOP_BUNDLE_PYTHON || '').trim().toLowerCase();
const skipPython = args.has('--skip-python') || ['0', 'false', 'no', 'off'].includes(envFlag);

const PYTHON_FILTER = [
  '**/*',
  '!**/__pycache__/**',
  '!**/*.pyc',
  '!**/*.pyo',
  '!**/site-packages/pip/**',
  '!**/site-packages/pip-*',
  '!**/site-packages/setuptools/**',
  '!**/site-packages/setuptools-*',
  '!**/site-packages/pkg_resources/**',
  '!**/site-packages/**/tests/**',
  '!**/site-packages/**/test/**',
  '!**/*.pdb',
  '!**/*.lib',
  '!**/*.a',
];

const readBaseConfig = () => {
  try {
    return JSON.parse(fs.readFileSync(baseConfigPath, 'utf8'));
  } catch (error) {
    throw new Error(`Unable to read electron-builder.json: ${error instanceof Error ? error.message : error}`);
  }
};

const buildConfig = () => {
  const base = readBaseConfig();
  const resources = (Array.isArray(base.extraResources) ? base.extraResources : []).filter(
    (entry) => entry && entry.from !== '.venv',
  );

  if (!skipPython) {
    resources.push({
      from: '.venv',
      to: 'app-runtime/.venv',
      filter: PYTHON_FILTER,
    });
  }

  return { ...base, extraResources: resources };
};

const main = () => {
  const config = buildConfig();
  fs.writeFileSync(outputConfigPath, `${JSON.stringify(config, null, 2)}\n`, 'utf8');
  const pythonEntry = config.extraResources.find((entry) => entry.from === '.venv');
  console.log(`[desktop:config] wrote ${path.basename(outputConfigPath)}`);
  console.log(`[desktop:config] python runtime bundled: ${pythonEntry ? 'yes (.venv -> app-runtime/.venv)' : 'no (shell-only package)'}`);
  if (!pythonEntry) {
    console.log('[desktop:config] shell-only packages require an existing Python runtime (SMART_DOC_FLOW_ELECTRON_PYTHON or .venv) on the target machine.');
  }
};

main();
