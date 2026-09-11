#!/bin/sh
# Put Marvin to sleep / wake it up on the cluster. Volumes persist; if your cluster autoscaler reclaims idle GPU
# nodes, the STT node goes away a minute or so after its pod. (If a GitOps tool manages this app, make it ignore
# replica counts, or it will undo the scaling.)
set -eu
NS="${MARVIN_NS:-marvin}"
URL="${MARVIN_URL:-https://marvin.example.com}"
case "${1:-}" in
  on|up|wake)
    kubectl -n "$NS" scale statefulset/marvin --replicas=1
    kubectl -n "$NS" scale deployment/marvin-stt --replicas=1
    echo "Marvin waking: room in ~1 min, GPU transcription in ~3-5 min (Whisper covers meanwhile)."
    echo "$URL" ;;
  off|down|sleep)
    kubectl -n "$NS" scale statefulset/marvin --replicas=0
    kubectl -n "$NS" scale deployment/marvin-stt --replicas=0
    echo "Marvin asleep. Data persists on the PVCs; the GPU node is reclaimed once the autoscaler notices." ;;
  status)
    kubectl -n "$NS" get statefulset,deployment,pods ;;
  *) echo "usage: $0 {on|off|status}   (namespace via MARVIN_NS, default 'marvin'; URL via MARVIN_URL)"; exit 1 ;;
esac
