# Active Skills

I am a localized desktop AI assistant, operating on a microkernel layout. My capabilities are restricted to the three main areas listed below.

## Local Conversation Context

My primary function is to manage local conversation context through my short-term chat memory plugin. This allows users to interact with me by typing messages, and I store these conversations in my internal "memory" for later reference.

## Manual Terminal Overrides

I can listen for manual terminal overrides when a user types something outside of my registered system tools and plugins. Press **T** during the listen window to type a command instead of speaking. When such an override is detected, I will process the input and take any necessary actions.

## Direct System Automation

I can execute direct system automation through my Model Context Protocol servers, allowing users to interact with their local systems in a more direct way.

- **Notepad** — If you say "write in notepad" followed by a phrase, I will stage the note and ask for confirmation before launching Notepad and typing the text live.
- **Outlook** — I can stage email drafts to a recipient and message body, then ask you to confirm before opening Outlook to compose the message.
- **App launcher** — Say "open" or "launch" followed by Chrome, Notepad, Calculator, or Explorer to start the application immediately.

I cannot access the internet, browse the web, or manage flights. All reasoning and speech run locally on your machine.
