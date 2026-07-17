import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })));

describe("DataPilot workspace", () => {
  it("presents the safety promise and a keyboard-operable project form", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /Turn changing data into reliable outputs/i })).toBeInTheDocument();
    expect(screen.getByText(/Source overwrites/i)).toBeInTheDocument();
    const input = screen.getByRole("textbox", { name: /Project name/i });
    await userEvent.clear(input);
    await userEvent.type(input, "Operations workspace");
    expect(input).toHaveValue("Operations workspace");
  });

  it("does not present locked future steps as available", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: /Source inspection/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Composition studio/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Schema drift review/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Calculated fields/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Run progress/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Results & export/i })).toBeDisabled();
  });

  it("exposes the complete composition workflow after a local project is created", async () => {
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith("/projects") && init?.method === "POST") {
        return new Response(JSON.stringify({
          id: "10000000-0000-4000-8000-000000000001", name: "Composition QA", locale: "en-IN",
          privacy_mode: "local_only", created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }), { status: 201, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /Create local project/i }));
    await userEvent.click(await screen.findByRole("button", { name: /Composition studio/i }));
    expect(screen.getByRole("heading", { name: /Compose changing datasets/i })).toBeInTheDocument();
    expect(screen.getByText("Schema alignment matrix")).toBeInTheDocument();
    expect(screen.getByText("Cardinality warning")).toBeInTheDocument();
    expect(screen.getByText("Batch result manifest")).toBeInTheDocument();
    expect(screen.getByLabelText(/Choose multiple Excel or CSV files/i)).toHaveAttribute("multiple");
  });
});
