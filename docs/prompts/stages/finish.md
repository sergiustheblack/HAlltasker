# Stage: finish — commit and close the issue

Prerequisite: verify is GREEN and review is APPROVED. If not, do not run
this stage.

Coordinator keeps after this stage: nothing. The issue is done.

On failure (tracker rejects the transition): stop and report to the owner;
do not amend history or force-push.

## Subagent prompt

> TASK: Commit and finish issue __ISSUE__.
>
> READ: `docs/TRACKER.md`, then the role file named there for your role
> (developer/architect/reviewer). No other repository files.
>
> RULES: this prompt's READ list is exhaustive. Follow the role file's
> closing flow exactly (`yt claim` / `yt done` / `REWORK:` routing as it
> prescribes).
>
> MAY TOUCH: the git index and one commit. The commit message is
> `__ISSUE__: <issue summary>` and must contain only the files from the
> task's whitelist. Then delete the directory `/tmp/halltasker/__ISSUE__/`.
>
> OUTPUT: a one-line report: commit hash, final issue status.
> Done when the report is produced.
