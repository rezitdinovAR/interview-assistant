def message_to_html(content_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <title>Code Export</title>

    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">

    <style>
        :root {{
            --bg: #ffffff;
            --text: #1f2937;
            --muted: #6b7280;

            --code-bg: #272822;
            --code-text: #f8f8f2;
            --code-border: #3e3d32;
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            padding: 4px;
            font-family: 'Montserrat', sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.4;
            font-size: 12px;
        }}

        .page {{
            margin: 0;
            max-width: none;
        }}

        h1, h2, h3 {{
            margin: 1.2em 0 0.4em;
            font-weight: 700;
            line-height: 1.25;
        }}

        h1 {{ font-size: 20px; }}
        h2 {{ font-size: 16px; }}
        h3 {{ font-size: 13px; }}

        p {{
            margin: 0.2em 0 0.4em;
        }}

        .muted {{
            color: var(--muted);
        }}

        pre {{
            margin: 16px 0;
            padding: 14px 16px;
            background: var(--code-bg);
            color: var(--code-text);
            border-radius: 8px;
            border: 1px solid var(--code-border);
            overflow-x: auto;
            font-size: 12px;
            line-height: 1.45;
        }}

        code {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}

        p code {{
            background: #f3f4f6;
            color: #111827;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.8em;
        }}

        ul, ol {{
            margin: 0.4em 0 0.8em 1.2em;
        }}

        li {{
            margin: 0.2em 0;
        }}

        hr {{
            border: none;
            border-top: 1px solid #e5e7eb;
            margin: 24px 0;
        }}

        @media print {{
            body {{
                padding: 0;
            }}

            pre {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="page">
        {content_html}
    </div>
</body>
</html>"""
