import { html, render } from 'lit-html';
import { repeat } from 'lit-html/directives/repeat.js';
import { readClientPayload } from './client-payload.mjs';
import { createUpdatesRouter } from './updates-route.mjs';

/** Enhance the complete readable server log; never replace an entry or live root. */
export function wireUpdates() {
  const admitted = /** @type {UpdatesPayload | null} */ (readClientPayload(document));
  if (!admitted) return;
  const payload = admitted;
  const controls = document.querySelector('[data-update-controls]');
  const count = document.querySelector('[data-update-count]');
  const empty = document.querySelector('[data-update-empty]');
  if (
    !(controls instanceof HTMLElement) ||
    !(count instanceof HTMLElement) ||
    !(empty instanceof HTMLElement)
  )
    return;
  const regions = { controls, count, empty };
  const entries = payload.entries.map((entry) => ({
    ...entry,
    element: document.querySelector(`[data-update-key="${entry.key}"]`),
  }));
  const topics = payload.topics.map((topic) => topic.id);
  const router = createUpdatesRouter(topics);
  let selected = router.read();
  const choices = [{ id: 'all', label: payload.all_label }, ...payload.topics];
  /** @param {string} topic */
  function toggle(topic) {
    selected =
      topic === 'all'
        ? []
        : topics.filter((id) => (id === topic ? !selected.includes(id) : selected.includes(id)));
    router.commit(selected);
    project();
  }
  function project() {
    render(
      repeat(
        choices,
        (choice) => choice.id,
        (choice) => html`<button
      type="button" class="topic-button" data-update-topic=${choice.id}
      aria-pressed=${String(choice.id === 'all' ? !selected.length : selected.includes(choice.id))}
      @click=${() => toggle(choice.id)}>${choice.label}</button>`,
      ),
      regions.controls,
    );
    let matching = 0;
    for (const entry of entries) {
      const visible = !selected.length || entry.topics.some((topic) => selected.includes(topic));
      if (visible) matching++;
      if (entry.element instanceof HTMLElement) entry.element.hidden = !visible;
    }
    regions.empty.hidden = matching !== 0;
    render(payload.count_labels[matching], regions.count);
  }
  // Controls are taken over at boot, before a reader can focus one. Entry
  // bodies remain server-owned and readable even if enhancement is unavailable.
  controls.replaceChildren();
  regions.count.replaceChildren();
  project();
  router.replace(selected);
  router.subscribe((restored) => {
    selected = restored;
    project();
  });
}
