# F002A — Secretos operativos en .env

- Estado: Completada y verificada para el alcance local.
- Fecha: 2026-11-10.
- Rama: `feature/secrets-env`, desde `develop`.
- Autorización: el responsable solicita expresamente colocar los secretos en `.env`.

## Objetivo y alcance

Sustituir referencias a archivos de contraseñas por valores operativos en el `.env`
ignorado de la raíz. Conservar credenciales existentes, certificados y configuración
personalizada; no exponer valores ni introducir contraseñas predeterminadas.

## Archivos

- `backend/src/document_platform/config.py` y pruebas de configuración/API: carga
  directa como secretos, lectura literal, validación y redacción.
- `scripts/bootstrap_local.py` y `tests/test_bootstrap_local.py`: generación y
  migración segura e idempotente de `.env`.
- `.env.example`, `AGENTS.md`, README, guía, arquitectura, requisitos y ADR 0003.
- Propuesta F003: registrar cuentas locales y preparar alcance revisable; sin código
  de autenticación ni migraciones de base de datos en esta rama.

## Exclusiones y riesgos

Sin Docker, servicios reales, cuentas de usuario, UI ni nueva base de datos. Las
claves TLS siguen como archivos protegidos. No borrar respaldos de secretos previos,
no rotar credenciales ni modificar valores reales como efecto de una verificación.
Un `.env` parcial, duplicado o en conflicto debe rechazarse sin cambios destructivos.

## Criterios de aceptación

- [x] Settings usa `APP_DB_PASSWORD` y `APP_BROKER_PASSWORD` desde `.env`/entorno.
- [x] No aparecen valores en representaciones, serializaciones, errores o logs.
- [x] Los secretos se leen literalmente y se aplica precedencia de entorno.
- [x] Bootstrap crea `.env` funcional y conserva configuración personalizada.
- [x] Migración real conserva las tres credenciales previas y los certificados.
- [x] Reejecución y `--check-only` no rotan ni modifican activos.
- [x] Pruebas, lint, formato, tipos, enlaces y diff correctos.
- [x] `.env`, claves y credenciales reales no están en el commit.

## Evidencia

Entorno local: Windows y CPython 3.14.6, sin Docker.

| Comprobación | Resultado |
| --- | --- |
| Pytest conjunto con warnings tratados como errores | 66 pruebas pasadas, sin fallos, warnings ni omisiones. |
| Ruff lint y formato | Correctos; 26 archivos Python. |
| Mypy estricto | Sin errores en 19 archivos fuente. |
| `pip check` | Sin dependencias incompatibles. |
| Enlaces locales, UTF-8 y diff | Correctos. |
| Exclusiones y revisión de contenido versionable | Sin `.env`, claves ni credenciales reales. |

Migración real ejecutada sin imprimir valores: las tres credenciales coinciden con
las anteriores; los ocho archivos TLS y los respaldos individuales siguen intactos.
Settings carga el `.env` migrado. Repetir bootstrap y `--check-only` no cambia sus
valores ni certificados. Se corrigió el comentario generado antiguo que decía que
las contraseñas no pertenecían al archivo; se conserva la configuración restante.

Arranque real mediante `python -m document_platform`: `/health` respondió 200 por
HTTPS con la CA verificada; `/ready` permaneció en 503 sin servicios provisionados.
El proceso de comprobación se detuvo al terminar.

Durante revisión se corrigieron interpolación de dotenv, inputs de errores/debug,
temporales ignorados, destino `.env.example` protegido y rutas TLS incompletas.
Las comprobaciones afectadas volvieron a pasar. Docker y servicios reales siguen
pendientes de su feature final; la propuesta F003 no está implementada.
