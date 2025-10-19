#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Oct  9 11:19:22 2025

@author: emiliano
"""
import polars as pl
import requests
import pdfplumber
import re
from io import BytesIO
import time
from pathlib import Path
import hashlib
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

# Configuración de directorios
DIRECTORIO_PDFS = Path("declaraciones_pdfs")
DIRECTORIO_METADATOS = Path("declaraciones_metadatos")
DIRECTORIO_RESULTADOS = Path("resultados")

# Crear directorios si no existen
DIRECTORIO_PDFS.mkdir(exist_ok=True)
DIRECTORIO_METADATOS.mkdir(exist_ok=True)
DIRECTORIO_RESULTADOS.mkdir(exist_ok=True)


def generar_codigo_declaracion(nombre: str, apellido1: str, apellido2: str, url: str) -> str:
    """
    Genera un código único para identificar cada declaración.
    Formato: APELLIDO1_APELLIDO2_NOMBRE_HASH
    """
    # Limpiar y normalizar nombres
    nombre_limpio = re.sub(r'[^a-zA-Z]', '', nombre or '').upper()[:10]
    apellido1_limpio = re.sub(r'[^a-zA-Z]', '', apellido1 or '').upper()[:15]
    apellido2_limpio = re.sub(r'[^a-zA-Z]', '', apellido2 or '').upper()[:15]
    
    # Generar hash corto de la URL para unicidad
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8].upper()
    
    # Construir código
    codigo = f"{apellido1_limpio}_{apellido2_limpio}_{nombre_limpio}_{url_hash}"
    
    return codigo


def descargar_pdf(url: str, codigo: str) -> Optional[Path]:
    """
    Descarga un PDF desde una URL y lo guarda con un código específico.
    Retorna la ruta del archivo descargado o None si hay error.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        print(f"  → Descargando desde: {url[:80]}...")
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # Verificar el tipo de contenido
        content_type = response.headers.get('Content-Type', '').lower()
        print(f"  → Tipo de contenido: {content_type}")
        
        # Verificar si realmente es un PDF
        contenido = response.content
        
        # Los PDFs comienzan con %PDF
        if not contenido.startswith(b'%PDF'):
            print(f"  ✗ El contenido no es un PDF válido")
            print(f"  → Primeros 200 caracteres: {contenido[:200]}")
            
            # Si es HTML, podría ser una página de redirección
            if b'<html' in contenido.lower() or b'<!doctype' in contenido.lower():
                print(f"  ⚠ La URL devuelve HTML en lugar de PDF")
                # Intentar buscar un enlace real al PDF en el HTML
                contenido_str = contenido.decode('utf-8', errors='ignore')
                
                # Buscar patrones comunes de enlaces a PDF
                import re
                patrones = [
                    r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                    r'src=["\']([^"\']*\.pdf[^"\']*)["\']',
                    r'(https?://[^\s<>"]+?\.pdf)',
                ]
                
                for patron in patrones:
                    matches = re.findall(patron, contenido_str, re.IGNORECASE)
                    if matches:
                        pdf_url = matches[0]
                        print(f"  → Encontrado enlace a PDF: {pdf_url[:80]}...")
                        # Intentar descargar el PDF real
                        return descargar_pdf(pdf_url, codigo)
            
            return None
        
        # Guardar PDF
        ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
        ruta_pdf.write_bytes(contenido)
        
        print(f"  ✓ PDF guardado: {ruta_pdf} ({len(contenido)} bytes)")
        return ruta_pdf
        
    except Exception as e:
        print(f"  ✗ Error descargando: {str(e)}")
        return None


def extraer_texto_pdf(ruta_pdf: Path) -> Optional[str]:
    """
    Extrae todo el texto de un PDF.
    """
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto_completo = ""
            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() or ""
        
        return texto_completo
    
    except Exception as e:
        print(f"  ✗ Error extrayendo texto: {str(e)}")
        return None


def extraer_ingreso_anual_neto(texto: str) -> Optional[float]:
    """
    Busca y extrae el ingreso anual neto del texto del PDF.
    """
    if not texto:
        return None
    
    # Patrón 1: Buscar la línea específica
    patron1 = r'A\.\s*INGRESO ANUAL NETO DEL DECLARANTE.*?(\d[\d,]+)'
    match1 = re.search(patron1, texto, re.IGNORECASE | re.DOTALL)
    
    if match1:
        monto = match1.group(1).replace(',', '')
        return float(monto)
    
    # Patrón 2: Buscar en formato de tabla
    patron2 = r'INGRESO ANUAL NETO.*?NUMERAL I Y II\)?\s*(\d[\d,]+)'
    match2 = re.search(patron2, texto, re.IGNORECASE | re.DOTALL)
    
    if match2:
        monto = match2.group(1).replace(',', '')
        return float(monto)
    
    return None


def extraer_datos_adicionales(texto: str) -> Dict:
    """
    Extrae información adicional del PDF para análisis futuro.
    """
    datos = {
        'remuneracion_cargo_publico': None,
        'otros_ingresos': None,
        'actividad_financiera': None,
        'servicios_profesionales': None,
        'fecha_recepcion': None,
        'cargo': None,
        'institucion': None,
    }
    
    # Extraer remuneración por cargo público
    patron_remuneracion = r'REMUNERACIÓN ANUAL NETA.*?PRESTACIONES.*?(\d[\d,]+)'
    match = re.search(patron_remuneracion, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['remuneracion_cargo_publico'] = float(match.group(1).replace(',', ''))
    
    # Extraer otros ingresos
    patron_otros = r'II\.\s*OTROS INGRESOS.*?II\.1 AL II\.5\)\s*(\d[\d,]+)'
    match = re.search(patron_otros, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['otros_ingresos'] = float(match.group(1).replace(',', ''))
    
    # Extraer actividad financiera
    patron_financiera = r'II\.2.*?ACTIVIDAD FINANCIERA.*?IMPUESTOS\)\s*(\d[\d,]+)'
    match = re.search(patron_financiera, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['actividad_financiera'] = float(match.group(1).replace(',', ''))
    
    # Extraer servicios profesionales
    patron_servicios = r'II\.3.*?SERVICIOS PROFESIONALES.*?IMPUESTOS\)\s*(\d[\d,]+)'
    match = re.search(patron_servicios, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['servicios_profesionales'] = float(match.group(1).replace(',', ''))
    
    # Extraer fecha de recepción
    patron_fecha = r'FECHA DE RECEPCIÓN:\s*(\d{2}/\d{2}/\d{4})'
    match = re.search(patron_fecha, texto)
    if match:
        datos['fecha_recepcion'] = match.group(1)
    
    # Extraer cargo
    patron_cargo = r'EMPLEO, CARGO O COMISIÓN\s+([A-ZÁÉÍÓÚÑ\s]+?)(?=\s*DOCENCIA|ESPECIFIQUE|NIVEL)'
    match = re.search(patron_cargo, texto, re.IGNORECASE)
    if match:
        datos['cargo'] = match.group(1).strip()
    
    # Extraer institución
    patron_institucion = r'NOMBRE DEL ENTE PÚBLICO\s+([A-ZÁÉÍÓÚÑ,.\s]+?)(?=\s*ÁREA|EMPLEO|NIVEL)'
    match = re.search(patron_institucion, texto, re.IGNORECASE)
    if match:
        datos['institucion'] = match.group(1).strip()
    
    return datos


def guardar_metadatos(codigo: str, datos_completos: Dict):
    """
    Guarda metadatos completos de la declaración en formato JSON.
    """
    ruta_metadatos = DIRECTORIO_METADATOS / f"{codigo}.json"
    
    # Agregar timestamp
    datos_completos['timestamp_procesamiento'] = datetime.now().isoformat()
    
    with open(ruta_metadatos, 'w', encoding='utf-8') as f:
        json.dump(datos_completos, f, indent=2, ensure_ascii=False)
    
    print(f"  ✓ Metadatos guardados: {ruta_metadatos}")


def procesar_declaracion(row: Dict) -> Dict:
    """
    Procesa una declaración completa: descarga, extrae datos y guarda metadatos.
    """
    url = row.get('url', '')
    nombre = row.get('nombre', '')
    apellido1 = row.get('primer_apellido', '')
    apellido2 = row.get('segundo_apellido', '')
    
    # Generar código único
    codigo = generar_codigo_declaracion(nombre, apellido1, apellido2, url)
    
    print(f"\n{'='*60}")
    print(f"Procesando: {apellido1} {apellido2} {nombre}")
    print(f"Código: {codigo}")
    print(f"{'='*60}")
    
    resultado = {
        'codigo_declaracion': codigo,
        'url': url,
        'nombre': nombre,
        'primer_apellido': apellido1,
        'segundo_apellido': apellido2,
        'ingreso_anual_neto': None,
        'pdf_descargado': False,
        'datos_extraidos': False,
        'ruta_pdf': None,
        'error': None,
    }
    
    # Verificar si ya existe el PDF
    ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
    if ruta_pdf.exists():
        print(f"  ℹ PDF ya existe, usando versión local")
    else:
        # Descargar PDF
        ruta_pdf = descargar_pdf(url, codigo)
        if not ruta_pdf:
            resultado['error'] = 'Error al descargar PDF'
            return resultado
    
    resultado['pdf_descargado'] = True
    resultado['ruta_pdf'] = str(ruta_pdf)
    
    # Extraer texto
    texto = extraer_texto_pdf(ruta_pdf)
    if not texto:
        resultado['error'] = 'Error al extraer texto del PDF'
        return resultado
    
    # Extraer ingreso anual neto
    ingreso = extraer_ingreso_anual_neto(texto)
    resultado['ingreso_anual_neto'] = ingreso
    
    # Extraer datos adicionales
    datos_adicionales = extraer_datos_adicionales(texto)
    resultado.update(datos_adicionales)
    resultado['datos_extraidos'] = True
    
    # Guardar metadatos completos
    guardar_metadatos(codigo, resultado)
    
    print(f"  ✓ Ingreso anual neto: ${ingreso:,.2f}" if ingreso else "  ⚠ Ingreso no encontrado")
    
    return resultado


def leer_excel(ruta_excel: str, skiprows: int = 5) -> pl.DataFrame:
    """
    Lee el archivo Excel saltando las filas de metadatos iniciales.
    
    Args:
        ruta_excel: Ruta al archivo Excel
        skiprows: Número de filas a saltar (default: 5 para archivos del portal de transparencia)
    """
    print(f"Leyendo archivo: {ruta_excel}")
    print(f"Saltando primeras {skiprows} filas de metadatos...")
    
    # Usar pandas para leer Excel
    import pandas as pd
    
    # Leer saltando las primeras filas de metadatos
    df_pandas = pd.read_excel(ruta_excel, skiprows=skiprows)
    
    # Limpiar nombres de columnas (eliminar espacios extra)
    df_pandas.columns = [str(col).strip() for col in df_pandas.columns]
    
    # Eliminar filas completamente vacías
    df_pandas = df_pandas.dropna(how='all')
    
    # Convertir tipos de datos problemáticos a tipos simples
    for col in df_pandas.columns:
        # Convertir Int64 (nullable integer) a float64 o int64 simple
        if pd.api.types.is_integer_dtype(df_pandas[col]):
            if df_pandas[col].isna().any():
                df_pandas[col] = df_pandas[col].astype('float64')
            else:
                df_pandas[col] = df_pandas[col].astype('int64')
        # Convertir datetime con timezone a datetime sin timezone
        elif pd.api.types.is_datetime64_any_dtype(df_pandas[col]):
            if hasattr(df_pandas[col].dtype, 'tz') and df_pandas[col].dtype.tz is not None:
                df_pandas[col] = df_pandas[col].dt.tz_localize(None)
    
    # Intentar convertir a Polars
    try:
        df = pl.from_pandas(df_pandas)
    except ImportError as e:
        print(f"\n⚠ Error al convertir a Polars: {e}")
        print("⚠ Continuando con Pandas (instala pyarrow: pip install pyarrow)")
        # Si falla, usar el DataFrame de pandas directamente
        # Necesitamos adaptar el resto del código para usar pandas
        return df_pandas
    
    print(f"✓ Registros encontrados: {len(df)}")
    print(f"\n✓ Columnas encontradas:")
    
    # Manejar tanto Polars como Pandas
    if isinstance(df, pl.DataFrame):
        for i, col in enumerate(df.columns, 1):
            tipo_dato = df[col].dtype
            no_nulos = df[col].null_count()
            print(f"  {i:2d}. {col[:60]:<60} | {tipo_dato} | {len(df) - no_nulos} valores")
    else:
        for i, col in enumerate(df.columns, 1):
            tipo_dato = df[col].dtype
            no_nulos = df[col].notna().sum()
            print(f"  {i:2d}. {col[:60]:<60} | {tipo_dato} | {no_nulos} valores")
    
    return df


def procesar_todas_declaraciones(df, 
                                 columna_url: str,
                                 limite: Optional[int] = None):
    """
    Procesa todas las declaraciones del DataFrame.
    Funciona tanto con Polars como con Pandas.
    """
    resultados = []
    
    # Detectar si es Polars o Pandas
    es_polars = isinstance(df, pl.DataFrame)
    
    # Obtener columnas
    columnas = df.columns
    
    # Buscar la columna de URL (puede tener nombres diferentes)
    columnas_posibles = [col for col in columnas if 'hipervínculo' in col.lower() or 'url' in col.lower() or 'versión pública' in col.lower()]
    
    if not columnas_posibles:
        print(f"\n✗ No se encontró columna de URL. Columnas disponibles:")
        for col in columnas:
            print(f"  - {col}")
        return pl.DataFrame() if es_polars else None
    
    # Usar la primera columna que contenga URLs
    columna_url_real = columnas_posibles[0] if columna_url not in columnas else columna_url
    print(f"\n✓ Usando columna: {columna_url_real}")
    
    # Buscar columnas de nombres
    col_nombre = next((col for col in columnas if 'nombre' in col.lower() and 'apellido' not in col.lower()), None)
    col_apellido1 = next((col for col in columnas if 'primer' in col.lower() and 'apellido' in col.lower()), None)
    col_apellido2 = next((col for col in columnas if 'segundo' in col.lower() and 'apellido' in col.lower()), None)
    
    print(f"✓ Columna nombre: {col_nombre}")
    print(f"✓ Columna primer apellido: {col_apellido1}")
    print(f"✓ Columna segundo apellido: {col_apellido2}")
    
    # Convertir a diccionarios para iterar
    if es_polars:
        registros = df.to_dicts()
    else:
        registros = df.to_dict('records')
    
    if limite:
        registros = registros[:limite]
        print(f"\n⚠ Procesando solo {limite} registros (modo prueba)")
    
    total = len(registros)
    
    for idx, row in enumerate(registros, 1):
        url = row.get(columna_url_real)
        
        # Preparar datos del row con nombres genéricos
        row_procesado = {
            'url': url,
            'nombre': row.get(col_nombre, '') if col_nombre else '',
            'primer_apellido': row.get(col_apellido1, '') if col_apellido1 else '',
            'segundo_apellido': row.get(col_apellido2, '') if col_apellido2 else '',
        }
        
        if url and isinstance(url, str) and url.startswith('http'):
            print(f"\n[{idx}/{total}]")
            
            resultado = procesar_declaracion(row_procesado)
            resultados.append(resultado)
            
            # Pausa entre peticiones
            if idx < total:
                time.sleep(2)
        else:
            print(f"\n[{idx}/{total}] ✗ URL no válida, saltando...")
    
    # Si no hay resultados, retornar DataFrame vacío con estructura
    if not resultados:
        print("\n⚠ No se procesaron registros")
        estructura_vacia = {
            'codigo_declaracion': [],
            'url': [],
            'nombre': [],
            'primer_apellido': [],
            'segundo_apellido': [],
            'ingreso_anual_neto': [],
            'pdf_descargado': [],
            'datos_extraidos': [],
            'ruta_pdf': [],
            'error': [],
        }
        return pl.DataFrame(estructura_vacia) if es_polars else None
    
    # Retornar en el formato apropiado
    if es_polars:
        return pl.DataFrame(resultados)
    else:
        import pandas as pd
        return pd.DataFrame(resultados)


def guardar_resultados(df_resultados):
    """
    Guarda los resultados en múltiples formatos.
    Funciona con Polars o Pandas.
    """
    if df_resultados is None or len(df_resultados) == 0:
        print("\n⚠ No hay resultados para guardar")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    es_polars = isinstance(df_resultados, pl.DataFrame)
    
    # CSV (compatible con ambos)
    ruta_csv = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.csv"
    if es_polars:
        df_resultados.write_csv(ruta_csv)
    else:
        df_resultados.to_csv(ruta_csv, index=False)
    print(f"\n✓ Resultados guardados: {ruta_csv}")
    
    # Parquet (más eficiente para grandes volúmenes)
    try:
        ruta_parquet = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.parquet"
        if es_polars:
            df_resultados.write_parquet(ruta_parquet)
        else:
            df_resultados.to_parquet(ruta_parquet, index=False)
        print(f"✓ Resultados guardados: {ruta_parquet}")
    except Exception as e:
        print(f"⚠ No se pudo guardar Parquet: {e}")
    
    # Excel
    try:
        ruta_excel = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.xlsx"
        if es_polars:
            df_resultados.write_excel(ruta_excel)
        else:
            df_resultados.to_excel(ruta_excel, index=False)
        print(f"✓ Resultados guardados: {ruta_excel}")
    except Exception as e:
        print(f"⚠ No se pudo guardar Excel: {e}")


def mostrar_estadisticas(df_resultados):
    """
    Muestra estadísticas de los resultados.
    Funciona con Polars o Pandas.
    """
    print("\n" + "="*60)
    print("ESTADÍSTICAS GENERALES")
    print("="*60)
    
    # Verificar que el DataFrame no esté vacío
    if df_resultados is None or len(df_resultados) == 0:
        print("⚠ No hay resultados para mostrar estadísticas")
        return
    
    es_polars = isinstance(df_resultados, pl.DataFrame)
    
    # Verificar que las columnas existan
    columnas_requeridas = ['datos_extraidos', 'pdf_descargado', 'ingreso_anual_neto']
    columnas_disponibles = df_resultados.columns if es_polars else df_resultados.columns.tolist()
    columnas_faltantes = [col for col in columnas_requeridas if col not in columnas_disponibles]
    
    if columnas_faltantes:
        print(f"⚠ Columnas faltantes: {columnas_faltantes}")
        print(f"Columnas disponibles: {columnas_disponibles}")
        return
    
    total = len(df_resultados)
    
    if es_polars:
        exitosos = df_resultados.filter(pl.col('datos_extraidos') == True).height
        pdfs_descargados = df_resultados.filter(pl.col('pdf_descargado') == True).height
        con_ingreso = df_resultados.filter(pl.col('ingreso_anual_neto').is_not_null()).height
    else:
        exitosos = (df_resultados['datos_extraidos'] == True).sum()
        pdfs_descargados = (df_resultados['pdf_descargado'] == True).sum()
        con_ingreso = df_resultados['ingreso_anual_neto'].notna().sum()
    
    print(f"Total de registros procesados: {total}")
    print(f"PDFs descargados exitosamente: {pdfs_descargados}")
    print(f"Datos extraídos exitosamente: {exitosos}")
    print(f"Ingresos encontrados: {con_ingreso}")
    
    if con_ingreso > 0:
        if es_polars:
            ingresos = df_resultados.filter(pl.col('ingreso_anual_neto').is_not_null())
            promedio = ingresos['ingreso_anual_neto'].mean()
            mediana = ingresos['ingreso_anual_neto'].median()
            minimo = ingresos['ingreso_anual_neto'].min()
            maximo = ingresos['ingreso_anual_neto'].max()
        else:
            ingresos = df_resultados[df_resultados['ingreso_anual_neto'].notna()]
            promedio = ingresos['ingreso_anual_neto'].mean()
            mediana = ingresos['ingreso_anual_neto'].median()
            minimo = ingresos['ingreso_anual_neto'].min()
            maximo = ingresos['ingreso_anual_neto'].max()
        
        print(f"\nPromedio de ingresos: ${promedio:,.2f}")
        print(f"Mediana de ingresos: ${mediana:,.2f}")
        print(f"Ingreso mínimo: ${minimo:,.2f}")
        print(f"Ingreso máximo: ${maximo:,.2f}")
    
    print("\n" + "="*60)


# Función principal
def main(ruta_excel: str, 
         columna_url: str = 'Hipervínculo a La Versión Pública de La Declaración de Situación Patrimonial, O a La Versión Pública de Los Sistemas Habilitados Que Registren Y Resguarden en Las Bases de Datos Correspondientes',
         limite: Optional[int] = None):
    """
    Función principal para ejecutar el scraping.
    
    Args:
        ruta_excel: Ruta al archivo Excel con las URLs
        columna_url: Nombre de la columna con las URLs
        limite: Número máximo de registros a procesar (None para todos)
    """
    print("\n" + "="*60)
    print("INICIANDO WEB SCRAPING DE DECLARACIONES PATRIMONIALES")
    print("="*60 + "\n")
    
    # Leer Excel
    df = leer_excel(ruta_excel)
    
    # Mostrar muestra de datos para verificar
    print("\n📊 Muestra de datos (primeras 3 filas):")
    print(df.head(3))
    
    # Procesar declaraciones
    df_resultados = procesar_todas_declaraciones(df, columna_url, limite)
    
    # Guardar resultados
    guardar_resultados(df_resultados)
    
    # Mostrar estadísticas
    mostrar_estadisticas(df_resultados)
    
    print("\n✓ Proceso completado")
    print(f"  - PDFs guardados en: {DIRECTORIO_PDFS}")
    print(f"  - Metadatos guardados en: {DIRECTORIO_METADATOS}")
    print(f"  - Resultados guardados en: {DIRECTORIO_RESULTADOS}")


def inspeccionar_url(url: str):
    """
    Inspecciona una URL para ver qué tipo de contenido devuelve.
    Útil para debugging.
    """
    print("\n" + "="*60)
    print("INSPECCIÓN DE URL")
    print("="*60)
    print(f"\n🔗 URL: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        print(f"\n✓ Status code: {response.status_code}")
        print(f"✓ Content-Type: {response.headers.get('Content-Type', 'No especificado')}")
        print(f"✓ Content-Length: {len(response.content)} bytes")
        
        # Verificar si hay redirecciones
        if response.history:
            print(f"\n📍 Redirecciones detectadas:")
            for i, redir in enumerate(response.history, 1):
                print(f"  {i}. {redir.status_code} -> {redir.url[:80]}...")
            print(f"  Final: {response.url[:80]}...")
        
        # Verificar tipo de contenido
        contenido = response.content
        
        if contenido.startswith(b'%PDF'):
            print(f"\n✓ Es un PDF válido")
            # Extraer versión del PDF
            version = contenido[:10].decode('latin-1', errors='ignore')
            print(f"  Versión: {version}")
        elif b'<html' in contenido.lower()[:500] or b'<!doctype' in contenido.lower()[:500]:
            print(f"\n⚠ Es una página HTML")
            contenido_str = contenido.decode('utf-8', errors='ignore')
            print(f"\n📄 Primeros 500 caracteres del HTML:")
            print(contenido_str[:500])
            
            # Buscar enlaces a PDF
            import re
            patrones = [
                r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                r'src=["\']([^"\']*\.pdf[^"\']*)["\']',
                r'(https?://[^\s<>"]+?\.pdf)',
            ]
            
            print(f"\n🔍 Buscando enlaces a PDF en el HTML...")
            for patron in patrones:
                matches = re.findall(patron, contenido_str, re.IGNORECASE)
                if matches:
                    print(f"\n✓ Enlaces encontrados con patrón '{patron}':")
                    for match in matches[:5]:  # Mostrar máximo 5
                        print(f"  - {match[:120]}")
        else:
            print(f"\n⚠ Tipo de contenido desconocido")
            print(f"📄 Primeros 200 bytes:")
            print(contenido[:200])
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
    
    print("\n" + "="*60)
    """
    Función auxiliar para inspeccionar la estructura del Excel.
    Útil para identificar qué columnas contienen las URLs y los nombres.
    
    Args:
        skiprows: Número de filas a saltar (default: 5)
    """
    import pandas as pd
    
    print("\n" + "="*60)
    print("INSPECCIÓN DEL ARCHIVO EXCEL")
    print("="*60 + "\n")
    
    # Primero mostrar las primeras filas sin saltar
    print("🔍 Primeras 5 filas del archivo (sin saltar):")
    df_raw = pd.read_excel(ruta_excel, nrows=5)
    print(df_raw)
    
    print("\n" + "-"*60)
    print(f"\n🔍 Ahora leyendo con skiprows={skiprows}:")
    
    # Leer saltando filas
    df = pd.read_excel(ruta_excel, skiprows=skiprows)
    
    print(f"\n📁 Archivo: {ruta_excel}")
    print(f"📊 Dimensiones: {df.shape[0]} filas x {df.shape[1]} columnas")
    print(f"\n📋 Columnas encontradas:")
    for i, col in enumerate(df.columns, 1):
        # Contar valores no nulos
        no_nulos = df[col].notna().sum()
        print(f"  {i:2d}. {col[:70]:<70} | {no_nulos} valores")
    
    print(f"\n🔍 Primeras 3 filas de datos:")
    print(df.head(3))
    
    print(f"\n🔍 Buscando URLs en las columnas...")
    urls_encontradas = False
    for col in df.columns:
        # Buscar celdas que contengan URLs
        urls = df[col].astype(str).str.contains('http', case=False, na=False)
        if urls.any():
            urls_encontradas = True
            print(f"\n  ✓ Columna '{col}'")
            print(f"    - Contiene {urls.sum()} URLs")
            print(f"    - Ejemplo: {df[col][urls].iloc[0][:120]}...")
    
    if not urls_encontradas:
        print("  ⚠ No se encontraron URLs en ninguna columna")
    
    return df


if __name__ == "__main__":
    # PASO 1: Primero inspeccionar el archivo para ver su estructura
    print("PASO 1: Inspeccionando el archivo Excel...")
    df_inspeccion = inspeccionar_excel('INFORMACION_49_708785.xls', skiprows=5)
    
    print("\n" + "="*60)
    input("Presiona ENTER para continuar con el scraping de prueba (5 registros)...")
    
    # PASO 2: Ejecutar el scraping con los primeros 5 registros
    main('INFORMACION_49_708785.xls', limite=5)
    
    # Para procesar todos los registros después de verificar que funciona:
    # main('INFORMACION_49_708785.xls')