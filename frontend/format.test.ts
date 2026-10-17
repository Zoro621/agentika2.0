import { describe, it, expect } from "vitest";
import { formatMetric } from "./format";
describe("scientific metric presentation", () => {
  it("preserves the different scales of error and bounded metrics", () => {
    expect(formatMetric(0.912, "accuracy")).toBe("91.20%");
    expect(formatMetric(2.7, "rmse")).toBe("2.7");
    expect(formatMetric(-0.4, "r2")).toBe("-0.4");
  });
});
