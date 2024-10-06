"""
    The following code is a modified version of the code from the ActivityWatch project.
    The original code can be found at https://github.com/ActivityWatch/aw-client/blob/main/aw_client/queries.py
"""

from typing import Union
import json
import re
from aw_client.classes import get_classes
from aw_client.queries import DesktopQueryParams,AndroidQueryParams,EnhancedJSONEncoder, isAndroidParams, isDesktopParams, browser_appnames, browsersWithBuckets


def browserEvents(params: DesktopQueryParams) -> str:
    """Returns a list of active browser events (where the browser was the active window) from all browser buckets"""
    code = "browser_events = [];"

    for browserName, bucketId in browsersWithBuckets(params.bid_browsers):
        browser_appnames_str = json.dumps(browser_appnames[browserName])
        # print(browser_appnames[browserName])
        not_pat = f"^(?!.*({'|'.join(browser_appnames[browserName])})).*"
        # print(not_pat)
        code += f"""
          events_{browserName} = flood(query_bucket("{bucketId}"));
          window_{browserName} = filter_keyvals(events, "app", {browser_appnames_str});
          events_{browserName} = filter_period_intersect(events_{browserName}, window_{browserName});
          events = filter_keyvals_regex(events, "app", "{not_pat}");
          events_{browserName} = split_url_events(events_{browserName});
          browser_events = concat(browser_events, events_{browserName});
          browser_events = sort_by_timestamp(browser_events);
        """
        # code += f"""
        #   events_{browserName} = flood(query_bucket("{bucketId}"));
        #   window_{browserName} = filter_keyvals(events, "app", {browser_appnames_str});
        #   events_{browserName} = filter_period_intersect(events_{browserName}, window_{browserName});
        #   events_{browserName} = split_url_events(events_{browserName});
        #   browser_events = concat(browser_events, events_{browserName});
        #   browser_events = sort_by_timestamp(browser_events);
        # """
    return code

def canonicalEvents(params: Union[DesktopQueryParams, AndroidQueryParams]) -> str:
    if not params.classes:
        # if categories not explicitly set,
        # get categories from server settings
        params.classes = get_classes()

    # Needs escaping for regex patterns like '\w' to work (JSON.stringify adds extra unnecessary escaping)
    classes_str = json.dumps(params.classes, cls=EnhancedJSONEncoder)
    classes_str = re.sub(r"\\\\", r"\\", classes_str)

    cat_filter_str = json.dumps(params.filter_classes)

    # For simplicity, we assume that bid_window and bid_android are exchangeable (note however it needs special treatment)
    bid_window = (
        params.bid_window
        if isinstance(params, DesktopQueryParams)
        else params.bid_android
    )
    return "\n".join(
        [
            # Fetch window/app events
            f'events = flood(query_bucket(find_bucket("{bid_window}")));',
            # On Android, merge events to avoid overload of events
            'events = merge_events_by_keys(events, ["app"]);'
            if isAndroidParams(params)
            else "",
            # Fetch not-afk events
            f"""
            not_afk = flood(query_bucket(find_bucket("{params.bid_afk}")));
            not_afk = filter_keyvals(not_afk, "status", ["not-afk"]);
            """
            if isDesktopParams(params)
            else "",
            # Fetch browser events
            (
                (
                    browserEvents(params)
                    if isDesktopParams(params)
                    else ""
                )
                + (  # Include focused and audible browser events as indications of not-afk
                    """
            audible_events = filter_keyvals(browser_events, "audible", [true]);
            not_afk = period_union(not_afk, audible_events);
            """
                    if params.include_audible
                    else ""
                )
                + (
                    "events=union_no_overlap(browser_events,events);"
                )
                if params.bid_browsers
                else ""
            ),
            # Filter out window events when the user was afk
            "events = filter_period_intersect(events, not_afk);"
            if isDesktopParams(params) and params.filter_afk
            else "",
            # Categorize
            f"events = categorize(events, {classes_str});" if params.classes else "",
            # Filter out selected categories
            f"events = filter_keyvals(events, '$category', {cat_filter_str});"
            if params.filter_classes
            else "",
        ]
    )