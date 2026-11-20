# Guides

Static PDF guides served directly at `/assets/guides/<filename>` (see the
`/assets` mount in `app/main.py`) — no upload endpoint, no database row, just
a file on disk.

To publish/update the auditee AI Assistant user guide, drop the converted PDF
here with this exact filename (the front-end links to it directly):

```
app/assets/guides/auditee-ai-assistant-user-guide.pdf
```

Replacing the file in place (same filename) is enough to update the guide —
no code change needed on either side.
