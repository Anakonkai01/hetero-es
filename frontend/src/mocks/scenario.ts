export type Scenario =
  | "normal"
  | "loading"
  | "empty"
  | "error"
  | "stale"
  | "notfound";

let currentScenario: Scenario = "normal";

export function getScenario(): Scenario {
  return currentScenario;
}

export function setScenario(scenario: Scenario): void {
  currentScenario = scenario;
}
