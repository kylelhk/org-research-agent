"""Generate docs/data-flow.svg: the research agent's data flow and safeguards.

Run: python docs/make_data_flow_diagram.py docs/data-flow.svg
"""

# SVG markup and diagram labels read better unbroken, so long lines are allowed here.
# ruff: noqa: E501

import sys
from xml.sax.saxutils import escape

OUT = sys.argv[1]
W, H = 1260, 724
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

SLATE, INK, MUTED, RULE = "#334155", "#0f172a", "#64748b", "#cbd5e1"
INDIGO, EMERALD, AMBER, SKY = "#4f46e5", "#059669", "#d97706", "#0284c7"

NODE_W, NODE_H, GAP, X0 = 170, 212, 34, 35
NODE_Y = 318
xs = [X0 + i * (NODE_W + GAP) for i in range(6)]
cx = [x + NODE_W / 2 for x in xs]

out = []
add = out.append


def text(x, y, s, size=12, weight=400, fill=INK, anchor="start", italic=False):
    style = ' font-style="italic"' if italic else ""
    add(
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}"{style}>{escape(s)}</text>'
    )


def check(x, y, colour):
    add(f'<circle cx="{x}" cy="{y - 4}" r="5.5" fill="{colour}" fill-opacity="0.14"/>')
    add(
        f'<path d="M{x - 2.6} {y - 4} l1.9 2 l3.4 -3.8" fill="none" stroke="{colour}" '
        f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
    )


add(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">'
)
add("""<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0 0 L10 5 L0 10 z" fill="#475569"/></marker>
  <marker id="arrow-ext" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0 0 L10 5 L0 10 z" fill="#0284c7"/></marker>
  <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
    <feDropShadow dx="0" dy="1.5" stdDeviation="2.2" flood-color="#0f172a" flood-opacity="0.10"/></filter>
</defs>""")
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

# Title
text(30, 44, "How the research agent handles data", 22, 700)
text(
    30,
    70,
    "Each outside service gets the least data it needs. The safeguards sit in code around the AI, not only in its instructions.",
    13.5,
    400,
    MUTED,
)

# Bands
add(f'<rect x="18" y="92" width="{W - 36}" height="114" rx="14" fill="#f1f5f9"/>')
text(34, 114, "OUTSIDE SERVICES", 11, 700, MUTED)
add(
    f'<rect x="18" y="290" width="{W - 36}" height="336" rx="14" fill="#f8fafc" stroke="{RULE}" stroke-dasharray="5 5"/>'
)
text(xs[0] + 4, NODE_Y + 22 + NODE_H + 30, "LOCAL PROGRAM", 11, 700, MUTED)
text(xs[0] + 4, NODE_Y + 22 + NODE_H + 46, "runs only when a person starts it,", 11, 400, MUTED)
text(xs[0] + 4, NODE_Y + 22 + NODE_H + 60, "on the business owner's computer", 11, 400, MUTED)

# External services, above nodes 1 to 4
externals = [
    ("OpenStreetMap", "public map data"),
    ("Brave Search API", "web search, no AI"),
    ("Claude model", "Anthropic, via Claude Code"),
    ("Public websites", "each organisation's own"),
]
for i, (name, sub) in enumerate(externals):
    x = xs[i]
    add(
        f'<rect x="{x}" y="126" width="{NODE_W}" height="62" rx="10" fill="#ffffff" stroke="{RULE}" filter="url(#shadow)"/>'
    )
    text(cx[i], 152, name, 14, 700, SLATE, "middle")
    text(cx[i], 171, sub, 11.5, 400, MUTED, "middle")

# What crosses the boundary
crossings = [
    (["area and", "types"], ["names,", "websites"]),
    (["business name", "and suburb"], ["website", "address only"]),
    (["masked text,", "fit criteria"], ["structured", "answer"]),
    (["page", "request"], ["page", "(checked locally)"]),
]
for i, (up, down) in enumerate(crossings):
    top, bottom = 190, NODE_Y - 2
    add(
        f'<line x1="{cx[i] - 13}" y1="{bottom}" x2="{cx[i] - 13}" y2="{top + 2}" stroke="{SKY}" stroke-width="2" marker-end="url(#arrow-ext)"/>'
    )
    add(
        f'<line x1="{cx[i] + 13}" y1="{top + 2}" x2="{cx[i] + 13}" y2="{bottom}" stroke="{SKY}" stroke-width="2" marker-end="url(#arrow-ext)"/>'
    )
    for k, line in enumerate(up):
        text(cx[i] - 22, 238 + k * 14, line, 11, 500, SLATE, "end")
    for k, line in enumerate(down):
        text(cx[i] + 22, 238 + k * 14, line, 11, 500, SLATE)

# Local nodes
nodes = [
    (
        "1",
        "Find organisations",
        "map search by area",
        SLATE,
        ["Sends area and types only", "Hand-added list as backup"],
    ),
    (
        "2",
        "Website lookup",
        "fills missing websites",
        SLATE,
        [
            "No AI in this step",
            "Result text discarded unread",
            "Nothing cached between runs",
            "Site confirmed by its own page",
        ],
    ),
    (
        "3",
        "Research agent",
        "Claude Code, headless",
        INDIGO,
        [
            "No built-in tools",
            "One tool: the fetch gate",
            "Answer must fit a schema",
            "Page text treated as untrusted",
            "Spending and time caps",
        ],
    ),
    (
        "4",
        "Fetch gate (MCP)",
        "our own tool, in code",
        EMERALD,
        [
            "Own website only",
            "Respects robots.txt",
            "Page cap per organisation",
            "Team pages blocked",
            "Likely personal info masked",
            "Log keeps no page text",
        ],
    ),
    (
        "5",
        "Validation",
        "rules applied in code",
        EMERALD,
        [
            "Fit rating decided by code",
            "Quotes checked against pages",
            "Personal info rejected",
            "One retry, then flagged",
        ],
    ),
    (
        "6",
        "Human review",
        "Excel list",
        AMBER,
        ["Every row reviewed", "Status set per row", "Nothing sent automatically"],
    ),
]
for i, (num, title, sub, colour, controls) in enumerate(nodes):
    x, y = xs[i], NODE_Y + 22
    add(
        f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="12" fill="#ffffff" stroke="{RULE}" filter="url(#shadow)"/>'
    )
    add(
        f'<path d="M{x} {y + 12} a12 12 0 0 1 12 -12 h{NODE_W - 24} a12 12 0 0 1 12 12 v4 h-{NODE_W} z" fill="{colour}"/>'
    )
    add(f'<circle cx="{x + 22}" cy="{y + 34}" r="12" fill="{colour}" fill-opacity="0.12"/>')
    text(x + 22, y + 38.5, num, 12.5, 700, colour, "middle")
    text(x + 41, y + 39, title, 13.5, 700, INK)
    text(x + 14, y + 60, sub, 11.5, 400, MUTED, italic=True)
    add(
        f'<line x1="{x + 14}" y1="{y + 72}" x2="{x + NODE_W - 14}" y2="{y + 72}" stroke="#e2e8f0"/>'
    )
    for k, line in enumerate(controls):
        yy = y + 94 + k * 19
        check(x + 20, yy, EMERALD if colour != AMBER else AMBER)
        text(x + 32, yy, line, 11, 400, SLATE)

# Local flow arrows
mid = NODE_Y + 22 + 36
for a, b in ((0, 1), (1, 2), (4, 5)):
    add(
        f'<line x1="{xs[a] + NODE_W + 2}" y1="{mid}" x2="{xs[b] - 3}" y2="{mid}" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>'
    )
add(
    f'<line x1="{xs[2] + NODE_W + 4}" y1="{mid}" x2="{xs[3] - 4}" y2="{mid}" stroke="#475569" stroke-width="2" marker-start="url(#arrow)" marker-end="url(#arrow)"/>'
)
# Agent answer goes under the fetch gate to validation
bottom = NODE_Y + 22 + NODE_H
add(
    f'<path d="M{cx[2]} {bottom + 2} V{bottom + 26} H{cx[4]} V{bottom + 4}" fill="none" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>'
)
text((cx[2] + cx[4]) / 2, bottom + 20, "answer", 11, 500, SLATE, "middle")

# Legend
ly = 666
items = [
    (INDIGO, "AI step"),
    (EMERALD, "Safeguard enforced in code"),
    (AMBER, "Human decision"),
    (SKY, "Crosses to an outside service"),
]
x = 30
for colour, label in items:
    if colour == SKY:
        add(
            f'<line x1="{x}" y1="{ly - 4}" x2="{x + 22}" y2="{ly - 4}" stroke="{SKY}" stroke-width="2" marker-end="url(#arrow-ext)"/>'
        )
        x += 30
    else:
        add(f'<rect x="{x}" y="{ly - 12}" width="14" height="14" rx="3" fill="{colour}"/>')
        x += 22
    text(x, ly, label, 12, 500, SLATE)
    x += 9 + len(label) * 6.6 + 22
text(W - 30, ly, "Synthetic diagram: no client data", 11, 400, MUTED, "end")
text(
    30,
    ly + 30,
    "The program emails and posts nothing. Its results stay in a local Excel list for a person to review.",
    12,
    400,
    MUTED,
)

add("</svg>")
open(OUT, "w").write("\n".join(out))
print("written", OUT)
