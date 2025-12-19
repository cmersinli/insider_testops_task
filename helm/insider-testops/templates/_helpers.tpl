{{- define "namespace" -}}
{{ .Values.namespace | default "insider-testops" }}
{{- end }}
