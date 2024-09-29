from datetime import timedelta

import aw_client
from aw_transform.filter_period_intersect import _intersecting_eventpairs

aw = aw_client.ActivityWatchClient()

buckets = aw.get_buckets()
print("Available bucket IDs:")
print()
for id in buckets.keys():
    print(id)
print()