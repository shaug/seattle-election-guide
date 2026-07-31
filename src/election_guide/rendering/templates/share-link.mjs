// Native share sheet when available, falling back to the same clipboard/
// execCommand pattern the per-race copy-link buttons use. A cancelled share
// sheet (AbortError) is not a failure and must leave the caller's status line
// untouched. Shared verbatim between every page that renders the shared
// footer (UI polish round 4, item L55) so this fallback policy has exactly
// one implementation.
export async function shareOrCopyLink(url, title) {
  if (navigator.share) {
    try {
      await navigator.share({ title, url });
      return 'shared';
    } catch (error) {
      if (error?.name === 'AbortError') return 'cancelled';
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

// The guide's race-dialog routing predates the module bundle and still lives
// in a classic script. Publish this one shared policy to that browser-only
// caller rather than duplicating native-share and clipboard fallbacks there.
if (typeof window !== 'undefined') window.shareOrCopyLink = shareOrCopyLink;

// Wires the shared footer's Share icon action (`site_footer_band_html` in
// shell.py) on every page that renders it: the guide, the dedicated Sources
// page, About, and the archive.
export function wireFooterShare() {
  const shareButton = document.querySelector('[data-footer-share]');
  const shareStatus = document.querySelector('[data-footer-share-status]');
  shareButton?.addEventListener('click', async () => {
    const value = window.location.href;
    const result = await shareOrCopyLink(value, document.title);
    if (!shareStatus) return;
    if (result === 'copied') shareStatus.textContent = 'Link copied.';
    else if (result === 'shared') shareStatus.textContent = 'Share menu opened.';
    else if (result === 'failed') shareStatus.textContent = `Copy failed. Link: ${value}`;
  });
}
