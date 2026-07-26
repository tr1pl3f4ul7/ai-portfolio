/**
 * Spam/quality classification — kept pure and apart from the fetch handler so
 * it can be unit tested without a Workers runtime (edge/CLAUDE.md).
 *
 * Fails open. A model error or a timeout returns "clean" rather than "spam" —
 * a missed spam message is an annoyance; a silently dropped job enquiry is
 * the actual failure mode this portfolio can't afford.
 */

export const MODEL = "@cf/meta/llama-3.1-8b-fast-v2";

const SYSTEM_PROMPT = `\
You screen contact-form submissions on a software engineer's portfolio site \
for spam and low-quality content. Real messages are recruiters, hiring \
managers, or engineers asking about the site owner's work and experience.

Reply with exactly one word: SPAM or CLEAN. Nothing else — no punctuation, \
no explanation.

Call it SPAM only for the obvious cases: unsolicited advertising, links to \
unrelated products or services, SEO/marketing pitches, or content unrelated \
to hiring or professional contact. If you are at all unsure, reply CLEAN — \
a real enquiry wrongly dropped is worse than an ad wrongly let through.`;

/** The slice of the Workers AI binding this module actually uses. */
export interface AiRunner {
  run(model: string, inputs: Record<string, unknown>): Promise<{ response?: string }>;
}

export interface Submission {
  name: string;
  email: string;
  message: string;
}

export type Classification = "clean" | "spam";

export async function classify(ai: AiRunner, submission: Submission): Promise<Classification> {
  try {
    const result = await ai.run(MODEL, {
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        {
          role: "user",
          content: `Name: ${submission.name}\nEmail: ${submission.email}\nMessage: ${submission.message}`,
        },
      ],
      max_tokens: 4,
      temperature: 0,
    });

    return (result.response ?? "").trim().toUpperCase().startsWith("SPAM") ? "spam" : "clean";
  } catch {
    return "clean";
  }
}
