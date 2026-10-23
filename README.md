# GitHub → Gitee public backup

This repository runs a GitHub Actions workflow every six hours and can also be started manually from **Actions**.

It discovers every public repository owned by `ckstock`, creates the same-name public repository under `gitee.com/ckstock` when needed, then copies branches and tags from GitHub to Gitee.

The workflow never uses force push, deletion refspecs, or pruning. A branch or tag that is later deleted on GitHub therefore remains preserved on Gitee.

## Required setup

Create the repository Actions secret `GITEE_TOKEN` with a Gitee personal access token that can create repositories and push code. The token must not be committed to this repository.
