/**
 * Unit tests for the classification logic — the bulk of the test value per
 * edge/CLAUDE.md, since it's kept pure and doesn't need a Workers runtime.
 * The AI binding is a plain object here, not a live model.
 */

import { describe, expect, it } from "vitest";
import { classify, MODEL, type AiRunner, type Submission } from "../src/classify";

const SUBMISSION: Submission = {
  name: "Dana Okafor",
  email: "dana@example.com",
  message: "Are you available for a contract role?",
};

function fakeAi(response: string): AiRunner {
  return { run: async () => ({ response }) };
}

describe("classify", () => {
  it("calls the model configured for this Worker", async () => {
    let calledModel = "";
    const ai: AiRunner = {
      run: async (model) => {
        calledModel = model;
        return { response: "CLEAN" };
      },
    };

    await classify(ai, SUBMISSION);

    expect(calledModel).toBe(MODEL);
  });

  it("treats a CLEAN verdict as clean", async () => {
    expect(await classify(fakeAi("CLEAN"), SUBMISSION)).toBe("clean");
  });

  it("treats a SPAM verdict as spam", async () => {
    expect(await classify(fakeAi("SPAM"), SUBMISSION)).toBe("spam");
  });

  it("is case-insensitive", async () => {
    expect(await classify(fakeAi("spam"), SUBMISSION)).toBe("spam");
  });

  it("treats an empty response as clean rather than guessing spam", async () => {
    expect(await classify(fakeAi(""), SUBMISSION)).toBe("clean");
  });

  it("treats an unexpected response as clean", async () => {
    expect(await classify(fakeAi("unsure, maybe?"), SUBMISSION)).toBe("clean");
  });

  it("fails open when the model throws", async () => {
    const ai: AiRunner = {
      run: async () => {
        throw new Error("model timed out");
      },
    };

    expect(await classify(ai, SUBMISSION)).toBe("clean");
  });
});
