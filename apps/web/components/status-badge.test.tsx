import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("renders readable pipeline statuses", () => {
    render(React.createElement(StatusBadge, { status: "COMPLETED_WITH_WARNINGS" }));
    expect(screen.getByText("COMPLETED WITH WARNINGS")).toBeTruthy();
  });
});
