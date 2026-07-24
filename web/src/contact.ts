/**
 * The contact form.
 *
 * Posts straight to the backend's /contact, which stores the submission before
 * anything that can fail, then triages it with Claude and emails LJ. Phase 4
 * puts the Cloudflare Worker in front of this for spam pre-filtering; until
 * then the path is direct.
 *
 * Client-side validation exists to save a round trip, not to be the gate — the
 * backend validates independently and is the only thing that actually counts.
 */

import { ApiError, submitContact } from "./api";

// Matches nothing clever on purpose: a full address grammar belongs on the
// server (which uses a real validator). This only catches obvious typos before
// the visitor waits for a round trip.
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const MAX_NAME = 120; // Mirrors MAX_NAME_CHARS on the backend.
const MAX_MESSAGE = 5000; // Mirrors MAX_MESSAGE_CHARS.

interface Fields {
  name: string;
  email: string;
  message: string;
}

/**
 * Pure validation, exported so it can be tested without a DOM.
 * Returns a field-keyed map of problems; empty means valid.
 */
export function validate(fields: Fields): Partial<Record<keyof Fields, string>> {
  const problems: Partial<Record<keyof Fields, string>> = {};

  if (!fields.name.trim()) problems.name = "Your name, please.";
  else if (fields.name.length > MAX_NAME) problems.name = `Keep it under ${MAX_NAME} characters.`;

  if (!fields.email.trim()) problems.email = "An email address, so I can reply.";
  else if (!LOOKS_LIKE_EMAIL.test(fields.email.trim())) problems.email = "That doesn't look like an email address.";

  if (!fields.message.trim()) problems.message = "Say something — anything.";
  else if (fields.message.length > MAX_MESSAGE) problems.message = `Keep it under ${MAX_MESSAGE} characters.`;

  return problems;
}

function field(
  id: string,
  labelText: string,
  control: HTMLInputElement | HTMLTextAreaElement,
): { wrap: HTMLElement; error: HTMLElement } {
  const wrap = document.createElement("div");
  wrap.className = "field";

  const label = document.createElement("label");
  label.htmlFor = id;
  label.textContent = labelText;

  control.id = id;
  control.name = id;

  const error = document.createElement("p");
  error.className = "field-error";
  error.id = `${id}-error`;
  error.hidden = true;
  // Tie the message to the control so screen readers announce it.
  control.setAttribute("aria-describedby", error.id);

  wrap.append(label, control, error);
  return { wrap, error };
}

export function mountContact(root: HTMLElement): void {
  root.replaceChildren();

  const form = document.createElement("form");
  form.className = "contact-form";
  // Our own validation runs first so the messages are ours, not the browser's.
  form.setAttribute("novalidate", "");

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.autocomplete = "name";
  nameInput.maxLength = MAX_NAME;

  const emailInput = document.createElement("input");
  emailInput.type = "email";
  emailInput.autocomplete = "email";

  const messageInput = document.createElement("textarea");
  messageInput.rows = 5;
  messageInput.maxLength = MAX_MESSAGE;

  const name = field("name", "name", nameInput);
  const email = field("email", "email", emailInput);
  const message = field("message", "message", messageInput);

  const button = document.createElement("button");
  button.type = "submit";
  button.className = "contact-send";
  button.textContent = "send";

  const status = document.createElement("p");
  status.className = "contact-status";
  status.setAttribute("aria-live", "polite");
  status.hidden = true;

  form.append(name.wrap, email.wrap, message.wrap, button, status);
  root.append(form);

  const controls = [
    { input: nameInput, error: name.error, key: "name" as const },
    { input: emailInput, error: email.error, key: "email" as const },
    { input: messageInput, error: message.error, key: "message" as const },
  ];

  const showProblems = (problems: Partial<Record<keyof Fields, string>>): void => {
    for (const { input, error, key } of controls) {
      const problem = problems[key];
      error.textContent = problem ?? "";
      error.hidden = !problem;
      input.setAttribute("aria-invalid", String(Boolean(problem)));
    }
  };

  let inFlight = false;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (inFlight) return;

    const fields: Fields = {
      name: nameInput.value,
      email: emailInput.value,
      message: messageInput.value,
    };

    const problems = validate(fields);
    showProblems(problems);
    if (Object.keys(problems).length > 0) {
      controls.find(({ key }) => problems[key])?.input.focus();
      return;
    }

    inFlight = true;
    button.disabled = true;
    button.textContent = "sending…";
    status.hidden = true;
    status.classList.remove("is-error", "is-sent");

    void submitContact({
      name: fields.name.trim(),
      email: fields.email.trim(),
      message: fields.message.trim(),
    })
      .then((response) => {
        form.reset();
        showProblems({});
        status.textContent = `Sent. Reference ${response.reference} — I'll come back to you.`;
        status.classList.add("is-sent");
        status.hidden = false;
      })
      .catch((error: unknown) => {
        status.textContent = error instanceof ApiError ? error.message : "Something went wrong.";
        status.classList.add("is-error");
        status.hidden = false;
      })
      .finally(() => {
        inFlight = false;
        button.disabled = false;
        button.textContent = "send";
      });
  });
}
