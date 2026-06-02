# Refresh the "Most Used Languages" card locally — no cloud PAT required.
# Uses your existing `gh` login; the read token never leaves this machine.
# Run on demand, or wire into Task Scheduler for periodic refresh.
$ErrorActionPreference = "Stop"
$repo = "C:\Users\rohan\rohanrgit"

$env:GH_TOKEN = (gh auth token)
python "$repo\scripts\generate_languages.py"
Remove-Item Env:\GH_TOKEN

git -C $repo add assets/langs-light.svg assets/langs-dark.svg
git -C $repo diff --staged --quiet
if ($LASTEXITCODE -ne 0) {
    git -C $repo commit -m "chore: refresh languages card (local)"
    git -C $repo push
    Write-Output "Languages card refreshed and pushed."
} else {
    Write-Output "No change - languages card already current."
}
