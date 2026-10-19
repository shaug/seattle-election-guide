"""Archive Cloudflare zone analytics before its retention window drops them.

Three halves, deliberately separable (issue #381):

- `window` decides which UTC days are missing. Pure.
- `cloudflare` fetches one day from both datasets. The only part that needs a
  credential.
- `storage` writes the committed archive. The only part that touches the tree.

Manual investigations ask what is missing, fetch it, and write it to a separate
output directory. Expired interior holes are explained under gaps/, without
changing daily rollups or restoring the retired collection schedule (#512).
"""

from election_guide.analytics.cloudflare import (
    ADAPTIVE_RETENTION_DAYS,
    GRAPHQL_ENDPOINT,
    TOKEN_VARIABLE,
    ZONE_VARIABLE,
    AdaptiveDetail,
    AnalyticsQuotaError,
    CloudflareZone,
    open_analytics_zone,
)
from election_guide.analytics.gaps import record_expired_gaps, unexplained_dates
from election_guide.analytics.models import (
    SOURCE_ADAPTIVE,
    SOURCE_DAILY,
    DailyRollup,
    DimensionCount,
)
from election_guide.analytics.storage import (
    ARCHIVE_DIR,
    archive_path,
    archived_dates,
    write_rollup,
)
from election_guide.analytics.window import (
    RETENTION_DAYS,
    missing_dates,
    newest_complete_day,
    window_floor,
)

__all__ = [
    "ADAPTIVE_RETENTION_DAYS",
    "ARCHIVE_DIR",
    "GRAPHQL_ENDPOINT",
    "RETENTION_DAYS",
    "SOURCE_ADAPTIVE",
    "SOURCE_DAILY",
    "TOKEN_VARIABLE",
    "ZONE_VARIABLE",
    "AdaptiveDetail",
    "AnalyticsQuotaError",
    "CloudflareZone",
    "DailyRollup",
    "DimensionCount",
    "archive_path",
    "archived_dates",
    "missing_dates",
    "newest_complete_day",
    "open_analytics_zone",
    "record_expired_gaps",
    "unexplained_dates",
    "window_floor",
    "write_rollup",
]
