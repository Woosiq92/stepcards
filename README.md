# StepCards

Film a task once and get checked picture step cards. Then a camera shows the learner the right card at the right time.

Demo video: https://youtu.be/WUuhKDdM5CM

Both ends see the task from the same eyes. The person who knows the task films it once through Ray-Ban Meta glasses (first-person, hands free). The person learning it follows the cards on Ray-Ban Display from the same point of view. So the card photos, the "done" reference and the live camera all look the same way. Without glasses, a phone's back camera held at eye level (or a fixed phone) stands in.

| Meta device / app | What it does in StepCards | Status |
|---|---|---|
| Ray-Ban Meta (camera) | records the demonstration from the doer's eyes | any video file works; tested with first-person videos, not yet with glasses footage |
| Ray-Ban Display | shows the current card, Help / Ask for help / Done, Check result | web app built to Meta's guidance, checked in the simulator, not on physical glasses |
| Glasses camera while following | sees the learner's hands | not built: needs the Wearables Device Access Toolkit (native phone app); a phone camera does this today |
| WhatsApp, Messenger, Instagram | send cards, today's run and follow-along links | through the phone's share sheet |

LogicCraft built StepCards during the Meta AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track. All code in this repository was written during the hackathon; the first commit is dated 2026-10-28.

## Try it

Live: https://stepcards-production.up.railway.app

- You can look around without a key. On the home page, press "See it work · no camera" first. It opens the napkin sample and plays the demonstration video in place of a camera while Muse Spark turns the cards. Then open a sample under "In the cafe, the kitchen, the classroom" and look through the cards, or press "Follow & check" → "Tablet view", or "Preview the lens view" for the 600×600 Ray-Ban Display page.
- Making cards from your own video, editing, drawings, Check, translation and Coach mode call the Meta Model API, so the app asks once for an access key. Judges: use the judge key from the submission form (it has a daily limit). Without a key, Coach mode and Check still work on any card set within a shared daily limit per set (learner devices need no key). On the samples, "Watch the demo" moves the cards by itself. Samples are read-only, so press "Edit" to try editing and Ask on your own copy.
- No camera at hand? Press "See it work · no camera" on the home page, or "Watch the demo" in Coach mode on a sample. It plays the demonstration video (CC BY) as the camera and makes live decisions, so you can see cards move on by themselves. This doesn't work for card sets that makers upload.
- A 30-second path: napkin sample → "Follow & check" → "Start following & checking" → choose "Help only when needed" and start (allow the camera) → press Help a few times to see text → picture → sound → motion → "Ask for help". Then sign in with the key, open the same card set's Follow & check page in another tab, look at the live board and press "On my way".

## The problem

Special-education teachers teach job skills (making a drink, doing laundry, packing) with task-analysis cards: one action per card, one photo, one short sentence. Today they make these by hand. They film the task, pause, take a screenshot, write a sentence and print. StepCards makes the first draft from a single video and checks it with code. The teacher stays in charge of the final version.

## Who it's for

We built it first for learners with intellectual disabilities, because that is the hardest case: every step has to be right and checked by a teacher. The same structure (one video → checked cards → follow along by camera, tablet, phone or glasses) fits anywhere someone has to follow another person's exact way of doing a hands-on task. Anyone who knows a task and films it once can be the maker.

| Situation | Who makes the cards | Who follows |
|---|---|---|
| Special-education job training | teacher | student |
| New staff training (cafés, kitchens, warehouses) | senior staff | new hires, including migrant workers (Korean and English cards) |
| Follow-along versions of creators' videos (e.g. teens filming POV "how to" Reels with Ray-Ban Meta) | the creator, from their own video | viewers; the cards they got stuck on go back to the creator |
| Assembly and setup | the maker | first-time buyers |
| Family know-how (a parent's recipe) | family | family |

We have also made cards from 26 open (CC BY) demonstration videos that match jobs in Korea's 2026 national disability job program (care support, towel handling, library shelving, mail, cleaning and washing jobs). Five of them ship as samples. We made and checked cards from six sample videos, at least one per row above: two latte videos (first-person, and a creator's recipe video), napkin folding, a Shoki dance lesson, a bedside-cabinet manual video and a family stew recipe. None of these situations has been tried with real learners or staff yet.

## What it does

1. Add a video of someone doing a hands-on task once, or press "Record with camera" to film it in the browser. First-person video, like from smart glasses, works well.
   The card set list works like blog categories. Each set sits in one folder, and folders can be renamed and show how many sets they hold. You can search by title, filter by Not checked / Checked / Making / Archived, and sort by recently edited, recently used or name. Select mode moves several sets to a folder or deletes them at once.
2. Making the cards
   - ffmpeg takes a frame every second.
   - Muse Voice Transcribe writes down what was said, with times. Spoken amounts and names (for example "18 g", "caramel syrup") go into the sentences.
   - Muse Spark splits the video into steps of one action each. For every step it gives the start, the end, the best moment, a plain Korean sentence, an English sentence, the object in hand and how that object looks.
   - A code checker (no model) tests every step: times inside the video, no overlaps, the chosen moment inside the step, sentence length, one action per sentence, the Korean polite ending, and two common Korean spelling mistakes. If a rule fails, the reasons go back to Muse Spark and it tries again (up to twice). Whatever still fails is shown to the maker.
   - SAM 3.1 finds the object in the worker's hand (by name, then by appearance) and outlines it. If the object does not touch a hand in the chosen frame, it tries other moments in the step.
3. Check & edit: ask Muse Spark in plain words ("simpler words for a learner who reads little"). It works as an agent. It proposes new sentences, calls the code checker as a tool, fixes what fails and answers, and then the code judges the final proposal again. The maker sees each change (old → new) and applies or closes it, with Undo.
   Each card can show a photo, a drawing (Muse Image) or motion. Motion is a silent loop of up to 4 s around the chosen moment, cut from the video, for dance and other movements a still cannot show. You can edit sentences in place (autosave, re-checked on every save), move, merge, remove or add cards, pick another frame from a filmstrip, and fix times and object names. Problems appear on the card in plain words.
   The editor also adds yellow notes, which do not block anything, for numbers that were not in the video's speech and for left/right. Pressing "Done → Follow & check" records that the maker checked the cards. Editing a card afterwards clears that mark, and Coach start and the tablet then show "not checked by the maker yet". Samples count as checked.
4. Use: send the cards as images through the phone's share sheet (messengers, text) or save them as one image. You can also print six cards per A4 page (plus a task-analysis record sheet for the maker), flip through them on a tablet, or start Coach mode.
5. Check (확인하기): on the tablet, phone or Coach screen the learner presses Check. After 3-2-1 the app takes one photo and compares it with that card's completion reference. The reference is the demonstration frame where the step ends (the maker can move it), plus an optional "done when" sentence the maker writes. Muse Spark answers done / not yet / different / can't see, with one short instruction. Code has the last word: low confidence becomes "can't see", and missing or long hints fall back to the card sentence. It judges how the work ends up after the step, not how the hands move. There is no praise or score. "Different" shows the reference beside the photo and raises the help level. On the glasses, Check asks the paired Coach screen's camera to take the photo, and the result appears on the lens. Photos are not stored. The maker can turn on learning records per device (no names: date, card, check result, help level). Measured so far (same-video smoke test, napkin frames before/after 6 steps): 10 of 12 right. A flip step looks the same before and after and fooled it. Each check takes about 2.7 s and costs about $0.005. `verify_eval.py` measures accuracy on any folder of `<card>_ok_*.jpg` / `<card>_bad_*.jpg` photos.
   Experimental, hidden unless the address has `?lab=1` (it is Google's MediaPipe, not a Meta model): a small MediaPipe image embedder (MobileNetV3-small, 4 MB) runs in the browser on this device. It turns the demonstration's 1-second frames into embeddings (each frame already belongs to a card by its time) and matches the camera against them several times a second by nearest-neighbour vote. There are no server calls and no cost, and frames stay on the device. We replayed the napkin video, which is the same video the frames came from, so this is an upper bound and not an independent test. It was ready in 2.0 s and took about 22 ms per frame on a Mac. All 12 cards advanced in order, a median of about 1 s from each card's start (range −4.9 to +5.3 s), against 6–8 s late with the cloud decision. Result checks ("different") stay with Muse Spark through Check.
   Maker's voice: when a person's voice exists for a card, the card is read in that voice. It can be the maker's own recording (recorded per card in the editor), or the demonstrator's speech cut from the video at that card's time using Muse Voice Transcribe's timings. Demonstrations mix in chatter, so video speech is used only after the maker listens and ticks "Use for this card". Otherwise Google Cloud Text-to-Speech reads the sentence with the Chirp 3 HD voice Zephyr (ko-KR / en-US), cached per sentence. Without the `GTTS_KEY` variable, or when that call fails, the device voice reads it as before.
   Live checking: while Coach mode runs, the same decision call every 2–4 s also gets the current card's reference photo and reports done / not yet / different. "Done" counts as the step finished. "Different" twice in a row shows the reference and one instruction without stopping the learner (once per card, help level up, also on the glasses). This is near-real-time (one decision every few seconds), not frame-by-frame.
   Stuck cards go back to the maker: the editor lists cards that people often got stuck on. It finds them in the learning records (sound or motion help on at least half the runs, or "different / not yet" twice in Check) or in the Coach run that just ended on this device ("Fix the cards that were hard" on the end screen, nothing stored). "Get a fix" asks the same Muse Spark agent to rewrite only that card, and the code checker checks it. The maker decides whether to apply it.
   Ask for help connects people instead of replacing them. When the help ladder runs out, someone who can help is called. The learner can call ("Ask for help" on the phone, or on the glasses, where Help becomes Ask for help at the last level). The call also goes out by itself when the last help level still doesn't get the step done, or when Check or live checking says "different" twice. The card set's Follow & check page shows a live board of everyone following that set (pairing code, card, help level, calls first, a short beep). "On my way" clears the call, and the learner's phone and glasses show "Help is on the way". Only card numbers and help levels travel; no video, photos or names. Calls clear by themselves when the learner moves to the next card.
6. Coach mode: a camera watches the learner. Muse Spark compares the last two camera frames with reference photos from the demonstration video: how the work looks before the current step, after it, and after the next two steps. It answers which one the work looks like. Each decision sends 6 images (2 camera frames + 4 reference photos). Matching pictures instead of reading sentences is what makes the later steps work; with sentences only, the napkin replay stopped at card 6 or 7 of 12.
   When the picture on screen stops moving, the app doesn't wait. It watches the change from frame to frame on a 32×18 grayscale copy, and when that drops from 4 or more to under 2, it sends one extra decision without waiting for the one in flight (at most 2 at a time).
   Some guards keep cards from moving on too early. Steps whose before and after photos look almost the same (turning the napkin over) need the same answer twice in a row. A card does not move on before half of that step's demonstration time has passed, because sprinkling or drizzling looks done after a little. Skipping ahead several cards needs two answers in a row. There is no praise, no score and nothing stored; camera frames are never saved.
   While the learner follows, the camera stays large beside the card, labelled Camera / Demonstration. One line under the camera says what the decision saw, for example "Still looks like before step 2" or "Step 2 looks like the demonstration → card 3". On a phone held sideways the screen splits into two columns.
   "Help only when needed" is optional and works like a prompt hierarchy in special-education practice. Each card starts as text only. The picture is added if the step takes more than twice as long as in the demonstration (10–60 s) or the learner presses Help (also on the glasses). The next levels read the sentence aloud (skipped if the maker turned sound off) and then play the motion clip.
   On the last card, when the model sees the step finished twice in a row (or someone presses Done), a plain "All steps done" screen appears with how far help went on each card. It is shown once and not saved. Back and Next always work by hand. "Share today's run" on the end screen sends one line (for example "Finished all 12 steps … Needed help on cards 3, 7 with picture") and the view-only card link through the phone's share sheet, to a parent, a manager or family. It sends no names or photos, and only when someone presses it.

7. Glasses display (`/glasses?run=<id>`): a 600×600 web app for Meta Ray-Ban Display. It has a black background (transparent on the glasses' additive display), focus-and-select controls only, and about 16 KB on first load. It shows the same card as Coach mode, and Back/Next on the glasses move Coach mode too. We checked it in Meta's Ray-Ban Display Simulator (Chrome extension) and built it to follow Meta's web-app guidance: toolkit colours and 88 px buttons, drawings on a see-through black background, one action per press, and a system Back that asks before leaving. Opened on its own (home page in the glasses browser), it lists the card sets with "See it work" and "Open on glasses", all reachable with the D-pad. We haven't tested it on physical glasses yet. For now a phone or tablet is the camera, and the glasses show the cards and take Help/Next. The next step is a glasses camera through Meta's Wearables Device Access Toolkit (a native phone app).

The interface is in Korean and English (switch at the top right). Card text can be Korean, English, or both, plus one more language for the people around the learner (a parent's language, a coworker's language). Muse Spark translates the cards. A second call that never sees the original translates them back into Korean and English, so the maker, who may not read that language, can check the meaning. Code flags any number from the original that is missing in the translation. The extra language reaches print, tablet, card images and glasses only after the maker presses "I've checked it", and it goes back to unconfirmed whenever a card sentence changes. Measured once: 27 cards of the stew recipe went into Vietnamese in 16 s for about $0.024, with no number flags. The back-translation showed one card where "split the tofu" came back as "separate the tofu". We have not measured translation quality otherwise.

## Meta models used

| Model | Used for |
|---|---|
| `muse-spark-1.3` | splitting into steps and writing sentences; Coach mode step recognition (`reasoning.effort = minimal`) |
| `muse-spark-1.3` (agent) | maker-request agent: rewrites sentences, calling the code checker (`check_cards` tool) until it passes; the same agent rewrites a single card people often got stuck on |
| `muse-spark-1.3` | Check and live checking: compares the learner's photo with the step's completion reference |
| `muse-spark-1.3` | one more card language: translation, then an independent back-translation that never sees the original |
| `sam-3.1` | outlining the object in hand |
| `muse-voice-transcribe-1.0` | transcribing what the demonstrator says (`/v1/asr/transcribe`, endpointing mode) |
| `muse-image-1.0` | drawing cards: redraws a card's photo as a simple illustration, with one fixed style for every card (`/v1/images/edits`) |
| `Muse Glimmer 30B` (open weights) | optional, on this Mac: making cards (step splitting and sentences), Coach mode step recognition and Check; video and camera frames never leave the computer |

All other model calls go to the Meta Model API (`https://api.meta.ai/v1`). Some parts are not Meta models, and all of those come from Google. The card voice is Google Cloud Text-to-Speech (Chirp 3 HD, voice Zephyr), used only when `GTTS_KEY` is set. In the browser, MediaPipe BlazeFace blurs faces before a camera frame is sent, MediaPipe Pose Landmarker checks that the whole body is in view for sets filmed facing the camera, and the experimental `?lab=1` matcher is also MediaPipe.

## Measured so far

From runs recorded in this build (small samples, see notes):

- 6 min 2 s first-person latte video → 19 cards in 2.9 min for about $0.20 (another run: 22 cards, 3.4 min, about $0.36).
- 3 min 13 s latte video → 15–17 cards for about $0.09–0.12 per run (4 runs).
- The checker sends failures back with reasons. On the family-recipe video, for example, the first answer wrote "썰으세요" (a common misspelling of "써세요", slice) on 5 cards. The checker named each one, and the second answer passed. In most recorded runs the first answer already passes.
- Coach mode, replaying the same video the cards were made from as the camera (a replay test, not live use, `coach_eval.py`): napkin (12 cards, twice, plus darkened and 1.5× faster), iced latte (16) and towel (15), twice each. Every run reached the last card on its own (before the change: napkin 6–7 of 12, towel 8 of 15). A card moved on a median 6.8 s after the step ended in the demonstration (75% within 11.7 s). 5 of 96 moves came more than 2 s early (2 more than 5 s, both on drizzling syrup). Each decision took about 2.5 s, and Coach mode cost about $0.07 per minute. In the app itself the napkin replay advanced all 11 cards, none early. We have not tested it with a different person or a live camera yet.
- Extra decision when motion stops (11-02): we ran paired replays of napkin and towel, two each, with and without the change at the same time. The median lag went from 9.6 s to 8.2 s, the 75th percentile from 13.4 s to 11.5 s, and the worst from 35 s to 20 s. It makes about 30% more decision calls, and 2 moves came more than 2 s early (0 without it).
- We tried sending fewer images per decision (6 → 5 → 4). Answers did not get faster (about 3 s each), so each decision still sends 6.
- Meta API latency for image decisions changed with the time of day on 11-02: a median of about 2.3 s in the morning and 4–13 s in the afternoon. The replay lags above depend on it.

- Coach mode on this Mac with Muse Glimmer 30B (Q4 GGUF, llama.cpp, 48 GB Apple Silicon) reached the last card in the same replay test at about 4.7 s per decision, $0. Glimmer writes a long reasoning trace first (18–21 s per answer). Pre-filling the start of the JSON answer skips it with about the same accuracy (Glimmer 15 and 13 of 16 cards, Muse Spark 15 and 14, on two single-frame-pair tests). This mode still uses the earlier sentence-based decision, because six reference photos per call are too slow on Glimmer. The numbers here are from before the photo-matching change.

- Making cards on this Mac with Muse Glimmer, end to end in the app ("On this Mac" on upload, same prompt, checker and retries): napkin video (2 min 20 s) → 11 cards in 172 s for $0. The checker found 3 problems in the first answer and 1 in the second, and the third passed. The cards matched 8 of the 10 steps in the video's own captions (Muse Spark also matched 8 of 10; both missed the last two shaping steps). The differences: Glimmer added a "pick up the napkin" card and one step the captions don't have. With the model file on the Mac's internal SSD the model server starts in about 3 s. An earlier script run on the dance video found the same 3 steps as the instructor's captions. Its Korean sentences were rougher than Muse Spark's, with one misspelling that the checker caught but the model could not fix.

Step accuracy against the sample videos' own on-screen step captions (not a teacher's task analysis):

| Sample | Steps in the video's captions | Matched by the cards |
|---|---|---|
| Napkin butterfly fold | 10 | 8 (the last two shaping steps, mostly off-screen, were missed) |
| Shoki dance | 3 | 3, with matching times |
| Bedside cabinet (manual video) | 16 numbered steps | cards follow steps 1–16 in order |

Not measured yet: how long the same cards take to make by hand, and step accuracy against a teacher's own task analysis.

## Run it

Requirements: Python 3.11+, ffmpeg, a Meta Model API key.

```bash
python3 -m venv .venv
.venv/bin/pip install openai python-dotenv pillow requests fastapi uvicorn python-multipart segno pytest
echo 'MODEL_API_KEY=...' > .env          # never commit this file
.venv/bin/python app.py                  # http://127.0.0.1:8790
```

Optional, for making cards and Coach mode on this Mac: download `Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf` and `mmproj-Muse-Glimmer-30B-Q4_K_M.gguf` from `meta-models/Muse-Glimmer-30B-GGUF`, then run

```bash
llama-server -m Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --mmproj mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -c 32768 -ngl 99 --port 8791
```

While that server runs, the home page offers "On this Mac (Muse Glimmer)" for making cards, and the Coach screen offers it for Coach mode. Making cards on this Mac uses the same prompt, code checker and retries, and sends nothing to the API (speech transcription and SAM outlines are skipped). Frames are 2–3 s apart to fit the 32K context.

Deploy (for example Railway, from this GitHub repository): the `Dockerfile` installs ffmpeg and the Python packages. Set these variables on the host:

| Variable | Value |
|---|---|
| `MODEL_API_KEY` | Meta Model API key |
| `APP_KEY` | the admin access key; anyone can view the cards, but adding videos, drawings, 3D folds, translation, the agent and edits ask for a key once (they cost credits or change cards). Learner devices need no key for Coach decisions, Check and learning records, within a daily limit per card set (900 decisions, 300 checks) |
| `JUDGE_KEY` | optional second key for judges: everything works on card sets they upload (samples are read-only), with daily limits on the calls that cost credits, shared by all judges (15 videos, 60 drawings, 20 agent requests, 15 retries, 3000 Coach decisions, 600 checks) |
| `TEACHER_KEYS` | optional per-teacher keys, `name:key,name:key`: each teacher sees the samples plus their own card sets, and can edit or delete only their own (Coach mode works on any set). `APP_KEY` stays the admin key |
| `ALERT_WEBHOOK` | optional webhook URL (Discord or Slack style): a one-line alert when card making stops or the server hits an unhandled error |
| `GTTS_KEY` | optional Google Cloud Text-to-Speech access for the card voice (Chirp 3 HD, Zephyr); without it the device voice reads the cards |
| `COMPACT_DAYS` / `ARCHIVE_DAYS` / `RETAIN_DAYS` / `CACHE_DAYS` | storage lifecycle (14 / 90 / off / 30 days), see Running it for real |
| `TEACHER_QUOTA_MB` / `TEACHER_MAX_SETS` | per-teacher storage limits (5000 MB / 50 sets) |
| `STEP_MODEL` / `SAM_MODEL` / `ASR_MODEL` | model names, if Meta renames or retires one |
| `DATA_DIR` | required in deployment: a persistent volume path (for example `/data`), so card sets, the state file and the spend ledger survive redeploys |
| `SPEND_CAP_USD` | credit cap (default 140): once the spend ledger reaches it, every request that calls the Meta API is refused (viewing and turning cards by hand keep working) |
| `SPEND_ALREADY_USD` | spend that happened outside this server's ledger (read it from the Meta developer console's billing page); added to the ledger total |

The app asks for the key the first time an action needs it, and a cookie keeps it for 30 days. On the glasses, add the web app as `https://<host>/glasses?run=<id>` (the Use page shows QR codes for it and for the tablet view). A phone camera or the glasses web app needs HTTPS, which the host provides.

Command line only: `.venv/bin/python pipeline.py video.mp4 [--fresh]`. Results go to `runs/<hash of the video>/` (not committed).

Tests (97 with pytest: checker, server, Coach decisions, agent; no paid model calls): `.venv/bin/pip install pytest httpx && .venv/bin/python -m pytest -q`

## Files

| File | What it is |
|---|---|
| `pipeline.py` | frames → speech → steps (with check and retry) → photos and outlines |
| `check.py` | the code-only rule checker |
| `coach.py` | Coach mode decision (Muse Spark matching camera frames with the demonstration's step photos) |
| `coach_eval.py` | Coach mode replay measurement: feeds a video as the camera at the browser's pace and reports when each card moved on |
| `agent.py` | maker-request agent (Muse Spark with the checker as a tool) |
| `verify.py`, `verify_eval.py` | Check: compare one photo with a card's completion reference; accuracy measurement |
| `coach_report.py` | Test runs: open Coach with `?log=1` to log decisions, card changes, checks and help levels (no photos, no names); this script turns one run into numbers (cards advanced automatically and kept, median decision time, check results) |
| `storage.py` | storage lifecycle, quotas, backup by maker |
| `app.py` | local web server (FastAPI) |
| `static/index.html` | the whole interface, one file |
| `coach_sim.py`, `coach_bench*.py` | Coach mode replay test and latency measurements |
| `exp1-3.py`, `look_eval.py` | first experiments (video input modes, stability, SAM prompts) and an object-description check; like the replay and latency scripts above, they read local `runs/` folders that are not committed |
| `demo/` | scripted screen recording and demo video assembly |

## Running it for real

- Who sees what: without a key, the home page lists only the sample sets. Card sets that makers upload are unlisted and open only by their link, which is what the QR codes carry. The id comes from the video's hash, so it is hard to guess but not secret to someone who has the same file; anyone with the link can see the card pictures and frame stills. `/runs/` serves only card pictures and frame stills; before 11-02 the whole run folder was public.
- Accounts: one admin key, optional per-teacher keys (own sets only), and a judge key with daily limits. Every change to a card set is appended to its `audit.jsonl` (who, when, what).
- Several learners at once: each Coach screen has its own pairing code, and its glasses link carries that code, so learners on the same card set don't move each other's cards. This state and the judge-key usage survive restarts (`state.json`).
- Cost guards: Coach mode pauses its camera after 5 minutes without a step change. The server limits uploads to 500 MB and 10 minutes, and refuses them when less than 2 GB is free. The keyless and judge daily limits count only requests that were handled, and only for card sets that exist. All judges share one set of judge limits. Daily limits reset at midnight Korea time.
- Restarts: when a restart or redeploy interrupts card making, the set is marked as stopped, so "Try again" appears instead of an endless "Making".
- Failure cases (from a review of failure scenarios on 11-02): with no camera, or when camera permission is denied, Coach starts in Back/Next mode. A 401, 402, 409 or 429 answer stops auto-advance and the screen says why. If the model names a reference number it was not shown, the app ignores it. Coach and Check calls to Meta time out after 30 s. Uploads no longer block other requests, and the video is hashed in 1 MB chunks. If another maker uploads the same video, they get their own card set. Reference stills are written atomically.
- Health and alerts: `/api/health` (free space, jobs, key present) is Railway's health check (`railway.json`), and `ALERT_WEBHOOK` sends failures to a chat.
- Storage over time (`storage.py`, runs every 6 hours): the audio file is deleted once speech is transcribed. A card set unused for `COMPACT_DAYS` (14) keeps a 640 px copy of its video with low-bitrate mono sound instead of the original and drops its 1-second frames and caches (frames come back from the copy when the frame strip is opened). After `ARCHIVE_DAYS` (90) only cards, drawings and text are kept. With `RETAIN_DAYS` set, sets are deleted after that many days, with a warning on the home and edit pages for the last 7 days. Each teacher key has a quota (`TEACHER_QUOTA_MB` 5000, `TEACHER_MAX_SETS` 50). On the samples, compacting cut a set by roughly three quarters.
- Admin page (`#view=admin`, admin key): every card set with owner, stage, last use and size by part; per-owner totals; compact, archive, .zip and delete buttons.
- Backups: a backup by maker (cards, drawings, titles, owners, audit; no video) is written every day to `backups/` and kept for 7 days, and you can download it from the admin page. Each card set also downloads as a .zip from the Use page. Railway volume backups need a paid plan.
- Without an API key (for example after the hackathon credit ends) the site still starts. Viewing, printing, tablet and glasses views work, and cards can still be made with Muse Glimmer on an Apple Silicon Mac with 48 GB of memory (without speech transcription or SAM outlines). A school deployment should use its own paid Meta API key, or Glimmer for anything involving students.
- Reproducible builds: the base image is pinned (`python:3.14.8-slim`) and Python packages are pinned in `requirements.txt`.

## Privacy

- If you run it on your own computer, videos and cards stay there (`runs/`). The hosted demo sends frames to the Meta Model API to make cards and run Coach mode.
- If `GTTS_KEY` is set, the text of card sentences (no photos, no video) is sent to Google Cloud Text-to-Speech to make the read-aloud audio, and the audio is cached with the card set. Without the key, the device voice reads them and nothing is sent.
- Do not use videos of students. Our tests and demo use adult demonstrations only.
- Coach mode never stores camera frames. The only learning records are anonymous help and check counts per card, sent only from devices where a person switched them on (no photos, no names).
- For school use, card making can run on Muse Glimmer on the school's own 48 GB Mac, so the video never leaves it. Coach mode on Glimmer still uses the older sentence-based decision and is slower (12–19 s per decision); a tablet needs an HTTPS address to use its camera, which we have not set up for a local network.
- In Coach mode and Check, the browser pixelates faces before a live camera frame is sent to the Meta API. If the face model cannot load (for example a network that blocks the CDN), no frame is sent and cards move by hand. Sets filmed facing the camera (sign language, dance) are not blurred, and the demonstration video is not blurred when cards are made.

## Credits

- We learned design patterns from Meta's hackathon workshop repository `meta-models/legal-agent-workshop`: checks built into the pipeline instead of left to the model, code-only verdicts, retry with reasons, content-hash caching, SAM box tokens and a progress board. No code was copied from it.
- Sample videos used for testing and the demo (small silent copies of the shipped samples are in `seed/`; the full videos are not included):
  - "POV Morning Latte in Costa Rica ASMR" by Cornffy, YouTube `vqv_DMMDqC8`, CC BY. Korean narration was added with a synthetic voice for testing.
  - Starbucks black glazed latte recipe by 베란다스튜디오, YouTube `sjgucMN4Aa8`, CC BY.
  - "Napkin Folding - Butterfly" by maitp, YouTube `jaHe0SBRLVA`, CC BY. 
  - "How to SHOKI - Quick dance tutorial by Afro 101" by AFRO 101, YouTube `DgqYEe7sIQw`, CC BY.
  - "30년 장사한 엄마의 첫 레시피, 10분 바지락 순두부찌개" by 장사만30년미화씨, YouTube `GStjzzIi4ew`, CC BY.
  - "Barcelona 2 drawer bedside Assembly Instructions" by INSIDE HOUSE, YouTube `RIJc1qKefGg`, CC BY.
  - National disability job samples (home page "Special education and disability jobs"): "Car Transfers With Transfer Belt" by PT Shan, YouTube `708QT4y6lco`; "Oral Care" by WisTech Open | Open RN, YouTube `SQEjgHODEz0`; "호텔수건접기, 수건 예쁘게 개기, 쉽게 개는방법까지" by 귀주부, YouTube `KKSIl9gbeBY`; "Basic Shelving 2011" by thirdpresident, YouTube `-qOS2Uyu1Tw`; "수어배우기 [초급반] 제2강 인사" by 박광철 목사, YouTube `UktSega5kmU`. All are CC BY (we read the licence from each video's YouTube metadata on 2026-11-01). Job names come from the Ministry of Health and Welfare's public guide 「2026년 장애인일자리 사업안내」 (2026-01-05). The 11 jobs tailored for people with severe disabilities are on p.70 (D&D Care and Deaf-to-deaf peer care, 농-농케어, are among them); towel handling and book arrangement are other welfare-job duties on p.70–74.
  - Sample card sets in `seed/` (shown on a fresh deployment, one per use case) include small silent copies of the CC BY videos above.
