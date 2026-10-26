#!/usr/bin/env bash
# Publish examples/delhi_air_quality/storymap/ as the root of the "storymap" branch for notebook.link.
#
# notebook.link loads a GitHub repository into the browser and requires it to stay under 50 MB; the main
# branch of this repository is larger, so the story map folder is published on its own branch. The branch
# is derived with `git subtree split`, so it keeps the folder's history and can be re-run after each rebuild.
#
#   ./examples/delhi_air_quality/publish_storymap_branch.sh            # split + push to origin
#   ./examples/delhi_air_quality/publish_storymap_branch.sh --no-push  # split only
#
# Afterwards:
#   https://notebook.link/github/<owner>/<repo>/tree/storymap/specta/?path=delhi_aq_storymap_ko.jGIS
set -euo pipefail

PREFIX="examples/delhi_air_quality/storymap"
BRANCH="${STORYMAP_BRANCH:-storymap}"
REMOTE="${STORYMAP_REMOTE:-origin}"

cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain -- "$PREFIX")" ]; then
  echo "error: uncommitted changes under $PREFIX; commit them first" >&2
  exit 1
fi
git subtree split --prefix="$PREFIX" -b "$BRANCH" --rejoin=false >/dev/null 2>&1 || git subtree split --prefix="$PREFIX" -b "$BRANCH"
echo "branch '$BRANCH' now points at $(git rev-parse --short "$BRANCH") (tree = $PREFIX)"
if [ "${1:-}" != "--no-push" ]; then
  git push --force-with-lease "$REMOTE" "$BRANCH"
  url="$(git remote get-url "$REMOTE" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
  echo "story map (ko): https://notebook.link/github/$url/tree/$BRANCH/specta/?path=delhi_aq_storymap_ko.jGIS"
  echo "story map (en): https://notebook.link/github/$url/tree/$BRANCH/specta/?path=delhi_aq_storymap_en.jGIS"
  echo "editor:         https://notebook.link/github/$url/tree/$BRANCH/lab/?path=delhi_aq_storymap_ko.jGIS"
  echo "storyboard (ko): https://notebook.link/github/$url/tree/$BRANCH/specta/?path=storyboard_ko.ipynb"
  echo "storyboard (en): https://notebook.link/github/$url/tree/$BRANCH/specta/?path=storyboard_en.ipynb"
fi
