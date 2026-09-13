# PDF Diff

A local PDF comparison tool that highlights changes directly on the source documents:

- Removed text is marked with a translucent red highlight on the initial PDF.
- Added text is marked with a translucent green highlight on the updated PDF.
- Table or structure changes are marked in amber.
- Text is compared across the full document, so unchanged content that moves to another page after reflow is not reported as a removal and addition.

All processing happens locally. Uploaded PDFs are held in memory only while the local server is running.

## Requirements

- Python 3.10 or newer
- The packages listed in `requirements.txt`

## Install

```bash
git clone https://github.com/teja-afk/pdf-diff-checker.git
cd pdf-diff
python -m venv venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Use in the browser

Start the local server:

```bash
python app.py --serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), select the initial and updated PDFs, then choose **Compare documents**. Each page is displayed side by side:

- **Previous document:** translucent red highlights identify removed text.
- **Updated document:** translucent green highlights identify added text.
- **Amber:** a table or structural change.

Use the page controls to move through the comparison.

## Use from the command line

```bash
python app.py initial.pdf updated.pdf
```

The command writes PNGs only for pages with detected changes:

```text
diff_old_page_1.png  # initial-page view with red removals
diff_new_page_1.png  # updated-page view with green additions
```

Unchanged pages do not produce PNG files.

## Notes and limitations

- The tool compares extractable PDF text. Image-only/scanned PDFs need OCR before text-level differences can be detected.
- Comparison is word-based and case-insensitive.
- Global document matching handles normal pagination reflow, though substantial content reordering or repeated boilerplate can still require manual review.
- Table detection is best effort and depends on the PDF having detectable table structure.

## Project files

```text
app.py            Local web server, PDF comparison, and CLI exporter
requirements.txt  Python dependencies
```

## Results
homepage.png
<img width="1917" height="1032" alt="image" src="https://github.com/user-attachments/assets/1faf2dc2-6404-41ae-8fe9-fd17aa6d75fa" />

pdf-diff-results.png
<img width="1917" height="982" alt="image" src="https://github.com/user-attachments/assets/4a87056a-3cfc-4cb7-b714-6f7102748618" />



