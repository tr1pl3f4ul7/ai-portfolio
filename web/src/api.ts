/**
 * Backend client.
 *
 * The types below mirror `backend/app/schemas.py`. That file is the contract
 * and this is one of its three consumers — change one, change all three (see
 * the `api-contract` skill).
 *
 * Deliberately DOM-free so the widgets can be tested without mocking a browser,
 * and so failure handling lives in one place rather than in every caller.
 */

import { API_BASE_URL, CONTACT_BASE_URL, REQUEST_TIMEOUT_MS } from "./config";

// --- Contract types (mirror backend/app/schemas.py) -------------------------

export interface Source {
  document: string;
  section: string;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
}

export interface ContactRequest {
  name: string;
  email: string;
  message: string;
}

export interface ContactResponse {
  received: boolean;
  reference: string;
}

// --- Content (mirror backend/app/content.py + schemas.py) -------------------
//
// Portfolio copy, fetched rather than hardcoded — see decision 57's write-up
// on why: one edit on the backend reaches web and mobile without a rebuild
// or an app-store resubmission. Only the sections web actually uses; the
// mobile-only `summarizer` content has no client here.

export interface ProfileContent {
  name: string;
  location: string;
  tagline: string;
}

export interface SectionContent {
  label: string;
  heading: string;
  description: string;
}

export type BrowserContent = SectionContent;

export interface AskContent extends SectionContent {
  suggestions: string[];
}

export type ContactContent = SectionContent;

export interface ProjectItem {
  company: string;
  year: string;
  name: string;
  note: string;
}

export interface ProjectsContent {
  label: string;
  heading: string;
  items: ProjectItem[];
}

// --- Failures ---------------------------------------------------------------

/**
 * Anything that stopped a request completing, carrying a message written for a
 * visitor to read rather than a status code to decode.
 */
export class ApiError extends Error {
  readonly status: number | null;
  readonly retryAfterSeconds: number | null;

  constructor(message: string, status: number | null = null, retryAfterSeconds: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function describeStatus(status: number, detail: string | null): string {
  switch (status) {
    case 422:
      // The backend validated and refused. Its detail is about field shape, not
      // something a visitor can act on, so say the useful thing instead.
      return "That didn't look right — check the fields and try again.";
    case 429:
      return "Daily limit reached. This runs on a small budget — try again tomorrow.";
    case 503:
      // Honest rather than reassuring: something downstream is genuinely down.
      return detail ?? "That service is temporarily unavailable.";
    default:
      return detail ?? `Something went wrong (${status}).`;
  }
}

async function readDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

async function request<T>(baseUrl: string, path: string, init: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, signal: controller.signal });
  } catch (cause) {
    const aborted = cause instanceof DOMException && cause.name === "AbortError";
    throw new ApiError(
      aborted ? "That took too long. Try again." : "Couldn't reach the server. Check your connection.",
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ApiError(
      describeStatus(response.status, await readDetail(response)),
      response.status,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    );
  }

  return (await response.json()) as T;
}

function postJson<T>(baseUrl: string, path: string, payload: unknown): Promise<T> {
  return request<T>(baseUrl, path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function getJson<T>(baseUrl: string, path: string): Promise<T> {
  return request<T>(baseUrl, path, { method: "GET" });
}

// --- Endpoints ---------------------------------------------------------------

/** Ask the RAG chatbot. Retrieval on the VM, generation at the Claude API. */
export function askQuestion(question: string): Promise<ChatResponse> {
  return postJson<ChatResponse>(API_BASE_URL, "/chat", { question });
}

/** Submit the contact form. Goes to the edge Worker's own domain, not the
 * backend directly — see config.ts. */
export function submitContact(submission: ContactRequest): Promise<ContactResponse> {
  return postJson<ContactResponse>(CONTACT_BASE_URL, "/contact", submission);
}

// --- Content ------------------------------------------------------------

/** Hero copy — the web hero and the mobile Home tab share this. */
export function getProfile(): Promise<ProfileContent> {
  return getJson<ProfileContent>(API_BASE_URL, "/content/profile");
}

/** Web's on-device project-finder section copy. Web-only. */
export function getBrowserContent(): Promise<BrowserContent> {
  return getJson<BrowserContent>(API_BASE_URL, "/content/browser");
}

/** Chat section copy, shared by web and mobile. */
export function getAskContent(): Promise<AskContent> {
  return getJson<AskContent>(API_BASE_URL, "/content/ask");
}

/** Contact section copy, shared by web and mobile. */
export function getContactContent(): Promise<ContactContent> {
  return getJson<ContactContent>(API_BASE_URL, "/content/contact");
}

/** The project cards — web's grid, its on-device finder's corpus (decision 44),
 * and mobile's Projects tab. */
export function getProjects(): Promise<ProjectsContent> {
  return getJson<ProjectsContent>(API_BASE_URL, "/content/projects");
}
