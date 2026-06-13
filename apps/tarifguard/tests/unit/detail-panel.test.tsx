import { render, screen } from "@testing-library/react";

import { DetailPanel } from "@/components/DetailPanel";
import { makeRecord } from "./_fixtures";

describe("DetailPanel — frozen-record detail", () => {
  it("anchors on the certified value with version + hash chips and provenance", () => {
    const record = makeRecord();
    const { container } = render(<DetailPanel record={record} />);

    const value = container.querySelector(".value-certified");
    expect(value?.textContent).toContain("9.57");

    expect(screen.getByText("v2")).toBeTruthy();
    const titles = Array.from(container.querySelectorAll("[title]")).map((el) => el.getAttribute("title") ?? "");
    expect(titles.some((t) => t.length === 64)).toBe(true); // the record_hash chip

    const provenance = screen.getByText("source document").closest("a");
    expect(provenance?.getAttribute("href")).toContain("tardoc.example");
  });

  it("discloses AI harmonisation as a labelled note, never as a value", () => {
    const record = makeRecord({
      metadata: {
        ai_assisted: true,
        ai_model: "claude-opus-4-8",
        ai_fields: ["designation_fr", "designation_it"],
      },
    });
    const { container } = render(<DetailPanel record={record} />);
    expect(screen.getByText(/AI-assisted/i)).toBeTruthy();
    expect(screen.getByText(/claude-opus-4-8/)).toBeTruthy();
    // The AI note is plain muted text, not the certified-value styling.
    const note = screen.getByText(/AI-assisted/i).closest("p");
    expect(note?.querySelector(".value-certified")).toBeNull();
  });

  it("shows a cross-walk hint when the code exists in other systems", () => {
    const { getByText } = render(
      <DetailPanel record={makeRecord()} crosswalkSystems={["EAL"]} />
    );
    expect(getByText(/also defined in/i)).toBeTruthy();
  });

  it("shows version history when more than one version exists", () => {
    const v1 = makeRecord({ version: 1, tax_points: "9.57", designation: { de: "Grundkonsultation", fr: null, it: null } });
    const v2 = makeRecord({ version: 2, tax_points: "10.10", designation: { de: "Grundkonsultation (rev)", fr: null, it: null } });
    render(<DetailPanel record={v2} versions={[v1, v2]} />);
    expect(screen.getByText(/Version history/i)).toBeTruthy();
    // The revised designation appears in both the header and the history row.
    expect(screen.getAllByText(/Grundkonsultation \(rev\)/).length).toBeGreaterThan(0);
  });
});
