const { buildBackendServices, runManagedServices } = require('./backend-service-runner.cjs');

runManagedServices({
  label: 'dev-backend',
  services: buildBackendServices({
    label: 'dev-backend',
    scriptPrefix: 'dev',
    defaultModule2Enabled: true,
    defaultModule4Enabled: true,
  }),
});
