import streamlit as st
import pandas as pd
import numpy as np
import re
import os

# Configuración de la página
st.set_page_config(page_title="Logística Rubiales & CASE", layout="wide")

@st.cache_data
def cargar_datos(file_name):
    # 1. Verificación de existencia del archivo
    if not os.path.exists(file_name):
        return None, f"❌ Archivo '{file_name}' no encontrado en el repositorio."
    
    try:
        # 2. Lectura del CSV (usando latin-1 para evitar errores de tildes/ñ)
        df = pd.read_csv(file_name, encoding='latin-1')
        
        # 3. Limpieza y Normalización de columnas
        # Pasamos todo a mayúsculas y quitamos espacios para que sea fácil buscar
        df.columns = df.columns.astype(str).str.strip().str.upper()
        cols = df.columns.tolist()
        
        # Buscamos las columnas que contengan las palabras clave (Flexibilidad total)
        col_loc = next((c for c in cols if 'LOC' in c), None)
        col_este = next((c for c in cols if 'ESTE' in c), None)
        col_norte = next((c for c in cols if 'NORTE' in c), None)
        col_pozo = next((c for c in cols if 'POZO' in c), None)
        
        if all([col_loc, col_este, col_norte, col_pozo]):
            # Creamos un DataFrame estandarizado
            df_std = pd.DataFrame()
            df_std['LOCACION'] = df[col_loc].astype(str).str.strip().str.upper()
            df_std['ESTE'] = pd.to_numeric(df[col_este], errors='coerce')
            df_std['NORTE'] = pd.to_numeric(df[col_norte], errors='coerce')
            df_std['POZO'] = df[col_pozo].astype(str)
            
            # Agrupamos por Locación para tener una sola coordenada por clúster
            df_final = df_std.dropna(subset=['ESTE', 'NORTE']).groupby('LOCACION').agg({
                'ESTE': 'first',
                'NORTE': 'first',
                'POZO': lambda x: ', '.join(x.unique())
            }).reset_index()
            
            return df_final, f"✅ Archivo '{file_name}' cargado correctamente."
        else:
            return None, f"⚠️ Error en columnas. Encontradas: {cols}. Asegúrate de que existan LOCACION, ESTE, NORTE y POZO."
            
    except Exception as e:
        return None, f"❌ Error al procesar: {str(e)}"

def calcular_distancia(p1, p2):
    dist = np.sqrt((p2['ESTE'] - p1['ESTE'])**2 + (p2['NORTE'] - p1['NORTE'])**2)
    return round(dist / 1000, 2)

# --- INTERFAZ ---

st.title("🚜 Sistema Logístico de Movilización")

# Nombre exacto según tu imagen 2 de GitHub
nombre_archivo = "COORDENADAS_GOR.xlsx" 
df_maestro, estado = cargar_datos(nombre_archivo)

# Visor de estado
st.sidebar.header("📁 Estado de Datos")
if df_maestro is not None:
    st.sidebar.success(estado)
    st.sidebar.info(f"Locaciones disponibles: {len(df_maestro)}")
else:
    st.sidebar.error(estado)
    st.stop()

# Entrada de Ruta
st.sidebar.header("📍 Plan de Ruta")
input_ruta = st.sidebar.text_area("Ingresa las Locaciones (una por línea):", 
                                 placeholder="CASE0015\nAGRIO-1\nCASE0019")

if input_ruta:
    nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', input_ruta) if n.strip()]
    puntos_ruta = []
    
    for i, nombre in enumerate(nombres_busqueda):
        match = df_maestro[df_maestro['LOCACION'] == nombre]
        if not match.empty:
            puntos_ruta.append({
                'Orden': i + 1,
                'Locacion': nombre,
                'ESTE': match.iloc[0]['ESTE'],
                'NORTE': match.iloc[0]['NORTE'],
                'Pozos': match.iloc[0]['POZO']
            })
        else:
            st.sidebar.warning(f"No encontrada: {nombre}")

    if puntos_ruta:
        st.write("### 📊 Itinerario de Coordenadas Planas")
        
        datos_tabla = []
        total_km = 0
        
        for i in range(len(puntos_ruta)):
            p = puntos_ruta[i]
            dist = 0
            if i > 0:
                dist = calcular_distancia(puntos_ruta[i-1], p)
                total_km += dist
            
            datos_tabla.append({
                "Secuencia": p['Orden'],
                "Locación": p['Locacion'],
                "Coordenada X (Este)": f"{p['ESTE']:,.2f}",
                "Coordenada Y (Norte)": f"{p['NORTE']:,.2f}",
                "KM Tramo": dist if i > 0 else "Punto de Partida",
                "Pozos": p['Pozos']
            })
        
        st.table(pd.DataFrame(datos_tabla))
        st.metric("Distancia Total Estimada", f"{total_km:.2f} Km")
else:
    st.info("Escribe los nombres de los clústeres en la izquierda para generar la tabla de coordenadas.")

# Ver base completa por si acaso
if st.checkbox("Mostrar base de datos cargada"):
    st.dataframe(df_maestro)
