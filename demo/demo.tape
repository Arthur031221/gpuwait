# demo/demo.tape
# Rendered with: vhs demo/demo.tape
# Requires: gpuwait installed in the current environment (uv sync), and a
# local server answering at http://localhost:11434 for the live section.
# The recording itself was made against a real Ollama serving qwen3:4b.

Output demo/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1200
Set Height 650
Set Padding 20
Set Theme "Dracula"

Type "uv run gpuwait --help"
Enter
Sleep 3s

Type "clear"
Enter
Sleep 500ms

Type "uv run gpuwait http://localhost:11434 --model qwen3:4b --concurrency 1 --duration-s 8 --think-time 2 --no-html"
Enter
Sleep 14s
Sleep 2s
