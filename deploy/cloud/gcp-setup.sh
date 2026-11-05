#!/usr/bin/env bash
# Cria a service account do BackupHub em um projeto GCP e concede as permissões mínimas.
# Uso: ./gcp-setup.sh <PROJECT_ID> <BUCKET>
set -euo pipefail
PROJECT="${1:?informe o PROJECT_ID}"
BUCKET="${2:?informe o nome do bucket}"
SA="backuphub@${PROJECT}.iam.gserviceaccount.com"

gcloud iam service-accounts create backuphub --project "$PROJECT" --display-name "BackupHub" || true
for role in roles/compute.viewer roles/compute.storageAdmin; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${SA}" --role "$role" --condition=None >/dev/null
done
gcloud storage buckets create "gs://${BUCKET}" --project "$PROJECT" --uniform-bucket-level-access 2>/dev/null || true
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member "serviceAccount:${SA}" --role roles/storage.objectAdmin >/dev/null
gcloud iam service-accounts keys create backuphub-sa.json --iam-account "$SA"
echo "Pronto. Cadastre o conteúdo de backuphub-sa.json em Credenciais > Google Cloud."
