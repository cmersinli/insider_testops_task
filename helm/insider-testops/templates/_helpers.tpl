{{/*
Expand the name of the chart.
*/}}
{{- define "insider-testops.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "insider-testops.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "insider-testops.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "insider-testops.labels" -}}
helm.sh/chart: {{ include "insider-testops.chart" . }}
{{ include "insider-testops.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: selenium-test-suite
{{- end }}

{{/*
Selector labels
*/}}
{{- define "insider-testops.selectorLabels" -}}
app.kubernetes.io/name: {{ include "insider-testops.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Test Controller labels
*/}}
{{- define "insider-testops.controllerLabels" -}}
{{ include "insider-testops.labels" . }}
app.kubernetes.io/component: test-case-controller
{{- end }}

{{/*
Test Controller selector labels
*/}}
{{- define "insider-testops.controllerSelectorLabels" -}}
{{ include "insider-testops.selectorLabels" . }}
app: test-case-controller
app.kubernetes.io/component: test-case-controller
{{- end }}

{{/*
Chrome Node labels
*/}}
{{- define "insider-testops.chromeNodeLabels" -}}
{{ include "insider-testops.labels" . }}
app.kubernetes.io/component: chrome-node
{{- end }}

{{/*
Chrome Node selector labels
*/}}
{{- define "insider-testops.chromeNodeSelectorLabels" -}}
{{ include "insider-testops.selectorLabels" . }}
app: chrome-node
app.kubernetes.io/component: chrome-node
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "insider-testops.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "insider-testops.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Generate ECR image URL for test controller
*/}}
{{- define "insider-testops.controllerImage" -}}
{{- if .Values.testController.image.repository }}
{{- printf "%s:%s" .Values.testController.image.repository .Values.testController.image.tag }}
{{- else if .Values.awsAccountId }}
{{- printf "%v.dkr.ecr.%s.amazonaws.com/%s:%s" .Values.awsAccountId .Values.awsRegion .Values.ecrRepository .Values.testController.image.tag }}
{{- else }}
{{- printf "python:3.12-slim" }}
{{- end }}
{{- end }}

{{/*
Generate ECR image URL for chrome node
*/}}
{{- define "insider-testops.chromeNodeImage" -}}
{{- if .Values.chromeNode.image.repository }}
{{- printf "%s:%s" .Values.chromeNode.image.repository .Values.chromeNode.image.tag }}
{{- else if .Values.awsAccountId }}
{{- printf "%v.dkr.ecr.%s.amazonaws.com/%s:%s" .Values.awsAccountId .Values.awsRegion .Values.ecrRepository .Values.chromeNode.image.tag }}
{{- else }}
{{- fail "awsAccountId or chromeNode.image.repository must be set" }}
{{- end }}
{{- end }}

{{/*
Namespace name
*/}}
{{- define "insider-testops.namespace" -}}
{{- default .Values.namespace .Release.Namespace }}
{{- end }}
