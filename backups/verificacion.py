import streamlit as st
import google.generativeai as genai

# Configuración de la página
st.set_page_config(page_title="Test API Gemini", page_icon="🤖")

st.title("🔍 Verificador de Modelos Gemini")
st.write("Ingresa tu API Key para ver qué modelos tienes activos y disponibles.")

# Input para la API Key (tipo password para que no se vea)
api_key = st.text_input("Pega tu Google AI Studio API Key aquí:", type="password")

if api_key:
    try:
        # Configuración de la API
        genai.configure(api_key=api_key)
        
        st.success("✅ API Key configurada correctamente.")
        
        st.subheader("Modelos Disponibles (generateContent):")
        
        # Tu lógica original adaptada
        modelos_encontrados = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos_encontrados.append(m.name)
                # Mostramos en la interfaz principal y en la barra lateral como querías
                st.code(m.name) 
                st.sidebar.write(f"🔹 {m.name}")

        if not modelos_encontrados:
            st.warning("No se encontraron modelos con capacidad de generación.")
            
    except Exception as e:
        st.error(f"❌ Error al conectar o listar modelos: {e}")
        st.info("Verifica que tu API Key sea correcta y tenga permisos.")
else:
    st.info("👆 Esperando API Key...")