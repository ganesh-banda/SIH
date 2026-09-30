# Demo handoff checklist

1. Start the backend and frontend using [README.md](README.md). Confirm the header reads **API CONNECTED**.
2. Click **Open featured case**. It selects alert `alert_00335`, which has a measured equal-output pattern and a supplied seed in its graph context.
3. Point out the score definition: highest model probability among transactions **spent** by this address. Call it a priority for review.
4. Read the SHAP heading aloud: **model log-odds**, not percentage-point changes in criminality.
5. Inspect the transaction graph and a relevant transaction. The source IP is a network observation, not an address owner.
6. Show **Method & boundaries** and note the held-out precision/recall. State that cities and ASN organizations are synthetic test fixtures.
7. Keep `POST /analysis/run` out of a live walkthrough; it temporarily rebuilds the database. Use the saved snapshot.
8. Check the event's exact video duration, aspect ratio, submission format, and upload limit before recording.

Use `backend/reports/model_evaluation.md` for exact evaluation figures and `backend/reports/synthetic_geo.md` for fixture provenance.
