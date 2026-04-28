import streamlit as st
import pandas as pd
import numpy as np
import os
import unicodedata

# 1. Función para normalizar nombres (quitar tildes y espacios)
def normalizar(texto):
    if not isinstance(texto, str): return str(texto)
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode("utf-8")
    return texto.strip().upper()

@st.cache_data
def cargar_datos_automatico():
    # Buscamos cualquier archivo .csv en la carpeta
    archivos = [f for f in os.listdir('.') if f.endswith('.csv')]
    
    if not archivos:
        return None, "❌ No se encontró ningún archivo .csv en la carpeta."
    
    # Priorizamos el que tenga "COORDENADAS" o usamos el primero que aparezca
    archivo_real = next((f for f in archivos if "COORDENADAS" in f.upper()), archivos[0])
    
    try:
        df = pd.read_csv(archivo_real, encoding='latin-1')
        
        # Limpiamos los nombres de las columnas del Excel
        # Esto convierte "Locación" en "LOCACION" y "Este (m)" en "ESTE"
        df.columns = [normalizar(c) for c in df.columns]
        
        # Mapeo de columnas por contenido
        col_loc = next((c for c in df.columns if 'LOC' in c), None)
        col_este = next((c for c in df.columns if 'ESTE' in c), None)
        col_norte = next((c for c in df.columns if 'NORTE' in c), None)
        col_pozo = next((c for c in df.columns if 'POZO' in c), None)
        
        if all([col_loc, col_este, col_norte, col_pozo]):
            df_std = pd.DataFrame()
            df_std['LOCACION'] = df[col_loc].apply(normalizar)
            df_std['ESTE'] = pd.to_numeric(df[col_este], errors='coerce')
            df_std['NORTE'] = pd.to_numeric(df[col_norte], errors='coerce')
            df_std['POZO'] = df[col_pozo].astype(str)
            
            df_final = df_std.dropna(subset=['ESTE', 'NORTE']).groupby('LOCACION').agg({
                'ESTE': 'first', 'NORTE': 'first', 'POZO': lambda x: ', '.join(x.unique())
            }).reset_index()
            
            return df_final, archivo_real
        else:
            return None, f"⚠️ Columnas no encontradas en {archivo_real}"
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

# --- INTERFAZ ---
st.title("🚜 Sistema Logístico de Coordenadas")

df, nombre_leido = cargar_datos_automatico()

if df is not None:
    st.sidebar.success(f"📂 Archivo detectado: {nombre_leido}")
    # ... resto del código de la ruta ...
else:
    st.error(nombre_leido)
