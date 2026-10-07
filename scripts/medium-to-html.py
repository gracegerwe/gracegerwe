#!/usr/bin/env python3
"""Turn a saved Medium story into a page on this site.

Medium blocks this host, so the text is captured elsewhere (the browser
tools, a search backend that renders the page, or a Medium mirror) and
saved into raw/ as markdown. This script cleans that capture and writes
the page, so a story can be redone or fixed without touching the HTML by
hand.

Usage: python3 medium-to-html.py            # rewrites every page in raw/
       python3 medium-to-html.py saudi      # just one, by its file name

raw/<file>.md holds the capture. The first line, when it is a `# heading`,
is the title and is dropped, because the page prints its own; a following
`## heading` is the standfirst, printed in italics.
"""

import html as H
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
SITE = os.path.dirname(HERE)

# file name in raw/ -> (page name, title, date)
STORIES = {
    "takeaways-from-a-free-10-day-trip-to-saudi-arabia-c695b1a7410b":
        ("saudi", "Takeaways from a free 10-day trip to Saudi Arabia", "Feb 2024"),
    "what-it-was-like-to-shave-my-head-8023f02fbb3e":
        ("shave", "What it was like to shave my head", "Jan 2024"),
    "going-from-olympic-triathlon-to-ironman-70-3-in-two-months-e6278cb5704f":
        ("70-3", "Going from Olympic triathlon to Ironman 70.3 in two months", "Jan 2024"),
    "ironman-florida-70-3-race-report-1e3307a60495":
        ("florida", "Ironman Florida 70.3 Race Report", "Jan 2024"),
    "the-month-that-triathlon-took-over-my-life-cd54849374d8":
        ("month", "The month that triathlon took over my life", "Jan 2024"),
    "my-vision-of-a-life-worth-living-f036d7e0d4c1":
        ("vision", "My vision of a life worth living", "Sep 2023"),
    "the-limits-of-human-endurance-a928d130f7b0":
        ("endurance", "The limits of human endurance", "Mar 2023"),
    "how-microbes-survive-in-extreme-environments-4b3b526914c3":
        ("microbes", "How microbes survive in extreme environments", "Feb 2023"),
    "biomimicry-d91dfdb99aef":
        ("biomimicry", "Biomimicry", "Feb 2023"),
    "you-can-actually-eat-too-much-protein-4d55a4af4e82":
        ("protein", "You can actually eat too much protein", "Feb 2023"),
    "the-grandma-hypothesis-why-does-menopause-exist-1f254215f557":
        ("grandma", "The grandma hypothesis — why does menopause exist?", "Jan 2023"),
    "why-we-age-and-how-to-slow-it-down-4bcbadddf20":
        ("aging", "Why aging happens and how to slow it down", "Jan 2023"),
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
  <link rel="stylesheet" href="assets/css/site.css?v=3">
</head>

<body>
  <main>
    <header>
      <h1><a href="/">Grace Gerwe</a></h1>
      <div class="icons">
        <a href="https://x.com/GraceGerwe" target="_blank" rel="noopener noreferrer" aria-label="X"
          class="fa-brands fa-x-twitter"></a>
        <a href="https://www.linkedin.com/in/gracegerwe/" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn"
          class="fa-brands fa-linkedin"></a>
        <a href="mailto:grace@gerwe.com" aria-label="Email" class="fa-solid fa-envelope"></a>
      </div>
    </header>

    <article class="story">
      <h2 class="story-heading">{title}</h2>
      <p class="story-date">{date}</p>
{subtitle}
{body}
    </article>

    <footer>
      <a href="/writing">Writing</a>
    </footer>
  </main>
</body>

</html>"""

# the subscribe box and bylines the capture picks up from the Medium page
CLUTTER = [
    r"\n#+\s*Get [^\n]*stories in your inbox\s*\n",
    r"\nJoin Medium for free[^\n]*\n?",
    r"\n#+\s*Written by[^\n]*\n",
]


# images that live with the site instead of on Medium's CDN
IMAGES = {
    "https://miro.medium.com/v2/resize:fit:362/1*uArHifxycQPa5a3D8CdEDg.jpeg": "assets/medium/shave.jpeg",
}


def strip_clutter(text):
    for pattern in CLUTTER:
        text = re.sub(pattern, "\n", text)
    return text


def inline(text):
    text = H.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    # a bold run holding an italic run can come out as <strong>..<em>..</strong></em>
    text = text.replace("</strong></em>", "</em></strong>")
    return text


def to_html(body):
    out = []
    list_open = None
    lines = body.split("\n")

    def close_list():
        nonlocal list_open
        if list_open:
            out.append(f"</{list_open}>")
            list_open = None

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            close_list()
            i += 1
            continue
        heading = re.match(r"^(#{2,4})\s+(.*)$", line)
        if heading:
            close_list()
            level = min(len(heading.group(1)), 4)
            out.append(f"<h{level}>{inline(heading.group(2).strip())}</h{level}>")
            i += 1
            continue
        if re.match(r"^>\s?", line):
            close_list()
            quote = []
            while i < len(lines) and re.match(r"^>\s?", lines[i]):
                quote.append(inline(re.sub(r"^>\s?", "", lines[i]).strip()))
                i += 1
            out.append("<blockquote><p>" + "<br>".join(quote) + "</p></blockquote>")
            continue
        item = re.match(r"^\d+\.\s+(.*)$", line)
        if item:
            if list_open != "ol":
                close_list()
                out.append("<ol>")
                list_open = "ol"
            out.append(f"<li>{inline(item.group(1).strip())}</li>")
            i += 1
            continue
        item = re.match(r"^[-*]\s+(.*)$", line)
        if item:
            if list_open != "ul":
                close_list()
                out.append("<ul>")
                list_open = "ul"
            out.append(f"<li>{inline(item.group(1).strip())}</li>")
            i += 1
            continue
        close_list()
        paragraph = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{2,4}\s|>\s?|\d+\.\s|[-*]\s)", lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    close_list()
    return "\n".join(out)


def build(name, title, date):
    text = strip_clutter(open(os.path.join(RAW, name + ".md")).read())
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("# "):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    subtitle = ""
    if lines and lines[0].startswith("## "):
        subtitle = inline(lines.pop(0)[3:].strip())
    body = to_html("\n".join(lines))
    for remote, local in IMAGES.items():
        body = body.replace(remote, local)
    page = TEMPLATE.format(
        title=H.escape(title),
        date=date,
        desc=H.escape(re.sub(r"<[^>]+>", "", subtitle) or title)[:180],
        subtitle=f'      <p class="story-subtitle">{subtitle}</p>' if subtitle else "",
        body=body,
    )
    target = os.path.join(SITE, STORIES[name][0] + ".html")
    open(target, "w").write(page)
    print("wrote", os.path.relpath(target, SITE))


def main():
    wanted = sys.argv[1:]
    for name, (page, title, date) in STORIES.items():
        if wanted and page not in wanted:
            continue
        build(name, title, date)


if __name__ == "__main__":
    main()
