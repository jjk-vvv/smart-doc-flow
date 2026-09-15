# Vite Public-Domain Host Allowlist Design

## Context

The FRP TCP tunnel forwards `154.9.26.119:56797` to the local Vite server on
`127.0.0.1:3000`. DNS resolves `www.smart-doc-flow.cn` to the FRP server.
Requests using the IP address or `Host: localhost` return HTTP 200, while the
same tunnel request using `Host: www.smart-doc-flow.cn` returns Vite's HTTP 403
host-denial response. This isolates the failure to Vite host validation.

## Requirements

- Allow exactly `www.smart-doc-flow.cn` through Vite's host validation.
- Preserve access through localhost and IP addresses.
- Do not enable a wildcard/all-host policy.
- Keep development and preview behavior consistent.
- Do not change DNS, FRP routing, backend routing, or application behavior.

## Considered Approaches

1. Set `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` before every launch. This avoids
   a source change but is easy to omit during later restarts.
2. Add an explicit domain to `server.allowedHosts` only. This fixes the current
   development server but leaves `vite preview` inconsistent.
3. Define one explicit allowlist and reuse it for `server.allowedHosts` and
   `preview.allowedHosts`. This is the recommended approach because it is
   persistent, narrow, and consistent.

## Design

Add a single `allowedHosts` constant inside the Vite configuration factory with
the value `['www.smart-doc-flow.cn']`. Pass it to both the `server` and `preview`
configuration objects. Vite remains responsible for parsing the request Host
header and returning its standard error response for every other untrusted
hostname.

## Verification

1. Build the frontend to verify that the Vite configuration remains valid.
2. Restart the development server.
3. Confirm local access returns HTTP 200.
4. Confirm the FRP IP endpoint returns HTTP 200.
5. Confirm `http://www.smart-doc-flow.cn:56797/` returns HTTP 200.
6. Send an unrelated Host header and confirm Vite still returns HTTP 403.

## Implementation Plan

1. Update `frontend/vite.config.ts` with the shared explicit allowlist.
2. Run the frontend build.
3. Restart the existing development process without changing FRP or PostgreSQL.
4. Execute local and public Host-header regression tests.
