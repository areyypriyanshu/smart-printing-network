import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Alert } from "./Alert";
import { Button } from "./Button";
import { PasswordField } from "./PasswordField";
import { Stepper } from "./Stepper";

describe("Button", () => {
  it("is a plain button unless it is told to submit", () => {
    render(<Button>Save</Button>);

    // A button with no type submits its form, which is a trap for a
    // button that is only ever a button.
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute(
      "type",
      "button",
    );
  });

  it("submits when it is told to", () => {
    render(
      <form>
        <Button type="submit">Save</Button>
      </form>,
    );

    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute(
      "type",
      "submit",
    );
  });

  it("says it is busy while a request is running", () => {
    render(
      <Button pending pendingLabel="Saving…">
        Save
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Saving…" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
  });

  it("is not busy when nothing is running", () => {
    render(<Button>Save</Button>);

    expect(screen.getByRole("button", { name: "Save" })).not.toHaveAttribute(
      "aria-busy",
    );
  });

  it("keeps a disabled label readable", () => {
    render(<Button disabled>Save</Button>);

    // The old disabled style was muted on hairline, 2.87:1. The label
    // has to stay legible even though the control is inert.
    const button = screen.getByRole("button", { name: "Save" });
    expect(button.className).toContain("disabled:text-stone");
    expect(button.className).not.toContain("disabled:text-muted");
  });
});

describe("Alert", () => {
  it("interrupts when it is an error", () => {
    render(<Alert>Something broke</Alert>);

    expect(screen.getByRole("alert")).toHaveTextContent("Something broke");
  });

  it("is announced politely when it is good news", () => {
    render(<Alert variant="success">Rates saved</Alert>);

    // A success is not an emergency, so it must not be assertive.
    expect(screen.getByRole("status")).toHaveTextContent("Rates saved");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Stepper", () => {
  it("marks a finished step in words, not only in colour", () => {
    render(<Stepper steps={["Shop", "Location", "Account"]} current={2} />);

    // The finished step says so in text, so the state does not depend
    // on seeing the colour.
    expect(screen.getByText("Done:")).toBeInTheDocument();
    // The step that is still to come does not.
    expect(screen.getAllByText("Done:")).toHaveLength(1);
  });

  it("marks the current step for a screen reader", () => {
    render(<Stepper steps={["Shop", "Location", "Account"]} current={2} />);

    expect(
      screen.getByText("Location").closest("[aria-current]"),
    ).toHaveAttribute("aria-current", "step");
  });

  it("tells a finished step apart from a step still to come", () => {
    render(<Stepper steps={["Shop", "Location", "Account"]} current={2} />);

    const done = screen.getByText("Shop").closest("span");
    const upcoming = screen.getByText("Account").closest("span");
    // A dashed border is a difference the eye can make without reading
    // the colour.
    expect(upcoming?.className).toContain("border-dashed");
    expect(done?.className).not.toContain("border-dashed");
  });
});

describe("PasswordField", () => {
  it("gives the show and hide button a full touch target", () => {
    render(<PasswordField label="Password" name="password" />);

    const button = screen.getByRole("button", { name: "Show password" });
    // 44 px, so the button is comfortable on a phone.
    expect(button.className).toContain("h-11");
    expect(button.className).toContain("w-11");
  });
});
