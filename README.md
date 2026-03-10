## Webmet25 - Sistema de Visualización y Procesamiento de Datos Radar
Este repositorio contiene la implementación completa de un sistema de visualización web y procesamiento de datos radar utilizando contenedores Docker. El proyecto está compuesto por tres servicios principales:

### Servicios Incluidos
* webmet25: Aplicación web desarrollada en Django que proporciona una interfaz de visualización con mapas interactivos (estilo Google Maps) donde se muestran los productos generados por el radar como capas superpuestas.

* genpro25: Servicio de procesamiento de datos radar que utiliza el módulo radarlib para ejecutar un gestor de daemons que procesa archivos BUFR, genera productos NetCDF y crea imágenes de radar. Los productos se almacenan en un directorio compartido.

* PostgreSQL: Base de datos relacional que almacena la información de estado del procesamiento radar y metadatos de los productos generados.

### Arquitectura
* Docker Compose: Orquestación de servicios con volúmenes compartidos para productos radar
* Procesamiento Asíncrono: Pipeline de daemons para descarga, procesamiento y generación de productos
* Visualización Web: Mapas interactivos con capas de productos radar en tiempo real
* Almacenamiento Compartido: Directorio compartido para productos entre servicios de procesamiento y web

### Características Principales
* Procesamiento automatizado de datos BUFR a productos visuales
* Visualización geográfica de datos radar en mapas web
* Arquitectura modular con servicios independientes
* Configuración completa para despliegue en contenedores
* Seguimiento de estado y metadatos en base de datos PostgreSQL

### Requisitos
* Docker y Docker Compose
* Conexión a servidor FTP para descarga de datos BUFR
* Configuración de radar específica (archivos de configuración incluidos)

Este repositorio proporciona una solución completa para el procesamiento y visualización de datos meteorológicos radar en un entorno contenerizado y escalable.
