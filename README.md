# TorrentGuard — Torrent File Integrity & Malicious Content Analyzer

TorrentGuard is a beginner-friendly BCA project built with HTML, CSS, JavaScript, Python/Flask, and SQLite. It performs a limited static analysis of uploaded `.torrent` metadata and presents a report with common warning signs.

## Features

- Responsive "scanning bay" interface: a cobalt hero with a reticle drop target (click to browse or drag and drop), white report sheets, and a risk ruler that shows where the score falls between Low, Medium and High.
- Accepts `.torrent` metadata files of any size (there is no upload size limit).
- Validates and parses bencoded torrent metadata.
- Lists the metadata's file paths and declared sizes.
- Flags executable/script extensions, suspicious path patterns, large file lists, and HTTP tracker URLs.
- Calculates a risk indicator from configured rules.
- Calculates SHA-256 for the uploaded `.torrent` file itself.
- Saves reports to a local SQLite database and shows recent scan history.
- Includes a small test suite.

## Project structure

```text
TorrentGuard/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── .gitkeep
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   ├── app.js
│   └── favicon.svg
└── tests/
    └── test_analyzer.py
```

## Requirements

- Python 3.10 or newer recommended
- pip

## Run on Windows

Open Command Prompt or PowerShell in the extracted `TorrentGuard` folder.

1. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

2. Activate it:

   ```powershell
   .venv\Scripts\activate
   ```

3. Install the dependency:

   ```powershell
   pip install -r requirements.txt
   ```

4. Start the application:

   ```powershell
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

To stop the server, press `Ctrl+C` in the terminal.

## Deploy on Render (Docker)

1. Put the project files themselves (not the `.zip`) at the top level of your GitHub repository, so `Dockerfile`, `app.py`, `requirements.txt`, `templates/` and `static/` sit next to each other.
2. In Render, create a **Web Service** from that repository, set **Language** to **Docker**, and leave **Root Directory** empty.
3. Deploy. The container runs `gunicorn app:app` on the port Render provides.

The SQLite database lives inside the container. On Render's free plan that storage is temporary, so scan history resets whenever the service restarts or redeploys.

## Run tests

With the virtual environment activated, run:

```powershell
python -m unittest discover -s tests -v
```

## How the risk score works

The score is a rule-based review indicator, not a probability that a file is malicious. Rules can add points for executable/script extensions, unusual paths, HTTP trackers, or very large file lists. The score is capped at 100 and categorized as Low, Medium, or High. A warning can be a false positive, and a low score does not prove a torrent is safe.

## Important scope and security limitations

- This version reads only the uploaded `.torrent` metadata. It does **not** download the content described by the torrent.
- SHA-256 is calculated for the `.torrent` file, not for the files listed inside it. It is a fingerprint and does not establish authenticity unless compared with a trusted known hash.
- This is not a full antivirus engine. It does not use YARA, ClamAV, VirusTotal, or other malware-intelligence services.
- Torrent metadata can be crafted by an attacker. The parser has a nesting limit, but this is an educational prototype, not a hardened public service. The upload size limit has been removed, so a very large file is read fully into memory; keep this in mind before exposing the app to anyone you do not trust.
- The interface loads the Archivo and IBM Plex Mono fonts from Google Fonts when you are online. Offline, it falls back to system fonts and works the same.
- Do not expose the Flask development server to the public internet. For deployment, configure production hosting, CSRF protection as appropriate, stronger secret management, authentication, retention policies, and additional upload controls.
- Uploaded files are not saved to disk by this app; the report data is saved in SQLite. The database is created automatically under `data/`.

## Suggested future enhancements

1. Add optional YARA or ClamAV scanning for files the user independently provides.
2. Verify downloaded file pieces against the torrent's piece hashes after safely obtaining the content.
3. Add trusted-hash comparison and optional threat-intelligence API integration.
4. Add login, exportable PDF reports, filters, and pagination for scan history.
5. Improve path normalization and add further parser fuzz tests.
