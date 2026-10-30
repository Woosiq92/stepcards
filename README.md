# StepCards

Turn one demonstration video into checked picture step cards — then let a camera show the learner the right card at the right time.

Built during the Meta AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track, by LogicCraft. All code in this repository was written during the hackathon; the first commit is dated 2026-10-28.

## The problem

Special-education teachers teach job skills (making a drink, doing laundry, packing) with task-analysis cards: one action per card, one photo, one short sentence. Today they make these by hand — film the task, pause, screenshot, write a sentence, print. StepCards does the first draft from a single video, checks it with code, and leaves the teacher in charge of the final version.

## Who it's for

Built first for the hardest case — learners with intellectual disabilities, where every step has to be right and checked by a teacher. The same structure (one video → checked cards → follow along by camera, tablet, phone or glasses) fits anywhere someone has to follow someone else's exact way of doing a hands-on task:

| Situation | Who makes the cards | Who follows |
|---|---|---|
| Special-education job training | teacher | student |
| New staff training (cafés, kitchens, warehouses) | senior staff | new hires, including migrant workers (Korean and English cards) |
| Follow-along versions of creators' videos | the creator, from their own video | viewers |
| Assembly and setup | the maker | first-time buyers |
| Family know-how (a parent's recipe) | family | family |

Tested so far: latte making (café training, two videos including a creator's recipe video) and napkin folding (restaurant service). The other situations are use cases, not yet tested.

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
5. **Coach mode**: a camera watches the learner. Muse Spark looks at the last two frames and says which step is happening; SAM 3.1 confirms the object in hand before the next card appears. If a later step shows up, the current card is shown again first; if it shows up twice in a row, the cards follow the learner. No praise, no scores, nothing stored — camera frames are never saved. Optional "help only when needed" (a prompt hierarchy, as in special-education practice): each card starts as text only; if the step takes more than twice as long as in the demonstration (10–60 s), or the learner presses Help (also on the glasses), it adds the picture, then reads it aloud (skipped if the teacher turned sound off), then plays the motion clip. On the last card, when the model sees the step finished twice in a row (or someone presses Done), a plain "All steps done" screen appears, with how far help went on each card; this is shown once and not saved. Back and Next always work by hand.

6. **Glasses display** (`/glasses?run=<id>`): a 600×600 web app for Meta Ray-Ban Display. Black background (transparent on the glasses' additive display), focus-and-select controls only, about 16 KB first load. It shows the same card as Coach mode, and Back/Next on the glasses move Coach mode too. Checked in Meta's Ray-Ban Display Simulator (Chrome extension) and built to Meta's web-app guidance (toolkit colours and 88 px buttons, drawings shown on a see-through black background, one action per press, system Back asks before leaving). Not yet tested on physical glasses. Today the camera is a phone or tablet and the glasses are the display and Help/Next input; a glasses camera through Meta's Wearables Device Access Toolkit (a native phone app) is the next step.

The interface is available in Korean and English (switch at the top right). Card text can be Korean, English, or both.

## Meta models used

| Model | Used for |
|---|---|
| `muse-spark-1.3` | splitting into steps and writing sentences; Coach mode step recognition (`reasoning.effort = minimal`) |
| `muse-spark-1.3` (agent) | teacher-request agent: rewrites sentences, calling the code checker (`check_cards` tool) until it passes |
| `sam-3.1` | outlining the object in hand; confirming the object before Coach mode moves on |
| `muse-voice-transcribe-1.0` | transcribing what the demonstrator says (`/v1/asr/transcribe`, endpointing mode) |
| `muse-image-1.0` | drawing cards: redraws a card's photo as a simple illustration, with one fixed style for every card (`/v1/images/edits`) |
| `Muse Glimmer 30B` (open weights) | optional, on this Mac: making cards (step splitting and sentences) and Coach mode step recognition — video and camera frames never leave the computer |

All other calls go to the Meta Model API (`https://api.meta.ai/v1`).

## Measured so far

From runs recorded in this build (small samples, see notes):

- 6 min 2 s first-person latte video → 19 cards in 2.9 min for about $0.20 (another run: 22 cards, 3.4 min, about $0.36).
- 3 min 13 s latte video → 15–17 cards for about $0.09–0.12 per run (4 runs).
- The checker sends failures back with reasons. Example: on the family-recipe video the first answer wrote "썰으세요" (a common misspelling of "써세요", slice) on 5 cards; the checker named each one, and the second answer passed. Across recorded runs most first answers already pass.
- Coach mode, replaying the same video the cards were made from as the camera (a replay test, not live use): about 3.6 s per decision (two frames, minimal reasoning; 4 frames with default reasoning took 9–11 s), about $0.08 per minute.

- Coach mode on this Mac with Muse Glimmer 30B (Q4 GGUF, llama.cpp, 48 GB Apple Silicon): reached the last card in the same replay test at about 4.7 s per decision, $0. Glimmer writes a long reasoning trace first (18–21 s per answer); pre-filling the start of the JSON answer skips it with about the same accuracy (Glimmer 15 and 13 of 16 cards, Muse Spark 15 and 14, on two single-frame-pair tests). The SAM check is skipped in this mode because SAM runs on the API.

- Making cards on this Mac with Muse Glimmer (same prompt, checker and retries; frames 2–3 s apart): napkin video, 11 steps, 8 of the 10 steps in the video's own captions (Muse Spark: also 8 of 10), passed the checker on the third try, about 3.3 min, $0; dance video, the same 3 steps as the instructor's captions, about 2.4 min. Korean sentences were rougher than Muse Spark's (one misspelling the checker caught but the model could not fix).

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
.venv/bin/pip install openai python-dotenv pillow requests fastapi uvicorn python-multipart pytest
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
| `APP_KEY` | an access key; anyone can view the cards, but adding videos, drawings, the agent, Coach mode and edits ask for this key once (they cost credits or change cards) |
| `JUDGE_KEY` | optional second key for judges: everything works, with daily limits on the calls that cost credits (6 videos, 60 drawings, 20 agent requests, about 30 minutes of Coach mode) |
| `DATA_DIR` | a persistent volume path (for example `/data`), so card sets survive redeploys |

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
| `app.py` | local web server (FastAPI) |
| `static/index.html` | the whole interface, one file |
| `coach_sim.py`, `coach_bench*.py` | Coach mode replay test and latency measurements |
| `exp1-3.py` | first experiments (video input modes, stability, SAM prompts) |
| `demo/` | scripted screen recording and demo video assembly |

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
  - Sample card sets in `seed/` (shown on a fresh deployment, one per use case) include small silent copies of the CC BY videos above.
