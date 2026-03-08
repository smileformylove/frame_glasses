PYTHON ?= python3
VENV_PYTHON := .venv/bin/python
FRAME_LAB := $(VENV_PYTHON) frame_lab.py

.PHONY: help bootstrap bootstrap-min doctor probe visual-probe live-check scan pair-test say meeting-demo vision-demo tap-vision-demo memory-demo tap-memory-demo voice-demo voice-codex-demo frame-mic-test frame-audio-probe frame-mic-live-demo frame-mic-codex-demo agent-hud-serve agent-hud-demo

help:
	@echo "Available targets:"
	@echo "  bootstrap           Full macOS setup"
	@echo "  bootstrap-min       Minimal setup"
	@echo "  doctor              Check local environment"
	@echo "  probe               Run the step-by-step Frame connectivity probe"
	@echo "  visual-probe        Run a persistent on-device visual probe"
	@echo "  live-check          Run probe + send text + Frame mic test"
	@echo "  scan                Scan nearby Frame devices"
	@echo "  pair-test           Find nearest Frame and send a test line"
	@echo "  say                 Dry-run send text demo"
	@echo "  meeting-demo        Meeting HUD dry-run demo"
	@echo "  vision-demo         Vision HUD dry-run demo"
	@echo "  tap-vision-demo     Tap Vision dry-run demo"
	@echo "  memory-demo         Memory HUD dry-run flow"
	@echo "  tap-memory-demo     Tap Memory HUD dry-run flow"
	@echo "  voice-demo          Voice Command HUD dry-run flow"
	@echo "  voice-codex-demo    Voice Codex Bridge dry-run flow"
	@echo "  frame-mic-codex-demo Frame Mic Codex Bridge dry-run flow"
	@echo "  frame-mic-test      Dry-run Frame microphone test"
	@echo "  frame-audio-probe   Probe Frame microphone RMS/transcript"
	@echo "  frame-mic-live-demo Frame microphone live transcript dry-run demo"
	@echo "  agent-hud-serve     Start Agent HUD in dry-run mode"
	@echo "  agent-hud-demo      Send sample notifications to a running Agent HUD"

bootstrap:
	./scripts/bootstrap_mac.sh --full

bootstrap-min:
	./scripts/bootstrap_mac.sh --minimal

doctor:
	$(FRAME_LAB) doctor

probe:
	./scripts/run_frame_lab.sh probe -- --name "Frame EF" --send-text "probe"

visual-probe:
	./scripts/run_frame_lab.sh visual-probe -- --name "Frame EF" --duration 15 --verbose

live-check:
	./scripts/live_connectivity_check.sh --name "Frame EF" --text "probe" --mic-duration 3

scan:
	$(FRAME_LAB) scan

pair-test:
	$(FRAME_LAB) pair-test -- --text "Hello from Mac mini"

say:
	$(FRAME_LAB) say -- --text "Hello from Makefile" --dry-run

meeting-demo:
	$(FRAME_LAB) meeting -- --demo --dry-run --render-mode unicode

vision-demo:
	$(FRAME_LAB) vision -- --source demo --analyzer mock --mock-result "Vision demo OK" --dry-run

tap-vision-demo:
	$(FRAME_LAB) tap-vision -- --demo --analyzer mock --mock-result "Tap Vision demo OK"

memory-demo:
	$(FRAME_LAB) memory -- remember --source demo --analyzer mock --mock-result "Desk prototype" --note "This is the Frame demo desk"


tap-memory-demo:
	$(FRAME_LAB) tap-memory -- --demo --analyzer mock --mock-result "Desk prototype"

voice-demo:
	$(FRAME_LAB) voice -- --demo --dry-run --source demo --demo-commands "help|describe this|remember this as desk prototype|recall this|exit" --analyzer mock --mock-result "Detected a Frame prototype desk."

voice-codex-demo:
	$(FRAME_LAB) voice-codex -- --demo --dry-run --demo-commands "help|doctor|git status|ask codex summarize this repo|exit"

frame-mic-codex-demo:
	$(FRAME_LAB) frame-mic-codex -- --demo --dry-run

frame-mic-test:
	$(FRAME_LAB) frame-mic -- --duration 5 --dry-run

frame-audio-probe:
	$(FRAME_LAB) frame-audio-probe -- --name "Frame EF" --duration 4 --transcribe

frame-mic-live-demo:
	$(FRAME_LAB) frame-mic-live -- --demo --dry-run

agent-hud-serve:
	$(FRAME_LAB) agent-hud -- serve --dry-run

agent-hud-demo:
	$(FRAME_LAB) agent-hud -- demo
