# Ajusta ComfyUI a una revision compatible con el torch que exige torch-directml.
#
# Por que: la instalacion del 12/09 00:44 clono ComfyUI HEAD (2026-09-12), pero
# torch-directml obliga a torch 2.4.1+cpu (sept 2024). El ComfyUI de hoy importa
# comfy_kitchen, que usa torch.library.custom_op con anotaciones list[int] que
# ese torch viejo no sabe leer -> ValueError: infer_schema y no arranca.
# Solucion: llevar ComfyUI al tag v0.3.10 (dic 2024), de la misma epoca que torch 2.4.1.

$ErrorActionPreference = "Continue"
$raiz = "C:\Users\damia\Desktop\AI\ComfyUI"
$py = "$raiz\venv\Scripts\python.exe"
$log = "C:\Users\damia\Desktop\AI\agente\registros\ajustar_comfyui_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log"

function Nota($texto) {
    $linea = "[" + (Get-Date -Format "HH:mm:ss") + "] " + $texto
    Write-Output $linea
    Add-Content -Path $log -Value $linea
}

Nota "=== AJUSTE COMFYUI A v0.3.10: EMPIEZA ==="

Nota "Checkout del tag v0.3.10..."
git -C $raiz checkout -f v0.3.10 2>&1 | Add-Content -Path $log
Nota ("HEAD ahora: " + (git -C $raiz log -1 --date=short --format="%h %ad %s"))

Nota "Preparando requirements sin las lineas de torch (torch-directml manda)..."
$req = Get-Content "$raiz\requirements.txt" | Where-Object { $_ -notmatch "^\s*(torch|torchvision|torchaudio)\s*($|[=<>!])" }
$req | Set-Content "$raiz\requirements_sin_torch.txt"
Nota ("Lineas a instalar: " + $req.Count)

Nota "Instalando dependencias de v0.3.10..."
& $py -m pip install -r "$raiz\requirements_sin_torch.txt" 2>&1 | Select-Object -Last 15 | Add-Content -Path $log

Nota "Comprobando que torch sigue siendo el de DirectML..."
& $py -c "import torch, torch_directml; print('torch', torch.__version__, '| dispositivo', torch_directml.device())" 2>&1 | Add-Content -Path $log

Nota "Comprobando que ComfyUI ya importa sin explotar..."
& $py -c "import sys; sys.path.insert(0, r'$raiz'); import comfy.utils; print('comfy.utils OK')" 2>&1 | Select-Object -Last 8 | Add-Content -Path $log

Nota "=== AJUSTE COMFYUI: TERMINADO ==="
Nota "FIN_AJUSTE"
