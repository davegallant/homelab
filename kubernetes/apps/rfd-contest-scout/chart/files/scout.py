"""RFD Contest Scout: daily digest of Ontario-eligible contests.

Port of the NanoClaw contest-scout.mjs RSS, parse, and dedupe logic. Runs
read-only against the RFD contests feed, records threads in SQLite under
/state, and sends one Gotify message per run. Dave enters contests himself.

The RFD forum HTML is behind a proof-of-work browser challenge, so there is no
HTML fallback in v1 and the feed carries no reply counts; contests are ranked
by expiry, then Once before other frequencies, then newest.
"""

import html
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

FEED_URL = "https://forums.redflagdeals.com/feed/forum/34"
FEED_HOST = "forums.redflagdeals.com"
GOTIFY_HOST = "gotify.davegallant.ca"
GOTIFY_MESSAGE_URL = f"https://{GOTIFY_HOST}/message"
DB_PATH = os.environ.get("CONTEST_SCOUT_DB", "/state/contest-scout.db")
TIME_ZONE = ZoneInfo("America/Toronto")
SOURCE = "rfd"
MAX_ITEMS = 12
REMINDER_DAYS = 3
TIMEOUT_SECONDS = 10
USER_AGENT = "ContestScout/1.0 (+personal RSS digest)"
ATOM = "{http://www.w3.org/2005/Atom}"

NON_ONTARIO_REGIONS = [
    "British Columbia", "BC", "Alberta", "AB", "Saskatchewan", "SK",
    "Manitoba", "MB", "Quebec", "Québec", "QC", "New Brunswick", "NB",
    "Nova Scotia", "NS", "Prince Edward Island", "PEI", "Newfoundland(?: and Labrador)?", "NL",
    "Yukon", "YT", "Northwest Territories", "NWT", "NT", "Nunavut", "NU",
]
REGION_PATTERN = "|".join(NON_ONTARIO_REGIONS)
EXCLUDES_ONTARIO = re.compile(
    r"\b(?:excluding|except(?:ing)?|not\s+(?:open|available)\s+in|unavailable\s+in)\s+"
    r"(?:the\s+)?(?:province\s+of\s+)?Ontario\b",
    re.IGNORECASE,
)
RESTRICTED_TO_OTHER_REGION = re.compile(
    rf"\b(?:{REGION_PATTERN})\s*(?:residents?\s*)?[-–:]?\s*only\b"
    rf"|\bonly\s+(?:(?:residents?|people)\s+(?:of|from|in)\s+)?(?:the\s+)?(?:province\s+of\s+)?(?:{REGION_PATTERN})\b"
    rf"|\bonly\s+(?:for\s+)?(?:{REGION_PATTERN})\s+residents?\b",
    re.IGNORECASE,
)
EXPIRY = re.compile(r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b")
FREQUENCY = re.compile(r"^\[(Once|Daily|Weekly|Other)\]", re.IGNORECASE)
REGION_NOTE = re.compile(r"[\(\[](No\s+[A-Za-z]{2,4})[\)\]]", re.IGNORECASE)
THREAD_PATH = re.compile(r"(?:^|[-/])(\d{5,})(?:/|$)")
MARKDOWN_SPECIAL = re.compile(r"[\\`*_{}\[\]()#+.!|<>]")
FREQUENCY_PREFIX = re.compile(r"^\[(?:Once|Daily|Weekly|Other)\]\s*", re.IGNORECASE)
DATE_IN_TITLE = re.compile(r"\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b\s*[-–]?\s*")


def parse_thread_id(link):
    url = urlparse(link)
    if url.scheme != "https" or url.hostname != FEED_HOST:
        raise ValueError("Expected an RFD forum link")
    value = parse_qs(url.query).get("t", [None])[0]
    if not value:
        match = THREAD_PATH.search(url.path)
        value = match.group(1) if match else None
    if not value or not value.isdigit():
        raise ValueError("RFD thread ID missing from link")
    return value


def expiry_from_title(title):
    match = EXPIRY.search(title)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def region_note_from_title(title):
    match = REGION_NOTE.search(title)
    return " ".join(match.group(1).split()) if match else None


def frequency_from_title(title):
    match = FREQUENCY.match(title)
    return match.group(1).lower() if match else "unknown"


def is_ontario_eligible(title):
    if EXCLUDES_ONTARIO.search(title):
        return False
    return RESTRICTED_TO_OTHER_REGION.search(title) is None


def parse_feed(xml_bytes):
    root = ElementTree.fromstring(xml_bytes)
    entries = root.findall(f"{ATOM}entry")
    if not entries:
        raise ValueError("RFD contests feed contained no entries")
    threads = {}
    for entry in entries:
        # RFD titles are type="html" CDATA, so entities such as &quot; must be decoded.
        title = html.unescape((entry.findtext(f"{ATOM}title") or "").strip())
        link = (entry.findtext(f"{ATOM}id") or "").strip()
        published = (entry.findtext(f"{ATOM}published") or "").strip()
        if not title or not link or not published:
            continue
        try:
            datetime.fromisoformat(published)
            thread_id = parse_thread_id(link)
        except ValueError:
            continue
        threads[thread_id] = {
            "source": SOURCE,
            "thread_id": thread_id,
            "title": title,
            "url": f"https://{FEED_HOST}/viewtopic.php?t={thread_id}",
            "published_at": published,
            "expires_on": expiry_from_title(title),
            "frequency": frequency_from_title(title),
            "region_note": region_note_from_title(title),
        }
    if not threads:
        raise ValueError("RFD contests feed had no usable threads")
    return list(threads.values())


def open_db(path=DB_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS contests (
            source TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_at TEXT,
            expires_on TEXT,
            frequency TEXT NOT NULL DEFAULT 'unknown',
            region_note TEXT,
            first_seen_at TEXT NOT NULL,
            first_notified_at TEXT,
            reminded_at TEXT,
            PRIMARY KEY (source, thread_id)
        )"""
    )
    return conn


def save_threads(conn, threads, now):
    conn.executemany(
        """INSERT INTO contests
            (source, thread_id, title, url, published_at, expires_on, frequency, region_note, first_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source, thread_id) DO UPDATE SET
            title=excluded.title, url=excluded.url, published_at=excluded.published_at,
            expires_on=excluded.expires_on, frequency=excluded.frequency,
            region_note=excluded.region_note""",
        [
            (t["source"], t["thread_id"], t["title"], t["url"], t["published_at"],
             t["expires_on"], t["frequency"], t["region_note"], now)
            for t in threads
        ],
    )


def rank(rows):
    """Soonest expiry first (unknown last), then Once before others, then newest."""
    newest_first = sorted(rows, key=lambda r: datetime.fromisoformat(r["published_at"] or "1970-01-01T00:00:00+00:00"),
                          reverse=True)
    return sorted(newest_first, key=lambda r: (r["expires_on"] or "9999-12-31", r["frequency"] != "once"))


def candidates(conn, today):
    columns = ("source", "thread_id", "title", "url", "published_at", "expires_on", "frequency",
               "region_note", "first_notified_at", "reminded_at")
    rows = conn.execute(
        f"""SELECT {", ".join(columns)} FROM contests
            WHERE source=? AND (expires_on IS NULL OR expires_on >= ?)""",
        (SOURCE, today.isoformat()),
    ).fetchall()
    pending = []
    for row in rows:
        item = dict(zip(columns, row))
        if not is_ontario_eligible(item["title"]):
            continue
        if not item["first_notified_at"]:
            pending.append({**item, "kind": "new"})
        elif item["expires_on"] and not item["reminded_at"] and days_until(item["expires_on"], today) <= REMINDER_DAYS:
            pending.append({**item, "kind": "ending"})
    return rank(pending)[:MAX_ITEMS]


def days_until(value, today):
    return (date.fromisoformat(value) - today).days


def mark_notified(conn, items, now, today):
    with conn:
        for item in items:
            if item["kind"] == "new":
                conn.execute("UPDATE contests SET first_notified_at=? WHERE source=? AND thread_id=?",
                             (now, SOURCE, item["thread_id"]))
                if item["expires_on"] and days_until(item["expires_on"], today) <= REMINDER_DAYS:
                    conn.execute("UPDATE contests SET reminded_at=? WHERE source=? AND thread_id=?",
                                 (now, SOURCE, item["thread_id"]))
            else:
                conn.execute("UPDATE contests SET reminded_at=? WHERE source=? AND thread_id=?",
                             (now, SOURCE, item["thread_id"]))


def escape_markdown(value):
    return " ".join(MARKDOWN_SPECIAL.sub(lambda m: "\\" + m.group(0), value).split())


def format_expiry(value):
    if not value:
        return "expiry unknown"
    d = date.fromisoformat(value)
    return f"{d:%b} {d.day}, {d.year}"


def render_digest(items, today):
    lines = [f"{today.isoformat()} · RFD contests", ""]
    for kind, heading in (("new", "New"), ("ending", "Ending soon")):
        group = [i for i in items if i["kind"] == kind]
        if not group:
            continue
        lines.append(f"**{heading}**")
        for item in group:
            title = DATE_IN_TITLE.sub("", FREQUENCY_PREFIX.sub("", item["title"]))
            note = f" · {item['region_note']}" if item["region_note"] else ""
            lines.append(f"- [{escape_markdown(title)}]({item['url']}) — "
                         f"{format_expiry(item['expires_on'])} · {item['frequency']}{note}")
        lines.append("")
    lines.append("Eligibility is based on the title; check the contest rules before entering.")
    return "\n".join(lines).strip()


def gotify_target(apprise_url):
    """Return (message URL, token) from an Apprise gotifys:// URL for the Gotify host."""
    url = urlparse(apprise_url)
    token = url.path.strip("/")
    if url.scheme != "gotifys" or url.hostname != GOTIFY_HOST or not token:
        raise ValueError("APPRISE_URL must be a gotifys:// URL for the Gotify host")
    return GOTIFY_MESSAGE_URL, token


def send_gotify(apprise_url, message):
    endpoint, token = gotify_target(apprise_url)
    body = json.dumps({
        "title": "Contest Scout",
        "message": message,
        "priority": 5,
        "extras": {"client::display": {"contentType": "text/markdown"}},
    }).encode()
    request = urllib.request.Request(endpoint, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Gotify-Key": token,
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Gotify returned HTTP {response.status}")


def fetch_feed():
    request = urllib.request.Request(FEED_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"RFD feed returned HTTP {response.status}")
        return response.read()


def digest(preview=False, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(TIME_ZONE).date()
    threads = parse_feed(fetch_feed())
    conn = open_db()
    try:
        with conn:
            save_threads(conn, threads, now.isoformat())
        items = candidates(conn, today)
        if not items:
            print("Contest Scout: no new or ending-soon contests", file=sys.stderr)
            return 0
        message = render_digest(items, today)
        if preview:
            print(message)
            print(f"Preview: {len(items)} selected", file=sys.stderr)
            return 0
        send_gotify(os.environ["APPRISE_URL"], message)
        mark_notified(conn, items, now.isoformat(), today)
        print(f"Contest Scout: delivered {len(items)} contests via Gotify", file=sys.stderr)
        return 0
    finally:
        conn.close()


def main(argv):
    preview = argv[1:] == ["preview"]
    if argv[1:] not in ([], ["digest"], ["preview"]):
        print("Usage: scout.py [digest|preview]", file=sys.stderr)
        return 2
    try:
        return digest(preview=preview)
    except Exception as error:  # the token is never in an exception message
        print(f"Contest Scout: failed with {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
