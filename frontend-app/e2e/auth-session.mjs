const DEFAULT_AUTH_ACCOUNT = String(
  process.env.PLAYWRIGHT_AUTH_ACCOUNT ||
    process.env.SMART_DOC_FLOW_E2E_ACCOUNT ||
    "regression.local+ui@example.com",
).trim();

const DEFAULT_AUTH_PASSWORD = String(
  process.env.PLAYWRIGHT_AUTH_PASSWORD ||
    process.env.SMART_DOC_FLOW_E2E_PASSWORD ||
    "Regression@123",
).trim();

function parseJsonSafe(rawText = "") {
  const text = String(rawText || "").trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function normalizeBase(value = "") {
  return String(value || "").trim().replace(/\/+$/, "");
}

function buildAuthBaseCandidates(appUrl) {
  const appOrigin = new URL(String(appUrl || "").trim()).origin;
  const appLocation = new URL(appOrigin);
  const candidates = [];
  const push = (value = "") => {
    const normalized = normalizeBase(value);
    if (normalized && !candidates.includes(normalized)) {
      candidates.push(normalized);
    }
  };

  push(process.env.PLAYWRIGHT_AUTH_API_BASE || process.env.SMART_DOC_FLOW_AUTH_API_BASE || "");
  push(appOrigin);

  return candidates;
}

async function resolveAuthBase(context, appUrl) {
  const candidates = buildAuthBaseCandidates(appUrl);
  let firstHealthyBase = "";

  for (const candidate of candidates) {
    try {
      const response = await context.request.get(`${candidate}/api/auth/health`);
      if (!response.ok()) continue;
      const payload = parseJsonSafe(await response.text()) || {};
      if (!firstHealthyBase) {
        firstHealthyBase = candidate;
      }
      if (payload.databaseConnected || payload.ok) {
        return candidate;
      }
    } catch {
      // Keep probing until we find a reachable auth backend.
    }
  }

  return firstHealthyBase || candidates[0] || new URL(String(appUrl || "").trim()).origin;
}

export function buildProtectedTabUrl(appUrl, tab = "") {
  const url = new URL(String(appUrl || "").trim());
  if (tab) {
    url.searchParams.set("tab", String(tab).trim());
  }
  return url.toString();
}

async function readPageMountState(page) {
  return await page
    .evaluate(() => {
      const root = document.getElementById("root");
      const main = document.querySelector("main");
      const bodyText = String(document.body?.innerText || "").trim();
      return {
        href: window.location.href,
        readyState: document.readyState,
        hasRoot: Boolean(root),
        rootChildCount: Number(root?.childElementCount || 0),
        hasMain: Boolean(main),
        bodyTextLength: bodyText.length,
      };
    })
    .catch(() => ({
      href: "",
      readyState: "",
      hasRoot: false,
      rootChildCount: 0,
      hasMain: false,
      bodyTextLength: 0,
    }));
}

function pageLooksMounted(state) {
  if (!state || typeof state !== "object") return false;
  if (Boolean(state.hasMain)) return true;
  if (Number(state.rootChildCount || 0) > 0) return true;
  return Number(state.bodyTextLength || 0) > 24;
}

export async function loginForProtectedApp(context, appUrl, credentials = {}) {
  if (String(process.env.PLAYWRIGHT_SKIP_AUTH || "").trim() === "1") {
    return {
      account: "",
      loginPayload: null,
      mePayload: null,
      cookieHeader: "",
    };
  }

  const account = String(credentials.account || DEFAULT_AUTH_ACCOUNT).trim();
  const password = String(credentials.password || DEFAULT_AUTH_PASSWORD).trim();
  if (!account || !password) {
    throw new Error("playwright_login_missing_credentials");
  }

  const baseUrl = await resolveAuthBase(context, appUrl);
  const loginResponse = await context.request.post(`${baseUrl}/api/login`, {
    headers: {
      "content-type": "application/json",
    },
    data: {
      account,
      password,
    },
  });
  const loginText = await loginResponse.text();
  const loginPayload = parseJsonSafe(loginText);
  if (!loginResponse.ok()) {
    throw new Error(
      `playwright_login_failed:${loginResponse.status()}:${String(loginText || "").slice(0, 400)}`,
    );
  }

  const meResponse = await context.request.get(`${baseUrl}/api/me`);
  const meText = await meResponse.text();
  const mePayload = parseJsonSafe(meText);
  if (!meResponse.ok()) {
    throw new Error(
      `playwright_login_verify_failed:${meResponse.status()}:${String(meText || "").slice(0, 400)}`,
    );
  }
  const cookies = await context.cookies(baseUrl);
  const cookieHeader = cookies
    .map((item) => `${String(item.name || "").trim()}=${String(item.value || "").trim()}`)
    .filter(Boolean)
    .join("; ");

  return {
    account,
    loginPayload,
    mePayload,
    cookieHeader,
  };
}

export async function openProtectedTab(page, appUrl, tab, options = {}) {
  const targetUrl = buildProtectedTabUrl(appUrl, tab);
  const attempts = Math.max(1, Number(options.attempts || 3));
  const retryDelayMs = Math.max(250, Number(options.retryDelayMs || 1200));
  let lastError = null;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await page.goto(targetUrl, {
        waitUntil: options.waitUntil || "domcontentloaded",
        timeout: options.timeout || 90_000,
      });
      await page.waitForLoadState("networkidle", {
        timeout: options.networkIdleTimeout || 30_000,
      }).catch(() => {});
      const mountState = await readPageMountState(page);
      if (pageLooksMounted(mountState)) {
        return targetUrl;
      }
      lastError = new Error(
        `protected_tab_not_mounted:${String(tab || "").trim()}:${JSON.stringify(mountState)}`,
      );
    } catch (error) {
      lastError = error;
    }

    if (attempt < attempts) {
      await page.waitForTimeout(retryDelayMs * attempt).catch(() => {});
      await page.goto("about:blank", {
        waitUntil: "load",
        timeout: Math.min(15_000, Number(options.timeout || 90_000)),
      }).catch(() => {});
    }
  }

  throw lastError || new Error(`protected_tab_open_failed:${String(tab || "").trim()}`);
  return targetUrl;
}
