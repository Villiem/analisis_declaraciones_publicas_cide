#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Scraper de Declaraciones Patrimoniales
Versión para Spyder con celdas separadas
"""

# %% CELDA 1: Importar librerías
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
from bs4 import BeautifulSoup

print("✓ Librerías importadas correctamente")

# %% CELDA 2: Configuración de directorios
DIRECTORIO_PDFS = Path("declaraciones_pdfs")
DIRECTORIO_METADATOS = Path("declaraciones_metadatos")
DIRECTORIO_RESULTADOS = Path("resultados")

# Crear directorios si no existen
DIRECTORIO_PDFS.mkdir(exist_ok=True)
DIRECTORIO_METADATOS.mkdir(exist_ok=True)
DIRECTORIO_RESULTADOS.mkdir(exist_ok=True)

print("✓ Directorios configurados:")
print(f"  - PDFs: {DIRECTORIO_PDFS}")
print(f"  - Metadatos: {DIRECTORIO_METADATOS}")
print(f"  - Resultados: {DIRECTORIO_RESULTADOS}")

# %% CELDA 3: Función para generar código único de declaración
def generar_codigo_declaracion(nombre: str, apellido1: str, apellido2: str, url: str) -> str:
    """
    Genera un código único para identificar cada declaración.
    Formato: APELLIDO1_APELLIDO2_NOMBRE_HASH
    """
    nombre_limpio = re.sub(r'[^a-zA-Z]', '', nombre or '').upper()[:10]
    apellido1_limpio = re.sub(r'[^a-zA-Z]', '', apellido1 or '').upper()[:15]
    apellido2_limpio = re.sub(r'[^a-zA-Z]', '', apellido2 or '').upper()[:15]
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8].upper()
    codigo = f"{apellido1_limpio}_{apellido2_limpio}_{nombre_limpio}_{url_hash}"
    return codigo

print("✓ Función generar_codigo_declaracion definida")

# %% CELDA 4: Función para buscar enlace PDF en página HTML
def buscar_enlace_pdf_en_html(url: str, contenido_html: str) -> Optional[str]:
    """
    Busca el enlace directo al PDF dentro de una página HTML.
    Usa BeautifulSoup para un análisis más robusto.
    """
    try:
        soup = BeautifulSoup(contenido_html, 'html.parser')
        
        # Estrategia 1: Buscar enlaces <a> con href que termine en .pdf
        enlaces_a = soup.find_all('a', href=re.compile(r'\.pdf', re.IGNORECASE))
        if enlaces_a:
            href = enlaces_a[0].get('href')
            # Si es relativo, construir URL absoluta
            if href.startswith('http'):
                return href
            else:
                from urllib.parse import urljoin
                return urljoin(url, href)
        
        # Estrategia 2: Buscar en iframes
        iframes = soup.find_all('iframe', src=re.compile(r'\.pdf', re.IGNORECASE))
        if iframes:
            src = iframes[0].get('src')
            if src.startswith('http'):
                return src
            else:
                from urllib.parse import urljoin
                return urljoin(url, src)
        
        # Estrategia 3: Buscar botones o enlaces de descarga
        botones_descarga = soup.find_all(['a', 'button'], 
                                        text=re.compile(r'descargar|download|pdf', re.IGNORECASE))
        for boton in botones_descarga:
            href = boton.get('href') or boton.get('data-url') or boton.get('onclick')
            if href and '.pdf' in href.lower():
                if href.startswith('http'):
                    return href
                else:
                    from urllib.parse import urljoin
                    return urljoin(url, href)
        
        # Estrategia 4: Buscar en atributos data-*
        elementos_data = soup.find_all(attrs={'data-pdf': True})
        if elementos_data:
            return elementos_data[0].get('data-pdf')
        
        # Estrategia 5: Buscar patrones en el HTML crudo
        patrones = [
            r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
            r'src=["\']([^"\']*\.pdf[^"\']*)["\']',
            r'(https?://[^\s<>"]+?\.pdf)',
        ]
        
        for patron in patrones:
            matches = re.findall(patron, contenido_html, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None
        
    except Exception as e:
        print(f"  ⚠ Error buscando PDF en HTML: {str(e)}")
        return None

print("✓ Función buscar_enlace_pdf_en_html definida")

# %% CELDA 5: Función mejorada para descargar PDF
def descargar_pdf(url: str, codigo: str, max_intentos: int = 3) -> Optional[Path]:
    """
    Descarga un PDF desde una URL, manejando páginas intermedias.
    """
    for intento in range(max_intentos):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            if intento > 0:
                print(f"  → Intento {intento + 1}/{max_intentos}...")
            else:
                print(f"  → Descargando desde: {url[:80]}...")
            
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            contenido = response.content
            
            # Verificar si es un PDF directo
            if contenido.startswith(b'%PDF'):
                ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
                ruta_pdf.write_bytes(contenido)
                print(f"  ✓ PDF descargado: {ruta_pdf.name} ({len(contenido):,} bytes)")
                return ruta_pdf
            
            # Si no es PDF, debe ser HTML con enlace al PDF
            elif b'<html' in contenido.lower()[:1000] or b'<!doctype' in contenido.lower()[:1000]:
                print(f"  → Página HTML detectada, buscando enlace al PDF...")
                contenido_html = contenido.decode('utf-8', errors='ignore')
                
                # Buscar enlace al PDF en el HTML
                pdf_url = buscar_enlace_pdf_en_html(response.url, contenido_html)
                
                if pdf_url:
                    print(f"  → PDF encontrado: {pdf_url[:80]}...")
                    # Recursión con el enlace directo al PDF
                    return descargar_pdf(pdf_url, codigo, max_intentos=1)
                else:
                    print(f"  ✗ No se encontró enlace al PDF en la página")
                    # Guardar HTML para debug
                    ruta_debug = DIRECTORIO_PDFS / f"{codigo}_debug.html"
                    ruta_debug.write_text(contenido_html[:5000], encoding='utf-8')
                    print(f"  → HTML guardado para debug: {ruta_debug.name}")
                    return None
            else:
                print(f"  ✗ Contenido desconocido (no es PDF ni HTML)")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error de red: {str(e)}")
            if intento < max_intentos - 1:
                time.sleep(2)
            continue
        except Exception as e:
            print(f"  ✗ Error inesperado: {str(e)}")
            return None
    
    return None

print("✓ Función descargar_pdf definida")

# %% CELDA 6: Funciones para validar y extraer texto del PDF
def validar_pdf(ruta_pdf: Path) -> bool:
    """Valida si un archivo es realmente un PDF válido."""
    try:
        # Verificar que existe
        if not ruta_pdf.exists():
            return False
        
        # Verificar tamaño mínimo (PDFs vacíos son sospechosos)
        if ruta_pdf.stat().st_size < 1024:  # Menos de 1KB
            print(f"  ⚠ Archivo muy pequeño: {ruta_pdf.stat().st_size} bytes")
            return False
        
        # Verificar que comienza con %PDF
        with open(ruta_pdf, 'rb') as f:
            header = f.read(4)
            if not header.startswith(b'%PDF'):
                print(f"  ✗ No tiene encabezado PDF válido: {header}")
                return False
        
        # Intentar abrir con pdfplumber
        with pdfplumber.open(ruta_pdf) as pdf:
            if len(pdf.pages) == 0:
                print(f"  ✗ PDF sin páginas")
                return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error validando PDF: {str(e)}")
        return False


def extraer_texto_pdf(ruta_pdf: Path) -> Optional[str]:
    """Extrae todo el texto de un PDF."""
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto_completo = ""
            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() or ""
        return texto_completo
    except Exception as e:
        print(f"  ✗ Error extrayendo texto: {str(e)}")
        return None

print("✓ Funciones validar_pdf y extraer_texto_pdf definidas")

# %% CELDA 7: Función para extraer ingreso anual neto
def extraer_ingreso_anual_neto(texto: str) -> Optional[float]:
    """Busca y extrae el ingreso anual neto del texto del PDF."""
    if not texto:
        return None
    
    # Patrón 1: Línea específica
    patron1 = r'A\.\s*INGRESO ANUAL NETO DEL DECLARANTE.*?(\d[\d,]+)'
    match1 = re.search(patron1, texto, re.IGNORECASE | re.DOTALL)
    if match1:
        monto = match1.group(1).replace(',', '')
        return float(monto)
    
    # Patrón 2: Formato de tabla
    patron2 = r'INGRESO ANUAL NETO.*?NUMERAL I Y II\)?\s*(\d[\d,]+)'
    match2 = re.search(patron2, texto, re.IGNORECASE | re.DOTALL)
    if match2:
        monto = match2.group(1).replace(',', '')
        return float(monto)
    
    return None

print("✓ Función extraer_ingreso_anual_neto definida")

# %% CELDA 8: Función para extraer datos adicionales
def extraer_datos_adicionales(texto: str) -> Dict:
    """Extrae información adicional del PDF."""
    datos = {
        'remuneracion_cargo_publico': None,
        'otros_ingresos': None,
        'actividad_financiera': None,
        'servicios_profesionales': None,
        'fecha_recepcion': None,
        'cargo': None,
        'institucion': None,
    }
    
    # Remuneración por cargo público
    patron = r'REMUNERACIÓN ANUAL NETA.*?PRESTACIONES.*?(\d[\d,]+)'
    match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['remuneracion_cargo_publico'] = float(match.group(1).replace(',', ''))
    
    # Otros ingresos
    patron = r'II\.\s*OTROS INGRESOS.*?II\.1 AL II\.5\)\s*(\d[\d,]+)'
    match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['otros_ingresos'] = float(match.group(1).replace(',', ''))
    
    # Actividad financiera
    patron = r'II\.2.*?ACTIVIDAD FINANCIERA.*?IMPUESTOS\)\s*(\d[\d,]+)'
    match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['actividad_financiera'] = float(match.group(1).replace(',', ''))
    
    # Servicios profesionales
    patron = r'II\.3.*?SERVICIOS PROFESIONALES.*?IMPUESTOS\)\s*(\d[\d,]+)'
    match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['servicios_profesionales'] = float(match.group(1).replace(',', ''))
    
    # Fecha de recepción
    patron = r'FECHA DE RECEPCIÓN:\s*(\d{2}/\d{2}/\d{4})'
    match = re.search(patron, texto)
    if match:
        datos['fecha_recepcion'] = match.group(1)
    
    # Cargo
    patron = r'EMPLEO, CARGO O COMISIÓN\s+([A-ZÁÉÍÓÚÑ\s]+?)(?=\s*DOCENCIA|ESPECIFIQUE|NIVEL)'
    match = re.search(patron, texto, re.IGNORECASE)
    if match:
        datos['cargo'] = match.group(1).strip()
    
    # Institución
    patron = r'NOMBRE DEL ENTE PÚBLICO\s+([A-ZÁÉÍÓÚÑ,.\s]+?)(?=\s*ÁREA|EMPLEO|NIVEL)'
    match = re.search(patron, texto, re.IGNORECASE)
    if match:
        datos['institucion'] = match.group(1).strip()
    
    return datos

print("✓ Función extraer_datos_adicionales definida")

# %% CELDA 9: Función para guardar metadatos
def guardar_metadatos(codigo: str, datos_completos: Dict):
    """Guarda metadatos completos en JSON."""
    ruta_metadatos = DIRECTORIO_METADATOS / f"{codigo}.json"
    datos_completos['timestamp_procesamiento'] = datetime.now().isoformat()
    with open(ruta_metadatos, 'w', encoding='utf-8') as f:
        json.dump(datos_completos, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Metadatos guardados: {ruta_metadatos.name}")

print("✓ Función guardar_metadatos definida")

# %% CELDA 10: Función principal para procesar una declaración
def procesar_declaracion(row: Dict, forzar_descarga: bool = False) -> Dict:
    """
    Procesa una declaración completa.
    
    Args:
        row: Diccionario con datos de la persona y URL
        forzar_descarga: Si True, descarga de nuevo aunque exista el PDF
    """
    url = row.get('url', '')
    nombre = row.get('nombre', '')
    apellido1 = row.get('primer_apellido', '')
    apellido2 = row.get('segundo_apellido', '')
    
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
    
    ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
    
    # Verificar si existe y es válido
    pdf_valido = False
    if ruta_pdf.exists() and not forzar_descarga:
        print(f"  ℹ PDF existe, validando...")
        pdf_valido = validar_pdf(ruta_pdf)
        
        if pdf_valido:
            print(f"  ✓ PDF válido, usando versión local")
        else:
            print(f"  ⚠ PDF corrupto, eliminando y descargando de nuevo...")
            ruta_pdf.unlink()  # Eliminar archivo corrupto
    
    # Descargar si no existe o es inválido
    if not pdf_valido:
        ruta_pdf = descargar_pdf(url, codigo)
        if not ruta_pdf:
            resultado['error'] = 'Error al descargar PDF'
            return resultado
        
        # Validar el PDF descargado
        if not validar_pdf(ruta_pdf):
            resultado['error'] = 'PDF descargado es inválido'
            return resultado
    
    resultado['pdf_descargado'] = True
    resultado['ruta_pdf'] = str(ruta_pdf)
    
    # Extraer texto
    texto = extraer_texto_pdf(ruta_pdf)
    if not texto:
        resultado['error'] = 'Error al extraer texto del PDF'
        return resultado
    
    # Extraer datos
    ingreso = extraer_ingreso_anual_neto(texto)
    resultado['ingreso_anual_neto'] = ingreso
    
    datos_adicionales = extraer_datos_adicionales(texto)
    resultado.update(datos_adicionales)
    resultado['datos_extraidos'] = True
    
    guardar_metadatos(codigo, resultado)
    
    if ingreso:
        print(f"  ✓ Ingreso anual neto: ${ingreso:,.2f}")
    else:
        print(f"  ⚠ Ingreso no encontrado")
    
    return resultado

print("✓ Función procesar_declaracion definida")

# %% CELDA 11: Función para leer Excel
def leer_excel(ruta_excel: str, skiprows: int = 5):
    """Lee el archivo Excel saltando metadatos iniciales."""
    import pandas as pd
    
    print(f"\nLeyendo archivo: {ruta_excel}")
    print(f"Saltando primeras {skiprows} filas...")
    
    df_pandas = pd.read_excel(ruta_excel, skiprows=skiprows)
    df_pandas.columns = [str(col).strip() for col in df_pandas.columns]
    df_pandas = df_pandas.dropna(how='all')
    
    # Convertir tipos problemáticos
    for col in df_pandas.columns:
        if pd.api.types.is_integer_dtype(df_pandas[col]):
            if df_pandas[col].isna().any():
                df_pandas[col] = df_pandas[col].astype('float64')
            else:
                df_pandas[col] = df_pandas[col].astype('int64')
        elif pd.api.types.is_datetime64_any_dtype(df_pandas[col]):
            if hasattr(df_pandas[col].dtype, 'tz') and df_pandas[col].dtype.tz is not None:
                df_pandas[col] = df_pandas[col].dt.tz_localize(None)
    
    print(f"✓ Registros encontrados: {len(df_pandas)}")
    print(f"\n✓ Columnas ({len(df_pandas.columns)}):")
    for i, col in enumerate(df_pandas.columns, 1):
        no_nulos = df_pandas[col].notna().sum()
        print(f"  {i:2d}. {col[:60]:<60} | {no_nulos} valores")
    
    return df_pandas

print("✓ Función leer_excel definida")

# %% CELDA 12: Función para procesar todas las declaraciones
def procesar_todas_declaraciones(df, columna_url: str = None, limite: Optional[int] = None, 
                                forzar_descarga: bool = False):
    """
    Procesa todas las declaraciones del DataFrame.
    
    Args:
        df: DataFrame con los datos
        columna_url: Nombre de la columna con URLs (None para auto-detectar)
        limite: Número máximo de registros a procesar
        forzar_descarga: Si True, re-descarga todos los PDFs
    """
    resultados = []
    columnas = df.columns.tolist()
    
    # Buscar columna de URL automáticamente
    if not columna_url or columna_url not in columnas:
        columnas_posibles = [col for col in columnas 
                           if any(x in col.lower() for x in ['hipervínculo', 'url', 'versión pública', 'enlace'])]
        
        if not columnas_posibles:
            print(f"\n✗ No se encontró columna de URL. Columnas disponibles:")
            for i, col in enumerate(columnas, 1):
                print(f"  {i}. {col}")
            return None
        
        columna_url = columnas_posibles[0]
    
    print(f"\n✓ Usando columna URL: {columna_url}")
    
    # Buscar columnas de nombres
    col_nombre = next((col for col in columnas if 'nombre' in col.lower() and 'apellido' not in col.lower()), None)
    col_apellido1 = next((col for col in columnas if 'primer' in col.lower() and 'apellido' in col.lower()), None)
    col_apellido2 = next((col for col in columnas if 'segundo' in col.lower() and 'apellido' in col.lower()), None)
    
    print(f"✓ Columna nombre: {col_nombre}")
    print(f"✓ Columna primer apellido: {col_apellido1}")
    print(f"✓ Columna segundo apellido: {col_apellido2}")
    
    registros = df.to_dict('records')
    
    if limite:
        registros = registros[:limite]
        print(f"\n⚠ Procesando solo {limite} registros (modo prueba)")
    
    if forzar_descarga:
        print(f"⚠ Modo forzar_descarga activado: se re-descargarán todos los PDFs")
    
    total = len(registros)
    
    for idx, row in enumerate(registros, 1):
        url = row.get(columna_url)
        
        row_procesado = {
            'url': url,
            'nombre': row.get(col_nombre, '') if col_nombre else '',
            'primer_apellido': row.get(col_apellido1, '') if col_apellido1 else '',
            'segundo_apellido': row.get(col_apellido2, '') if col_apellido2 else '',
        }
        
        if url and isinstance(url, str) and url.startswith('http'):
            print(f"\n[{idx}/{total}]")
            resultado = procesar_declaracion(row_procesado, forzar_descarga=forzar_descarga)
            resultados.append(resultado)
            
            if idx < total:
                time.sleep(2)
        else:
            print(f"\n[{idx}/{total}] ✗ URL no válida, saltando...")
    
    if not resultados:
        print("\n⚠ No se procesaron registros")
        return None
    
    import pandas as pd
    return pd.DataFrame(resultados)

print("✓ Función procesar_todas_declaraciones definida")

# %% CELDA 13: Funciones para guardar resultados y estadísticas
def guardar_resultados(df_resultados):
    """Guarda los resultados en múltiples formatos."""
    if df_resultados is None or len(df_resultados) == 0:
        print("\n⚠ No hay resultados para guardar")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # CSV
    ruta_csv = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.csv"
    df_resultados.to_csv(ruta_csv, index=False)
    print(f"\n✓ CSV guardado: {ruta_csv}")
    
    # Excel
    try:
        ruta_excel = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.xlsx"
        df_resultados.to_excel(ruta_excel, index=False)
        print(f"✓ Excel guardado: {ruta_excel}")
    except Exception as e:
        print(f"⚠ No se pudo guardar Excel: {e}")

def mostrar_estadisticas(df_resultados):
    """Muestra estadísticas de los resultados."""
    if df_resultados is None or len(df_resultados) == 0:
        print("⚠ No hay resultados")
        return
    
    print("\n" + "="*60)
    print("ESTADÍSTICAS GENERALES")
    print("="*60)
    
    total = len(df_resultados)
    exitosos = (df_resultados['datos_extraidos'] == True).sum()
    pdfs_desc = (df_resultados['pdf_descargado'] == True).sum()
    con_ingreso = df_resultados['ingreso_anual_neto'].notna().sum()
    
    print(f"Total procesados: {total}")
    print(f"PDFs descargados: {pdfs_desc}")
    print(f"Datos extraídos: {exitosos}")
    print(f"Ingresos encontrados: {con_ingreso}")
    
    if con_ingreso > 0:
        ingresos = df_resultados[df_resultados['ingreso_anual_neto'].notna()]
        print(f"\nPromedio de ingresos: ${ingresos['ingreso_anual_neto'].mean():,.2f}")
        print(f"Mediana: ${ingresos['ingreso_anual_neto'].median():,.2f}")
        print(f"Mínimo: ${ingresos['ingreso_anual_neto'].min():,.2f}")
        print(f"Máximo: ${ingresos['ingreso_anual_neto'].max():,.2f}")
    
    print("="*60)

print("✓ Funciones guardar_resultados y mostrar_estadisticas definidas")

# %% CELDA 14: INSPECCIONAR EXCEL (ejecutar primero)
# Cambia el nombre del archivo según corresponda
df = leer_excel('INFORMACION_49_708785.xls', skiprows=5)
print("\n📊 Muestra de datos:")
print(df.head(3))

# %% CELDA 14B: INSPECCIONAR UNA URL ESPECÍFICA (debugging)
# Usa esto para ver qué hay en una URL problemática
def inspeccionar_url_detallada(url: str):
    """Inspecciona una URL para debugging."""
    print("\n" + "="*60)
    print("🔍 INSPECCIÓN DETALLADA DE URL")
    print("="*60)
    print(f"\n🔗 URL: {url[:100]}...")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        print(f"\n✓ Status: {response.status_code}")
        print(f"✓ Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"✓ Tamaño: {len(response.content):,} bytes")
        
        if response.history:
            print(f"\n🔄 Hubo {len(response.history)} redirección(es)")
            for i, r in enumerate(response.history, 1):
                print(f"  {i}. {r.status_code} -> {r.url[:80]}...")
        
        contenido = response.content
        
        if contenido.startswith(b'%PDF'):
            print(f"\n✓ Es un PDF válido")
            print(f"  Versión: {contenido[:10].decode('latin-1', errors='ignore')}")
        elif b'<html' in contenido.lower()[:500]:
            print(f"\n📄 Es HTML, mostrando inicio:")
            html_str = contenido.decode('utf-8', errors='ignore')
            print(html_str[:800])
            
            print(f"\n🔍 Buscando enlaces a PDF...")
            pdf_url = buscar_enlace_pdf_en_html(response.url, html_str)
            if pdf_url:
                print(f"✓ PDF encontrado: {pdf_url[:100]}...")
            else:
                print(f"✗ No se encontró enlace al PDF")
        else:
            print(f"\n⚠ Contenido desconocido, primeros 200 bytes:")
            print(contenido[:200])
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
    
    print("="*60)

# Para inspeccionar la primera URL del dataframe:
# inspeccionar_url_detallada(df.iloc[0]['nombre_columna_url'])

# %% CELDA 15: PROBAR CON UNA SOLA URL (recomendado)
# Prueba con el primer registro para verificar que funciona
# IMPORTANTE: Usa forzar_descarga=True para re-descargar PDFs corruptos
if len(df) > 0:
    print("\n🔬 PRUEBA CON 1 REGISTRO (forzando descarga)")
    df_prueba = procesar_todas_declaraciones(df, limite=1, forzar_descarga=True)
    if df_prueba is not None:
        mostrar_estadisticas(df_prueba)
        
        # Mostrar errores si los hay
        if 'error' in df_prueba.columns:
            errores = df_prueba[df_prueba['error'].notna()]
            if len(errores) > 0:
                print("\n⚠ ERRORES ENCONTRADOS:")
                for idx, row in errores.iterrows():
                    print(f"  - {row['codigo_declaracion']}: {row['error']}")

# %% CELDA 16: PROCESAR PRIMEROS 5 REGISTROS
# Una vez verificado, procesar más registros
df_resultados_5 = procesar_todas_declaraciones(df, limite=5, forzar_descarga=False)
if df_resultados_5 is not None:
    guardar_resultados(df_resultados_5)
    mostrar_estadisticas(df_resultados_5)
    
    # Mostrar resumen de errores
    errores = df_resultados_5[df_resultados_5['error'].notna()]
    if len(errores) > 0:
        print(f"\n⚠ {len(errores)} registros con errores:")
        for idx, row in errores.iterrows():
            print(f"  - {row['primer_apellido']} {row['segundo_apellido']}: {row['error']}")

# %% CELDA 17: PROCESAR TODOS LOS REGISTROS (¡CUIDADO!)
# Solo ejecutar cuando estés seguro de que todo funciona
# df_todos = procesar_todas_declaraciones(df)
# guardar_resultados(df_todos)
# mostrar_estadisticas(df_todos)