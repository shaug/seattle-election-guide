// Native share sheet when available, falling back to the same clipboard/
// execCommand pattern the per-race copy-link buttons use. A cancelled share
// sheet (AbortError) is not a failure and must leave the caller's status line
// untouched. Shared verbatim between every page that renders the shared
// footer (UI polish round 4, item L55) so this fallback policy has exactly
// one implementation.
/**
 * @param {string} url
 * @param {string} title
 * @returns {Promise<ShareResult>}
 */
export async function shareOrCopyLink(url, title) {
  if (navigator.share) {
    try {
      await navigator.share({ title, url });
      return 'shared';
    } catch (error) {
      if (/** @type {Error|null} */ (error)?.name === 'AbortError') return 'cancelled';
    }
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
    } else {
      const field = document.createElement('textarea');
      field.value = url;
      field.setAttribute('readonly', '');
      field.className = 'visually-hidden';
      document.body.append(field);
      field.select();
      const copied = document.execCommand('copy');
      field.remove();
      if (!copied) throw new Error('Copy command was unavailable');
    }
    return 'copied';
  } catch {
    return 'failed';
  }
}

// Wires the masthead's Share action (the `band` macro in `_shell.html.j2`) on every
// shareable page: the guide, Comparisons, Sources, About, and the archive. The
// 404 renders no Share action at all, since it declares itself unshareable for
// its social card and one flag governs both (issue 192, R2).
//
// Share moved out of the footer in issue 192: the masthead carries actions on
// the page, the footer carries meta about the site.
export function wireShellShare() {
  const shareButton = document.querySelector('[data-shell-share]');
  const shareStatus = document.querySelector('[data-shell-share-status]');
  shareButton?.addEventListener('click', async () => {
    const value = window.location.href;
    const result = await shareOrCopyLink(value, document.title);
    if (!shareStatus) return;
    if (result === 'copied') shareStatus.textContent = 'Link copied.';
    else if (result === 'shared') shareStatus.textContent = 'Share menu opened.';
    else if (result === 'failed') shareStatus.textContent = `Copy failed. Link: ${value}`;
  });
}
