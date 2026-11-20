# GitHub to Gitee backup

GitHub Actions copies repositories owned by `ckstock` to the same names under `gitee.com/ckstock`. The workflow runs every six hours at minute 17 (approximately 00:17, 06:17, 12:17 and 18:17 Beijing time; GitHub may delay scheduled runs), and supports manual dispatch.

## Scope and preservation

Public repositories are copied to public targets; `github-gitee-mirror` itself is excluded from the public job. Private repositories are copied only to targets confirmed private. A same-name public target stops the private job before code is pushed.

The backup copies Git commits, branches and tags. It does not copy Issues, pull requests, release attachments, Git LFS objects, repository settings, Actions secrets or separate wiki repositories. It never force-pushes, prunes or deletes target refs. Divergent target history requires manual resolution. Keep GitHub as the source of truth.

## Credentials

Configure repository Actions secrets `GITEE_TOKEN` (target repository creation and Git push) and `GH_MIRROR_TOKEN` (access to all owned source private repositories). Prefer a dedicated GitHub fine-grained token with Contents read-only and access to all required repositories. The current setup reuses the existing GitHub CLI OAuth credential, which has broader repo/workflow permissions; replacing or revoking it requires updating this secret. Never commit credentials or include their values in logs.

Private discovery is paginated; public discovery currently supports up to 100 owned repositories. The private job hides repository names in logs, but counts and failure diagnostics can remain visible in this public Actions repository.

## Verification and recovery

After dispatch, verify both mirror jobs, source repository counts and target branch/tag refs. A successful credential check alone is not a completed backup. Check Gitee repository capacity and permissions if creation fails. Disable the workflow to stop future backups; existing Gitee copies remain intact. Rotate credentials and update the corresponding secret if access changes.
Private targets are resolved by source name, lowercase path, then matching Gitee display name to its actual path. Multiple same-page matches stop the job. Cross-page duplicate display names remain a limitation if the target account grows beyond 100 repositories. After every private push, the workflow reads back target refs and verifies that each source branch/tag has the same SHA; extra target refs remain preserved.


## Complete account backup

All 22 currently owned GitHub repositories, including this automation repository, are included. GitHub is authoritative. Private source repositories require private Gitee targets.

After Git synchronization, `scripts/complete_backup.py` exports GitHub repository metadata, Issues, pull requests with commits/files/comments/reviews, Releases, labels and milestones into the corresponding Gitee repository's `github-metadata-backup` branch. Source identities, timestamps and links remain in JSON; these are archives, not impersonated Gitee posts. The backup branch is owned by the script and checked through its ownership marker. Each update is read back and its commit SHA verified.

Existing GitHub wiki repositories are copied to `github-wiki-backup/<source-branch>` branches in the same Gitee repository. Missing wikis are explicitly reported. The code default branch is not changed by metadata archival. If new Issues or Release assets appear, the archive job currently fails explicitly until their binary/comment handling is extended; it must not silently claim full backup. Settings requiring provider-specific permissions, secrets whose values GitHub cannot export, and external linked resources cannot be reproduced as equivalent Gitee features.

Current inventory: 22 repositories, 9 merged PRs, no Issues or Releases. Future runs discover inventory again. Workflow summary reports archive counts. Disable the workflow to stop updates; no local browser login is required for normal scheduled execution.
