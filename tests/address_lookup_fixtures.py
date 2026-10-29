"""Prevent actual GIS calls in general navigation fixtures; preserve local page fetches."""


def without_live_address_requests(html: str) -> str:
    return html.replace(
        "<head>",
        """<head><script>(() => {
          const originalFetch = window.fetch.bind(window);
          window.fetch = (url, options) => {
            if (String(url).startsWith('https://gismaps.kingcounty.gov/arcgis/') ||
                String(url).startsWith('https://services.arcgis.com/Ej0PsM5Aw677QF1W/')) {
              return Promise.resolve(new Response(JSON.stringify({suggestions: []})));
            }
            return originalFetch(url, options);
          };
        })();</script>""",
        1,
    )
