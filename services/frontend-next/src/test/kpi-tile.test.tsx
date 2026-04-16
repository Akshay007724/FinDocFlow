import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiTile } from "@/components/kpi-tile";
import { Activity } from "lucide-react";

describe("KpiTile", () => {
  it("renders label, value, and hint", () => {
    render(<KpiTile label="Docs" value="128" hint="last 24h" icon={Activity} />);
    expect(screen.getByText("Docs")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("last 24h")).toBeInTheDocument();
  });

  it("shows a positive delta with up-arrow styling", () => {
    render(<KpiTile label="X" value="1" delta={0.12} deltaLabel="vs y" />);
    expect(screen.getByText(/12.0%/)).toBeInTheDocument();
  });

  it("renders skeleton while loading", () => {
    const { container } = render(<KpiTile label="X" loading />);
    expect(container.querySelector(".shimmer")).toBeInTheDocument();
  });
});
