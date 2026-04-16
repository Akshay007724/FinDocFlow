import { describe, it, expect } from "vitest";
import {
  cn,
  classForStatus,
  formatNumber,
  formatPercent,
  formatDelta,
  formatDuration,
  relativeTime,
} from "@/lib/utils";

describe("cn", () => {
  it("merges class names and dedupes tailwind utilities", () => {
    expect(cn("p-2", "p-4", false && "hidden")).toContain("p-4");
  });
});

describe("classForStatus", () => {
  it.each([
    ["done", "accent"],
    ["completed", "accent"],
    ["processing", "primary"],
    ["pending", "primary"],
    ["failed", "destructive"],
    ["error", "destructive"],
    ["unknown", "warning"],
  ])("returns a class containing %s colour for status %s", (status, expected) => {
    expect(classForStatus(status)).toContain(expected);
  });
});

describe("formatters", () => {
  it("formats numbers", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
  });
  it("formats percent", () => {
    expect(formatPercent(0.1234, 1)).toBe("12.3%");
  });
  it("formats deltas with sign", () => {
    expect(formatDelta(0.05)).toBe("+5.0%");
    expect(formatDelta(-0.02)).toBe("-2.0%");
    expect(formatDelta(0)).toBe("0.0%");
  });
  it("formats durations in the appropriate unit", () => {
    expect(formatDuration(500)).toBe("500ms");
    expect(formatDuration(2500)).toBe("2.5s");
    expect(formatDuration(135_000)).toBe("2m 15s");
  });
  it("computes relative time", () => {
    const recent = new Date(Date.now() - 5_000).toISOString();
    expect(relativeTime(recent)).toMatch(/s ago/);
  });
});
