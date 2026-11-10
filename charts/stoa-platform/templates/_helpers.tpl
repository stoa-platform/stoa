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

CAB-2563 (#3130) and CAB-2566 (#3131) both define stoa-platform.environment.
Standalone installs keep the CAB-2563 rule: a non-empty component value wins,
otherwise global.environment, otherwise "dev". The stoa-stack umbrella always
sets global.observability; when that key is present the CAB-2566 rule applies
and global.environment is the single source shared with sibling charts, so it
wins over the component value.

clusterName follows CAB-2566 in every install: global.clusterName, then the
component value, then "default". CAB-2563 does not redefine it.

Call environment, clusterName and otelEndpoint with
(dict "root" $ "value" <component override>).
*/}}
{{- define "stoa-platform.environment" -}}
{{- $global := .root.Values.global | default dict -}}
{{- $observability := $global.observability | default dict -}}
{{- if hasKey $observability "enabled" -}}
{{- $global.environment | default .value | default "dev" -}}
{{- else -}}
{{- .value | default $global.environment | default "dev" -}}
{{- end -}}
{{- end -}}

{{- define "stoa-platform.clusterName" -}}
{{- $global := .root.Values.global | default dict -}}
{{- $global.clusterName | default .value | default "default" -}}
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
