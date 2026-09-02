# Stele v1.0.2

## Included changes

- Integrated the expanded desktop application with works, witnesses, fragments, reconstruction, and analytics.
- Translated the public website, browser edition, desktop UI, messages, and documentation into English.
- Added the new canonical sample GeoPackage at `desktop/stele_app/data/demo_project.gpkg`.
- Added persistent English disclaimers identifying all bundled examples as fictional, AI-generated mock data.
- Added **Delete all sample data** to the Dashboard. The action requires the exact phrase `REMOVE SAMPLE DATA`, creates a timestamped GeoPackage backup, and then replaces the demo corpus with a clean project while retaining schema and controlled vocabularies.
- Existing project databases are migrated automatically and non-destructively when opened by v1.0.2.

## Publish the update

Review the files, then run from the repository root:

```bash
git add -A
git commit -m "Release Stele v1.0.2"
git push origin main
git tag v1.0.2
git push origin v1.0.2
```

Pushing `main` updates GitHub Pages. Pushing the `v1.0.2` tag triggers the release workflow, which builds and uploads the macOS, Windows, and Linux packages.

Do not copy the bundled demo database over an existing user's project. Installed user databases live in the operating system's application-data directory and are preserved during normal application replacement; v1.0.2 applies only the required schema migrations when it opens them.

## Verification

- Desktop automated suite: 100 unit tests plus 163 legacy scenario checks.
- Upgrade smoke test: a v1.0.1 project retained its objects and text documents, received the new schema, and opened the new Works and Dashboard routes successfully.
- Bundled GeoPackage: byte-for-byte identical to the supplied `project(3).gpkg`; SQLite integrity check passed.
- Web JavaScript syntax, sample JSON, and sample TEI XML validated.
