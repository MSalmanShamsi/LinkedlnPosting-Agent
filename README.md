# Weekly LinkedIn posting agent

Every Monday at 13:17 UTC, GitHub Actions scans the official CMS newsroom RSS feed for a relevant headline. The OpenAI API writes an original post about its implications for pharmacy operations and business analytics. The script checks Buffer for that article URL and, if it is new, schedules the post on the connected personal LinkedIn profile for two hours later. If the feed, generation, or Buffer call fails, the run fails without queuing a post. A successful GitHub run means Buffer accepted a scheduled post; check Buffer's sent status after the due time to confirm LinkedIn publication.

## Setup

1. Connect your personal LinkedIn profile to Buffer and create a Buffer API key in Buffer Settings → API.
2. Create an OpenAI Platform API key with API billing enabled. ChatGPT subscription access is separate from API billing.
3. In this repository, open Settings → Secrets and variables → Actions and add `BUFFER_API_KEY` and `OPENAI_API_KEY` as repository secrets. Never commit keys or paste them into an issue or chat.
4. Run the workflow manually from Actions to queue one post, then inspect its text and scheduled time in Buffer. To generate a preview without sending to Buffer, run `python agent.py --dry-run` locally with `OPENAI_API_KEY` set in your environment.

The default model is `gpt-4.1-mini`. Set `OPENAI_MODEL` as a workflow environment variable if you prefer another model available to your API account. The prompt receives only the CMS headline, so it explicitly avoids unsupported article claims. The source link is appended by the script after generation. Posting continues weekly while the workflow is enabled and a relevant, unposted story appears within the last 21 days. GitHub scheduled runs may start later than the configured time.

Buffer's API does not support reading and replying to LinkedIn comments; handle engagement manually in Buffer or LinkedIn.
