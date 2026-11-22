"""Free, weekly LinkedIn publisher: CMS news -> original caption -> Buffer."""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

FEED = "https://www.cms.gov/newsroom/rss-feeds"
API = "https://api.buffer.com"
KEYWORDS = {
    "interoperability": 6, "health technology": 5, "health information": 5,
    "pharmacy": 5, "prescription": 4, "drug benefit": 4,
    "claims": 4, "data": 3, "prior authorization": 3,
    "artificial intelligence": 3, "electronic": 2, "digital": 2,
}
EXCLUDE = ("november 12, 2026", "industry electronic prior authorization testing initiative")


def fetch_feed():
    req = urllib.request.Request(FEED, headers={"User-Agent": "SalmanLinkedInNewsAgent/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def candidates(xml_bytes, today):
    root = ET.fromstring(xml_bytes)
    found = []
    for item in root.findall(".//item"):
        title = unescape(" ".join((item.findtext("title") or "").split()))
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate") or item.findtext("date") or ""
        try:
            day = parsedate_to_datetime(published).date()
        except (ValueError, TypeError):
            continue
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname not in {"cms.gov", "www.cms.gov"}:
            continue
        if not (0 <= (today - day).days <= 21):
            continue
        low = title.lower()
        if any(x in low for x in EXCLUDE):
            continue
        score = sum(weight for word, weight in KEYWORDS.items() if word in low)
        if score >= 4:
            found.append((score, day, title, link))
    return sorted(found, key=lambda x: (x[0], x[1]), reverse=True)


def caption(title, link):
    low = title.lower()
    if "pharmacy" in low or "prescription" in low or "drug benefit" in low:
        perspective = "Working in pharmacy operations has made me curious about how medication and coverage data move between teams and systems."
        question = "Where do you see the biggest opportunity to make pharmacy data more useful?"
    elif "claim" in low or "authorization" in low:
        perspective = "In pharmacy operations, I see how important accurate records and clear handoffs are when investigating insurance and billing questions."
        question = "Which data handoff creates the most work for your team?"
    else:
        perspective = "My work validating pharmacy operations data keeps bringing me back to the value of accurate, usable information across workflows."
        question = "What would make healthcare data easier to use in your day-to-day work?"
    # Link to the source; frame the headline as an announcement, not as a proven outcome.
    return (f"A health informatics update I’m following: {title}\n\n"
            f"{perspective} With my background in business analytics, I’m interested in how this develops in practice.\n\n"
            f"{question}\n\nSource: {link}\n\n"
            "#HealthInformatics #HealthcareAnalytics #PharmacyOperations")


def graphql(token, query, variables=None):
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("Buffer GraphQL error: " + str(result["errors"]))
    return result["data"]


def linkedin_channel(token):
    orgs = graphql(token, "query { account { organizations { id } } }")["account"]["organizations"]
    matches = []
    for org in orgs:
        channels = graphql(token, "query($id: OrganizationId!) { channels(input: {organizationId: $id}) { id name service type isQueuePaused } }", {"id": org["id"]})["channels"]
        matches.extend((org["id"], c) for c in channels if c["service"].lower() == "linkedin" and c["type"].lower() == "profile")
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one LinkedIn channel, found {len(matches)}. Configure a single personal profile before enabling publishing.")
    if matches[0][1]["isQueuePaused"]:
        raise RuntimeError("LinkedIn queue is paused in Buffer; no post queued.")
    return matches[0]


def existing_texts(token, org_id, channel_id):
    query = """query($org: OrganizationId!, $channel: ChannelId!) {
      posts(first: 50, input: {organizationId: $org,
        filter: {status: [sent, scheduled], channelIds: [$channel]}}) {
        edges { node { text } } }
    }"""
    result = graphql(token, query, {"org": org_id, "channel": channel_id})
    return [edge["node"]["text"] for edge in result["posts"]["edges"]]


def publish(token, channel_id, text):
    due = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    query = """mutation($text: String!, $channel: ChannelId!, $due: DateTime!) {
      createPost(input: {text: $text, channelId: $channel,
        schedulingType: automatic, mode: customScheduled, dueAt: $due}) {
        ... on PostActionSuccess { post { id text dueAt } }
        ... on MutationError { message }
      }
    }"""
    result = graphql(token, query, {"text": text, "channel": channel_id, "due": due})["createPost"]
    if "post" not in result:
        raise RuntimeError("Buffer rejected post: " + result.get("message", str(result)))
    return result["post"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without Buffer access or publishing")
    args = parser.parse_args()
    today = dt.datetime.now(dt.timezone.utc).date()
    if not args.dry_run and not (dt.date(2026, 11, 23) <= today <= dt.date(2026, 12, 14)):
        print("Outside the four-week news pilot; no post queued.")
        return
    stories = candidates(fetch_feed(), today)
    if not stories:
        print("No sufficiently relevant recent CMS news: skipped publishing.")
        return
    if args.dry_run:
        print(caption(stories[0][2], stories[0][3]))
        return
    token = os.environ.get("BUFFER_API_KEY", "")
    if not token:
        raise RuntimeError("BUFFER_API_KEY is missing; no post published.")
    org_id, channel = linkedin_channel(token)
    posted = existing_texts(token, org_id, channel["id"])
    for _, day, title, link in stories:
        if any(link in text for text in posted):
            continue
        result = publish(token, channel["id"], caption(title, link))
        print(f"Queued CMS story from {day.isoformat()} in Buffer: post ID {result['id']}, due {result['dueAt']}")
        return
    print("All relevant recent CMS stories were already queued or sent; skipped publishing.")


if __name__ == "__main__":
    main()
