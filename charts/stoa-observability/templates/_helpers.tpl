{{/*
Common labels for stoa-observability resources.
*/}}
{{- define "stoa-observability.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: stoa-observability
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: stoa-platform
{{- end }}

{{/*
Selector labels
*/}}
{{- define "stoa-observability.selectorLabels" -}}
app.kubernetes.io/name: stoa-observability
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
