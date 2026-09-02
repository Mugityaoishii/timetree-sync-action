from config import Config
from gcalendar import GoogleCalendarClient
from logger import logger
from models import Event
from timetree import TimeTree


def _private_properties(google_event: dict) -> dict:
    return google_event.get("extendedProperties", {}).get("private", {})


def _is_managed_google_event(google_event: dict, calendar_code: str) -> bool:
    """Return True only for events owned by this TimeTree sync.

    Events created by older versions are also accepted when they contain a
    timetree_id but do not yet have the newer ownership markers.
    """
    props = _private_properties(google_event)
    timetree_id = props.get("timetree_id")

    if not timetree_id:
        return False

    sync_source = props.get("sync_source")
    source_calendar_code = props.get("timetree_calendar_code")

    # Backward compatibility for events created by older versions.
    if sync_source is None and source_calendar_code is None:
        return True

    return sync_source == Event.SYNC_SOURCE and source_calendar_code == calendar_code


def sync():
    client = TimeTree()
    client.login(
        Config.TIMETREE_EMAIL,
        Config.TIMETREE_PASSWORD,
    )
    calendar = client.get_calendar(
        Config.TIMETREE_CALENDAR_CODE,
    )
    logger.info("Selected TimeTree calendar")
    labels = client.get_labels(calendar)
    raw_events = client.get_events(calendar)
    events = [Event.from_timetree(raw) for raw in raw_events]
    label_names = {
        label_id: label["name"]
        for label_id, label in labels.items()
    }

    calendar_by_label = {
        "2人の予定":Config.GOOGLE_CALENDAR_ID_SHARED,
        "ももこの予定":Config.GOOGLE_CALENDAR_ID_MOMOKO,
        "けんたの予定":Config.GOOGLE_CALENDAR_ID_KENTA,
        "ももこ会社":Config.GOOGLE_CALENDAR_ID_MOMOKO_WORK,
        "けんた会社":Config.GOOGLE_CALENDAR_ID_KENTA_WORK,
    }
    
    timetree_ids = {event.id for event in events}

    google = GoogleCalendarClient(
        Config.GOOGLE_SERVICE_ACCOUNT_JSON,
    )
    logger.info("Connected to Google Calendar")

        # Collect managed events from all destination Google calendars.
    google_event_map: dict[str, list[tuple[str, dict]]] = {}

    destination_calendar_ids = list(dict.fromkeys(calendar_by_label.values()))

    for calendar_id in destination_calendar_ids:
        google_events = google.list_events(calendar_id)

        for google_event in google_events:
            if not _is_managed_google_event(
                google_event,
                Config.TIMETREE_CALENDAR_CODE,
            ):
                continue

            timetree_id = _private_properties(google_event)["timetree_id"]
            google_event_map.setdefault(timetree_id, []).append(
                (calendar_id, google_event)
            )

    created_count = 0
    updated_count = 0
    deleted_count = 0
    skipped_count = 0

    # Create/update only events whose TimeTree label is mapped.
    synced_timetree_ids = set()

    for event in events:
        label_name = label_names.get(event.label_id)
        target_calendar_id = calendar_by_label.get(label_name)

        # Unmapped labels (including gray labels) are not synced.
        if target_calendar_id is None:
            continue

        synced_timetree_ids.add(event.id)
        matches = google_event_map.get(event.id, [])

        target_matches = [
            google_event
            for calendar_id, google_event in matches
            if calendar_id == target_calendar_id
        ]

        if not target_matches:
            google.create_event(
                target_calendar_id,
                event.to_google(Config.TIMETREE_CALENDAR_CODE),
            )
            created_count += 1
        else:
            google_event = target_matches[0]
            props = _private_properties(google_event)

            needs_marker_migration = (
                props.get("sync_source") != Event.SYNC_SOURCE
                or props.get("timetree_calendar_code")
                != Config.TIMETREE_CALENDAR_CODE
            )

            if needs_marker_migration or not event.equals_google(
                google_event,
                Config.TIMETREE_CALENDAR_CODE,
            ):
                google.update_event(
                    target_calendar_id,
                    google_event["id"],
                    event.to_google(Config.TIMETREE_CALENDAR_CODE),
                )
                updated_count += 1
            else:
                skipped_count += 1

        # Remove copies from the wrong calendar, and duplicate copies.
        kept_target_copy = False

        for calendar_id, google_event in matches:
            if calendar_id == target_calendar_id and not kept_target_copy:
                kept_target_copy = True
                continue

            google.delete_event(
                calendar_id,
                google_event["id"],
            )
            deleted_count += 1

    # Delete previously synced events that were deleted from TimeTree
    # or changed to an unmapped label.
    for timetree_id, matches in google_event_map.items():
        if timetree_id in synced_timetree_ids:
            continue

        for calendar_id, google_event in matches:
            google.delete_event(
                calendar_id,
                google_event["id"],
            )
            deleted_count += 1    

    logger.info(
        "Sync complete: created=%d updated=%d deleted=%d skipped=%d",
        created_count,
        updated_count,
        deleted_count,
        skipped_count,
    )
