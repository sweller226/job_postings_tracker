# Internship watcher

Get a phone notification when a new Summer 2027 internship is posted.

This project runs as a GitHub Actions workflow. Every 20 minutes, it checks five community-maintained internship lists and sends you a push notification for any posting it hasn't seen before. Tap the notification to open the application page.

There’s no server or database to run. The workflow keeps track of previously seen postings in `state/seen.json` and commits the updated file back to your repository. On a public repo, the whole thing runs for free.

A notification looks like this:

```text
Figma — Software Engineer Intern - Summer 2027

San Francisco, CA

via SimplifyJobs

https://boards.greenhouse.io/figma/jobs/6143238004
```

**What you need:** a GitHub account and a phone with the free [ntfy](https://ntfy.sh) app. Setup takes about five minutes, and you don't need to know Python.

## The lists it watches

| Source                                                                                                                                                            | Format              |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| [vanshb03/Summer2027-Internships](https://github.com/vanshb03/Summer2027-Internships)                                                                             | `listings.json`     |
| [zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships) | `jobs.json`         |
| [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships)                                                                     | README, HTML tables |
| [speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs)                                                                         | README, pipe tables |
| [LorenzoLaCorte/european-tech-internships-2026](https://github.com/LorenzoLaCorte/european-tech-internships-2026)                                                 | README, pipe tables |

Together, these lists contain roughly 3,200 postings matching the current filters, or about **2,450 unique jobs** after duplicates are removed.

The European list is mostly made up of 2026 new-grad roles, so it currently contributes nothing. It's left in the config in case that changes.

Sources are configured in `config.json`, so you can add, remove, or disable them without changing the code.

## What to expect

**Timing.** GitHub doesn't always start scheduled workflows exactly on time. Runs can be delayed by 5–30 minutes, and some may be skipped when GitHub's runners are busy. In practice, "every 20 minutes" means a few checks per hour.

Most postings should reach your phone within a few minutes to about an hour.

**Notifications per run:**

* Up to `max_individual` postings (12 by default) get their own notification.
* Additional postings are grouped into summaries, with one summary for each source.
* For example, you might get a notification saying `+25 more new Summer 2027 postings from SimplifyJobs`.
* Each summary includes up to 20 postings and links back to that list on GitHub.
* A run can send at most 17 notifications, and normally sends around 13–14.

**Volume.** In mid-September 2026, during the busiest part of the recruiting cycle, these lists were adding around **74 new postings per day** after filtering, with some days reaching close to 150. That works out to roughly 50–100 notifications per day. Outside the fall recruiting rush, the volume should be much lower.

**Service limits.** On ntfy.sh, the free tier allows 250 messages per day per IP address, with a burst limit of 60 requests that refills at one request every 5 seconds. Normal usage should stay well below this.

* If the daily limit is already reached when a run starts, every send fails. That run's postings are not marked as seen, so a later run retries them.
* If the limit is reached partway through a run, the remaining notifications from that run are skipped.

If you want fewer notifications, lower `max_individual` or narrow the filters with `title_include`, `location_include`, or `countries`.
