# Public Release Audit

Initial audit date: 2026-10-16. Pre-cleanup branch: `dev-ts` at
`f84514b1e44ce61d901bf3fc0f410d7a0ea53ba1`, plus the existing uncommitted
worktree changes. Repeat the scans after any further changes or fetches.

## Result

No credentials were detected by Gitleaks v8.24.3 with its built-in rules in
the reachable root history, locally available camera-submodule history,
or a snapshot of publishable working files. This is a bounded audit, not a
guarantee that no private information exists.

The initial audit findings below describe the pre-cleanup history. The
cleanup section records the subsequent rewrite and verification. Remote
visibility and non-Git surfaces still need verification before public release.

## Scope and Evidence

- Root refs included local branches, remote-tracking branches, backup refs,
  and local Codex refs: 70 reachable commits and 193 unique historical blobs.
- `gitleaks git --log-opts='--all --full-history' --redact=100` reported
  68 commits with scanned patch content, about 1.34 MB, and no leaks.
- The working-file snapshot contained 92 regular files, including tracked
  files and non-ignored untracked UI files. `gitleaks dir --redact=100`
  scanned about 399 KB and reported no leaks. This report was written after
  that scan; it contains only audit findings and no raw secret values.
- The camera submodule was at
  `af9b38a2fa4c09ed251a6dcc1c06652daa818f3a`. Its local Git history scan
  covered six commits, about 164 KB, and reported no leaks.
- Supplemental checks covered credential-like strings in commit messages,
  author/committer identities, historical private-data paths, and local
  home-directory paths. No credential candidates were found in messages.
- No committed recording, transcript, log, or database artifacts were found
  under the historical private-data directories. `vlog/` and `logs/` contain
  only tracked `.gitkeep` placeholders.

## Privacy Findings

- Two historical versions of `config/env` remain reachable, despite the file
  now being ignored. Their keys are schema/pipeline versions and video,
  audio, and VAAPI device configuration. No credentials were detected.
- `dev-ts` uses the `kexec-run` author/committer identity. The cached remote
  refs for `main`, `dev`, and `recording-july`, and a local identity-rewrite
  backup ref, retain a different author name and email. Making an existing
  repository public exposes all published branches, not only its default
  branch. Email values are deliberately omitted from this document.
- Older `docs/avcam.md` content contains a machine-specific home path. The
  current file does not. Editing today's file cannot remove historical data.
- Tracked `config/tags.txt` and `config/custom_schema.yaml` expose tag and
  field definitions. They contain no individual recording values; review
  vocabulary separately if these definitions themselves are personal.
- Local `.codegraph/` and `.codebase-memory/` caches are now ignored to prevent
  accidental publication of local indexes. Existing runtime, recording,
  transcript, log, SQLite, and test-output ignore rules were verified using
  nonexistent probe paths; no test data was created.

## License and Publication

- Added a root MIT license, copyright 2026 `kexec-run`, and a README link.
- `tools/avcam-cli` has its own tracked MIT license and copyright notice.
  The root license does not replace dependency license notices.
- The camera submodule URL uses SSH. HTTPS would allow anonymous cloning
  without GitHub SSH setup. Remote submodule visibility was not verified.
- GitHub CLI authentication is unavailable, so repository visibility,
  remote-only refs, PR refs, releases, artifacts, issues, and attachments
  were not audited. Local remote-tracking refs are a cached view.
- Ignored personal files and unreachable/dangling Git objects were outside
  scope. Do not publish a raw workspace or `.git` archive as a substitute
  for a reviewed Git push.

## History Cleanup Completed

All four GitHub branches (`dev`, `dev-ts`, `main`, and `recording-july`) were
rewritten and replaced atomically using exact `--force-with-lease` checks.
Live remote refs were verified afterward. The cleaned tips are:

- `dev-ts`: `4a158f7cb0f3cdb52e4e2e2a28c6f2bd6c1dc79a`
- `main`: `baa6f3690cd8b85c46c885f892c1ead0cb71aa26`
- `dev` and `recording-july`: `6bbb539c1c8686d1fabe422636a9fc91f4fcda6f`

Verification traversed all 33 reachable cleaned commits across those branches:

- No `vlog/`, `logs/`, `.privledger/`, or `config/env` paths remain.
- No MOV, MP4, MKV, SQLite, or database file paths remain.
- Both author and committer identities use `kexec-run` with a GitHub noreply
  address. Historical home-directory usernames were replaced with `USER`.
- Branch-tip file comparisons found only the intended placeholder removals;
  application source was preserved. Gitleaks re-scanned all 33 cleaned commits
  and reported no leaks.

Local branch refs were aligned to their rewritten equivalents while preserving
the working-file contents and existing uncommitted changes. Local `main`
remains at the cleaned equivalent of its original, older commit. No development
changes were merged into `main` as part of this cleanup.

Original mirrors and a local-ref backup bundle remain under the ignored
`.privledger/history-cleanup.G52g3O/` directory for recovery. Local backup refs,
reflogs, and tool snapshots may also retain old objects; never mirror-push this
working checkout or distribute its `.git` directory. Other existing clones
must adopt the rewritten history before pushing, to avoid reintroducing it.

## Remaining Release Checks

1. Verify GitHub and submodule visibility and inspect non-Git remote surfaces.
2. Verify the camera submodule's own identity/privacy history separately before
   changing its visibility; this rewrite affected only the root repository.
3. Re-scan the exact final commit after demo assets and release edits are added.

History cleanup was pushed. No branch promotion or visibility change was performed.
Redacted scanner reports were kept outside the repository in a temporary
audit directory; they are not release artifacts.
