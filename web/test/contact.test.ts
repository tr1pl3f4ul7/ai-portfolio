/**
 * Interaction tests for the contact form.
 *
 * The rule these encode: client-side validation saves a round trip, it is not
 * the gate. The backend validates independently — so the tests check that
 * obvious mistakes are caught early AND that a rejected submission never
 * reaches the network.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api";
import { validate } from "../src/contact";

const submitContact = vi.fn();
vi.mock("../src/api", async () => {
  const actual = await vi.importActual<typeof import("../src/api")>("../src/api");
  return { ...actual, submitContact: (s: unknown) => submitContact(s) };
});

const { mountContact } = await import("../src/contact");

let root: HTMLElement;

const nameInput = () => root.querySelector<HTMLInputElement>("#name")!;
const emailInput = () => root.querySelector<HTMLInputElement>("#email")!;
const messageInput = () => root.querySelector<HTMLTextAreaElement>("#message")!;
const button = () => root.querySelector<HTMLButtonElement>(".contact-send")!;
const status = () => root.querySelector<HTMLElement>(".contact-status")!;
const text = () => root.textContent ?? "";

function fill(fields: { name?: string; email?: string; message?: string }): void {
  if (fields.name !== undefined) nameInput().value = fields.name;
  if (fields.email !== undefined) emailInput().value = fields.email;
  if (fields.message !== undefined) messageInput().value = fields.message;
}

function submit(): void {
  root
    .querySelector<HTMLFormElement>(".contact-form")!
    .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
}

const VALID = { name: "Dana Okafor", email: "dana@example.com", message: "Are you available?" };

beforeEach(() => {
  document.body.innerHTML = "<div id='contact'></div>";
  root = document.querySelector("#contact")!;
  submitContact.mockReset();
  mountContact(root);
});

describe("validate (pure)", () => {
  it("accepts a complete submission", () => {
    expect(validate(VALID)).toEqual({});
  });

  it.each([
    ["name", { ...VALID, name: "  " }],
    ["email", { ...VALID, email: "" }],
    ["message", { ...VALID, message: "" }],
  ])("requires %s", (field, fields) => {
    expect(validate(fields)).toHaveProperty(field);
  });

  it.each(["not-an-email", "missing@tld", "@example.com", "two @ example.com"])(
    "rejects %s as an email",
    (email) => {
      expect(validate({ ...VALID, email })).toHaveProperty("email");
    },
  );

  it("rejects a message past the backend's ceiling", () => {
    expect(validate({ ...VALID, message: "a".repeat(5001) })).toHaveProperty("message");
  });

  it("rejects a name past the backend's ceiling", () => {
    expect(validate({ ...VALID, name: "a".repeat(121) })).toHaveProperty("name");
  });
});

describe("submitting", () => {
  it("sends the trimmed fields", async () => {
    submitContact.mockResolvedValue({ received: true, reference: "abc123" });

    fill({ name: "  Dana  ", email: "  dana@example.com ", message: "  Hello.  " });
    submit();

    await vi.waitFor(() => expect(submitContact).toHaveBeenCalled());
    expect(submitContact.mock.calls[0]![0]).toEqual({
      name: "Dana",
      email: "dana@example.com",
      message: "Hello.",
    });
  });

  it("shows the reference so the visitor can quote it", async () => {
    submitContact.mockResolvedValue({ received: true, reference: "2418ab6cf5e0" });

    fill(VALID);
    submit();

    await vi.waitFor(() => expect(status().hidden).toBe(false));
    expect(text()).toContain("2418ab6cf5e0");
    expect(status().classList.contains("is-sent")).toBe(true);
  });

  it("clears the form after a successful send", async () => {
    submitContact.mockResolvedValue({ received: true, reference: "abc" });

    fill(VALID);
    submit();

    await vi.waitFor(() => expect(status().hidden).toBe(false));
    expect(nameInput().value).toBe("");
    expect(messageInput().value).toBe("");
  });

  it("disables the button while sending", async () => {
    let release: (value: unknown) => void = () => {};
    submitContact.mockReturnValue(new Promise((resolve) => (release = resolve)));

    fill(VALID);
    submit();

    expect(button().disabled).toBe(true);

    release({ received: true, reference: "abc" });
    await vi.waitFor(() => expect(button().disabled).toBe(false));
  });

  it("will not send twice from a double submit", async () => {
    let release: (value: unknown) => void = () => {};
    submitContact.mockReturnValue(new Promise((resolve) => (release = resolve)));

    fill(VALID);
    submit();
    submit();

    expect(submitContact).toHaveBeenCalledTimes(1);

    release({ received: true, reference: "abc" });
    await vi.waitFor(() => expect(button().disabled).toBe(false));
  });
});

describe("invalid input never reaches the network", () => {
  it("does not submit when fields are empty", () => {
    submit();
    expect(submitContact).not.toHaveBeenCalled();
  });

  it("does not submit with a malformed email", () => {
    fill({ ...VALID, email: "nope" });
    submit();
    expect(submitContact).not.toHaveBeenCalled();
  });

  it("shows a message against the offending field", () => {
    fill({ ...VALID, email: "nope" });
    submit();

    const error = root.querySelector<HTMLElement>("#email-error")!;
    expect(error.hidden).toBe(false);
    expect(error.textContent).toBeTruthy();
    expect(emailInput().getAttribute("aria-invalid")).toBe("true");
  });

  it("clears the message once the field is corrected", async () => {
    submitContact.mockResolvedValue({ received: true, reference: "abc" });

    fill({ ...VALID, email: "nope" });
    submit();
    expect(root.querySelector<HTMLElement>("#email-error")!.hidden).toBe(false);

    fill({ email: "dana@example.com" });
    submit();

    await vi.waitFor(() => expect(submitContact).toHaveBeenCalled());
    expect(root.querySelector<HTMLElement>("#email-error")!.hidden).toBe(true);
  });
});

describe("failures", () => {
  it("shows the rate-limit message", async () => {
    submitContact.mockRejectedValue(new ApiError("Daily limit reached.", 429));

    fill(VALID);
    submit();

    await vi.waitFor(() => expect(status().hidden).toBe(false));
    expect(text()).toContain("Daily limit reached.");
    expect(status().classList.contains("is-error")).toBe(true);
  });

  it("keeps what the visitor typed when sending fails", async () => {
    submitContact.mockRejectedValue(new ApiError("could not store the submission", 503));

    fill(VALID);
    submit();

    await vi.waitFor(() => expect(status().hidden).toBe(false));
    // Losing a message someone just wrote would be the worst outcome here.
    expect(messageInput().value).toBe(VALID.message);
  });

  it("lets the visitor retry after a failure", async () => {
    submitContact.mockRejectedValue(new ApiError("boom", 503));
    fill(VALID);
    submit();
    await vi.waitFor(() => expect(status().hidden).toBe(false));

    submitContact.mockResolvedValue({ received: true, reference: "second-try" });
    submit();

    await vi.waitFor(() => expect(text()).toContain("second-try"));
    expect(status().classList.contains("is-error")).toBe(false);
  });
});
