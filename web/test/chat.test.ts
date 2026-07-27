/**
 * Interaction tests for the chat widget.
 *
 * The API module is mocked, so these assert on what the visitor actually sees:
 * the answer, the sections it was grounded in, the honest failure messages, and
 * that the widget cannot be made to fire two requests at once.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api";

const askQuestion = vi.fn();
vi.mock("../src/api", async () => {
  const actual = await vi.importActual<typeof import("../src/api")>("../src/api");
  return { ...actual, askQuestion: (q: string) => askQuestion(q) };
});

const { mountChat } = await import("../src/chat");

let root: HTMLElement;

const input = () => root.querySelector<HTMLInputElement>(".chat-input")!;
const form = () => root.querySelector<HTMLFormElement>(".chat-form")!;
const send = () => root.querySelector<HTMLButtonElement>(".chat-send")!;
const text = () => root.textContent ?? "";

/** Fill the box and submit, then let pending promises settle. */
async function ask(question: string): Promise<void> {
  input().value = question;
  form().dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  await vi.waitFor(() => expect(send().disabled).toBe(false));
}

beforeEach(() => {
  document.body.innerHTML = "<div id='chat'></div>";
  root = document.querySelector("#chat")!;
  askQuestion.mockReset();
  mountChat(root);
});

describe("asking a question", () => {
  it("shows the answer", async () => {
    askQuestion.mockResolvedValue({ answer: "He works at AI Talent.", sources: [] });

    await ask("Who does he work for?");

    expect(text()).toContain("He works at AI Talent.");
  });

  it("echoes the question back into the transcript", async () => {
    askQuestion.mockResolvedValue({ answer: "Yes.", sources: [] });

    await ask("Does he have security experience?");

    expect(text()).toContain("Does he have security experience?");
  });

  it("lists the sections the answer was grounded in", async () => {
    askQuestion.mockResolvedValue({
      answer: "Four years at PropertyMe.",
      sources: [
        { document: "experience.md", section: "Software Engineer at PropertyMe" },
        { document: "projects-mobile.md", section: "PropertyMe" },
      ],
    });

    await ask("Tell me about PropertyMe");

    expect(text()).toContain("experience.md · Software Engineer at PropertyMe");
    expect(text()).toContain("projects-mobile.md · PropertyMe");
  });

  it("shows a real measured round trip, not a fixed string", async () => {
    askQuestion.mockResolvedValue({ answer: "Yes.", sources: [] });

    await ask("anything");

    expect(text()).toMatch(/server \+ cloud · \d+\.\d{2}s/);
  });

  it("reports the measurement to the caller so the trace can use it", async () => {
    const onAnswered = vi.fn();
    document.body.innerHTML = "<div id='chat2'></div>";
    const other = document.querySelector<HTMLElement>("#chat2")!;
    mountChat(other, { onAnswered });
    askQuestion.mockResolvedValue({ answer: "Yes.", sources: [] });

    other.querySelector<HTMLInputElement>(".chat-input")!.value = "hi";
    other.querySelector<HTMLFormElement>(".chat-form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    await vi.waitFor(() => expect(onAnswered).toHaveBeenCalled());
    expect(onAnswered.mock.calls[0]![0]).toBeTypeOf("number");
  });

  it("clears the box so the next question can be typed straight away", async () => {
    askQuestion.mockResolvedValue({ answer: "Yes.", sources: [] });

    await ask("first question");

    expect(input().value).toBe("");
  });

  it("keeps earlier exchanges in the transcript", async () => {
    askQuestion.mockResolvedValue({ answer: "First answer.", sources: [] });
    await ask("first");
    askQuestion.mockResolvedValue({ answer: "Second answer.", sources: [] });
    await ask("second");

    expect(root.querySelectorAll(".chat-exchange")).toHaveLength(2);
    expect(text()).toContain("First answer.");
  });
});

describe("markdown emphasis is normalised away", () => {
  // Observed live: the model returned "**Hood VR**" despite the system prompt
  // asking for plain prose. A visitor would have seen literal asterisks.
  it("renders bold markers as plain text", async () => {
    askQuestion.mockResolvedValue({
      answer: "The main projects were **Hood VR**, **OMV VR** and __Wincanton__.",
      sources: [],
    });

    await ask("What VR work has he done?");

    expect(text()).toContain("The main projects were Hood VR, OMV VR and Wincanton.");
    expect(text()).not.toContain("**");
    expect(text()).not.toContain("__");
  });

  it("strips heading markers", async () => {
    askQuestion.mockResolvedValue({ answer: "## Experience\nTen years.", sources: [] });

    await ask("hi");

    expect(text()).not.toContain("##");
    expect(text()).toContain("Experience");
  });

  it("leaves ordinary prose untouched", async () => {
    askQuestion.mockResolvedValue({ answer: "He rated 6.25 out of 7 — a distinction.", sources: [] });

    await ask("hi");

    expect(text()).toContain("He rated 6.25 out of 7 — a distinction.");
  });
});

describe("guards", () => {
  it("ignores an empty question", () => {
    input().value = "   ";
    form().dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(askQuestion).not.toHaveBeenCalled();
  });

  it("disables the input while a request is in flight", async () => {
    let release: (value: unknown) => void = () => {};
    askQuestion.mockReturnValue(new Promise((resolve) => (release = resolve)));

    input().value = "slow question";
    form().dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(input().disabled).toBe(true);
    expect(send().disabled).toBe(true);

    release({ answer: "done", sources: [] });
    await vi.waitFor(() => expect(send().disabled).toBe(false));
  });

  it("will not fire a second request while one is running", async () => {
    let release: (value: unknown) => void = () => {};
    askQuestion.mockReturnValue(new Promise((resolve) => (release = resolve)));

    input().value = "one";
    form().dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    input().value = "two";
    form().dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(askQuestion).toHaveBeenCalledTimes(1);

    release({ answer: "done", sources: [] });
    await vi.waitFor(() => expect(send().disabled).toBe(false));
  });
});

describe("failures", () => {
  it("shows the rate-limit message rather than a silent nothing", async () => {
    askQuestion.mockRejectedValue(new ApiError("Daily limit reached. Try again tomorrow.", 429));

    await ask("hi");

    expect(text()).toContain("Daily limit reached");
  });

  it("shows what is unavailable on a 503", async () => {
    askQuestion.mockRejectedValue(new ApiError("vector store missing", 503));

    await ask("hi");

    expect(text()).toContain("vector store missing");
  });

  it("recovers — the widget still works after a failure", async () => {
    askQuestion.mockRejectedValue(new ApiError("boom", 503));
    await ask("first");

    askQuestion.mockResolvedValue({ answer: "Recovered.", sources: [] });
    await ask("second");

    expect(text()).toContain("Recovered.");
  });

  it("does not leak an unexpected error object into the page", async () => {
    askQuestion.mockRejectedValue(new Error("TypeError: undefined is not a function"));

    await ask("hi");

    expect(text()).toContain("Something went wrong.");
    expect(text()).not.toContain("undefined is not a function");
  });
});

describe("suggested prompts", () => {
  it("submits the prompt when one is clicked", async () => {
    // Suggestions come from GET /content/ask now (decision 57), not a
    // hardcoded list — the shared beforeEach's plain mountChat(root) renders
    // none, so this test mounts its own with some to click.
    mountChat(root, { suggestions: ["What's the hardest thing you've built?"] });
    askQuestion.mockResolvedValue({ answer: "Answered.", sources: [] });

    root.querySelector<HTMLButtonElement>(".chat-prompt")!.click();

    await vi.waitFor(() => expect(askQuestion).toHaveBeenCalled());
    expect(askQuestion.mock.calls[0]![0]).toBeTruthy();
  });
});
