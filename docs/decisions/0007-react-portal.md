# ADR 0007 — React sobre la API HTTPS existente

- Estado: selección React/Vue autorizada; React adoptado para F004A.
- Fecha: 2026-11-12.
- Rama: `feature/interfaz-react`.

## Contexto y decisión

El responsable prefiere un framework React o Vue para la interfaz operativa. Se
elige React con TypeScript y Vite para componentes y contratos tipados. Vue sigue
siendo una alternativa válida; no se necesita incorporar ambos. Esta decisión
sustituye la recomendación de interfaz sin framework de la propuesta F004.

Vite compila archivos estáticos; el runtime es el FastAPI HTTPS ya aprobado. Se
mantienen origen, cookies y CSRF. Node 24 se utiliza solo para instalar, comprobar
y compilar. No se añade Next/Nuxt, SSR, proxy, CORS ni servidor HTTP para desarrollar:
`npm run dev` ejecuta build --watch y la API sirve el resultado por HTTPS.

## Alternativas consideradas

Una SPA React compilada permite conservar backend, usuarios y sesiones sin añadir
un segundo servidor. Un framework con servidor propio cubriría SSR u otras funciones
no necesarias para este panel privado, ampliando runtime e integración. Vue también
resolvería las pantallas; elegir React evita mantener dos ecosistemas a la vez.

La navegación de estas cuatro vistas usa fragmentos del URL y enlaces nativos.
No se añade un router hasta necesitar rutas anidadas/carga de datos más compleja.
El cliente valida la forma de las respuestas y presenta mensajes públicos por
estado HTTP, sin volcar errores crudos ni contenidos enviados. React escapa los
motivos de auditoría como texto; no se usa dangerouslySetInnerHTML.

## Consecuencias

Se mantienen herramientas frontend y un package-lock.json además de las dependencias
Python. El build debe existir antes de iniciar la API para registrar assets. El
servidor permite solo recursos públicos con huella y aplica CSP del mismo origen.
TypeScript 6.0.3 respeta los peers del linter; migrar a 7 exige verificar compatibilidad.
El override minimatch 11.0.1 aplica [el parche del proveedor](https://github.com/advisories/GHSA-g3hv-75wg-m249),
con validación de herramientas. No se cambia el npm global de la computadora.

El 2026-11-13 el responsable autorizó la CA existente en Usuario CurrentUser\Root.
Se instaló únicamente ese certificado público, se verificó su huella y se comprobó
HTTPS con el almacén normal y el navegador. La aplicación no instala confianza al
arrancar y la máquina no recibió la CA. La revisión visual se completó con cuentas
sintéticas aisladas, conservando la validación de cadena/hostname.
La ingestión F004 y su esquema/grants se implementarán en su propia entrega.

## Referencias primarias

- [React: Vite y TypeScript](https://react.dev/learn/build-a-react-app-from-scratch).
- [React: createRoot](https://react.dev/reference/react-dom/client/createRoot).
- [Vite](https://vite.dev/guide/).
- [Vitest](https://vitest.dev/guide/).
