const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const { rootDir, sourceRootDir } = require('./python-service-utils.cjs');

const runtimeRoot = rootDir;
const packagedOutputDir = process.env.DESKTOP_DOCTOR_OUTPUT_DIR || 'dist-electron';
const packagedOutputRoot = path.join(sourceRootDir, packagedOutputDir, 'win-unpacked');
const packagedRuntimeRoot = path.join(packagedOutputRoot, 'resources', 'app-runtime');

const exists = (targetPath) => fs.existsSync(targetPath);

const statKind = (targetPath) => {
  try {
    const stats = fs.statSync(targetPath);
    if (stats.isDirectory()) return 'dir';
    if (stats.isFile()) return 'file';
    return 'other';
  } catch {
    return 'missing';
  }
};

const checkItem = (label, targetPath, expectedKind = 'exists') => {
  const kind = statKind(targetPath);
  const ok = expectedKind === 'exists' ? kind !== 'missing' : kind === expectedKind;
  return {
    label,
    path: targetPath,
    expected: expectedKind,
    actual: kind,
    ok,
  };
};

const checkMissing = (label, targetPath) => {
  const actual = statKind(targetPath);
  return {
    label,
    path: targetPath,
    expected: 'missing',
    actual,
    ok: actual === 'missing',
  };
};

const checkValue = (label, targetPath, expected, actual, ok) => ({
  label,
  path: targetPath,
  expected,
  actual,
  ok,
});

const firstExistingPath = (...candidates) => {
  for (const candidate of candidates.filter(Boolean)) {
    if (exists(candidate)) {
      return candidate;
    }
  }
  return candidates.find(Boolean) || '';
};

const runPythonImportCheck = (pythonPath, modules) => {
  if (!exists(pythonPath) || statKind(pythonPath) !== 'file') {
    return {
      ok: false,
      expected: `python import ${modules.join(',')}`,
      actual: 'python executable missing',
    };
  }

  const script = [
    'import importlib, sys',
    `mods = ${JSON.stringify(modules)}`,
    'failed = []',
    'for name in mods:',
    '    try:',
    '        importlib.import_module(name)',
    '    except Exception as exc:',
    "        failed.append(f'{name}:{type(exc).__name__}:{exc}')",
    'if failed:',
    "    print('FAILED:' + ' | '.join(failed))",
    '    sys.exit(1)',
    "print('OK')",
  ].join('\n');

  const result = spawnSync(pythonPath, ['-c', script], {
    encoding: 'utf8',
    shell: false,
    windowsHide: true,
  });
  const stdout = String(result.stdout || '').trim();
  const stderr = String(result.stderr || '').trim();
  const detail = [stdout, stderr].filter(Boolean).join(' | ') || `exit=${result.status}`;
  return {
    ok: result.status === 0,
    expected: `python import ${modules.join(',')}`,
    actual: detail,
  };
};

const countMatchingEntries = (rootPath, { dirNames = [], fileNames = [], fileExtensions = [] } = {}) => {
  if (!exists(rootPath)) {
    return { total: 0, samples: [] };
  }

  const dirNameSet = new Set(dirNames);
  const fileNameSet = new Set(fileNames);
  const extensionSet = new Set(fileExtensions.map((item) => String(item || '').toLowerCase()));
  const samples = [];
  let total = 0;
  const stack = [rootPath];

  while (stack.length > 0) {
    const currentPath = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(currentPath, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = path.join(currentPath, entry.name);
      if (entry.isDirectory()) {
        if (dirNameSet.has(entry.name)) {
          total += 1;
          if (samples.length < 20) {
            samples.push(fullPath);
          }
          continue;
        }
        stack.push(fullPath);
        continue;
      }

      if (!entry.isFile()) {
        continue;
      }

      const lowerName = entry.name.toLowerCase();
      const matchesName = fileNameSet.has(entry.name);
      const matchesExtension = extensionSet.has(path.extname(lowerName));
      if (matchesName || matchesExtension) {
        total += 1;
        if (samples.length < 20) {
          samples.push(fullPath);
        }
      }
    }
  }

  return { total, samples };
};

const readJson = (targetPath) => {
  try {
    return JSON.parse(fs.readFileSync(targetPath, 'utf8'));
  } catch {
    return null;
  }
};

const packageJsonPath = path.join(sourceRootDir, 'package.json');
const packageJson = readJson(packageJsonPath);
const packageAuthor = typeof packageJson?.author === 'string' ? packageJson.author.trim() : '';
const sourceUnifiedPythonPath = firstExistingPath(
  path.join(sourceRootDir, '.venv', 'Scripts', 'python.exe'),
  path.join(sourceRootDir, '.venv-module2-py311', 'Scripts', 'python.exe'),
);
const sourceGraphPythonPath = firstExistingPath(
  path.join(sourceRootDir, '.venv', 'Scripts', 'python.exe'),
  path.join(sourceRootDir, '.venv-module4-py311', 'Scripts', 'python.exe'),
  path.join(sourceRootDir, '.venv-module2-py311', 'Scripts', 'python.exe'),
);

const sourceChecks = [
  checkItem('electron_main', path.join(sourceRootDir, 'electron', 'main.cjs'), 'file'),
  checkItem('electron_builder', path.join(sourceRootDir, 'electron-builder.json'), 'file'),
  checkItem('electron_icon_png', path.join(sourceRootDir, 'electron', 'icon.png'), 'file'),
  checkItem('electron_icon_ico', path.join(sourceRootDir, 'electron', 'icon.ico'), 'file'),
  checkItem('frontend_dist_index', path.join(sourceRootDir, 'frontend', 'dist', 'index.html'), 'file'),
  checkItem('backend_entry', path.join(sourceRootDir, 'backend', 'app', 'main.py'), 'file'),
  checkItem('start_backend_fastapi', path.join(sourceRootDir, 'scripts', 'start-backend-fastapi.cjs'), 'file'),
  checkItem('desktop_local_launcher', path.join(sourceRootDir, 'scripts', 'start-electron-local.cjs'), 'file'),
  checkItem('desktop_dev_launcher', path.join(sourceRootDir, 'scripts', 'start-electron-dev.cjs'), 'file'),
  checkItem('backend_python', sourceUnifiedPythonPath, 'file'),
  checkItem('graphrag_python', sourceGraphPythonPath, 'file'),
  checkValue('package_author', packageJsonPath, 'non-empty string', packageAuthor || 'missing', Boolean(packageAuthor)),
  (() => {
    const pythonPath = sourceUnifiedPythonPath;
    const probe = runPythonImportCheck(
      pythonPath,
      ['asyncpg', 'openpyxl', 'docx', 'pypdf', 'sqlalchemy', 'pandas', 'graphrag', 'neo4j', 'pyarrow'],
    );
    return checkValue('backend_python_imports', pythonPath, probe.expected, probe.actual, probe.ok);
  })(),
];

const packagedChecks = exists(packagedOutputRoot)
  ? (() => {
      const packagedBackendRoot = path.join(packagedRuntimeRoot, 'backend');
      const packagedUnifiedPythonPath = firstExistingPath(
        path.join(packagedRuntimeRoot, '.venv', 'Scripts', 'python.exe'),
        path.join(packagedRuntimeRoot, '.venv-module2-py311', 'Scripts', 'python.exe'),
      );
      const packagedGraphPythonPath = firstExistingPath(
        path.join(packagedRuntimeRoot, '.venv', 'Scripts', 'python.exe'),
        path.join(packagedRuntimeRoot, '.venv-module4-py311', 'Scripts', 'python.exe'),
        path.join(packagedRuntimeRoot, '.venv-module2-py311', 'Scripts', 'python.exe'),
      );
      const unexpectedBackendEntries = countMatchingEntries(packagedBackendRoot, {
        dirNames: ['__pycache__', '.runlogs', '.runtime', '.mcache', '.pytest_cache', 'tests', 'trace_rois'],
        fileNames: ['.env', '.env.local', '.env.example', 'auth.runtime.log', 'package-lock.json', 'users.json'],
        fileExtensions: ['.pyc', '.pyo'],
      });

      return [
        checkItem('packaged_output_root', packagedOutputRoot, 'dir'),
        checkItem('packaged_runtime_root', packagedRuntimeRoot, 'dir'),
        checkItem('packaged_backend_entry', path.join(packagedRuntimeRoot, 'backend', 'app', 'main.py'), 'file'),
        checkItem('packaged_frontend_dist_index', path.join(packagedRuntimeRoot, 'frontend', 'dist', 'index.html'), 'file'),
        checkItem(
          'packaged_script_start_backend_fastapi',
          path.join(packagedRuntimeRoot, 'scripts', 'start-backend-fastapi.cjs'),
          'file',
        ),
        checkItem('packaged_backend_python', packagedUnifiedPythonPath, 'file'),
        checkItem('packaged_graphrag_python', packagedGraphPythonPath, 'file'),
        checkMissing(
          'packaged_module2_artifacts_absent',
          path.join(packagedRuntimeRoot, 'backend', 'app', 'modules', 'module2', 'artifacts'),
        ),
        checkMissing(
          'packaged_module2_workspaces_absent',
          path.join(packagedRuntimeRoot, 'backend', 'app', 'modules', 'module2', 'workspaces'),
        ),
        checkMissing(
          'packaged_module4_workspaces_absent',
          path.join(packagedRuntimeRoot, 'backend', 'app', 'modules', 'module4', 'workspaces'),
        ),
        checkMissing(
          'packaged_module2_tests_absent',
          path.join(packagedRuntimeRoot, 'backend', 'app', 'modules', 'module2', 'tests'),
        ),
        checkMissing('packaged_backend_env_absent', path.join(packagedRuntimeRoot, 'backend', '.env')),
        checkMissing(
          'packaged_module2_env_absent',
          path.join(packagedRuntimeRoot, 'backend', 'app', 'modules', 'module2', '.env'),
        ),
        checkMissing(
          'packaged_module4_env_absent',
          path.join(packagedRuntimeRoot, 'backend', 'app', 'modules', 'module4', '.env'),
        ),
        checkValue(
          'packaged_backend_junk_entries_absent',
          packagedBackendRoot,
          '0 unexpected cache/test/debug entries',
          unexpectedBackendEntries.total === 0
            ? '0'
            : `${unexpectedBackendEntries.total} found; samples=${unexpectedBackendEntries.samples.join(' | ')}`,
          unexpectedBackendEntries.total === 0,
        ),
        (() => {
          const pythonPath = packagedUnifiedPythonPath;
          const probe = runPythonImportCheck(
            pythonPath,
            ['asyncpg', 'openpyxl', 'docx', 'pypdf', 'sqlalchemy', 'pandas', 'graphrag', 'neo4j', 'pyarrow'],
          );
          return checkValue('packaged_backend_python_imports', pythonPath, probe.expected, probe.actual, probe.ok);
        })(),
      ];
    })()
  : [];

const summarize = (checks) => ({
  ok: checks.every((item) => item.ok),
  total: checks.length,
  passed: checks.filter((item) => item.ok).length,
  failed: checks.filter((item) => !item.ok).length,
});

const payload = {
  ok: false,
  source_root: sourceRootDir,
  runtime_root: runtimeRoot,
  packaged_output_dir: packagedOutputDir,
  packaged_runtime_root: packagedRuntimeRoot,
  source: {
    ...summarize(sourceChecks),
    checks: sourceChecks,
  },
  packaged: packagedChecks.length > 0
    ? {
        present: true,
        ...summarize(packagedChecks),
        checks: packagedChecks,
      }
    : {
        present: false,
        ok: true,
        total: 0,
        passed: 0,
        failed: 0,
        checks: [],
      },
};

payload.ok = Boolean(payload.source.ok) && Boolean(payload.packaged.ok);

console.log(JSON.stringify(payload, null, 2));

if (!payload.source.ok) {
  process.exit(1);
}
