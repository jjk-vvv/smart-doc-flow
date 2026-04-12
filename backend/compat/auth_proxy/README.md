# Auth Compatibility Proxy

This directory is the canonical compatibility-layer location for the legacy
Node.js auth/chat proxy.

Current production/dev runtime still executes from `backend/auth/` for
backward compatibility. During the next migration step, startup scripts will
switch to `backend/compat/auth_proxy/` as the primary path.

