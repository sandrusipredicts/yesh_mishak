import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";
import { SharedArray } from "k6/data";
import { Rate } from "k6/metrics";

// ISSUE-088 game creation load test.
//
// Safe by default:
// - Requires explicit BASE_URL.
// - Requires synthetic test JWTs via TOKENS or TOKEN_FILE.
// - Requires approved/open synthetic field ids via FIELD_IDS or FIELD_ID_FILE.
// - Refuses production-looking URLs unless ALLOW_PRODUCTION_LOAD_TEST=true.
// - Uses low default load and tags requests with issue/scenario metadata.
//
// Run one scenario at a time with SCENARIO:
// baseline, scheduled, duplicate-instant, duplicate-scheduled, validation.
// Notification fanout is observed naturally when matching notification
// preferences exist in the target test environment.

const scenarioName = (__ENV.SCENARIO || "baseline").toLowerCase();
const baseUrl = (__ENV.BASE_URL || "").replace(/\/+$/, "");
const sportType = __ENV.SPORT_TYPE || "football";
const vus = Number(__ENV.VUS || "1");
const duration = __ENV.DURATION || "1m";
const iterations = Number(__ENV.ITERATIONS || "1");
const duplicateAttempts = Number(__ENV.DUPLICATE_ATTEMPTS || "10");
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || "1");
const allowProduction = (__ENV.ALLOW_PRODUCTION_LOAD_TEST || "").toLowerCase() === "true";
const unexpectedErrorRate = new Rate("game_creation_unexpected_error_rate");
const successRate = new Rate("game_creation_success_rate");
const controlledRejectionRate = new Rate("game_creation_controlled_rejection_rate");

function splitValues(value) {
  return (value || "")
    .split(/[,\n\r]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function readValues(envValueName, envFileName) {
  const inline = splitValues(__ENV[envValueName]);
  if (inline.length > 0) {
    return inline;
  }

  const filePath = __ENV[envFileName];
  if (!filePath) {
    return [];
  }

  return splitValues(open(filePath));
}

function assertSafeConfiguration() {
  if (!baseUrl) {
    fail("BASE_URL is required. Use a local or staging URL only.");
  }

  let parsedUrl;
  try {
    parsedUrl = new URL(baseUrl);
  } catch (e) {
    // Fail closed if the URL is invalid or malformed.
    fail("Invalid BASE_URL. It must be a valid URL.");
  }

  const hostname = parsedUrl.hostname.toLowerCase();

  const localHosts = ["localhost", "127.0.0.1"];
  const prodHosts = ["yeshmishak.com", "www.yeshmishak.com"];

  const isLocal = localHosts.includes(hostname);
  const isProd = prodHosts.includes(hostname);

  // Validate parsed.hostname exactly against an explicit allowlist.
  // Using exact hostname matching instead of substring matching/includes prevents
  // potential bypasses from attacker-controlled domains containing the target domain as a substring.
  if (!isLocal && !isProd) {
    fail(`Host '${hostname}' is not in the explicit allowlist of authorized test targets.`);
  }

  // Keep safety checks intact and do not weaken any checks.
  // Production hosts are only allowed if allowProduction is explicitly set to true.
  if (isProd && !allowProduction) {
    fail(
      "Refusing to run against a production BASE_URL. Set ALLOW_PRODUCTION_LOAD_TEST=true only after explicit approval."
    );
  }
}

assertSafeConfiguration();

const tokens = new SharedArray("auth tokens", () => readValues("TOKENS", "TOKEN_FILE"));
const fieldIds = new SharedArray("field ids", () => readValues("FIELD_IDS", "FIELD_ID_FILE"));

if (tokens.length === 0) {
  fail("Provide at least one test JWT via TOKENS or TOKEN_FILE.");
}

if (fieldIds.length === 0) {
  fail("Provide at least one approved/open synthetic field id via FIELD_IDS or FIELD_ID_FILE.");
}

export const options = buildOptions();

function buildOptions() {
  const thresholds = {
    http_req_duration: ["p(95)<3000"],
    game_creation_unexpected_error_rate: ["rate<0.01"],
  };

  if (scenarioName === "duplicate-instant" || scenarioName === "duplicate-scheduled") {
    return {
      scenarios: {
        [scenarioName]: {
          executor: "shared-iterations",
          vus: duplicateAttempts,
          iterations: duplicateAttempts,
          maxDuration: "30s",
        },
      },
      thresholds,
    };
  }

  if (scenarioName === "validation") {
    return {
      scenarios: {
        validation: {
          executor: "shared-iterations",
          vus: Math.max(1, vus),
          iterations,
          maxDuration: duration,
        },
      },
      thresholds: {
        http_req_duration: ["p(95)<3000"],
      },
    };
  }

  return {
    scenarios: {
      [scenarioName]: {
        executor: "constant-vus",
        vus,
        duration,
      },
    },
    thresholds,
  };
}

function tokenForIteration() {
  return tokens[exec.scenario.iterationInTest % tokens.length];
}

function fieldForIteration() {
  if (scenarioName === "duplicate-instant" || scenarioName === "duplicate-scheduled") {
    return fieldIds[0];
  }
  return fieldIds[exec.scenario.iterationInTest % fieldIds.length];
}

function futureTimestamp(minutesFromNow) {
  return new Date(Date.now() + minutesFromNow * 60 * 1000).toISOString();
}

function headers(token) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

function postGame(payload, expectedStatuses) {
  const response = http.post(`${baseUrl}/games/`, JSON.stringify(payload), {
    headers: headers(tokenForIteration()),
    tags: {
      endpoint: "POST /games/",
      issue: "ISSUE-088",
      scenario: scenarioName,
    },
  });

  unexpectedErrorRate.add(response.status >= 500);
  successRate.add(response.status === 200);
  controlledRejectionRate.add(response.status >= 400 && response.status < 500);

  check(response, {
    [`${scenarioName}: expected status`]: (res) => expectedStatuses.includes(res.status),
    [`${scenarioName}: structured JSON response`]: (res) => {
      try {
        const body = res.json();
        return Boolean(body && (body.game || body.error || body.message));
      } catch (_) {
        return false;
      }
    },
  });

  return response;
}

function basePayload(overrides = {}) {
  return {
    field_id: fieldForIteration(),
    sport_type: sportType,
    players_present: 1,
    max_players: 10,
    age_note: "LOADTEST ISSUE-088 synthetic game creation request",
    scheduled_at: null,
    ...overrides,
  };
}

function baseline() {
  const response = postGame(basePayload(), [200, 400]);
  check(response, {
    "baseline: success or controlled conflict": (res) => {
      if (res.status === 200) {
        return res.json("message") === "Game created" && Boolean(res.json("game.id"));
      }
      return res.json("code") === "CONFLICT";
    },
  });
}

function scheduled() {
  const offset = 24 * 60 + exec.scenario.iterationInTest * 5;
  const scheduledAt = futureTimestamp(offset);
  const response = postGame(basePayload({ scheduled_at: scheduledAt }), [200, 400]);
  check(response, {
    "scheduled: created or controlled conflict": (res) => {
      if (res.status === 200) {
        return res.json("message") === "Game created" && Boolean(res.json("game.id"));
      }
      return res.json("code") === "CONFLICT";
    },
  });
}

function duplicateInstant() {
  const response = postGame(basePayload(), [200, 400, 409]);
  check(response, {
    "duplicate instant: created or controlled conflict": (res) =>
      [200, 400, 409].includes(res.status),
  });
}

function duplicateScheduled() {
  const scheduledAt = __ENV.DUPLICATE_SCHEDULED_AT || futureTimestamp(24 * 60);
  const response = postGame(basePayload({ scheduled_at: scheduledAt }), [200, 400, 409]);
  check(response, {
    "duplicate scheduled: created or controlled conflict": (res) =>
      [200, 400, 409].includes(res.status),
  });
}

function validation() {
  const invalidCases = [
    basePayload({ players_present: 11, max_players: 10 }),
    basePayload({ sport_type: "tennis" }),
    basePayload({ scheduled_at: new Date(Date.now() - 60 * 60 * 1000).toISOString() }),
  ];
  const payload = invalidCases[exec.scenario.iterationInTest % invalidCases.length];
  const response = postGame(payload, [400, 422]);
  check(response, {
    "validation: rejected without success": (res) => res.status === 400 || res.status === 422,
  });
}

export default function () {
  if (scenarioName === "scheduled") {
    scheduled();
  } else if (scenarioName === "duplicate-instant") {
    duplicateInstant();
  } else if (scenarioName === "duplicate-scheduled") {
    duplicateScheduled();
  } else if (scenarioName === "validation") {
    validation();
  } else {
    baseline();
  }

  sleep(sleepSeconds);
}
