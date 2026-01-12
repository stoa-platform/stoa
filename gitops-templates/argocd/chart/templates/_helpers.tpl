{{/*
Common labels
*/}}
{{- define "argocd-appsets.labels" -}}
app.kubernetes.io/part-of: {{ .Values.labels | default dict | dig "app.kubernetes.io/part-of" "stoa-platform" }}
app.kubernetes.io/managed-by: {{ .Values.labels | default dict | dig "app.kubernetes.io/managed-by" "argocd" }}
{{- end }}

{{/*
GitLab Repo URL
*/}}
{{- define "argocd-appsets.gitlabRepoUrl" -}}
{{ .Values.gitlab.repoUrl | default (printf "%s/%s.git" .Values.gitlab.url .Values.gitlab.projectPath) }}
{{- end }}

{{/*
Namespace with prefix
*/}}
{{- define "argocd-appsets.namespace" -}}
{{ .Values.kubernetes.namespacePrefix | default "stoa" }}
{{- end }}
