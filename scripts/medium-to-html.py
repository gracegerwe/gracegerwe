#!/usr/bin/env python3
"""Turn a saved capture of a Medium story into a page on this site.

Medium blocks this host, so the pages are captured elsewhere: raw/<page>.html
is the whole page from a server-rendered Medium mirror (libmedium), which
carries the story's text and its photographs in order. This script reads that
capture, saves the photographs into assets/medium/, and writes the page, so a
story can be redone or fixed without touching HTML by hand.

Usage: python3 medium-to-html.py                # every story in raw/
       python3 medium-to-html.py saudi shave    # only these, by page name

The article's first heading is its standfirst, printed in italics; later ones
are section headings. Photographs are saved as assets/medium/<page>-<n>.<ext>,
numbered in the order they appear in the story.
"""

import html as H
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
SITE = os.path.dirname(HERE)
IMAGES = os.path.join(SITE, "assets", "medium")
MIRROR = "https://libmedium.batsense.net"
USER_AGENT = {"User-Agent": "Mozilla/5.0"}

# page name -> (title, date)
STORIES = {
    "saudi": ("Takeaways from a free 10-day trip to Saudi Arabia", "Feb 2024"),
    "shave": ("What it was like to shave my head", "Jan 2024"),
    "70-3": ("Going from Olympic triathlon to Ironman 70.3 in two months", "Jan 2024"),
    "florida": ("Ironman Florida 70.3 Race Report", "Jan 2024"),
    "month": ("The month that triathlon took over my life", "Jan 2024"),
    "vision": ("My vision of a life worth living", "Sep 2023"),
    "endurance": ("The limits of human endurance", "Mar 2023"),
    "microbes": ("How microbes survive in extreme environments", "Feb 2023"),
    "biomimicry": ("Biomimicry", "Feb 2023"),
    "grandma": ("The grandma hypothesis — why does menopause exist?", "Jan 2023"),
    "aging": ("Why aging happens and how to slow it down", "Jan 2023"),
}

TEMPLATE = """<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>{title} — Grace Gerwe</title>
  <meta name="description" content="{desc}">

  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
  <link rel="stylesheet" href="assets/css/site.css?v=9">
</head>

<body>
  <main>
    <header>
      <h1><a href="/">Grace Gerwe</a></h1>
    </header>

    <article class="story">
      <h2 class="story-heading">{title}</h2>
      <p class="story-date">{date}</p>
{subtitle}
{body}
    </article>

    <footer>
      <a href="/writing">Writing</a>
      <div class="icons">
        <a href="https://x.com/GraceGerwe" target="_blank" rel="noopener noreferrer" aria-label="X"
          class="fa-brands fa-x-twitter"></a>
        <a href="https://www.linkedin.com/in/gracegerwe/" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn"
          class="fa-brands fa-linkedin"></a>
        <a href="mailto:grace@gerwe.com" aria-label="Email" class="fa-solid fa-envelope"></a>
      </div>
    </footer>
  </main>
</body>

</html>"""


class Node:
    def __init__(self, tag=None, attrs=None, text=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.text = text
        self.children = []


class Tree(HTMLParser):
    """A capture, as a tree, so an article can be walked in its own order."""

    VOID = {"img", "br", "hr", "meta", "link", "source", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(Node(text=data))


def find(node, tag):
    """Every node carrying this tag, below this one."""
    found = []
    for child in node.children:
        if child.tag == tag:
            found.append(child)
        found.extend(find(child, tag))
    return found


def run(node):
    """One run of text with its links and emphasis kept, other markup dropped."""
    out = []
    for child in node.children:
        if child.text is not None:
            out.append(H.escape(child.text, quote=False))
        elif child.tag == "a":
            href = H.escape(child.attrs.get("href", ""), quote=True)
            out.append(f'<a href="{href}">{run(child)}</a>')
        elif child.tag in ("strong", "b"):
            out.append(f"<strong>{run(child)}</strong>")
        elif child.tag in ("em", "i"):
            out.append(f"<em>{run(child)}</em>")
        elif child.tag == "img":
            continue
        else:
            out.append(run(child))
    return "".join(out)


def run_of(node):
    """The same, trimmed, for a node that is itself the run."""
    return re.sub(r"\s+", " ", run(node)).strip()


def save_images(page, urls):
    """Keep each photograph beside the site; return the paths, in order.

    Medium serves the originals, which are far larger than a page needs, so
    each is scaled down to at most 1400 pixels wide and re-saved.
    """
    os.makedirs(IMAGES, exist_ok=True)
    paths = []
    for n, url in enumerate(urls, start=1):
        full = url if url.startswith("http") else MIRROR + url
        ext = os.path.splitext(urllib.parse.urlparse(full).path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            ext = ".jpg"
        name = f"{page}-{n}{ext}"
        target = os.path.join(IMAGES, name)
        if not os.path.exists(target):
            with open(target, "wb") as fh:
                fh.write(fetch(full))
            shrink(target)
        paths.append(f"assets/medium/{name}")
    return paths


def fetch(mirror_url):
    """The still, from Medium's own resized copy where that answers."""
    candidates = []
    path = urllib.parse.urlparse(mirror_url).path
    if "/asset/medium/" in path:
        candidates.append("https://miro.medium.com/v2/resize:fit:1400/" + path.rsplit("/", 1)[-1])
    candidates.append(mirror_url)
    for candidate in candidates:
        try:
            request = urllib.request.Request(candidate, headers=USER_AGENT)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            continue
    raise RuntimeError(f"could not fetch {mirror_url}")


def shrink(path, widest=1400):
    """Bring one photograph down to a size a page can use."""
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(path) as image:
        if image.width <= widest:
            return
        height = round(image.height * widest / image.width)
        image = image.convert("RGB").resize((widest, height), Image.LANCZOS)
        image.save(path, quality=82, optimize=True)


def render(article, paths):
    """The article as this site's own HTML, photographs left where they were."""
    images = iter(paths)
    blocks = []
    subtitle = ""

    for block in article.children:
        tag = block.tag
        if not tag:
            continue
        if tag == "figure":
            src = next(images, None)
            if src:
                blocks.append(f'<figure><img src="{src}" alt=""></figure>')
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            label = run_of(block)
            if not label:
                continue
            if not subtitle:
                subtitle = label
            else:
                blocks.append(f"<h2>{label}</h2>" if tag in ("h1", "h2", "h3") else f"<h3>{label}</h3>")
        elif tag == "p":
            body = run_of(block)
            if body:
                blocks.append(f"<p>{body}</p>")
        elif tag in ("ol", "ul"):
            items = [i for i in (run_of(li) for li in find(block, "li")) if i]
            if items:
                fence = "ol" if tag == "ol" else "ul"
                blocks.append(f"<{fence}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{fence}>")
        elif tag == "blockquote":
            body = " ".join(filter(None, (run_of(p) for p in find(block, "p")))) or run_of(block)
            if body:
                blocks.append(f"<blockquote><p>{body}</p></blockquote>")
    return subtitle, row_up(blocks)


def row_up(blocks, per_row=3):
    """Photographs the story ran together become one horizontal row.

    Medium puts consecutive stills side by side, never stacked, so a run of
    figures is fenced into a .photo-row; a run longer than a row is split,
    the last row holding the remainder.
    """
    out, run = [], []

    def flush():
        sizes = []
        left = len(run)
        while left > 0:
            take = min(per_row, left)
            if left - take == 1 and take > 2:
                take -= 1  # a row of three then a single looks broken; 2 + 2 does not
            sizes.append(take)
            left -= take
        for size in sizes:
            chunk, run[:] = run[:size], run[size:]
            if size == 1:
                out.append(chunk[0])
            else:
                out.append('<div class="photo-row">' + "".join(chunk) + "</div>")

    for block in blocks:
        if block.startswith("<figure"):
            run.append(block)
        else:
            flush()
            out.append(block)
    flush()
    return out


def build(page, title, date):
    html = open(os.path.join(RAW, page + ".html")).read()
    tree = Tree()
    tree.feed(html)
    articles = find(tree.root, "article")
    if not articles:
        sys.exit(f"{page}: no article in the capture")
    article = articles[0]

    urls = [img.attrs.get("src", "") for img in find(article, "img") if img.attrs.get("src")]
    subtitle, blocks = render(article, save_images(page, urls))

    page_html = TEMPLATE.format(
        title=H.escape(title),
        date=date,
        desc=H.escape(re.sub(r"<[^>]+>", "", subtitle) or title)[:180],
        subtitle=f'      <p class="story-subtitle">{subtitle}</p>' if subtitle else "",
        body="\n".join("      " + block for block in blocks),
    )
    open(os.path.join(SITE, page + ".html"), "w").write(page_html)
    print(f"wrote {page}.html  ({len(blocks)} blocks, {len(urls)} photographs)")


def main():
    wanted = sys.argv[1:]
    for page, (title, date) in STORIES.items():
        if wanted and page not in wanted:
            continue
        build(page, title, date)


if __name__ == "__main__":
    main()
