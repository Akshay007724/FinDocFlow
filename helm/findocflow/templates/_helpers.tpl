{{/*
Expand the name of the chart.
*/}}
{{- define "findocflow.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "findocflow.fullname" -}}
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
{{- define "findocflow.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource managed by this chart.
*/}}
{{- define "findocflow.labels" -}}
helm.sh/chart: {{ include "findocflow.chart" . }}
{{ include "findocflow.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: {{ include "findocflow.name" . }}
{{- end }}

{{/*
Selector labels — used in matchLabels and pod template labels.
A component name must be passed via the "component" key in the sub-context.
Usage:
  {{- include "findocflow.selectorLabels" (dict "Release" .Release "Chart" .Chart "Values" .Values "component" "ingestion") }}
When called without "component" (e.g. from findocflow.labels itself) the
component key is omitted so the macro remains safe in both contexts.
*/}}
{{- define "findocflow.selectorLabels" -}}
app.kubernetes.io/name: {{ include "findocflow.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .component }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
{{- end }}

{{/*
Return the image pull policy for a given service values dict.
*/}}
{{- define "findocflow.imagePullPolicy" -}}
{{- .pullPolicy | default "IfNotPresent" }}
{{- end }}
