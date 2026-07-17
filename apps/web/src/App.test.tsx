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
    expect(screen.getByRole("button", { name: /Results & export/i })).toBeDisabled();
  });
});
