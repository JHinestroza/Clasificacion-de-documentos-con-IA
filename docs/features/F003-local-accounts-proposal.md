# Propuesta F003 — Cuentas locales, permisos y auditoría

- Estado: Alcance técnico y esquema aprobados por el responsable. Implementación
  pendiente; la integración RabbitMQ local recibió prioridad el 2026-11-12.
- Fecha: 2026-11-10.
- Rama prevista: `feature/usuarios-permisos-auditoria`, desde `develop`.

## Problema y resultado esperado

El superusuario debe crear cuentas y decidir qué puede hacer cada persona. La API
debe rechazar acciones no autorizadas y conservar quién cambió una cuenta o permiso,
cuándo ocurrió y el resultado. Esta propuesta no implementa aún esos comportamientos.

## Alternativas de sesión

| Alternativa | Ventaja | Coste para este proyecto |
| --- | --- | --- |
| Sesión opaca persistida en PostgreSQL | Cerrar sesiones, desactivar cuentas y revocar permisos de forma inmediata. | Consultar estado persistente en solicitudes autenticadas. |
| JWT autocontenido | Validación local del token por varios servicios. | Revocación inmediata requiere estado adicional y controlar permisos obsoletos. |

Se propone la primera: ya tenemos PostgreSQL y una aplicación administrativa
modular. El cliente conserva un identificador aleatorio; la base guarda únicamente
su hash y vigencia. No se necesita introducir un secreto global de firma JWT.

## Seguridad propuesta

- Contraseñas de usuarios con Argon2id y sal aleatoria; nunca en texto plano en la
  base ni en logs. `.env` conserva secretos operativos y, si se aprueba, la contraseña
  de inicialización del primer superusuario; no es un catálogo de contraseñas de usuarios.
- Parámetros Argon2id al menos equivalentes a la recomendación OWASP y límites de
  entrada/concurrencia. Medir el coste en el servidor antes de ajustar producción.
- Cookie `__Host-session` con Secure, HttpOnly, SameSite=Strict, Path=/ y sin Domain.
  Token CSRF y comprobación de origen para las operaciones que cambian estado.
- Sesión con caducidad inactiva y absoluta configurables; propuesta inicial:
  30 minutos sin actividad y 8 horas como máximo.
- Login con respuesta genérica, control persistente de intentos y bloqueo temporal
  acotado; evitar enumeración de usuarios y bloqueo permanente automático.
- Logout revoca la sesión en servidor. Desactivar usuario, cambiar contraseña o
  permisos revoca sus sesiones. Denegar por defecto y revisar permiso en cada acción.
- No permitir que un usuario se conceda permisos ni que se deje el sistema sin
  superusuario activo. Sin registro público de cuentas o credenciales predeterminadas.
- Mantener HTTPS y no introducir exposición remota ni proveedor externo.

## Modelo propuesto y migraciones

Usar PostgreSQL y el adaptador psycopg existentes. Se propone Alembic para
migraciones versionadas; su incorporación es parte de la aprobación solicitada.
No sustituir PostgreSQL por SQLite para presentar como comprobada la integración.

| Tabla | Datos y restricciones principales |
| --- | --- |
| `users` | UUID, nombre de acceso normalizado único, hash de contraseña, activo, superusuario, marcas de tiempo y control de intentos. |
| `permissions` | Catálogo de códigos únicos de acciones permitidas. |
| `user_permissions` | Usuario y permiso con claves foráneas y unicidad; inicialmente concesiones individuales explícitas. |
| `sessions` | Hash de token único, usuario, creación, última actividad, expiración absoluta y revocación. |
| `audit_logs` | Identificador, actor o intento no autenticado, acción, recurso, fecha, resultado y motivo pertinente; sin contraseñas, tokens ni cuerpos completos. |

La cuenta de servicio podrá añadir y consultar auditoría, sin UPDATE/DELETE sobre
esa tabla. No se promete protección frente al administrador propietario de la base.
Se desactivan cuentas en lugar de borrarlas, preservando sus referencias históricas.
Cada cambio de cuenta o permiso y su auditoría se guardarán en una misma transacción:
si falla la auditoría, se revierte el cambio. La protección del último superusuario
debe contemplar también dos desactivaciones concurrentes; no basta un conteo previo.

## Permisos y alcance de recursos

El superusuario administra cuentas y concesiones. El catálogo inicial podrá incluir
consulta de documentos, contenido, dashboard, reportes y auditoría; inicio, pausa y
parada; reencolado y retirada de fallidos. Crear el catálogo no implementa esas
funciones ni autoriza acceso a recursos todavía inexistentes.

En esta feature se aplican permisos a sus endpoints de cuentas y auditoría. El
alcance por fondo y por reporte se diseñará con sus modelos antes de exponer esos
recursos; una concesión genérica no debe saltarse ese filtro. Los roles agrupados
son opcionales posteriores si simplifican la administración de muchos usuarios.

## API y archivos previstos

API inicial propuesta: login, logout, usuario actual, cambio de contraseña;
listar/crear/desactivar cuentas; consultar/asignar permisos y consultar auditoría.
El primer superusuario se crea mediante un comando explícito con secretos de `.env`,
sin imprimirlos. No se crea automáticamente durante el arranque de cada worker.

Módulos previstos: `domain/identity/`, `application/identity/`, adaptadores de
persistencia, `api/auth.py`, `api/users.py`, `api/audit.py`, configuración y pruebas.
`backend/migrations/` contendrá migraciones y restricciones de privilegios. Se
actualizarán dependencias, `.env.example`, ADR y guía con ejemplos HTTPS.
Solo crear carpetas/componentes al tener una responsabilidad real.

## Exclusiones

Sin interfaz web, correo, SSO, recuperación por email, API keys de ingestión,
procesamiento documental, Docker ni publicación. No se generan aún sesiones,
usuarios, tablas o secretos adicionales mediante esta propuesta.

## Pruebas y criterios de aceptación propuestos

- Login correcto/incorrecto, respuesta genérica y control de intentos; hash seguro,
  ausencia de contraseña en respuestas, logs y auditoría.
- Cookies y CSRF; expiración, logout y revocación al cambiar estado o permisos.
- Usuarios sin permiso reciben rechazo, incluso llamando directamente a la API.
- Administración y primer superusuario sin credenciales predeterminadas; proteger
  el último superusuario activo.
- Cambios de cuenta/permiso y rechazos pertinentes dejan auditoría con actor y fecha.
- Un fallo al guardar auditoría revierte el cambio administrativo correspondiente.
- Pruebas unitarias y API con datos sintéticos/dobles. La integración real de
  migraciones, transacciones, restricciones y privilegios PostgreSQL se ejecutará
  en la feature final de Docker, incluida la desactivación concurrente de superusuarios,
  dejando este límite visible en la entrega local.

## Riesgos y aprobación registrada

El responsable aprobó incorporar este esquema, migraciones, Argon2id y sesiones
revocables. La aprobación persiste y no debe solicitarse de nuevo. La implementación
sigue pendiente y no se presenta como funcionalidad verificada.

## Referencias primarias

- [OWASP: contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- [OWASP: sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- [OWASP: autorización](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
- [OWASP: CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
