# DEMO.md — 3–5 Minute Presentation Script

## Setup (before you're on stage)

```bash
python run.py
```

Open http://127.0.0.1:5057. Click **"Load Demo Data"** once so the corpus isn't empty —
everything below assumes the synthetic demo dataset (a proposal doc, a roadmap doc, an
architecture slide deck, a sprint-board screenshot, and a project-sync meeting transcript) is
loaded. It's clearly labeled as synthetic in the audit log (`"demo": true`).

## Script

1. **Open SnapMemory.** "Everything you're about to see runs entirely on this device."

2. **Dashboard.** Point at `Cloud requests: 0` and `Internet required: NO`. "Zero cloud calls,
   by construction — there isn't a cloud code path in the core system to call."

3. **Documents tab.** Show the three indexed documents (a proposal, a roadmap, and an
   architecture slide deck), each with a real chunk count.

4. **Visual Memory tab.** Open the sprint-board screenshot. Show the OCR'd text — this was
   extracted locally by Tesseract, not sent anywhere.

5. **Meetings tab.** Open the demo meeting. Show:
   - Transcript
   - Summary
   - Decisions (the Firebase authentication decision)
   - Action items (James / backend pipeline / Nov 28)
   - Note honestly: *"This demo meeting was seeded from a written transcript rather than an
     audio recording, since real audio transcription needs a Whisper model installed — the
     Meetings tab clearly shows the transcription provider used."* If you have `faster-whisper`
     installed or a Qualcomm AI Hub Whisper model configured, upload a **real** audio file here
     instead for a stronger demo.

6. **Ask SnapMemory tab.** Ask: *"What did we decide about authentication?"*
   - Show the grounded answer.
   - Expand the sources — point out it cites the meeting **and** the slide deck **and**
     cross-references the OCR'd screenshot, with exact slide/timestamp references.

7. Ask a second question: *"Who was assigned the backend and what was the deadline?"*
   - Show that James/Nov 28 comes from multiple independent sources (meeting transcript, slide
     deck, and the screenshot) that all agree — a nice demonstration of cross-source grounding.

8. **Privacy Center.** Show the audit log — every import, every query, every embedding
   generation is logged in real time.

9. **Performance tab.** Click **Start Benchmark**. Show the real measured latency numbers and
   the device/model status panel. Be upfront: *"On this development machine there's no
   Snapdragon NPU, so it correctly reports CPU execution. On the target Snapdragon HP device
   with the AI Hub models configured per SNAPDRAGON_SETUP.md, this same panel reports NPU."*

10. **Disable networking** (airplane mode / disconnect Wi-Fi).

11. **Ask another question.** Show it still works — nothing in the core query path depends on
    connectivity.

## What to say if asked "is this really running on the NPU?"

Be direct: on whatever machine you're demoing on, the Performance tab is the source of truth.
If it says CPU, say CPU — and point to the honest-by-design architecture (`ai/providers.py`)
as the reason you can say that confidently rather than guessing.
