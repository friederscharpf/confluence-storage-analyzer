# Version V1.1
# Confluence Storage & Attachments Analysis
# - Robust link check across versions (handles special chars, HTML-escaped and URL-encoded names)
# - Tries to fetch version info for attachments; falls back gracefully
# - Reliable client-side sorter for HTML tables (no external libs)
# - Keeps TOP-100, Unreferenced lists, Download/Attachment/API Delete links
# - English labels and messages
# - Optional config file for Confluence credentials

import os
import csv
import requests
from datetime import datetime
from html import escape, unescape
from urllib.parse import quote
from pathlib import Path
import configparser
import sys

# ---------------------- VERSION -----------------------
VERSION = "V1_1"

# ---------------------- CONFIG ------------------------
BASE_URL = ""
API_USER = ""
API_TOKEN = ""

# Try to read config file if values are empty
config_path = Path(__file__).parent / "confluence_storage_analyzer.cfg"
if config_path.exists():
    config = configparser.ConfigParser()
    config.read(config_path)
    if not BASE_URL:
        BASE_URL = config.get("confluence", "base_url", fallback="")
    if not API_USER:
        API_USER = config.get("confluence", "api_user", fallback="")
    if not API_TOKEN:
        API_TOKEN = config.get("confluence", "api_token", fallback="")

# Validate config
if not BASE_URL or not API_USER or not API_TOKEN:
    print("ERROR: BASE_URL, API_USER, and API_TOKEN must be set either in the script or in confluence_storage_analyzer.cfg")
    sys.exit(1)

# Output folder with version in name
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_ROOT = Path(f"confluence_analysis_{VERSION}_{timestamp}")
OUTPUT_ROOT.mkdir(exist_ok=True)

# ---------------------- HELPERS ------------------------
def api_get(url, params=None):
    """Simple GET with auth, raises on failure"""
    r = requests.get(url, auth=(API_USER, API_TOKEN), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def safe_api_get(url, params=None):
    """Like api_get but returns None on failure (resilient)."""
    try:
        return api_get(url, params=params)
    except Exception:
        return None

def get_spaces():
    """Fetch all spaces in Confluence instance."""
    spaces = []
    start = 0
    while True:
        data = safe_api_get(f"{BASE_URL}/rest/api/space", params={"limit": 50, "start": start})
        if not data:
            break
        spaces.extend(data.get("results", []))
        # check for next page
        if "_links" in data and "next" in data["_links"]:
            start += 50
        else:
            break
    return spaces

def get_all_pages(space_key):
    """Fetch all pages in a space, paginated."""
    pages = []
    start = 0
    while True:
        params = {"spaceKey": space_key, "limit": 100, "start": start, "type": "page"}
        data = safe_api_get(f"{BASE_URL}/rest/api/content", params=params)
        if not data:
            break
        pages.extend(data.get("results", []))
        if "_links" in data and "next" in data["_links"]:
            start += 100
        else:
            break
    return pages

def get_attachments_from_page(page_id):
    """
    Fetch attachments of a page. We request expand=version to get version meta.
    We will attempt to fetch fuller version details for each attachment afterwards.
    """
    attachments = []
    start = 0
    while True:
        data = safe_api_get(f"{BASE_URL}/rest/api/content/{page_id}/child/attachment",
                            params={"limit": 100, "start": start, "expand": "version"})
        if not data:
            break
        for att in data.get("results", []):
            # leave a slot for versions list; we'll try to enrich it
            att["versions_all"] = []
        attachments.extend(data.get("results", []))
        if "_links" in data and "next" in data["_links"]:
            start += 100
        else:
            break
    return attachments

def get_attachment_versions(page_id, attachment_id):
    """
    Try to fetch all versions for a given attachment.
    Endpoint attempted:
      /rest/api/content/{pageId}/child/attachment/{attachmentId}?expand=version
    If that doesn't deliver multiple versions, try /rest/api/content/{attachmentId}?expand=version
    Returns list of version dicts (at least current representation).
    """
    # 1) try page-scoped endpoint
    data = safe_api_get(f"{BASE_URL}/rest/api/content/{page_id}/child/attachment/{attachment_id}", params={"expand":"version"})
    if data and "results" in data and len(data["results"]) > 0:
        res = data["results"][0]
        ver = res.get("version")
        if ver:
            # sometimes the single result is the attachment itself
            return [res]
        else:
            return [res]
    # 2) try content endpoint for attachment id
    data2 = safe_api_get(f"{BASE_URL}/rest/api/content/{attachment_id}", params={"expand":"version"})
    if data2:
        return [data2]
    # fallback: None
    return None

def normalize_title_variants(title):
    """
    Build possible variants that may appear in page HTML:
    - original title
    - HTML-escaped (escape)
    - HTML-unescaped (unescape)
    - URL-encoded (quote)
    - In quotes patterns used by ri:attachment (ri:filename="...") etc.
    """
    variants = set()
    if title is None:
        return []
    title = str(title)
    variants.add(title)
    variants.add(escape(title))
    variants.add(unescape(title))
    try:
        variants.add(quote(title, safe=''))
    except Exception:
        pass
    # also consider spaces replaced by + (some encodings)
    variants.add(title.replace(" ", "+"))
    # patterns common in storage format
    variants.add(f'ri:filename="{title}"')
    variants.add(f'ri:filename="{escape(title)}"')
    variants.add(f'ri:attachment ri:filename="{title}"')
    variants.add(f'ri:attachment ri:filename="{escape(title)}"')
    # anchor / href containing filename or download path
    variants.add(f'/download/attachments/')
    return list(variants)

def is_attachment_linked_on_page_versions(page_id, versions):
    """
    Robust check: for each version's title we try multiple variants.
    Also check for download-URL patterns that may include attachment id or filename.
    Returns True if any variant is found in page storage HTML.
    """
    data = safe_api_get(f"{BASE_URL}/rest/api/content/{page_id}", params={"expand":"body.storage"})
    if not data:
        return False
    html_content = data.get("body", {}).get("storage", {}).get("value", "") or ""
    html_low = html_content.lower()

    for v in versions:
        title = v.get("title") if isinstance(v, dict) else str(v)
        if not title:
            continue
        variants = normalize_title_variants(title)
        for var in variants:
            if var in html_content or var.lower() in html_low:
                return True
        try:
            encoded = quote(title, safe='')
            if encoded in html_content or encoded in html_low:
                return True
        except Exception:
            pass
        base = title.rsplit('/', 1)[-1]
        if base and (base in html_content or base.lower() in html_low):
            return True
    return False

# ---------------------- ANALYZE SPACE -----------------
def analyze_space(space, all_attachments_global):
    space_key = space.get("key")
    space_name = space.get("name", space_key)
    print(f"Analyzing Space: {space_key} - {space_name}")

    space_folder = OUTPUT_ROOT / space_key
    space_folder.mkdir(exist_ok=True)

    pages = get_all_pages(space_key)
    for page in pages:
        page_id = page.get("id")
        page_title = page.get("title")
        page_url = BASE_URL + page.get("_links", {}).get("webui", "")

        attachments = get_attachments_from_page(page_id)
        for att in attachments:
            att_id = att.get("id")
            filename = att.get("title")
            size = att.get("extensions", {}).get("fileSize", 0)
            download_url = BASE_URL + att.get("_links", {}).get("download", "")
            delete_url_free = f"{BASE_URL}/pages/viewpageattachments.action?pageId={page_id}"
            delete_url_api = f"{BASE_URL}/rest/api/content/{att_id}"

            # try to get full versions list
            versions = get_attachment_versions(page_id, att_id)
            if not versions:
                # fallback: treat current att object as single-version array
                versions = [att]

            # check if any version is linked on the owning page
            is_linked_on_page = is_attachment_linked_on_page_versions(page_id, versions)

            att_info = {
                "id": att_id,
                "name": filename,
                "size": size,
                "download_url": download_url,
                "delete_url_free": delete_url_free,
                "delete_url_api": delete_url_api,
                "original_page": {"id": page_id, "title": page_title, "url": page_url},
                "linked_pages": [],
                "is_linked_on_page": is_linked_on_page,
                "versions": versions
            }

            if att_id not in all_attachments_global:
                all_attachments_global[att_id] = att_info
            else:
                all_attachments_global[att_id]["linked_pages"].append({"id": page_id, "title": page_title, "url": page_url})
                try:
                    all_attachments_global[att_id]["versions"].extend(v for v in versions if v not in all_attachments_global[att_id]["versions"])
                except Exception:
                    pass

    # Build per-space file list (files whose original_page is within this space)
    space_files = [a for a in all_attachments_global.values() if a.get("original_page", {}).get("url", "").startswith(f"{BASE_URL}/spaces/{space_key}")]
    # sort by size desc
    space_files.sort(key=lambda x: x.get("size", 0), reverse=True)

    # unreferenced: none of the versions are linked anywhere (owning page nor other pages)
    unreferenced_files = []
    for a in space_files:
        linked_elsewhere = [p for p in a.get("linked_pages", []) if p.get("id") != a.get("original_page", {}).get("id")]
        any_linked = a.get("is_linked_on_page", False) or len(linked_elsewhere) > 0
        if not any_linked:
            unreferenced_files.append(a)

    # write CSV/HTML for this space
    csv_path = space_folder / f"{space_key}_attachments.csv"
    html_path = space_folder / f"{space_key}_attachments.html"
    write_csv_html(space_files, csv_path, html_path, space_name)

    csv_unref = space_folder / f"{space_key}_unreferenced.csv"
    html_unref = space_folder / f"{space_key}_unreferenced.html"
    write_csv_html(unreferenced_files, csv_unref, html_unref, space_name + " (Unreferenced)")

    return {
        "space_key": space_key,
        "space_name": space_name,
        "total_size": sum(a.get("size", 0) for a in space_files),
        "file_count": len(space_files),
        "html": html_path,
        "html_unref": html_unref,
        "unreferenced_count": len(unreferenced_files)
    }

# ---------------------- CSV + HTML Writer -----------------
def write_csv_html(attachments, csv_path, html_path, space_name):
    # CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = [
            "Filename", "Size(Bytes)", "Size(MB)", "Download URL",
            "Original Page", "Linked on Page", "Linked on Other Pages",
            "Attachment Page Link", "API Delete Link"
        ]
        w.writerow(header)
        for att in attachments:
            linked_other = [p for p in att.get("linked_pages", []) if p.get("id") != att.get("original_page", {}).get("id")]
            linked_other_str = ", ".join(f"{p.get('title')} ({p.get('url')})" for p in linked_other)
            row = [
                att.get("name"),
                att.get("size"),
                f"{att.get('size', 0)/(1024*1024):.2f}",
                att.get("download_url"),
                f"{att.get('original_page', {}).get('title')} ({att.get('original_page', {}).get('url')})",
                "Yes" if att.get("is_linked_on_page") else "No",
                linked_other_str,
                att.get("delete_url_free"),
                att.get("delete_url_api")
            ]
            w.writerow(row)

    # HTML
    rows = ""
    for att in attachments[:100]:
        linked_other = [p for p in att.get("linked_pages", []) if p.get("id") != att.get("original_page", {}).get("id")]
        linked_other_html = "<br>".join(f'<a href="{p.get("url")}" target="_blank">{escape(p.get("title"))}</a>' for p in linked_other)
        rows += f"""
        <tr>
            <td>{escape(att.get('name') or '')}</td>
            <td data-sort="{att.get('size', 0)}" style="text-align:right">{att.get('size',0)/1024/1024:.2f} MB</td>
            <td><a href="{att.get('download_url')}" target="_blank">Download</a></td>
            <td><a href="{att.get('original_page', {}).get('url')}" target="_blank">{escape(att.get('original_page', {}).get('title') or '')}</a></td>
            <td>{'Yes' if att.get('is_linked_on_page') else 'No'}</td>
            <td>{linked_other_html}</td>
            <td><a href="{att.get('delete_url_free')}" target="_blank">Attachment Page</a></td>
            <td><a href="{att.get('delete_url_api')}" target="_blank">API Delete</a></td>
        </tr>
        """

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(space_name)} Report</title>
<style>
body {{ font-family: Arial, sans-serif; padding: 18px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; vertical-align: top; }}
th {{ background: #f2f2f2; cursor: pointer; }}
th.sort-asc::after {{ content: " ▲"; }}
th.sort-desc::after {{ content: " ▼"; }}
</style>

<!-- Inline robust sorter (no external libs) -->
<script>
document.addEventListener('DOMContentLoaded', function () {{
    function getCellValue(row, idx) {{
        const cell = row.children[idx];
        if (!cell) return "";
        const sortAttr = cell.getAttribute("data-sort");
        if (sortAttr !== null) return sortAttr;
        return cell.textContent.trim();
    }}

    function comparer(idx, asc) {{
        return function(a, b) {{
            const v1 = getCellValue(asc ? a : b, idx);
            const v2 = getCellValue(asc ? b : a, idx);
            const n1 = parseFloat(String(v1).replace(',', '.'));
            const n2 = parseFloat(String(v2).replace(',', '.'));
            if (!isNaN(n1) && !isNaN(n2)) return n1 - n2;
            return String(v1).localeCompare(String(v2), undefined, {{numeric: true, sensitivity: 'base'}});
        }};
    }}

    document.querySelectorAll("table.sortable").forEach(table => {{
        const ths = table.querySelectorAll("th");
        ths.forEach((th, idx) => {{
            th.addEventListener('click', function() {{
                const tbody = table.tBodies[0] || table;
                const rows = Array.from(tbody.querySelectorAll("tr"));
                const asc = !th.classList.contains('sort-asc');
                ths.forEach(h => h.classList.remove('sort-asc','sort-desc'));
                th.classList.add(asc ? 'sort-asc' : 'sort-desc');
                rows.sort(comparer(idx, asc));
                rows.forEach(r => tbody.appendChild(r));
            }});
        }});
    }});
}});
</script>

</head>
<body>
<h1>Space: {escape(space_name)}</h1>
<p><b>Total Files:</b> {len(attachments)} | <b>Top 100 files displayed</b></p>
<table class="sortable">
<thead>
<tr>
  <th>Filename</th><th>Size</th><th>Download</th><th>Original Page</th><th>Linked on Page</th><th>Linked on Other Pages</th><th>Attachment Page</th><th>API Delete Link</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

# ---------------------- ROOT HTML ----------------------
def generate_root_html(space_results):
    rows = ""
    for s in space_results:
        html_rel = os.path.relpath(s["html"], OUTPUT_ROOT)
        html_unref_rel = os.path.relpath(s["html_unref"], OUTPUT_ROOT)
        rows += f"""
        <tr>
            <td>{escape(s['space_name'])} ({s['space_key']})</td>
            <td data-sort="{s['total_size']}" style="text-align:right">{s['total_size']/1024/1024:.2f} MB</td>
            <td data-sort="{s['file_count']}">{s['file_count']}</td>
            <td><a href="{html_rel}" target="_blank">Report</a></td>
            <td><a href="{html_unref_rel}" target="_blank">Unreferenced</a> ({s.get('unreferenced_count',0)})</td>
        </tr>
        """

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Confluence Storage Analysis Overview</title>
<style>
body {{ font-family: Arial, sans-serif; padding: 18px; }}
table {{ border-collapse: collapse; width: 90%; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
th {{ background: #f2f2f2; cursor: pointer; }}
th.sort-asc::after {{ content: " ▲"; }}
th.sort-desc::after {{ content: " ▼"; }}
</style>
<script>
document.addEventListener('DOMContentLoaded', function () {{
    function getCellValue(row, idx) {{
        const cell = row.children[idx];
        if (!cell) return "";
        const sortAttr = cell.getAttribute("data-sort");
        if (sortAttr !== null) return sortAttr;
        return cell.textContent.trim();
    }}
    function comparer(idx, asc) {{
        return function(a, b) {{
            const v1 = getCellValue(asc ? a : b, idx);
            const v2 = getCellValue(asc ? b : a, idx);
            const n1 = parseFloat(String(v1).replace(',', '.'));
            const n2 = parseFloat(String(v2).replace(',', '.'));
            if (!isNaN(n1) && !isNaN(n2)) return n1 - n2;
            return String(v1).localeCompare(String(v2), undefined, {{numeric: true, sensitivity: 'base'}});
        }};
    }}
    document.querySelectorAll("table.sortable").forEach(table => {{
        const ths = table.querySelectorAll("th");
        ths.forEach((th, idx) => {{
            th.addEventListener('click', function() {{
                const tbody = table.tBodies[0] || table;
                const rows = Array.from(tbody.querySelectorAll("tr"));
                const asc = !th.classList.contains('sort-asc');
                ths.forEach(h => h.classList.remove('sort-asc','sort-desc'));
                th.classList.add(asc ? 'sort-asc' : 'sort-desc');
                rows.sort(comparer(idx, asc));
                rows.forEach(r => tbody.appendChild(r));
            }});
        }});
    }});
}});
</script>
</head>
<body>
<h1>Confluence Storage Analysis from {timestamp}</h1>
<table class="sortable">
<thead>
<tr><th>Space</th><th>Total Size (MB)</th><th>Files</th><th>Report</th><th>Unreferenced Report</th></tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""
    path = OUTPUT_ROOT / "index.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

# ---------------------- MAIN --------------------------
def main():
    all_attachments_global = {}
    spaces = get_spaces()
    results = []

    for space in spaces:
        res = analyze_space(space, all_attachments_global)
        results.append(res)

    generate_root_html(results)
    print("\nDONE! Analysis folder created:")
    print(os.path.abspath(OUTPUT_ROOT))

if __name__ == "__main__":
    main()

