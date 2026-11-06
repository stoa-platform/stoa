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
Shared parameters.
When this chart is installed through the stoa-stack umbrella chart, `global`
is the single source for values shared with sibling charts and takes
precedence over component-local values. Standalone installs keep using the
component-local values, which remain the fallback.
Usage: include "stoa-platform.environment" (dict "root" $ "value" .Values.x.environment)
*/}}
{{- define "stoa-platform.environment" -}}
{{- $global := .root.Values.global | default dict -}}
{{- $global.environment | default .value | default "dev" -}}
{{- end -}}

{{- define "stoa-platform.clusterName" -}}
{{- $global := .root.Values.global | default dict -}}
{{- $global.clusterName | default .value | default "default" -}}
{{- end -}}

{{/*
Namespace that hosts the OTLP collector. With `global.observability` set, an
empty namespace means the collector is co-installed in the release namespace.
*/}}
{{- define "stoa-platform.observabilityNamespace" -}}
{{- $global := .Values.global | default dict -}}
{{- $observability := $global.observability | default dict -}}
{{- if hasKey $observability "enabled" -}}
{{- $observability.namespace | default .Release.Namespace -}}
{{- else -}}
{{- .Values.networkPolicy.monitoringNamespace -}}
{{- end -}}
{{- end -}}

{{/*
OTLP gRPC endpoint for a component; an empty result disables trace export.
With `global.observability` set, the endpoint targets the stoa-alloy-otlp
Service rendered by the stoa-observability chart, and is empty when
observability is disabled. Otherwise the component-local value is used.
Usage: include "stoa-platform.otelEndpoint" (dict "root" $ "value" .Values.x.otelEndpoint)
*/}}
{{- define "stoa-platform.otelEndpoint" -}}
{{- $global := .root.Values.global | default dict -}}
{{- $observability := $global.observability | default dict -}}
{{- if hasKey $observability "enabled" -}}
{{- if $observability.enabled -}}
{{- printf "http://stoa-alloy-otlp.%s:4317" (include "stoa-platform.observabilityNamespace" .root) -}}
{{- end -}}
{{- else -}}
{{- .value | default "" -}}
{{- end -}}
{{- end -}}
