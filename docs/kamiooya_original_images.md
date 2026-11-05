# Original-resolution community images

Some WeStudy archive records pointed to WordPress resized images (`-150x150`, `-1024x...`) rather than the available original. Storage preserved the downloaded bytes correctly; the source selection was the problem.

`scripts/jarvis_kamiooya_image_originals.py` tries the unsized URL only for HTTPS WeStudy upload URLs, without redirects, credentials or query parameters. It streams within the existing file limit, verifies the image container and dimensions, and stores the unchanged original bytes under a new content hash. JPEG camera MPO files are preserved as JPEG-compatible originals. Missing or unsuitable originals leave the existing image in place; no upscaling or re-encoding is performed.

The original attachment ID/source identity stays stable. Additional metadata records the actual original URL and dimensions. The previous small objects remain available for rollback and existing short-lived links. The database trigger and both importers protect upgraded records from being overwritten by old thumbnail catalogs.

The weekly `ProgramCode/alfred_python/westudy_forum_all.py` collector also prefers available original uploads and records that provenance in its catalog; the regular importer retains it. An unavailable original falls back to the current thumbnail without claiming that an original was captured.

Apply `20261105_community_original_images.sql` before running the updated importer. Existing private bucket and member authorization remain unchanged. The recovery command defaults to a dry run; `--apply` is explicit. Reports contain only record identifiers, counts, dimensions and sizes, and belong in a private nonsynchronized directory. An 80 GB project storage ceiling holds further uploads; it is not a guarantee about all organization costs or concurrent writers.

Example:

```
python scripts/jarvis_kamiooya_image_originals.py --limit 10 --report /private/path/report.json
python scripts/jarvis_kamiooya_image_originals.py --apply --limit 5000 --workers 3 --report /private/path/report.json
```

Successful records are skipped on subsequent runs. Failed/missing candidates retain their thumbnails and remain visible in the report for an explicit retry.

## Daily community attachment delta

`jarvis_kamiooya_community_daily.py` consumes full harvest CSVs after the existing daily comment import in `westudy-raimo-weekly.yml`. It also runs when the text delta is zero. Known attachment identities are skipped without binary downloads; new attachment URLs are checked independently. Missing parent comments and capacity/deferred/error counts make the job fail visibly for retry. Missing sources and untrusted external links are counted separately.

Only HTTPS WeStudy `/wp-content/uploads/` files are fetched, without redirects or authentication cookies. Other hosts and query-bearing URLs are held out rather than followed. Files are bounded at 50 MiB and validated using the existing importer. The worker prefers a larger original for new image attachments and preserves unchanged bytes, then verifies the stored hash. Local temporary binaries are removed after the run and never uploaded to CI artifacts or Git. The 80 GB project ceiling and a per-run file bound prevent unbounded backfills. This daily path does not attempt to detect replaced content behind an already known unchanged URL, or claim external links are backed up.
