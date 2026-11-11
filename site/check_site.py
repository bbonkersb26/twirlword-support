"""Dependency-free checks for the static pages; no network or account access."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent / 'public'
class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path, self.ids, self.links, self.tags = path, set(), [], []
        self.has_language = self.has_viewport = self.has_description = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        assert tag not in {'script', 'iframe', 'form'}, f'Unexpected data/embedded surface: {self.path}: {tag}'
        assert not any(k.startswith('on') for k in a), f'Inline event handler: {self.path}'
        if tag == 'html': self.has_language = a.get('lang') == 'en'
        if tag == 'meta' and a.get('name') == 'viewport': self.has_viewport = True
        if tag == 'meta' and a.get('name') == 'description': self.has_description = bool(a.get('content'))
        if 'id' in a:
            assert a['id'] not in self.ids, f'Duplicate id: {self.path}: {a["id"]}'
            self.ids.add(a['id'])
        if tag == 'img': assert 'alt' in a, f'Missing image alternative: {self.path}'
        for key in ('href', 'src'):
            if key in a: self.links.append(a[key])

pages = {}
for path in sorted(ROOT.rglob('*.html')):
    source = path.read_text(encoding='utf-8')
    assert source.lower().startswith('<!doctype html>'), f'Missing doctype: {path}'
    assert not re.search(r'chatgpt|chat\.openai|plugin://|appstoreconnect|OWNER_CONFIGURE|TODO', source, re.I), f'Private/placeholder reference: {path}'
    page = Page(path); page.feed(source); page.close()
    assert page.has_language and page.has_viewport and page.has_description, f'Page metadata: {path}'
    for tag in ('title', 'h1', 'main'): assert page.tags.count(tag) == 1, f'Expected one {tag}: {path}'
    pages[path.resolve()] = page
external = set(); checked = 0
for page in pages.values():
    for link in page.links:
        url = urlsplit(link)
        if url.scheme or url.netloc:
            assert url.scheme == 'https' and url.hostname in {'testflight.apple.com', 'www.apple.com', 'privacy.apple.com', 'render.com'}, f'Unexpected public link: {link}'
            external.add(link); continue
        target = (ROOT / unquote(url.path).lstrip('/') if url.path.startswith('/') else page.path.parent / unquote(url.path)).resolve() if url.path else page.path.resolve()
        assert target.is_relative_to(ROOT.resolve()), f'Link escapes public files: {link}'
        if target.is_dir(): target = target / 'index.html'
        assert target.is_file(), f'Broken local link {page.path}: {link}'
        if url.fragment: assert target in pages and url.fragment in pages[target].ids, f'Broken fragment: {link}'
        checked += 1
for path in ROOT.rglob('*.svg'): ET.parse(path)
css = (ROOT / 'assets/style.css').read_text(encoding='utf-8')
assert 'prefers-reduced-motion' in css and ':focus-visible' in css and '@media' in css
assert not re.search(r'@import|url\(\s*[\'\"]?https?://', css, re.I), 'Unexpected external styles/assets'
print(json.dumps({'status': 'pass', 'htmlPages': len(pages), 'checkedLocalLinks': checked,
                  'svgAssets': len(list(ROOT.rglob('*.svg'))), 'externalLinks': sorted(external),
                  'scope': 'Static metadata/link/asset checks; browser layout and hosted HTTP validation are separate.'}, indent=2))
