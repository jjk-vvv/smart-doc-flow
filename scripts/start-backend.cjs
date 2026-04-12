const { buildBackendServices, runManagedServices } = require('./backend-service-runner.cjs');

runManagedServices({
  label: 'start-backend',
  services: buildBackendServices({
    label: 'start-backend',
    scriptPrefix: 'start',
    defaultModule2Enabled: true,
    defaultModule4Enabled: true,
  }),
  watchParentPid: true,
});
