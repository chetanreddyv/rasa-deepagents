"""Live command-line runner for the Always-On AI Coworker.

Watch the conversation unfold in real time:

    user audio --> [Speechmatics ASR] --> text
              --> [Rasa CALM + Nebius] --> reply
              --> [Rime TTS]           --> spoken reply

Rasa is the brain; the client just calls its REST API. Spinners show each stage
(listening / transcribing / thinking / speaking) and colored panels show the
transcript as it streams.

Usage:
    python -m voice.demo                    # full voice loop (run `make generate-audio` first)
    python -m voice.demo --tts speechmatics # use a Speechmatics voice for the agent reply
    python -m voice.demo --text             # no audio: type to the coworker live
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from voice.audio_io import play_wav_bytes
from voice.script import USER_TURNS
from voice.speechmatics_service import SpeechmaticsService

load_dotenv()

RASA_URL = "http://localhost:5005/webhooks/rest/webhook"
AUDIO_DIR = Path("voice/audio")
console = Console()


def banner() -> None:
    console.print(
        Panel(
            Text("Always-On AI Coworker  —  live demo\n", style="bold white", justify="center")
            + Text("Speechmatics (ears)  ·  Rasa CALM + Nebius (brain)  ·  Rime (voice)",
                   style="dim", justify="center"),
            border_style="magenta", box=box.DOUBLE, padding=(0, 2),
        )
    )


def bubble(speaker: str, text: str, *, who: str) -> None:
    style = {"user": "cyan", "coworker": "green", "system": "yellow"}[who]
    title = {"user": "\U0001F464  You", "coworker": "\U0001F916  Coworker",
             "system": "\u2139  System"}[who]
    console.print(
        Panel(Text(text or "(silence)", style="white"),
              title=f"[bold]{title}[/bold]", border_style=style,
              box=box.ROUNDED, padding=(0, 2)),
        justify="left" if who == "user" else "right",
    )


async def send_to_rasa(session: aiohttp.ClientSession, sender: str, text: str) -> str:
    async with session.post(
        RASA_URL, json={"sender": sender, "message": text},
        timeout=aiohttp.ClientTimeout(total=60),
    ) as resp:
        resp.raise_for_status()
        msgs = await resp.json()
    return "  ".join(m["text"] for m in msgs if m.get("text"))


async def run_text() -> None:
    banner()
    console.print("[dim]Text mode. Type a message (or 'quit'). "
                  'Try: "I need to open a support ticket."[/dim]\n')
    sender = "demo-user"
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                text = console.input("[bold cyan]you ›[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"quit", "exit"}:
                break
            if not text:
                continue
            with console.status("[green]Thinking (Rasa + Nebius)…", spinner="dots"):
                reply = await send_to_rasa(session, sender, text)
            bubble("Coworker", reply, who="coworker")
    console.print("\n[dim]Bye. Tickets persisted to .data/tickets.json.[/dim]")


async def run_voice(agent_tts: str) -> None:
    banner()
    sender = "demo-user"
    asr = SpeechmaticsService()

    if agent_tts == "rime":
        from voice.rime_service import RimeTTS
        rime = RimeTTS()
        speak = rime.synthesize
        voice_label = "Rime"
    else:
        async def speak(text: str) -> bytes:  # type: ignore[misc]
            return await asr.synthesize(text, role="agent")
        voice_label = "Speechmatics"

    clips = [AUDIO_DIR / f"user_{i}.wav" for i in range(1, len(USER_TURNS) + 1)]
    missing = [c.name for c in clips if not c.exists()]
    if missing:
        console.print(f"[red]Missing audio: {', '.join(missing)}. "
                      f"Run: make generate-audio[/red]")
        raise SystemExit(1)

    async with aiohttp.ClientSession() as session:
        for clip in clips:
            audio = clip.read_bytes()
            with console.status(f"[cyan]Listening… ({clip.name})", spinner="dots"):
                play_wav_bytes(audio)
            with console.status("[cyan]Transcribing (Speechmatics)…", spinner="earth"):
                transcript = await asr.transcribe(audio) or ""
            bubble("You", transcript, who="user")

            with console.status("[green]Thinking (Rasa + Nebius)…", spinner="dots"):
                reply = await send_to_rasa(session, sender, transcript)
            bubble("Coworker", reply, who="coworker")

            if reply:
                with console.status(f"[green]Speaking ({voice_label})…", spinner="dots"):
                    spoken = await speak(reply)
                play_wav_bytes(spoken)

    console.print(
        Panel(
            Text("Demo complete. Tickets were saved to .data/tickets.json — restart and ask "
                 "for the ticket status to watch the coworker remember across sessions.",
                 style="white"),
            border_style="green", box=box.ROUNDED,
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Live runner for the Rasa AI coworker.")
    ap.add_argument("--text", action="store_true", help="No audio; type messages live.")
    ap.add_argument("--tts", choices=["rime", "speechmatics"], default="rime",
                    help="Engine for the agent's voice (default: rime).")
    args = ap.parse_args()
    try:
        asyncio.run(run_text() if args.text else run_voice(args.tts))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
