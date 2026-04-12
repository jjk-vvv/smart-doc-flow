const { buildBackendServices, runManagedServices } = require('./backend-service-runner.cjs');

if (
  process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE == null
  || process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE === ''
) {
  process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE = 'managed';
}

runManagedServices({
  label: 'dev-backend-fastapi',
  services: buildBackendServices({
    label: 'dev-backend-fastapi',
    scriptPrefix: 'dev',
    defaultModule2Enabled: false,
    defaultModule4Enabled: false,
  }),
});
