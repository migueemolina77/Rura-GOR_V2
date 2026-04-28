import streamlit as st
import pandas as pd
import numpy as np
import re
import os

# Configuración de la página
st.set_page_config(page_title="Logística Rubiales & CASE", layout="wide")

# 1. Función de Carga con Visor de Verificación
@st.cache_data
def cargar_datos(file_name):
    if not os.path.exists(file_name):
        return None, f"Archivo '{file_name}' no encontrado."
    
    try:
        # Lectura del CSV con encoding estándar para Excel/Spanish
        df = pd.read_csv(file_name, encoding='latin-1')
        
        # Limpieza de nombres de columnas (quitar espacios y pasar a MAYÚSCULAS)
        df.columns = df.columns.astype(str).str.strip().str.upper()
        
        # Validación de columnas necesarias
        columnas_requeridas = ['LOCACION', 'ESTE', 'NORTE', 'POZO']
        columnas_presentes = df.columns.tolist()
        
        # Verificamos si están todas las necesarias
        if all(col in columnas_presentes for col in columnas_requeridas):
            # Limpieza de datos numéricos
            df['ESTE'] = pd.to_numeric(df['ESTE'], errors='coerce')
            df['NORTE'] = pd.to_numeric(df['NORTE'], errors='coerce')
            
            # Agrupación por Locación
            df_final = df.dropna(subset=['ESTE', 'NORTE']).groupby('LOCACION').agg({
                'ESTE': 'first',
                'NORTE': 'first',
                'POZO': lambda x: ', '.join(x.astype(str))
            }).reset_index()
            
            return df_final, f"Cargado exitosamente: {file_name}"
        else:
            return None, f"Error: Columnas faltantes. Encontradas: {columnas_presentes}"
            
    except Exception as e:
        return None, f"Error al leer el archivo: {e}"

# 2. Cálculo de Distancia Euclidiana (Metros a Kilómetros)
def calcular_distancia(p1, p2):
    dist = np.sqrt((p2['ESTE'] - p1['ESTE'])**2 + (p2['NORTE'] - p1['NORTE'])**2)
    return round(dist / 1000, 2)

# --- INTERFAZ DE USUARIO ---

st.title("🚜 Logística: Visor de Movilización Rubiales & CASE")

# Lógica de carga
archivo_objetivo = "datam.csv"
df_maestro, mensaje_estado = cargar_datos(archivo_objetivo)

# Visor de estado en la barra lateral
st.sidebar.header("📁 Estado del Archivo")
if df_maestro is not None:
    st.sidebar.success(mensaje_estado)
    st.sidebar.write(f"**Registros (Locaciones):** {len(df_maestro)}")
else:
    st.sidebar.error(mensaje_estado)
    st.stop() # Detiene la ejecución si no hay datos

# Entrada de Ruta
st.sidebar.header("📍 Planificación de Ruta")
input_ruta = st.sidebar.text_area("Lista de Locaciones (una por línea):", 
                                 placeholder="CASE0015\nAGRIO-1\nRB-162")

if input_ruta:
    nombres_solicitados = [n.strip().upper() for n in re.split(r'[\n,]+', input_ruta) if n.strip()]
    
    puntos_ruta = []
    for i, nombre in enumerate(nombres_solicitados):
        match = df_maestro[df_maestro['LOCACION'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'Orden': i + 1,
                'Locacion': nombre,
                'ESTE': match.iloc[0]['ESTE'],
                'NORTE': match.iloc[0]['NORTE'],
                'Pozos': match.iloc[0]['POZO']
            })
        else:
            st.sidebar.warning(f"⚠️ No se encontró: {nombre}")

    # Mostrar Resultados
    if puntos_ruta:
        st.write("### 📋 Itinerario y Coordenadas Planas")
        
        datos_tabla = []
        total_km = 0
        
        for i in range(len(puntos_ruta)):
            p_actual = puntos_ruta[i]
            dist_tramo = 0
            
            if i > 0:
                dist_tramo = calcular_distancia(puntos_ruta[i-1], p_actual)
                total_km += dist_tramo
            
            datos_tabla.append({
                "Orden": p_actual['Orden'],
                "Locación": p_actual['Locacion'],
                "Este (X)": f"{p_actual['ESTE']:,}",
                "Norte (Y)": f"{p_actual['NORTE']:,}",
                "Dist. Tramo (Km)": dist_tramo if i > 0 else "---",
                "Pozos Asociados": p_actual['Pozos']
            })
            
        st.table(pd.DataFrame(datos_tabla))
        
        col1, col2 = st.columns(2)
        col1.metric("Distancia Total de la Campaña", f"{total_km:.2f} Km")
        col2.info("Nota: Los cálculos se basan en distancia euclidiana entre coordenadas planas.")
else:
    st.info("💡 Por favor, ingresa los nombres de las locaciones en el panel de la izquierda para comenzar.")

# Opcional: Ver toda la base de datos cargada
if st.checkbox("Ver base de datos completa de coordenadas"):
    st.dataframe(df_maestro)
