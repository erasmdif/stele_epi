# Stele v1.0.3

This maintenance release preserves all functionality and sample data introduced
in v1.0.2 and fixes Linux binary compatibility.

## Changes

- Linux packages are built on Ubuntu 22.04 / glibc 2.35 instead of
  `ubuntu-latest`, making them compatible with Ubuntu 22.04-derived systems.
- The Linux release workflow verifies that the generated executable starts
  before publishing the archive.
- The Linux launcher uses an absolute application path and preserves arguments.
- The complete desktop source, updated sample GeoPackage, English interface,
  AI-generated-data disclaimers, sample-data removal, analytics, Works and
  witness-comparison features are included.
- The landing page includes the presentation, release screenshot and download
  instructions.

## Publishing

Copy this complete package into the repository working tree, then run:

```bash
git add -A
git commit -m "Release Stele v1.0.3"
git push origin main
git tag v1.0.3
git push origin v1.0.3
```

Use `git add -A`, not `git add .`, so files accidentally deleted by the prior
site-only update are restored in the commit.
