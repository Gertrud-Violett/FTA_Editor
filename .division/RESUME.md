# Resume

- Project: `fta-editor`
- Director session: `FTA_Editor-director`
- Team: `fta-editor-team`

This session was compacted or resumed. Both the Director and the browser agent read this note.
The Director follows every step below, before anything else. The browser agent (`FTA_Editor-browser`) does only step 6, then waits for messages.

1. Re-read `.division/STATUS.md`, the newest handoff, the open requests and `.division/board/AGENTS.md`.
2. Write your heartbeat, then start the board watcher with `--once` in the background, as a background Bash command: `bash ~/.claude/division/board-watch.sh --once .division/board` (PC_AGENTS.md section 5.1). Background commands are not restored after a resume. It exits to wake you: start it again after every wake it causes (never run two).
3. Re-launch, from the files, any subagent the resume shows as unfinished.
4. Burst teammates (agent teams) are gone after a resume. If they were on, switch them off with `~/.claude/division/pc-setup.py teams off --repo .` and carry on with subagents.
5. If setup.json has dropbox_ignore, run `powershell -NoProfile -ExecutionPolicy Bypass -File "<clone>\windows\dropbox-ignore.ps1" -Repo "<folder>"` again (new caches and worktrees; <clone> is setup.json's le_repo, <folder> this project).
6. Check `/loop`; re-create the 30-minute board /loop if it is missing or expired (loops come back after a resume but expire after 7 days):

   /loop 30m Check the board for anything new for you (PC_AGENTS.md "Each run"); if nothing is new, end the turn without a message.

7. The org chart (SETUP.md section 2, step 13): if `.division/org-chart.url` does not exist and this session has the Artifact tool (load it if it is only listed as deferred), build it and publish it as a private page now; otherwise refresh it if what waits on the CEO, the roster, the plan or a feature's state changed since it was built. Build it with `~/.claude/division/org-chart.py --repo .`.

The Director runs until the CEO closes the project (`~/.claude/division/pc-setup.py close`).
