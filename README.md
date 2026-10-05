# Instana Maturity Assessment

Automatiza el assessment de madurez en observabilidad Instana que hoy se hace a
mano (ver `Assessment Madurez Instana.xlsx`). Corre 100% local, sin infraestructura
adicional.

## Como corre

1. **Evidencia por aplicacion** en 8 dimensiones (APM, RUM/Mobile/Synthetic,
   SLO/Apdex, Smart Alerts, Dashboard, Infraestructura, Eventos, Gobierno) se
   clasifica como `Si` / `Parcial` / `No evidenciado`.
2. **Scoring**: cada dimension tiene un peso (ver `config/rubric.yaml`). El score de una app es la suma
   ponderada; el nivel de madurez (1-5) sale de bandas de 20 puntos.
3. **Recomendaciones**: reglas deterministas sobre los promedios por dimension
   y sobre las apps en nivel 1-2.
4. **Salidas**: un HTML autocontenido y un CSV con el detalle. Ambos archivos incluyen un
   timestamp en el nombre (`report_YYYYMMDD_HHMMSS.html / .csv`) de la fecha y hora de ejecución.

**Guia paso a paso para ejecutarlo en tu propio tenant: ver [MANUAL.md](MANUAL.md).**

Las 8 dimensiones se completan contra la API REST de Instana. **Gobierno** es
hibrido: parte sale de la API (propietario de dashboards, acciones de
automatizacion) y parte -owner/team/runbook/ITSM- no vive en Instana y se
completa en un CSV (`config/governance.example.csv`).

## Instalar

```bash
pip install -r requirements.txt
```

## Uso rapido (sin tocar Instana, con datos de ejemplo)

```bash
python -m instana_assessment.cli \
  --config config/client.yaml \
  --source csv \
  --input config/example_evidence.csv
```

Genera `out/report_YYYYMMDD_HHMMSS.html` y `out/report_YYYYMMDD_HHMMSS.csv`.

`config/example_evidence.csv` esta digitalizado a partir de un Excel manual
(Top 20 PROD) usando la evidencia cualitativa (Si/Parcial/No).

Este modo tambien sirve para digitalizar un assessment hecho a mano (capturas de
pantalla) sin necesidad de conectarse a la API.

## Uso contra un tenant real de Instana

### 1. Preparar el config del cliente

Copiar `config/client.example.yaml` a `config/client.yaml` y ajustar:

```yaml
client_name: "NOMBRE_CLIENTE"

instana:
  base_url: "https://<tenant>.instana.io"
  api_token_env: "INSTANA_API_TOKEN"
  verify_ssl: true
  timeout_seconds: 30

governance:
  csv_path: "config/governance.example.csv"

rubric_path: "config/rubric.yaml"

output:
  html_path: "out/report.html"   # base; el timestamp se añade automaticamente
```

### 2. Completar el CSV de gobierno

Editar `config/governance.example.csv` con owner/team/runbook/ITSM por aplicacion:

```
app_name,owner,team,runbook,itsm_integrated
MiApp,Juan Perez,SRE,https://wiki/runbook-miapp,Si
```

### 3. Exportar el API token

**Linux / macOS**
```bash
export INSTANA_API_TOKEN="tu-token-aqui"
```

**Windows PowerShell**
```powershell
$env:INSTANA_API_TOKEN = "tu-token-aqui"
```

### 4. Ejecutar

```bash
python -m instana_assessment.cli --config config/client.yaml --source live
```

### Argumentos disponibles

| Argumento | Descripcion | Default |
|---|---|---|
| `--config` | Path al YAML de config del cliente | `config/client.yaml` |
| `--source` | `csv` = evidencia manual \| `live` = API de Instana | `csv` |
| `--input` | Path al CSV de evidencia (requerido si `--source csv`) | — |
| `--out` | Path base del HTML de salida (se añade timestamp) | `out/report.html` |
| `--csv` | Path base del CSV de salida (se añade timestamp) | mismo nombre que `--out` con `.csv` |

### Archivos de salida

Cada ejecucion genera dos archivos en `out/` con timestamp para no sobreescribir:

```
out/report_20250601_143022.html   # reporte ejecutivo HTML
out/report_20250601_143022.csv    # scoring por app (= hoja "Scoring Top 20 PROD" del Excel)
```

## Ejecución en VM Linux remota (via SSH)

Esta sección documenta cómo correr el assessment desde una VM Linux remota
(ej: una VM de laboratorio) usando una llave SSH privada. Util cuando el entorno de
trabajo principal es Windows pero la ejecucion debe hacerse en Linux.

### Pre-requisitos

- Tener la llave SSH privada (archivo `.pem` o `.vm`) que da acceso a la VM.
- Conocer el usuario, host y puerto SSH de la VM.
- Tener el API Token de Instana disponible (se ingresara como variable de entorno,
  nunca en un archivo).
- Python 3.8+ en la VM (la mayoria de distribuciones modernas ya lo incluyen).

### Paso 1 — Ajustar config/client.yaml

En Windows, antes de transferir, editar `config/client.yaml`:

```yaml
client_name: "Nombre del Cliente"   # ajustar por cliente
instana:
  base_url: "https://<tenant>.instana.io"   # URL del tenant real
  api_token_env: "INSTANA_API_TOKEN"
```

### Paso 2 — Verificar permisos de la llave SSH (Windows)

OpenSSH en Windows rechaza llaves con permisos demasiado abiertos.
Ejecutar en PowerShell antes de conectarse:

```powershell
icacls "C:\ruta\a\vm_ssh_key.vm" /inheritance:r /grant:r "$env:USERNAME:(R)"
```

### Paso 3 — Conectar a la VM Linux

```powershell
ssh -i "C:\ruta\a\vm_ssh_key.vm" -p <puerto> <usuario>@<host>
```

### Paso 4 — Transferir el proyecto a la VM

Desde PowerShell en Windows (nueva ventana, NO dentro de la sesion SSH):

```powershell
scp -i "C:\ruta\a\vm_ssh_key.vm" -P <puerto> -r `
    "C:\ruta\a\instana-assessment" `
    <usuario>@<host>:~/instana-assessment
```

Verificar en la VM que la transferencia fue exitosa:

```bash
ls ~/instana-assessment/
# Debe mostrar: config/ instana_assessment/ scripts/ requirements.txt README.md
```

### Paso 5 — Instalar dependencias en la VM

```bash
cd ~/instana-assessment
pip3 install -r requirements.txt
# Verificar imports:
python3 -c "import requests, yaml; print('OK')"
```

Si `pip3` no esta disponible:
```bash
# Debian/Ubuntu:
sudo apt-get update && sudo apt-get install -y python3 python3-pip
# RHEL/CentOS:
sudo yum install -y python3 python3-pip
```

### Paso 6 — Exportar el API Token

El token **nunca** se graba en un archivo. Solo se exporta en la sesion activa:

```bash
export INSTANA_API_TOKEN="tu-token-aqui"
```

### Paso 7 — Smoke test (validar conectividad API)

Antes de correr el assessment completo, verificar que el token y la URL son correctos:

```bash
cd ~/instana-assessment
python3 scripts/smoke_test.py --config config/client.yaml
```

Interpretar la salida:
- `[OK]` — endpoint funcional con datos.
- `[WARN] 404` — modulo realmente ausente en este tenant (p.ej. Mobile App Monitoring sin licencia).
- `[WARN] 403` — al token le falta un permiso de solo lectura; el mensaje de Instana nombra cual (p.ej. `canViewSyntheticTests`).
- `[ERROR] 401` — token invalido; re-exportar con el valor correcto y reintentar.

### Paso 8 — Ejecutar el assessment

```bash
cd ~/instana-assessment
python3 -m instana_assessment.cli --config config/client.yaml --source live
```

Verificar los archivos generados:
```bash
ls -lh out/
# report_YYYYMMDD_HHMMSS.html
# report_YYYYMMDD_HHMMSS.csv
```

### Paso 9 — Recuperar los reportes a Windows

Desde PowerShell en Windows (nueva ventana, NO dentro de la sesion SSH):

```powershell
scp -i "C:\ruta\a\vm_ssh_key.vm" -P <puerto> `
    "<usuario>@<host>:~/instana-assessment/out/report_*" `
    "C:\ruta\destino\en\windows\"
```

Abrir el `.html` en el navegador — es autocontenido, no requiere conexion a internet.

### Notas sobre endpoints de la API

Los endpoints estan verificados contra un tenant SaaS de pruebas. En otros tenants
pueden variar — revisar el Swagger en `https://<tenant>/openapi/`. Un `[WARN]` no
detiene la ejecucion, pero esa dimension puede quedar en `0`: **un `[WARN]` en la
salida siempre merece revision**, porque suele indicar una URL mal escrita o un
permiso faltante del token, no ausencia real de datos.

## Estructura

```
config/
  rubric.yaml               # pesos, criterios de evidencia, niveles (= hoja Metodologia)
  client.example.yaml       # template de config por cliente
  client.yaml               # config activa (no versionar si contiene datos sensibles)
  governance.example.csv    # owner/team/runbook por app (completar a mano)
  example_evidence.csv      # evidencia mock digitalizada del Excel manual
instana_assessment/
  instana_client.py         # wrapper REST sobre la API de Instana
  collectors/               # un modulo por dimension -> evidencia full/partial/none
  scoring.py                # rubric + evidencia -> score/nivel por app y agregados
  recommendations.py        # reglas deterministas -> lista priorizada de recomendaciones
  report.py                 # genera el HTML final
  csv_export.py             # genera el CSV (formato hoja "Scoring Top 20 PROD")
  cli.py                    # entrypoint principal
out/
  report_YYYYMMDD_HHMMSS.html   # salida HTML (generada, no versionar)
  report_YYYYMMDD_HHMMSS.csv    # salida CSV  (generada, no versionar)
```
