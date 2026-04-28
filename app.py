import streamlit as st
import pandas as pd
import numpy as np
import re

# 1. Carga limpia del archivo (Sin Lat/Lon)
@st.cache_data
def cargar_base_coordenadas(file_path):
    # Leemos el archivo directo (Encabezado: GERENCIA, LOCACION, ESTE, NORTE, POZO)
    df = pd.read_csv(file_path, encoding='latin-1')
    
    # Limpiamos nombres de columnas (quitar espacios invisibles)
    df.columns = df.columns.str.strip()
    
    # Seleccionamos y renombramos para facilitar el uso en el resto del código
    df_coords = df[['POZO', 'LOCACION', 'ESTE', 'NORTE']].copy()
    df_coords.columns = ['pozo', 'cluster', 'este', 'norte']
    
    # Aseguramos que las coordenadas sean números (flotantes)
    df_coords['este'] = pd.to_numeric(df_coords['este'], errors='coerce')
    df_coords['norte'] = pd.to_numeric(df_coords['norte'], errors='coerce')
    
    # Agrupamos por Locación (Cluster)
    return df_coords.dropna(subset=['este', 'norte']).groupby('cluster').agg({
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()

# 2. Cálculo de Distancia Plana (Pitagórica) en metros
def calcular_distancia_euclidiana(p1, p2):
    # Distancia = raíz cuadrada de ((E2-E1)² + (N2-N1)²)
    distancia = np.sqrt((p2['este'] - p1['este'])**2 + (p2['norte'] - p1['norte'])**2)
    return round(distancia / 1000, 2) # Convertimos a Kilómetros

# --- INTERFAZ ---
st.title("🚜 Logística Rubiales & CASE: Análisis de Movilización")

try:
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")

    st.sidebar.header("Itinerario de Movilización")
    ruta_input = st.sidebar.text_area("Pega las Locaciones en orden:", placeholder="CASE0015\nAGRIO-1")
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
        match = df_maestro[df_maestro['cluster'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'orden': i + 1,
                'nombre': nombre, 
                'este': match.iloc[0]['este'],
                'norte': match.iloc[0]['norte'],
                'pozos': match.iloc[0]['pozo']
            })

    if len(puntos_ruta) >= 1:
        st.write("### 📋 Resumen Logístico de la Ruta")
        
        # Generar tabla de movimientos y distancias
        resumen_datos = []
        total_km = 0
        
        for i in range(len(puntos_ruta)):
            p_actual = puntos_ruta[i]
            dist_tramo = 0
            
            if i > 0:
                p_prev = puntos_ruta[i-1]
                dist_tramo = calcular_distancia_euclidiana(p_prev, p_actual)
                total_km += dist_tramo
            
            resumen_datos.append({
                "Orden": p_actual['orden'],
                "Locación": p_actual['nombre'],
                "Distancia Tramo (Km)": dist_tramo if i > 0 else "---",
                "Coordenada Este": p_actual['este'],
                "Coordenada Norte": p_actual['norte']
            })
            
        st.table(pd.DataFrame(resumen_datos))
        st.metric("Distancia Total Estimada (Línea Recta)", f"{total_km:.2f} Km")
        
    else:
        st.info("Ingresa los clústeres en el panel izquierdo para calcular la ruta.")

except Exception as e:
    st.error(f"Error: {e}")
