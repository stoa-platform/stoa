{{/*
Expand the name of the chart.
*/}}
{{- define "stoa-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "stoa-platform.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "stoa-platform.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: stoa-platform
{{- end }}

{{/* Render an immutable image reference; reject missing or malformed pins. */}}
{{- define "stoa-platform.pinnedImage" -}}
{{- $repository := required "image repository is required" .repository -}}
{{- $digest := required "image digest is required" .digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail "image digest must be sha256 followed by 64 lowercase hexadecimal characters" -}}
{{- end -}}
{{- printf "image: %s" (printf "%s@%s" $repository $digest | quote) -}}
{{- end -}}

{{/* Validate complete image references while preserving scalar values overrides. */}}
{{- define "stoa-platform.pinnedImageReference" -}}
{{- $image := required "image reference is required" . -}}
{{- if not (regexMatch "^[^@[:space:]]+@sha256:[0-9a-f]{64}$" $image) -}}
{{- fail "image reference must include @sha256: followed by 64 lowercase hexadecimal characters" -}}
{{- end -}}
{{- printf "image: %s" ($image | quote) -}}
{{- end -}}

{{/*
Effective environment label: a non-empty component override wins, otherwise
global.environment, otherwise "dev". Call with (dict "root" $ "value" <override>).
*/}}
{{- define "stoa-platform.environment" -}}
{{- $global := .root.Values.global | default dict -}}
{{- .value | default $global.environment | default "dev" -}}
{{- end -}}

{{/* Shared identity realm used by bootstrap jobs and as the workload default. */}}
{{- define "stoa-platform.keycloakRealm" -}}
{{- .Values.keycloak.realm | default "stoa" -}}
{{- end -}}

{{/* In-cluster identity admin endpoint used by the bootstrap jobs. */}}
{{- define "stoa-platform.keycloakInternalUrl" -}}
{{- .Values.keycloak.internalUrl | default (printf "http://keycloak-http.%s.svc.cluster.local:80" .Release.Namespace) -}}
{{- end -}}

{{/* Realm bootstrap runs unless the identity operator owns the realm. */}}
{{- define "stoa-platform.realmBootstrapEnabled" -}}
{{- if and .Values.stoa.bootstrap.enabled (not .Values.keycloak.operator.enabled) -}}true{{- end -}}
{{- end -}}
