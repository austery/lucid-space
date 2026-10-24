# Lucid Space mirror

Read the blog at **https://austery.github.io/lucid-space/**.

The private writing vault stays private. This repository contains only the receiver
and deployment configuration, plus a public Cloudflare build ID in `trigger.json`.
It never checks out the writing vault, scans notes, or runs the site generator.
Cloudflare exports explicitly selected articles and builds the complete static site.
The receiver waits for the exact requested build, checks its SHA-256 digest, and
publishes that snapshot using GitHub Pages. A fresh output and full replacement
remove withdrawn articles; prior downloadable artifacts expire after one day.
Previously published material may still exist in caches or reader downloads.

The owner's existing manual publication button requests both destinations. Normal
note synchronization does not trigger publication. If Cloudflare fails, this mirror
retains its previous deployment and the receiver eventually fails rather than
publishing an older build. If receiving or Pages deployment fails, retry this
repository's workflow for the latest request after checking the Cloudflare build.
This repository uses standard GitHub-hosted runners in a public repository.

The existing https://austery.github.io/ site is managed separately and unchanged.
