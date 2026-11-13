# Requisitos y restricciones

Actualizado: 2026-11-13. Fuente: instrucciones del responsable del proyecto.
Este documento registra requisitos; no acredita funcionalidades implementadas.

## Acordado

| ID | Requisito |
| --- | --- |
| R01 | Trabajar por features con alcance, documentación, verificación y pendientes propios. |
| R02 | Mantener estado persistente e historial de documentos y trabajos para identificar avances y fallos. |
| R03 | Desarrollar inicialmente en Windows. Docker Compose con servicios Linux está aprobado, pero su instalación, definición de contenedores y validación de despliegue se difieren explícitamente a una feature final. El objetivo operativo final es descargar imágenes y arrancar el sistema. |
| R04 | Mover físicamente los archivos desde ingreso/procesamiento hacia `failed` o `success`; retirarlos del origen solo mediante una operación recuperable que preserve su contenido. |
| R05 | Ingresar documentos desde una carpeta mediante una interfaz amigable con controles de inicio y parada. Definir pausa y cancelación por separado. |
| R06 | Omitir una nueva ingestión si su código ya está registrado y dejar constancia del motivo. Ejemplos acordados: CAB01.pdf/CAB02.pdf con códigos completos CAB01/CAB02, conservando ceros. |
| R07 | Configurar fondo y metadatos según los archivos o lotes, mediante configuración y prompts. La salida debe respetar un esquema validado. |
| R08 | Administrar usuarios mediante un superusuario de la aplicación y aplicar mínimo privilegio. |
| R09 | Distinguir permisos para consultar documentos, ver dashboard y reportes, iniciar, pausar, detener, reencolar y eliminar. El backend debe verificar los permisos. |
| R10 | Registrar fallidos con motivo y permitir reprocesarlos o retirarlos de la lista de reencolamiento. Retirar exige actor, fecha y motivo, conserva el PDF y la auditoría y no destruye resultados ni historial. |
| R11 | Cifrar todas las comunicaciones de la aplicación, incluidos documentos, credenciales y control, verificando la identidad del servidor. Proteger también los datos en reposo y sus copias; el mecanismo debe definirse y comprobarse. |
| R12 | Crear nuevas ramas `feature/nombre-feature` desde `develop` hasta nueva indicación; integrar localmente features verificadas. Conservar ramas anteriores. Preparar releases con versión y tag según criterios acordados. |
| R13 | Incorporar un dashboard avanzado más adelante; la consulta operativa de estados e historial debe acompañar al procesamiento. |
| R14 | `success` significa que pasó por la cola y terminó el procesamiento de metadatos. No requiere aprobación humana habitual. La intervención manual inicial atiende fallidos y sus acciones. |
| R15 | El responsable confirma cifrado en las ubicaciones actuales de datos. La cobertura de futuros volúmenes, respaldos y servidor se verificará antes del despliegue con documentos reales. Esta confirmación no es una auditoría técnica del host. |
| R16 | Guardar los secretos operativos en el `.env` de la raíz, excluido de Git. `.env.example` solo documenta nombres y valores ficticios/vacíos. Los certificados y claves TLS siguen en archivos protegidos referenciados desde la configuración. |
| R17 | Usar cuentas locales administradas por el superusuario. F003 implementa y verifica localmente sesiones revocables, permisos, auditoría y esquema PostgreSQL por TLS. |

El superusuario de la aplicación no implica permisos de administrador del sistema,
de Docker o de PostgreSQL. El acceso a documentos y reportes deberá considerar el
alcance autorizado, por ejemplo por fondo, además del permiso de ejecutar una acción.

## Restricciones persistentes

- Consultar cambios relevantes de arquitectura, infraestructura, autenticación,
  seguridad, base de datos o alcance antes de implementarlos.
- No publicar código, imágenes, releases ni realizar operaciones Git remotas sin
  autorización expresa. Los merges locales de features verificadas están autorizados.
- No ejecutar borrados destructivos de datos o volúmenes sin autorización.
- No enviar documentos reales a proveedores de IA u otros servicios externos sin
  autorización. Utilizar documentos sintéticos durante las pruebas.
- No guardar secretos ni contenido documental en logs; limitar sus datos y proteger
  el acceso al historial y a la auditoría.
- No declarar una función terminada sin implementación, verificación y evidencia.
- No habilitar comunicaciones en texto plano ni desactivar la verificación de
  certificados. HTTPS y conexiones TLS verificadas serán obligatorias en los
  componentes seleccionados, también dentro de la red de Docker.

## Base técnica aprobada

- FastAPI, PostgreSQL, RabbitMQ y Celery; aplicación modular con API/workers separados.
- Docker Compose y contenedores Linux, diferidos a una feature final.
- F002: backend local, configuración segura, certificados y pruebas TLS. La
  integración con servicios reales y la ejecución Linux no son parte de su cierre.

## Recomendaciones y detalles pendientes

- Reintentos automáticos limitados para errores transitorios y evaluación manual
  de fallidos definitivos; la base de datos conserva el historial, aunque exista
  una cola separada de fallidos.
- Una reejecución autorizada crea un intento para el mismo documento, no una nueva
  ingestión que entre en conflicto con el control de código repetido.
- Perfiles, esquema de metadatos y prompts versionados por ejecución. Empezar con
  reglas o simulador hasta aprobar un proveedor y su tratamiento de datos.
- Un fallo puede ocurrir antes o después de generar artefactos parciales. Solo una
  ejecución completada publica metadatos válidos; se conserva la causa y etapa del
  fallo para diagnóstico. La retirada lógica no debe borrar esa evidencia.
- Mover con registro recuperable: renombrar de forma atómica donde sea posible; si
  cruza unidades, copiar a temporal, verificar contenido, publicar destino y solo
  entonces retirar origen. Probar reinicios entre pasos antes de habilitarlo.

## Secuencia propuesta de features

| Feature | Resultado demostrable propuesto |
| --- | --- |
| F001 — Acuerdos de trabajo | Requisitos, decisiones pendientes y ficha verificable de esta entrega documental. |
| F002 — Base backend segura | API HTTPS local, configuración validada, secretos en archivos, certificados y pruebas TLS. Docker y servicios reales se verifican en la feature final. |
| F002A — Secretos en .env | Migrar credenciales sin rotarlas, validar lectura literal y mantener redacción de errores y exclusiones de Git. |
| F002B — RabbitMQ local TLS | Broker real, permisos mínimos y cola sintética verificable en Windows; sin worker Celery. |
| F003 — Usuarios y permisos | Cuentas locales, sesiones revocables, permisos y auditoría implementados y verificados con PostgreSQL TLS nativo Windows. |
| F004A — Portal React | Portal React de acceso, cuentas, permisos y auditoría verificado en navegador por HTTPS con confianza autorizada para Usuario. |
| F004B — Ingreso por carpetas (propuesto) | [Alcance pendiente de consulta](features/F004B-ingestion-carpetas-proposal.md): carpeta por fondo, ingreso recuperable, estados e historial y publicación RabbitMQ. |
| F005 — Extracción recuperable | Workers, texto por página, fallos, cola separada, reencolado e idempotencia comprobada. |
| F006 — Metadatos configurables | Perfil de fondo, esquema y prompt versionados; propuestas validadas con evidencia. |
| F007 — Resultados y operación | Completar consulta operativa y acciones auditadas sobre fallidos; sin aprobación humana obligatoria de los procesados correctamente. |
| Final — Despliegue Linux | Docker/Compose, servicios PostgreSQL/RabbitMQ reales, workers Linux, cifrado de almacenamiento, integración, reinicios y evidencia de ejecución completa. |

La base técnica, F002, F003 y la prueba F002B están aprobadas; el resto de features requiere su alcance.
El dashboard y los reportes avanzados
se planificarán después. Las funciones de seguridad, historial y recuperación
acompañarán a las features que las necesitan; no serán un endurecimiento posterior.

## Actualización del 2026-11-12

RabbitMQ instalado y prueba real por TLS autorizada antes de Docker. El responsable
exige archivos bajo Usuario, sin propietarios Codex. F003 está implementada y verificada con PostgreSQL 18.7 nativo Windows y TLS.
La integración real local no sustituye el despliegue Linux/Compose de la feature final.

## Reglas concretadas para F004

Código completo sin extensión: CAB01.pdf → CAB01, CAB02.pdf → CAB02. Conservar
ceros; máximo de 100 MB por PDF. Controles por lote: pausar/detener finaliza la
admisión iniciada y conserva pendientes. React o Vue autorizado; F004A adopta React.
