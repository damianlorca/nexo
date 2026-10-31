# Instancia de PRUEBA de Ollama en la iGPU (:11435). No toca la instancia normal (:11434).
$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:OLLAMA_IGPU_ENABLE = "1"
$env:OLLAMA_MODELS = "C:\Users\damia\Desktop\AI"
ollama serve *> "$PSScriptRoot\..\registros\ollama_igpu_serve.log"
