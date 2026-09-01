import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AppShell } from "./AppShell"

describe("AppShell", () => {
  it("shows the product boundary and lets a user move between primary views", () => {
    render(<AppShell />)

    expect(
      screen.getByRole("heading", { name: /understand how communities respond/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/synthetic data until you import your own export/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Campaigns" }))

    expect(screen.getByRole("heading", { name: "Campaigns" })).toBeInTheDocument()
    expect(screen.getByText(/run a demo or import data/i)).toBeInTheDocument()
  })

  it("exposes keyboard-readable navigation and a demo action", () => {
    render(<AppShell />)

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /run synthetic demo/i })).toBeEnabled()
  })
})
