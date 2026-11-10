# F002 — Base backend segura local

- Estado: Completada y verificada para el alcance local. Despliegue diferido.
- Fecha: 2026-11-10.
- Rama: `feature/entorno-seguro`, desde `develop`.

## Problema y alcance autorizado

Preparar una base pequeña y verificable para las siguientes features, con FastAPI,
configuración centralizada, conexiones cifradas y secretos fuera del código.
El responsable aprobó FastAPI/PostgreSQL/RabbitMQ/Celery/Compose, el significado de
success, movimiento físico de archivos y retirada lógica auditada de fallidos.

Durante esta feature indicó que Docker no está instalado y difirió esa parte a
una feature final. El alcance se ajustó: no se entregan Dockerfile, Compose,
provisionamiento de servicios ni una afirmación de ejecución Linux verificada.
También confirmó cifrado en las ubicaciones actuales, sin auditoría técnica del host.

## Archivos y responsabilidades

- `backend/`: paquete FastAPI, settings, adaptadores TLS de disponibilidad,
  configuración Celery y pruebas unitarias/API/HTTPS.
- `scripts/bootstrap_local.py`: generación y validación sin rotación de CA,
  certificados y secretos de desarrollo.
- `tests/`: pruebas de integridad e idempotencia del bootstrap.
- `.env.example`, `.gitignore`, `.gitattributes`, `.editorconfig`: configuración
  ficticia, exclusiones y convenciones para Windows/Linux.
- `AGENTS.md`, `README.md`, documentación de requisitos, ADRs y operación.

## Exclusiones

Sin documentos reales, ingestión, movimiento de PDF, tablas de dominio, usuarios,
roles de aplicación, auditoría persistente, UI, IA ni tareas documentales. No instala
Docker, PostgreSQL, RabbitMQ, certificados en Windows ni modifica cifrado del host.
Las features siguientes implementarán esas responsabilidades dentro de su alcance.

## Criterios de aceptación locales

- [x] La API arranca en HTTPS con configuración válida, inicialmente en loopback.
- [x] Confianza válida funciona; CA o nombre incorrectos y HTTP plano se rechazan.
- [x] Configuración incompleta falla sin exponer secretos; no hay fallback sin TLS.
- [x] `/health` es independiente de las dependencias; `/ready` devuelve 503 genérico
  si una dependencia falla, sin filtrar su excepción.
- [x] PostgreSQL exige `verify-full`; RabbitMQ verifica CA/nombre y Celery solo JSON.
- [x] El worker no requiere ni carga la clave privada de la API.
- [x] Bootstrap idempotente; activos incoherentes no se sobrescriben.
- [x] Pruebas, lint, formato, tipos, enlaces locales y diff verificados.
- [x] Ningún secreto, clave privada ni documento real incorporado al commit.

## Riesgos y límites

- Salud del proceso no significa que PostgreSQL/RabbitMQ estén disponibles.
- Pruebas con dobles no sustituyen servicios reales. `/ready` debe permanecer no
  disponible cuando no existan dependencias configuradas accesibles por TLS.
- La CA local no es una PKI institucional ni incluye rotación automática.
- Permisos de archivos y TLS no prueban cifrado del host o respaldos.
- Una dependencia fijada directamente no es una validación de todo Linux/producción.

## Verificación ejecutada

Entorno: Windows, CPython 3.14.6, dependencias en `backend/.venv`.

| Comprobación | Resultado |
| --- | --- |
| Pytest conjunto con warnings tratados como errores | 30 pruebas pasadas, sin fallos ni pruebas omitidas. |
| Ruff lint y formato con configuración común | Correcto; 26 archivos Python con formato válido. |
| Mypy estricto, backend y scripts | Sin errores en 19 archivos fuente. |
| `pip check` | Sin dependencias incompatibles. |
| Enlaces Markdown locales y UTF-8 | Correctos. |
| Diff y exclusiones Git | Sin errores; `.env`, `.local` y `.venv` excluidos. |

Además de las pruebas automatizadas, se ejecutó `python -m document_platform`
usando `.env` y los activos de desarrollo locales: `/health` respondió 200 mediante
HTTPS con la CA verificada y `/ready` respondió 503 sin servicios provisionados.
El proceso de comprobación se detuvo al terminar. El bootstrap se ejecutó y volvió
a verificar los mismos activos sin cambiarlos, sin imprimir sus contenidos.

Durante verificación se corrigieron la firma del callback TLS de Uvicorn y la
clasificación de imports de Ruff al ejecutar desde la raíz. Las comprobaciones
afectadas volvieron a pasar. No quedan fallos locales pendientes conocidos.

Los commits y la integración local quedan trazados en el historial Git de
`feature/entorno-seguro` y `develop`. No se crean tags ni publicaciones remotas.

## Pendiente para la feature final

Instalar Docker, crear imágenes/Compose, provisionar PostgreSQL/RabbitMQ con mínimos
privilegios y listeners seguros, ejecutar workers Linux, probar integración real,
reinicios, persistencia, permisos y cifrado del despliegue. Sin publicar imágenes
ni tags sin autorización remota.
