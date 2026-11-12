# ADR 0005 — Identidad local y auditoría transaccional

- Estado: aprobado por el responsable; implementado en F003.
- Fecha de implementación: 2026-11-12.
- Alcance: backend local con PostgreSQL nativo Windows y TLS verificado.

## Contexto y alternativas

Las cuentas son locales y un superusuario administra sus permisos. Desactivar una
cuenta o retirar un permiso debe tener efecto inmediato. La aplicación modular ya
usa PostgreSQL y no requiere validación de tokens sin consultar estado compartido.

| Alternativa | Ventaja | Coste |
| --- | --- | --- |
| Sesión opaca en PostgreSQL | Revocación inmediata y estado único. | Consulta y actualización de sesión por petición autenticada. |
| JWT autocontenido | Validación local sin consultar sesiones. | Revocación y permisos cambiantes requieren estado adicional, caducidades y custodia de firma. |

Se eligen sesiones opacas aleatorias de 256 bits; solo su hash SHA-256 se persiste.
SHA-256 corresponde a un token aleatorio de alta entropía; las contraseñas utilizan
Argon2id con sal, no ese hash rápido. No se añade secreto JWT.

## Decisión

- Argon2id con 19 456 KiB, tiempo dos, paralelismo uno y límite de concurrencia;
  contraseñas de 16–128 caracteres. Los errores y vistas no contienen credenciales.
- Cookie de sesión `__Host-`, Secure, HttpOnly, SameSite=Strict, sin Domain.
  Caducidad inactiva y absoluta en servidor. Logout, contraseña, estado y permisos
  revocan sesiones persistidas. Se puede crear un segundo superusuario mediante
  una acción explícita de otro superusuario; no se permite desactivar al último.
- Todas las mutaciones verifican Origin HTTPS exacto y doble presentación del CSRF
  (cookie y cabecera). Tras login, el CSRF está ligado a la sesión mediante un HMAC
  derivado del token; su hash se persiste. El desafío inicial no autentica al cliente.
- Fallos de login registrados por hash de nombre, con ventana temporal persistente,
  límite uniforme para cuentas conocidas/desconocidas y respuesta genérica.
- Autorización en casos de uso. Administración de cuentas exclusiva del superusuario;
  consulta de auditoría exige superusuario o `audit.read`. El resto de permisos no
  habilita endpoints futuros ni elimina sus futuros filtros de recursos.
- Repositorio y unidad de trabajo con psycopg; API, casos de uso y dominio separados.
  Cambios y auditoría comparten transacción. Los rechazos se confirman antes de
  devolver su error. Un bloqueo asesor transaccional común evita estado de permisos
  obsoleto y carreras del último superusuario bajo READ COMMITTED.
- Alembic versiona cambios aditivos. Solo herramientas administrativas explícitas
  cargan `APP_DB_ADMIN_PASSWORD`; la API utiliza el rol `document_app`, no propietario,
  sin DDL, DELETE de cuentas ni UPDATE/DELETE/TRUNCATE de auditoría. La inicialización
  restaura las concesiones del proyecto, conservando contraseñas y registros.
- Primer superusuario mediante comando explícito y contraseña aleatoria en `.env`.
  Inicializar otra vez registra el rechazo y no restablece la contraseña.

## Consecuencias y límites

La serialización simplifica las garantías para una carga administrativa local. A
cambio, no permite ejecutar en paralelo todas las operaciones de identidad. Medir
carga, latencia, coste Argon2id y contención antes de cambiar el diseño. Los índices
sostienen la consulta de intentos y la paginación de auditoría; su retención necesita
una política futura, sin limpieza automática destructiva.

La cuenta propietaria de la base conserva capacidad administrativa sobre los datos.
La separación de roles no equivale a auditoría inmutable frente a ese administrador.
Los permisos por fondo/reporte y la recuperación de cuentas se diseñarán antes de
exponer tales funciones. No se añaden SSO, registro público, correo ni API keys.

PostgreSQL nativo se incorporó después de que el responsable lo instaló para
continuar F003. Las pruebas locales reales anticipan esta verificación; Docker,
paquetización Linux y despliegue completo permanecen diferidos a la feature final.

## Fuentes primarias

- [OWASP: almacenamiento de contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- [OWASP: sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- [OWASP: CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- [PostgreSQL: TLS](https://www.postgresql.org/docs/18/ssl-tcp.html).
- [PostgreSQL: bloqueos asesores](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS).
- [Alembic: entorno de migración](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
