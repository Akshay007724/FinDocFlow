import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "@/components/status-pill";

describe("StatusPill", () => {
  it("renders the given label with aria role status", () => {
    render(<StatusPill status="done" label="Shipped" />);
    const el = screen.getByRole("status");
    expect(el).toHaveTextContent("Shipped");
    expect(el.getAttribute("aria-label")).toContain("Shipped");
  });

  it("falls back to status text when no label provided", () => {
    render(<StatusPill status="processing" />);
    expect(screen.getByRole("status")).toHaveTextContent("processing");
  });
});
