const { buildBackendServices, runManagedServices } = require('./backend-service-runner.cjs');

if (
  process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE == null
  || process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE === ''
) {
  process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE = 'auto';
}

runManagedServices({
  label: 'start-backend-fastapi',
  services: buildBackendServices({
    label: 'start-backend-fastapi',
    scriptPrefix: 'start',
    defaultModule2Enabled: false,
    defaultModule4Enabled: false,
  }),
  watchParentPid: true,
});
