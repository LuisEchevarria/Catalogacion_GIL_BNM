import streamlit as st
import json
import os
import hashlib
import fitz
from PIL import Image
import io
import pandas as pd
from pathlib import Path
import logging
from typing import Dict, Optional, List, Tuple
import time
import base64
import re
import requests

# --- CONFIGURACIÓN ---
DB_JSON = "biblioteca_temas.json"
DB_EXCEL = "reporte_libros.xlsx"
BACKUP_DIR = "backups"
LOG_FILE = "app.log"

# Configurar logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
    errors='replace'
)

st.set_page_config(
    page_title="AI Book Classifier",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- UTILIDADES ---
def create_backup(db_dict: dict) -> None:
    """Crea backup incremental de la DB."""
    Path(BACKUP_DIR).mkdir(exist_ok=True)
    backup_path = Path(BACKUP_DIR) / f"backup_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(db_dict, f, indent=2, ensure_ascii=False)

def load_db() -> dict:
    """Carga DB con validación."""
    if not os.path.exists(DB_JSON):
        return {}
    
    try:
        with open(DB_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("DB corrupta: no es un diccionario")
        return data
    except Exception as e:
        logging.error(f"Error cargando DB: {e}")
        st.error(f"Error cargando base de datos: {e}")
        return {}

@st.cache_data(ttl=300)
def generate_excel_bytes(db_dict: dict) -> bytes:
    """Genera Excel en memoria."""
    df_data = []
    for h, info in db_dict.items():
        df_data.append({
            "ID_Hash": h[:8],
            "Archivo_Original": info.get('filename', 'N/A'),
            "Título": info.get('titulo', 'Sin título'),
            "Autor": info.get('autor', 'Desconocido'),
            "Temas": ", ".join(info.get('temas', [])),
            "Página Portada": info.get('cover_page', 0),
            "Descripción Portada": info.get('datos_portada', "N/A")[:200]
        })
    
    df = pd.DataFrame(df_data)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Biblioteca')
        worksheet = writer.sheets['Biblioteca']
        for idx, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
    
    buffer.seek(0)
    return buffer.getvalue()

def save_and_sync(db_dict: dict) -> bool:
    """Guarda JSON y Excel."""
    try:
        create_backup(db_dict)
        
        temp_json = f"{DB_JSON}.tmp"
        with open(temp_json, 'w', encoding='utf-8') as f:
            json.dump(db_dict, f, indent=2, ensure_ascii=False)
        
        os.replace(temp_json, DB_JSON)
        
        excel_bytes = generate_excel_bytes(db_dict)
        with open(DB_EXCEL, 'wb') as f:
            f.write(excel_bytes)
        
        logging.info(f"DB sincronizada exitosamente. {len(db_dict)} libros.")
        return True
        
    except Exception as e:
        logging.error(f"Error guardando DB: {e}")
        st.error(f"Error al guardar: {e}")
        return False

# --- EXTRACCIÓN INTELIGENTE DE METADATOS ---
def extract_author_from_metadata(metadata: dict) -> Optional[str]:
    """
    Extrae el autor de múltiples campos de metadatos.
    Busca en: author, subject, keywords, creator
    """
    author = None
    
    # Campo author directo
    if metadata.get('author') and metadata['author'].strip():
        author = metadata['author'].strip()
        logging.info(f"  ✓ Autor en campo 'author': {author}")
        return author
    
    # Campo subject (común en PDFs de bibliotecas)
    if metadata.get('subject'):
        subject = metadata['subject'].strip()
        # Buscar patrones como "Arriaga, Isaac 1890-1921"
        # Extraer nombre antes de fechas
        match = re.search(r'([A-Za-zÁ-ÿ\s,]+)\s*\d{4}', subject)
        if match:
            author = match.group(1).strip().rstrip(',').strip()
            logging.info(f"  ✓ Autor extraído de 'subject': {author}")
            return author
        
        # Si subject tiene formato "Apellido, Nombre"
        if ',' in subject and not any(kw in subject.lower() for kw in ['tema', 'topic', 'subject']):
            parts = subject.split(',')
            if len(parts) >= 2:
                author = f"{parts[1].strip()} {parts[0].strip()}"
                logging.info(f"  ✓ Autor reformateado de 'subject': {author}")
                return author
    
    # Campo keywords
    if metadata.get('keywords'):
        keywords = metadata['keywords'].strip()
        # Buscar nombres propios en keywords
        match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', keywords)
        if match:
            author = match.group(1)
            logging.info(f"  ✓ Autor extraído de 'keywords': {author}")
            return author
    
    # Campo creator
    if metadata.get('creator') and metadata['creator'].strip():
        author = metadata['creator'].strip()
        logging.info(f"  ✓ Autor en campo 'creator': {author}")
        return author
    
    return None

def extract_author_from_title(title: str) -> Optional[str]:
    """
    Intenta extraer el autor del título.
    Ej: "Isaac Arriaga: trabajos premiados..." → "Isaac Arriaga"
    """
    if not title or title == "No disponible":
        return None
    
    # Patrón 1: "Nombre Apellido: resto del título"
    match = re.match(r'^([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]+){1,3})\s*[:;]', title)
    if match:
        author = match.group(1).strip()
        logging.info(f"  ✓ Autor extraído del título: {author}")
        return author
    
    # Patrón 2: "Apellido, Nombre"
    match = re.match(r'^([A-ZÁÉÍÓÚ][a-záéíóúñ]+),\s+([A-ZÁÉÍÓÚ][a-záéíóúñ]+)', title)
    if match:
        author = f"{match.group(2)} {match.group(1)}"
        logging.info(f"  ✓ Autor extraído del título (invertido): {author}")
        return author
    
    return None

def extract_pdf_metadata(pdf_bytes: bytes, filename: str) -> dict:
    """Extrae metadatos completos del PDF."""
    metadata = {
        'title': None,
        'author': None,
        'subject': None,
        'keywords': None,
        'creator': None
    }
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_metadata = doc.metadata
        
        if pdf_metadata:
            metadata['title'] = pdf_metadata.get('title', '').strip()
            metadata['author'] = pdf_metadata.get('author', '').strip()
            metadata['subject'] = pdf_metadata.get('subject', '').strip()
            metadata['keywords'] = pdf_metadata.get('keywords', '').strip()
            metadata['creator'] = pdf_metadata.get('creator', '').strip()
            
            logging.info(f"Metadatos extraídos de {filename}:")
            logging.info(f"  Title: {metadata['title']}")
            logging.info(f"  Author: {metadata['author']}")
            logging.info(f"  Subject: {metadata['subject']}")
            logging.info(f"  Keywords: {metadata['keywords']}")
            logging.info(f"  Creator: {metadata['creator']}")
        
        doc.close()
    except Exception as e:
        logging.warning(f"Error extrayendo metadatos de {filename}: {e}")
    
    return metadata

# --- DETECCIÓN INTELIGENTE DE PORTADA ---
def analyze_page_content(page) -> dict:
    """Analiza el contenido de una página con mayor detalle."""
    try:
        images = page.get_images()
        image_count = len(images)
        
        text = page.get_text()
        text_length = len(text.strip())
        words = text.strip().split()
        word_count = len(words)
        
        has_paragraphs = text_length > 500
        
        text_lower = text.lower()
        cover_indicators = [
            'título', 'title', 'autor', 'author', 'editorial', 'publisher',
            'edición', 'edition', 'isbn', 'universidad', 'university',
            'tesis', 'thesis', 'dissertation', 'biblioteca', 'library',
            'departamento', 'department', 'secretaria', 'ministry',
            'instituto', 'institute', 'trabajos', 'premiados', 'concurso',
            'religión', 'religion', 'ediciones', 'editions'
        ]
        has_cover_keywords = any(keyword in text_lower for keyword in cover_indicators)
        
        is_just_cover_photo = image_count > 0 and word_count < 5
        
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height
        
        total_image_area = 0
        for img_info in images:
            try:
                bbox = page.get_image_bbox(img_info)
                if bbox:
                    img_area = (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)
                    total_image_area += img_area
            except:
                pass
        
        image_coverage = (total_image_area / page_area) if page_area > 0 else 0
        
        lines = text.split('\n')
        non_empty_lines = [l.strip() for l in lines if l.strip()]
        has_structure = len(non_empty_lines) > 3 and len(non_empty_lines) < 25
        
        has_many_numbers = sum(c.isdigit() for c in text) > (text_length * 0.3)
        
        return {
            'image_count': image_count,
            'text_length': text_length,
            'word_count': word_count,
            'has_paragraphs': has_paragraphs,
            'has_cover_keywords': has_cover_keywords,
            'is_just_cover_photo': is_just_cover_photo,
            'image_coverage': image_coverage,
            'has_structure': has_structure,
            'has_many_numbers': has_many_numbers,
            'text': text
        }
    except Exception as e:
        logging.error(f"Error analizando contenido de página: {e}")
        return None

def calculate_cover_score(page_num: int, analysis: dict) -> float:
    """Scoring ultra-mejorado para detectar portadas reales."""
    score = 0.0
    
    if page_num == 0 and analysis['is_just_cover_photo']:
        score -= 150
        logging.debug(f"Página {page_num}: Pasta sin texto (penalización -150)")
    
    if analysis['has_paragraphs']:
        score -= 40
        logging.debug(f"Página {page_num}: Muchos párrafos (-40)")
    
    if analysis['has_many_numbers'] and analysis['word_count'] > 50:
        score -= 30
        logging.debug(f"Página {page_num}: Muchos números (-30)")
    
    if analysis['has_cover_keywords']:
        score += 60
        logging.debug(f"Página {page_num}: Keywords de portada (+60)")
    
    if analysis['has_structure']:
        score += 45
        logging.debug(f"Página {page_num}: Estructura de portada (+45)")
    
    if 5 <= analysis['word_count'] <= 150:
        score += 35
        logging.debug(f"Página {page_num}: Cantidad ideal de palabras (+35)")
    
    if 1 <= analysis['image_count'] <= 3 and analysis['word_count'] > 10:
        score += 25
        logging.debug(f"Página {page_num}: Balance imagen/texto (+25)")
    
    if 0.2 <= analysis['image_coverage'] <= 0.75:
        score += 20
        logging.debug(f"Página {page_num}: Cobertura balanceada (+20)")
    
    if page_num in [1, 2, 3]:
        score += 20
    elif page_num in [4, 5]:
        score += 10
    
    logging.debug(f"Página {page_num}: Score final = {score:.1f}")
    return score

def find_best_cover_page(pdf_bytes: bytes, filename: str, max_pages: int = 8) -> Tuple[Optional[Image.Image], int]:
    """Búsqueda ultra-mejorada de portada."""
    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if doc.page_count == 0:
            raise ValueError(f"{filename} no tiene páginas")
        
        pages_to_check = min(max_pages, doc.page_count)
        candidates = []
        
        logging.info(f"=== Analizando {filename} ({pages_to_check} de {doc.page_count} páginas) ===")
        
        for page_num in range(pages_to_check):
            try:
                page = doc[page_num]
                analysis = analyze_page_content(page)
                if analysis is None:
                    continue
                
                score = calculate_cover_score(page_num, analysis)
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                
                candidates.append({
                    'page_num': page_num,
                    'score': score,
                    'pixmap': pix,
                    'analysis': analysis
                })
                
                logging.info(
                    f"Página {page_num}: score={score:.1f}, "
                    f"palabras={analysis['word_count']}, "
                    f"imágenes={analysis['image_count']}, "
                    f"keywords={analysis['has_cover_keywords']}"
                )
                
            except Exception as e:
                logging.warning(f"Error procesando página {page_num} de {filename}: {e}")
                continue
        
        if not candidates:
            raise ValueError(f"No se pudieron procesar páginas de {filename}")
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        best = candidates[0]
        
        if best['score'] < -50:
            logging.warning(f"Score muy bajo ({best['score']}), buscando alternativa...")
            for candidate in candidates:
                if candidate['analysis']['word_count'] > 10:
                    best = candidate
                    logging.info(f"Usando página {best['page_num']} como alternativa")
                    break
        
        logging.info(f"✅ Mejor portada: Página {best['page_num']} (score={best['score']:.1f})")
        
        img = Image.open(io.BytesIO(best['pixmap'].tobytes("png")))
        
        if img.size[0] * img.size[1] > 8_000_000:
            img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        
        return img, best['page_num']
        
    except Exception as e:
        logging.error(f"Error buscando portada de {filename}: {e}")
        st.error(f"❌ Error procesando {filename}: {e}")
        return None, -1
        
    finally:
        if doc:
            doc.close()

# --- PARSEO JSON ---
def extract_json_from_text(text: str) -> Optional[dict]:
    """Extrae JSON de texto de forma robusta."""
    try:
        # Intento 1: Carga directa (gracias a response_format funciona el 99% de veces)
        return json.loads(text)
    except:
        pass

    # Limpieza agresiva de Markdown
    cleaned = re.sub(r'```json', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned)
    cleaned = cleaned.strip()
    
    # Intento 2: Buscar el primer { y el último }
    try:
        start = cleaned.find('{')
        end = cleaned.rfind('}') + 1
        if start != -1 and end != 0:
            json_str = cleaned[start:end]
            return json.loads(json_str)
    except:
        pass

    # Intento 3: Reparación de comillas simples (común en Python strings)
    try:
        fixed = cleaned.replace("'", '"')
        return json.loads(fixed)
    except:
        return None

# --- ANÁLISIS CON OPENAI MEJORADO ---
def analyze_with_openai(img: Image.Image, api_key: str, filename: str, metadata: dict = None, max_retries: int = 3) -> dict:
    """Análisis con GPT-4o forzando modo JSON y mejor fallback."""
    
    buffered = io.BytesIO()
    
    max_dimension = 2048
    if img.size[0] > max_dimension or img.size[1] > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    img.save(buffered, format="PNG", optimize=True, quality=95)
    img_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # PROMPT (Mismo prompt, no hace falta cambiarlo)
    prompt = """Analiza esta portada de documento/libro escaneado histórico.

CONTEXTO IMPORTANTE:
- Documento antiguo (o moderno) escaneado
- Calidad de escaneo variable
- Texto en español antiguo o con ortografía diferente
- Puede tener texto manuscrito o tipografía antigua

TU TAREA CRÍTICA:
1. **AUTOR** - BUSCA EL NOMBRE DE LA PERSONA:
   - Mira TODA la imagen, especialmente el centro y parte superior
   - El autor puede aparecer como: "NOMBRE APELLIDO", "Apellido, Nombre", o simplemente en grande
   - Si ves un nombre de persona en la portada, ESE ES EL AUTOR
   - Si el título menciona un nombre (ej: "Isaac Arriaga: trabajos..."), ESE ES EL AUTOR
   - NO respondas "No disponible" si hay CUALQUIER nombre visible

2. **TÍTULO** - El título completo del documento

3. **TEMAS** - 3 a 5 categorías/temas académicas relevantes

4. **DESCRIPCIÓN** - Tipo de documento y contexto

REGLA CRÍTICA PARA AUTOR:
- Si ves "ISAAC ARRIAGA" en grande → autor: "Isaac Arriaga"
- Si ves "Juan Carlos Pérez Guerrero" → autor: "Juan Carlos Pérez Guerrero"
- Si título dice "Apellido, Nombre: obra..." → autor: "Nombre Apellido"
- SOLO usa "No disponible" si NO HAY ningún nombre de persona en TODA la imagen


RESPONDE SOLO CON ESTE JSON (sin markdown):
{
  "titulo": "título exacto completo",
  "autor": "NOMBRE DEL AUTOR (busca cuidadosamente)",
  "temas": ["tema1", "tema2", "tema3"],
  "datos_portada": "descripción breve"
}"""
    
    # Agregar pistas de metadatos al prompt
    if metadata:
        metadata_hint = "\n\n🔍 PISTAS ADICIONALES DEL PDF:"
        if metadata.get('title'):
            metadata_hint += f"\n- Título en metadatos: {metadata['title']}"
        if metadata.get('subject'):
            metadata_hint += f"\n- Subject: {metadata['subject']}"
        if metadata.get('author'):
            metadata_hint += f"\n- Autor en metadatos: {metadata['author']}"    
        prompt += metadata_hint
    
    payload = {
        "model": "gpt-4o",
        "response_format": {"type": "json_object"},  # <--- CAMBIO CRÍTICO: FUERZA JSON PURO
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_base64}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1500,
        "temperature": 0.2
    }
    
    for attempt in range(max_retries):
        try:
            logging.debug(f"Intento {attempt + 1}/{max_retries} para {filename}")
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 429:
                time.sleep(5)
                continue
            
            response.raise_for_status()
            
            result_text = response.json()['choices'][0]['message']['content']
            result = extract_json_from_text(result_text)
            
            if result is None:
                raise ValueError("No se pudo parsear JSON")
            
            # Post-procesamiento
            if isinstance(result.get('temas'), list):
                result['temas'] = [str(t).strip().title() for t in result['temas'][:5] if t]
            else:
                result['temas'] = ["Sin clasificar"]
            
            # Recuperación de autor si GPT falla pero tenemos metadatos
            if result.get('autor') in ['No disponible', 'N/A', 'Desconocido', '', None] and metadata:
                extracted_author = extract_author_from_metadata(metadata)
                if extracted_author:
                    result['autor'] = extracted_author
                    result['_author_source'] = 'metadata_fallback'

            return result
            
        except Exception as e:
            logging.error(f"Error OpenAI intento {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                # CAMBIO CRÍTICO: FALLBACK INTELIGENTE
                # Si falla OpenAI, usamos los metadatos del PDF en lugar de devolver "Error"
                fallback_title = metadata.get('title') if metadata else f"[Error Procesamiento] {filename}"
                fallback_author = extract_author_from_metadata(metadata) if metadata else "Error"
                
                return {
                    "titulo": fallback_title or filename,
                    "autor": fallback_author or "Revisar Manualmente",
                    "temas": ["Requiere Revisión"],
                    "datos_portada": f"Falló IA, datos de metadatos. Error original: {str(e)[:100]}"
                }
        
        time.sleep(1)
    
    return {"titulo": "Error Fatal", "autor": "Error", "temas": [], "datos_portada": "Error desconocido"}

# --- NUEVA FUNCIÓN: ELIMINAR LIBRO ---
def delete_book(file_hash: str, db: dict) -> bool:
    """Elimina un libro de la base de datos."""
    try:
        if file_hash in db:
            book_title = db[file_hash].get('titulo', 'Sin título')
            del db[file_hash]
            if save_and_sync(db):
                logging.info(f"Libro eliminado: {book_title} ({file_hash[:8]})")
                return True
        return False
    except Exception as e:
        logging.error(f"Error eliminando libro {file_hash[:8]}: {e}")
        return False

# --- INTERFAZ STREAMLIT ---
def main():
    st.title("📚 Clasificador Inteligente de Libros")
    st.caption("🎯 Extracción Inteligente de Temas de Libros")
    
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        st.info("🤖 **GPT-4o** + Extracción Multi-Fuente de Autores")
        
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="https://platform.openai.com/api-keys"
        )
        
        api_valid = False
        if api_key:
            if api_key.startswith("sk-"):
                api_valid = True
                st.success("✓ API Key válida")
            else:
                st.error("⚠ API Key debe empezar con 'sk-'")
        
        with st.expander("⚙️ Configuración Avanzada"):
            max_pages_scan = st.slider(
                "Páginas a escanear",
                min_value=3,
                max_value=12,
                value=8
            )
            
            delay_between_requests = st.slider(
                "Delay entre requests",
                min_value=1,
                max_value=10,
                value=2
            )
            
            extract_metadata = st.checkbox(
                "Extraer metadatos del PDF",
                value=True,
                help="Busca autor en propiedades del PDF"
            )
        
        st.divider()
        
        if st.button("📄 Ver Logs"):
            if os.path.exists(LOG_FILE):
                try:
                    with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        last_40 = ''.join(lines[-40:])
                        st.code(last_40, language='log')
                except Exception as e:
                    st.error(f"Error: {e}")
        
        st.divider()
        
        db = load_db()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📖 Libros", len(db))
        with col2:
            all_temas = []
            for book in db.values():
                all_temas.extend(book.get('temas', []))
            st.metric("🏷️ Temas", len(set(all_temas)))
        
        st.divider()
        
        if os.path.exists(DB_EXCEL):
            excel_bytes = generate_excel_bytes(db)
            st.download_button(
                label="📥 Excel",
                data=excel_bytes,
                file_name=f"biblioteca_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        st.download_button(
            label="📥 JSON",
            data=json.dumps(db, indent=2, ensure_ascii=False),
            file_name=f"biblioteca_{pd.Timestamp.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    st.success("""
    - 🔍 Busca autor en imagen con GPT-4o
    - 📄 Extrae de metadatos PDF (author, subject, creator)
    - 📖 Detecta del título ("Isaac Arriaga: obra...")
    - 🎯 Triple validación para no perder autores
    """)
    
    uploaded_files = st.file_uploader(
        "📤 Subir PDFs",
        type="pdf",
        accept_multiple_files=True
    )
    
    if uploaded_files and api_valid:
        if st.button("🚀 Procesar", type="primary", use_container_width=True):
            process_books(
                uploaded_files, 
                api_key, 
                db, 
                max_pages_scan,
                delay_between_requests,
                extract_metadata
            )
    elif uploaded_files and not api_valid:
        st.warning("⚠️ Ingresa API Key")
    
    display_library(db)

def process_books(uploaded_files, api_key: str, db: dict, max_pages: int, delay: int, extract_metadata: bool):
    """Procesa libros."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    
    stats = {"new": 0, "skipped": 0, "failed": 0, "authors_recovered": 0, "reanalyzed": 0}
    
    for idx, uploaded_file in enumerate(uploaded_files):
        progress = (idx + 1) / len(uploaded_files)
        progress_bar.progress(progress)
        status_text.text(f"📖 {idx + 1}/{len(uploaded_files)}: {uploaded_file.name}")
        
        try:
            file_bytes = uploaded_file.read()
            file_hash = hashlib.md5(file_bytes).hexdigest()
            
            # Verificar si existe y si el usuario quiere re-analizar
            already_exists = file_hash in db
            
            if already_exists:
                # Mostrar mensaje que ya existe con opción de re-analizar
                with results_container:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.info(f"⏭️ **{uploaded_file.name}** ya procesado")
                    with col2:
                        # Botón para re-analizar este archivo específico
                        if st.button("🔄 Re-analizar", key=f"reanalyze_{file_hash}"):
                            st.session_state[f'force_reanalyze_{file_hash}'] = True
                            st.rerun()
                
                # Si no se solicitó re-análisis, continuar con el siguiente
                if not st.session_state.get(f'force_reanalyze_{file_hash}', False):
                    stats["skipped"] += 1
                    continue
                else:
                    # Limpiar la bandera
                    st.session_state[f'force_reanalyze_{file_hash}'] = False
                    stats["reanalyzed"] += 1
            
            metadata = None
            if extract_metadata:
                metadata = extract_pdf_metadata(file_bytes, uploaded_file.name)
            
            img, cover_page = find_best_cover_page(file_bytes, uploaded_file.name, max_pages)
            
            if img is None:
                stats["failed"] += 1
                continue
            
            result = analyze_with_openai(img, api_key, uploaded_file.name, metadata)
            
            result['filename'] = uploaded_file.name
            result['cover_page'] = cover_page
            result['fecha_procesado'] = pd.Timestamp.now().isoformat()
            result['ai_provider'] = "OpenAI GPT-4o FINAL"
            
            if metadata and (metadata.get('title') or metadata.get('author') or metadata.get('subject')):
                result['pdf_metadata'] = {
                    'title': metadata.get('title'),
                    'author': metadata.get('author'),
                    'subject': metadata.get('subject')
                }
            
            if '_author_source' in result:
                stats["authors_recovered"] += 1
            
            db[file_hash] = result
            
            if not already_exists:
                stats["new"] += 1
            
            with results_container:
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.image(img, width=150)
                with col2:
                    if "[Error" in result['titulo']:
                        st.error(f"❌ **{uploaded_file.name}**")
                        st.caption(f"Error: {result['datos_portada']}")
                    else:
                        status_emoji = "🔄" if already_exists else "✅"
                        st.success(f"{status_emoji} **{result['titulo']}**")
                        author_label = f"👤 {result['autor']}"
                        if '_author_source' in result:
                            author_label += f" (de {result['_author_source']})"
                        st.caption(f"{author_label} | 📄 Pág. {cover_page}")
                        st.caption(f"🏷️ {', '.join(result['temas'])}")
            
            if idx < len(uploaded_files) - 1:
                time.sleep(delay)
        
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            with results_container:
                st.error(f"💥 **{uploaded_file.name}**: {e}")
            stats["failed"] += 1
    
    if stats["new"] > 0 or stats["reanalyzed"] > 0:
        if save_and_sync(db):
            st.balloons()
            st.success(f"""
            ✅ Completado
            - ✅ Nuevos: {stats["new"]}
            - 🔄 Re-analizados: {stats["reanalyzed"]}
            - 🔍 Autores recuperados: {stats["authors_recovered"]}
            - ⏭️ Omitidos: {stats["skipped"]}
            - ❌ Fallidos: {stats["failed"]}
            """)
            st.cache_data.clear()
    else:
        st.info("No se agregaron libros nuevos")
    
    progress_bar.empty()
    status_text.empty()

def display_library(db: dict):
    """Muestra biblioteca con opciones de gestión."""
    st.divider()
    st.subheader("📖 Biblioteca")
    
    if not db:
        st.info("👆 Sube PDFs")
        return
    
    df_display = pd.DataFrame([
        {
            "Hash": h[:8],
            "Título": v.get('titulo', 'N/A'),
            "Autor": v.get('autor', 'N/A'),
            "Temas": ", ".join(v.get('temas', [])),
            "Pág": v.get('cover_page', 0),
            "Archivo": v.get('filename', 'N/A')
        }
        for h, v in db.items()
    ])
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search = st.text_input("🔍 Buscar", placeholder="Título, autor...")
        if search:
            mask = df_display.apply(
                lambda row: search.lower() in row.to_string().lower(),
                axis=1
            )
            df_display = df_display[mask]
    
    with col2:
        all_temas = set()
        for book in db.values():
            all_temas.update(book.get('temas', []))
        
        tema_filter = st.selectbox(
            "Tema",
            ["Todos"] + sorted(list(all_temas))
        )
        
        if tema_filter != "Todos":
            df_display = df_display[
                df_display['Temas'].str.contains(tema_filter, case=False, na=False)
            ]
    
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.caption(f"Mostrando {len(df_display)} de {len(db)} libros")
    
    # --- NUEVA SECCIÓN: GESTIÓN DE LIBROS ---
    st.divider()
    st.subheader("🗑️ Gestión de Libros")
    
    # Selector de libro a eliminar
    book_options = {f"{v.get('titulo', 'Sin título')} - {h[:8]}": h 
                    for h, v in db.items()}
    
    if book_options:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            selected_book = st.selectbox(
                "Seleccionar libro para eliminar:",
                options=["-- Seleccionar libro --"] + list(book_options.keys())
            )
        
        with col2:
            if selected_book != "-- Seleccionar libro --":
                if st.button("🗑️ Eliminar", type="primary"):
                    file_hash = book_options[selected_book]
                    if delete_book(file_hash, db):
                        st.success(f"✅ Libro eliminado: {selected_book}")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Error al eliminar el libro")

if __name__ == "__main__":
    main()