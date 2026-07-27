/**
 * Populates the page from fetched content (decision 57) — the DOM-writing
 * half of the split from api.ts's fetching. Every id here matches an empty
 * element already in index.html; nothing is hardcoded there for this to
 * overwrite, so a fetch failure just leaves those elements empty rather than
 * replacing real copy with something stale.
 */

import type { AskContent, BrowserContent, ContactContent, ProfileContent, ProjectItem, ProjectsContent } from "./api";

export interface PageContent {
  profile: ProfileContent;
  browser: BrowserContent;
  ask: AskContent;
  contact: ContactContent;
  projects: ProjectsContent;
}

function setText(id: string, text: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function renderProjectList(items: ProjectItem[]): void {
  const list = document.getElementById("work-list");
  if (!list) return;
  list.replaceChildren();

  for (const item of items) {
    const li = document.createElement("li");
    li.className = "work-item";

    const meta = document.createElement("p");
    meta.className = "work-meta";
    meta.textContent = `${item.company} · ${item.year}`;

    const name = document.createElement("h3");
    name.className = "work-name";
    name.textContent = item.name;

    const note = document.createElement("p");
    note.className = "work-note";
    note.textContent = item.note;

    li.append(meta, name, note);
    list.append(li);
  }
}

export function renderContent(content: PageContent): void {
  setText("hero-location", content.profile.location);
  setText("hero-name", content.profile.name);
  setText("hero-tagline", content.profile.tagline);

  setText("browser-label", content.browser.label);
  setText("browser-heading", content.browser.heading);
  setText("browser-description", content.browser.description);

  setText("ask-label", content.ask.label);
  setText("ask-heading", content.ask.heading);
  setText("ask-description", content.ask.description);

  setText("contact-label", content.contact.label);
  setText("contact-heading", content.contact.heading);
  setText("contact-description", content.contact.description);

  setText("projects-label", content.projects.label);
  setText("projects-heading", content.projects.heading);
  renderProjectList(content.projects.items);
}
