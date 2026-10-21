# Privacy

Polarity is designed around data minimisation. Singapore's PDPA is the context we had in mind; this page describes
how the software behaves and is not legal advice or a compliance claim.

**People.** Students enter a nickname ("Use a nickname — no real names needed"). Bench IDs identify benches, not
people. The TA dashboard shows nicknames only.

**What stays on the bench computer.** The live camera stream, the ring buffer of recent frames, the motion and
quality analysis, the LED detector and all stored records (SQLite at `data/polarity.db`, images and voice clips
under `data/media/<session>/`) stay on the bench. Nothing is uploaded in the background.

**What leaves the bench, and when.** Only when the student presses **Check** or asks a question:

- one image of the board, already cropped and warped to the breadboard area by the marker mat (not the whole room);
- the student's voice clip (up to 15 s), if they spoke a question and the verified audio mode sends audio.

These go to Nebius Token Factory over HTTPS to be judged by NVIDIA Nemotron models. Text-only calls (TA summaries,
the class report, the lab compiler's assembly step) send statistics and attempt histories with nicknames, not images.
Part lookups send only the part number to Tavily. Nebius and Tavily handle that data under their own terms; see
their privacy policies.

**Hub mode.** Benches send session, attempt and help-request records to the TA laptop on the local network. Images are
not sent unless `hub.send_thumbnails: true` is set; raw images and audio are never sent.

**Retention.** Media older than `MEDIA_RETENTION_DAYS` (default 14) is deleted by `python -m polarity purge`; run it
from a scheduled task, or at the end of term. Simulated demo data is flagged in the database and removed with
`python -m polarity seed-demo --clear`.

**Secrets.** API keys live only in `.env` (gitignored). The app never prints a full key (it shows `****abcd`), never
logs request headers, and masks keys in log files.
