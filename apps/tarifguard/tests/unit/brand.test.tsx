import { render, screen } from "@testing-library/react";

import { AiContent, CertifiedValue, ConfidenceMeter, HashChip, VersionChip } from "@/components/brand";

describe("brand primitives — the visual law", () => {
  it("CertifiedValue renders the frozen value inside the .value-certified class", () => {
    const { container } = render(<CertifiedValue value="10.10" unit="TP" />);
    const el = container.querySelector(".value-certified");
    expect(el).toBeTruthy();
    expect(el?.textContent).toContain("10.10");
    expect(el?.textContent).toContain("TP");
  });

  it("CertifiedValue still uses the certified class (never blank) for a null value", () => {
    const { container } = render(<CertifiedValue value={null} />);
    const el = container.querySelector(".value-certified");
    expect(el).toBeTruthy();
    expect(el?.textContent).toContain("—");
  });

  it("AiContent puts children on the labelled .ai-content surface", () => {
    // The 'AI-generated — not a billing value' label is injected by .ai-content::before (CSS),
    // so its rendered text is asserted by the Playwright smoke against real CSS. Here we assert
    // the surface (the carrier of the label) is applied and never the frozen-value styling.
    const { container } = render(
      <AiContent>
        <span>an explanation</span>
      </AiContent>
    );
    const surface = container.querySelector(".ai-content");
    expect(surface).toBeTruthy();
    expect(surface?.querySelector(".value-certified")).toBeNull();
    expect(surface?.textContent).toContain("an explanation");
  });

  it("VersionChip shows v{n}", () => {
    render(<VersionChip version={3} />);
    expect(screen.getByText("v3")).toBeTruthy();
  });

  it("HashChip truncates the hash but keeps the full SHA-256 in the title", () => {
    const full = "a".repeat(64);
    const { container } = render(<HashChip hash={full} />);
    const chip = container.querySelector("[title]");
    expect(chip?.getAttribute("title")).toBe(full);
    expect(chip?.textContent ?? "").toMatch(/…$/);
    expect((chip?.textContent ?? "").length).toBeLessThan(full.length);
  });

  it("ConfidenceMeter reads the warning tone below the 0.85 review threshold", () => {
    const { container } = render(<ConfidenceMeter value={0.71} />);
    expect(container.textContent).toContain("71%");
    expect(container.querySelector(".text-warning")).toBeTruthy();
    expect(container.querySelector(".text-success")).toBeNull();
  });

  it("ConfidenceMeter reads the success tone at or above the threshold", () => {
    const { container } = render(<ConfidenceMeter value={0.95} />);
    expect(container.querySelector(".text-success")).toBeTruthy();
    expect(container.querySelector(".text-warning")).toBeNull();
  });
});
