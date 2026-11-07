#!/usr/bin/env bash
# AV3: seis medições C1/C2 alternadas; piloto opcional.
# Executar da raiz ATV_3: bash scripts/run_experimentos.sh
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGEM_LAB="${IMAGEM_LAB:-python@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54}"
ITERACOES="${ITERACOES:-20000000}"
MODO="${MODO:-oficial}"  # piloto / oficial
[[ "$MODO" == "piloto" || "$MODO" == "oficial" ]] || { echo 'MODO deve ser piloto ou oficial'; exit 2; }
[[ "$ITERACOES" =~ ^[0-9]+$ ]] || { echo 'ITERACOES deve ser inteiro positivo'; exit 2; }
command -v timeout >/dev/null || { echo 'GNU timeout não encontrado'; exit 2; }
command -v sudo >/dev/null || { echo 'sudo não encontrado'; exit 2; }
sudo docker image inspect "$IMAGEM_LAB" >/dev/null || { echo 'Imagem por digest indisponível'; exit 2; }

RUNID="$(date -u +%Y%m%dT%H%M%SZ)_$$"
DESTINO="$RAIZ/resultados/parte_c/${MODO}_${RUNID}"
mkdir -p "$DESTINO"
printf '%s\n' "Imagem: $IMAGEM_LAB" "Iterações: $ITERACOES" "Modo: $MODO" "Início UTC: $(date -u -Is)" \
  "SHA256 carga_cpu.py: $(sha256sum "$RAIZ/scripts/carga_cpu.py" | awk '{print $1}')" > "$DESTINO/manifesto.txt"
(git -C "$RAIZ" rev-parse HEAD 2>/dev/null || true) >> "$DESTINO/manifesto.txt"

executar() {
  local cond="$1" rep="$2" cpus="1.0"
  [[ "$cond" == 'C1' ]] && cpus="0.5"
  local pasta="$DESTINO/${cond}_rep_${rep}"
  mkdir -p "$pasta"
  local nome="av3-c-${cond,,}-${rep}-$$"
  printf '>>> %s repetição %s: quota=%s CPU, iterações=%s\n' "$cond" "$rep" "$cpus" "$ITERACOES"
  local saida=0
  timeout --signal=TERM --kill-after=5s 90s \
    sudo docker run --rm --name "$nome" \
       --network none --cpus "$cpus" \
       --memory 256m --memory-swap 256m --pids-limit 64 \
       --read-only --cap-drop ALL --security-opt no-new-privileges \
       --user 65534:65534 -e PYTHONDONTWRITEBYTECODE=1 \
       --mount "type=bind,src=$RAIZ/scripts,dst=/lab/scripts,readonly" \
       "$IMAGEM_LAB" python /lab/scripts/carga_cpu.py \
       --iteracoes "$ITERACOES" --condicao "$cond" --repeticao "$rep" \
       > "$pasta/stdout.txt" 2> "$pasta/stderr.txt" || saida=$?
  printf '%s\n' "$saida" > "$pasta/exit_code.txt"
  # Se timeout interromper o cliente, encerrar APENAS o contêiner criado por este script.
  sudo docker rm -f "$nome" >/dev/null 2>&1 || true
  python3 - "$pasta" "$cond" "$rep" "$saida" <<'PY'
import json, pathlib, sys
p,cond,rep,exitcode = pathlib.Path(sys.argv[1]),sys.argv[2],int(sys.argv[3]),int(sys.argv[4])
obj = {'condicao':cond,'repeticao':rep,'docker_exit_code':exitcode,'status':'erro_execucao'}
try:
    texto = (p/'stdout.txt').read_text(encoding='utf-8')
    registro = [s[len('AV3_RESULTADO_JSON='):] for s in texto.splitlines() if s.startswith('AV3_RESULTADO_JSON=')]
    if registro:
        obj.update(json.loads(registro[-1]))
        if exitcode != 0:
            obj['status'] = 'erro_execucao' if obj.get('status') == 'ok' else obj.get('status')
    else:
        obj['erro'] = 'não foi emitido registro JSON; consulte stdout/stderr'
except Exception as exc:
    obj['erro'] = str(exc)
(p/'registro.json').write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print('   status=',obj['status'],'tempo_total_s=',obj.get('tempo_total_s'),'checksum=',obj.get('checksum_sha256'))
PY
}

if [[ "$MODO" == "piloto" ]]; then
  executar C1 1
  echo "Piloto finalizado: $DESTINO"
else
  for rep in 1 2 3; do
    executar C1 "$rep"
    sleep 1
    executar C2 "$rep"
    sleep 1
  done
  echo '=== RESUMO ==='
  resumo_status=0
  python3 "$RAIZ/scripts/resumo.py" "$DESTINO" || resumo_status=$?
  echo "Resultados brutos preservados em: $DESTINO"
  if [[ "$resumo_status" -ne 0 ]]; then
    echo "ATENÇÃO: resumo não validou seis execuções oficiais. Consulte os logs."
    exit "$resumo_status"
  fi
fi
