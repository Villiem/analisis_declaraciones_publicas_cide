#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Oct  9 14:36:42 2025

@author: emiliano
"""

# %% CELDA 18: EJECUTAR - Procesar 100 registros
print("\n" + "="*80)
print("🚀 PROCESANDO 100 REGISTROS")
print("="*80)
print("\n⏱️  Tiempo estimado: ~25-30 minutos")
print("💡 El navegador se abrirá y trabajará automáticamente")
print("💡 Puedes minimizar la ventana pero no cierres Spyder\n")

df_resultados_404 = procesar_todas(df, limite=404, forzar_descarga=False)
#%%

if df_resultados_404 is not None:
    print("\n" + "="*80)
    print("💾 GUARDANDO RESULTADOS")
    print("="*80)
    guardar_resultados(df_resultados_404)
    
    print("\n" + "="*80)
    print("📊 ESTADÍSTICAS FINALES - 100 REGISTROS")
    print("="*80)
    mostrar_estadisticas(df_resultados_404)
    
    # Resumen de errores
    errores = df_resultados_404[df_resultados_404['error'].notna()]
    exitosos = df_resultados_404[df_resultados_404['datos_extraidos'] == True]
    con_ingreso = df_resultados_404[df_resultados_404['ingreso_anual_neto'].notna()]
    
    print(f"\n{'='*80}")
    print(f"📈 RESUMEN GENERAL:")
    print(f"{'='*80}")
    print(f"✅ Exitosos: {len(exitosos)}/100 ({len(exitosos)/100*100:.1f}%)")
    print(f"💰 Con ingreso: {len(con_ingreso)}/100 ({len(con_ingreso)/100*100:.1f}%)")
    print(f"❌ Con errores: {len(errores)}/100 ({len(errores)/100*100:.1f}%)")
    
    if len(errores) > 0:
        print(f"\n⚠️  TIPOS DE ERRORES:")
        print(errores['error'].value_counts())
    
    print("\n" + "="*80)
    print("✅ PROCESO COMPLETADO")
    print("="*80)
    print(f"📁 Archivos guardados en:")
    print(f"   - {DIRECTORIO_RESULTADOS}")
else:
    print("\n❌ No se pudieron procesar los registros")
#%%
import os

print(os.getcwd())
os.chdir('/home/emiliano/Documentos/python/webscrap')