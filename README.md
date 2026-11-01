# StepCards

Turn one demonstration video into checked picture step cards — then let a camera show the learner the right card at the right time.

Same eyes on both ends: the person who knows the task films it once through Ray-Ban Meta glasses (first-person, hands free), and the person learning it follows the cards on Ray-Ban Display from the same point of view — so the card photos, the "done" reference and the live camera all look the same way. Without glasses, a phone's back camera held at eye level (or a fixed phone) stands in.

| Meta device / app | What it does in StepCards | Status |
|---|---|---|
| Ray-Ban Meta (camera) | records the demonstration from the doer's eyes | any video file works; tested with first-person videos, not yet with glasses footage |
| Ray-Ban Display | shows the current card, Help / Ask for help / Done, Check result | web app built to Meta's guidance, checked in the simulator, not on physical glasses |
| Glasses camera while following | sees the learner's hands | not built: needs the Wearables Device Access Toolkit (native phone app); a phone camera does this today |
| WhatsApp, Messenger, Instagram | send cards, today's run and follow-along links | through the phone's share sheet |

Built during the Meta AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track, by LogicCraft. All code in this repository was written during the hackathon; the first commit is dated 2026-10-28.

## Try it

Live: https://stepcards-production.up.railway.app

- Viewing needs no key: open a sample under "In the café, the kitchen, the classroom" on the home page (the napkin fold is the quickest), look through the cards, then "Follow & check" → "Tablet view", or "Glasses view" for the 600×600 Ray-Ban Display page.
- Making cards from your own video, editing, drawings, Check, translation and Coach mode call the Meta Model API, so the app asks once for an access key. Judges: use the judge key from the submission form (it has a daily limit). Without a key, Coach mode still runs but cards move only by hand.
- A 30-second path: napkin sample → "Follow & check" → "Start following & checking" → choose "Help only when needed" and start (allow the camera) → press Help a few times to see text → picture → sound → motion → "Ask for help", then, signed in with the key, open the same card set's Follow & check page in another tab to see the live board and press "On my way".

## The problem

Special-education teachers teach job skills (making a drink, doing laundry, packing) with task-analysis cards: one action per card, one photo, one short sentence. Today they make these by hand — film the task, pause, screenshot, write a sentence, print. StepCards does the first draft from a single video, checks it with code, and leaves the teacher in charge of the final version.

## Who it's for

Built first for the hardest case — learners with intellectual disabilities, where every step has to be right and checked by a teacher. The same structure (one video → checked cards → follow along by camera, tablet, phone or glasses) fits anywhere someone has to follow someone else's exact way of doing a hands-on task:

| Situation | Who makes the cards | Who follows |
|---|---|---|
| Special-education job training | teacher | student |
| New staff training (cafés, kitchens, warehouses) | senior staff | new hires, including migrant workers (Korean and English cards) |
| Follow-along versions of creators' videos (e.g. teens filming POV "how to" Reels with Ray-Ban Meta) | the creator, from their own video | viewers — and the cards they got stuck on go back to the creator |
| Assembly and setup | the maker | first-time buyers |
| Family know-how (a parent's recipe) | family | family |

Cards have also been made from 26 open (CC BY) demonstration videos matching jobs in Korea's 2026 national disability job program (care support, towel handling, library shelving, mail, cleaning and washing jobs); five of them ship as samples. Cards have been made and checked from six sample videos, one or more per row above: two latte videos (first-person, and a creator's recipe video), napkin folding, a Shoki dance lesson, a bedside-cabinet manual video and a family stew recipe. None of these situations has been tried with real learners or staff yet.

## What it does

1. **Add a video** of someone doing a hands-on task once (first-person, like smart glasses, works well).
2. **Making the cards**
   - Frames are taken every second (ffmpeg).
   - **Muse Voice Transcribe** writes down what was said, with times. Spoken amounts and names (for example "18 g", "caramel syrup") go into the sentences.
   - **Muse Spark** splits the video into one-action steps: start, end, best moment, a plain Korean sentence, an English sentence, the object in hand and how it looks.
   - **A code checker** (no model) tests every step: times inside the video, no overlaps, the chosen moment inside the step, sentence length, one action per sentence, Korean polite ending, two common Korean spelling mistakes. If a rule fails, the reasons go back to Muse Spark and it tries again (up to twice). Whatever still fails is shown to the teacher.
   - **SAM 3.1** finds the object in the worker's hand (by name, then by appearance) and outlines it. If the object does not touch a hand in the chosen frame, other moments in the step are tried.
3. **Check & edit**: ask Muse Spark in plain words ("simpler words for a learner who reads little"). It works as an agent: it proposes new sentences, calls the code checker as a tool, fixes what fails, and answers; the code then judges the final proposal again. The teacher sees each change (old → new) and applies or closes it, with Undo. Then show each card as a photo, a drawing (Muse Image) or motion (a silent loop of up to 4 s around the chosen moment, cut from the video — useful for dance and other movements a still cannot show); edit sentences in place (autosave, re-checked on every save), move, merge, remove or add cards, choose another frame from a filmstrip, fix times and object names. Problems appear on the card in plain words.
4. **Use**: send the cards as images through the phone's share sheet (messengers, text) or save them as one image, print six cards per A4 page (plus a task-analysis record sheet for the teacher), flip through on a tablet, or start **Coach mode**.
5. **Check (확인하기)**: on the tablet, phone or Coach screen the learner presses Check; after 3-2-1 one photo is compared with that card's completion reference — the demonstration frame where the step ends (the teacher can move it) plus an optional teacher-written "done when" sentence. Muse Spark answers done / not yet / different / can't see, with one short instruction; code has the last word (low confidence becomes "can't see", missing or long hints fall back to the card sentence). It judges the result state of the step, not how the hands move. No praise or score: "different" shows the reference beside the photo and raises the help level. On the glasses, Check asks the paired Coach screen's camera to take the photo and the result appears on the lens. Photos are not stored. Optional per-device learning records (no names: date, card, check result, help level) for the teacher. Measured so far (same-video smoke test, napkin frames before/after 6 steps): 10 of 12 right — a flip step looks the same before and after and fooled it; about 2.7 s and $0.005 per check. `verify_eval.py` measures accuracy on any folder of `<card>_ok_*.jpg` / `<card>_bad_*.jpg` photos.
   Experimental, hidden unless the address has `?lab=1` (it is Google's MediaPipe, not a Meta model): on this device, a small MediaPipe image embedder (MobileNetV3-small, 4 MB) runs in the browser, turns the demonstration's 1-second frames into embeddings (each frame already belongs to a card by its time), and matches the camera against them several times a second by nearest-neighbour vote — no server calls, no cost, frames stay on the device. On a replay of the napkin video (the same video the frames came from, so this is an upper bound, not an independent test): ready in 2.0 s, about 22 ms per frame on a Mac, all 12 cards advanced in order, median about 1 s from each card's start (range −4.9 to +5.3 s), versus 6–8 s late with the cloud decision. Result checks ("different") stay with Muse Spark through Check.
   Teacher's voice: cards are read in a person's voice when one exists — the teacher's own recording (record per card in the editor), or the demonstrator's speech cut from the video at that card's time using Muse Voice Transcribe's timings; video speech is only used after the teacher listens and ticks "Use for this card", because demonstrations mix in chatter. Otherwise a natural installed device voice reads the sentence (Meta Model API has no speech synthesis).
   Live checking: while Coach mode runs, the same decision call every 2–4 s also gets the current card's reference photo and reports done / not yet / different; "done" counts as the step finished, and "different" twice in a row shows the reference and one instruction without stopping the learner (once per card, help level up, also on the glasses). It is near-real-time (one decision every few seconds), not frame-by-frame.
   Stuck cards go back to the maker: the editor lists cards that people following them often got stuck on — from the learning records (sound or motion help on at least half the runs, or "different / not yet" twice in Check) or from the Coach run that just ended on this device ("Fix the cards that were hard" on the end screen, nothing stored). "Get a fix" asks the same Muse Spark agent to rewrite only that card, checked by the code checker; the maker applies it or not.
   Ask for help (connecting people, not replacing them): when the help ladder runs out, the person who made the cards is called — by the learner ("Ask for help" on the phone, or on the glasses where Help becomes Ask for help at the last level), or automatically when the last help level still doesn't get the step done, or Check / live checking says "different" twice. The maker's Follow & check page shows a live board of everyone following that card set (pairing code, card, help level, calls first, a short beep); "On my way" clears the call and the learner's phone and glasses show "Help is on the way". Only card numbers and help levels travel — no video, photos or names. Calls clear by themselves when the learner moves to the next card.
6. **Coach mode**: a camera watches the learner. Muse Spark looks at the last two frames and says which step is happening; SAM 3.1 confirms the object in hand before the next card appears. If a later step shows up, the current card is shown again first; if it shows up twice in a row, the cards follow the learner. No praise, no scores, nothing stored — camera frames are never saved. Optional "help only when needed" (a prompt hierarchy, as in special-education practice): each card starts as text only; if the step takes more than twice as long as in the demonstration (10–60 s), or the learner presses Help (also on the glasses), it adds the picture, then reads it aloud (skipped if the teacher turned sound off), then plays the motion clip. On the last card, when the model sees the step finished twice in a row (or someone presses Done), a plain "All steps done" screen appears, with how far help went on each card; this is shown once and not saved. Back and Next always work by hand. "Share today's run" on the end screen sends one line (for example "Finished all 12 steps … Needed help on cards 3, 7 with picture") and the view-only card link through the phone's share sheet — to a parent, a manager or family; no names or photos, and only when someone presses it.

7. **Glasses display** (`/glasses?run=<id>`): a 600×600 web app for Meta Ray-Ban Display. Black background (transparent on the glasses' additive display), focus-and-select controls only, about 16 KB first load. It shows the same card as Coach mode, and Back/Next on the glasses move Coach mode too. Checked in Meta's Ray-Ban Display Simulator (Chrome extension) and built to Meta's web-app guidance (toolkit colours and 88 px buttons, drawings shown on a see-through black background, one action per press, system Back asks before leaving). Not yet tested on physical glasses. Today the camera is a phone or tablet and the glasses are the display and Help/Next input; a glasses camera through Meta's Wearables Device Access Toolkit (a native phone app) is the next step.

The interface is available in Korean and English (switch at the top right). Card text can be Korean, English, or both — plus one more language for the people around the learner (a parent's language, a coworker's language). Muse Spark translates the cards; a second call that never sees the original translates them back into Korean and English so the maker, who may not read that language, can check the meaning; code flags any number from the original missing in the translation. The extra language reaches print, tablet, card images and glasses only after the maker presses "I've checked it", and is unconfirmed again whenever a card sentence changes. Measured once: 27 cards of the stew recipe into Vietnamese in 16 s for about $0.024, no number flags; the back-translation showed one card where "split the tofu" came back as "separate the tofu". Translation quality is not otherwise measured.

## Meta models used

| Model | Used for |
|---|---|
| `muse-spark-1.3` | splitting into steps and writing sentences; Coach mode step recognition (`reasoning.effort = minimal`) |
| `muse-spark-1.3` (agent) | teacher-request agent: rewrites sentences, calling the code checker (`check_cards` tool) until it passes; the same agent rewrites a single card people often got stuck on |
| `muse-spark-1.3` | Check and live checking: compares the learner's photo with the step's completion reference |
| `muse-spark-1.3` | one more card language: translation, then an independent back-translation that never sees the original |
| `sam-3.1` | outlining the object in hand; confirming the object before Coach mode moves on |
| `muse-voice-transcribe-1.0` | transcribing what the demonstrator says (`/v1/asr/transcribe`, endpointing mode) |
| `muse-image-1.0` | drawing cards: redraws a card's photo as a simple illustration, with one fixed style for every card (`/v1/images/edits`) |
| `Muse Glimmer 30B` (open weights) | optional, on this Mac: making cards (step splitting and sentences), Coach mode step recognition and Check — video and camera frames never leave the computer |

All other calls go to the Meta Model API (`https://api.meta.ai/v1`).

## Measured so far

From runs recorded in this build (small samples, see notes):

- 6 min 2 s first-person latte video → 19 cards in 2.9 min for about $0.20 (another run: 22 cards, 3.4 min, about $0.36).
- 3 min 13 s latte video → 15–17 cards for about $0.09–0.12 per run (4 runs).
- The checker sends failures back with reasons. Example: on the family-recipe video the first answer wrote "썰으세요" (a common misspelling of "써세요", slice) on 5 cards; the checker named each one, and the second answer passed. Across recorded runs most first answers already pass.
- Coach mode, replaying the same video the cards were made from as the camera (a replay test, not live use): about 3.6 s per decision (two frames, minimal reasoning; 4 frames with default reasoning took 9–11 s), about $0.08 per minute.

- Coach mode on this Mac with Muse Glimmer 30B (Q4 GGUF, llama.cpp, 48 GB Apple Silicon): reached the last card in the same replay test at about 4.7 s per decision, $0. Glimmer writes a long reasoning trace first (18–21 s per answer); pre-filling the start of the JSON answer skips it with about the same accuracy (Glimmer 15 and 13 of 16 cards, Muse Spark 15 and 14, on two single-frame-pair tests). The SAM check is skipped in this mode because SAM runs on the API.

- Making cards on this Mac with Muse Glimmer, end to end in the app ("On this Mac" on upload, same prompt, checker and retries): napkin video (2 min 20 s) → 11 cards in 172 s for $0; the checker found 3 problems in the first answer, 1 in the second, and the third passed. 8 of the 10 steps in the video's own captions (Muse Spark: also 8 of 10; both missed the last two shaping steps); differences: Glimmer added a "pick up the napkin" card and one step the captions don't have. With the model file on the Mac's internal SSD the model server starts in about 3 s. An earlier script run on the dance video found the same 3 steps as the instructor's captions; its Korean sentences were rougher than Muse Spark's (one misspelling the checker caught but the model could not fix).

Step accuracy against the sample videos' own on-screen step captions (not a teacher's task analysis):

| Sample | Steps in the video's captions | Matched by the cards |
|---|---|---|
| Napkin butterfly fold | 10 | 8 (the last two shaping steps, mostly off-screen, were missed) |
| Shoki dance | 3 | 3, with matching times |
| Bedside cabinet (manual video) | 16 numbered steps | cards follow steps 1–16 in order |

Not measured yet: time to make the same cards by hand, and step accuracy against a teacher's own task analysis.

## Run it

Requirements: Python 3.11+, ffmpeg, a Meta Model API key.

```bash
python3 -m venv .venv
.venv/bin/pip install openai python-dotenv pillow requests fastapi uvicorn python-multipart segno pytest
echo 'MODEL_API_KEY=...' > .env          # never commit this file
.venv/bin/python app.py                  # http://127.0.0.1:8790
```

Optional, making cards and Coach mode on this Mac: download `Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf` and `mmproj-Muse-Glimmer-30B-Q4_K_M.gguf` from `meta-models/Muse-Glimmer-30B-GGUF`, then

```bash
llama-server -m Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --mmproj mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -c 32768 -ngl 99 --port 8791
```

When that server is running, the home page offers "On this Mac (Muse Glimmer)" for making cards and the Coach screen offers it for Coach mode. Making cards on this Mac uses the same prompt, code checker and retries, sends nothing to the API (speech transcription and SAM outlines are skipped), and gives frames 2–3 s apart to fit the 32K context.

Deploy (for example Railway, from this GitHub repository): the `Dockerfile` installs ffmpeg and the Python packages. Set these variables on the host:

| Variable | Value |
|---|---|
| `MODEL_API_KEY` | Meta Model API key |
| `APP_KEY` | the admin access key; anyone can view the cards, but adding videos, drawings, 3D folds, translation, the agent and edits ask for a key once (they cost credits or change cards). Learner devices need no key for Coach decisions, Check and learning records, within a daily limit per card set (900 decisions, 300 checks) |
| `JUDGE_KEY` | optional second key for judges: everything works on card sets they upload (samples are read-only), with daily limits on the calls that cost credits (6 videos, 60 drawings, 20 agent requests, about 30 minutes of Coach mode) |
| `TEACHER_KEYS` | optional per-teacher keys, `name:key,name:key`: each teacher sees the samples plus their own card sets, and can edit or delete only their own (Coach mode works on any set). `APP_KEY` stays the admin key |
| `ALERT_WEBHOOK` | optional webhook URL (Discord or Slack style): a one-line alert when card making stops or the server hits an unhandled error |
| `COMPACT_DAYS` / `ARCHIVE_DAYS` / `RETAIN_DAYS` / `CACHE_DAYS` | storage lifecycle (14 / 90 / off / 30 days), see Running it for real |
| `TEACHER_QUOTA_MB` / `TEACHER_MAX_SETS` | per-teacher storage limits (5000 MB / 50 sets) |
| `STEP_MODEL` / `SAM_MODEL` / `ASR_MODEL` | model names, if Meta renames or retires one |
| `DATA_DIR` | required in deployment: a persistent volume path (for example `/data`), so card sets, the state file and the spend ledger survive redeploys |
| `SPEND_CAP_USD` | credit cap (default 140): once the spend ledger reaches it, every request that calls the Meta API is refused (viewing and turning cards by hand keep working) |
| `SPEND_ALREADY_USD` | spend that happened outside this server's ledger (read it from the Meta developer console's billing page); added to the ledger total |

The key is asked inside the app the first time an action needs it; a cookie keeps it for 30 days. On the glasses, add the web app as `https://<host>/glasses?run=<id>` (the Use page shows QR codes for it and for the tablet view). A phone camera or glasses web app needs HTTPS, which the host provides.

Command line only: `.venv/bin/python pipeline.py video.mp4 [--fresh]`. Results go to `runs/<hash of the video>/` (not committed).

Tests (checker, server, Coach decisions; no paid model calls): `.venv/bin/pip install pytest httpx && .venv/bin/python -m pytest -q`

## Files

| File | What it is |
|---|---|
| `pipeline.py` | frames → speech → steps (with check and retry) → photos and outlines |
| `check.py` | the code-only rule checker |
| `coach.py` | Coach mode decision (Muse Spark + SAM 3.1) |
| `agent.py` | teacher-request agent (Muse Spark with the checker as a tool) |
| `verify.py`, `verify_eval.py` | Check: compare one photo with a card's completion reference; accuracy measurement |
| `coach_report.py` | Test runs: open Coach with `?log=1` to log decisions, card changes, checks and help levels (no photos, no names); this script turns one run into numbers (cards advanced automatically and kept, median decision time, check results) |
| `storage.py` | storage lifecycle, quotas, teacher-data backup |
| `app.py` | local web server (FastAPI) |
| `static/index.html` | the whole interface, one file |
| `coach_sim.py`, `coach_bench*.py` | Coach mode replay test and latency measurements |
| `exp1-3.py` | first experiments (video input modes, stability, SAM prompts) |
| `demo/` | scripted screen recording and demo video assembly |

## Running it for real

- **Who sees what**: without a key, the home page lists only the sample sets; card sets that teachers upload are unlisted and open only by their link (an unguessable id), which is what the QR codes carry.
- **Accounts**: one admin key, optional per-teacher keys (own sets only), and a judge key with daily limits. Every change to a card set is appended to its `audit.jsonl` (who, when, what).
- **Several learners at once**: each Coach screen has its own pairing code, and its glasses link carries that code, so learners using the same card set don't move each other's cards. This state and the judge-key usage survive restarts (`state.json`).
- **Cost guards**: Coach mode pauses its camera after 5 minutes without a step change; uploads are limited to 500 MB and 10 minutes on the server, and refused when less than 2 GB is free.
- **Restarts**: card making that was interrupted by a restart or redeploy is marked as stopped, so "Try again" appears instead of an endless "Making".
- **Health and alerts**: `/api/health` (free space, jobs, key present) is Railway's health check (`railway.json`); `ALERT_WEBHOOK` sends failures to a chat.
- **Storage over time** (`storage.py`, runs every 6 hours): the audio file is deleted once speech is transcribed; a card set unused for `COMPACT_DAYS` (14) keeps a 640 px silent copy of its video instead of the original and drops its 1-second frames and caches (frames come back from the copy when the frame strip is opened); after `ARCHIVE_DAYS` (90) only cards, drawings and text are kept; with `RETAIN_DAYS` set, sets are deleted after that many days, with a warning on the home and edit pages for the last 7 days. Each teacher has a quota (`TEACHER_QUOTA_MB` 5000, `TEACHER_MAX_SETS` 50). Measured on the samples, compacting cuts a set by roughly three quarters. Design notes: per-component sizes and the full lifecycle.
- **Admin page** (`#view=admin`, admin key): every card set with owner, stage, last use and size by part; per-owner totals; compact, archive, .zip and delete buttons.
- **Backups**: a teacher-data backup (cards, drawings, titles, owners, audit; no video) is written every day to `backups/` and kept for 7 days, downloadable from the admin page; each card set also downloads as a .zip from the Use page. Railway volume backups need a paid plan.
- **Without an API key** (for example after the hackathon credit ends) the site still starts: viewing, printing, tablet and glasses views work, and cards can still be made on a school computer with Muse Glimmer. A school deployment should use its own paid Meta API key, or Glimmer for anything involving students.
- **Reproducible builds**: the base image is pinned (`python:3.14.8-slim`) and Python packages are pinned in `requirements.txt`.

## Privacy

- Run on your own computer, videos and cards stay there (`runs/`). The hosted demo sends frames to the Meta Model API to make cards and run Coach mode.
- Do not use videos of students. Our tests and demo use adult demonstrations only.
- Coach mode never stores camera frames and keeps no records of the learner.
- For school use, both making cards and Coach mode can run on Muse Glimmer on the school's own computer, so student video never leaves it.

## Credits

- Design patterns (checks built into the pipeline instead of left to the model, code-only verdicts, retry with reasons, content-hash caching, SAM box tokens, progress board) were learned from Meta's hackathon workshop repository `meta-models/legal-agent-workshop`. No code was copied from it.
- Sample videos used for testing and the demo (not included in this repository unless noted):
  - "POV Morning Latte in Costa Rica ASMR" by Cornffy, YouTube `vqv_DMMDqC8`, CC BY. Korean narration was added with a synthetic voice for testing.
  - Starbucks black glazed latte recipe by 베란다스튜디오, YouTube `sjgucMN4Aa8`, CC BY.
  - "Napkin Folding - Butterfly" by maitp, YouTube `jaHe0SBRLVA`, CC BY. 
  - "How to SHOKI - Quick dance tutorial by Afro 101" by AFRO 101, YouTube `DgqYEe7sIQw`, CC BY.
  - "30년 장사한 엄마의 첫 레시피, 10분 바지락 순두부찌개" by 장사만30년미화씨, YouTube `GStjzzIi4ew`, CC BY.
  - "Barcelona 2 drawer bedside Assembly Instructions" by INSIDE HOUSE, YouTube `RIJc1qKefGg`, CC BY.
  - National disability job samples (home page "Cards for Korea's national disability jobs"): "Car Transfers With Transfer Belt" by PT Shan, YouTube `708QT4y6lco`; "Oral Care" by WisTech Open | Open RN, YouTube `SQEjgHODEz0`; "호텔수건접기, 수건 예쁘게 개기, 쉽게 개는방법까지" by 귀주부, YouTube `KKSIl9gbeBY`; "Basic Shelving 2011" by thirdpresident, YouTube `-qOS2Uyu1Tw`; "수어배우기 [초급반] 제2강 인사" by 박광철 목사, YouTube `UktSega5kmU` — all CC BY (licence read from each video's YouTube metadata on 2026-11-01). Job names come from the Ministry of Health and Welfare's public guide 「2026년 장애인일자리 사업안내」 (2026-01-05): the 11 jobs tailored for people with severe disabilities are on p.70 (D&D Care and Deaf-to-deaf peer care, 농-농케어, are among them); towel handling and book arrangement are other welfare-job duties on p.70–74.
  - Sample card sets in `seed/` (shown on a fresh deployment, one per use case) include small silent copies of the CC BY videos above.
