import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ClientConsoleHomePage from "../../apps/client-console/src/app/page";
import CustomerWebHomePage from "../../apps/customer-web/src/app/page";
import PlatformConsoleHomePage from "../../apps/platform-console/src/app/page";
import playwrightConfig from "../../playwright.config";

afterEach(() => {
  cleanup();
});

describe("frontend application scaffolds", () => {
  it("renders the Client Console landmark", () => {
    render(<ClientConsoleHomePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Client Console" }),
    ).toBeTruthy();
  });

  it("renders the Customer Support landmark", () => {
    render(<CustomerWebHomePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Customer Support" }),
    ).toBeTruthy();
  });

  it("renders the Platform Console landmark", () => {
    render(<PlatformConsoleHomePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Platform Console" }),
    ).toBeTruthy();
  });
});

describe("browser test foundation", () => {
  it("keeps sensitive browser artifacts disabled by default", () => {
    expect(playwrightConfig.reporter).toBe("line");
    expect(playwrightConfig.use).toMatchObject({
      trace: "off",
      screenshot: "off",
      video: "off",
    });
  });
});
