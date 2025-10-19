#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Oct  9 14:29:32 2025

@author: emiliano
"""

# %% VER TOP 10 CON MAYORES INGRESOS
import pandas as pd

# Leer el último archivo de resultados
archivos = sorted(DIRECTORIO_RESULTADOS.glob("resultados_*.csv"))
df_resultados = pd.read_csv(archivos[-1])

# Filtrar solo los que tienen ingreso
con_ingreso = df_resultados[df_resultados['ingreso_anual_neto'].notna()].copy()

# Ordenar de mayor a menor
top_ingresos = con_ingreso.sort_values('ingreso_anual_neto', ascending=False)

print("\n" + "="*80)
print("💰 TOP 10 - MAYORES INGRESOS ANUALES NETOS")
print("="*80)

for idx, row in top_ingresos.head(90).iterrows():
    nombre_completo = f"{row['primer_apellido']} {row['segundo_apellido']} {row['nombre']}"
    ingreso = row['ingreso_anual_neto']
    print(f"\n{idx+1}. {nombre_completo}")
    print(f"   💵 Ingreso anual neto: ${ingreso:,.2f}")
    if pd.notna(row.get('cargo')):
        print(f"   👔 Cargo: {row['cargo']}")
    if pd.notna(row.get('institucion')):
        print(f"   🏢 Institución: {row['institucion']}")