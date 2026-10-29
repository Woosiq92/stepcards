# StepCards

Turn one demonstration video into checked picture step cards — then let a camera show the learner the right card at the right time.

Built during the Meta AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track, by LogicCraft. All code in this repository was written during the hackathon; the first commit is dated 2026-10-28.

## The problem

Special-education teachers teach job skills (making a drink, doing laundry, packing) with task-analysis cards: one action per card, one photo, one short sentence. Today they make these by hand — film the task, pause, screenshot, write a sentence, print. StepCards does the first draft from a single video, checks it with code, and leaves the teacher in charge of the final version.

## What it does

1. **Add a video** of someone doing a hands-on task once (first-person, like smart glasses, works well).
2. **Making the cards**
   - Frames are taken every second (ffmpeg).
   - **Muse Voice Transcribe** writes down what was said, with times. Spoken amounts and names (for example "18 g", "caramel syrup") go into the sentences.
   - **Muse Spark** splits the video into one-action steps: start, end, best moment, a plain Korean sentence, an English sentence, the object in hand and how it looks.
   - **A code checker** (no model) tests every step: times inside the video, no overlaps, the chosen moment inside the step, sentence length, one action per sentence, Korean polite ending, two common Korean spelling mistakes. If a rule fails, the reasons go back to Muse Spark and it tries again (up to twice). Whatever still fails is shown to the teacher.
   - **SAM 3.1** finds the object in the worker's hand (by name, then by appearance) and outlines it. If the object does not touch a hand in the chosen frame, other moments in the step are tried.
3. **Check & edit**: edit sentences in place (autosave, re-checked on every save), move, merge, remove or add cards, choose another frame from a filmstrip, fix times and object names. Problems appear on the card in plain words.
4. **Use**: print six cards per A4 page, flip through on a tablet, or start **Coach mode**.
5. **Coach mode**: a camera watches the learner. Muse Spark looks at the last two frames and says which step is happening; SAM 3.1 confirms the object in hand before the next card appears. If a later step shows up, the current card is shown again first; if it shows up twice in a row, the cards follow the learner. No praise, no scores, nothing stored — camera frames are never saved. Back and Next always work by hand.

6. **Glasses display** (`/glasses?run=<id>`): a 600×600 web app for Meta Ray-Ban Display. Black background (transparent on the glasses' additive display), focus-and-select controls only, about 16 KB first load. It shows the same card as Coach mode, and Back/Next on the glasses move Coach mode too. Tested in desktop Chrome at 600×600; not yet tested on glasses or in Meta's simulator.

The interface is available in Korean and English (switch at the top right). Card text can be Korean, English, or both.

## Meta models used

| Model | Used for |
|---|---|
| `muse-spark-1.3` | splitting into steps and writing sentences; Coach mode step recognition (`reasoning.effort = minimal`) |
| `sam-3.1` | outlining the object in hand; confirming the object before Coach mode moves on |
| `muse-voice-transcribe-1.0` | transcribing what the demonstrator says (`/v1/asr/transcribe`, endpointing mode) |

| `Muse Glimmer 30B` (open weights) | optional Coach mode on this Mac: step recognition runs locally, camera frames never leave the computer |

All other calls go to the Meta Model API (`https://api.meta.ai/v1`).

## Measured so far

From runs recorded in this build (small samples, see notes):

- 6 min 2 s first-person latte video → 19 cards in 2.9 min for about $0.20 (another run: 22 cards, 3.4 min, about $0.36).
- 3 min 13 s latte video → 15–17 cards for about $0.09–0.12 per run (4 runs).
- The checker sent a step back to the model in 1 of 8 full runs so far; that run passed on the second try.
- Coach mode, replaying a video as the camera: about 3.6 s per decision (two frames, minimal reasoning; 4 frames with default reasoning took 9–11 s), about $0.08 per minute.

- Coach mode on this Mac with Muse Glimmer 30B (Q4 GGUF, llama.cpp, 48 GB Apple Silicon): reached the last card in the same replay test at about 4.7 s per decision, $0. Glimmer writes a long reasoning trace first (18–21 s per answer); pre-filling the start of the JSON answer skips it with about the same accuracy (Glimmer 15 and 13 of 16 cards, Muse Spark 15 and 14, on two single-frame-pair tests). The SAM check is skipped in this mode because SAM runs on the API.

Not measured yet: time to make the same cards by hand, and step accuracy against a teacher's own task analysis.

## Run it

Requirements: Python 3.11+, ffmpeg, a Meta Model API key.

```bash
python3 -m venv .venv
.venv/bin/pip install openai python-dotenv pillow requests fastapi uvicorn python-multipart pytest
echo 'MODEL_API_KEY=...' > .env          # never commit this file
.venv/bin/python app.py                  # http://127.0.0.1:8790
```

Optional, Coach mode on this Mac: download `Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf` and `mmproj-Muse-Glimmer-30B-Q4_K_M.gguf` from `meta-models/Muse-Glimmer-30B-GGUF`, then

```bash
llama-server -m Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --mmproj mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -c 8192 -ngl 99 --port 8791
```

The Coach screen shows "On this Mac (Muse Glimmer)" when that server is running.

Command line only: `.venv/bin/python pipeline.py video.mp4 [--fresh]`. Results go to `runs/<hash of the video>/` (not committed).

Tests for the checker: `.venv/bin/python -m pytest -q test_check.py`

## Files

| File | What it is |
|---|---|
| `pipeline.py` | frames → speech → steps (with check and retry) → photos and outlines |
| `check.py` | the code-only rule checker |
| `coach.py` | Coach mode decision (Muse Spark + SAM 3.1) |
| `app.py` | local web server (FastAPI) |
| `static/index.html` | the whole interface, one file |
| `coach_sim.py`, `coach_bench*.py` | Coach mode replay test and latency measurements |
| `exp1-3.py` | first experiments (video input modes, stability, SAM prompts) |
| `demo/` | scripted screen recording and demo video assembly |

## Privacy

- Runs locally; videos and cards stay on the machine (`runs/`).
- Do not use videos of students. Our tests and demo use adult demonstrations only.
- Coach mode never stores camera frames and keeps no records of the learner.
- For school use, Coach mode can run on Muse Glimmer on the school's own computer so student video never leaves it.

## Credits

- Design patterns (checks built into the pipeline instead of left to the model, code-only verdicts, retry with reasons, content-hash caching, SAM box tokens, progress board) were learned from Meta's hackathon workshop repository `meta-models/legal-agent-workshop`. No code was copied from it.
- Sample videos used for testing and the draft demo (not included in this repository):
  - "POV Morning Latte in Costa Rica ASMR" by Cornffy, YouTube `vqv_DMMDqC8`, CC BY. Korean narration was added with a synthetic voice for testing.
  - Starbucks black glazed latte recipe by 베란다스튜디오, YouTube `sjgucMN4Aa8`, CC BY.
