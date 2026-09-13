"""PDF Diff - local visual PDF comparison. Run: python app.py --serve"""
import base64, difflib, io, json, sys, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pymupdf

SESSIONS = {}

def words(page):
    return [{"norm": w[4].casefold(), "rect": pymupdf.Rect(w[:4])} for w in page.get_text("words", sort=True) if w[4].strip()]

def changed_rectangles(old_page, new_page):
    old, new = words(old_page), words(new_page)
    matcher = difflib.SequenceMatcher(None, [x["norm"] for x in old], [x["norm"] for x in new], autojunk=False)
    removed, added = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"): removed.extend(x["rect"] for x in old[i1:i2])
        if tag in ("replace", "insert"): added.extend(x["rect"] for x in new[j1:j2])
    return removed, added

def document_words(document):
    """Return words in reading order, retaining the page that owns each word."""
    return [dict(word, page=page_number) for page_number, page in enumerate(document) for word in words(page)]

def document_change_map(old_document, new_document):
    """Find edits across the whole document, rather than treating a page break as an edit."""
    old, new = document_words(old_document), document_words(new_document)
    matcher = difflib.SequenceMatcher(None, [word["norm"] for word in old], [word["norm"] for word in new], autojunk=False)
    removed, added = {}, {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            for word in old[i1:i2]: removed.setdefault(word["page"], []).append(word["rect"])
        if tag in ("replace", "insert"):
            for word in new[j1:j2]: added.setdefault(word["page"], []).append(word["rect"])
    return removed, added

def tables(page):
    """Best-effort vector/text table detection; empty result is safe for scanned PDFs."""
    try:
        return [{"rect": pymupdf.Rect(t.bbox), "value": "|".join(" ".join((cell or "").split()) for row in t.extract() for cell in row).casefold()} for t in page.find_tables().tables]
    except Exception: return []

def structure_changes(old_page, new_page):
    old, new = tables(old_page), tables(new_page)
    if len(old) != len(new): return [f"Table count changed: {len(old)} → {len(new)}"], [x["rect"] for x in old], [x["rect"] for x in new]
    changed = [(a, b) for a, b in zip(old, new) if a["value"] != b["value"]]
    return ([f"Table {i + 1} content or structure changed" for i, (a, b) in enumerate(zip(old, new)) if a["value"] != b["value"]], [x[0]["rect"] for x in changed], [x[1]["rect"] for x in changed])

def render(page, removed_rects=(), added_rects=(), table_rects=()):
    """Render one page with translucent change layers composited over its text."""
    from PIL import Image, ImageDraw
    scale = 2
    image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).pil_image().convert("RGBA")
    # Direct RGBA drawing replaces pixels; a separate layer preserves the text.
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for rect in removed_rects: draw.rounded_rectangle(tuple(v * scale for v in rect), radius=2, fill=(239, 68, 68, 72))
    for rect in added_rects: draw.rounded_rectangle(tuple(v * scale for v in rect), radius=2, fill=(34, 197, 94, 72))
    for rect in table_rects:
        box = tuple(v * scale for v in rect); draw.rectangle(box, outline=(245, 158, 11, 180), width=4); draw.rectangle(box, fill=(245, 158, 11, 40))
    output = io.BytesIO(); Image.alpha_composite(image, overlay).convert("RGB").save(output, "PNG", optimize=True)
    return base64.b64encode(output.getvalue()).decode()

def page_result(session, index):
    old_doc, new_doc = session["old"], session["new"]
    old = old_doc[index] if index < len(old_doc) else None; new = new_doc[index] if index < len(new_doc) else None
    if "text_changes" not in session:
        session["text_changes"] = document_change_map(old_doc, new_doc)
    removed, added = (changes.get(index, []) for changes in session["text_changes"])
    result = {"page": index + 1, "old": None, "new": None, "events": []}
    if old is None:
        result["events"] = ["This page exists only in the updated document."]
        result["new"] = render(new, (), added)
    elif new is None:
        result["events"] = ["This page exists only in the initial document."]
        result["old"] = render(old, removed)
    else:
        events, old_tables, new_tables = structure_changes(old, new)
        # Each document is rendered on its own page canvas: removed text remains
        # visible in red on the initial PDF and added text in green on the update.
        result["old"] = render(old, removed, (), old_tables)
        result["new"] = render(new, (), added, new_tables)
        result["events"] = events or ([f"{len(removed)} removed words; {len(added)} added words"] if removed or added else ["No text or table changes detected on this page."])
    # Used by the command-line exporter so it does not create blank diff PNGs.
    result["has_changes"] = bool(removed or added or (old is not None and new is not None and result["events"] != ["No text or table changes detected on this page."]))
    return result

HTML = '''<!doctype html><html><head><meta charset="utf-8"><title>TenderDiff</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172033;font:14px Inter,Segoe UI,Arial,sans-serif}header{padding:18px 28px;background:#172554;color:#fff;display:flex;align-items:center;justify-content:space-between}h1{font-size:20px;margin:0}header small{color:#c7d2fe}.upload{margin:28px auto;padding:26px;max-width:720px;background:#fff;border:1px solid #dce3f0;border-radius:14px;box-shadow:0 4px 14px #17255412}input{display:block;width:100%;padding:12px;border:1px dashed #94a3b8;border-radius:8px;margin:9px 0 18px}button{padding:11px 17px;background:#2563eb;color:#fff;border:0;border-radius:7px;font-weight:700;cursor:pointer}.hidden{display:none}.toolbar{padding:12px 28px;background:#fff;border-bottom:1px solid #dce3f0;display:flex;gap:18px;align-items:center}.legend{margin-left:auto;display:flex;gap:15px}.chip{padding:4px 8px;border-radius:4px}.red{background:#fecaca}.green{background:#bbf7d0}.orange{background:#fde68a}.grid{display:grid;grid-template-columns:1fr 1fr 310px;gap:14px;padding:16px;min-height:calc(100vh - 120px)}.panel{background:#fff;border:1px solid #dce3f0;border-radius:10px;overflow:auto}.panel h2{font-size:14px;margin:0;padding:13px 15px;border-bottom:1px solid #e5e7eb;position:sticky;top:0;background:#fff;z-index:1}.panel img{width:100%;display:block}.changes{padding:12px}.event{padding:11px;margin:0 0 9px;border-left:4px solid #f59e0b;background:#fffbeb;border-radius:4px}.loading{color:#64748b}@media(max-width:950px){.grid{grid-template-columns:1fr}.legend{display:none}}</style></head><body><header><h1>TenderDiff</h1><small>Private, local PDF change review</small></header><section id="upload" class="upload"><h2>Compare tender documents</h2><p>Upload previous and new PDFs. Green = additions, red = removals, amber = table/structure changes.</p><label>Previous tender document<input id="old" type="file" accept="application/pdf"></label><label>New tender document<input id="new" type="file" accept="application/pdf"></label><button onclick="compare()">Compare documents</button><p id="status" class="loading"></p></section><main id="viewer" class="hidden"><div class="toolbar"><button onclick="move(-1)">← Previous</button><strong id="page"></strong><button onclick="move(1)">Next →</button><span class="legend"><span class="chip red">Removed</span><span class="chip green">Added</span><span class="chip orange">Table / structure change</span></span></div><div class="grid"><section class="panel"><h2 id="oldTitle">Previous document</h2><img id="oldImg"></section><section class="panel"><h2 id="newTitle">New document</h2><img id="newImg"></section><aside class="panel"><h2>Change summary</h2><div id="events" class="changes"></div></aside></div></main><script>
let id,page=0,total=0;async function compare(){let a=old.files[0],b=new.files[0];if(!a||!b)return status.textContent='Please choose both PDF files.';status.textContent='Analysing documents…';let f=new FormData();f.append('old',a);f.append('new',b);let r=await fetch('/api/compare',{method:'POST',body:f}),x=await r.json();if(x.error){status.textContent=x.error;return}id=x.id;total=x.pages;oldTitle.textContent='Previous · '+a.name;newTitle.textContent='New · '+b.name;upload.classList.add('hidden');viewer.classList.remove('hidden');load()}async function load(){page=Math.max(0,Math.min(page,total-1));events.innerHTML='<p class="loading">Rendering page…</p>';let x=await (await fetch('/api/page?id='+id+'&page='+page)).json();document.getElementById('page').textContent='Page '+x.page+' of '+total;oldImg.src=x.old?'data:image/png;base64,'+x.old:'';newImg.src=x.new?'data:image/png;base64,'+x.new:'';events.innerHTML=x.events.map(e=>'<div class="event">'+e+'</div>').join('')}function move(n){page+=n;load()}</script></body></html>'''

# Prevent the compact original script from failing to parse on the reserved
# JavaScript keyword ``new``. The handlers below then use explicit DOM lookups.
HTML = HTML.replace("let a=old.files[0],b=new.files[0]", "let a=document.getElementById('old').files[0],b=document.getElementById('new').files[0]")
HTML = HTML.replace("TenderDiff", "PDF Diff")
HTML = HTML.replace("Compare tender documents", "Compare documents")
HTML = HTML.replace("Upload previous and new PDFs. Green = additions, red = removals, amber = table/structure changes.", """Upload an initial and an updated PDF. <span class=\"visual-info\">Visual info: <span class=\"info-badge added\">Additions</span><span class=\"info-badge removed\">Removed</span><span class=\"info-badge structure\">Table/Structure</span></span>""")
HTML = HTML.replace("Previous tender document", "Initial document")
HTML = HTML.replace("New tender document", "Updated document")
HTML = HTML.replace("</style>", """.visual-info{white-space:nowrap}.info-badge{display:inline-block;margin-left:6px;padding:3px 8px;border-radius:999px;font-weight:700;font-size:12px}.info-badge.added{background:#bbf7d0;color:#15803d}.info-badge.removed{background:#fecaca;color:#b91c1c}.info-badge.structure{background:#fde68a;color:#a16207}.upload label{display:inline-block;width:calc(50% - 9px);vertical-align:top}.upload label+label{margin-left:14px}@media(max-width:600px){.upload label{display:block;width:100%}.upload label+label{margin-left:0}}</style>""")
HTML = HTML.replace("</body>", """<script>
var comparisonId, comparisonPage = 0, comparisonTotal = 0;
async function compare() {
  const initialFile = document.getElementById('old').files[0];
  const updatedFile = document.getElementById('new').files[0];
  const status = document.getElementById('status');
  if (!initialFile || !updatedFile) { status.textContent = 'Please choose both PDF files.'; return; }
  status.textContent = 'Analysing documents…';
  const form = new FormData(); form.append('old', initialFile); form.append('new', updatedFile);
  const response = await fetch('/api/compare', {method: 'POST', body: form});
  const data = await response.json();
  if (data.error) { status.textContent = data.error; return; }
  comparisonId = data.id; comparisonTotal = data.pages;
  document.getElementById('oldTitle').textContent = 'Previous · ' + initialFile.name;
  document.getElementById('newTitle').textContent = 'Updated · ' + updatedFile.name;
  document.getElementById('upload').classList.add('hidden');
  document.getElementById('viewer').classList.remove('hidden');
  load();
}
async function load() {
  comparisonPage = Math.max(0, Math.min(comparisonPage, comparisonTotal - 1));
  const events = document.getElementById('events'); events.innerHTML = '<p class="loading">Rendering page…</p>';
  const response = await fetch('/api/page?id=' + encodeURIComponent(comparisonId) + '&page=' + comparisonPage);
  const data = await response.json();
  if (data.error) { events.innerHTML = '<div class="event">' + data.error + '</div>'; return; }
  document.getElementById('page').textContent = 'Page ' + data.page + ' of ' + comparisonTotal;
  document.getElementById('oldImg').src = data.old ? 'data:image/png;base64,' + data.old : '';
  document.getElementById('newImg').src = data.new ? 'data:image/png;base64,' + data.new : '';
  events.innerHTML = data.events.map(function (event) { return '<div class="event">' + event + '</div>'; }).join('');
}
function move(amount) { comparisonPage += amount; load(); }
</script></body>""")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_json(self, data, code=200):
        body=json.dumps(data).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/":
            body=HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path.startswith("/api/page?"):
            from urllib.parse import parse_qs, urlparse
            try:
                q=parse_qs(urlparse(self.path).query); self.send_json(page_result(SESSIONS[q["id"][0]],int(q["page"][0])))
            except Exception as exc: self.send_json({"error":str(exc)},400)
            return
        self.send_error(404)
    def do_POST(self):
        if self.path != "/api/compare": self.send_error(404); return
        try:
            # Python 3.13 removed cgi.FieldStorage, so parse the two multipart parts
            # directly. Uploads are kept in memory only for this local session.
            content_type=self.headers["Content-Type"]
            boundary=content_type.split("boundary=",1)[1].strip('"').encode()
            raw=self.rfile.read(int(self.headers["Content-Length"]))
            files={}
            for part in raw.split(b"--"+boundary):
                headers, marker, body=part.partition(b"\r\n\r\n")
                if marker and b'name="old"' in headers: files["old"]=body.rsplit(b"\r\n",1)[0]
                if marker and b'name="new"' in headers: files["new"]=body.rsplit(b"\r\n",1)[0]
            key=uuid.uuid4().hex; SESSIONS[key]={"old":pymupdf.open(stream=files["old"],filetype="pdf"),"new":pymupdf.open(stream=files["new"],filetype="pdf")}
            SESSIONS[key]["text_changes"] = document_change_map(SESSIONS[key]["old"], SESSIONS[key]["new"])
            self.send_json({"id":key,"pages":max(len(SESSIONS[key]["old"]),len(SESSIONS[key]["new"]))})
        except Exception as exc: self.send_json({"error":"Could not read the PDFs: "+str(exc)},400)

def cli(old_path,new_path):
    session={"old":pymupdf.open(old_path),"new":pymupdf.open(new_path)}
    session["text_changes"] = document_change_map(session["old"], session["new"])
    for i in range(max(len(session["old"]),len(session["new"]))):
        data=page_result(session,i)
        if data["has_changes"]:
            for side in ("old", "new"):
                if data[side]: Path(f"diff_{side}_page_{i+1}.png").write_bytes(base64.b64decode(data[side]))
        print(f"Page {i+1}: "+"; ".join(data["events"]))

def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("PDF Diff running at http://127.0.0.1:8000 (press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPDF Diff stopped.")
    finally:
        server.server_close()

if __name__ == "__main__":
    if len(sys.argv)==2 and sys.argv[1] in ("--serve", "--server"):
        serve()
    elif len(sys.argv)==3: cli(sys.argv[1],sys.argv[2])
    else: print("Usage: python app.py --serve  OR  python app.py old.pdf new.pdf")
