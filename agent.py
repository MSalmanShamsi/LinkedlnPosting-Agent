"""Weekly LinkedIn publisher: CMS news -> OpenAI draft -> Buffer."""
import argparse
import datetime as dt
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

FEED = "https://www.cms.gov/newsroom/rss-feeds"
API = "https://api.buffer.com"
OPENAI_API = "https://api.openai.com/v1/responses"
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


def caption(title, link, key):
    """Generate original copy; only the headline is supplied as article evidence."""
    prompt = (
        "Write a LinkedIn post for Muhammad Salman Shamsi, an operations analyst "
        "in pharmacy healthcare with an MS in Business Analytics. He works with "
        "pharmacy operations data, insurance claim issues, billing reconciliation, "
        "and data accuracy.\n"
        "Use this CMS headline as the topic, not as evidence of details inside the article:\n"
        f"{title}\n\n"
        "Write 100-160 words in first person, with a clear hook, one practical "
        "analytics or operations perspective, and one specific question at the end. "
        "Sound thoughtful and natural. Do not claim to have read the article, cite "
        "statistics, describe specific policy changes or outcomes, or invent a "
        "personal anecdote. Do not quote the headline verbatim or write a link-only "
        "announcement. No markdown formatting, no URLs, no hashtags. Output only "
        "the post text."
    )
    payload = json.dumps({"model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                          "input": prompt, "max_output_tokens": 500}).encode()
    req = urllib.request.Request(OPENAI_API, data=payload, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.load(response)
    if result.get("status") != "completed":
        raise RuntimeError("OpenAI did not finish the draft; nothing queued.")
    draft = "\n".join(part.get("text", "") for item in result.get("output", [])
                      for part in item.get("content", []) if part.get("type") == "output_text").strip()
    if not 60 <= len(draft.split()) <= 210 or "http" in draft.lower():
        raise RuntimeError("Generated draft failed length or link validation; nothing queued.")
    return f"{draft}\n\nSource: {link}\n\n#HealthcareAnalytics #PharmacyOperations"


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
    parser.add_argument("--dry-run", action="store_true", help="Generate a preview without Buffer access or publishing")
    args = parser.parse_args()
    today = dt.datetime.now(dt.timezone.utc).date()
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is missing; nothing queued.")
    stories = candidates(fetch_feed(), today)
    if not stories:
        print("No sufficiently relevant recent CMS news: skipped publishing.")
        return
    if args.dry_run:
        print(caption(stories[0][2], stories[0][3], openai_key))
        return
    token = os.environ.get("BUFFER_API_KEY", "")
    if not token:
        raise RuntimeError("BUFFER_API_KEY is missing; no post published.")
    org_id, channel = linkedin_channel(token)
    posted = existing_texts(token, org_id, channel["id"])
    for _, day, title, link in stories:
        if any(link in text for text in posted):
            continue
        generated = caption(title, link, openai_key)
        result = publish(token, channel["id"], generated)
        print(f"Queued CMS story from {day.isoformat()} in Buffer: post ID {result['id']}, due {result['dueAt']}")
        return
    print("All relevant recent CMS stories were already queued or sent; skipped publishing.")


if __name__ == "__main__":
    main()
