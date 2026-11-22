# Free LinkedIn news agent

This job runs every Monday at 13:17 UTC. For the four Mondays from November 23 through December 14, 2026, it scans CMS's official newsroom RSS feed for recent health informatics stories, selects one by headline relevance, writes a short original caption based on Salman's pharmacy operations and business analytics background, checks recent Buffer posts for the article link, and schedules it for two hours after the job runs. Buffer then publishes it automatically. If there is no relevant new story or any connection fails, it does not publish. After December 14, it stops scheduling news.

**Set up:**

1. Create a **free** Buffer account and connect **only your personal LinkedIn profile**. This agent schedules its own time, so you do not need a recurring Buffer queue slot.
2. In Buffer, open Settings → API and create a personal API key. Keep it private; **do not paste it into chat or commit it to GitHub**.
3. Create a GitHub repository and upload `agent.py` and `.github/workflows/post.yml` with the same directory structure. In the repository, open Settings → Secrets and variables → Actions → New repository secret. Name it `BUFFER_API_KEY` and paste the key there.
4. In the repository Actions tab, enable the workflow if prompted. Run `python agent.py --dry-run` locally to preview a story. If you manually use **Run workflow** during the pilot dates, it will schedule a real post; check Buffer immediately afterward. A manual run outside the pilot dates will not schedule anything.

You can preview without publishing with `python agent.py --dry-run`. The feed is public and requires internet access. The GitHub workflow needs internet access to CMS and Buffer.

This is a rule-based agent and deliberately quotes only the article headline. It does not claim to summarize full articles or invent details. After the news pilot, your existing ChatGPT Monday task can keep preparing original experience-based drafts. A future automatic publishing phase needs factual input from you; do not automate invented personal experiences. The separate ChatGPT Monday draft task can be paused for the four pilot weeks once this agent is verified, so you don't get duplicate drafts.

**Limitations:** A missing feed, disconnected LinkedIn profile, full Buffer free queue, or expired API key prevents publishing. GitHub scheduled jobs can be delayed. The job reports scheduling success, which is not the same as confirming that LinkedIn has published the post. Check Buffer's sent/error status after the scheduled time.
