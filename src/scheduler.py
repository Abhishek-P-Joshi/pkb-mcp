import sys
from src.config import config


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()

    # Sync Watch Later every 6 hours
    if config.youtube_sync_enabled:
        from src.connectors.youtube_api import sync_playlist
        scheduler.add_job(
            lambda: sync_playlist("WL"),
            "interval",
            hours=6,
            id="youtube_watch_later_sync",
            replace_existing=True,
        )
        print("YouTube Watch Later auto-sync scheduled (every 6 hours)", file=sys.stderr)

    scheduler.start()
    return scheduler
