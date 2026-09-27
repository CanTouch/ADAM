# A.D.A.M

Adam is your personal computer agent. You tell it what you want, by typing or by voice, and it does it one step at a time on this computer: finding files, writing notes, browsing in your own Chrome, reading your Obsidian vault, opening apps and windows.

## Starting Adam

- Adam starts by itself when you log in.
- To start it yourself, open the menu and search for **Adam**, or run `./run_adam.sh` in this folder.
- Only one Adam runs at a time. Starting it again just brings the window forward.

## Talking to Adam

- **Type:** click the box at the bottom ("Ask Adam anything..."), type, and press Enter.
- **Speak:** press **Super+A** (Super is the Windows-logo key). Say your request after the pop-up appears. The Adam window doesn't need to be open. You can also click the microphone button.
- **Stop:** say or type `stop`, or click the square button. This cancels the current task and stops Adam talking.
- **Replies out loud:** say or type `voice off` or `voice on`, or click the speaker button. Adam remembers your choice.

When the Adam window is hidden, pop-ups in the corner of the screen show what it heard and what it answered.

## The orb

The orb at the top shows what Adam is doing:

| Colour | Meaning |
|---|---|
| Blue, slowly breathing | Standing by |
| Teal, rings pulsing with your voice | Listening |
| Violet, spinning fast | Working |
| Sky blue | Speaking |
| Amber | Waiting for your OK |
| Red | Something went wrong (the message is in the conversation) |

Under the title, the **CHROME** light is green when the Chrome extension is connected. The **VOICE** light is on when spoken replies are on.

The first time Adam starts after the orb design changes, it takes about 20 seconds to draw all the orb colours in the background. After that they load instantly.

## Approvals

Adam asks before it does any of these:

- deleting a file (it goes to the Trash)
- moving or renaming a file
- clicking on a web page
- typing into a form on a web page
- adding to a note that already exists
- forgetting something from its memory

Answer by typing `y` or `n`, or press Super+A and say "yes" or "no". Everything else, such as reading, searching and opening things, happens straight away.

## Memory

Tell Adam "remember that..." and it keeps that fact across restarts. Tell it "forget ..." to remove a fact. The memory is a plain text file you can read or edit yourself: `~/AgentSandbox/memory.md`.

## Recording the screen

Say or type "start recording" and Adam records the whole screen, with sound, using OBS Studio. Say "stop recording" and Adam tells you where the video was saved (your home folder, named by date and time).

- If OBS isn't open, Adam opens it quietly in the tray (the system-tray icon near the clock). On this computer that takes about 40 seconds the first time; after that, recording starts at once.
- Adam makes its own OBS scene called **Adam Demo**. Your other OBS scenes are left alone.
- Videos are 1280×720. To change that, open OBS, then Settings > Video.

## Where things are

| What | Where |
|---|---|
| Notes Adam writes | `~/AgentSandbox/notes/` |
| Screenshots | `~/AgentSandbox/screenshots/` |
| Log of every action | `~/AgentSandbox/logs/adam_log.txt` |
| Memory | `~/AgentSandbox/memory.md` |
| Voice files | `~/AgentSandbox/voices/` |
| If Adam crashes | `adam_error.txt` in this folder |

Adam can only read your Obsidian vault. It never changes it.

## Settings: `config.json`

| Setting | What it does |
|---|---|
| `api_key` | Your key for the AI model. Keep it secret. |
| `base_url` | Where the AI model lives. OpenRouter is `https://openrouter.ai/api/v1`. |
| `model` | Which AI model to use. Right now it's a free one, `google/gemma-4-26b-a4b-it:free`. |
| `fallback_models` | Backup models Adam tries, in order, when the main one is busy. OpenRouter only. |
| `max_tokens` | The longest answer the model may give (4096). Lower it if you get "requires more credits" errors. |
| `obsidian_vault` | The folder of your Obsidian vault. |
| `speak_replies` | `true` or `false`. The same as saying "voice on" or "voice off". |

Restart Adam after editing this file. Close the window, then start it again.

**Free models:** Adam currently runs on free models, so it works without credit. They can be slower, a little less careful, and sometimes busy. If every model is busy, you'll see a red "Model error". Wait a minute and try again.

**Going back to the paid model:** top up at openrouter.ai, then set `model` to `deepseek/deepseek-chat` and `fallback_models` to `[]`. Or use DeepSeek directly: create a key at platform.deepseek.com, then set `api_key` to it, `base_url` to `https://api.deepseek.com`, `model` to `deepseek-chat`, and `fallback_models` to `[]`.

## Chrome

Adam browses in your normal Google Chrome, in a tab labelled **Adam**. This needs the **Adam Bridge** extension, which is in the `extension` folder of this project and loaded in Chrome. To have Adam work on the page you're already looking at, say "use this tab" or "on this page...".
