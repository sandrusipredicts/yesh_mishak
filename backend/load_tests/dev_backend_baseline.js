import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";
import { Counter, Rate, Trend } from "k6/metrics";

const scenarioName = (__ENV.SCENARIO || "public-read").toLowerCase();
const baseUrl = (__ENV.BASE_URL || "").replace(/\/+$/, "");
const expectedDevHost = (__ENV.EXPECTED_DEV_HOST || "").trim().toLowerCase();
const productionHosts = new Set(
  (__ENV.PRODUCTION_BACKEND_HOSTS || "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean)
);
const testRunId = (__ENV.TEST_RUN_ID || "").trim();
const requestTimeout = __ENV.REQUEST_TIMEOUT || "10s";
const runDuration = __ENV.RUN_DURATION || "60s";
const pressureDuration = __ENV.PRESSURE_DURATION || "20s";
const testEmail = __ENV.STAGING_TEST_EMAIL || "";
const testPassword = __ENV.STAGING_TEST_PASSWORD || "";
const testIdentityLabel = "synthetic_dev_test_identity";

const supportedScenarios = new Set([
  "public-read",
  "authenticated-read",
  "controlled-write",
  "invalid-auth",
  "connection-pressure",
]);

const latency = {
  root: new Trend("latency_root", true),
  fields_unbounded: new Trend("latency_fields_unbounded", true),
  fields_bounded: new Trend("latency_fields_bounded", true),
  fields_empty: new Trend("latency_fields_empty", true),
  games_active: new Trend("latency_games_active", true),
  games_upcoming: new Trend("latency_games_upcoming", true),
  login: new Trend("latency_login", true),
  games_me: new Trend("latency_games_me", true),
  notifications_unread: new Trend("latency_notifications_unread", true),
  notification_preferences: new Trend("latency_notification_preferences", true),
  push_token_save: new Trend("latency_push_token_save", true),
  push_token_delete: new Trend("latency_push_token_delete", true),
  invalid_auth: new Trend("latency_invalid_auth", true),
  pressure_fields: new Trend("latency_pressure_fields", true),
};

const unexpectedErrorRate = new Rate("unexpected_error_rate");
const unexpected5xx = new Counter("unexpected_5xx_count");
const timeoutCount = new Counter("timeout_count");
const httpStatusCount = new Counter("http_status_count");
const cleanupFailureCount = new Counter("cleanup_failure_count");

function assertSafeConfiguration() {
  if (!supportedScenarios.has(scenarioName)) {
    fail(`Unsupported SCENARIO '${scenarioName}'.`);
  }
  if (!baseUrl || !expectedDevHost || !testRunId) {
    fail("BASE_URL, EXPECTED_DEV_HOST, and TEST_RUN_ID are required.");
  }

  const parsed = /^(https?):\/\/([^/:?#]+)(?::\d+)?(?:[/?#]|$)/i.exec(baseUrl);
  if (!parsed) {
    fail("BASE_URL must be a valid URL.");
  }

  const protocol = parsed[1].toLowerCase();
  const hostname = parsed[2].toLowerCase();
  if (protocol !== "https") {
    fail("Only HTTPS dev targets are permitted.");
  }
  if (hostname !== expectedDevHost) {
    fail(`BASE_URL host '${hostname}' does not match EXPECTED_DEV_HOST.`);
  }
  if (productionHosts.has(hostname)) {
    fail("Refusing to run against a production backend host.");
  }
  if (!hostname.includes("dev") && !hostname.includes("staging")) {
    fail("Target hostname must visibly identify a dev or staging environment.");
  }

  if (
    ["authenticated-read", "controlled-write"].includes(scenarioName) &&
    (!testEmail || !testPassword)
  ) {
    fail(`Synthetic credentials are required for ${scenarioName}.`);
  }
}

assertSafeConfiguration();

function buildScenario() {
  if (scenarioName === "public-read" || scenarioName === "authenticated-read") {
    return {
      executor: "constant-arrival-rate",
      rate: 1,
      timeUnit: "3s",
      duration: runDuration,
      preAllocatedVUs: 2,
      maxVUs: 4,
    };
  }
  if (scenarioName === "controlled-write") {
    return {
      executor: "constant-arrival-rate",
      rate: 1,
      timeUnit: "5s",
      duration: runDuration,
      preAllocatedVUs: 1,
      maxVUs: 2,
    };
  }
  if (scenarioName === "invalid-auth") {
    return {
      executor: "shared-iterations",
      vus: 3,
      iterations: 12,
      maxDuration: "30s",
    };
  }
  return {
    executor: "constant-vus",
    vus: 10,
    duration: pressureDuration,
  };
}

const thresholds = {
  unexpected_error_rate: ["rate<0.01"],
  unexpected_5xx_count: ["count==0"],
  timeout_count: ["count==0"],
};

export const options = {
  scenarios: {
    [scenarioName]: buildScenario(),
  },
  thresholds,
  summaryTrendStats: ["avg", "min", "p(50)", "p(95)", "p(99)", "max"],
  systemTags: ["status", "method", "url", "name", "scenario", "expected_response"],
  discardResponseBodies: false,
};

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    "X-Performance-Test-Run": testRunId,
  };
}

function requestHeaders() {
  return {
    "X-Performance-Test-Run": testRunId,
  };
}

function isTimeout(response) {
  return (
    response.status === 0 &&
    /timeout|deadline/i.test(`${response.error || ""} ${response.error_code || ""}`)
  );
}

function record(endpoint, response, expectedStatuses, contractCheck) {
  latency[endpoint].add(response.timings.duration);
  httpStatusCount.add(1, {
    endpoint,
    status: String(response.status),
  });

  const expected = expectedStatuses.includes(response.status);
  unexpectedErrorRate.add(!expected);
  if (response.status >= 500) {
    unexpected5xx.add(1);
  }
  if (isTimeout(response)) {
    timeoutCount.add(1);
  }

  const checks = {
    [`${endpoint}: expected HTTP status`]: () => expected,
  };
  if (contractCheck) {
    checks[`${endpoint}: response contract`] = () => contractCheck(response);
  }
  check(response, checks);
  return response;
}

function request(method, endpoint, path, expectedStatuses, body, headers, contractCheck) {
  const params = {
    headers: headers || requestHeaders(),
    timeout: requestTimeout,
    tags: {
      endpoint,
      test_run_id: testRunId,
      workload: scenarioName,
      test_identity: testIdentityLabel,
      name: `${method} ${path.split("?")[0]}`,
    },
    responseCallback: http.expectedStatuses(...expectedStatuses),
  };

  let response;
  if (method === "GET") {
    response = http.get(`${baseUrl}${path}`, params);
  } else if (method === "POST") {
    response = http.post(`${baseUrl}${path}`, JSON.stringify(body), params);
  } else if (method === "DELETE") {
    response = http.del(`${baseUrl}${path}`, JSON.stringify(body), params);
  } else {
    fail(`Unsupported method '${method}'.`);
  }

  return record(endpoint, response, expectedStatuses, contractCheck);
}

function parseJson(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

function login({ record: shouldRecord = true } = {}) {
  const credentials = { username: testEmail, password: testPassword };
  const headers = {
    "Content-Type": "application/json",
    "X-Performance-Test-Run": testRunId,
  };
  const contract = (res) => {
    const body = parseJson(res);
    return Boolean(body && body.access_token && body.user && body.user.id);
  };

  const response = shouldRecord
    ? request("POST", "login", "/auth/login", [200], credentials, headers, contract)
    : http.post(`${baseUrl}/auth/login`, JSON.stringify(credentials), {
        headers,
        timeout: requestTimeout,
        responseCallback: http.expectedStatuses(200),
        tags: {
          endpoint: "login_preflight",
          test_run_id: testRunId,
          workload: scenarioName,
          test_identity: testIdentityLabel,
        },
      });

  const body = parseJson(response);
  if (response.status !== 200 || !body || !body.access_token) {
    // Never interpolate the response body or credentials into this message -
    // it is printed to the console log that ships with the artifacts.
    fail("Synthetic dev account login failed.");
  }
  return body.access_token;
}

// Access tokens are deliberately NEVER returned from setup(). k6 serializes the
// setup() return value into the --summary-export file as "setup_data", so any
// credential placed there is written to disk and uploaded with the artifacts.
// Instead each VU authenticates on demand and caches the token in module scope,
// which k6 keeps per-VU in memory and never serializes.
let cachedToken = null;

function currentToken() {
  if (cachedToken === null) {
    cachedToken = login({ record: true });
  }
  return cachedToken;
}

// Derived from the run ID rather than passed through setup_data, so no scenario
// depends on setup() returning anything.
function syntheticPushToken() {
  return `perf-baseline-${testRunId}`;
}

export function setup() {
  // Preflight only: prove the synthetic dev account can authenticate so the run
  // fails fast on bad credentials. The token is discarded, not returned, and
  // this probe is excluded from the reported login latency.
  if (scenarioName === "authenticated-read" || scenarioName === "controlled-write") {
    login({ record: false });
  }
  // Must stay free of credentials - this value becomes setup_data on disk.
  return {};
}

function publicRead() {
  request("GET", "root", "/", [200], null, requestHeaders(), (res) => {
    const body = parseJson(res);
    return body && body.status === "ok";
  });
  request("GET", "fields_unbounded", "/fields/", [200], null, requestHeaders(), (res) =>
    Array.isArray(parseJson(res))
  );
  request(
    "GET",
    "fields_bounded",
    "/fields/?north=32.15&south=31.95&east=34.85&west=34.70",
    [200],
    null,
    requestHeaders(),
    (res) => Array.isArray(parseJson(res))
  );
  request(
    "GET",
    "fields_empty",
    "/fields/?north=1.1&south=1.0&east=1.1&west=1.0",
    [200],
    null,
    requestHeaders(),
    (res) => Array.isArray(parseJson(res)) && parseJson(res).length === 0
  );
  request("GET", "games_active", "/games/active", [200], null, requestHeaders(), (res) =>
    Array.isArray(parseJson(res))
  );
  request(
    "GET",
    "games_upcoming",
    "/games/upcoming",
    [200],
    null,
    requestHeaders(),
    (res) => Array.isArray(parseJson(res))
  );
}

function authenticatedRead() {
  const headers = authHeaders(currentToken());
  request("GET", "games_me", "/games/me", [200], null, headers, (res) => {
    const body = parseJson(res);
    return Boolean(
      body &&
        Array.isArray(body.created) &&
        Array.isArray(body.joined) &&
        Array.isArray(body.past_created) &&
        Array.isArray(body.past_joined)
    );
  });
  request(
    "GET",
    "notifications_unread",
    "/notifications/unread-count",
    [200],
    null,
    headers,
    (res) => Number.isInteger(parseJson(res)?.unread_count)
  );
  request(
    "GET",
    "notification_preferences",
    "/notifications/preferences",
    [200],
    null,
    headers,
    (res) => Array.isArray(parseJson(res))
  );
}

function controlledWrite() {
  const headers = authHeaders(currentToken());
  const pushToken = syntheticPushToken();
  const payload = {
    token: pushToken,
    platform: "web",
    installation_id: `perf-${testRunId}`,
  };

  request(
    "POST",
    "push_token_save",
    "/notifications/push-token",
    [200],
    payload,
    headers,
    (res) => parseJson(res)?.message === "Push token saved"
  );
  request(
    "DELETE",
    "push_token_delete",
    "/notifications/push-token",
    [200],
    { token: pushToken },
    headers,
    (res) => parseJson(res)?.message === "Push token deleted"
  );
}

function invalidAuth() {
  request(
    "GET",
    "invalid_auth",
    "/games/me",
    [401],
    null,
    authHeaders("invalid.synthetic.performance.token"),
    (res) => {
      const body = parseJson(res);
      return body && body.error === true && body.code === "AUTH_REQUIRED";
    }
  );
}

function connectionPressure() {
  request(
    "GET",
    "pressure_fields",
    "/fields/?north=32.15&south=31.95&east=34.85&west=34.70",
    [200],
    null,
    requestHeaders(),
    (res) => Array.isArray(parseJson(res))
  );
  sleep(1);
}

export default function () {
  if (scenarioName === "public-read") {
    publicRead();
  } else if (scenarioName === "authenticated-read") {
    authenticatedRead();
  } else if (scenarioName === "controlled-write") {
    controlledWrite();
  } else if (scenarioName === "invalid-auth") {
    invalidAuth();
  } else {
    connectionPressure();
  }
}

export function teardown() {
  if (scenarioName !== "controlled-write") {
    return;
  }

  // teardown runs in its own runtime, so this authenticates once more rather
  // than receiving a token through setup_data.
  const response = http.del(
    `${baseUrl}/notifications/push-token`,
    JSON.stringify({ token: syntheticPushToken() }),
    {
      headers: authHeaders(currentToken()),
      timeout: requestTimeout,
      responseCallback: http.expectedStatuses(200),
      tags: {
        endpoint: "push_token_cleanup",
        test_run_id: testRunId,
        workload: scenarioName,
        test_identity: testIdentityLabel,
        name: "DELETE /notifications/push-token cleanup",
      },
    }
  );

  if (response.status !== 200) {
    cleanupFailureCount.add(1);
  }
}
