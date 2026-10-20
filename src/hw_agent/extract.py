"""Bounded document extraction worker. Run in a separate process."""
import json
from pathlib import Path
import sys
import subprocess
import zipfile
from defusedxml import ElementTree

LIMIT = 200_000


def extract(path):
    p = Path(path)
    ext = p.suffix.lower()
    if p.stat().st_size > 32 * 1024**2:
        return "", "size_limit"
    if ext in {".txt", ".md", ".csv", ".json", ".py", ".log", ".yaml", ".yml", ".xml"}:
        raw = p.read_bytes()[:1_000_000]
        for encoding in ("utf-8", "utf-16", "cp949"):
            try:
                return raw.decode(encoding)[:LIMIT], "ok"
            except UnicodeError:
                pass
        return raw.decode("utf-8", errors="replace")[:LIMIT], "partial"
    if ext in {".docx", ".hwpx"}:
        with zipfile.ZipFile(p) as archive:
            if sum(i.file_size for i in archive.infolist()) > 64 * 1024**2:
                return "", "expanded_size_limit"
            names = (["word/document.xml"] if ext == ".docx" else
                     sorted(n for n in archive.namelist() if n.startswith("Contents/section") and n.endswith(".xml")))
            texts = []
            for name in names:
                root = ElementTree.fromstring(archive.read(name))
                texts.extend(e.text for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "t" and e.text)
            return " ".join(texts)[:LIMIT], "ok"
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(p)
        return "\n".join(page.extract_text() or "" for page in reader.pages[:100])[:LIMIT], "ok"
    if ext == ".hwp":
        result = subprocess.run([sys.executable, "-c", "from hwp5.hwp5txt import main; main()", str(p)],
                                capture_output=True, text=True, timeout=10)
        return (result.stdout[:LIMIT], "ok") if result.returncode == 0 else ("", "hwp_parse_error")
    return "", "unsupported"


if __name__ == "__main__":
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    try:
        text, status = extract(sys.argv[1])
        print(json.dumps({"text": text, "status": status}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"text": "", "status": type(exc).__name__}))
