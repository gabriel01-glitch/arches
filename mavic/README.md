# Los Primos

Private availability calendar for the Eichelmann Burk Grandkids.
Pick your card once, drag it onto the days you can make it, and everyone sees it.

## What's in here

| Path | What it is |
|---|---|
| `public/index.html` | The whole app (one file). The family list is at the top of the script, marked **EDIT HERE**. |
| `public/avatars/` | Put `gabriel.png`, `oscar.png`, etc. here. Missing ones show the emoji card. |
| `netlify/functions/cal.mjs` | The shared storage (Netlify Blobs) and the family code check. |
| `netlify.toml` | Netlify settings. No build command needed. |
| `AVATAR-PROMPTS.md` | ChatGPT prompts for the 10 cards. |

## Go live (about 10 minutes, free)

1. **GitHub**: New repository, name it `los-primos`, set it to **Private**, create.
   Click **uploading an existing file**, drag in everything from this folder (keep the folders), **Commit changes**.
2. **Netlify**: **Add new project > Import an existing project > GitHub**, pick `los-primos`.
3. Optional: a family code. Without one, the link alone opens the calendar (easiest).
   If the link ever spreads, add an environment variable `FAMILY_CODE` in Netlify
   (a long random value like `kakapo-tamales-rainbow-4827`) and redeploy. Then share
   `https://your-site.netlify.app/#code=THATCODE` so nobody has to type it.
4. **Deploy**. Then **Project configuration > Change project name**, for example `los-primos-eb`.
5. Share the link in the WhatsApp group and pin it. One tap opens the calendar.

## Good to know

- **Privacy**: the site is hidden from search engines and the address is not guessable. Anyone holding the link can open it, so share it only in the group. For a real lock, set `FAMILY_CODE` (see step 3): the server then refuses anyone without it.
- **Honor system**: anyone with the code can tap any card. It's family. Every change shows in "What's new", confirmed plans can't be removed until reopened, and removing a plan has Undo.
- **Leaked link**: set or change `FAMILY_CODE` in Netlify and redeploy. Every phone then asks for the code.
- **Netlify credits**: if your account is on the credit plan (300 free credits a month), every production deploy costs 15 credits and every GitHub commit triggers one. Batch your edits. The calendar's own traffic is tiny. If credits ever hit zero, Netlify pauses all your sites until next month.
- **Months**: the calendar always shows at least 12 months ahead, so it never runs out.
- **Adding or renaming a cousin**: change the list in `public/index.html` (EDIT HERE) and the `MEMBER_IDS` line in `netlify/functions/cal.mjs`. The server refuses anyone not on its list.
- **Time zones**: plans store their own time zone; each phone also shows the time in its own zone. A date only counts as "past" once it is over everywhere the family lives (`zones` in EDIT HERE).
- **Week starts Monday**: set `weekStart: 1`.
