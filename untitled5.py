

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
    
    # Directorio de descargas
    download_dir = str(DIRECTORIO_PDFS.absolute())
    
    # Opciones para descargar PDFs automáticamente
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "plugins.plugins_disabled": ["Chrome PDF Viewer"],
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Opcional: ejecutar en modo headless (sin ventana visible)
    # chrome_options.add_argument("--headless")
    
    # Otras opciones útiles
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
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

# %% CELDA 6: Descargar PDF con Selenium usando botón de descarga
def descargar_pdf_selenium(driver, url: str, codigo: str, timeout: int = 30) -> Optional[Path]:
    """
    Descarga un PDF haciendo clic en el botón de descarga.
    """
    try:
        print(f"  → Abriendo URL: {url[:80]}...")
        driver.get(url)
        
        # Esperar a que PDF.js cargue completamente
        print(f"  → Esperando que PDF.js cargue...")
        time.sleep(8)  # Dar tiempo a que se renderice el PDF
        
        # Buscar el archivo de descarga antes de hacer clic
        archivos_antes = set(DIRECTORIO_PDFS.glob("*.pdf"))
        archivos_antes_crdownload = set(DIRECTORIO_PDFS.glob("*.crdownload"))
        
        # Estrategia 1: Buscar el botón de descarga y hacer clic
        print(f"  → Buscando botón de descarga...")
        
        selectores_descarga = [
            # Selectores específicos para PDF.js
            "//button[@id='download']",
            "//a[@id='download']",
            "//button[@title='Download']",
            "//button[@title='Descargar']",
            "//button[contains(@class, 'download')]",
            "//a[contains(@class, 'download')]",
            "//button[contains(@class, 'toolbarButton')][@title='Download']",
            "//button[contains(@class, 'toolbarButton')][@title='Descargar']",
            # Botones genéricos
            "//*[@download]",
            "//button[contains(text(), 'Descargar')]",
            "//a[contains(text(), 'Descargar')]",
        ]
        
        boton_encontrado = False
        for selector in selectores_descarga:
            try:
                boton = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                
                print(f"  → Botón encontrado con selector: {selector[:50]}...")
                print(f"  → Haciendo clic en el botón de descarga...")
                
                # Scroll al botón para asegurarse que es visible
                driver.execute_script("arguments[0].scrollIntoView(true);", boton)
                time.sleep(1)
                
                # Hacer clic
                boton.click()
                boton_encontrado = True
                print(f"  ✓ Clic realizado")
                break
                
            except Exception as e:
                continue
        
        if not boton_encontrado:
            print(f"  ✗ No se encontró botón de descarga")
            return None
        
        # Esperar a que se complete la descarga
        print(f"  → Esperando descarga...")
        max_espera = 30  # segundos
        tiempo_transcurrido = 0
        archivo_descargado = None
        
        while tiempo_transcurrido < max_espera:
            time.sleep(1)
            tiempo_transcurrido += 1
            
            # Buscar archivos nuevos
            archivos_ahora = set(DIRECTORIO_PDFS.glob("*.pdf"))
            archivos_nuevos = archivos_ahora - archivos_antes
            
            # Verificar si hay archivos en descarga (.crdownload)
            archivos_crdownload = set(DIRECTORIO_PDFS.glob("*.crdownload"))
            descargando = len(archivos_crdownload) > len(archivos_antes_crdownload)
            
            if archivos_nuevos and not descargando:
                archivo_descargado = list(archivos_nuevos)[0]
                print(f"  ✓ Archivo descargado: {archivo_descargado.name}")
                break
            
            if tiempo_transcurrido % 5 == 0:
                print(f"  → Esperando... ({tiempo_transcurrido}s)")
        
        if not archivo_descargado:
            print(f"  ✗ Timeout esperando descarga")
            return None
        
        # Renombrar archivo a nuestro código
        ruta_final = DIRECTORIO_PDFS / f"{codigo}.pdf"
        
        # Si ya existe, eliminarlo
        if ruta_final.exists():
            ruta_final.unlink()
        
        archivo_descargado.rename(ruta_final)
        print(f"  ✓ PDF renombrado a: {ruta_final.name}")
        
        # Validar que sea un PDF válido
        if not validar_pdf(ruta_final):
            print(f"  ✗ El archivo descargado no es un PDF válido")
            return None
        
        tamanio = ruta_final.stat().st_size
        print(f"  ✓ PDF descargado exitosamente: {tamanio:,} bytes")
        
        return ruta_final
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
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

# %% CELDA 16: EJECUTAR - Procesar 5 registros
df_resultados_5 = procesar_todas(df, limite=5, forzar_descarga=False)
if df_resultados_5 is not None:
    guardar_resultados(df_resultados_5)
    mostrar_estadisticas(df_resultados_5)
    
    # Mostrar resumen de errores
    errores = df_resultados_5[df_resultados_5['error'].notna()]
    if len(errores) > 0:
        print(f"\n⚠ {len(errores)} registros con errores:")
        for idx, row in errores.iterrows():
            print(f"  - {row['primer_apellido']} {row['segundo_apellido']}: {row['error']}")

# %% Ejecutar prueba con 1 registro
df_prueba = procesar_todas(df, limite=1, forzar_descarga=True)
mostrar_estadisticas(df_prueba)

#%%
# %% CELDA 16: EJECUTAR - Procesar 5 registros
# %% CELDA 17: EJECUTAR - Procesar 40 registros
print("\n" + "="*80)
print("🚀 PROCESANDO 40 REGISTROS")
print("="*80)
print("\n⏱️  Tiempo estimado: ~10-15 minutos")
print("💡 Consejo: Deja que el navegador trabaje sin interrumpir\n")

df_resultados_40 = procesar_todas(df, limite=40, forzar_descarga=False)

if df_resultados_40 is not None:
    print("\n" + "="*80)
    print("💾 GUARDANDO RESULTADOS")
    print("="*80)
    guardar_resultados(df_resultados_40)
    
    print("\n" + "="*80)
    print("📊 ESTADÍSTICAS FINALES")
    print("="*80)
    mostrar_estadisticas(df_resultados_40)
    
    # Mostrar detalles de errores
    errores = df_resultados_40[df_resultados_40['error'].notna()]
    if len(errores) > 0:
        print(f"\n⚠️  ERRORES ENCONTRADOS: {len(errores)}/{len(df_resultados_40)}")
        print("-" * 80)
        for idx, row in errores.iterrows():
            print(f"  {idx+1}. {row['primer_apellido']} {row['segundo_apellido']} {row['nombre']}")
            print(f"     Error: {row['error']}")
            print(f"     URL: {row['url'][:80]}...")
    
    # Mostrar casos exitosos
    exitosos = df_resultados_40[df_resultados_40['datos_extraidos'] == True]
    print(f"\n✅ EXITOSOS: {len(exitosos)}/{len(df_resultados_40)}")
    
    con_ingreso = df_resultados_40[df_resultados_40['ingreso_anual_neto'].notna()]
    print(f"💰 CON INGRESO EXTRAÍDO: {len(con_ingreso)}/{len(exitosos)}")
    
    print("\n" + "="*80)
    print("✅ PROCESO COMPLETADO")
    print("="*80)
else:
    print("\n❌ No se pudieron procesar los registros")