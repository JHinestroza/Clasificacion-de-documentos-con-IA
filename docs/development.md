# Desarrollo y verificación local

## Alcance actual

F002 es una base backend HTTPS local. No admite documentos, no administra usuarios
ni ejecuta procesamiento documental. PostgreSQL y RabbitMQ no se instalan aquí.
Docker, servicios reales y workers Linux se ejecutarán y verificarán en una feature
final, por indicación del responsable.

La API escucha en `127.0.0.1:8443` y solo expone:

- `GET /api/v1/health`: el proceso responde, independiente de PostgreSQL/RabbitMQ.
- `GET /api/v1/ready`: consulta ambas dependencias por TLS; responde 503 si no están
  disponibles. Sin servicios reales, ese 503 es el resultado esperado.

La UI de documentación está deshabilitada en esta base. No se ha implementado
autenticación; solo se permite su uso local con datos sintéticos y endpoints de salud.

## Preparar el entorno en Windows

Ejecutar PowerShell desde la raíz del repositorio. Se requiere Python 3.13 o 3.14.
Las dependencias directas y herramientas están fijadas en `backend/pyproject.toml`.
Los snapshots `backend/requirements.lock` y `backend/requirements-dev.lock` fijan
también las transitivas resueltas en Windows/CPython 3.14.6. Revalidarlos al cambiar
de plataforma o versión de Python; no son una certificación del futuro Linux.

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
.\backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
.\backend\.venv\Scripts\python.exe scripts/bootstrap_local.py
```

Si aún no existe `.env`, copiar `.env.example` como `.env`. Conservar cualquier
configuración local ya existente; no sobrescribirla al actualizar el proyecto.

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
.\backend\.venv\Scripts\python.exe scripts/bootstrap_local.py --check-only
```

El bootstrap genera certificados de API, PostgreSQL y RabbitMQ firmados por una CA
de desarrollo, y credenciales distintas aleatorias. Los certificados de servicios
son válidos durante 90 días; la CA durante 365 días. El certificado API incluye
`localhost`, `127.0.0.1` y `api`; los otros incluyen `postgres` y `rabbitmq`.

Reejecutar el bootstrap comprueba los activos y no los cambia. Un conjunto parcial,
expirado o incompatible se rechaza: no borrar ni sustituir archivos para intentar
repararlo sin planificar la recuperación o rotación. Los secretos generados aún no
se han provisionado en una base de datos ni en un broker.

## Arrancar y consultar HTTPS

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform
```

En otra terminal PowerShell:

```powershell
curl.exe --cacert .local/certs/ca.crt https://localhost:8443/api/v1/health
curl.exe --cacert .local/certs/ca.crt https://localhost:8443/api/v1/ready
```

Los comandos anteriores usan `curl.exe` explícitamente para evitar los alias de
PowerShell. No usar opciones que omitan la verificación de certificados. La CA no
se incorpora al almacén de Windows, por lo que navegador o clientes del sistema no
confiarán automáticamente en ella.

Ejemplo equivalente con Python:

```python
import ssl
from urllib.request import urlopen

context = ssl.create_default_context(cafile=".local/certs/ca.crt")
with urlopen("https://localhost:8443/api/v1/health", context=context, timeout=5) as response:
    print(response.read().decode())
```

Detener el proceso con `Ctrl+C`. No cambiar el bind a una interfaz remota sin
aprobar y completar autenticación, autorización y el diseño de exposición.

## Configuración y secretos

`APP_*` se valida con Pydantic Settings desde el entorno y `.env`. Credenciales
obligatorias se leen de archivos, no de valores predeterminados ni de JavaScript.
`APP_TLS_CA_FILE` es obligatorio; PostgreSQL usa `verify-full` y RabbitMQ verifica
CA y nombre de servidor. No se ofrece una bandera para desactivar estas comprobaciones.

El worker comparte la configuración de dependencias, pero no necesita la clave
privada de la API. Celery acepta únicamente JSON; resultados, eventos y control
remoto están deshabilitados en esta base. No iniciar un worker Celery en Windows:
su ejecución soportada se comprobará en Linux en la feature final.

Los secretos y claves están en `.local/`, fuera de Git. Los permisos POSIX se
restringen al crear archivos; esos permisos no prueban las ACL ni el cifrado de
Windows. El responsable declara cifrado en las ubicaciones actuales. Verificar
volúmenes, respaldos, custodia de CA y servidor antes de procesar datos reales.

## Comprobaciones

Desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -c backend/pyproject.toml backend/tests tests
.\backend\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend scripts tests
.\backend\.venv\Scripts\python.exe -m ruff format --check --config backend/pyproject.toml backend scripts tests
.\backend\.venv\Scripts\python.exe -m mypy --config-file backend/pyproject.toml backend/src/document_platform scripts
git diff --check
```

Las pruebas generan activos sintéticos temporales. Verifican TLS real de la API,
rechazo de confianza/nombre incorrectos y tráfico en texto plano, configuración,
errores de disponibilidad y bootstrap idempotente. Las pruebas de adaptadores con
dobles no acreditan conectividad con servicios reales.

## Diagnóstico

- Fallo de inicio por configuración: comprobar archivos requeridos y rutas relativas
  a la raíz; los errores no deben imprimir credenciales.
- Certificado rechazado: usar la CA correspondiente y uno de los nombres del SAN.
  No desactivar la validación ni instalar confianza global para ocultar el problema.
- `/ready` devuelve 503: comprobar disponibilidad, nombre, certificados y credenciales
  de PostgreSQL/RabbitMQ. Mientras no estén provisionados, es el estado esperado.
- Bootstrap rechaza activos: conservarlos para diagnóstico; planificar recuperación
  o rotación. No contiene un modo de reemplazo automático.

No existen todavía imágenes publicadas, Compose ni comandos de despliegue. El
objetivo final de descargar imágenes se concretará al aprobar registro y publicación.
