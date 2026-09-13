# Watch later triage

Local browser app for triaging a YouTube playlist (Watch Later or any `list=` URL). Mark remove / keep / later, filter and group, then let a userscript click YouTube's own Remove.

Nothing is uploaded. Playlist rows live in your browser (`localStorage`). The userscript runs in your logged-in YouTube tab.

## Use

1. Install [Tampermonkey](https://www.tampermonkey.net/) (or Violentmonkey).
2. Open this app and download **userscript** (or install [`web/public/watchlater-remove.user.js`](web/public/watchlater-remove.user.js)).
3. On YouTube, open **Watch Later** or any playlist.
4. In the helper panel: **Export playlist** (copies JSON and downloads a file).
5. Back in the app: **pull playlist** (reads the clipboard) or **import** the file.

Then triage. **copy remove ids** → userscript **Load** → **Start remove**. After a run, **import** the userscript result so gone IDs hide.

## Develop

```bash
cd web
npm install
npm run dev
```

Optional richer ingest (categories, watch progress, scores) if you have a playlist JSONL plus a playlist HTML dump:

```bash
uv run analyze.py
cd web && npm run data && npm run dev
```

`analyze.py` is optional. The app works on a bare userscript export.

## Privacy

Do not commit playlist dumps, HTML captures, or generated `videos.jsonl` / `insights.json`. Those paths are gitignored.
