# Desarrollo y verificación local

## Alcance actual

Backend local Windows con HTTPS, cuentas locales, permisos y auditoría PostgreSQL.
PostgreSQL y RabbitMQ están provisionados con TLS verificado. F004A añade un portal
React de cuentas/auditoría verificado en navegador. Su CA tiene confianza autorizada
en el almacén Windows de Usuario. No hay ingestión ni procesamiento de PDF. Docker y los workers Linux se difieren a
la feature final por indicación del responsable.

- [Portal React](react-portal.md): compilar, ejecutar por HTTPS y estado de confianza del navegador.
- [Usuarios, permisos y PostgreSQL local](identity-local.md): arranque, prueba de
  login/logout, aprovisionamiento explícito, contrato HTTP y pruebas reales.
- [RabbitMQ local](rabbitmq-local.md): cola sintética, permisos y diagnóstico.
- [F003](features/F003-local-accounts-proposal.md): alcance y evidencia.

## Preparar Python y activos locales

Ejecutar PowerShell desde la raíz del repositorio con la cuenta propia `Usuario`.
Se requiere Python 3.13 o 3.14. No crear archivos con cuentas sandbox Codex.
Las dependencias directas y herramientas están fijadas en `backend/pyproject.toml`;
los snapshots fijan también las transitivas resueltas en Windows/CPython 3.14.6.
Revalidarlos al cambiar de plataforma/Python; Linux no está certificado aún.

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
.\backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
.\backend\.venv\Scripts\python.exe scripts/bootstrap_local.py
.\backend\.venv\Scripts\python.exe scripts/bootstrap_local.py --check-only
```

El bootstrap crea o valida CA, certificados de desarrollo y credenciales aleatorias
para PostgreSQL/RabbitMQ en `.env`; no provisiona por sí mismo esos servicios.
Conserva la configuración personalizada y no rota contraseñas ni identidades.
La contraseña inicial del portal requiere su configuración y comando explícitos
explicados en la guía F003. `.env.example` solo documenta nombres y campos vacíos.

Certificados de servicio válidos 90 días, CA 365 días. El bootstrap no instala
confianza. La CA existente se importó aparte con autorización expresa para Usuario
CurrentUser\Root; no en el almacén de la máquina. Activos parciales, vencidos o incompatibles se rechazan; no
borrarlos para forzar una regeneración. Planificar su renovación y recuperación.
El preparador PostgreSQL local conserva la CA y añade SAN de loopback específicos.

Para migraciones antiguas de F002, el bootstrap conserva las contraseñas anteriores
de `.local/secrets` en `.env` sin borrarlas ni rotarlas. No hay fallback de lectura
a `*_PASSWORD_FILE`; un conflicto se rechaza y `--check-only` no migra ni escribe.

## Arrancar y consultar HTTPS

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform
```

En otra terminal:

```powershell
curl.exe --cacert .local/certs/ca.crt https://localhost:8443/api/v1/health
curl.exe --cacert .local/certs/ca.crt https://localhost:8443/api/v1/ready
.\backend\.venv\Scripts\python.exe scripts/probe_identity_local.py
```

`health` acredita el proceso; `ready` consulta PostgreSQL, presencia del esquema de
identidad y RabbitMQ. Un fallo devuelve 503 con estados genéricos. El probe de
identidad consulta por HTTPS e inicia/cierra una sesión del superusuario de bootstrap;
lee el secreto de `.env` y no lo imprime. No es una interfaz para usuarios finales.

No usar opciones que omitan CA o hostname. Detener la API con `Ctrl+C`. La API
escucha en loopback; habilitar acceso remoto necesita el diseño de exposición.
Swagger y OpenAPI públicos están deshabilitados; se incluye
[el contrato estático](api/F003-openapi.json).

## Configuración y secretos

Pydantic valida `APP_*` desde entorno y `.env` (el entorno tiene precedencia).
Las contraseñas se leen literalmente, sin expandir `${VARIABLE}`, y no se admiten
valores vacíos, demasiado cortos, multilínea o claves APP duplicadas ambiguas.
Los errores de configuración no incluyen valores recibidos. Las credenciales de
administración SQL se cargan solo en herramientas administrativas explícitas.

`.env` guarda secretos operativos; `.local/` guarda certificados, claves TLS y
artefactos privados, ambos ignorados por Git. Las claves privadas no se incorporan
a `.env` ni al contexto futuro de imágenes. Las ACL no acreditan cifrado en reposo.
El responsable confirma cifrado actual; verificar volumen del servicio PostgreSQL,
respaldos, custodia de CA y servidor antes de documentos sensibles reales.

PostgreSQL usa `verify-full`, CA, hostname y TLS mínimo 1.2. RabbitMQ exige CA y
nombre. No existe bandera de aplicación para deshabilitar las comprobaciones.
El worker comparte ajustes, sin necesitar la clave privada API. Celery acepta JSON;
resultados, eventos y control remoto permanecen deshabilitados. No iniciar Celery
worker en Windows: su ejecución soportada se verificará en Linux al final.

## Comprobaciones

Desde la raíz, con Usuario:

```powershell
$testParent = Join-Path (Get-Location).Path '.local/test-runs'
New-Item -ItemType Directory -Path $testParent -Force | Out-Null
$testRun = Join-Path $testParent ('tests-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
# Incluir la siguiente variable solo cuando PostgreSQL TLS esté provisionado:
$env:RUN_PG_INTEGRATION = '1'
.\backend\.venv\Scripts\python.exe -m pytest -c backend/pyproject.toml backend/tests tests -q -W error --basetemp $testRun
.\backend\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend scripts tests
.\backend\.venv\Scripts\python.exe -m ruff format --check --config backend/pyproject.toml backend scripts tests
.\backend\.venv\Scripts\python.exe -m mypy --config-file backend/pyproject.toml backend/src/document_platform scripts
.\backend\.venv\Scripts\python.exe -m pip check
git diff --check
```

Usar un basetemp nuevo evita carpetas de temporales de pruebas antiguas. La suite
utiliza certificados/datos sintéticos y prueba TLS real, rechazo de texto plano y
confianza/nombre incorrectos. Con `RUN_PG_INTEGRATION=1` verifica bases nuevas,
privilegios, transacciones y concurrencia contra PostgreSQL real. Sin esa variable,
las pruebas de integración se omiten explícitamente. Las bases sintéticas quedan
conservadas: no se ejecuta DROP ni se eliminan datos automáticamente.

## Diagnóstico

- Inicio rechazado: revisar rutas desde raíz, campos requeridos y `.env` sin
  imprimir su contenido. Evitar variables de entorno antiguas que lo sobrescriban.
- Certificado rechazado: comprobar CA, vigencia y SAN. No ocultar el problema
  deshabilitando la validación o instalando confianza global.
- `/ready` 503: revisar estados de base/broker, sus certificados/credenciales y
  haber ejecutado `identity_admin init-db`. Health no depende de esos servicios.
- Login rechazado: revisar contraseña actual, cookie CSRF, Origin y cabecera.
  Tras cinco fallos por cuenta, esperar a que venza la ventana configurada.
- Bootstrap repetido: no cambia contraseña ni recrea al superusuario. No es un reset.

No hay imágenes publicadas, Compose ni despliegue final. La publicación requiere
registro y autorización expresa.
