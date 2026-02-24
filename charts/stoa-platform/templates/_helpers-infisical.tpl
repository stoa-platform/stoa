{{/*
Infisical init container — fetches secrets from Infisical and writes them
to a shared emptyDir volume at /secrets as individual files.

Usage in a Deployment template:
  initContainers:
    {{- include "stoa-platform.infisicalInitContainer" . | nindent 8 }}
  volumes:
    {{- include "stoa-platform.infisicalVolume" . | nindent 8 }}

The main container can then mount the volume:
  volumeMounts:
    - name: infisical-secrets
      mountPath: /secrets
      readOnly: true

Or source all exported env vars via envFrom on a generated .env file.
*/}}

{{/*
Reusable init container that fetches secrets from Infisical.
Secrets are written as individual files under /secrets/<KEY>=<VALUE> format
and also as a combined /secrets/.env file for envFrom consumption.
*/}}
{{- define "stoa-platform.infisicalInitContainer" -}}
{{- if .Values.infisical.enabled }}
- name: infisical-secrets-init
  image: {{ .Values.infisical.image | default "infisical/cli:latest" }}
  command:
    - /bin/sh
    - -c
    - |
      set -e
      echo "Fetching secrets from Infisical..."
      echo "  Address: ${INFISICAL_API_URL}"
      echo "  Project: ${INFISICAL_PROJECT_ID}"
      echo "  Env:     ${INFISICAL_ENVIRONMENT}"
      echo "  Path:    ${INFISICAL_SECRET_PATH}"

      # Authenticate with Universal Auth (Machine Identity)
      export INFISICAL_TOKEN=$(infisical login \
        --method=universal-auth \
        --client-id="${INFISICAL_CLIENT_ID}" \
        --client-secret="${INFISICAL_CLIENT_SECRET}" \
        --domain="${INFISICAL_API_URL}" \
        --silent 2>/dev/null || echo "")

      if [ -z "${INFISICAL_TOKEN}" ]; then
        echo "ERROR: Failed to authenticate with Infisical"
        {{- if .Values.infisical.required }}
        exit 1
        {{- else }}
        echo "WARN: infisical.required=false — continuing without secrets"
        touch /secrets/.env
        exit 0
        {{- end }}
      fi

      # Export secrets as individual files + combined .env
      infisical export \
        --domain="${INFISICAL_API_URL}" \
        --projectId="${INFISICAL_PROJECT_ID}" \
        --env="${INFISICAL_ENVIRONMENT}" \
        --path="${INFISICAL_SECRET_PATH}" \
        --format=dotenv \
        --token="${INFISICAL_TOKEN}" \
        > /secrets/.env

      # Also write each secret as an individual file for flexible consumption
      while IFS='=' read -r key value; do
        # Skip empty lines and comments
        [ -z "$key" ] && continue
        case "$key" in \#*) continue ;; esac
        printf '%s' "$value" > "/secrets/${key}"
      done < /secrets/.env

      echo "Secrets synced successfully ($(wc -l < /secrets/.env) entries)"
  env:
    - name: INFISICAL_API_URL
      value: {{ .Values.infisical.address | quote }}
    - name: INFISICAL_PROJECT_ID
      value: {{ .Values.infisical.projectId | quote }}
    - name: INFISICAL_ENVIRONMENT
      value: {{ .Values.infisical.environment | quote }}
    - name: INFISICAL_SECRET_PATH
      value: {{ .Values.infisical.secretPath | default "/" | quote }}
    - name: INFISICAL_CLIENT_ID
      valueFrom:
        secretKeyRef:
          name: {{ .Values.infisical.clientSecretRef.name | quote }}
          key: {{ .Values.infisical.clientSecretRef.clientIdKey | default "client-id" | quote }}
    - name: INFISICAL_CLIENT_SECRET
      valueFrom:
        secretKeyRef:
          name: {{ .Values.infisical.clientSecretRef.name | quote }}
          key: {{ .Values.infisical.clientSecretRef.clientSecretKey | default "client-secret" | quote }}
  volumeMounts:
    - name: infisical-secrets
      mountPath: /secrets
  securityContext:
    privileged: false
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: false
    capabilities:
      drop:
        - ALL
    seccompProfile:
      type: RuntimeDefault
  resources:
    requests:
      cpu: 50m
      memory: 32Mi
    limits:
      cpu: 100m
      memory: 64Mi
{{- end }}
{{- end }}

{{/*
Shared volume for Infisical secrets — emptyDir that init container writes to
and main container reads from.
*/}}
{{- define "stoa-platform.infisicalVolume" -}}
{{- if .Values.infisical.enabled }}
- name: infisical-secrets
  emptyDir:
    medium: Memory
    sizeLimit: 10Mi
{{- end }}
{{- end }}

{{/*
Volume mount for main container to read Infisical secrets.
*/}}
{{- define "stoa-platform.infisicalVolumeMount" -}}
{{- if .Values.infisical.enabled }}
- name: infisical-secrets
  mountPath: /secrets
  readOnly: true
{{- end }}
{{- end }}
