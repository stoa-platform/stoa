{{/*
Infisical init container for secret sync (CAB-1342)
Fetches secrets from Infisical API at pod startup and writes them
as individual files to a shared emptyDir volume.
Main container reads secrets via volumeMount.

Usage in a deployment:
  spec:
    initContainers:
      {{- include "stoa-platform.infisical-init-container" (dict "Values" .Values "secretPath" "/database") | nindent 6 }}
    volumes:
      {{- include "stoa-platform.infisical-volumes" . | nindent 6 }}
*/}}

{{- define "stoa-platform.infisical-init-container" -}}
- name: infisical-secret-sync
  image: "{{ .Values.infisical.image.repository }}:{{ .Values.infisical.image.tag }}"
  imagePullPolicy: IfNotPresent
  command: ["sh", "-c"]
  args:
    - |
      set -e
      TOKEN=$(cat /var/run/secrets/infisical/token)
      RESPONSE=$(curl -sf \
        "${INFISICAL_URL}/api/v3/secrets/raw?workspaceId=${INFISICAL_PROJECT_ID}&environment=${INFISICAL_ENV}&secretPath=${SECRET_PATH}" \
        -H "Authorization: Bearer ${TOKEN}")
      echo "${RESPONSE}" | python3 -c "
      import json, sys, os
      data = json.load(sys.stdin)
      secrets = data.get('secrets', [])
      for s in secrets:
          path = os.path.join('/secrets', s['secretKey'])
          with open(path, 'w') as f:
              f.write(s['secretValue'])
      print(f'Synced {len(secrets)} secrets from Infisical')
      "
  env:
    - name: INFISICAL_URL
      value: {{ .Values.infisical.url | quote }}
    - name: INFISICAL_PROJECT_ID
      value: {{ .Values.infisical.projectId | quote }}
    - name: INFISICAL_ENV
      value: {{ .Values.infisical.environment | quote }}
    - name: SECRET_PATH
      value: {{ .secretPath | default "/" | quote }}
  volumeMounts:
    - name: infisical-secrets
      mountPath: /secrets
    - name: infisical-token
      mountPath: /var/run/secrets/infisical
      readOnly: true
  securityContext:
    privileged: false
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    readOnlyRootFilesystem: false
    allowPrivilegeEscalation: false
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
{{- end -}}

{{/*
Volumes required by the Infisical init container.
Includes: shared emptyDir for secrets + projected token secret.

Usage:
  volumes:
    {{- include "stoa-platform.infisical-volumes" . | nindent 6 }}
*/}}
{{- define "stoa-platform.infisical-volumes" -}}
- name: infisical-secrets
  emptyDir:
    medium: Memory
    sizeLimit: 1Mi
- name: infisical-token
  secret:
    secretName: {{ .Values.infisical.tokenSecretName | default "infisical-machine-identity-token" }}
    optional: false
{{- end -}}
