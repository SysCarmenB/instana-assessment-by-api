# Manual de ejecución Assessment de Instana

Mide el nivel de madurez de observabilidad de un tenant de Instana. Consulta la
API REST (solo lectura, no modifica nada), puntúa cada aplicación en 8
dimensiones y genera un reporte **HTML** y un **CSV**.

Tiempo estimado: 15 minutos de preparación + ~1 minuto de ejecución cada ~80 apps.

---

## 1. Requisitos

- Python **3.9 o superior** (probado en 3.12)
- Acceso de red al tenant de Instana (SaaS o self-hosted)
- Un **API token de Instana de solo lectura** (ver paso 3)

## 2. Instalación

```bash
git clone <URL-DEL-REPOSITORIO> instana-assessment
cd instana-assessment
python -m venv .venv
```

Instala las dependencias **usando el Python del entorno virtual** (no hace falta activarlo):

| Sistema | Comando |
|---|---|
| Windows PowerShell | `.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| Linux / macOS | `.venv/bin/python -m pip install -r requirements.txt` |

Solo instala dos librerías: `requests` y `PyYAML`.

## 3. Crear el API token en Instana

En la interfaz de Instana: **Settings → API Tokens → Add API Token** (según la versión puede estar bajo *Team Settings*).

- El assessment nunca escribe ni configura nada.
- Para evaluar los **tests sintéticos**, en la lista de permisos del token activa
  **"Access to synthetic tests"** (categoría *Synthetic monitoring*).

> El token **nunca** se guarda en un archivo ni se sube al repositorio. Solo se
> exporta como variable de entorno en tu sesión (paso 5).

## 4. Configurar tu tenant

```bash
cp config/client.example.yaml config/client.yaml      # Windows: copy ...
```

Edita `config/client.yaml`. Lo mínimo:

```yaml
client_name: "Nombre de tu organización"

instana:
  base_url: "https://TU-TENANT.instana.io"   # self-hosted: https://host:puerto
  api_token_env: "INSTANA_API_TOKEN"         # nombre de la variable con el token
  verify_ssl: true                           # false solo si es self-hosted con certificado propio
```

### Alcance: qué aplicaciones se evalúan

Bloque `scope` (opcional) en el mismo archivo:

| Parámetro | Efecto |
|---|---|
| `require_traffic: true` | Solo apps con servicios/endpoints en las últimas `window_hours` (**por defecto**) |
| `require_traffic: false` | **Todo el catálogo**, incluidas perspectivas abandonadas |
| `window_hours: 24` | Ventana para medir el tráfico (24 horas por defecto; `168` = 7 días) |
| `top_n: 20` | Solo las 20 de mayor volumen (vacío = sin tope) |
| `name_filter: "PROD"` | Solo apps cuyo nombre contenga ese texto |

> **Por defecto solo se evalúan las aplicaciones con tráfico, y es lo recomendado.**

### Gobierno (opcional)

Owner, team, runbook e ITSM **no viven en Instana** (el propietario de los
dashboards sí se lee de la API, pero como ID sin nombre). Para completarlos:

```bash
cp config/governance.example.csv config/governance.csv
```

```csv
app_name,owner,team,runbook,itsm_integrated
Mi Aplicacion,Juan Perez,SRE,Si,Si
```

El `app_name` debe coincidir **exactamente** con el nombre de la aplicación en
Instana. Luego apunta `governance.csv_path` en tu `client.yaml` a ese archivo.
Si no lo completas, Gobierno puntúa solo con lo que sale de la API.

## 5. Exportar el token

**Windows PowerShell**
```powershell
$env:INSTANA_API_TOKEN = "tu-token-aqui"
```

**Linux / macOS**
```bash
export INSTANA_API_TOKEN="tu-token-aqui"
```

Dura solo mientras la terminal esté abierta.

## 6. Verificar conectividad (opcional)

**Windows PowerShell**
```powershell
.venv\Scripts\python.exe scripts\smoke_test.py --config config\client.yaml
```

**Linux / macOS**
```bash
.venv/bin/python scripts/smoke_test.py --config config/client.yaml
```

Debe mostrar `OK` en cada línea:

```
[applications] -> OK, 78 items
[websites] -> OK, 36 items
[slo_configs] -> OK, 16 items
...
```

| Salida | Significado |
|---|---|
| `OK, N items` | Funciona y trajo datos |
| `OK, 0 items` | Funciona, simplemente no hay datos de ese tipo |
| `SIN DATOS: no se pudo leer ...` | **No** es "sin datos": la llamada falló. Si va precedida de `[WARN] ... 403`, al token le falta un permiso de vista (el mensaje lo nombra). Si no hay `[WARN]` o es `404`, ese módulo no existe / no tiene licencia en tu tenant (típico: Mobile App Monitoring) |
| `InstanaAuthError ... 401` | Token inválido o expirado → revisa paso 5 |
| `Falta el API token...` | La variable de entorno no está definida en esta terminal |

## 7. Ejecutar el assessment

**Windows PowerShell**
```powershell
.venv\Scripts\python.exe -m instana_assessment.cli --config config\client.yaml --source live
```

**Linux / macOS**
```bash
.venv/bin/python -m instana_assessment.cli --config config/client.yaml --source live
```

> `--source live` es **obligatorio**. Sin él, el programa corre en modo demo con
> datos de ejemplo y no consulta tu tenant.

Salida esperada:

```
  [1/9] descubriendo topologia (apps, servicios, endpoints)...
        78 aplicaciones descubiertas -> 12 en alcance
  ...
Reporte HTML generado: ...\out\report_20260925_163455.html
Reporte CSV generado:  ...\out\report_20260925_163455.csv
Apps evaluadas: 12 | Score promedio: 41.3 | Nivel estimado: 3
```

(Los números son ilustrativos.) La línea **"descubiertas -> en alcance"** indica
cuántas aplicaciones se evaluaron realmente.

Los archivos quedan en `out/` con fecha y hora en el nombre: **cada corrida crea
archivos nuevos, no sobrescribe los anteriores**.

## 8. Leer el resultado

**HTML** (ábrelo en el navegador, no necesita internet): score por dimensión,
distribución por nivel, tabla por aplicación, recomendaciones y la sección
**"Alcance por dimensión"**, que explica qué cuenta como *Si / Parcial / No
evidenciado* en cada una. En la tabla por aplicación, **pasa el cursor sobre un
número subrayado** para ver el objeto concreto de Instana que lo sustenta.

**CSV** (ábrelo en Excel): una fila por aplicación. Las columnas
`Detalle: <dimensión>` al final nombran el objeto exacto validado (el SLO, la
alerta, el dashboard, el test sintético...) con su ID.

| Dimensión | Peso | Qué mide |
|---|---|---|
| APM | 20 | La app tiene servicios y endpoints descubiertos |
| RUM / Mobile / Synthetic | 15 | Tests sintéticos vinculados por ID (webapps y mobile solo por nombre) |
| SLO / Apdex | 15 | SLO apuntando a la app/servicio/endpoint |
| Smart Alerts | 15 | Alerta habilitada, con canal de aviso, sobre la app |
| Dashboard | 10 | Widget que filtra por la app |
| Infraestructura | 10 | Tecnología de ejecución identificada |
| Eventos | 10 | Incidencias (`issue`) enlazadas por ID en los últimos 7 días |
| Gobierno | 5 | Owner, team, runbook, ITSM, dueño de dashboard |

Regla general: **vínculo por ID = Si; vínculo solo por coincidencia de nombre =
máximo Parcial.** Niveles: 1 (0–19) · 2 (20–39) · 3 (40–59) · 4 (60–79) · 5 (80–100).

## 9. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `Activate.ps1 ... la ejecución de scripts está deshabilitada` | Política de PowerShell. No actives el entorno: usa `.venv\Scripts\python.exe` (paso 2). Alternativa solo para esa ventana: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (si tu organización lo bloquea por política de grupo, usa la primera opción) |
| `ModuleNotFoundError: No module named 'requests'` | Estás usando el Python del sistema en vez del del entorno: ejecuta con `.venv\Scripts\python.exe` (Windows) o `.venv/bin/python` (Linux / macOS) |
| Corre en modo demo (20 apps `App1…`) | Faltó `--source live` |
| `[WARN] ... HTTP 403` | Falta un permiso de vista en el token; el mensaje de Instana lo nombra |
| Una dimensión sale en 0 en todas las apps | Mira si hay un `[WARN]` en la salida: suele ser permiso o módulo ausente, no falta real de datos |
| `SSLError` | Self-hosted con certificado propio → `verify_ssl: false` |
| Tarda mucho | Son ~2 llamadas por aplicación; con cientos de apps usa `top_n` o `name_filter` |
| `[RATE] quedan N llamadas; esperando...` | Normal: el programa respeta el límite de la API y espera solo |
| Solo se evalúa 1 aplicación (o muy pocas) | Filtro de tráfico por defecto (bloque `scope`, paso 4) o token con acceso limitado por alcance |
| Score muy bajo con muchas apps | Perspectivas sin tráfico → deja `require_traffic: true` |

## 10. Limitaciones que debes conocer

- **No valida la conexión real webapp ↔ backend.** Eso requiere correlación de
  trazas de usuario real (RUM); el campo `appName` de un website no sirve de
  prueba (siempre es igual al nombre del propio website). Hoy RUM puntúa por tests
  sintéticos con `applicationId` y, el resto, por coincidencia de nombre.
- **Nombres distintos entre módulos dan falsos negativos.** Si el dashboard de una
  app se llama distinto que la app en Instana, no se enlaza. Normalizar el naming
  es, de hecho, la primera recomendación del assessment.
- **El dueño de un dashboard sale como ID** (`ownerId`), no como nombre: resolverlo
  exigiría un permiso de administración de usuarios que no se pide a propósito.
- Solo lectura: no crea ni modifica nada en el tenant.
