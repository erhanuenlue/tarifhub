import { render, screen } from "@testing-library/react";

import { TariffCard } from "@/components/TariffCard";
import { makeRecord } from "./_fixtures";

describe("TariffCard — master-list row", () => {
  it("renders code, designation and the certified value with version + hash chips", () => {
    const { container } = render(<TariffCard record={makeRecord()} rank={1} />);
    expect(screen.getByText("AA.00.0010")).toBeTruthy();
    expect(screen.getByText("TARDOC")).toBeTruthy();
    expect(screen.getByText(/Grundkonsultation/)).toBeTruthy();

    const value = container.querySelector(".value-certified");
    expect(value?.textContent).toContain("9.57");
    expect(value?.textContent).toContain("TP");

    expect(screen.getByText("v2")).toBeTruthy();
    const titles = Array.from(container.querySelectorAll("[title]")).map((el) => el.getAttribute("title") ?? "");
    expect(titles.some((t) => t.length === 64)).toBe(true); // the record_hash chip
  });

  it("keeps the full record_hash in the hash chip title", () => {
    const { container } = render(<TariffCard record={makeRecord()} />);
    const titles = Array.from(container.querySelectorAll("[title]")).map((el) => el.getAttribute("title") ?? "");
    expect(titles).toContain("a".repeat(64));
  });

  it("is the master→detail link", () => {
    const { container } = render(<TariffCard record={makeRecord()} />);
    expect(container.querySelector("a")?.getAttribute("href")).toBe("/tariffs/TARDOC/AA.00.0010");
  });

  it("shows the review pill only when the record is flagged", () => {
    const { rerender } = render(<TariffCard record={makeRecord({ requires_review: false })} />);
    expect(screen.queryByText(/requires review/i)).toBeNull();
    rerender(<TariffCard record={makeRecord({ requires_review: true })} />);
    expect(screen.getByText(/requires review/i)).toBeTruthy();
  });

  it("falls back to price (CHF) when there are no tax points", () => {
    const { container } = render(
      <TariffCard record={makeRecord({ tax_points: null, price_chf: "4.85" })} />
    );
    const value = container.querySelector(".value-certified");
    expect(value?.textContent).toContain("4.85");
    expect(value?.textContent).toContain("CHF");
  });
});
