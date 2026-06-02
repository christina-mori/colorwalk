# ColorWalk Studio

ColorWalk Studio is a small Flask app for generating playful image compositions from a photo.

It currently supports two tools:

- **ColorWalk**: combine a photo with a color block and text.
- **Dot Puzzle**: combine a photo with cutout dots, shapes, blocks, gradients, stripes, and text.

The app is intentionally lightweight: one Flask server, no build step, SQLite-backed community submissions, and static frontend assets.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`.

## Environment Variables

Copy `.env.example` and set production-safe values:

```text
SECRET_KEY=replace-with-a-random-secret
ADMIN_PASSWORD=replace-with-a-strong-password
DATA_DIR=/app/data
SUBMISSION_SALT=replace-with-another-random-secret
MAX_COMMUNITY_SUBMISSION_MB=20
APP_BASE_URL=https://your-app.up.railway.app
```

## Railway Deploy

This repo includes Railway deployment files:

- `railway.json`
- `Procfile`
- `requirements.txt`

Railway start command:

```text
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

Health check:

```text
/healthz
```

After deploying, set the environment variables above in Railway.

## Tests

```powershell
python -m unittest discover -s tests
```

## Project Structure

```text
app.py              Flask routes and request parsing
utils/              Image generation and community store logic
templates/          Flask templates
static/css/         Shared styling
static/js/          Frontend state and UI interactions
static/gallery/     Demo gallery assets
tests/              Python regression tests
```

## License

Open source license is not set yet. Add a `LICENSE` file before promoting this as a reusable public project.
