if (process.env.MODULE2_ENABLED == null || process.env.MODULE2_ENABLED === '') {
  process.env.MODULE2_ENABLED = '0';
}
if (
  process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE == null
  || process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE === ''
) {
  process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE = 'disabled';
}
if (
  process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE == null
  || process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE === ''
) {
  process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE = 'disabled';
}
require('./dev-all.cjs');
