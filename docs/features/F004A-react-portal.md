# F004A — Portal React para cuentas y auditoría

- Estado: implementación y pruebas automáticas; revisión en navegador pendiente de confianza de CA.
- Rama: `feature/interfaz-react`, desde `develop`.
- Fecha: 2026-11-12.
- Parte inicial verificable de F004. La ingestión de PDF permanece pendiente y no se presenta como implementada.

## Alcance y decisiones registradas

El responsable eligió React o Vue frente a HTML/JavaScript sin framework. Se adopta
React, TypeScript y Vite para construir una interfaz conectada a F003. La interfaz
compilada se sirve por el FastAPI HTTPS existente: no se añade un servidor Node
operativo, CORS ni otro backend. Las dependencias y sus transitivas quedan fijadas
en `frontend/package.json` y `package-lock.json`.

Se implementan login/logout, inicio con disponibilidad real de servicios, creación
de cuentas locales, activación/desactivación, concesión de permisos, auditoría
paginada y cambio de contraseña propia. La interfaz muestra solo opciones autorizadas;
la API F003 sigue verificando cada acción, incluyendo llamadas directas.

Se mantienen sesiones opacas, cookies Secure/HttpOnly/SameSite=Strict y CSRF de F003.
El navegador envía cookies del mismo origen y obtiene un CSRF nuevo antes de cada
mutación. No se guardan contraseñas ni tokens en localStorage/sessionStorage. Se
retiran vistas privadas ante un 401 y se revalida al volver a una pestaña visible,
sin polling de sesión que mantenga artificialmente la caducidad por inactividad.

El responsable confirmó para la ingestión posterior: `CAB01.pdf` y `CAB02.pdf`,
códigos completos `CAB01` y `CAB02` conservando ceros; máximo de 100 MB por archivo;
pausa y detención por lote, terminando la admisión iniciada y conservando pendientes.
Estas reglas están registradas, pero F004A no admite ni procesa PDF.

## Archivos

| Archivos | Responsabilidad |
| --- | --- |
| `frontend/src/api/` | Contratos públicos, validación de respuestas, cliente HTTPS/CSRF y errores sanitizados. |
| `frontend/src/auth.tsx` | Estado de sesión en memoria, revalidación y retirada de vistas privadas. |
| `frontend/src/App.tsx`, `pages/`, `components/`, `hooks/` | Navegación, formularios, consultas cancelables y pantallas React. |
| `frontend/src/styles.css`, `theme.css` | Diseño adaptable, controles de teclado, contraste y movimiento reducido. |
| `frontend/src/*.test.tsx`, `api/client.test.ts` | Comprobaciones de permisos, formularios, XSS, revocación, CSRF y fallos. |
| `frontend/package*.json`, `tsconfig.json`, Vite/ESLint | Dependencias fijadas, compilación y herramientas. |
| `backend/src/document_platform/api/web.py` | Shell público y assets compilados permitidos; CSP y cabeceras del navegador. |
| `config.py`, `main.py`, `backend/tests/test_web.py` | Directorio compilado, integración y protección de rutas/recursos. |
| [Guía del portal](../react-portal.md), [ADR 0007](../decisions/0007-react-portal.md) | Operación y fundamento de decisiones. |

## Seguridad de entrega web

`GET /` sirve únicamente el shell compilado, sin datos privados ni credenciales.
`/assets/` solo admite nombres con huella y extensiones públicas limitadas. No se
sirven fuentes TSX, `.env`, mapas de fuentes, directorios del proyecto o archivos
fuera del directorio compilado. La ausencia del build produce un 503 de interfaz;
health y API continúan funcionando. HTTP y cabeceras proxy falsas se rechazan.

CSP permite scripts, estilos y conexiones del mismo origen, sin unsafe-inline/eval;
se añaden nosniff, no-referrer, DENY, política de capacidades y recursos del mismo
origen. Shell/API usan no-store; assets con huella pueden cachearse. Vite no lee
archivos `.env` y no expone variables de entorno al bundle. `frontend/dist` y
node_modules permanecen fuera de Git. Los secretos operativos siguen en el `.env`
raíz y las claves TLS en archivos protegidos, sin cambiar su contenido.

Se fijó TypeScript 6.0.3 porque la versión del linter elegida soporta TypeScript
anterior a 6.1, en vez de introducir TypeScript 7 sin compatibilidad. npm inicialmente
reportó diez avisos moderados derivados de minimatch. Se verificó el parche oficial
11.0.1 y se fijó un override; volver a comprobar lint/build/tests y auditoría forma
parte del cierre, sin ejecutar un upgrade global ni npm audit fix --force.

## Comprobaciones reales

- Backend completo con PostgreSQL TLS real: **150 pruebas pasaron**, incluyendo
  las 139 anteriores y once de entrega web/protección de archivos.
- React/cliente con identidades sintéticas y respuestas controladas: **19 pruebas
  pasaron**. Se verifican acceso sin privilegios y URL directa, cuenta sin permisos
  por defecto, concesiones con motivo, desactivación, password/logout/revocación,
  errores sanitizados, CSRF, cancelación de respuestas antiguas y auditoría como texto.
- La validación detectó y permitió corregir etiquetas accesibles; los nombres y
  ayudas se relacionan por label/aria-describedby. El salto al contenido conserva
  la navegación de la aplicación.
- HTTPS real en puerto temporal 8444, CA y nombre verificados: shell y JS/CSS con
  huella, cabeceras, ready con base/broker, login, identidad, cuentas, permisos,
  auditoría, logout y 401 posterior. Solo cambian sesiones/eventos de la prueba.
- npm audit después del parche: cero vulnerabilidades reportadas en la instalación.
- Build React, TypeScript, ESLint y Prettier correctos. Ruff correcto y mypy
  estricto sin errores en 38 módulos/scripts. npm audit final sin vulnerabilidades.
- Propietarios de los archivos nuevos/modificados comprobados: Usuario. Escaneo
  del código y build sin valores de secretos operativos ni claves privadas.
  Los enlaces locales de documentación son válidos.

Las pruebas de componentes usan jsdom; acreditan lógica y DOM, no una revisión
visual en un motor de navegador. La navegación real a HTTPS fue rechazada con
`ERR_CERT_AUTHORITY_INVALID`. La CA de desarrollo no está en los almacenes Root
de Usuario ni de la máquina. No se omitió esa verificación ni se cambió la confianza
por iniciativa propia. La instalación de confianza o un certificado institucional
requieren la decisión del responsable antes de completar la comprobación visual.

## Exclusiones y pendientes

Sin cambios de tablas, grants del broker, fondos/documentos, carga PDF, ejecución de
lotes, publicación de trabajos, extracción, IA ni Docker. Se mantiene la propuesta
F004 en `feature/ingestion-operacion`. Los permisos de funciones futuras se muestran
como concesiones del catálogo, sin fingir que esas funciones ya están operativas.

No se fusionará esta rama como entrega cerrada mientras quede pendiente la
comprobación requerida del navegador. El servidor temporal de prueba debe detenerse
al terminar la sesión de comprobación; los servicios de PostgreSQL/RabbitMQ se conservan.
