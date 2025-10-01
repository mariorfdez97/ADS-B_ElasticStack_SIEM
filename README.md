Detección de anomalías en tráfico aéreo ADS-B simulado mediante Elastic Stack (SIEM)


El Elastic Stack – conjunto de herramientas que incluye Elasticsearch, Logstash, Beats y Kibana – se ha
consolidado como una plataforma flexible para la administración de sistemas y la gestión de
información y eventos de seguridad (SIEM). Su capacidad para centralizar logs, correlacionarlos y
visualizarlos en tiempo real lo hace atractivo en entornos críticos como la aviación y el transporte. En
este trabajo exploramos el uso de Elastic Stack (u otras soluciones SIEM) aplicado a un caso concreto: la
centralización y análisis de datos ADS-B (Automatic Dependent Surveillance–Broadcast) con fines de
seguridad, particularmente para detectar anomalías en el tráfico aéreo simulado. A continuación, se
revisa el estado del arte de SIEM en ámbitos aeronáuticos, las vulnerabilidades de ADS-B y cómo un SIEM
puede ayudar, ejemplos de implementaciones prácticas en aviación/telemetría, métodos para simular
datos ADS-B anómalos, y posibles mejoras para reforzar la seguridad de este protocolo. Finalmente, se
destaca qué aspectos son reproducibles en un proyecto estudiantil usando Docker, Elastic Stack y scripts
en Python.


Estado del arte: SIEM en aviación e infraestructuras críticas

En sectores de infraestructuras críticas como la aviación, el despliegue de centros de operaciones de
seguridad (SOC) con soluciones SIEM se ha vuelto cada vez más común. Por ejemplo, algunos
proveedores de navegación aérea han comenzado a implementar SOC a pesar de operar redes
cerradas. En Emiratos Árabes Unidos se integró un SOC para el control de tráfico aéreo con monitoreo
en tiempo real, detección de ataques e incident response, reconociendo que incluso sistemas ATM
aislados enfrentan ciberamenazas 1. Organismos como EATM-CERT en Europa también apoyan este
enfoque. Un SIEM en estos entornos recopila y correla registros de múltiples sistemas aeronáuticos
(servidores, equipos de red, aplicaciones de control, etc.) para detectar amenazas de seguridad 2 .
Boeing y Thales incluso han establecido servicios gestionados de SOC específicos para la industria
aeronáutica    3.




El Elastic Stack en particular ha demostrado su utilidad en aviación, no solo para seguridad sino para
análisis operacional. Un caso destacado es Flightwatching, una empresa francesa de tecnología
aeroespacial que monitorea datos de cientos de aviones en tiempo real. Su plataforma utiliza Elastic
Cloud y Kibana como núcleo para almacenar, buscar y analizar enormes volúmenes de datos de
aeronaves, permitiendo crear dashboards, generar alertas y emplear detección de anomalías sobre
esos datos .4Estas capacidades ayudan a identificar eventos inusuales en la flota (p.ej. tendencias
anómalas de rendimiento o mantenimiento) y mejorar la eficiencia operativa. Aunque el objetivo de
Flightwatching es mantenimiento predictivo y ahorro de combustible, es un ejemplo del poder de
Elastic para centralizar datos aeronáuticos y detectar comportamientos fuera de lo normal en tiempo
real   5   .


En el ámbito de seguridad TI, Elastic Stack ya incorpora una solución SIEM propia (Elastic Security) que
permite definir reglas de correlación y alertas. Esto ha llevado a adoptarlo como alternativa de código
abierto a herramientas tradicionales (Splunk, ArcSight, etc.) en muchos entornos. Su uso se extiende a
sistemas de control industrial y transporte. Por ejemplo, la plataforma Elastic se ha aplicado en
monitorización de telemetría de vehículos y sensores IoT debido a su capacidad de indexar datos
diversos y escalar con facilidad   6   . En el sector aéreo, Elasticsearch y Kibana han sido utilizados para




                                                       1
analizar datos de vuelos y sensores en tiempo real
                                               7             , habilitando casos de uso como seguimiento
de flotas, análisis de rutas, e incluso detección de patrones anómalos (fraude, accesos no autorizados o
fallos) mediante técnicas de machine learning 6 . Todo esto indica que existe un terreno fértil para
aplicar SIEM open-source como Elastic Stack a la seguridad en aviación, complementando las
herramientas especializadas de gestión de tráfico.


Desde la perspectiva de administración de sistemas, desplegar Elastic Stack para estos fines
típicamente implica configurar varios servicios: Elasticsearch (motor de almacenamiento/búsqueda),
Logstash o Beats (ingesta de datos) y Kibana (visualización y gestión de alertas). En entornos actuales es
habitual recurrir a contenedores Docker sobre Linux para simplificar la instalación y configuración de
estos componentes. Esta portabilidad permite montar un laboratorio SIEM rápidamente y reproducirlo
en distintas máquinas. De hecho, Elastic proporciona imágenes Docker oficiales, y la comunidad
comparte tutoriales y casos de uso orientados a seguridad. Un administrador de sistemas puede, por
ejemplo, desplegar Elastic Stack en Docker y conectarle módulos de ingesta para distintas fuentes de
datos de aviación (logs de sistemas ATC, flujos ADS-B, etc.), todo ello aplicando buenas prácticas de
gestión (monitorización de recursos, backups, seguridad de acceso, etc.). Esta aproximación reduce la
complejidad de la puesta en marcha y es perfectamente viable en un proyecto académico.


Vulnerabilidades del sistema ADS-B en aviación

El ADS-B (Automatic Dependent Surveillance–Broadcast) es un sistema de vigilancia cooperativa
clave en la aviación moderna. Equipado en la mayoría de aeronaves comerciales, ADS-B obtiene la
posición vía GPS y la transmite periódicamente por radio junto con otros datos (identificación del vuelo,
altitud, velocidad, rumbo, indicadores de emergencia, etc.) para que pueda ser recibida por
controladores aéreos y otros aviones 8 9 . Su adopción ha sido rápida debido a las ventajas
operativas: mejora la cobertura y precisión de vigilancia con menor costo que radares tradicionales. De
hecho, desde enero de 2020 la FAA de EE. UU. exige ADS-B Out en aeronaves que vuelan en la mayoría
del espacio aéreo controlado, y Europa impuso un mandato similar a partir de junio de 2020 10 . En
España, el proveedor ENAIRE ha desplegado una red ADS-B para complementar la vigilancia radar,
cumpliendo con el Reglamento Europeo 1207/2011 11 . Esto ha extendido la cobertura de vigilancia a
zonas remotas y mejorado la conciencia situacional en operaciones de aterrizaje y despegue 12 .


¿En qué consiste la inseguridad de ADS-B? En pocas palabras, ADS-B fue diseñado sin mecanismos de
seguridad robustos. No incorpora cifrado ni autenticación en sus transmisiones. Los mensajes se envían
en texto claro sobre radiofrecuencia (1090 MHz en aviación comercial, 978 MHz en aviación general) y
pueden ser captados por cualquiera en rango 13 . Cualquier receptor ADS-B básico (incluso un dongle
SDR de bajo costo) puede decodificar el tráfico aéreo cercano. Más preocupante aún, el protocolo
carece de validación de integridad: los sistemas receptores confían ciegamente en los datos
transmitidos, por lo que no hay forma de distinguir en origen si un mensaje ADS-B es legítimo o ha sido
falsificado 14 . Esto abre la puerta a múltiples vulnerabilidades y amenazas bien documentadas:


     • Suplantación (spoofing) y emisión de aviones fantasma: Dado que no se exige autenticación,
       un atacante con equipo de radio adecuado puede emitir mensajes ADS-B falsos haciéndose
       pasar por un avión. Es posible generar un avión inexistente en el aire simplemente
       transmitiendo tramas ADS-B con un identificador y posición inventados 15 . Los sistemas de
       control interpretarían esos mensajes como aeronaves reales, pudiendo mostrar en pantalla un
       avión fantasma donde no lo hay. Un ataque de este tipo logró que un avión comercial recibiera
       una alerta TCAS de colisión contra un blanco inexistente, provocado por una prueba de ADS-B en
       tierra 16. Las implicaciones de seguridad son evidentes: se podrían inducir maniobras evasivas
       innecesarias o confundir seriamente al controlador.




                                                     2
         • Ataques de denegación de servicio (DoS) por saturación: Mediante la inyección masiva de
          falsos contactos ADS-B (ghost aircraft flooding), un agresor puede inundar los sistemas de
          vigilancia con decenas de objetivos fantasma . Esto
                                                         15   satura las pantallas radar y sistemas
          de alerta de aeronaves y centros de control, dificultando la detección de tráfico real. En casos
          extremos obligaría a las autoridades a cerrar el espacio aéreo temporalmente por seguridad.
          Como contramedida, se ha sugerido que los operadores atribuyan estas situaciones a fallos
          técnicos (ej. interferencias) para no alarmar, pero el riesgo operacional es claro 17 18 .


         • Manipulación de datos legítimos: Un actor malicioso con acceso a un transpondedor (p. ej., un
           insider en cabina) podría alterar los datos emitidos. ADS-B transmite un código único de 24 bits
          (código ICAO) por aeronave, el cual debería identificarla de forma unívoca. Sin embargo, se
          podría reprogramar un transpondedor para emitir un código ICAO ajeno, simulando ser otra
                    . Esto resultaría en confusión de identidad (dos señales con el mismo ID) y
          aeronave 19
          potencial encubrimiento de vuelos ilícitos. Asimismo, nada impide modificar campos como
          altitud o velocidad en los mensajes, causando incoherencias (por ejemplo, hacer aparecer un
          avión a una altitud muy diferente a la real).


         • Ausencia de confidencialidad y privacidad: Al no cifrarse la información, cualquiera puede
           monitorear movimientos de aeronaves. Esto ha suscitado preocupaciones por la privacidad de
          vuelos sensibles (p.ej. movimientos de jefes de estado o vuelos militares). Páginas web y apps
          públicas (FlightRadar24, OpenSky, ADS-B Exchange, etc.) muestran en tiempo real la posición de
          aviones en base a estas transmisiones abiertas 20 13 . Si bien divulgar la posición no supone un
          ataque por sí mismo, sí facilita inteligencia a actores maliciosos (seguimiento de patrones de
          vuelo, horarios, etc.) y podría combinarse con ataques activos.


En resumen, ADS-B es intrínsecamente inseguro porque fue concebido para mejorar la vigilancia
aérea, no la seguridad informática. Las autoridades son conscientes de estas vulnerabilidades, pero
hasta ahora la mitigación se ha basado en procedimientos externos (como combinar con radar
secundario, o utilizar multilateración de señales para verificar posiciones) más que en asegurar el
protocolo en sí. Esto deja un espacio donde herramientas SIEM y correlación de datos pueden aportar
valor, al detectar anomalías o inconsistencias en los datos ADS-B que podrían indicar un ataque o
fallo.


Elastic Stack como SIEM para datos ADS-B: usos y casos prácticos

Dado el panorama anterior, surge la idea de aplicar un SIEM como Elastic Security para centralizar los
flujos de datos ADS-B y otros logs asociados, con el fin de monitorizar y correlacionar eventos
anómalos. En la práctica, esto implicaría desplegar los componentes de Elastic Stack en servidores (on-
premise o en la nube) y recopilar en tiempo real las tramas ADS-B decodificadas desde una o múltiples
estaciones receptoras. Un administrador de sistemas podría configurar un pipeline donde Beats o
Logstash ingesten los mensajes (por ejemplo, en formato JSON) y los indexen en Elasticsearch; luego
utilizar Kibana para visualizar las rutas de vuelo y, crucialmente, definir reglas de detección que alerten
sobre condiciones sospechosas (valores fuera de rango, patrones inusuales, etc.).


Existen implementaciones prácticas y proyectos que sientan las bases de este enfoque. Por ejemplo,
la comunidad ha desarrollado soluciones open source para integrar datos de vigilancia aérea en Elastic
Stack. Un caso es Flight Track, un proyecto que provee configuraciones de Logstash y dashboards de
Kibana para visualizar señales ADS-B
                                  21 . Empleando un receptor ADS-B (p. ej. un RTL-SDR ejecutando

dump1090), los datos de posición de aviones pueden introducirse periódicamente en Elasticsearch
mediante Logstash 22 . Kibana luego muestra un mapa de vuelos en tiempo real y estadísticas de




                                                       3
tráfico. Si bien este proyecto se orienta a hobbyistas para monitoreo de tráfico aéreo, ilustra cómo
Elastic Stack puede absorber datos ADS-B de forma continua. Un estudiante podría reutilizar
componentes similares, añadiendo sobre ellos reglas de correlación para detectar, por ejemplo, dos
aviones con el mismo identificador o velocidades improbables.


Asimismo, iniciativas como la OpenSky Network (comunidad que agrega datos ADS-B de miles de
receptores globales) han demostrado la viabilidad de recolectar y analizar grandes volúmenes de datos
de telemetría aeronáutica. OpenSky ofrece APIs y conjuntos de datos históricos que pueden importarse
a plataformas Big Data. De hecho, en estudios de ciberseguridad, investigadores han empleado datos
de OpenSky para buscar anomalías en las trayectorias y evaluar ataques de spoofing. Aunque estos
trabajos suelen usar herramientas de data science a medida, es perfectamente posible cargar dichos
datos en Elasticsearch para aprovechar su capacidad de búsqueda rápida y agregaciones. Elastic, por su
parte, incorpora funciones de detección de anomalías automatizada (via Machine Learning jobs) que
podrían aplicarse a métricas de vuelo (detectando comportamientos fuera de lo común en altitud,
rumbo, etc.). Esta funcionalidad ha sido utilizada por clientes de Elastic en aviación para identificar
outliers en tiempo real en flujos de datos operacionales 6 , y se puede reaprovechar en el contexto de
seguridad.


En cuanto a herramientas SIEM alternativas en entornos críticos, cabe mencionar que existen
soluciones como Splunk (comercial) o Wazuh (open-source) que igualmente podrían ingerir datos ADS-
B. Por ejemplo, Wazuh extiende Elastic Stack con reglas de seguridad predefinidas y agentes; con la
configuración adecuada, se podría enseñar al agente a reconocer formatos ADS-B y generar alertas. Sin
embargo, al contar ya Elastic Stack con capacidad nativa de indexar y consultar estos datos, suele ser
más directo construir encima de Elastic Security reglas personalizadas. La comunidad de seguridad ha
compartido experiencias usando ELK para monitorizar sistemas SCADA, IoT y tráfico de red, lo cual es
análogo a monitorizar telemetrías aeronáuticas. La clave está en definir un esquema de datos común
(normalizar los campos relevantes de ADS-B: identificador, coordenadas, velocidad, etc.) para luego
aprovechar el motor de correlación del SIEM.


Un trabajo académico reciente propone precisamente un marco conceptual de SOC para sistemas de
gestión de tráfico aéreo que incluye la ingesta de datos de vigilancia aérea en un SIEM. En este enfoque,
todos los logs de seguridad y eventos operativos (incluyendo mensajes ADS-B, datos de radar,
registros de redes y sistemas ATM) serían normalizados y almacenados en un SIEM, donde se
correlacionan con inteligencia de amenazas para detectar posibles ciberataques 2 . Esto confirma que
la idea de usar un SIEM en aviación no es descabellada: al contrario, es una línea de desarrollo
recomendada para mejorar la visibilidad de seguridad en un entorno tan delicado. Un SIEM puede
alertar tempranamente de, por ejemplo, la aparición de un transmisor ADS-B no autorizado operando
en la red de vigilancia, o de discrepancias entre distintas fuentes de datos de vigilancia (radar vs ADS-B).
En suma, los casos prácticos e investigaciones consultados demuestran que Elastic Stack y
herramientas similares pueden integrarse con éxito en entornos de aviación para centralizar datos y
apoyar la detección de anomalías de seguridad.


Métodos de simulación de datos ADS-B anómalos

Para probar las capacidades de un SIEM en este contexto, es necesario contar con datos ADS-B
simulados que incluyan tanto escenarios normales como eventos anómalos o maliciosos. Generar
datos ADS-B falsos o manipulados resulta factible mediante varias técnicas, de complejidad variable. A




                                                     4
continuación, se enumeran algunos métodos de simulación y ejemplos de anomalías introducidas
deliberadamente:


     • Reproducción de tráfico real con modificaciones: Una opción sencilla es tomar registros reales
       de ADS-B (por ejemplo, datos históricos de vuelos obtenidos de OpenSky u otro feed) y luego
       alterar ciertos campos para simular incoherencias. Por ejemplo, se podría reducir artificialmente
       la altitud de un vuelo comercial a un valor negativo para ver cómo el SIEM lo detecta. También es
       posible duplicar entradas cambiando solo el identificador (código ICAO) para crear un
       doppelgänger de un avión real en la misma posición. Esta técnica aprovecha datos plausibles
       como base y solo altera lo necesario para introducir la anomalía.


     • Generación sintética por script: Usando lenguajes como Python, es viable escribir scripts que
       emitan mensajes ADS-B sintéticos en formato JSON o CSV siguiendo la estructura típica (campos
       de tiempo, ICAO, latitud, longitud, altitud, velocidad, rumbo, etc.). Estos scripts pueden generar
       valores aleatorios dentro de rangos realistas para múltiples “vuelos” simulados, e insertar casos
       extremos para pruebas. Por ejemplo, se pueden crear aeronaves con velocidades imposibles
       (e.g. 2500 nudos, muy por encima de cualquier avión comercial) o con saltos bruscos de
       posición (teleportaciones) de un segundo a otro. Asimismo, se puede generar dos mensajes
       simultáneos con el mismo código ICAO pero posiciones distintas, simulando la colisión de
       identificadores que podría ocurrir en un ataque de spoofing 19 . Estos datos sintéticos se
       pueden enviar al Elastic Stack de varias formas: o bien escribiéndolos en un archivo de log que
       Filebeat/Logstash lea continuamente, o haciendo POST por API a Elasticsearch simulando un
       flujo en tiempo real.


     • Emulación con software especializado: Existen herramientas más elaboradas diseñadas para
       simular entornos ADS-B. Por ejemplo, ciertos simuladores de ATC o utilidades de prueba de
       transpondedores pueden emitir datos ADS-B en un ambiente controlado. Algunos
       investigadores han usado radios definidas por software (SDR) para generar realmente señales
       ADS-B RF de prueba 15 , aunque esto suele requerir hardware y permisos (ya que transmitir en
       1090 MHz sin autorización es ilegal). En el contexto de un trabajo académico, no es necesario
       transmitir por aire; es suficiente con emular la salida decodificada de un receptor. Por ejemplo,
       dump1090 (software decodificador) tiene un modo de reproducción donde acepta datos desde
       un archivo en lugar de la antena, permitiendo “reinyectar” mensajes grabados o fabricados. Así,
       se podría tomar un conjunto de mensajes ADS-B reales capturados y mezclar en ellos falsos para
       luego alimentar el SIEM desde dump1090 en modo test.


     • Introducción de errores de formato o protocolo: Otra categoría de anomalías simulables son
       las que provienen de fallos técnicos más que de atacantes. Por ejemplo, mensajes corruptos o
       mal formateados, campos vacíos o con valores fuera de especificación (como una altitud = 99999
       o = -5, que podrían indicar error de sensor). Un script puede generar tales outliers para verificar
       si el sistema los identifica. Del mismo modo, podría simularse la pérdida intermitente de señales
       (como ocurriría bajo jamming), enviando mensajes válidos que de pronto cesan abruptamente
       durante intervalos anormales.


Al implementar estos métodos, es importante definir escenarios de prueba que correspondan a
amenazas o situaciones reales que queremos detectar. Por ejemplo, un escenario puede ser: “aparición
de aeronave fantasma”: el script introduce un nuevo avión en una zona donde no debería haber
ninguno, o duplica un vuelo existente con distinto rumbo. Otro escenario: “datos físicamente
imposibles”: un avión que reporta altitud negativa a medio vuelo, o velocidad supersónica sin ser un
caza. También “inconsistencia multi-sensor”: dos receptores distintos que reportan datos conflictivos (si
se tuviera un entorno distribuido). Cada escenario servirá para validar reglas específicas en el SIEM.




                                                    5
La simulación de datos anómalos debe realizarse con cuidado para no provocar falsos positivos
excesivos. Se recomienda introducir las anomalías de forma aislada en un mar de datos normales, de
modo que destaquen como picos o eventos puntuales – tal como ocurriría en la realidad. Por ejemplo,
de 1000 mensajes simulados, quizás 980 son lógicos y 20 contienen irregularidades diversas. Esto
facilita que las reglas de correlación o detección de outliers de Elastic puedan diferenciarlos con
claridad.


En un proyecto de estudiante, probablemente lo más práctico es optar por la generación sintética con
Python y/o la modificación de trazas reales, pues ofrecen control total sobre los valores. Además, son
métodos poco complejos de implementar (no requieren equipamiento extra más allá de un PC). De
hecho, hay antecedentes de estudiantes que en sus proyectos definieron alertas para “altitud negativa”
o “velocidad fuera de rango” en análisis de ADS-B, lo cual sugiere que esta aproximación es manejable y
efectiva 23. En resumen, disponemos de múltiples formas de simular datos ADS-B anómalos, todas
asequibles con software libre, lo que permite probar a fondo las capacidades del SIEM sin tocar
sistemas reales.


Posibles mejoras y refuerzo de la seguridad con SIEM

Finalmente, es válido preguntarse cómo un SIEM y las técnicas de administración de sistemas
pueden reforzar la seguridad y monitorización de ADS-B, dado que el protocolo en sí no puede
cambiarse fácilmente en el corto plazo. Varias mejoras son factibles:


      • Correlación multi-fuente de datos de vigilancia: Un SIEM permite correlacionar eventos de
       distintas fuentes. Aplicado a ADS-B, se puede comparar la información de múltiples receptores y
       de otros sistemas (radares secundarios, multilateración MLAT, planes de vuelo, etc.). Si solo una
       estación reporta un avión X pero las demás no lo “ven”, el SIEM podría marcar ese objetivo como
       sospechoso de ser un fantasma. De igual modo, si ADS-B indica algo discrepante con el radar
       (por ejemplo, un avión que ADS-B sitúa a 3000 m de altitud pero el radar lo tiene a 9000 m), una
       regla de correlación podría generar una alerta de integridad. Esta fusión de datos mejora la
       confiabilidad de la vigilancia: esencialmente, el SIEM actúa como un filtro inteligente que cruza
       fuentes para detectar incoherencias.


      • Reglas de detección de comportamiento anómalo: Inspirándose en cómo se configuran SIEM
       para IT, se pueden crear reglas de uso aceptable para el tráfico ADS-B. Por ejemplo: “Si una
       aeronave excede cierta velocidad o razón de ascenso, alertar”; “Si aparece un nuevo código ICAO que
       no estaba previsto (según plan de vuelo o lista blanca), alertar”; “Si dos objetos comparten el mismo
       identificador al mismo tiempo, alertar”. Estas reglas, implementadas en Elastic Security u otro
       SIEM, funcionarían en tiempo real sobre los datos ingestados. Algunas pueden apoyarse en
       listas externas (por ejemplo, cargar al SIEM la base de datos de códigos asignados a aerolíneas,
       para detectar uno que no corresponda a la región). Otras pueden ser puramente estadísticas
       (detectar valores fuera de rangos típicos, como altitud < 0, velocidad > X, posición que salta > Y
       km en un segundo, etc.). En esencia, el SIEM haría las veces de un IDS (Intrusion Detection
       System) adaptado a la señal ADS-B, identificando patrones sospechosos de interferencia o fallo.


      • Alertas en tiempo real y respuesta más rápida: La centralización de logs en un SIEM con
       alertas automatizadas permitiría a los administradores recibir notificaciones inmediatas (por
       email, dashboard, etc.) cuando ocurre algo anómalo en el espacio aéreo monitoreado.
       Actualmente, muchas irregularidades ADS-B podrían pasar desapercibidas hasta que causan un
       problema operacional. Con un SIEM, en cambio, se podría notificar al instante al personal de
       seguridad o al centro de control. Por ejemplo, ante un ataque de ghost aircraft flooding, el SIEM




                                                     6
       podría detectar la creación de, digamos, 50 nuevos contactos en un minuto e inmediatamente
       alertar de un posible sabotaje, permitiendo activar protocolos de mitigación antes de que la
       situación escale. Esto mejora la postura de seguridad al pasar de un esquema reactivo (donde
       se investiga tras un incidente) a uno más proactivo/preventivo.


     • Consolidación de registros para forense: Un beneficio clásico de SIEM es guardar los eventos
       históricamente para análisis forense. En aviación, esto se traduce en tener un histórico
       centralizado de todos los datos ADS-B y eventos correlacionados. Si ocurre un incidente (p.
       ej., se sospecha que alguien envió señales falsas durante cierto periodo), los datos almacenados
       en Elasticsearch permiten retroceder y consultar exactamente qué se recibió, de dónde (en
       términos de estación receptora), qué otras actividades concurrentes había, etc. Esto facilitaría
       enormemente la investigación post-incidente y la recopilación de evidencias. Adicionalmente,
       ayuda en la toma de estadísticas a largo plazo: por ejemplo, medir cuántas anomalías se
       detectan por mes, en qué zonas, a qué horas, si aumentan con el tiempo (indicador de
       amenazas crecientes), etc.


     • Seguridad de la infraestructura ADS-B en sí: Más allá del análisis de la señal, un enfoque
       integral de administración de sistemas debe considerar proteger los propios receptores ADS-B y
       sistemas de distribución de datos. Muchos receptores son básicamente mini-PC (Raspberry Pi,
       etc.) conectados a internet para compartir datos con redes como Flightradar24. Estos nodos
       pueden ser blanco de ataques para falsear datos en origen. Incluirlos en el ámbito del SIEM
       permite también monitorizar su estado y accesos. Por ejemplo, enviando al SIEM los logs del
       sistema operativo de los receptores, se podría detectar intentos de intrusión, cambios de
       configuración no autorizados o caídas de servicio. Un administrador podría configurar alertas si
       un receptor se desconecta abruptamente (posible señal de sabotaje físico) o si empieza a enviar
       datos con un formato inesperado (posible comprometimiento del software). Integrar estos
       aspectos de seguridad de sistemas junto con los datos ADS-B propiamente dichos, brinda una
       visión completa de la superficie de ataque y fortalece la resiliencia del conjunto.


     • Hacia un ADS-B más seguro: Si bien un SIEM ayuda a detectar problemas, también se buscan
       soluciones para prevenirlos. En este sentido, los hallazgos del monitoreo podrían retroalimentar
       mejoras en procedimientos y tecnología. Por ejemplo, si el SIEM muestra que cierta zona es
       propensa a recepción de señales inválidas, las autoridades podrían aumentar la vigilancia
       radioeléctrica allí o recalibrar filtros en los receptores. A nivel de protocolos, existen propuestas
       en estudio para añadir autenticación a ADS-B (mediante firmas digitales, por ejemplo), o para
       complementar sus datos con redes alternativas cifradas (como utilizar enlaces satelitales
       seguros para verificar posiciones). Mientras esas soluciones de próxima generación llegan, un
       SIEM actúa como capa de mitigación detectando cualquier uso indebido del protocolo actual.
       Además, sensibiliza a los operadores sobre las vulnerabilidades activas, fomentando prácticas de
  “defensa en profundidad”: no confiar en una sola fuente de datos, segmentar las redes ADS-B

## Estructura de código modular (refactor 2025-10)

Se ha refactorizado el script monolítico en un paquete Python modular sin cambiar la funcionalidad ni la interfaz CLI. El archivo `adsb_textual_atc.py` sigue funcionando como lanzador para mantener compatibilidad.

Nueva estructura:

- `adsb_atc/` paquete con módulos:
  - `__init__.py`: expone `main` y versión.
  - `cli.py`: parseo de argumentos y punto de entrada.
  - `app.py`: lógica de la aplicación Textual (TUI) y simulación.
  - `model.py`: modelo de vuelo y física simplificada.
  - `exporters.py`: exportadores (`JsonlExporter`, plantilla Elastic) y config.
  - `anomalies.py`: catálogo de inyecciones de anomalías.
  - `utils.py`: utilidades comunes (tiempo, geografía, constantes mapa).
  - `ui_widgets.py` y `ui_components.py`: widgets y componentes de UI.

- `adsb_textual_atc.py`: wrapper que llama a `adsb_atc.cli:main`.

Requisitos:

Ver `requirements.txt` para instalar dependencias:

```powershell
python -m pip install -r requirements.txt
```

Uso (sin cambios):

```powershell
python adsb_textual_atc.py -o adsb_stream.jsonl -n 25 -r 10 -d 300 -A alt_neg,speed_impossible,dup_icao,teleport
```

También se puede invocar el paquete directamente:

```powershell
python -m adsb_atc -o adsb_stream.jsonl -n 25 -r 10
```

Notas de compatibilidad:

- No se ha alterado la semántica de generación de eventos ni los campos JSONL.
- La integración con Elastic sigue siendo una plantilla (sin llamadas de red).

       del resto de sistemas, mantener actualizado el software de los receptores, etc.


Para un estudiante llevando a cabo este proyecto, muchas de estas mejoras son asequibles de
demostrar en pequeño escala. Por ejemplo, se pueden implementar varias reglas de correlación en
Elastic Stack para identificar las anomalías simuladas (como las listadas arriba) y comprobar su eficacia.
Usando Docker en Linux, es relativamente fácil desplegar un entorno de Elastic Stack aislado donde el
estudiante tenga control total. Las pruebas con datos simulados confirmarán qué tan bien las alertas
funcionan y qué ajustes requieren (p. ej., umbrales, excepciones para evitar falsos positivos). Esto no
solo refuerza la seguridad del experimento, sino que brinda feedback inmediato para afinar la
configuración del SIEM tal como lo haría un administrador en producción.




                                                     7
Conclusiones
En conclusión, el Elastic Stack ofrece un marco versátil para centralizar y analizar datos de ADS-B
desde la óptica de la ciberseguridad. A través de esta investigación hemos visto que: (1) En el estado del
arte, las soluciones SIEM ya están encontrando espacio en la aviación y sectores críticos, con Elastic
siendo utilizado para monitoreo de datos masivos y detección de anomalías en tiempo real  5   6 . (2)

ADS-B, a pesar de sus ventajas operativas, presenta graves vulnerabilidades (transmisión abierta sin
autenticación) que permiten interferencias maliciosas como spoofing y DoS 9 15 . (3) Un SIEM como

Elastic puede desplegarse para correlacionar logs de múltiples fuentes aeronáuticas y alertar sobre
comportamientos atípicos, complementando así la vigilancia tradicional 2. (4) Existen ya proyectos e
investigaciones prácticas que ingieren datos de vuelos en Elastic, demostrando la viabilidad técnica de
esta integración 21. (5) Es posible generar datos ADS-B simulados con anomalías (altitudes negativas,
velocidades irreales, duplicación de identificadores, etc.) mediante scripts en Python u otras
herramientas, lo cual permite probar nuestras reglas de detección en un entorno controlado. (6) Un
SIEM ayuda a reforzar la seguridad de ADS-B al proporcionar alertas en tiempo real, análisis forense y
correlación multi-fuente, mitigando en parte la falta de seguridad del protocolo.


Para un trabajo de estudiante, todos estos hallazgos se pueden materializar con herramientas
asequibles: por ejemplo, montando Elastic Stack en contenedores Docker sobre Linux (como se
recomienda) y desarrollando scripts sencillos para alimentar datos simulados. La complejidad técnica es
manejable ya que no se requiere implementar algoritmos nuevos, sino configurar componentes
existentes y reglas lógicas sobre ellos, lo que encaja con el enfoque de administración de sistemas
más que de ingeniería pura. En definitiva, el proyecto de implementar un SIEM con Elastic para
centralizar y analizar datos ADS-B ofrece un aporte original y práctico: combina la gestión de sistemas
(despliegue, configuración, monitoreo de una plataforma) con un caso de uso de seguridad aeronáutica
innovador, aportando lecciones tanto en el plano técnico como en la concienciación sobre
ciberseguridad en la aviación.


Referencias:


     • Mavleos, B. & Hodac, O. (2023). Flightwatching ayuda a las empresas de transporte a reducir las
       emisiones de CO2... con Elastic. Elastic Blog 4 .
     • La Roche, A. & Beeching, B. (2025). Elasticsearch in the aviation industry: A game-changer for data
       management. Elastic Blog 6 .
     • Segurilatam (2017). Ciberseguridad en aeropuertos y compañías de aviación civil 13 17 .
     • Pérez Benítez, J. I. (2019). Ciberdefensa aeroespacial. Revista Seguridad, Ciencia y Defensa, Nº 5
         9   15    .
                  19

     • Controladores Aéreos (2024). ADS-B: La Revolución en la Vigilancia del Tráfico Aéreo en España 11 .
     • Scitepress (2025). A Conceptual SOC Framework for Air Traffic Management Systems. Proceedings of
       ICISSP 2025 2 1 .
     • Kosho (2018). Flight Track – ADS-B Signal Visualization with Elastic Stack. GitHub 22 21 .
     • Gilbert,
        16      G. (2017). FAA Cautions about Transponder and ADS-B Testing. Aviation International Ne
