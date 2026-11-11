# Agentic Studio: Windows quick start

**Download one file: `AgenticStudio-1.0.0-win-x64.zip` (about 502 MB).**
This is a portable app: extract it and open it. **There is no Setup.exe installer
in this release.** You do not need Python, Docker or any commands.

The ZIP contains:

| Item | What it does |
| --- | --- |
| `AgenticStudio.exe` | Starts the app and opens the dashboard |
| `_internal` | Includes the backend, Python and browser files the app needs |
| `BrowserCompanion` | Extension for using your existing Chrome or Edge tab |
| `GettingStarted.txt` | These setup instructions |

**Keep the extracted files and folders together. Do not move the EXE alone.**

## Open the app

1. Right-click the ZIP, choose **Extract All**, and select a permanent folder.
2. Open that folder and double-click **AgenticStudio.exe**.
3. Keep its small status window open. The dashboard opens in your browser.
4. Create a local account, open **API connection**, and add your own OpenAI API key.
5. Choose **Open a new browser**, describe your task and start. This option uses
   the included browser and needs no extension setup.
6. Review the results, then **Save** and download Excel, CSV or JSON.

Complete website sign-in, CAPTCHA or missing details when prompted.
If your development dashboard is already running, close it first.

## Use your existing Chrome or Edge tab (optional)

1. In the app's status window, click **Extension setup** to open the included folder.
2. Open `chrome://extensions` or `edge://extensions` in your browser.
3. Turn on **Developer mode**, click **Load unpacked**, and select the
   **BrowserCompanion** folder. Disable any older developer copy first.
4. Keep the dashboard signed in in that same browser. Open your website tab,
   open Browser Companion, describe your task and click **Start**.

The extension is included in the download but must be added to the browser
separately. You do not need the separate Companion ZIP for these steps.

## Where it runs and saves

The backend starts automatically on **your own computer**. It does not depend
on the developer's PC. Your prompt and captured page content go to OpenAI over
the internet; API usage is billed to your configured account.

Accounts and results are saved in `%LOCALAPPDATA%\AgenticStudio\data`.
Use **Open saved-data folder** in the status window to find them.
Keep the app and dashboard tab open during tasks. Stop the task, then choose
**Stop and close** in the app's status window when finished.

This is an unsigned pilot package awaiting manual verification.
[Build and release details for engineers](WINDOWS_RELEASE_BUILD.md).
