
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Scraper de Declaraciones Patrimoniales - Versión Selenium
Para páginas dinámicas con JavaScript (DeclaraNet)
"""

# %% CELDA 1: Instalar dependencias necesarias
"""
Primero instala estas librerías:

pip install selenium webdriver-manager

Selenium controla un navegador real (Chrome/Firefox)
webdriver-manager descarga automáticamente el driver del navegador
"""
print("📦 Asegúrate de haber instalado: pip install selenium webdriver-manager")

# %% CELDA 2: Importar librerías
import pandas as pd
import pdfplumber
import re
from io import BytesIO
import time
from pathlib import Path
import hashlib
import json
from datetime import datetime
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests

print("✓ Librerías importadas")

# %% CELDA 3: Configuración de directorios
DIRECTORIO_PDFS = Path("declaraciones_pdfs")
DIRECTORIO_METADATOS = Path("declaraciones_metadatos")
DIRECTORIO_RESULTADOS = Path("resultados")

DIRECTORIO_PDFS.mkdir(exist_ok=True)
DIRECTORIO_METADATOS.mkdir(exist_ok=True)
DIRECTORIO_RESULTADOS.mkdir(exist_ok=True)

print("✓ Directorios configurados")

# %% CELDA 4: Configurar navegador Selenium
def crear_driver():
    """Crea y configura el driver de Chrome con opciones optimizadas."""
    chrome_options = Options()
    
    # Opciones para descargar PDFs automáticamente
    prefs = {
        "download.default_directory": str(DIRECTORIO_PDFS.absolute()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,  # No abrir en visor de Chrome
        "plugins.plugins_disabled": ["Chrome PDF Viewer"]
    }
    
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Opcional: ejecutar en modo headless (sin ventana visible)
    # chrome_options.add_argument("--headless")
    
    # Otras opciones útiles
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Crear driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

print("✓ Función crear_driver definida")

# %% CELDA 5: Funciones auxiliares
def generar_codigo_declaracion(nombre: str, apellido1: str, apellido2: str, url: str) -> str:
    """Genera código único para cada declaración."""
    nombre_limpio = re.sub(r'[^a-zA-Z]', '', nombre or '').upper()[:10]
    apellido1_limpio = re.sub(r'[^a-zA-Z]', '', apellido1 or '').upper()[:15]
    apellido2_limpio = re.sub(r'[^a-zA-Z]', '', apellido2 or '').upper()[:15]
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8].upper()
    codigo = f"{apellido1_limpio}_{apellido2_limpio}_{nombre_limpio}_{url_hash}"
    return codigo

def validar_pdf(ruta_pdf: Path) -> bool:
    """Valida si un archivo es un PDF válido."""
    try:
        if not ruta_pdf.exists() or ruta_pdf.stat().st_size < 1024:
            return False
        
        with open(ruta_pdf, 'rb') as f:
            if not f.read(4).startswith(b'%PDF'):
                return False
        
        with pdfplumber.open(ruta_pdf) as pdf:
            if len(pdf.pages) == 0:
                return False
        
        return True
    except:
        return False

print("✓ Funciones auxiliares definidas")

# %% CELDA 6: Descargar PDF con Selenium
def descargar_pdf_selenium(driver, url: str, codigo: str, timeout: int = 30) -> Optional[Path]:
    """
    Descarga un PDF usando Selenium para manejar JavaScript.
    
    Estrategias:
    1. Buscar iframe con el PDF e intentar descargarlo directamente
    2. Buscar botón de descarga y hacer clic
    3. Esperar a que se descargue automáticamente
    """
    try:
        print(f"  → Abriendo URL con Selenium: {url[:80]}...")
        driver.get(url)
        
        # Esperar a que la página cargue completamente
        print(f"  → Esperando carga completa de la página...")
        time.sleep(5)  # Aumentado a 5 segundos
        
        # Estrategia 1: Buscar iframe con PDF
        try:
            print(f"  → Buscando iframes...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            print(f"  → Encontrados {len(iframes)} iframes")
            
            for idx, iframe in enumerate(iframes):
                iframe_src = iframe.get_attribute("src")
                iframe_id = iframe.get_attribute("id")
                iframe_class = iframe.get_attribute("class")
                
                print(f"  → Iframe {idx + 1}:")
                print(f"     ID: {iframe_id}")
                print(f"     Class: {iframe_class}")
                print(f"     Src: {iframe_src[:100] if iframe_src else 'None'}...")
                
                # Intentar con cualquier iframe que tenga src
                if iframe_src:
                    try:
                        # Opción 1: Si el src es una URL de PDF directo
                        if '.pdf' in iframe_src.lower():
                            print(f"  → PDF directo en iframe, descargando...")
                            response = requests.get(iframe_src, timeout=30)
                            response.raise_for_status()
                            
                            if response.content.startswith(b'%PDF'):
                                ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
                                ruta_pdf.write_bytes(response.content)
                                print(f"  ✓ PDF descargado: {len(response.content):,} bytes")
                                return ruta_pdf
                        
                        # Opción 2: El iframe contiene el visor, hacer request al src
                        else:
                            print(f"  → Probando descargar contenido del iframe...")
                            response = requests.get(iframe_src, timeout=30)
                            
                            # Verificar si la respuesta es un PDF
                            if response.content.startswith(b'%PDF'):
                                ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
                                ruta_pdf.write_bytes(response.content)
                                print(f"  ✓ PDF descargado desde iframe: {len(response.content):,} bytes")
                                return ruta_pdf
                            
                            # Si no es PDF, buscar en el HTML del iframe
                            if b'<' in response.content[:100]:
                                contenido_str = response.content.decode('utf-8', errors='ignore')
                                # Buscar URLs de PDF en el HTML del iframe
                                pdf_matches = re.findall(r'(https?://[^\s<>"]+?\.pdf[^\s<>"]*)', 
                                                        contenido_str, re.IGNORECASE)
                                if pdf_matches:
                                    pdf_url = pdf_matches[0]
                                    print(f"  → PDF encontrado en HTML del iframe: {pdf_url[:80]}...")
                                    response2 = requests.get(pdf_url, timeout=30)
                                    if response2.content.startswith(b'%PDF'):
                                        ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
                                        ruta_pdf.write_bytes(response2.content)
                                        print(f"  ✓ PDF descargado: {len(response2.content):,} bytes")
                                        return ruta_pdf
                    
                    except Exception as e:
                        print(f"  ⚠ Error procesando iframe {idx + 1}: {e}")
                        continue
        
        except Exception as e:
            print(f"  ⚠ Error buscando iframes: {e}")
        
        # Estrategia 2: Buscar botón de descarga
        try:
            # Selectores comunes para botones de descarga
            selectores_descarga = [
                "//button[contains(@class, 'download')]",
                "//a[contains(@class, 'download')]",
                "//button[contains(@title, 'Descargar')]",
                "//a[contains(@title, 'Descargar')]",
                "//button[contains(@aria-label, 'download')]",
                "//a[@download]",
                "//mat-icon[text()='download']/..",
                "//i[contains(@class, 'download')]/..",
            ]
            
            for selector in selectores_descarga:
                try:
                    boton = driver.find_element(By.XPATH, selector)
                    print(f"  → Botón de descarga encontrado, haciendo clic...")
                    boton.click()
                    time.sleep(3)
                    
                    # Buscar el archivo descargado
                    archivos_antes = set(DIRECTORIO_PDFS.glob("*.pdf"))
                    time.sleep(5)  # Esperar descarga
                    archivos_despues = set(DIRECTORIO_PDFS.glob("*.pdf"))
                    
                    nuevos_archivos = archivos_despues - archivos_antes
                    
                    if nuevos_archivos:
                        archivo_descargado = list(nuevos_archivos)[0]
                        ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
                        archivo_descargado.rename(ruta_pdf)
                        print(f"  ✓ PDF descargado via botón")
                        return ruta_pdf
                    
                    break
                except:
                    continue
        
        except Exception as e:
            print(f"  ⚠ Error buscando botón: {e}")
        
        # Estrategia 3: Intentar obtener el PDF desde el contexto de la página
        try:
            # Buscar en el código fuente de la página
            page_source = driver.page_source
            
            # Buscar URLs de PDF en el HTML renderizado
            pdf_patterns = [
                r'src="([^"]+\.pdf[^"]*)"',
                r"src='([^']+\.pdf[^']*)'",
                r'href="([^"]+\.pdf[^"]*)"',
                r"href='([^']+\.pdf[^']*)'",
                r'(https?://[^\s<>"]+?\.pdf)',
            ]
            
            for pattern in pdf_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    pdf_url = matches[0]
                    print(f"  → PDF encontrado en código fuente: {pdf_url[:80]}...")
                    
                    response = requests.get(pdf_url, timeout=30)
                    if response.content.startswith(b'%PDF'):
                        ruta_pdf = DIRECTORIO_PDFS / f"{codigo}.pdf"
                        ruta_pdf.write_bytes(response.content)
                        print(f"  ✓ PDF descargado desde código fuente")
                        return ruta_pdf
        
        except Exception as e:
            print(f"  ⚠ Error extrayendo de código fuente: {e}")
        
        print(f"  ✗ No se pudo descargar el PDF")
        return None
        
    except Exception as e:
        print(f"  ✗ Error con Selenium: {str(e)}")
        return None

print("✓ Función descargar_pdf_selenium definida")

# %% CELDA 7: Funciones de extracción de datos
def extraer_texto_pdf(ruta_pdf: Path) -> Optional[str]:
    """Extrae texto del PDF."""
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto = ""
            for pagina in pdf.pages:
                texto += pagina.extract_text() or ""
        return texto
    except Exception as e:
        print(f"  ✗ Error extrayendo texto: {e}")
        return None

def extraer_ingreso_anual_neto(texto: str) -> Optional[float]:
    """Extrae el ingreso anual neto."""
    if not texto:
        return None
    
    patrones = [
        r'A\.\s*INGRESO ANUAL NETO DEL DECLARANTE.*?(\d[\d,]+)',
        r'INGRESO ANUAL NETO.*?NUMERAL I Y II\)?\s*(\d[\d,]+)',
    ]
    
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1).replace(',', ''))
    
    return None

def extraer_datos_adicionales(texto: str) -> Dict:
    """Extrae información adicional."""
    datos = {
        'remuneracion_cargo_publico': None,
        'otros_ingresos': None,
        'actividad_financiera': None,
        'servicios_profesionales': None,
        'fecha_recepcion': None,
        'cargo': None,
        'institucion': None,
    }
    
    # Implementación de patrones (igual que antes)
    patron = r'REMUNERACIÓN ANUAL NETA.*?PRESTACIONES.*?(\d[\d,]+)'
    match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    if match:
        datos['remuneracion_cargo_publico'] = float(match.group(1).replace(',', ''))
    
    # ... (resto de patrones)
    
    return datos

def guardar_metadatos(codigo: str, datos: Dict):
    """Guarda metadatos en JSON."""
    ruta = DIRECTORIO_METADATOS / f"{codigo}.json"
    datos['timestamp_procesamiento'] = datetime.now().isoformat()
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Metadatos guardados")

print("✓ Funciones de extracción definidas")

# %% CELDA 8: Procesar una declaración
def procesar_declaracion(driver, row: Dict, forzar_descarga: bool = False) -> Dict:
    """Procesa una declaración completa."""
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
    if ruta_pdf.exists() and not forzar_descarga:
        print(f"  ℹ PDF existe, validando...")
        if validar_pdf(ruta_pdf):
            print(f"  ✓ PDF válido")
        else:
            print(f"  ⚠ PDF inválido, eliminando...")
            ruta_pdf.unlink()
            ruta_pdf = None
    
    # Descargar si es necesario
    if not ruta_pdf or not ruta_pdf.exists():
        ruta_pdf = descargar_pdf_selenium(driver, url, codigo)
        if not ruta_pdf:
            resultado['error'] = 'No se pudo descargar PDF'
            return resultado
        
        if not validar_pdf(ruta_pdf):
            resultado['error'] = 'PDF descargado es inválido'
            return resultado
    
    resultado['pdf_descargado'] = True
    resultado['ruta_pdf'] = str(ruta_pdf)
    
    # Extraer datos
    texto = extraer_texto_pdf(ruta_pdf)
    if not texto:
        resultado['error'] = 'Error extrayendo texto'
        return resultado
    
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

# %% CELDA 9: Leer Excel
def leer_excel(ruta_excel: str, skiprows: int = 5):
    """Lee el archivo Excel."""
    print(f"\nLeyendo: {ruta_excel}")
    df = pd.read_excel(ruta_excel, skiprows=skiprows)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.dropna(how='all')
    
    print(f"✓ {len(df)} registros encontrados")
    print(f"\nColumnas:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col[:60]}")
    
    return df

print("✓ Función leer_excel definida")

# %% CELDA 10: Procesar todas las declaraciones
def procesar_todas(df, limite: Optional[int] = None, forzar_descarga: bool = False):
    """Procesa todas las declaraciones."""
    
    # Buscar columna URL
    columnas = df.columns.tolist()
    col_url = next((col for col in columnas 
                   if any(x in col.lower() for x in ['hipervínculo', 'url', 'versión pública'])), None)
    
    if not col_url:
        print("✗ No se encontró columna URL")
        return None
    
    print(f"✓ Columna URL: {col_url}")
    
    # Buscar columnas de nombres
    col_nombre = next((col for col in columnas if 'nombre' in col.lower() and 'apellido' not in col.lower()), None)
    col_ap1 = next((col for col in columnas if 'primer' in col.lower() and 'apellido' in col.lower()), None)
    col_ap2 = next((col for col in columnas if 'segundo' in col.lower() and 'apellido' in col.lower()), None)
    
    print(f"✓ Columnas: nombre={col_nombre}, ap1={col_ap1}, ap2={col_ap2}")
    
    registros = df.to_dict('records')
    if limite:
        registros = registros[:limite]
        print(f"\n⚠ Procesando solo {limite} registros")
    
    # Crear driver
    print("\n🌐 Iniciando navegador Chrome...")
    driver = crear_driver()
    
    resultados = []
    total = len(registros)
    
    try:
        for idx, row in enumerate(registros, 1):
            url = row.get(col_url)
            
            row_proc = {
                'url': url,
                'nombre': row.get(col_nombre, ''),
                'primer_apellido': row.get(col_ap1, ''),
                'segundo_apellido': row.get(col_ap2, ''),
            }
            
            if url and isinstance(url, str) and url.startswith('http'):
                print(f"\n[{idx}/{total}]")
                resultado = procesar_declaracion(driver, row_proc, forzar_descarga)
                resultados.append(resultado)
                
                if idx < total:
                    time.sleep(2)
            else:
                print(f"\n[{idx}/{total}] ✗ URL inválida")
    
    finally:
        print("\n🔒 Cerrando navegador...")
        driver.quit()
    
    if not resultados:
        return None
    
    return pd.DataFrame(resultados)

print("✓ Función procesar_todas definida")

# %% CELDA 11: Guardar resultados
def guardar_resultados(df_resultados):
    """Guarda resultados."""
    if df_resultados is None or len(df_resultados) == 0:
        print("⚠ Sin resultados")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    ruta_csv = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.csv"
    df_resultados.to_csv(ruta_csv, index=False)
    print(f"\n✓ CSV: {ruta_csv}")
    
    try:
        ruta_excel = DIRECTORIO_RESULTADOS / f"resultados_{timestamp}.xlsx"
        df_resultados.to_excel(ruta_excel, index=False)
        print(f"✓ Excel: {ruta_excel}")
    except:
        pass

def mostrar_estadisticas(df):
    """Muestra estadísticas."""
    if df is None or len(df) == 0:
        return
    
    print("\n" + "="*60)
    print("ESTADÍSTICAS")
    print("="*60)
    
    total = len(df)
    exitosos = (df['datos_extraidos'] == True).sum()
    con_ingreso = df['ingreso_anual_neto'].notna().sum()
    
    print(f"Total: {total}")
    print(f"Exitosos: {exitosos}")
    print(f"Con ingreso: {con_ingreso}")
    
    if con_ingreso > 0:
        ing = df[df['ingreso_anual_neto'].notna()]['ingreso_anual_neto']
        print(f"\nPromedio: ${ing.mean():,.2f}")
        print(f"Mediana: ${ing.median():,.2f}")
        print(f"Min: ${ing.min():,.2f}")
        print(f"Max: ${ing.max():,.2f}")
    
    errores = df[df['error'].notna()]
    if len(errores) > 0:
        print(f"\n⚠ {len(errores)} errores:")
        for _, row in errores.iterrows():
            print(f"  - {row['codigo_declaracion']}: {row['error']}")
    
    print("="*60)

print("✓ Funciones de resultados definidas")

# %% CELDA 12: DIAGNÓSTICO - Ver qué hay en una URL
def diagnosticar_url(url: str):
    """
    Diagnóstico detallado de una URL para ver cómo extraer el PDF.
    """
    print("\n" + "="*80)
    print("🔬 DIAGNÓSTICO DETALLADO")
    print("="*80)
    print(f"\n🔗 URL: {url}")
    
    print("\n🌐 Iniciando Chrome...")
    driver = crear_driver()
    
    try:
        print(f"\n→ Navegando a la URL...")
        driver.get(url)
        time.sleep(5)
        
        print(f"\n→ Título de la página: {driver.title}")
        print(f"→ URL actual: {driver.current_url}")
        
        # Buscar todos los iframes
        print(f"\n📦 IFRAMES ENCONTRADOS:")
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"Total: {len(iframes)}")
        
        for idx, iframe in enumerate(iframes, 1):
            print(f"\n  Iframe #{idx}:")
            print(f"    ID: {iframe.get_attribute('id')}")
            print(f"    Name: {iframe.get_attribute('name')}")
            print(f"    Class: {iframe.get_attribute('class')}")
            src = iframe.get_attribute('src')
            print(f"    Src: {src if src else 'None'}")
            
            if src:
                print(f"    → Intentando acceder al contenido del iframe...")
                try:
                    response = requests.get(src, timeout=10)
                    print(f"    → Status: {response.status_code}")
                    print(f"    → Content-Type: {response.headers.get('Content-Type', 'N/A')}")
                    print(f"    → Tamaño: {len(response.content):,} bytes")
                    
                    if response.content.startswith(b'%PDF'):
                        print(f"    ✓ ¡Es un PDF válido!")
                    else:
                        print(f"    → Primeros 200 caracteres:")
                        print(f"       {response.content[:200]}")
                except Exception as e:
                    print(f"    ✗ Error: {e}")
        
        # Buscar botones y enlaces
        print(f"\n🔘 BOTONES Y ENLACES DE DESCARGA:")
        
        # Buscar elementos con "download" en el texto o atributos
        elementos_download = driver.find_elements(By.XPATH, 
            "//*[contains(translate(text(), 'DESCARGAR', 'descargar'), 'descargar') or "
            "contains(@class, 'download') or contains(@id, 'download') or "
            "contains(@title, 'descargar') or @download]")
        
        print(f"Total encontrados: {len(elementos_download)}")
        for idx, elem in enumerate(elementos_download[:5], 1):  # Mostrar máximo 5
            print(f"\n  Elemento #{idx}:")
            print(f"    Tag: {elem.tag_name}")
            print(f"    Texto: {elem.text[:50] if elem.text else 'None'}")
            print(f"    Href: {elem.get_attribute('href')}")
            print(f"    Class: {elem.get_attribute('class')}")
        
        # Guardar screenshot para análisis visual
        screenshot_path = DIRECTORIO_PDFS / f"diagnostico_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"\n📸 Screenshot guardado: {screenshot_path}")
        
        # Guardar el HTML completo
        html_path = DIRECTORIO_PDFS / f"diagnostico_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_path.write_text(driver.page_source, encoding='utf-8')
        print(f"📄 HTML guardado: {html_path}")
        
        # Buscar en el código fuente
        print(f"\n🔍 BUSCANDO PATRONES DE PDF EN EL CÓDIGO FUENTE:")
        page_source = driver.page_source
        
        pdf_patterns = [
            r'(https?://[^\s<>"]+?\.pdf[^\s<>"]*)',
            r'src="([^"]+)"',
            r"src='([^']+)'",
        ]
        
        for pattern in pdf_patterns:
            matches = re.findall(pattern, page_source, re.IGNORECASE)
            if matches:
                print(f"\n  Patrón '{pattern[:30]}...' encontró {len(matches)} coincidencias:")
                # Filtrar solo las que parezcan PDFs o documentos
                pdf_matches = [m for m in matches if 'pdf' in m.lower() or 'declaracion' in m.lower() or 'documento' in m.lower()]
                for match in pdf_matches[:5]:
                    print(f"    - {match[:100]}")
        
        print(f"\n" + "="*80)
        print(f"Mantén el navegador abierto para inspección manual...")
        print(f"Presiona Enter cuando termines de inspeccionar...")
        input()
        
    finally:
        driver.quit()
        print(f"✓ Navegador cerrado")

print("✓ Función diagnosticar_url definida")

# %% CELDA 12B: EJECUTAR DIAGNÓSTICO con la primera URL
# Primero encuentra la columna URL
if 'df' in globals():
    columna_url = [col for col in df.columns if 'hipervínculo' in col.lower() or 'url' in col.lower()][0]
    primera_url = df.iloc[0][columna_url]
    print(f"Primera URL del Excel: {primera_url}")
    
    # Ejecuta el diagnóstico
    # diagnosticar_url(primera_url)

# %% CELDA 13: EJECUTAR - Leer Excel
# %% CELDA 13: EJECUTAR - Leer Excel
df = leer_excel('INFORMACION_49_708785.xls', skiprows=5)
print("\n📊 Muestra:")
print(df.head(3))

# %% CELDA 14: EJECUTAR - Probar con 1 registro
# %% CELDA 14: EJECUTAR - Probar con 1 registro
df_prueba = procesar_todas(df, limite=1, forzar_descarga=True)
if df_prueba is not None:
    mostrar_estadisticas(df_prueba)
    guardar_resultados(df_prueba)

# %% CELDA 15: EJECUTAR - Procesar 5 registros
# df_5 = procesar_todas(df, limite=5)
# guardar_resultados(df_5)
# mostrar_estadisticas(df_5)

# %% CELDA 16: EJECUTAR - Procesar TODOS (cuidado)
# df_todos = procesar_todas(df)
# guardar_resultados(df_todos)
# mostrar_estadisticas(df_todos)

# %% EJECUTAR DIAGNÓSTICO
diagnosticar_url(primera_url)