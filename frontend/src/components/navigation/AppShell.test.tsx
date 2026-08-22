import { render, screen } from "@testing-library/react";
import AppShell from "@/components/navigation/AppShell";

jest.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("AppShell", () => {
  it("renders primary navigation with accessible labels", () => {
    render(
      <AppShell>
        <p>Innhold</p>
      </AppShell>,
    );
    expect(screen.getByRole("navigation", { name: "Hovednavigasjon" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Mobilnavigasjon" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "I dag" })).toHaveLength(2);
    expect(screen.getByText("Innhold")).toBeInTheDocument();
  });
});
