// Native share sheet when available, falling back to the same clipboard/
// execCommand pattern the per-race copy-link buttons use. A cancelled share
// sheet (AbortError) is not a failure and must leave the caller's status line
// untouched. Shared verbatim between the rendered guide and the site-wide
// About page so both pages implement this fallback policy exactly once.
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
