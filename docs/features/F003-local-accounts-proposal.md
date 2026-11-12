# F003 — Cuentas locales, permisos y auditoría

- Estado: implementada y verificada localmente; integración local en `develop`.
- Diseño aprobado: 2026-11-10. Implementación: 2026-11-12.
- Rama: `feature/usuarios-permisos-auditoria`, desde `develop`.
- La ruta conserva el nombre de la propuesta original para mantener sus enlaces.

## Resultado y alcance

El superusuario crea cuentas locales, activa/desactiva usuarios y asigna permisos.
La API aplica autorización en el servidor. Las sesiones se revocan al cerrar sesión,
cambiar contraseña, estado o permisos. PostgreSQL conserva cuentas, sesiones y
sucesos de auditoría con actor, recurso, acción, fecha, resultado y motivo pertinente.
La auditoría y cada cambio se confirman en una misma transacción; si falla el
registro, el cambio se revierte.

PostgreSQL 18.7 nativo de Windows está integrado mediante TLS con CA y nombre
verificados. El primer superusuario de la aplicación se inicializó explícitamente;
su contraseña aleatoria está en `.env`, sin imprimirla. Es distinto del administrador
PostgreSQL y de la cuenta de servicio `document_app`.

## Decisiones aplicadas

- [ADR 0005](../decisions/0005-local-identity.md): sesiones opacas persistidas,
  Argon2id y auditoría transaccional. No hace falta una clave global de firma JWT.
- Argon2id: memoria 19 456 KiB, dos iteraciones, paralelismo uno, sal aleatoria de
  16 bytes y salida de 32 bytes; concurrencia limitada. Contraseñas de 16–128
  caracteres, sin truncamiento ni credenciales predeterminadas.
- Solo se almacenan SHA-256 de identificadores de sesión y desafíos CSRF. La cookie
  `__Host-session` es Secure, HttpOnly, SameSite=Strict, Path=/, sin Domain.
- Inactividad de 30 minutos y máximo absoluto de ocho horas, configurables.
  Los cambios de seguridad invalidan todas las sesiones del usuario afectado.
- Origen HTTPS exacto, cookie y cabecera CSRF en cada mutación, incluido el login.
  El CSRF autenticado se deriva por HMAC del token aleatorio y se comprueba contra
  su hash persistido; no se almacena el token bruto.
- Intentos fallidos persistidos por hash del nombre normalizado: cinco en 15 minutos
  por defecto. Respuestas genéricas para usuario desconocido, inactivo o contraseña
  incorrecta; el bloqueo temporal no se extiende por solicitudes ya bloqueadas.
- Un bloqueo asesor transaccional de PostgreSQL serializa las operaciones de
  identidad y evita carreras entre revocación, permisos y último superusuario.
- Alembic ejecuta migraciones aditivas con credenciales administrativas explícitas.
  La API usa otro rol, sin DDL ni modificación/borrado de auditoría. Reaprovisionar
  no rota contraseñas ni reemplaza cuentas; restaura concesiones mínimas del proyecto.

## Archivos y responsabilidades

| Archivos | Responsabilidad |
| --- | --- |
| `backend/src/document_platform/domain/identity/` | Registros, permisos, errores, reglas de nombre/contraseña y vistas públicas. |
| `application/identity/` | Casos de uso, puertos y política de sesiones; no depende de HTTP. |
| `infrastructure/persistence/identity.py`, `database.py` | Repositorio, unidad de trabajo y conexiones TLS verificadas con psycopg. |
| `infrastructure/passwords.py` | Argon2id y límite de concurrencia. |
| `api/identity.py`, `main.py` | Rutas, contratos de respuesta, cookies, Origin/CSRF y errores públicos sin datos de entrada. |
| `identity_runtime.py`, `identity_admin.py` | Composición de la API y comandos explícitos de migración/inicialización. |
| `backend/migrations/`, `backend/alembic.ini` | Esquema `identity`, índices, catálogo y versión; sin downgrade destructivo. |
| `scripts/prepare_postgres_local.py`, `configure_postgres_windows.ps1` | Certificado loopback y configuración nativa Windows; claves protegidas en ProgramData. |
| `scripts/probe_identity_local.py` | Prueba reproducible por HTTPS usando secretos locales sin mostrarlos. |
| `backend/tests/identity/`, `test_database_probe.py` | Política, HTTP y pruebas reales de transacciones, privilegios, concurrencia y TLS. |
| `backend/pyproject.toml`, snapshots de dependencias, `.env.example` | Dependencias y configuración documentada, sin secretos. |
| [Contrato OpenAPI](../api/F003-openapi.json), [guía](../identity-local.md) | Uso de la API local y preparación de PostgreSQL. |

## Comprobaciones y evidencia real

- Suite completa con `RUN_PG_INTEGRATION=1`, advertencias tratadas como errores:
  **139 pruebas pasaron** en Windows/Python 3.14.6 con PostgreSQL 18.7 real.
- Lint y formato Ruff correctos; mypy estricto correcto sobre backend y scripts.
  `pip check` sin incompatibilidades.
- Migración sobre bases sintéticas nuevas; hash Argon2id y solo hashes de sesión;
  login, bloqueo temporal persistente y caducidad inactiva/absoluta comprobados.
- Denegación directa de administración y auditoría a un usuario sin autorización;
  asignación/revocación invalida sesiones; sin autoasignación de permisos.
- Cambio de contraseña, desactivación y logout revocan sesiones. Una doble
  desactivación simultánea conserva exactamente un superusuario activo.
- Un fallo inyectado de auditoría revierte la modificación administrativa.
  `document_app` no puede actualizar, borrar ni truncar auditoría ni crear esquema.
- PostgreSQL rechaza tráfico en texto plano antes de solicitar contraseña; una CA
  ajena o un nombre incorrecto impiden completar el handshake TLS.
- Prueba real por HTTPS: health y ready 200 (PostgreSQL y RabbitMQ), login, usuario
  actual, listado de usuarios, catálogo, auditoría, logout y respuesta 401 posterior.
  El proceso temporal de API fue detenido después de la prueba.
- El rol de servicio y la base principal se provisionaron por TLS; el comando de
  creación inicial no reemplaza una cuenta previamente inicializada.
- Reaprovisionar restaura privilegios mínimos y conserva cuentas y contraseñas.
  Todos los archivos nuevos/modificados se comprobaron con propietario Usuario;
  claves y `.env` permanecen fuera de Git.

Las pruebas PostgreSQL crean bases `document_platform_test_<hex>` con datos
sintéticos, independientes de la base principal. Se conservan, sin DROP ni TRUNCATE;
`.local/identity-test-databases.json` anota las inicializadas completamente.
No se han enviado documentos reales ni usado servicios de pago.

## Riesgos y límites

Solo acceso local loopback, CA de desarrollo y API sin interfaz visual. La
serialización global es deliberada para esta primera administración; medir carga y
coste Argon2id antes del servidor definitivo. El control por cuenta no sustituye
límites generales de tráfico cuando se diseñe una exposición remota. La retención,
respaldo y limpieza de auditoría/sesiones no borran datos automáticamente.

El propietario/administrador PostgreSQL puede modificar su base; no se afirma
inmutabilidad frente a ese administrador. Los motivos administrativos deben limitarse
al hecho operativo, sin documentos ni secretos. No hay recuperación por correo ni
restablecimiento administrativo de contraseñas en esta entrega.

El catálogo de documentos, reportes, procesamiento y fallidos reserva acciones para
features posteriores. No implementa esos recursos ni su alcance por fondo/reporte.
Sin PDF, movimientos de archivos, reencolado, dashboard, Docker, worker Celery
Windows, publicación ni release. Linux, reinicios completos, PKI institucional y
verificación de cifrado de volúmenes/respaldos siguen en la feature final.
